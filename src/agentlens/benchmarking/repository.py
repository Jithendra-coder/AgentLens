"""Benchmarking and qualification persistence protocol and implementations ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.benchmarking.models import (
    ModelBenchmark,
    ModelBenchmarkRun,
    ModelQualification,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    model_benchmark_runs,
    model_benchmarks,
    model_qualifications,
)


class BenchmarkRepository(Protocol):
    """Protocol for persisting benchmark suites, run metrics, and qualification records."""

    def save_benchmark(self, benchmark: ModelBenchmark) -> ModelBenchmark: ...

    def get_benchmark(self, benchmark_id: UUID) -> ModelBenchmark | None: ...

    def list_benchmarks(self, project_id: str) -> Sequence[ModelBenchmark]: ...

    def delete_benchmark(self, benchmark_id: UUID) -> bool: ...

    def record_run(self, run: ModelBenchmarkRun) -> ModelBenchmarkRun: ...

    def list_runs(
        self, project_id: str, benchmark_id: UUID | None = None
    ) -> Sequence[ModelBenchmarkRun]: ...

    def save_qualification(self, qualification: ModelQualification) -> ModelQualification: ...

    def list_qualifications(self, project_id: str) -> Sequence[ModelQualification]: ...


class InMemoryBenchmarkRepository:
    """In-memory benchmark repository for testing and development."""

    def __init__(self) -> None:
        self._benchmarks: dict[UUID, ModelBenchmark] = {}
        self._runs: list[ModelBenchmarkRun] = []
        self._qualifications: dict[str, ModelQualification] = {}

    def save_benchmark(self, benchmark: ModelBenchmark) -> ModelBenchmark:
        self._benchmarks[benchmark.benchmark_id] = benchmark
        return benchmark

    def get_benchmark(self, benchmark_id: UUID) -> ModelBenchmark | None:
        return self._benchmarks.get(benchmark_id)

    def list_benchmarks(self, project_id: str) -> Sequence[ModelBenchmark]:
        return [b for b in self._benchmarks.values() if b.project_id == project_id]

    def delete_benchmark(self, benchmark_id: UUID) -> bool:
        self._runs = [r for r in self._runs if r.benchmark_id != benchmark_id]
        return self._benchmarks.pop(benchmark_id, None) is not None

    def record_run(self, run: ModelBenchmarkRun) -> ModelBenchmarkRun:
        self._runs.append(run)
        return run

    def list_runs(
        self, project_id: str, benchmark_id: UUID | None = None
    ) -> Sequence[ModelBenchmarkRun]:
        matched = [r for r in self._runs if r.project_id == project_id]
        if benchmark_id is not None:
            matched = [r for r in matched if r.benchmark_id == benchmark_id]
        return list(reversed(matched))

    def save_qualification(self, qualification: ModelQualification) -> ModelQualification:
        key = f"{qualification.project_id}:{qualification.model_name}"
        self._qualifications[key] = qualification
        return qualification

    def list_qualifications(self, project_id: str) -> Sequence[ModelQualification]:
        return [q for q in self._qualifications.values() if q.project_id == project_id]


class PostgresBenchmarkRepository:
    """PostgreSQL implementation of BenchmarkRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def save_benchmark(self, benchmark: ModelBenchmark) -> ModelBenchmark:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(model_benchmarks).values(
                    benchmark_id=benchmark.benchmark_id,
                    project_id=benchmark.project_id,
                    name=benchmark.name,
                    description=benchmark.description,
                    created_at=benchmark.created_at,
                )
            )
        return benchmark

    def get_benchmark(self, benchmark_id: UUID) -> ModelBenchmark | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(model_benchmarks).where(
                    model_benchmarks.c.benchmark_id == benchmark_id
                )
            ).mappings().first()
            if r is None:
                return None
            return ModelBenchmark(
                benchmark_id=r["benchmark_id"],
                project_id=r["project_id"],
                name=r["name"],
                description=r["description"],
                created_at=r["created_at"],
            )

    def list_benchmarks(self, project_id: str) -> Sequence[ModelBenchmark]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(model_benchmarks).where(model_benchmarks.c.project_id == project_id)
            ).mappings().all()
            return [
                ModelBenchmark(
                    benchmark_id=r["benchmark_id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    description=r["description"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_benchmark(self, benchmark_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(model_benchmarks).where(
                    model_benchmarks.c.benchmark_id == benchmark_id
                )
            )
            return bool(res.rowcount > 0)

    def record_run(self, run: ModelBenchmarkRun) -> ModelBenchmarkRun:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(model_benchmark_runs).values(
                    run_id=run.run_id,
                    benchmark_id=run.benchmark_id,
                    project_id=run.project_id,
                    model_name=run.model_name,
                    provider_type=run.provider_type,
                    overall_score=run.overall_score,
                    mean_latency_ms=run.mean_latency_ms,
                    mean_cost_usd=run.mean_cost_usd,
                    pass_rate=run.pass_rate,
                    status=run.status,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                )
            )
        return run

    def list_runs(
        self, project_id: str, benchmark_id: UUID | None = None
    ) -> Sequence[ModelBenchmarkRun]:
        with self._engine.connect() as conn:
            stmt = sa.select(model_benchmark_runs).where(
                model_benchmark_runs.c.project_id == project_id
            )
            if benchmark_id is not None:
                stmt = stmt.where(model_benchmark_runs.c.benchmark_id == benchmark_id)
            stmt = stmt.order_by(model_benchmark_runs.c.started_at.desc())

            rows = conn.execute(stmt).mappings().all()
            return [
                ModelBenchmarkRun(
                    run_id=r["run_id"],
                    benchmark_id=r["benchmark_id"],
                    project_id=r["project_id"],
                    model_name=r["model_name"],
                    provider_type=r["provider_type"],
                    overall_score=float(r["overall_score"]),
                    mean_latency_ms=float(r["mean_latency_ms"]),
                    mean_cost_usd=float(r["mean_cost_usd"]),
                    pass_rate=float(r["pass_rate"]),
                    status=r["status"],
                    started_at=r["started_at"],
                    completed_at=r["completed_at"],
                )
                for r in rows
            ]

    def save_qualification(self, qualification: ModelQualification) -> ModelQualification:
        with self._engine.begin() as conn:
            # Delete existing qualification for project/model
            conn.execute(
                sa.delete(model_qualifications).where(
                    sa.and_(
                        model_qualifications.c.project_id == qualification.project_id,
                        model_qualifications.c.model_name == qualification.model_name,
                    )
                )
            )
            conn.execute(
                sa.insert(model_qualifications).values(
                    qualification_id=qualification.qualification_id,
                    project_id=qualification.project_id,
                    model_name=qualification.model_name,
                    provider_type=qualification.provider_type,
                    is_qualified=qualification.is_qualified,
                    min_required_score=qualification.min_required_score,
                    latest_run_id=qualification.latest_run_id,
                    updated_at=qualification.updated_at,
                )
            )
        return qualification

    def list_qualifications(self, project_id: str) -> Sequence[ModelQualification]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(model_qualifications).where(
                    model_qualifications.c.project_id == project_id
                )
            ).mappings().all()
            return [
                ModelQualification(
                    qualification_id=r["qualification_id"],
                    project_id=r["project_id"],
                    model_name=r["model_name"],
                    provider_type=r["provider_type"],
                    is_qualified=bool(r["is_qualified"]),
                    min_required_score=float(r["min_required_score"]),
                    latest_run_id=r["latest_run_id"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]
