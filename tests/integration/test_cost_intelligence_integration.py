"""Integration tests for Cost Intelligence, Token Attribution, and Budget Governance."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.cost.calculator import CostCalculator
from agentlens.cost.repository import InMemoryCostRepository
from agentlens.domain import Span, Trace
from agentlens.domain.types import SpanType, Status
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-cost-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-costing",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    cost_repo = InMemoryCostRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        cost_repository=cost_repo,
    )
    return app, sink, cost_repo


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


def test_cost_attribution_and_budget_governance() -> None:
    app, sink, cost_repo = make_test_app()
    calculator = CostCalculator()

    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()

    s1 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.LLM,
        name="GPT4oQuery",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=1),
        status=Status.OK,
        attributes={
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 10000,
            "completion_tokens": 2000,
        },
    )
    trace = Trace(
        trace_id=trace_id,
        project_id="proj-costing",
        name="AgentLlmTrace",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=1),
        status=Status.OK,
        spans=[s1],
    )
    sink.ingest(trace)

    # Compute and record costs
    costs = calculator.calculate_trace_costs(trace)
    cost_repo.record_span_costs(costs)

    async def run():
        # 1. Create a tight budget for testing alerts
        create_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-costing/budgets",
            json_body={
                "name": "Dev Daily Cap",
                "amount_usd": 0.05,
                "period": "daily",
                "alert_threshold_pct": 80.0,
            },
        )
        assert create_res.status_code == 200
        budget_data = create_res.json()
        assert budget_data["name"] == "Dev Daily Cap"

        # 2. Get cost summary
        summary_res = await send_request(app, "GET", "/v1/projects/proj-costing/cost/summary")
        assert summary_res.status_code == 200
        summary_data = summary_res.json()
        assert summary_data["total_tokens"] == 12000
        # 10k in * 0.005/1k + 2k out * 0.015/1k = 0.05 + 0.03 = 0.08
        assert summary_data["total_cost_usd"] == 0.08
        assert len(summary_data["by_model"]) == 1
        assert summary_data["by_model"][0]["dimension_key"] == "openai/gpt-4o"

        # 3. Check budget burn & breach status
        budgets_res = await send_request(app, "GET", "/v1/projects/proj-costing/budgets")
        assert budgets_res.status_code == 200
        budgets_data = budgets_res.json()
        assert len(budgets_data["budgets"]) == 1
        b_status = budgets_data["budgets"][0]
        assert b_status["current_spend_usd"] == 0.08
        assert b_status["burn_percentage"] == 160.0  # (0.08 / 0.05) * 100
        assert b_status["alert_triggered"] is True
        assert b_status["is_breached"] is True

    asyncio.run(run())
