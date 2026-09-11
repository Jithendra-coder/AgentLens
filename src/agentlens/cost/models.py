"""Cost intelligence and budget domain models ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Pricing rates per 1,000 tokens for a specific model or regex pattern."""

    provider: str
    model_pattern: str
    input_cost_per_1k: float  # USD per 1k input tokens
    output_cost_per_1k: float  # USD per 1k output tokens
    pricing_id: UUID = field(default_factory=uuid4)
    effective_from: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.input_cost_per_1k < 0.0 or self.output_cost_per_1k < 0.0:
            raise ValueError("Token pricing rates cannot be negative.")


@dataclass(frozen=True, slots=True)
class SpanCostRecord:
    """Calculated cost and token attribution for a single span."""

    span_id: UUID
    trace_id: UUID
    project_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_cost_usd: float
    calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class CostBudget:
    """Budget definition and threshold alert rules for a project."""

    project_id: str
    name: str
    amount_usd: float
    period: str = "monthly"  # "daily" | "monthly"
    alert_threshold_pct: float = 80.0
    notification_webhook_url: str | None = None
    budget_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.amount_usd <= 0.0:
            raise ValueError("Budget amount_usd must be greater than 0.")
        if not (0.0 < self.alert_threshold_pct <= 100.0):
            raise ValueError("alert_threshold_pct must be between 0.0 and 100.0.")


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    """Active evaluation of current spend vs budget ceiling."""

    budget: CostBudget
    current_spend_usd: float
    burn_percentage: float
    is_breached: bool
    alert_triggered: bool


@dataclass(frozen=True, slots=True)
class CostBreakdownItem:
    """Aggregated cost and token metric for a single dimension slice."""

    dimension_key: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    percentage: float


@dataclass(frozen=True, slots=True)
class CostSummary:
    """Comprehensive multi-dimensional cost analytics report."""

    project_id: str
    total_cost_usd: float
    total_tokens: int
    by_model: list[CostBreakdownItem] = field(default_factory=list)
    by_agent: list[CostBreakdownItem] = field(default_factory=list)
    by_span_type: list[CostBreakdownItem] = field(default_factory=list)
