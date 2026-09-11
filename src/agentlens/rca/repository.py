"""Persistence protocol and implementations for RCA reports and failure clusters ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.rca.clusterer import FailureClusterer
from agentlens.rca.models import (
    FailureCluster,
    RCAReport,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    failure_clusters,
    rca_reports,
)


class RCARepository(Protocol):
    """Protocol for persisting RCA diagnostic reports and failure clusters."""

    def save_report(self, report: RCAReport) -> RCAReport: ...

    def get_report(self, rca_id: UUID) -> RCAReport | None: ...

    def list_reports(self, project_id: str) -> Sequence[RCAReport]: ...

    def list_clusters(self, project_id: str) -> Sequence[FailureCluster]: ...

    def record_failure_cluster(
        self, project_id: str, raw_error: str, name: str | None = None
    ) -> FailureCluster: ...


class InMemoryRCARepository:
    """In-memory RCA repository."""

    def __init__(self) -> None:
        self._reports: dict[UUID, RCAReport] = {}
        self._clusters: list[FailureCluster] = []

    def save_report(self, report: RCAReport) -> RCAReport:
        self._reports[report.rca_id] = report
        return report

    def get_report(self, rca_id: UUID) -> RCAReport | None:
        return self._reports.get(rca_id)

    def list_reports(self, project_id: str) -> Sequence[RCAReport]:
        matched = [r for r in self._reports.values() if r.project_id == project_id]
        return sorted(matched, key=lambda x: x.created_at, reverse=True)

    def list_clusters(self, project_id: str) -> Sequence[FailureCluster]:
        matched = [c for c in self._clusters if c.project_id == project_id]
        return sorted(matched, key=lambda x: x.occurrences_count, reverse=True)

    def record_failure_cluster(
        self, project_id: str, raw_error: str, name: str | None = None
    ) -> FailureCluster:
        return FailureClusterer.cluster_or_update(
            self._clusters, project_id, raw_error, name=name
        )


class PostgresRCARepository:
    """PostgreSQL implementation of RCARepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def save_report(self, report: RCAReport) -> RCAReport:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(rca_reports).values(
                    rca_id=report.rca_id,
                    project_id=report.project_id,
                    trace_id=report.trace_id,
                    incident_id=report.incident_id,
                    failure_category=report.failure_category,
                    root_cause_summary=report.root_cause_summary,
                    confidence_score=report.confidence_score,
                    recommended_action=report.recommended_action,
                    created_at=report.created_at,
                )
            )
        return report

    def get_report(self, rca_id: UUID) -> RCAReport | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(rca_reports).where(rca_reports.c.rca_id == rca_id)
            ).mappings().first()
            if r is None:
                return None
            return RCAReport(
                rca_id=r["rca_id"],
                project_id=r["project_id"],
                trace_id=r["trace_id"],
                incident_id=r["incident_id"],
                failure_category=r["failure_category"],
                root_cause_summary=r["root_cause_summary"],
                confidence_score=float(r["confidence_score"]),
                recommended_action=r["recommended_action"],
                created_at=r["created_at"],
            )

    def list_reports(self, project_id: str) -> Sequence[RCAReport]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(rca_reports)
                .where(rca_reports.c.project_id == project_id)
                .order_by(rca_reports.c.created_at.desc())
            ).mappings().all()
            return [
                RCAReport(
                    rca_id=r["rca_id"],
                    project_id=r["project_id"],
                    trace_id=r["trace_id"],
                    incident_id=r["incident_id"],
                    failure_category=r["failure_category"],
                    root_cause_summary=r["root_cause_summary"],
                    confidence_score=float(r["confidence_score"]),
                    recommended_action=r["recommended_action"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def list_clusters(self, project_id: str) -> Sequence[FailureCluster]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(failure_clusters)
                .where(failure_clusters.c.project_id == project_id)
                .order_by(failure_clusters.c.occurrences_count.desc())
            ).mappings().all()
            return [
                FailureCluster(
                    cluster_id=r["cluster_id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    failure_pattern=r["failure_pattern"],
                    occurrences_count=int(r["occurrences_count"]),
                    first_seen=r["first_seen"],
                    last_seen=r["last_seen"],
                )
                for r in rows
            ]

    def record_failure_cluster(
        self, project_id: str, raw_error: str, name: str | None = None
    ) -> FailureCluster:
        existing = list(self.list_clusters(project_id))
        updated = FailureClusterer.cluster_or_update(existing, project_id, raw_error, name=name)

        with self._engine.begin() as conn:
            conn.execute(
                sa.delete(failure_clusters).where(
                    failure_clusters.c.cluster_id == updated.cluster_id
                )
            )
            conn.execute(
                sa.insert(failure_clusters).values(
                    cluster_id=updated.cluster_id,
                    project_id=updated.project_id,
                    name=updated.name,
                    failure_pattern=updated.failure_pattern,
                    occurrences_count=updated.occurrences_count,
                    first_seen=updated.first_seen,
                    last_seen=updated.last_seen,
                )
            )
        return updated
