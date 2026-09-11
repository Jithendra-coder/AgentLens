"""Integration tests  Automated RCA & Failure Clustering API."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.rbac import InMemoryRbacRepository, Role
from agentlens.rca.repository import InMemoryRCARepository

MASTER_KEY = "test-rca-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-rca-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    rca_repo = InMemoryRCARepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        rca_repository=rca_repo,
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


def test_rca_and_failure_clustering_workflow() -> None:
    app = make_test_app()

    async def run():
        # 1. Diagnose a rate limit failure
        diag_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-rca-test/rca/diagnose",
            json_body={
                "error_message": "Rate limit exceeded (HTTP 429) for gpt-4o",
                "http_status": 429,
                "latency_ms": 150.0,
            },
        )
        assert diag_res.status_code == 200
        diag_data = diag_res.json()
        assert diag_data["failure_category"] == "provider_error"
        assert "Upstream provider" in diag_data["root_cause_summary"]
        rca_id = diag_data["rca_id"]

        # 2. Get specific RCA report
        get_res = await send_request(
            app,
            "GET",
            f"/v1/projects/proj-rca-test/rca/reports/{rca_id}",
        )
        assert get_res.status_code == 200
        assert get_res.json()["failure_category"] == "provider_error"

        # 3. List RCA reports
        list_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-rca-test/rca/reports",
        )
        assert list_res.status_code == 200
        reports = list_res.json()["reports"]
        assert len(reports) == 1

        # 4. List failure clusters
        clust_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-rca-test/rca/clusters",
        )
        assert clust_res.status_code == 200
        clusters = clust_res.json()["clusters"]
        assert len(clusters) == 1
        assert clusters[0]["occurrences_count"] == 1

    asyncio.run(run())
