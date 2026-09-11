"""Integration tests  Model Provider layer and API endpoints."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.providers.fallback import ProviderFallbackEngine
from agentlens.providers.models import ModelRequest, ModelResponse, TokenUsage
from agentlens.providers.protocol import ModelProvider
from agentlens.rbac import InMemoryRbacRepository, Role
from agentlens.security.secrets import InMemorySecretStore

MASTER_KEY = "test-providers-master-key"


class MockEchoProvider(ModelProvider):
    provider_name = "openai"

    def generate(
        self,
        request: ModelRequest,
        api_key: str,
        base_url: str | None = None,
    ) -> ModelResponse:
        return ModelResponse(
            content=f"Echo: {request.messages[0].content} (key_len={len(api_key)})",
            finish_reason="stop",
            usage=TokenUsage(input_tokens=8, output_tokens=12, total_tokens=20),
            latency_ms=45.0,
            provider="openai",
            model=request.model,
        )


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-providers",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    secret_store = InMemorySecretStore(master_secret="test-master-secret-123456789012")
    secret_store.store_secret(
        project_id="proj-providers",
        name="test-openai-key",
        provider="openai",
        plaintext="sk-test-mock-openai-key-secret-999",
    )

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        secret_store=secret_store,
    )
    return app


async def send_request(
    app,
    method: str,
    path: str,
    *,
    api_key: str | None = MASTER_KEY,
    json_body: object | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request_headers = dict(headers or {})
    if api_key is not None:
        request_headers.setdefault("Authorization", f"Bearer {api_key}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, headers=request_headers, json=json_body)


def test_provider_endpoints_with_mock_adapter() -> None:
    app = make_test_app()

    # Monkey patch adapter on ProviderFallbackEngine for integration test
    original_init = ProviderFallbackEngine.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._adapters["openai"] = MockEchoProvider()

    ProviderFallbackEngine.__init__ = patched_init  # type: ignore

    async def run():
        # 1. Test provider connectivity endpoint
        test_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-providers/providers/test",
            json_body={
                "provider": {
                    "name": "OpenAI Primary",
                    "provider_type": "openai",
                    "model_name": "gpt-4o",
                    "secret_name": "test-openai-key",
                    "priority": 1,
                    "enabled": True,
                },
            },
        )
        assert test_res.status_code == 200
        test_data = test_res.json()
        assert test_data["status"] == "connected"
        assert "Echo: Ping" in test_data["sample_output"]
        assert test_data["provider"] == "openai"

        # 2. Test generation endpoint with fallback profile
        gen_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-providers/providers/generate",
            json_body={
                "messages": [{"role": "user", "content": "What is AI Agent evaluation?"}],
                "profiles": [
                    {
                        "name": "OpenAI Primary",
                        "provider_type": "openai",
                        "model_name": "gpt-4o",
                        "secret_name": "test-openai-key",
                        "priority": 1,
                        "enabled": True,
                    }
                ],
                "temperature": 0.0,
                "max_tokens": 100,
            },
        )
        assert gen_res.status_code == 200
        gen_data = gen_res.json()
        assert "Echo: What is AI Agent evaluation?" in gen_data["content"]
        assert gen_data["usage"]["total_tokens"] == 20

    try:
        asyncio.run(run())
    finally:
        ProviderFallbackEngine.__init__ = original_init
