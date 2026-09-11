"""Integration tests for Custom Evaluator Plugin registration and suite execution."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.domain import Span, Trace
from agentlens.domain.types import SpanType, Status
from agentlens.evaluation.plugins.repository import InMemoryCustomEvaluatorRepository
from agentlens.evaluation.suite_repository import InMemoryEvaluationSuiteRepository
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-plugins-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-plugins",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    suite_repo = InMemoryEvaluationSuiteRepository()
    custom_repo = InMemoryCustomEvaluatorRepository()
    return create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        suite_repository=suite_repo,
        custom_evaluator_repository=custom_repo,
    ), sink


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


def test_custom_evaluator_lifecycle_and_execution() -> None:
    app, sink = make_test_app()
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()

    s1 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.AGENT,
        name="MainOrchestrator",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
    )
    s2 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.TOOL,
        name="web_search",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
        attributes={"query": "agent evaluation"},
    )
    trace = Trace(
        trace_id=trace_id,
        project_id="proj-plugins",
        name="AgentExecutionWithSearch",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
        spans=[s1, s2],
    )
    sink.ingest(trace)

    async def run():
        # 1. Register custom evaluator plugin
        code_str = """
def evaluate(context, parameters):
    has_search = any(s.name == "web_search" for s in context.spans)
    findings = (
        ["Found required web_search tool call"]
        if has_search
        else ["Missing web_search tool"]
    )
    return CustomEvaluationOutput(
        score=1.0 if has_search else 0.0,
        passed=has_search,
        findings=findings,
    )
"""
        reg_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-plugins/custom-evaluators",
            json_body={
                "name": "custom.search_validator",
                "version": "1.0.0",
                "evaluator_type": "deterministic",
                "description": "Ensures agent used web_search tool",
                "code_body": code_str,
            },
        )
        assert reg_res.status_code == 200
        plugin_data = reg_res.json()
        plugin_id = plugin_data["plugin_id"]
        assert plugin_data["name"] == "custom.search_validator"

        # 2. List custom evaluators
        list_res = await send_request(app, "GET", "/v1/projects/proj-plugins/custom-evaluators")
        assert list_res.status_code == 200
        assert len(list_res.json()["custom_evaluators"]) == 1

        # 3. Test custom evaluator directly
        test_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-plugins/custom-evaluators/{plugin_id}/test",
            json_body={"trace_id": str(trace_id)},
        )
        assert test_res.status_code == 200
        test_data = test_res.json()
        assert test_data["score"] == 1.0
        assert test_data["passed"] is True
        assert "Found required web_search tool call" in test_data["findings"]

        # 4. Create an evaluation suite containing this custom evaluator
        suite_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-plugins/evaluation-suites",
            json_body={
                "name": "Custom Plugin Quality Suite",
                "passing_threshold": 0.8,
                "evaluators": [
                    {
                        "evaluator_name": "agentlens.latency",
                        "weight": 0.5,
                        "threshold": 0.8,
                    },
                    {
                        "evaluator_name": "custom.search_validator",
                        "evaluator_version": "1.0.0",
                        "weight": 0.5,
                        "threshold": 0.9,
                    },
                ],
            },
        )
        assert suite_res.status_code == 200
        suite_id = suite_res.json()["suite_id"]

        # 5. Run suite against trace
        suite_run_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-plugins/evaluation-suites/{suite_id}/run",
            json_body={"trace_id": str(trace_id)},
        )
        assert suite_run_res.status_code == 200
        suite_out = suite_run_res.json()
        assert suite_out["aggregate_score"] >= 0.8
        assert suite_out["passed"] is True
        assert len(suite_out["metric_scores"]) == 2

    asyncio.run(run())
