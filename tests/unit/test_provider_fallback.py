"""Unit tests for ProviderFallbackEngine resilience and secret resolution."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agentlens.providers.fallback import ProviderFallbackEngine
from agentlens.providers.models import (
    ChatMessage,
    ModelRequest,
    ModelResponse,
    ProviderProfile,
    TokenUsage,
)
from agentlens.providers.protocol import (
    ModelProvider,
    ProviderError,
    ProviderRateLimitError,
)
from agentlens.security.secrets import InMemorySecretStore


class MockFailingProvider(ModelProvider):
    provider_name = "mock_failing"

    def generate(
        self,
        request: ModelRequest,
        api_key: str,
        base_url: str | None = None,
    ) -> ModelResponse:
        raise ProviderRateLimitError("Rate limit exceeded on primary provider", status_code=429)


class MockSuccessfulProvider(ModelProvider):
    provider_name = "mock_successful"

    def generate(
        self,
        request: ModelRequest,
        api_key: str,
        base_url: str | None = None,
    ) -> ModelResponse:
        return ModelResponse(
            content=f"Fallback response to: {request.messages[0].content}",
            finish_reason="stop",
            usage=TokenUsage(input_tokens=5, output_tokens=10, total_tokens=15),
            latency_ms=85.0,
            provider="mock_successful",
            model=request.model,
        )


def test_fallback_engine_failover_flow() -> None:
    secret_store = InMemorySecretStore(master_secret="test-master-secret-123456789012")
    secret_store.store_secret("proj-fallback", "key-primary", "openai", "primary-api-key")
    secret_store.store_secret("proj-fallback", "key-secondary", "anthropic", "secondary-api-key")

    engine = ProviderFallbackEngine(secret_store=secret_store)
    engine.register_adapter("openai", MockFailingProvider())
    engine.register_adapter("anthropic", MockSuccessfulProvider())

    p1 = ProviderProfile(
        profile_id=uuid4(),
        project_id="proj-fallback",
        name="Primary OpenAI",
        provider_type="openai",
        model_name="gpt-4o",
        secret_name="key-primary",
        priority=1,
    )
    p2 = ProviderProfile(
        profile_id=uuid4(),
        project_id="proj-fallback",
        name="Backup Claude",
        provider_type="anthropic",
        model_name="claude-3-5-sonnet-20241022",
        secret_name="key-secondary",
        priority=2,
    )

    req = ModelRequest(
        messages=(ChatMessage(role="user", content="Ping"),),
        model="gpt-4o",
    )

    res = engine.generate_with_fallback(
        project_id="proj-fallback",
        profiles=[p1, p2],
        request=req,
    )

    assert res.provider == "mock_successful"
    assert res.model == "claude-3-5-sonnet-20241022"
    assert "Fallback response" in res.content


def test_fallback_engine_all_failing_raises_error() -> None:
    engine = ProviderFallbackEngine()
    engine.register_adapter("openai", MockFailingProvider())

    p1 = ProviderProfile(
        profile_id=uuid4(),
        project_id="proj-fail",
        name="Only Provider",
        provider_type="openai",
        model_name="gpt-4o",
        priority=1,
    )

    req = ModelRequest(
        messages=(ChatMessage(role="user", content="Ping"),),
        model="gpt-4o",
    )

    with pytest.raises(ProviderError, match="All model providers in fallback chain failed"):
        engine.generate_with_fallback(
            project_id="proj-fail",
            profiles=[p1],
            request=req,
        )
