"""Domain models for GA Platform Readiness & End-to-End Certification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class SubsystemStatus:
    """Individual operational subsystem readiness health status."""

    name: str
    is_ready: bool
    version: str
    details: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class PlatformReadinessReport:
    """Aggregated GA platform readiness report across all 30 milestones."""

    platform_version: str
    overall_status: str  # "GA_CERTIFIED" | "DEGRADED" | "NOT_READY"
    readiness_score: float  # 0.0 to 100.0
    total_subsystems: int
    ready_subsystems: int
    subsystems: list[SubsystemStatus]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class GACertificationToken:
    """Cryptographically verifiable platform certification token."""

    certificate_id: UUID = field(default_factory=uuid4)
    platform_version: str = "1.0.0-GA"
    certification_status: str = "CERTIFIED"
    readiness_score: float = 100.0
    digital_seal: str = ""
    certified_at: datetime = field(default_factory=lambda: datetime.now(UTC))
