"""Integration tests for Multi-Channel Alerting & Incident Intelligence API."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.alerting.repository import InMemoryAlertingRepository
from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-alerting-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-alert-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    alert_repo = InMemoryAlertingRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        alerting_repository=alert_repo,
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


def test_alerting_and_incident_lifecycle_workflow() -> None:
    app = make_test_app()

    async def run():
        # 1. Create alert rule
        rule_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-alert-test/alerts/rules",
            json_body={
                "name": "Prod Slack Alert Rule",
                "trigger_type": "drift_alert",
                "channel_type": "slack",
                "destination_url": "https://hooks.slack.com/services/prod",
                "cooldown_seconds": 300,
            },
        )
        assert rule_res.status_code == 200
        rule_data = rule_res.json()
        assert rule_data["name"] == "Prod Slack Alert Rule"

        # 2. Trigger incident
        inc_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-alert-test/alerts/incidents",
            json_body={
                "title": "Severe Quality Drift in RAG Engine",
                "details": "Z-score dropped below -2.5 on faithfulness metric",
                "trigger_type": "drift_alert",
                "severity": "P1",
            },
        )
        assert inc_res.status_code == 200
        inc_data = inc_res.json()
        incident_id = inc_data["incident_id"]
        assert inc_data["status"] == "open"
        assert len(inc_data["dispatches"]) == 1
        assert inc_data["dispatches"][0]["dispatched"] is True

        # 3. Acknowledge incident
        ack_res = await send_request(
            app,
            "PATCH",
            f"/v1/projects/proj-alert-test/alerts/incidents/{incident_id}",
            json_body={
                "status": "acknowledged",
                "user": "oncall@agentlens.io",
            },
        )
        assert ack_res.status_code == 200
        ack_data = ack_res.json()
        assert ack_data["status"] == "acknowledged"
        assert ack_data["acknowledged_by"] == "oncall@agentlens.io"

        # 4. Resolve incident
        res_res = await send_request(
            app,
            "PATCH",
            f"/v1/projects/proj-alert-test/alerts/incidents/{incident_id}",
            json_body={
                "status": "resolved",
            },
        )
        assert res_res.status_code == 200
        res_data = res_res.json()
        assert res_data["status"] == "resolved"
        assert res_data["resolved_at"] is not None

        # 5. List incidents
        list_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-alert-test/alerts/incidents",
        )
        assert list_res.status_code == 200
        incidents = list_res.json()["incidents"]
        assert len(incidents) == 1
        assert incidents[0]["status"] == "resolved"

    asyncio.run(run())
