"""Budget evaluation and threshold breach detection ."""

from __future__ import annotations

from agentlens.cost.models import BudgetStatus, CostBudget


class BudgetEvaluator:
    """Evaluates project budgets and triggers alerts upon threshold breach."""

    @staticmethod
    def evaluate(budget: CostBudget, current_spend_usd: float) -> BudgetStatus:
        burn_pct = round((current_spend_usd / budget.amount_usd) * 100.0, 2)
        is_breached = current_spend_usd >= budget.amount_usd
        alert_triggered = burn_pct >= budget.alert_threshold_pct

        return BudgetStatus(
            budget=budget,
            current_spend_usd=round(current_spend_usd, 4),
            burn_percentage=burn_pct,
            is_breached=is_breached,
            alert_triggered=alert_triggered,
        )
