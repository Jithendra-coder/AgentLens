"""Integration tests  evaluation suites and composite quality runs."""

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
from agentlens.evaluation.suite_repository import InMemoryEvaluationSuiteRepository
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-suites-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-eval",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    suite_repo = InMemoryEvaluationSuiteRepository()
    return create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        suite_repository=suite_repo,
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


def test_evaluation_suite_lifecycle_and_composite_run() -> None:
    app, sink = make_test_app()
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()

    s1 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.AGENT,
        name="PlannerAgent",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
    )
    s2 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.TOOL,
        name="web_browser",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
    )
    trace = Trace(
        trace_id=trace_id,
        project_id="proj-eval",
        name="AgentWithTools",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
        spans=[s1, s2],
    )
    sink.ingest(trace)

    async def run():
        # 1. Create evaluation suite
        create_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-eval/evaluation-suites",
            json_body={
                "name": "Production Agent Quality Suite",
                "description": "Composite evaluation suite combining latency and tool correctness",
                "passing_threshold": 0.8,
                "evaluators": [
                    {
                        "evaluator_name": "agentlens.latency",
                        "evaluator_version": "1.0.0",
                        "evaluator_type": "deterministic",
                        "weight": 0.5,
                        "threshold": 0.75,
                    },
                    {
                        "evaluator_name": "agentlens.tool_correctness",
                        "evaluator_version": "1.0.0",
                        "evaluator_type": "deterministic",
                        "weight": 0.5,
                        "threshold": 0.75,
                    },
                ],
            },
        )
        assert create_res.status_code == 200
        suite_data = create_res.json()
        suite_id = suite_data["suite_id"]
        assert suite_data["name"] == "Production Agent Quality Suite"
        assert len(suite_data["evaluators"]) == 2

        # 2. List suites
        list_res = await send_request(app, "GET", "/v1/projects/proj-eval/evaluation-suites")
        assert list_res.status_code == 200
        assert len(list_res.json()["suites"]) == 1

        # 3. Run composite suite against trace
        run_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-eval/evaluation-suites/{suite_id}/run",
            json_body={"trace_id": str(trace_id)},
        )
        assert run_res.status_code == 200
        run_data = run_res.json()
        assert run_data["suite_id"] == suite_id
        assert run_data["trace_id"] == str(trace_id)
        assert run_data["aggregate_score"] >= 0.8
        assert run_data["passed"] is True
        assert len(run_data["metric_scores"]) == 2

        # 4. List composite results
        results_res = await send_request(
            app,
            "GET",
            f"/v1/projects/proj-eval/evaluation-suites/{suite_id}/results",
        )
        assert results_res.status_code == 200
        results_data = results_res.json()["results"]
        assert len(results_data) == 1
        assert results_data[0]["passed"] is True

    asyncio.run(run())
