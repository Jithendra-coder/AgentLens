"""Experimentation, traffic splitting, and variant domain models ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ExperimentVariant:
    """A single prompt or model variant within an experiment."""

    name: str
    prompt_template: str = ""
    model_name: str = ""
    provider_type: str = "openai"
    traffic_weight: float = 0.5
    is_control: bool = False
    variant_id: UUID = field(default_factory=uuid4)
    experiment_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ExperimentVariant name cannot be empty.")
        if not (0.0 <= self.traffic_weight <= 1.0):
            raise ValueError("traffic_weight must be between 0.0 and 1.0.")


@dataclass(frozen=True, slots=True)
class Experiment:
    """Experiment definition containing variants, traffic weights, and operational status."""

    project_id: str
    name: str
    description: str | None = None
    experiment_type: str = "ab_test"  # "ab_test" | "shadow" | "canary"
    status: str = "running"  # "draft" | "running" | "paused" | "concluded"
    variants: tuple[ExperimentVariant, ...] = field(default_factory=tuple)
    experiment_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    concluded_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Experiment name cannot be empty.")
        if not self.project_id:
            raise ValueError("Experiment project_id cannot be empty.")


@dataclass(frozen=True, slots=True)
class ExperimentEvaluation:
    """Recorded metric observation for an evaluation run on a specific variant."""

    experiment_id: UUID
    variant_id: UUID
    trace_id: UUID
    score: float
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    eval_id: UUID = field(default_factory=uuid4)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class VariantComparativeMetric:
    """Statistical summary comparing a variant against the control."""

    variant_id: UUID
    name: str
    is_control: bool
    sample_count: int
    mean_score: float
    mean_cost_usd: float
    mean_latency_ms: float
    score_delta_pct: float = 0.0
    cost_delta_pct: float = 0.0
    latency_delta_pct: float = 0.0


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    """Aggregated statistical report comparing control vs treatment variants."""

    experiment_id: UUID
    project_id: str
    name: str
    status: str
    total_evaluations: int
    variants: list[VariantComparativeMetric] = field(default_factory=list)
