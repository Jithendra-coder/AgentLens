"""Unit tests  Model Provider domain models and adapters."""

from __future__ import annotations

import pytest

from agentlens.providers.adapters.anthropic_adapter import AnthropicProviderAdapter
from agentlens.providers.adapters.gemini_adapter import GeminiProviderAdapter
from agentlens.providers.adapters.openai_adapter import OpenAIProviderAdapter
from agentlens.providers.models import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    ProviderProfile,
    TokenUsage,
)


def test_model_request_and_profile_invariants() -> None:
    msg = ChatMessage(role="user", content="Hello world")
    assert msg.role == "user"

    with pytest.raises(ValueError, match="ChatMessage role cannot be empty"):
        ChatMessage(role="", content="Hello")

    with pytest.raises(ValueError, match="at least one ChatMessage"):
        ModelRequest(messages=(), model="gpt-4o")

    with pytest.raises(ValueError, match="temperature must be between"):
        ModelRequest(messages=(msg,), model="gpt-4o", temperature=3.0)

    with pytest.raises(ValueError, match="priority must be >= 1"):
        ProviderProfile(name="Test", model_name="gpt-4o", priority=0)


def test_provider_adapters_instantiation_and_metadata() -> None:
    openai_adapter = OpenAIProviderAdapter()
    assert openai_adapter.provider_name == "openai"

    anthropic_adapter = AnthropicProviderAdapter()
    assert anthropic_adapter.provider_name == "anthropic"

    gemini_adapter = GeminiProviderAdapter()
    assert gemini_adapter.provider_name == "gemini"


def test_token_usage_and_model_response() -> None:
    usage = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
    assert usage.total_tokens == 30

    res = ModelResponse(
        content="Test content",
        finish_reason="stop",
        usage=usage,
        latency_ms=120.5,
        provider="openai",
        model="gpt-4o",
    )
    assert res.content == "Test content"
    assert res.latency_ms == 120.5
