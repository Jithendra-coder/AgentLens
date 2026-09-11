"""Integration tests  production deployment, health probes, and correlation IDs."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.cli import main as cli_main


@pytest.fixture
def client() -> TestClient:
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(api_key="test-api-key-12345", key_id="key-1", project_id="proj-1")
    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=InMemoryTraceSink(),
    )
    return TestClient(app)


def test_health_live_endpoint(client: TestClient) -> None:
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_health_startup_endpoint(client: TestClient) -> None:
    res = client.get("/health/startup")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "agentlens-api", "initialized": True}


def test_health_ready_endpoint(client: TestClient) -> None:
    res = client.get("/health/ready")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_request_and_correlation_id_headers(client: TestClient) -> None:
    # Client sends explicit correlation ID
    res = client.get("/health/live", headers={"x-correlation-id": "client-correlation-uuid-999"})
    assert res.status_code == 200
    assert res.headers.get("x-correlation-id") == "client-correlation-uuid-999"
    assert res.headers.get("x-request-id") is not None

    # Client sends no correlation ID -> correlation ID equals generated request ID
    res2 = client.get("/health/live")
    assert res2.status_code == 200
    req_id = res2.headers.get("x-request-id")
    corr_id = res2.headers.get("x-correlation-id")
    assert req_id is not None
    assert corr_id == req_id


def test_cli_config_check() -> None:
    with patch("sys.argv", ["agentlens", "config", "check"]):
        code = cli_main(["config", "check"])
        assert code == 0
