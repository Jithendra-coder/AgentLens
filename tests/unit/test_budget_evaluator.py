"""Unit tests  BudgetEvaluator and domain validation."""

from __future__ import annotations

import pytest

from agentlens.cost.budget import BudgetEvaluator
from agentlens.cost.models import CostBudget, ModelPricing


def test_model_pricing_and_budget_invariants() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        ModelPricing(
            provider="openai",
            model_pattern="gpt-4o",
            input_cost_per_1k=-0.01,
            output_cost_per_1k=0.01,
        )

    with pytest.raises(ValueError, match="amount_usd must be greater than 0"):
        CostBudget(
            project_id="proj-1",
            name="Invalid",
            amount_usd=0.0,
        )

    with pytest.raises(ValueError, match="alert_threshold_pct must be between"):
        CostBudget(
            project_id="proj-1",
            name="Invalid",
            amount_usd=100.0,
            alert_threshold_pct=150.0,
        )


def test_budget_evaluator_states() -> None:
    budget = CostBudget(
        project_id="proj-test",
        name="Monthly Cap",
        amount_usd=100.0,
        period="monthly",
        alert_threshold_pct=80.0,
    )

    # 1. Healthy spend (below alert threshold)
    s1 = BudgetEvaluator.evaluate(budget, current_spend_usd=50.0)
    assert s1.current_spend_usd == 50.0
    assert s1.burn_percentage == 50.0
    assert s1.alert_triggered is False
    assert s1.is_breached is False

    # 2. Alert threshold triggered (85% burn)
    s2 = BudgetEvaluator.evaluate(budget, current_spend_usd=85.0)
    assert s2.burn_percentage == 85.0
    assert s2.alert_triggered is True
    assert s2.is_breached is False

    # 3. Budget breach (105% burn)
    s3 = BudgetEvaluator.evaluate(budget, current_spend_usd=105.0)
    assert s3.burn_percentage == 105.0
    assert s3.alert_triggered is True
    assert s3.is_breached is True
