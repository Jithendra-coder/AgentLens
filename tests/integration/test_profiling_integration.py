"""Integration tests  trace profiling and project bottleneck hotspots APIs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.domain import Span, Trace, Usage
from agentlens.domain.types import SpanType, Status
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-profiling-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-m17",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    return create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
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


def test_trace_profile_and_project_hotspots_api() -> None:
    app, sink = make_test_app()
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()
    root_id = uuid4()
    llm_id = uuid4()

    root = Span(
        span_id=root_id,
        trace_id=trace_id,
        span_type=SpanType.AGENT,
        name="PlannerAgent",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=3),
        status=Status.OK,
    )
    llm = Span(
        span_id=llm_id,
        trace_id=trace_id,
        parent_span_id=root_id,
        span_type=SpanType.LLM,
        name="claude-3-5-sonnet",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=3),
        status=Status.OK,
        usage=Usage(input_tokens=500, output_tokens=200, total_tokens=700),
    )
    trace = Trace(
        trace_id=trace_id,
        project_id="proj-m17",
        name="ComplexAgentExecution",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=3),
        status=Status.OK,
        spans=[root, llm],
    )
    sink.ingest(trace)

    async def run():
        # 1. Get trace profile
        profile_res = await send_request(app, "GET", f"/v1/traces/{trace_id}/profile")
        assert profile_res.status_code == 200
        data = profile_res.json()
        assert data["trace_id"] == str(trace_id)
        assert data["total_duration_ms"] == 3000.0
        assert str(root_id) in data["critical_path_span_ids"]
        assert data["latency_breakdown"]["llm_time_ms"] == 2000.0
        assert data["latency_breakdown"]["overhead_time_ms"] == 1000.0
        assert data["token_breakdown"]["total_tokens"] == 700

        # 2. Get project hotspots
        hotspots_res = await send_request(app, "GET", "/v1/analytics/hotspots")
        assert hotspots_res.status_code == 200
        h_data = hotspots_res.json()
        assert h_data["project_id"] == "proj-m17"
        assert h_data["analyzed_traces_count"] == 1
        assert len(h_data["heaviest_token_spans"]) == 1
        assert h_data["heaviest_token_spans"][0]["name"] == "claude-3-5-sonnet"

    asyncio.run(run())
