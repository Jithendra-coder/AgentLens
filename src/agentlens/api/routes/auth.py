"""Enterprise authentication and session management routes (JWT / OIDC / SAML)."""

from __future__ import annotations

import os
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.rbac.models import ALL_PERMISSIONS, Role
from agentlens.security.jwt_tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_access_token,
)
from agentlens.security.users import UserRepository

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    auth_provider: str = Field(default="local")
    external_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


def _get_jwt_secret() -> str:
    return os.environ.get("AGENTLENS_JWT_SECRET", "agentlens-jwt-secret-dev-insecure-32-chars")


def _get_user_repo(request: Request) -> UserRepository:
    repo = getattr(request.app.state.gateway, "user_repository", None)
    if repo is None:
        raise GatewayError(
            code="auth_unavailable",
            message="User repository is not configured.",
            status_code=503,
        )
    return cast(UserRepository, repo)


@router.post("/v1/auth/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    user_repo = _get_user_repo(request)
    user = user_repo.get_or_create_user(
        email=str(payload.email),
        name=payload.name,
        auth_provider=payload.auth_provider,
        external_id=payload.external_id,
    )

    raw_refresh_token, refresh_hash = generate_refresh_token()
    user_agent = request.headers.get("user-agent")
    session = user_repo.create_session(
        user_id=user.user_id,
        refresh_token_hash=refresh_hash,
        user_agent=user_agent,
    )

    jwt_secret = _get_jwt_secret()
    access_token = create_access_token(
        user_id=str(user.user_id),
        email=user.email,
        secret_key=jwt_secret,
        roles=[Role.ORG_ADMIN.value],
        expires_in_seconds=3600,
    )

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh_token,
        "token_type": "bearer",
        "expires_in": 3600,
        "user": {
            "user_id": str(user.user_id),
            "email": user.email,
            "name": user.name,
            "auth_provider": user.auth_provider,
            "session_id": str(session.session_id),
        },
    }


@router.post("/v1/auth/refresh")
async def refresh_token(payload: RefreshRequest, request: Request) -> dict[str, Any]:
    user_repo = _get_user_repo(request)
    refresh_hash = hash_refresh_token(payload.refresh_token)
    session = user_repo.get_session(refresh_hash)

    if session is None or not session.is_valid:
        raise GatewayError(
            code="invalid_refresh_token",
            message="Refresh token is expired, revoked, or invalid.",
            status_code=401,
        )

    user = user_repo.get_user_by_id(session.user_id)
    if user is None:
        raise GatewayError(code="user_not_found", message="User not found.", status_code=404)

    jwt_secret = _get_jwt_secret()
    access_token = create_access_token(
        user_id=str(user.user_id),
        email=user.email,
        secret_key=jwt_secret,
        roles=[Role.ORG_ADMIN.value],
        expires_in_seconds=3600,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 3600,
    }


@router.post("/v1/auth/logout")
async def logout(payload: LogoutRequest, request: Request) -> dict[str, Any]:
    user_repo = _get_user_repo(request)
    refresh_hash = hash_refresh_token(payload.refresh_token)
    session = user_repo.get_session(refresh_hash)

    if session is not None:
        user_repo.revoke_session(session.session_id)

    return {"status": "logged_out"}


@router.get("/v1/auth/me")
async def get_current_user_profile(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    # Check if Bearer JWT
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ")[1]
        jwt_secret = _get_jwt_secret()
        try:
            claims = verify_access_token(raw_token, jwt_secret)
            user_repo = _get_user_repo(request)
            user = user_repo.get_user_by_id(UUID(claims["sub"]))
            if user:
                return {
                    "user_id": str(user.user_id),
                    "email": user.email,
                    "name": user.name,
                    "auth_provider": user.auth_provider,
                    "role": claims.get("roles", ["org_admin"])[0],
                    "permissions": sorted(list(ALL_PERMISSIONS)),
                }
        except Exception:
            pass

    # Fallback to standard AuthContext from API key
    auth: AuthContext = require_auth(request)
    return {
        "user_id": auth.key_id,
        "email": f"{auth.project_id}@agentlens.internal",
        "name": f"API Key ({auth.key_id})",
        "auth_provider": "api_key",
        "role": auth.role,
        "permissions": sorted(list(auth.permissions)),
    }
