"""Model Provider and Generation API endpoints ."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.providers.fallback import ProviderFallbackEngine
from agentlens.providers.models import (
    ChatMessage,
    ModelRequest,
    ProviderProfile,
)
from agentlens.providers.protocol import ProviderError
from agentlens.security.secrets import SecretStore

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class ChatMessageInput(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1)


class ProviderProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    provider_type: str = Field(min_length=1, max_length=32)
    model_name: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=512)
    secret_name: str = Field(default="", max_length=255)
    priority: int = Field(default=1, ge=1)
    enabled: bool = Field(default=True)


class GenerateRequest(BaseModel):
    messages: list[ChatMessageInput] = Field(min_length=1)
    profiles: list[ProviderProfileInput] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0.0)


class TestProviderRequest(BaseModel):
    provider: ProviderProfileInput


def _secret_store(request: Request) -> SecretStore | None:
    return getattr(request.app.state.gateway, "secret_store", None)


@router.post("/v1/projects/{project_id}/providers/test")
async def test_provider_connectivity(
    project_id: str,
    body: TestProviderRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    secret_store = _secret_store(request)
    engine = ProviderFallbackEngine(secret_store=secret_store)

    prof = body.provider
    profile_obj = ProviderProfile(
        profile_id=uuid4(),
        project_id=project_id,
        name=prof.name,
        provider_type=prof.provider_type,
        model_name=prof.model_name,
        base_url=prof.base_url,
        secret_name=prof.secret_name,
        priority=1,
        enabled=True,
    )

    test_request = ModelRequest(
        messages=(ChatMessage(role="user", content="Ping. Respond with 'pong'."),),
        model=prof.model_name,
        temperature=0.0,
        max_tokens=16,
        timeout_seconds=10.0,
    )

    try:
        response = engine.generate_with_fallback(
            project_id=project_id,
            profiles=[profile_obj],
            request=test_request,
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "connected",
                "latency_ms": response.latency_ms,
                "provider": response.provider,
                "model": response.model,
                "sample_output": response.content,
            },
        )
    except ProviderError as exc:
        raise GatewayError(
            code="provider_connection_failed",
            message=str(exc),
            status_code=502,
        ) from exc


@router.post("/v1/projects/{project_id}/providers/generate")
async def generate_with_model(
    project_id: str,
    body: GenerateRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    secret_store = _secret_store(request)
    engine = ProviderFallbackEngine(secret_store=secret_store)

    profiles = [
        ProviderProfile(
            profile_id=uuid4(),
            project_id=project_id,
            name=p.name,
            provider_type=p.provider_type,
            model_name=p.model_name,
            base_url=p.base_url,
            secret_name=p.secret_name,
            priority=p.priority,
            enabled=p.enabled,
        )
        for p in body.profiles
    ]

    messages = tuple(ChatMessage(role=m.role, content=m.content) for m in body.messages)
    req = ModelRequest(
        messages=messages,
        model=body.profiles[0].model_name,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        timeout_seconds=body.timeout_seconds,
    )

    try:
        res = engine.generate_with_fallback(
            project_id=project_id,
            profiles=profiles,
            request=req,
        )
        return JSONResponse(
            status_code=200,
            content={
                "content": res.content,
                "finish_reason": res.finish_reason,
                "usage": {
                    "input_tokens": res.usage.input_tokens,
                    "output_tokens": res.usage.output_tokens,
                    "total_tokens": res.usage.total_tokens,
                },
                "latency_ms": res.latency_ms,
                "provider": res.provider,
                "model": res.model,
            },
        )
    except ProviderError as exc:
        raise GatewayError(
            code="provider_generation_failed",
            message=str(exc),
            status_code=502,
        ) from exc
