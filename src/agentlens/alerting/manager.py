"""Incident lifecycle transition management ."""

from __future__ import annotations

from datetime import UTC, datetime

from agentlens.alerting.models import IncidentRecord


class IncidentManager:
    """Validates and applies lifecycle state transitions for incidents."""

    @staticmethod
    def update_status(
        incident: IncidentRecord,
        new_status: str,
        user: str | None = None,
    ) -> IncidentRecord:
        if new_status not in ("open", "acknowledged", "resolved"):
            raise ValueError(f"Invalid incident status: '{new_status}'.")

        acknowledged_by = incident.acknowledged_by
        resolved_at = incident.resolved_at

        if new_status == "acknowledged":
            acknowledged_by = user or "system"
        elif new_status == "resolved":
            resolved_at = datetime.now(UTC)

        return IncidentRecord(
            incident_id=incident.incident_id,
            project_id=incident.project_id,
            rule_id=incident.rule_id,
            title=incident.title,
            details=incident.details,
            severity=incident.severity,
            status=new_status,
            acknowledged_by=acknowledged_by,
            resolved_at=resolved_at,
            created_at=incident.created_at,
        )
