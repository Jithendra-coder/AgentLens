"""Integration tests  Immutable Governance & Compliance API."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.governance.repository import InMemoryGovernanceRepository
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-governance-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-gov-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    gov_repo = InMemoryGovernanceRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        governance_repository=gov_repo,
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


def test_governance_audit_and_compliance_workflow() -> None:
    app = make_test_app()

    async def run():
        # 1. Record an audit event
        ev_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-gov-test/governance/audit",
            json_body={
                "action": "model.route.update",
                "resource_type": "routing_rule",
                "resource_id": "rule-456",
                "payload": '{"min_quality":0.90}',
            },
        )
        assert ev_res.status_code == 200
        ev_data = ev_res.json()
        assert len(ev_data["event_hash"]) == 64

        # 2. Verify audit chain integrity
        audit_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-gov-test/governance/audit",
        )
        assert audit_res.status_code == 200
        audit_data = audit_res.json()
        assert audit_data["is_valid"] is True
        assert audit_data["verification_status"] == "VERIFIED"
        assert audit_data["total_events"] == 1

        # 3. Create retention policy
        pol_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-gov-test/governance/policies",
            json_body={
                "name": "SOC2 365-Day Telemetry Retention",
                "retention_days": 365,
                "auto_redact_pii": True,
            },
        )
        assert pol_res.status_code == 200
        pol_data = pol_res.json()
        assert pol_data["retention_days"] == 365

        # 4. Generate signed compliance export bundle
        export_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-gov-test/governance/export",
        )
        assert export_res.status_code == 200
        export_data = export_res.json()
        assert export_data["status"] == "ATTESTED"
        assert len(export_data["digital_signature"]) == 64
        assert export_data["total_audit_events"] == 1

    asyncio.run(run())
