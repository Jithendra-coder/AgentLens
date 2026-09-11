"""Domain models for Automated Model Benchmarking & Qualification Pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ModelBenchmark:
    """Benchmark test suite definition."""

    project_id: str
    name: str
    description: str | None = None
    benchmark_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ModelBenchmark name cannot be empty.")
        if not self.project_id:
            raise ValueError("ModelBenchmark project_id cannot be empty.")


@dataclass(frozen=True, slots=True)
class ModelBenchmarkRun:
    """Execution run results of a benchmark against a specific model."""

    benchmark_id: UUID
    project_id: str
    model_name: str
    provider_type: str = "openai"
    overall_score: float = 0.0
    mean_latency_ms: float = 0.0
    mean_cost_usd: float = 0.0
    pass_rate: float = 0.0
    status: str = "completed"  # "completed" | "failed"
    run_id: UUID = field(default_factory=uuid4)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.overall_score <= 1.0):
            raise ValueError("overall_score must be between 0.0 and 1.0.")
        if not (0.0 <= self.pass_rate <= 1.0):
            raise ValueError("pass_rate must be between 0.0 and 1.0.")


@dataclass(frozen=True, slots=True)
class ModelQualification:
    """Qualification status gate for routing readiness."""

    project_id: str
    model_name: str
    provider_type: str = "openai"
    is_qualified: bool = False
    min_required_score: float = 0.8
    latest_run_id: UUID | None = None
    qualification_id: UUID = field(default_factory=uuid4)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ParetoPoint:
    """A point representing a model on the Cost vs Quality evaluation plane."""

    model_name: str
    provider_type: str
    quality_score: float
    cost_per_1k: float
    latency_ms: float
    is_optimal: bool  # True if lying on the non-dominated Pareto frontier


@dataclass(frozen=True, slots=True)
class ParetoFrontierReport:
    """Aggregated Cost/Quality Pareto Frontier summary."""

    project_id: str
    benchmark_id: UUID | None
    points: list[ParetoPoint] = field(default_factory=list)
