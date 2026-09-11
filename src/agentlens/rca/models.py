"""Domain models for Automated Root-Cause Analysis (RCA) & Failure Clustering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class RCAReport:
    """Automated root-cause analysis diagnostic report."""

    project_id: str
    failure_category: str  # provider_error | timeout | prompt_injection | context_overflow
    root_cause_summary: str
    recommended_action: str
    confidence_score: float = 1.0  # 0.0 to 1.0
    trace_id: UUID | None = None
    incident_id: UUID | None = None
    rca_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("RCAReport project_id cannot be empty.")
        if not self.root_cause_summary:
            raise ValueError("RCAReport root_cause_summary cannot be empty.")
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError("confidence_score must be between 0.0 and 1.0.")


@dataclass(frozen=True, slots=True)
class FailureCluster:
    """Aggregated cluster of recurring failure signatures."""

    project_id: str
    name: str
    failure_pattern: str
    occurrences_count: int = 1
    cluster_id: UUID = field(default_factory=uuid4)
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class DiagnosticInput:
    """Raw telemetry input parameters for automated RCA diagnosis."""

    project_id: str
    error_message: str | None = None
    http_status: int | None = None
    latency_ms: float | None = None
    total_tokens: int | None = None
    prompt_text: str | None = None
    eval_score: float | None = None
    trace_id: UUID | None = None
    incident_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    """Diagnostic outcome containing root cause classification and prescribed action."""

    failure_category: str
    root_cause_summary: str
    confidence_score: float
    recommended_action: str
