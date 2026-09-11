"""Integration tests for Continuous Monitoring & Aggregated Health Service API."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.monitoring.repository import InMemoryMonitoringRepository
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-monitoring-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-mon-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    mon_repo = InMemoryMonitoringRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        monitoring_repository=mon_repo,
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


def test_continuous_monitoring_and_health_rollup_workflow() -> None:
    app = make_test_app()

    async def run():
        # 1. Create a production monitor
        mon_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-mon-test/monitors",
            json_body={
                "name": "Live Assistant Production Monitor",
                "sampling_rate": 0.20,
            },
        )
        assert mon_res.status_code == 200
        mon_data = mon_res.json()
        monitor_id = mon_data["monitor_id"]

        # 2. Record a health snapshot (healthy metrics)
        snap_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-mon-test/monitors/{monitor_id}/snapshots",
            json_body={
                "mean_quality_score": 0.94,
                "p95_latency_ms": 400.0,
                "error_rate": 0.01,
                "total_spans_evaluated": 250,
            },
        )
        assert snap_res.status_code == 200
        snap_data = snap_res.json()
        assert snap_data["health_index"] >= 85.0
        assert snap_data["health_status"] == "healthy"

        # 3. Check aggregate project health summary
        health_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-mon-test/monitors/health",
        )
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert health_data["overall_health_status"] == "healthy"
        assert health_data["monitors_count"] == 1
        assert health_data["active_monitors"] == 1

        # 4. List snapshots
        snaps_res = await send_request(
            app,
            "GET",
            f"/v1/projects/proj-mon-test/monitors/{monitor_id}/snapshots",
        )
        assert snaps_res.status_code == 200
        snapshots = snaps_res.json()["snapshots"]
        assert len(snapshots) == 1
        assert snapshots[0]["total_spans_evaluated"] == 250

    asyncio.run(run())
