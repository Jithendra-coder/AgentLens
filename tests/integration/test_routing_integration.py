"""Integration tests for Adaptive Model Routing and API routes."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.rbac import InMemoryRbacRepository, Role
from agentlens.routing.repository import InMemoryRoutingRepository

MASTER_KEY = "test-routing-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-routing-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    routing_repo = InMemoryRoutingRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        routing_repository=routing_repo,
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


def test_adaptive_routing_workflow() -> None:
    app = make_test_app()

    async def run():
        # 1. Create a specialized routing rule for code tasks
        create_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-routing-test/routing/rules",
            json_body={
                "name": "Code Generation Routing Policy",
                "task_type": "code",
                "min_quality_score": 0.85,
                "tier_priority": ["gpt-4o-mini", "claude-3-5-haiku", "gpt-4o", "claude-3-5-sonnet"],
                "fallback_model": "claude-3-5-sonnet",
            },
        )
        assert create_res.status_code == 200
        rule_data = create_res.json()
        assert rule_data["name"] == "Code Generation Routing Policy"
        assert rule_data["task_type"] == "code"

        # 2. Route a simple general question -> should pick cost-effective model
        simple_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-routing-test/routing/route",
            json_body={"prompt": "What is the boiling point of water?"},
        )
        assert simple_res.status_code == 200
        simple_data = simple_res.json()
        assert simple_data["task_type"] == "general"
        assert simple_data["selected_model"] == "gpt-4o-mini"
        assert "cost-efficient" in simple_data["reason"]

        # 3. Route complex code generation prompt -> should detect code and escalate
        code_prompt = """
        def build_distributed_consensus_raft():
            import asyncio
            # Complex cluster election and state machine replication logic
            pass
        """ * 30
        code_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-routing-test/routing/route",
            json_body={"prompt": code_prompt},
        )
        assert code_res.status_code == 200
        code_data = code_res.json()
        assert code_data["task_type"] == "code"
        assert code_data["selected_model"] in ("gpt-4o", "claude-3-5-sonnet")
        assert "Escalated to frontier model" in code_data["reason"]

        # 4. Check routing decision logs
        decisions_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-routing-test/routing/decisions",
        )
        assert decisions_res.status_code == 200
        dec_data = decisions_res.json()
        assert len(dec_data["decisions"]) == 2

    asyncio.run(run())
