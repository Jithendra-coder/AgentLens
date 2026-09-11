"""OpenAI and OpenAI-compatible API adapter ."""

from __future__ import annotations

import time
from typing import Any

import httpx

from agentlens.providers.models import ModelRequest, ModelResponse, TokenUsage
from agentlens.providers.protocol import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIProviderAdapter:
    """Adapter for OpenAI and OpenAI-compatible endpoints (e.g. vLLM, Ollama, TGI)."""

    provider_name = "openai"

    def generate(
        self,
        request: ModelRequest,
        api_key: str,
        base_url: str | None = None,
    ) -> ModelResponse:
        url = f"{(base_url or DEFAULT_OPENAI_BASE_URL).rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": request.json_schema, "name": "output_schema"},
            }

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=request.timeout_seconds) as client:
                res = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"OpenAI request timed out after {request.timeout_seconds}s",
                provider=self.provider_name,
            ) from exc
        except Exception as exc:
            raise ProviderError(
                f"OpenAI connection error: {exc}",
                provider=self.provider_name,
            ) from exc

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        if res.status_code == 429:
            raise ProviderRateLimitError(
                res.text or "Rate limit exceeded (HTTP 429)",
                status_code=429,
                provider=self.provider_name,
            )
        if res.status_code in (401, 403):
            raise ProviderAuthenticationError(
                res.text or "Authentication failed (HTTP 401/403)",
                status_code=res.status_code,
                provider=self.provider_name,
            )
        if not res.is_success:
            raise ProviderError(
                f"OpenAI API error ({res.status_code}): {res.text}",
                status_code=res.status_code,
                provider=self.provider_name,
            )

        data = res.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = str(msg.get("content") or "")
        finish_reason = str(choice.get("finish_reason") or "stop")

        raw_usage = data.get("usage") or {}
        usage = TokenUsage(
            input_tokens=int(raw_usage.get("prompt_tokens") or 0),
            output_tokens=int(raw_usage.get("completion_tokens") or 0),
            total_tokens=int(raw_usage.get("total_tokens") or 0),
        )

        return ModelResponse(
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency_ms,
            provider=self.provider_name,
            model=request.model,
            raw_response=data,
        )
