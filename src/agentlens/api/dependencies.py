"""FastAPI dependency boundaries for auth, rate limiting, and RBAC permissions."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from fastapi import Request

from .auth import AuthContext
from .errors import GatewayError


def require_auth(request: Request) -> AuthContext:
    """Authenticate a Bearer key before canonical payload reconstruction."""
    header = request.headers.get("authorization")
    if header is None:
        raise GatewayError(
            code="unauthorized",
            message="Authentication is required.",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = header.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1] or len(parts[1]) > 4096:
        raise GatewayError(
            code="unauthorized",
            message="Authentication is invalid.",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    context = cast(
        AuthContext | None,
        request.app.state.gateway.authenticator.authenticate(parts[1]),
    )
    if context is None:
        raise GatewayError(
            code="unauthorized",
            message="Authentication is invalid.",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    decision = request.app.state.gateway.rate_limiter.allow(context.key_id)
    if not decision.allowed:
        headers = {"Retry-After": str(decision.retry_after or 1)}
        raise GatewayError(
            code="rate_limited",
            message="Rate limit exceeded.",
            status_code=429,
            headers=headers,
        )
    return context


def require_permission(permission: str) -> Callable[[Request], AuthContext]:
    """Dependency factory checking that the authenticated key holds the required RBAC permission."""

    def dependency(request: Request) -> AuthContext:
        auth = require_auth(request)
        if permission not in auth.permissions:
            raise GatewayError(
                code="forbidden",
                message=f"Access denied: missing required permission '{permission}'.",
                status_code=403,
            )
        return auth

    return dependency
