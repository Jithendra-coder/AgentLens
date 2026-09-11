"""Integration tests  Quality Baselines and Statistical Drift Intelligence API."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.rbac import InMemoryRbacRepository, Role
from agentlens.regression.drift.repository import InMemoryDriftRepository

MASTER_KEY = "test-drift-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-drift-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    drift_repo = InMemoryDriftRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        drift_repository=drift_repo,
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


def test_drift_detection_and_regression_workflow() -> None:
    app = make_test_app()

    async def run():
        # 1. Create a quality baseline (mean=0.90, std=0.03)
        base_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-drift-test/drift/baselines",
            json_body={
                "name": "Core Reasoning Baseline",
                "metric_name": "quality_score",
                "baseline_mean": 0.90,
                "baseline_std": 0.03,
                "window_size": 50,
            },
        )
        assert base_res.status_code == 200
        base_data = base_res.json()
        baseline_id = base_data["baseline_id"]

        # 2. Ingest regressed values
        detect_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-drift-test/drift/detect",
            json_body={
                "baseline_id": baseline_id,
                "observed_values": [0.70, 0.72, 0.71, 0.69, 0.73],
                "z_alert_threshold": 2.0,
            },
        )
        assert detect_res.status_code == 200
        detect_data = detect_res.json()
        assert detect_data["drift_type"] == "quality_drop"
        assert detect_data["is_alert"] is True
        assert detect_data["z_score"] < -2.0

        # 3. List observations
        obs_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-drift-test/drift/observations",
        )
        assert obs_res.status_code == 200
        observations = obs_res.json()["observations"]
        assert len(observations) == 1
        assert observations[0]["is_alert"] is True
        assert observations[0]["drift_type"] == "quality_drop"

    asyncio.run(run())
