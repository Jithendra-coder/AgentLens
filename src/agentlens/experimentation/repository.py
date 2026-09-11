"""Experimentation persistence protocol and implementations ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.experimentation.models import (
    Experiment,
    ExperimentEvaluation,
    ExperimentVariant,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    experiment_evaluations,
    experiment_variants,
    experiments,
)


class ExperimentRepository(Protocol):
    """Protocol for persisting experiments, variants, and evaluation results."""

    def save_experiment(self, experiment: Experiment) -> Experiment: ...

    def get_experiment(self, experiment_id: UUID) -> Experiment | None: ...

    def list_experiments(self, project_id: str) -> Sequence[Experiment]: ...

    def delete_experiment(self, experiment_id: UUID) -> bool: ...

    def record_evaluation(self, evaluation: ExperimentEvaluation) -> ExperimentEvaluation: ...

    def list_evaluations(self, experiment_id: UUID) -> Sequence[ExperimentEvaluation]: ...


class InMemoryExperimentRepository:
    """In-memory experiment repository for testing and development."""

    def __init__(self) -> None:
        self._experiments: dict[UUID, Experiment] = {}
        self._evaluations: dict[UUID, list[ExperimentEvaluation]] = {}

    def save_experiment(self, experiment: Experiment) -> Experiment:
        self._experiments[experiment.experiment_id] = experiment
        return experiment

    def get_experiment(self, experiment_id: UUID) -> Experiment | None:
        return self._experiments.get(experiment_id)

    def list_experiments(self, project_id: str) -> Sequence[Experiment]:
        return [e for e in self._experiments.values() if e.project_id == project_id]

    def delete_experiment(self, experiment_id: UUID) -> bool:
        self._evaluations.pop(experiment_id, None)
        return self._experiments.pop(experiment_id, None) is not None

    def record_evaluation(self, evaluation: ExperimentEvaluation) -> ExperimentEvaluation:
        self._evaluations.setdefault(evaluation.experiment_id, []).append(evaluation)
        return evaluation

    def list_evaluations(self, experiment_id: UUID) -> Sequence[ExperimentEvaluation]:
        return self._evaluations.get(experiment_id, [])


class PostgresExperimentRepository:
    """PostgreSQL implementation of ExperimentRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def save_experiment(self, experiment: Experiment) -> Experiment:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(experiments).values(
                    experiment_id=experiment.experiment_id,
                    project_id=experiment.project_id,
                    name=experiment.name,
                    description=experiment.description,
                    experiment_type=experiment.experiment_type,
                    status=experiment.status,
                    created_at=experiment.created_at,
                    concluded_at=experiment.concluded_at,
                )
            )
            for v in experiment.variants:
                conn.execute(
                    sa.insert(experiment_variants).values(
                        variant_id=v.variant_id,
                        experiment_id=experiment.experiment_id,
                        name=v.name,
                        prompt_template=v.prompt_template,
                        model_name=v.model_name,
                        provider_type=v.provider_type,
                        traffic_weight=v.traffic_weight,
                        is_control=v.is_control,
                    )
                )
        return experiment

    def get_experiment(self, experiment_id: UUID) -> Experiment | None:
        with self._engine.connect() as conn:
            exp_row = conn.execute(
                sa.select(experiments).where(experiments.c.experiment_id == experiment_id)
            ).mappings().first()
            if exp_row is None:
                return None

            variant_rows = conn.execute(
                sa.select(experiment_variants).where(
                    experiment_variants.c.experiment_id == experiment_id
                )
            ).mappings().all()

        variants = tuple(
            ExperimentVariant(
                variant_id=r["variant_id"],
                experiment_id=r["experiment_id"],
                name=r["name"],
                prompt_template=r["prompt_template"],
                model_name=r["model_name"],
                provider_type=r["provider_type"],
                traffic_weight=float(r["traffic_weight"]),
                is_control=bool(r["is_control"]),
            )
            for r in variant_rows
        )

        return Experiment(
            experiment_id=exp_row["experiment_id"],
            project_id=exp_row["project_id"],
            name=exp_row["name"],
            description=exp_row["description"],
            experiment_type=exp_row["experiment_type"],
            status=exp_row["status"],
            variants=variants,
            created_at=exp_row["created_at"],
            concluded_at=exp_row["concluded_at"],
        )

    def list_experiments(self, project_id: str) -> Sequence[Experiment]:
        with self._engine.connect() as conn:
            exp_rows = conn.execute(
                sa.select(experiments).where(experiments.c.project_id == project_id)
            ).mappings().all()

            results: list[Experiment] = []
            for exp_row in exp_rows:
                v_rows = conn.execute(
                    sa.select(experiment_variants).where(
                        experiment_variants.c.experiment_id == exp_row["experiment_id"]
                    )
                ).mappings().all()

                variants = tuple(
                    ExperimentVariant(
                        variant_id=r["variant_id"],
                        experiment_id=r["experiment_id"],
                        name=r["name"],
                        prompt_template=r["prompt_template"],
                        model_name=r["model_name"],
                        provider_type=r["provider_type"],
                        traffic_weight=float(r["traffic_weight"]),
                        is_control=bool(r["is_control"]),
                    )
                    for r in v_rows
                )

                results.append(
                    Experiment(
                        experiment_id=exp_row["experiment_id"],
                        project_id=exp_row["project_id"],
                        name=exp_row["name"],
                        description=exp_row["description"],
                        experiment_type=exp_row["experiment_type"],
                        status=exp_row["status"],
                        variants=variants,
                        created_at=exp_row["created_at"],
                        concluded_at=exp_row["concluded_at"],
                    )
                )
        return results

    def delete_experiment(self, experiment_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(experiments).where(experiments.c.experiment_id == experiment_id)
            )
            return bool(res.rowcount > 0)

    def record_evaluation(self, evaluation: ExperimentEvaluation) -> ExperimentEvaluation:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(experiment_evaluations).values(
                    eval_id=evaluation.eval_id,
                    experiment_id=evaluation.experiment_id,
                    variant_id=evaluation.variant_id,
                    trace_id=evaluation.trace_id,
                    score=evaluation.score,
                    cost_usd=evaluation.cost_usd,
                    latency_ms=evaluation.latency_ms,
                    evaluated_at=evaluation.evaluated_at,
                )
            )
        return evaluation

    def list_evaluations(self, experiment_id: UUID) -> Sequence[ExperimentEvaluation]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(experiment_evaluations).where(
                    experiment_evaluations.c.experiment_id == experiment_id
                )
            ).mappings().all()

        return [
            ExperimentEvaluation(
                eval_id=r["eval_id"],
                experiment_id=r["experiment_id"],
                variant_id=r["variant_id"],
                trace_id=r["trace_id"],
                score=float(r["score"]),
                cost_usd=float(r["cost_usd"]),
                latency_ms=float(r["latency_ms"]),
                evaluated_at=r["evaluated_at"],
            )
            for r in rows
        ]
