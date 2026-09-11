"""Persistence protocol and implementations for production monitors and health snapshots ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.monitoring.models import (
    HealthSnapshot,
    ProductionMonitor,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    production_health_snapshots,
    production_monitors,
)


class MonitoringRepository(Protocol):
    """Protocol for persisting monitors and time-series health snapshots."""

    def save_monitor(self, monitor: ProductionMonitor) -> ProductionMonitor: ...

    def get_monitor(self, monitor_id: UUID) -> ProductionMonitor | None: ...

    def list_monitors(self, project_id: str) -> Sequence[ProductionMonitor]: ...

    def delete_monitor(self, monitor_id: UUID) -> bool: ...

    def update_monitor_health(
        self, monitor_id: UUID, health_index: float, health_status: str
    ) -> bool: ...

    def record_snapshot(self, snapshot: HealthSnapshot) -> HealthSnapshot: ...

    def list_snapshots(
        self, project_id: str, monitor_id: UUID | None = None
    ) -> Sequence[HealthSnapshot]: ...


class InMemoryMonitoringRepository:
    """In-memory monitor and health snapshot repository."""

    def __init__(self) -> None:
        self._monitors: dict[UUID, ProductionMonitor] = {}
        self._snapshots: list[HealthSnapshot] = []

    def save_monitor(self, monitor: ProductionMonitor) -> ProductionMonitor:
        self._monitors[monitor.monitor_id] = monitor
        return monitor

    def get_monitor(self, monitor_id: UUID) -> ProductionMonitor | None:
        return self._monitors.get(monitor_id)

    def list_monitors(self, project_id: str) -> Sequence[ProductionMonitor]:
        return [m for m in self._monitors.values() if m.project_id == project_id]

    def delete_monitor(self, monitor_id: UUID) -> bool:
        self._snapshots = [s for s in self._snapshots if s.monitor_id != monitor_id]
        return self._monitors.pop(monitor_id, None) is not None

    def update_monitor_health(
        self, monitor_id: UUID, health_index: float, health_status: str
    ) -> bool:
        m = self._monitors.get(monitor_id)
        if m is None:
            return False
        updated = ProductionMonitor(
            monitor_id=m.monitor_id,
            project_id=m.project_id,
            name=m.name,
            sampling_rate=m.sampling_rate,
            health_status=health_status,
            health_index=health_index,
            is_active=m.is_active,
            created_at=m.created_at,
        )
        self._monitors[monitor_id] = updated
        return True

    def record_snapshot(self, snapshot: HealthSnapshot) -> HealthSnapshot:
        self._snapshots.append(snapshot)
        return snapshot

    def list_snapshots(
        self, project_id: str, monitor_id: UUID | None = None
    ) -> Sequence[HealthSnapshot]:
        matched = [s for s in self._snapshots if s.project_id == project_id]
        if monitor_id is not None:
            matched = [s for s in matched if s.monitor_id == monitor_id]
        return list(reversed(matched))


class PostgresMonitoringRepository:
    """PostgreSQL implementation of MonitoringRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def save_monitor(self, monitor: ProductionMonitor) -> ProductionMonitor:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(production_monitors).values(
                    monitor_id=monitor.monitor_id,
                    project_id=monitor.project_id,
                    name=monitor.name,
                    sampling_rate=monitor.sampling_rate,
                    health_status=monitor.health_status,
                    health_index=monitor.health_index,
                    is_active=monitor.is_active,
                    created_at=monitor.created_at,
                )
            )
        return monitor

    def get_monitor(self, monitor_id: UUID) -> ProductionMonitor | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(production_monitors).where(
                    production_monitors.c.monitor_id == monitor_id
                )
            ).mappings().first()
            if r is None:
                return None
            return ProductionMonitor(
                monitor_id=r["monitor_id"],
                project_id=r["project_id"],
                name=r["name"],
                sampling_rate=float(r["sampling_rate"]),
                health_status=r["health_status"],
                health_index=float(r["health_index"]),
                is_active=bool(r["is_active"]),
                created_at=r["created_at"],
            )

    def list_monitors(self, project_id: str) -> Sequence[ProductionMonitor]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(production_monitors).where(
                    production_monitors.c.project_id == project_id
                )
            ).mappings().all()
            return [
                ProductionMonitor(
                    monitor_id=r["monitor_id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    sampling_rate=float(r["sampling_rate"]),
                    health_status=r["health_status"],
                    health_index=float(r["health_index"]),
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_monitor(self, monitor_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(production_monitors).where(
                    production_monitors.c.monitor_id == monitor_id
                )
            )
            return bool(res.rowcount > 0)

    def update_monitor_health(
        self, monitor_id: UUID, health_index: float, health_status: str
    ) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.update(production_monitors)
                .where(production_monitors.c.monitor_id == monitor_id)
                .values(
                    health_index=health_index,
                    health_status=health_status,
                )
            )
            return bool(res.rowcount > 0)

    def record_snapshot(self, snapshot: HealthSnapshot) -> HealthSnapshot:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(production_health_snapshots).values(
                    snapshot_id=snapshot.snapshot_id,
                    monitor_id=snapshot.monitor_id,
                    project_id=snapshot.project_id,
                    health_index=snapshot.health_index,
                    p95_latency_ms=snapshot.p95_latency_ms,
                    mean_quality_score=snapshot.mean_quality_score,
                    error_rate=snapshot.error_rate,
                    total_spans_evaluated=snapshot.total_spans_evaluated,
                    recorded_at=snapshot.recorded_at,
                )
            )
        return snapshot

    def list_snapshots(
        self, project_id: str, monitor_id: UUID | None = None
    ) -> Sequence[HealthSnapshot]:
        with self._engine.connect() as conn:
            stmt = sa.select(production_health_snapshots).where(
                production_health_snapshots.c.project_id == project_id
            )
            if monitor_id is not None:
                stmt = stmt.where(production_health_snapshots.c.monitor_id == monitor_id)
            stmt = stmt.order_by(production_health_snapshots.c.recorded_at.desc())

            rows = conn.execute(stmt).mappings().all()
            return [
                HealthSnapshot(
                    snapshot_id=r["snapshot_id"],
                    monitor_id=r["monitor_id"],
                    project_id=r["project_id"],
                    health_index=float(r["health_index"]),
                    p95_latency_ms=float(r["p95_latency_ms"]),
                    mean_quality_score=float(r["mean_quality_score"]),
                    error_rate=float(r["error_rate"]),
                    total_spans_evaluated=int(r["total_spans_evaluated"]),
                    recorded_at=r["recorded_at"],
                )
                for r in rows
            ]
