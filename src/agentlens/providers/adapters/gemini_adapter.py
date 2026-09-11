"""Google Gemini API adapter ."""

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

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProviderAdapter:
    """Adapter for Google Gemini generateContent REST API."""

    provider_name = "gemini"

    def generate(
        self,
        request: ModelRequest,
        api_key: str,
        base_url: str | None = None,
    ) -> ModelResponse:
        base = (base_url or DEFAULT_GEMINI_BASE_URL).rstrip("/")
        model_name = (
            request.model if request.model.startswith("models/") else f"models/{request.model}"
        )
        url = f"{base}/{model_name}:generateContent?key={api_key}"

        contents: list[dict[str, Any]] = []
        for m in request.messages:
            role = "model" if m.role.lower() in ("assistant", "model") else "user"
            contents.append({
                "role": role,
                "parts": [{"text": m.content}],
            })

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=request.timeout_seconds) as client:
                res = client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"Gemini request timed out after {request.timeout_seconds}s",
                provider=self.provider_name,
            ) from exc
        except Exception as exc:
            raise ProviderError(
                f"Gemini connection error: {exc}",
                provider=self.provider_name,
            ) from exc

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        if res.status_code == 429:
            raise ProviderRateLimitError(
                res.text or "Gemini rate limit exceeded (HTTP 429)",
                status_code=429,
                provider=self.provider_name,
            )
        if res.status_code in (400, 401, 403) and "API_KEY_INVALID" in res.text:
            raise ProviderAuthenticationError(
                res.text or "Gemini API key invalid (HTTP 401/403)",
                status_code=res.status_code,
                provider=self.provider_name,
            )
        if not res.is_success:
            raise ProviderError(
                f"Gemini API error ({res.status_code}): {res.text}",
                status_code=res.status_code,
                provider=self.provider_name,
            )

        data = res.json()
        candidates = data.get("candidates") or []
        first_cand = candidates[0] if candidates else {}
        parts = ((first_cand.get("content") or {}).get("parts") or [])
        content = "".join(p.get("text", "") for p in parts)
        finish_reason = str(first_cand.get("finishReason") or "STOP")

        raw_meta = data.get("usageMetadata") or {}
        input_tokens = int(raw_meta.get("promptTokenCount") or 0)
        output_tokens = int(raw_meta.get("candidatesTokenCount") or 0)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=int(raw_meta.get("totalTokenCount") or (input_tokens + output_tokens)),
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
