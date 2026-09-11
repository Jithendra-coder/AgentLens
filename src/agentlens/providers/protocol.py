"""Model provider protocol and error hierarchy ."""

from __future__ import annotations

from typing import Protocol

from agentlens.providers.models import ModelRequest, ModelResponse


class ProviderError(Exception):
    """Base exception for model provider errors."""

    def __init__(self, message: str, status_code: int | None = None, provider: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider = provider


class ProviderRateLimitError(ProviderError):
    """Raised when provider returns HTTP 429 rate limit / quota exceeded."""


class ProviderAuthenticationError(ProviderError):
    """Raised on invalid API key or permission denial (HTTP 401/403)."""


class ProviderTimeoutError(ProviderError):
    """Raised when a request exceeds configured timeout."""


class ModelProvider(Protocol):
    """Protocol for unified LLM provider adapters."""

    provider_name: str

    def generate(
        self,
        request: ModelRequest,
        api_key: str,
        base_url: str | None = None,
    ) -> ModelResponse:
        """Execute model generation synchronously or raise a ProviderError."""
        ...
