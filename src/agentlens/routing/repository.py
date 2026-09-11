"""Routing persistence protocol and implementations ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.routing.models import RoutingDecision, RoutingRule
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import routing_decisions, routing_rules


class RoutingRepository(Protocol):
    """Protocol for persisting routing rules and decision logs."""

    def save_rule(self, rule: RoutingRule) -> RoutingRule: ...

    def get_rule(self, rule_id: UUID) -> RoutingRule | None: ...

    def list_rules(self, project_id: str) -> Sequence[RoutingRule]: ...

    def delete_rule(self, rule_id: UUID) -> bool: ...

    def record_decision(self, decision: RoutingDecision) -> RoutingDecision: ...

    def list_decisions(self, project_id: str, limit: int = 50) -> Sequence[RoutingDecision]: ...


class InMemoryRoutingRepository:
    """In-memory routing repository for testing and development."""

    def __init__(self) -> None:
        self._rules: dict[UUID, RoutingRule] = {}
        self._decisions: list[RoutingDecision] = []

    def save_rule(self, rule: RoutingRule) -> RoutingRule:
        self._rules[rule.rule_id] = rule
        return rule

    def get_rule(self, rule_id: UUID) -> RoutingRule | None:
        return self._rules.get(rule_id)

    def list_rules(self, project_id: str) -> Sequence[RoutingRule]:
        return [r for r in self._rules.values() if r.project_id == project_id]

    def delete_rule(self, rule_id: UUID) -> bool:
        return self._rules.pop(rule_id, None) is not None

    def record_decision(self, decision: RoutingDecision) -> RoutingDecision:
        self._decisions.append(decision)
        return decision

    def list_decisions(self, project_id: str, limit: int = 50) -> Sequence[RoutingDecision]:
        matched = [d for d in self._decisions if d.project_id == project_id]
        return list(reversed(matched))[:limit]


class PostgresRoutingRepository:
    """PostgreSQL implementation of RoutingRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def save_rule(self, rule: RoutingRule) -> RoutingRule:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(routing_rules).values(
                    rule_id=rule.rule_id,
                    project_id=rule.project_id,
                    name=rule.name,
                    task_type=rule.task_type,
                    min_quality_score=rule.min_quality_score,
                    max_cost_per_1k=rule.max_cost_per_1k,
                    max_latency_ms=rule.max_latency_ms,
                    fallback_model=rule.fallback_model,
                    tier_priority=list(rule.tier_priority),
                    is_active=rule.is_active,
                    created_at=rule.created_at,
                )
            )
        return rule

    def get_rule(self, rule_id: UUID) -> RoutingRule | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(routing_rules).where(routing_rules.c.rule_id == rule_id)
            ).mappings().first()
            if r is None:
                return None
            return RoutingRule(
                rule_id=r["rule_id"],
                project_id=r["project_id"],
                name=r["name"],
                task_type=r["task_type"],
                min_quality_score=float(r["min_quality_score"]),
                max_cost_per_1k=float(r["max_cost_per_1k"]),
                max_latency_ms=float(r["max_latency_ms"]),
                fallback_model=r["fallback_model"],
                tier_priority=tuple(r["tier_priority"] or ()),
                is_active=bool(r["is_active"]),
                created_at=r["created_at"],
            )

    def list_rules(self, project_id: str) -> Sequence[RoutingRule]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(routing_rules).where(routing_rules.c.project_id == project_id)
            ).mappings().all()

            return [
                RoutingRule(
                    rule_id=r["rule_id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    task_type=r["task_type"],
                    min_quality_score=float(r["min_quality_score"]),
                    max_cost_per_1k=float(r["max_cost_per_1k"]),
                    max_latency_ms=float(r["max_latency_ms"]),
                    fallback_model=r["fallback_model"],
                    tier_priority=tuple(r["tier_priority"] or ()),
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_rule(self, rule_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(routing_rules).where(routing_rules.c.rule_id == rule_id)
            )
            return bool(res.rowcount > 0)

    def record_decision(self, decision: RoutingDecision) -> RoutingDecision:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(routing_decisions).values(
                    decision_id=decision.decision_id,
                    project_id=decision.project_id,
                    trace_id=decision.trace_id,
                    rule_id=decision.rule_id,
                    selected_model=decision.selected_model,
                    selected_provider=decision.selected_provider,
                    estimated_cost_usd=decision.estimated_cost_usd,
                    reason=decision.reason,
                    decided_at=decision.decided_at,
                )
            )
        return decision

    def list_decisions(self, project_id: str, limit: int = 50) -> Sequence[RoutingDecision]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(routing_decisions)
                .where(routing_decisions.c.project_id == project_id)
                .order_by(routing_decisions.c.decided_at.desc())
                .limit(limit)
            ).mappings().all()

            return [
                RoutingDecision(
                    decision_id=r["decision_id"],
                    project_id=r["project_id"],
                    trace_id=r["trace_id"],
                    rule_id=r["rule_id"],
                    selected_model=r["selected_model"],
                    selected_provider=r["selected_provider"],
                    estimated_cost_usd=float(r["estimated_cost_usd"]),
                    reason=r["reason"],
                    decided_at=r["decided_at"],
                )
                for r in rows
            ]
