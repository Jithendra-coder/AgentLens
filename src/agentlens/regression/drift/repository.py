"""Persistence protocol and implementations for quality baselines and drift observations ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.regression.drift.models import (
    DriftObservation,
    QualityBaseline,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    drift_observations,
    quality_baselines,
)


class DriftRepository(Protocol):
    """Protocol for persisting baselines and drift observations."""

    def save_baseline(self, baseline: QualityBaseline) -> QualityBaseline: ...

    def get_baseline(self, baseline_id: UUID) -> QualityBaseline | None: ...

    def list_baselines(self, project_id: str) -> Sequence[QualityBaseline]: ...

    def delete_baseline(self, baseline_id: UUID) -> bool: ...

    def record_observation(self, observation: DriftObservation) -> DriftObservation: ...

    def list_observations(
        self, project_id: str, baseline_id: UUID | None = None
    ) -> Sequence[DriftObservation]: ...


class InMemoryDriftRepository:
    """In-memory baseline and drift repository."""

    def __init__(self) -> None:
        self._baselines: dict[UUID, QualityBaseline] = {}
        self._observations: list[DriftObservation] = []

    def save_baseline(self, baseline: QualityBaseline) -> QualityBaseline:
        self._baselines[baseline.baseline_id] = baseline
        return baseline

    def get_baseline(self, baseline_id: UUID) -> QualityBaseline | None:
        return self._baselines.get(baseline_id)

    def list_baselines(self, project_id: str) -> Sequence[QualityBaseline]:
        return [b for b in self._baselines.values() if b.project_id == project_id]

    def delete_baseline(self, baseline_id: UUID) -> bool:
        self._observations = [o for o in self._observations if o.baseline_id != baseline_id]
        return self._baselines.pop(baseline_id, None) is not None

    def record_observation(self, observation: DriftObservation) -> DriftObservation:
        self._observations.append(observation)
        return observation

    def list_observations(
        self, project_id: str, baseline_id: UUID | None = None
    ) -> Sequence[DriftObservation]:
        matched = [o for o in self._observations if o.project_id == project_id]
        if baseline_id is not None:
            matched = [o for o in matched if o.baseline_id == baseline_id]
        return list(reversed(matched))


class PostgresDriftRepository:
    """PostgreSQL implementation of DriftRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def save_baseline(self, baseline: QualityBaseline) -> QualityBaseline:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(quality_baselines).values(
                    baseline_id=baseline.baseline_id,
                    project_id=baseline.project_id,
                    name=baseline.name,
                    metric_name=baseline.metric_name,
                    baseline_mean=baseline.baseline_mean,
                    baseline_std=baseline.baseline_std,
                    window_size=baseline.window_size,
                    status=baseline.status,
                    created_at=baseline.created_at,
                )
            )
        return baseline

    def get_baseline(self, baseline_id: UUID) -> QualityBaseline | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(quality_baselines).where(
                    quality_baselines.c.baseline_id == baseline_id
                )
            ).mappings().first()
            if r is None:
                return None
            return QualityBaseline(
                baseline_id=r["baseline_id"],
                project_id=r["project_id"],
                name=r["name"],
                metric_name=r["metric_name"],
                baseline_mean=float(r["baseline_mean"]),
                baseline_std=float(r["baseline_std"]),
                window_size=int(r["window_size"]),
                status=r["status"],
                created_at=r["created_at"],
            )

    def list_baselines(self, project_id: str) -> Sequence[QualityBaseline]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(quality_baselines).where(quality_baselines.c.project_id == project_id)
            ).mappings().all()
            return [
                QualityBaseline(
                    baseline_id=r["baseline_id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    metric_name=r["metric_name"],
                    baseline_mean=float(r["baseline_mean"]),
                    baseline_std=float(r["baseline_std"]),
                    window_size=int(r["window_size"]),
                    status=r["status"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_baseline(self, baseline_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(quality_baselines).where(
                    quality_baselines.c.baseline_id == baseline_id
                )
            )
            return bool(res.rowcount > 0)

    def record_observation(self, observation: DriftObservation) -> DriftObservation:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(drift_observations).values(
                    drift_id=observation.drift_id,
                    baseline_id=observation.baseline_id,
                    project_id=observation.project_id,
                    observed_mean=observation.observed_mean,
                    z_score=observation.z_score,
                    drift_magnitude_pct=observation.drift_magnitude_pct,
                    drift_type=observation.drift_type,
                    is_alert=observation.is_alert,
                    observed_at=observation.observed_at,
                )
            )
        return observation

    def list_observations(
        self, project_id: str, baseline_id: UUID | None = None
    ) -> Sequence[DriftObservation]:
        with self._engine.connect() as conn:
            stmt = sa.select(drift_observations).where(
                drift_observations.c.project_id == project_id
            )
            if baseline_id is not None:
                stmt = stmt.where(drift_observations.c.baseline_id == baseline_id)
            stmt = stmt.order_by(drift_observations.c.observed_at.desc())

            rows = conn.execute(stmt).mappings().all()
            return [
                DriftObservation(
                    drift_id=r["drift_id"],
                    baseline_id=r["baseline_id"],
                    project_id=r["project_id"],
                    observed_mean=float(r["observed_mean"]),
                    z_score=float(r["z_score"]),
                    drift_magnitude_pct=float(r["drift_magnitude_pct"]),
                    drift_type=r["drift_type"],
                    is_alert=bool(r["is_alert"]),
                    observed_at=r["observed_at"],
                )
                for r in rows
            ]
