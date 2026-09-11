"""Domain models for Multi-Channel Alerting, Notification Webhooks & Incident Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class AlertRule:
    """Routing policy rule for dispatching alerts to external channels."""

    project_id: str
    name: str
    trigger_type: str  # "drift_alert" | "health_critical" | "budget_exhausted"
    channel_type: str  # "slack" | "pagerduty" | "webhook" | "email"
    destination_url: str
    is_enabled: bool = True
    cooldown_seconds: int = 300
    rule_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("AlertRule name cannot be empty.")
        if not self.project_id:
            raise ValueError("AlertRule project_id cannot be empty.")
        if not self.destination_url:
            raise ValueError("AlertRule destination_url cannot be empty.")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative.")


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    """Enterprise incident record with lifecycle tracking."""

    project_id: str
    title: str
    details: str
    severity: str = "P2"  # "P1" | "P2" | "P3"
    status: str = "open"  # "open" | "acknowledged" | "resolved"
    rule_id: UUID | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    incident_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("Incident title cannot be empty.")
        if not self.project_id:
            raise ValueError("Incident project_id cannot be empty.")


@dataclass(frozen=True, slots=True)
class AlertTriggerEvent:
    """Incoming event to be evaluated against alert rules."""

    project_id: str
    trigger_type: str
    title: str
    details: str
    severity: str = "P2"


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Outcome of attempting to dispatch an alert to a configured destination."""

    rule_id: UUID
    channel_type: str
    destination_url: str
    dispatched: bool
    reason: str
