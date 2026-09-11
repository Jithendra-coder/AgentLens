"""Domain models for Adaptive Quality and Cost-Aware Model Routing Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TaskComplexity:
    """Classified task classification and complexity assessment."""

    task_type: str  # "code" | "rag" | "extraction" | "reasoning" | "general"
    complexity_score: float  # 0.0 (simple) to 1.0 (deep reasoning/complex)
    detected_features: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RoutingRule:
    """Routing policy rule governing model selection."""

    project_id: str
    name: str
    task_type: str = "general"
    min_quality_score: float = 0.8
    max_cost_per_1k: float = 0.05
    max_latency_ms: float = 2000.0
    fallback_model: str = "gpt-4o"
    tier_priority: tuple[str, ...] = (
        "gpt-4o-mini",
        "claude-3-5-haiku",
        "gpt-4o",
        "claude-3-5-sonnet",
    )
    is_active: bool = True
    rule_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RoutingRule name cannot be empty.")
        if not self.project_id:
            raise ValueError("RoutingRule project_id cannot be empty.")
        if not (0.0 <= self.min_quality_score <= 1.0):
            raise ValueError("min_quality_score must be between 0.0 and 1.0.")
        if self.max_cost_per_1k < 0.0:
            raise ValueError("max_cost_per_1k cannot be negative.")


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Audit log of a model routing choice."""

    project_id: str
    selected_model: str
    selected_provider: str
    estimated_cost_usd: float
    reason: str
    trace_id: UUID | None = None
    rule_id: UUID | None = None
    decision_id: UUID = field(default_factory=uuid4)
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class RouteRequest:
    """Input payload to the adaptive routing engine."""

    project_id: str
    prompt: str
    trace_id: UUID | None = None
    max_latency_ms: float | None = None
    min_quality_score: float | None = None


@dataclass(frozen=True, slots=True)
class RouteResult:
    """Output decision from the adaptive routing engine."""

    selected_model: str
    selected_provider: str
    task_type: str
    complexity_score: float
    estimated_cost_per_1k: float
    reason: str
    rule_id: UUID | None = None
