"""Domain models for Continuous Production Monitoring & Aggregated Health Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ProductionMonitor:
    """Continuous background sampling and health evaluation monitor."""

    project_id: str
    name: str
    sampling_rate: float = 0.10  # 10% default
    health_status: str = "healthy"  # "healthy" | "degraded" | "critical"
    health_index: float = 100.0  # 0 to 100
    is_active: bool = True
    monitor_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ProductionMonitor name cannot be empty.")
        if not self.project_id:
            raise ValueError("ProductionMonitor project_id cannot be empty.")
        if not (0.0 <= self.sampling_rate <= 1.0):
            raise ValueError("sampling_rate must be between 0.0 and 1.0.")
        if not (0.0 <= self.health_index <= 100.0):
            raise ValueError("health_index must be between 0.0 and 100.0.")


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    """Time-series rollup record of production health metrics."""

    monitor_id: UUID
    project_id: str
    health_index: float = 100.0
    p95_latency_ms: float = 0.0
    mean_quality_score: float = 1.0
    error_rate: float = 0.0
    total_spans_evaluated: int = 0
    snapshot_id: UUID = field(default_factory=uuid4)
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class HealthMetrics:
    """Raw input metrics for health index evaluation."""

    mean_quality_score: float = 1.0
    p95_latency_ms: float = 200.0
    error_rate: float = 0.0
    total_spans_evaluated: int = 0


@dataclass(frozen=True, slots=True)
class ProjectHealthSummary:
    """Aggregated project-level health overview."""

    project_id: str
    overall_health_index: float
    overall_health_status: str
    monitors_count: int
    active_monitors: int
