"""Encrypted Model Provider Secret Store management routes ."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_permission
from agentlens.api.errors import GatewayError
from agentlens.rbac.models import Permission
from agentlens.security.secrets import SecretStore

router = APIRouter()
KEYS_MANAGE_DEP = Depends(require_permission(Permission.KEYS_MANAGE.value))


class StoreSecretRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=64)  # e.g. openai, anthropic, gemini
    secret_value: str = Field(min_length=1)


def _get_secret_store(request: Request) -> SecretStore:
    store = getattr(request.app.state.gateway, "secret_store", None)
    if store is None:
        raise GatewayError(
            code="secrets_unavailable",
            message="Secret store is not configured.",
            status_code=503,
        )
    return cast(SecretStore, store)


@router.post("/v1/projects/{project_id}/secrets")
async def store_secret(
    project_id: str,
    payload: StoreSecretRequest,
    request: Request,
    auth: AuthContext = KEYS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    store = _get_secret_store(request)
    meta = store.store_secret(
        project_id=project_id,
        name=payload.name,
        provider=payload.provider.lower(),
        plaintext=payload.secret_value,
    )
    return {
        "secret_id": str(meta.secret_id),
        "project_id": meta.project_id,
        "name": meta.name,
        "provider": meta.provider,
        "key_version": meta.key_version,
        "created_at": meta.created_at.isoformat(),
        "updated_at": meta.updated_at.isoformat(),
        "is_encrypted": True,
    }


@router.get("/v1/projects/{project_id}/secrets")
async def list_secrets(
    project_id: str,
    request: Request,
    auth: AuthContext = KEYS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    store = _get_secret_store(request)
    secrets = store.list_secrets(project_id)
    return {
        "secrets": [
            {
                "secret_id": str(s.secret_id),
                "project_id": s.project_id,
                "name": s.name,
                "provider": s.provider,
                "key_version": s.key_version,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "is_encrypted": True,
            }
            for s in secrets
        ]
    }


@router.delete("/v1/projects/{project_id}/secrets/{name}")
async def delete_secret(
    project_id: str,
    name: str,
    request: Request,
    auth: AuthContext = KEYS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    store = _get_secret_store(request)
    success = store.delete_secret(project_id, name)
    if not success:
        raise GatewayError(code="not_found", message="Secret not found.", status_code=404)
    return {"deleted": True, "project_id": project_id, "name": name}
