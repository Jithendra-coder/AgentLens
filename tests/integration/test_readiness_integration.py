"""Integration tests  GA Platform Readiness & Certification API."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-readiness-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-readiness-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
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


def test_platform_readiness_and_ga_certification_api() -> None:
    app = make_test_app()

    async def run():
        # 1. Audit platform readiness
        ready_res = await send_request(
            app,
            "GET",
            "/v1/system/readiness",
        )
        assert ready_res.status_code == 200
        ready_data = ready_res.json()
        assert ready_data["overall_status"] == "GA_CERTIFIED"
        assert ready_data["readiness_score"] == 100.0
        assert ready_data["total_subsystems"] == 10
        assert ready_data["ready_subsystems"] == 10
        assert len(ready_data["subsystems"]) == 10

        # 2. Issue official GA certification
        cert_res = await send_request(
            app,
            "POST",
            "/v1/system/certify",
        )
        assert cert_res.status_code == 200
        cert_data = cert_res.json()
        assert cert_data["certification_status"] == "GA_CERTIFIED"
        assert cert_data["readiness_score"] == 100.0
        assert len(cert_data["digital_seal"]) == 64

    asyncio.run(run())
