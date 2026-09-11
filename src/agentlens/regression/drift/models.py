"""Domain models for Advanced Regression Intelligence & Baseline Drift Detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class QualityBaseline:
    """Statistical reference baseline for a key performance or quality metric."""

    project_id: str
    name: str
    metric_name: str  # "quality_score" | "latency_ms" | "cost_usd"
    baseline_mean: float
    baseline_std: float = 0.05
    window_size: int = 50
    status: str = "active"  # "active" | "deprecated"
    baseline_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("QualityBaseline name cannot be empty.")
        if not self.project_id:
            raise ValueError("QualityBaseline project_id cannot be empty.")
        if self.baseline_std < 0:
            raise ValueError("baseline_std cannot be negative.")
        if self.window_size <= 0:
            raise ValueError("window_size must be positive.")


@dataclass(frozen=True, slots=True)
class DriftObservation:
    """Recorded drift observation record."""

    baseline_id: UUID
    project_id: str
    observed_mean: float
    z_score: float
    drift_magnitude_pct: float
    drift_type: str  # "quality_drop" | "latency_spike" | "cost_inflation" | "stable"
    is_alert: bool = False
    drift_id: UUID = field(default_factory=uuid4)
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class DriftEvaluationResult:
    """Result of statistical drift evaluation against an active baseline."""

    baseline_id: UUID
    baseline_name: str
    metric_name: str
    observed_mean: float
    baseline_mean: float
    z_score: float
    drift_magnitude_pct: float
    drift_type: str
    is_alert: bool
    reason: str
