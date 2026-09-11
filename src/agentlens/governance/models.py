"""Domain models for Immutable Compliance Audit Trail & Data Retention Policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Cryptographically chained immutable compliance audit record."""

    project_id: str
    actor_id: str
    action: str  # e.g., "secret.create", "routing_rule.update", "incident.resolve"
    resource_type: str  # e.g., "secret", "experiment", "incident"
    resource_id: str
    payload_hash: str
    previous_event_hash: str
    event_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("AuditEvent project_id cannot be empty.")
        if not self.action:
            raise ValueError("AuditEvent action cannot be empty.")
        if not self.event_hash:
            raise ValueError("AuditEvent event_hash cannot be empty.")


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Data lifecycle retention and PII redaction policy."""

    project_id: str
    name: str
    retention_days: int = 90
    auto_redact_pii: bool = True
    is_active: bool = True
    policy_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RetentionPolicy name cannot be empty.")
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive.")


@dataclass(frozen=True, slots=True)
class AuditChainVerificationResult:
    """Outcome of cryptographic hash chain verification."""

    project_id: str
    total_events: int
    is_valid: bool
    compromised_event_id: UUID | None = None
    reason: str = "Hash chain integrity verified."


@dataclass(frozen=True, slots=True)
class ComplianceExportBundle:
    """Cryptographically signed compliance export archive."""

    project_id: str
    total_audit_events: int
    root_hash: str
    digital_signature: str
    events: list[AuditEvent]
    export_id: UUID = field(default_factory=uuid4)
    exported_at: datetime = field(default_factory=lambda: datetime.now(UTC))
