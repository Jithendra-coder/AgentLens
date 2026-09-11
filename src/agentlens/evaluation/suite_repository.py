"""Evaluation suite repository implementation ."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, desc, select
from sqlalchemy.engine import Engine

from agentlens.evaluation.composite import (
    CompositeEvaluationResult,
    EvaluationSuite,
    EvaluatorConfigRef,
    MetricScore,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    composite_evaluation_results,
    evaluation_suites,
    suite_evaluators,
)


class EvaluationSuiteRepository(Protocol):
    """Protocol for storing and retrieving evaluation suites and composite results."""

    def create_suite(self, suite: EvaluationSuite) -> EvaluationSuite: ...

    def get_suite(self, suite_id: UUID) -> EvaluationSuite | None: ...

    def list_suites(self, project_id: str) -> Sequence[EvaluationSuite]: ...

    def delete_suite(self, suite_id: UUID) -> bool: ...

    def store_result(self, result: CompositeEvaluationResult) -> CompositeEvaluationResult: ...

    def list_results(
        self,
        project_id: str,
        suite_id: UUID | None = None,
        limit: int = 50,
    ) -> Sequence[CompositeEvaluationResult]: ...


class InMemoryEvaluationSuiteRepository:
    """In-memory implementation of EvaluationSuiteRepository for tests and local dev."""

    def __init__(self) -> None:
        self._suites: dict[UUID, EvaluationSuite] = {}
        self._results: list[CompositeEvaluationResult] = []

    def create_suite(self, suite: EvaluationSuite) -> EvaluationSuite:
        self._suites[suite.suite_id] = suite
        return suite

    def get_suite(self, suite_id: UUID) -> EvaluationSuite | None:
        return self._suites.get(suite_id)

    def list_suites(self, project_id: str) -> Sequence[EvaluationSuite]:
        return [s for s in self._suites.values() if s.project_id == project_id]

    def delete_suite(self, suite_id: UUID) -> bool:
        if suite_id in self._suites:
            del self._suites[suite_id]
            return True
        return False

    def store_result(self, result: CompositeEvaluationResult) -> CompositeEvaluationResult:
        self._results.append(result)
        return result

    def list_results(
        self,
        project_id: str,
        suite_id: UUID | None = None,
        limit: int = 50,
    ) -> Sequence[CompositeEvaluationResult]:
        filtered = [
            r
            for r in self._results
            if r.project_id == project_id and (suite_id is None or r.suite_id == suite_id)
        ]
        return list(reversed(filtered))[:limit]


class PostgresEvaluationSuiteRepository:
    """Durable PostgreSQL implementation of EvaluationSuiteRepository."""

    def __init__(self, config: DatabaseConfig, engine: Engine | None = None) -> None:
        self._config = config
        self._engine = engine or create_engine(config.url, pool_pre_ping=True)

    def create_suite(self, suite: EvaluationSuite) -> EvaluationSuite:
        with self._engine.begin() as conn:
            conn.execute(
                evaluation_suites.insert().values(
                    suite_id=suite.suite_id,
                    project_id=suite.project_id,
                    name=suite.name,
                    description=suite.description,
                    passing_threshold=suite.passing_threshold,
                    created_at=suite.created_at,
                    updated_at=suite.updated_at,
                )
            )
            for ev in suite.evaluators:
                conn.execute(
                    suite_evaluators.insert().values(
                        id=uuid4(),
                        suite_id=suite.suite_id,
                        evaluator_name=ev.evaluator_name,
                        evaluator_version=ev.evaluator_version,
                        evaluator_type=ev.evaluator_type,
                        weight=ev.weight,
                        threshold=ev.threshold,
                        parameters=ev.parameters,
                    )
                )
        return suite

    def get_suite(self, suite_id: UUID) -> EvaluationSuite | None:
        with self._engine.connect() as conn:
            suite_row = conn.execute(
                select(evaluation_suites).where(evaluation_suites.c.suite_id == suite_id)
            ).mappings().first()
            if suite_row is None:
                return None

            ev_rows = conn.execute(
                select(suite_evaluators).where(suite_evaluators.c.suite_id == suite_id)
            ).mappings().all()

            evaluators = [
                EvaluatorConfigRef(
                    evaluator_name=cast(str, r["evaluator_name"]),
                    evaluator_version=cast(str, r["evaluator_version"]),
                    evaluator_type=cast(str, r["evaluator_type"]),
                    weight=cast(float, r["weight"]),
                    threshold=cast(float, r["threshold"]),
                    parameters=cast(dict[str, Any], r["parameters"] or {}),
                )
                for r in ev_rows
            ]

            return EvaluationSuite(
                suite_id=cast(UUID, suite_row["suite_id"]),
                project_id=cast(str, suite_row["project_id"]),
                name=cast(str, suite_row["name"]),
                description=cast(str | None, suite_row["description"]),
                passing_threshold=cast(float, suite_row["passing_threshold"]),
                evaluators=tuple(evaluators),
                created_at=cast(datetime, suite_row["created_at"]),
                updated_at=cast(datetime, suite_row["updated_at"]),
            )

    def list_suites(self, project_id: str) -> Sequence[EvaluationSuite]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(evaluation_suites)
                .where(evaluation_suites.c.project_id == project_id)
                .order_by(desc(evaluation_suites.c.created_at))
            ).mappings().all()

            result: list[EvaluationSuite] = []
            for r in rows:
                sid = cast(UUID, r["suite_id"])
                ev_rows = conn.execute(
                    select(suite_evaluators).where(suite_evaluators.c.suite_id == sid)
                ).mappings().all()
                evaluators = [
                    EvaluatorConfigRef(
                        evaluator_name=cast(str, er["evaluator_name"]),
                        evaluator_version=cast(str, er["evaluator_version"]),
                        evaluator_type=cast(str, er["evaluator_type"]),
                        weight=cast(float, er["weight"]),
                        threshold=cast(float, er["threshold"]),
                        parameters=cast(dict[str, Any], er["parameters"] or {}),
                    )
                    for er in ev_rows
                ]
                result.append(
                    EvaluationSuite(
                        suite_id=sid,
                        project_id=cast(str, r["project_id"]),
                        name=cast(str, r["name"]),
                        description=cast(str | None, r["description"]),
                        passing_threshold=cast(float, r["passing_threshold"]),
                        evaluators=tuple(evaluators),
                        created_at=cast(datetime, r["created_at"]),
                        updated_at=cast(datetime, r["updated_at"]),
                    )
                )
            return result

    def delete_suite(self, suite_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                evaluation_suites.delete().where(evaluation_suites.c.suite_id == suite_id)
            )
            return bool(res.rowcount and res.rowcount > 0)

    def store_result(self, result: CompositeEvaluationResult) -> CompositeEvaluationResult:
        metric_dicts = [
            {
                "evaluator_name": m.evaluator_name,
                "evaluator_version": m.evaluator_version,
                "evaluator_type": m.evaluator_type,
                "raw_score": m.raw_score,
                "weight": m.weight,
                "weighted_score": m.weighted_score,
                "threshold": m.threshold,
                "passed": m.passed,
                "details": m.details,
            }
            for m in result.metric_scores
        ]
        with self._engine.begin() as conn:
            conn.execute(
                composite_evaluation_results.insert().values(
                    composite_result_id=result.composite_result_id,
                    suite_id=result.suite_id,
                    project_id=result.project_id,
                    trace_id=result.trace_id,
                    aggregate_score=result.aggregate_score,
                    passed=result.passed,
                    metric_scores=metric_dicts,
                    created_at=result.created_at,
                )
            )
        return result

    def list_results(
        self,
        project_id: str,
        suite_id: UUID | None = None,
        limit: int = 50,
    ) -> Sequence[CompositeEvaluationResult]:
        with self._engine.connect() as conn:
            clauses = [composite_evaluation_results.c.project_id == project_id]
            if suite_id is not None:
                clauses.append(composite_evaluation_results.c.suite_id == suite_id)

            rows = conn.execute(
                select(composite_evaluation_results)
                .where(and_(*clauses))
                .order_by(desc(composite_evaluation_results.c.created_at))
                .limit(limit)
            ).mappings().all()

            results: list[CompositeEvaluationResult] = []
            for r in rows:
                metrics_raw = cast(list[dict[str, Any]], r["metric_scores"] or [])
                metric_objs = [
                    MetricScore(
                        evaluator_name=m["evaluator_name"],
                        evaluator_version=m["evaluator_version"],
                        evaluator_type=m["evaluator_type"],
                        raw_score=m["raw_score"],
                        weight=m["weight"],
                        weighted_score=m["weighted_score"],
                        threshold=m["threshold"],
                        passed=m["passed"],
                        details=m.get("details", {}),
                    )
                    for m in metrics_raw
                ]
                results.append(
                    CompositeEvaluationResult(
                        composite_result_id=cast(UUID, r["composite_result_id"]),
                        suite_id=cast(UUID, r["suite_id"]),
                        project_id=cast(str, r["project_id"]),
                        trace_id=cast(UUID, r["trace_id"]),
                        aggregate_score=cast(float, r["aggregate_score"]),
                        passed=cast(bool, r["passed"]),
                        metric_scores=tuple(metric_objs),
                        created_at=cast(datetime, r["created_at"]),
                    )
                )
            return results
