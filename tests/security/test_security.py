"""security boundaries that do not require external provider credentials."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import GatewayConfig, InMemoryApiKeyAuthenticator, InMemoryTraceSink, create_app
from agentlens.api.rate_limit import RedisRateLimiter


def test_redis_limiter_falls_back_without_raw_key_material() -> None:
    limiter = RedisRateLimiter(
        redis_url="redis://127.0.0.1:56398/15",
        max_requests=1,
        window_seconds=60,
    )
    assert limiter.allow("secret-project-api-key").allowed
    assert limiter.health == "degraded"
    assert "secret-project-api-key" not in repr(limiter._client)


def test_local_health_does_not_expose_credentials() -> None:
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key="m12-key-not-real", key_id="m12-key", project_id="m12")
    app = create_app(
        config=GatewayConfig(max_request_bytes=1024),
        authenticator=auth,
        sink=InMemoryTraceSink(),
    )

    async def run() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/health/ready")

    response = asyncio.run(run())
    assert response.status_code == 200
    assert "m12-key-not-real" not in response.text
