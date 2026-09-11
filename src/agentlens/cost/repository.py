"""Cost intelligence and budget repository protocol and implementations ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.cost.models import (
    CostBreakdownItem,
    CostBudget,
    CostSummary,
    SpanCostRecord,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import cost_budgets, span_costs


class CostRepository(Protocol):
    """Protocol for persisting and querying span costs and budgets."""

    def record_span_costs(self, records: Sequence[SpanCostRecord]) -> None: ...

    def get_cost_summary(self, project_id: str) -> CostSummary: ...

    def save_budget(self, budget: CostBudget) -> CostBudget: ...

    def get_budget(self, budget_id: UUID) -> CostBudget | None: ...

    def list_budgets(self, project_id: str) -> Sequence[CostBudget]: ...

    def delete_budget(self, budget_id: UUID) -> bool: ...


class InMemoryCostRepository:
    """In-memory implementation of CostRepository for testing."""

    def __init__(self) -> None:
        self._span_costs: list[SpanCostRecord] = []
        self._budgets: dict[UUID, CostBudget] = {}

    def record_span_costs(self, records: Sequence[SpanCostRecord]) -> None:
        self._span_costs.extend(records)

    def get_cost_summary(self, project_id: str) -> CostSummary:
        records = [r for r in self._span_costs if r.project_id == project_id]
        total_cost = sum(r.total_cost_usd for r in records)
        total_tokens = sum(r.input_tokens + r.output_tokens for r in records)

        # By model
        model_map: dict[str, dict[str, float]] = {}
        for r in records:
            key = f"{r.provider}/{r.model}" if r.provider != "unknown" else r.model
            entry = model_map.setdefault(key, {"cost": 0.0, "in": 0.0, "out": 0.0})
            entry["cost"] += r.total_cost_usd
            entry["in"] += r.input_tokens
            entry["out"] += r.output_tokens

        by_model: list[CostBreakdownItem] = []
        for k, v in model_map.items():
            tot = int(v["in"] + v["out"])
            pct = round((v["cost"] / total_cost * 100.0), 2) if total_cost > 0 else 0.0
            by_model.append(
                CostBreakdownItem(
                    dimension_key=k,
                    cost_usd=round(v["cost"], 6),
                    input_tokens=int(v["in"]),
                    output_tokens=int(v["out"]),
                    total_tokens=tot,
                    percentage=pct,
                )
            )

        return CostSummary(
            project_id=project_id,
            total_cost_usd=round(total_cost, 6),
            total_tokens=total_tokens,
            by_model=sorted(by_model, key=lambda x: x.cost_usd, reverse=True),
        )

    def save_budget(self, budget: CostBudget) -> CostBudget:
        self._budgets[budget.budget_id] = budget
        return budget

    def get_budget(self, budget_id: UUID) -> CostBudget | None:
        return self._budgets.get(budget_id)

    def list_budgets(self, project_id: str) -> Sequence[CostBudget]:
        return [b for b in self._budgets.values() if b.project_id == project_id]

    def delete_budget(self, budget_id: UUID) -> bool:
        return self._budgets.pop(budget_id, None) is not None


class PostgresCostRepository:
    """PostgreSQL implementation of CostRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def record_span_costs(self, records: Sequence[SpanCostRecord]) -> None:
        if not records:
            return
        with self._engine.begin() as conn:
            for r in records:
                conn.execute(
                    sa.insert(span_costs).values(
                        span_id=r.span_id,
                        trace_id=r.trace_id,
                        project_id=r.project_id,
                        provider=r.provider,
                        model=r.model,
                        input_tokens=r.input_tokens,
                        output_tokens=r.output_tokens,
                        total_cost_usd=r.total_cost_usd,
                        calculated_at=r.calculated_at,
                    )
                )

    def get_cost_summary(self, project_id: str) -> CostSummary:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(span_costs).where(span_costs.c.project_id == project_id)
            ).mappings().all()

        total_cost = sum(float(r["total_cost_usd"]) for r in rows)
        total_tokens = sum(int(r["input_tokens"]) + int(r["output_tokens"]) for r in rows)

        model_map: dict[str, dict[str, float]] = {}
        for r in rows:
            provider = str(r["provider"])
            model = str(r["model"])
            key = f"{provider}/{model}" if provider != "unknown" else model
            entry = model_map.setdefault(key, {"cost": 0.0, "in": 0.0, "out": 0.0})
            entry["cost"] += float(r["total_cost_usd"])
            entry["in"] += int(r["input_tokens"])
            entry["out"] += int(r["output_tokens"])

        by_model: list[CostBreakdownItem] = []
        for k, v in model_map.items():
            tot = int(v["in"] + v["out"])
            pct = round((v["cost"] / total_cost * 100.0), 2) if total_cost > 0 else 0.0
            by_model.append(
                CostBreakdownItem(
                    dimension_key=k,
                    cost_usd=round(v["cost"], 6),
                    input_tokens=int(v["in"]),
                    output_tokens=int(v["out"]),
                    total_tokens=tot,
                    percentage=pct,
                )
            )

        return CostSummary(
            project_id=project_id,
            total_cost_usd=round(total_cost, 6),
            total_tokens=total_tokens,
            by_model=sorted(by_model, key=lambda x: x.cost_usd, reverse=True),
        )

    def save_budget(self, budget: CostBudget) -> CostBudget:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(cost_budgets).values(
                    budget_id=budget.budget_id,
                    project_id=budget.project_id,
                    name=budget.name,
                    period=budget.period,
                    amount_usd=budget.amount_usd,
                    alert_threshold_pct=budget.alert_threshold_pct,
                    notification_webhook_url=budget.notification_webhook_url,
                    created_at=budget.created_at,
                )
            )
        return budget

    def get_budget(self, budget_id: UUID) -> CostBudget | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(cost_budgets).where(cost_budgets.c.budget_id == budget_id)
            ).mappings().first()
        if row is None:
            return None
        return CostBudget(
            budget_id=row["budget_id"],
            project_id=row["project_id"],
            name=row["name"],
            period=row["period"],
            amount_usd=float(row["amount_usd"]),
            alert_threshold_pct=float(row["alert_threshold_pct"]),
            notification_webhook_url=row["notification_webhook_url"],
            created_at=row["created_at"],
        )

    def list_budgets(self, project_id: str) -> Sequence[CostBudget]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(cost_budgets).where(cost_budgets.c.project_id == project_id)
            ).mappings().all()
        return [
            CostBudget(
                budget_id=r["budget_id"],
                project_id=r["project_id"],
                name=r["name"],
                period=r["period"],
                amount_usd=float(r["amount_usd"]),
                alert_threshold_pct=float(r["alert_threshold_pct"]),
                notification_webhook_url=r["notification_webhook_url"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def delete_budget(self, budget_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(cost_budgets).where(cost_budgets.c.budget_id == budget_id)
            )
            return bool(res.rowcount > 0)
