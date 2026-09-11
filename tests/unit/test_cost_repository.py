"""Unit tests for InMemoryCostRepository lifecycle and aggregation."""

from __future__ import annotations

from uuid import uuid4

from agentlens.cost.models import CostBudget, SpanCostRecord
from agentlens.cost.repository import InMemoryCostRepository


def test_in_memory_cost_repository_lifecycle() -> None:
    repo = InMemoryCostRepository()

    # 1. Record span costs
    r1 = SpanCostRecord(
        span_id=uuid4(),
        trace_id=uuid4(),
        project_id="proj-alpha",
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=500,
        total_cost_usd=0.0125,
    )
    r2 = SpanCostRecord(
        span_id=uuid4(),
        trace_id=uuid4(),
        project_id="proj-alpha",
        provider="anthropic",
        model="claude-3-5-sonnet",
        input_tokens=2000,
        output_tokens=1000,
        total_cost_usd=0.0210,
    )
    repo.record_span_costs([r1, r2])

    summary = repo.get_cost_summary("proj-alpha")
    assert summary.project_id == "proj-alpha"
    assert summary.total_cost_usd == 0.0335
    assert summary.total_tokens == 4500
    assert len(summary.by_model) == 2

    # 2. Budget lifecycle
    budget_id = uuid4()
    budget = CostBudget(
        budget_id=budget_id,
        project_id="proj-alpha",
        name="Alpha Cap",
        amount_usd=50.0,
        period="monthly",
        alert_threshold_pct=80.0,
    )

    saved = repo.save_budget(budget)
    assert saved.budget_id == budget_id

    fetched = repo.get_budget(budget_id)
    assert fetched is not None
    assert fetched.name == "Alpha Cap"

    budgets = repo.list_budgets("proj-alpha")
    assert len(budgets) == 1

    assert repo.delete_budget(budget_id) is True
    assert repo.get_budget(budget_id) is None
