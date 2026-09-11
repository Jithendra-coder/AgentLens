"""Integration tests  platform observability, metrics endpoints, and system overview."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink

API_KEY = "test-m14-api-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(api_key=API_KEY, key_id="key-1", project_id="proj-1")
    return create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=InMemoryTraceSink(),
    )


async def send_request(
    app,
    method: str,
    path: str,
    *,
    api_key: str | None = API_KEY,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request_headers = dict(headers or {})
    if api_key is not None:
        request_headers.setdefault("Authorization", f"Bearer {api_key}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, headers=request_headers)


def test_prometheus_metrics_endpoint() -> None:
    app = make_test_app()

    async def run():
        await send_request(app, "GET", "/health/live", api_key=None)
        await send_request(app, "GET", "/health/live", api_key=None)
        return await send_request(app, "GET", "/metrics", api_key=None)

    res = asyncio.run(run())
    assert res.status_code == 200
    assert "text/plain" in res.headers.get("content-type", "")
    assert "agentlens_api_requests_total" in res.text
    assert "agentlens_api_request_duration_seconds" in res.text


def test_system_metrics_authenticated() -> None:
    app = make_test_app()

    async def run():
        unauth = await send_request(app, "GET", "/v1/system/metrics", api_key=None)
        auth = await send_request(app, "GET", "/v1/system/metrics", api_key=API_KEY)
        return unauth, auth

    res_unauth, res_auth = asyncio.run(run())
    assert res_unauth.status_code in (401, 403)
    assert res_auth.status_code == 200

    data = res_auth.json()
    assert "api_latency_summary" in data
    assert "worker_latency_summary" in data
    assert "timestamp" in data


def test_system_overview_authenticated() -> None:
    app = make_test_app()

    async def run():
        return await send_request(app, "GET", "/v1/system/overview", api_key=API_KEY)

    res = asyncio.run(run())
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "agentlens-platform"
    assert "infrastructure" in data
    assert "database" in data["infrastructure"]
    assert "redis" in data["infrastructure"]
    assert "queues" in data
    assert "evaluation_depth" in data["queues"]
    assert "workers" in data
    assert "fleet" in data["workers"]
    assert "telemetry" in data
