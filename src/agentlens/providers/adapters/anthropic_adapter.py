"""Anthropic Claude API adapter ."""

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

DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProviderAdapter:
    """Adapter for Anthropic Claude Messages API."""

    provider_name = "anthropic"

    def generate(
        self,
        request: ModelRequest,
        api_key: str,
        base_url: str | None = None,
    ) -> ModelResponse:
        url = f"{(base_url or DEFAULT_ANTHROPIC_BASE_URL).rstrip('/')}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": DEFAULT_ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        system_prompt: str | None = None
        messages_payload: list[dict[str, str]] = []
        for m in request.messages:
            if m.role.lower() == "system":
                system_prompt = (system_prompt + "\n" + m.content) if system_prompt else m.content
            else:
                role = "assistant" if m.role.lower() == "assistant" else "user"
                messages_payload.append({"role": role, "content": m.content})

        if not messages_payload:
            messages_payload.append({"role": "user", "content": "Hello"})

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages_payload,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_prompt is not None:
            payload["system"] = system_prompt

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=request.timeout_seconds) as client:
                res = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"Anthropic request timed out after {request.timeout_seconds}s",
                provider=self.provider_name,
            ) from exc
        except Exception as exc:
            raise ProviderError(
                f"Anthropic connection error: {exc}",
                provider=self.provider_name,
            ) from exc

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        if res.status_code == 429:
            raise ProviderRateLimitError(
                res.text or "Anthropic rate limit exceeded (HTTP 429)",
                status_code=429,
                provider=self.provider_name,
            )
        if res.status_code in (401, 403):
            raise ProviderAuthenticationError(
                res.text or "Anthropic authentication failed (HTTP 401/403)",
                status_code=res.status_code,
                provider=self.provider_name,
            )
        if not res.is_success:
            raise ProviderError(
                f"Anthropic API error ({res.status_code}): {res.text}",
                status_code=res.status_code,
                provider=self.provider_name,
            )

        data = res.json()
        content_blocks = data.get("content") or []
        content = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        finish_reason = str(data.get("stop_reason") or "end_turn")

        raw_usage = data.get("usage") or {}
        input_tokens = int(raw_usage.get("input_tokens") or 0)
        output_tokens = int(raw_usage.get("output_tokens") or 0)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
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
