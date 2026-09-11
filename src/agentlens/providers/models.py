"""Model provider domain models, request/response structures, and profile definitions ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """Standardized chat message structure across model providers."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("ChatMessage role cannot be empty.")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Reported token consumption for a model generation request."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Provider-agnostic request definition for LLM generation."""

    messages: tuple[ChatMessage, ...]
    model: str
    temperature: float = 0.0
    max_tokens: int = 2048
    json_schema: dict[str, Any] | None = None
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("ModelRequest must contain at least one ChatMessage.")
        if not self.model:
            raise ValueError("ModelRequest model cannot be empty.")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Normalized response returned from any LLM provider."""

    content: str
    finish_reason: str = "stop"
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    provider: str = "unknown"
    model: str = ""
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Configured provider endpoint and model configuration with fallback priority."""

    profile_id: UUID = field(default_factory=uuid4)
    project_id: str = ""
    name: str = ""
    provider_type: str = "openai"  # "openai" | "anthropic" | "gemini" | "custom_http"
    model_name: str = ""
    base_url: str | None = None
    secret_name: str = ""  # Key name in SecretStore
    priority: int = 1  # 1 is highest priority
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ProviderProfile name cannot be empty.")
        if not self.model_name:
            raise ValueError("ProviderProfile model_name cannot be empty.")
        if self.priority < 1:
            raise ValueError("ProviderProfile priority must be >= 1.")
