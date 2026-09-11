"""Persistence protocol and implementations for alert rules and incidents ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.alerting.models import (
    AlertRule,
    IncidentRecord,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    alert_rules,
    incident_records,
)


class AlertingRepository(Protocol):
    """Protocol for persisting alert policies and enterprise incidents."""

    def save_rule(self, rule: AlertRule) -> AlertRule: ...

    def get_rule(self, rule_id: UUID) -> AlertRule | None: ...

    def list_rules(self, project_id: str) -> Sequence[AlertRule]: ...

    def delete_rule(self, rule_id: UUID) -> bool: ...

    def save_incident(self, incident: IncidentRecord) -> IncidentRecord: ...

    def get_incident(self, incident_id: UUID) -> IncidentRecord | None: ...

    def list_incidents(
        self, project_id: str, status: str | None = None
    ) -> Sequence[IncidentRecord]: ...


class InMemoryAlertingRepository:
    """In-memory alert rules and incidents repository."""

    def __init__(self) -> None:
        self._rules: dict[UUID, AlertRule] = {}
        self._incidents: dict[UUID, IncidentRecord] = {}

    def save_rule(self, rule: AlertRule) -> AlertRule:
        self._rules[rule.rule_id] = rule
        return rule

    def get_rule(self, rule_id: UUID) -> AlertRule | None:
        return self._rules.get(rule_id)

    def list_rules(self, project_id: str) -> Sequence[AlertRule]:
        return [r for r in self._rules.values() if r.project_id == project_id]

    def delete_rule(self, rule_id: UUID) -> bool:
        return self._rules.pop(rule_id, None) is not None

    def save_incident(self, incident: IncidentRecord) -> IncidentRecord:
        self._incidents[incident.incident_id] = incident
        return incident

    def get_incident(self, incident_id: UUID) -> IncidentRecord | None:
        return self._incidents.get(incident_id)

    def list_incidents(
        self, project_id: str, status: str | None = None
    ) -> Sequence[IncidentRecord]:
        matched = [i for i in self._incidents.values() if i.project_id == project_id]
        if status is not None:
            matched = [i for i in matched if i.status == status]
        return sorted(matched, key=lambda x: x.created_at, reverse=True)


class PostgresAlertingRepository:
    """PostgreSQL implementation of AlertingRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def save_rule(self, rule: AlertRule) -> AlertRule:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(alert_rules).values(
                    rule_id=rule.rule_id,
                    project_id=rule.project_id,
                    name=rule.name,
                    trigger_type=rule.trigger_type,
                    channel_type=rule.channel_type,
                    destination_url=rule.destination_url,
                    is_enabled=rule.is_enabled,
                    cooldown_seconds=rule.cooldown_seconds,
                    created_at=rule.created_at,
                )
            )
        return rule

    def get_rule(self, rule_id: UUID) -> AlertRule | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(alert_rules).where(alert_rules.c.rule_id == rule_id)
            ).mappings().first()
            if r is None:
                return None
            return AlertRule(
                rule_id=r["rule_id"],
                project_id=r["project_id"],
                name=r["name"],
                trigger_type=r["trigger_type"],
                channel_type=r["channel_type"],
                destination_url=r["destination_url"],
                is_enabled=bool(r["is_enabled"]),
                cooldown_seconds=int(r["cooldown_seconds"]),
                created_at=r["created_at"],
            )

    def list_rules(self, project_id: str) -> Sequence[AlertRule]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(alert_rules).where(alert_rules.c.project_id == project_id)
            ).mappings().all()
            return [
                AlertRule(
                    rule_id=r["rule_id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    trigger_type=r["trigger_type"],
                    channel_type=r["channel_type"],
                    destination_url=r["destination_url"],
                    is_enabled=bool(r["is_enabled"]),
                    cooldown_seconds=int(r["cooldown_seconds"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_rule(self, rule_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(alert_rules).where(alert_rules.c.rule_id == rule_id)
            )
            return bool(res.rowcount > 0)

    def save_incident(self, incident: IncidentRecord) -> IncidentRecord:
        with self._engine.begin() as conn:
            # Delete if exists (upsert simulation)
            conn.execute(
                sa.delete(incident_records).where(
                    incident_records.c.incident_id == incident.incident_id
                )
            )
            conn.execute(
                sa.insert(incident_records).values(
                    incident_id=incident.incident_id,
                    project_id=incident.project_id,
                    rule_id=incident.rule_id,
                    title=incident.title,
                    severity=incident.severity,
                    status=incident.status,
                    details=incident.details,
                    acknowledged_by=incident.acknowledged_by,
                    resolved_at=incident.resolved_at,
                    created_at=incident.created_at,
                )
            )
        return incident

    def get_incident(self, incident_id: UUID) -> IncidentRecord | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(incident_records).where(
                    incident_records.c.incident_id == incident_id
                )
            ).mappings().first()
            if r is None:
                return None
            return IncidentRecord(
                incident_id=r["incident_id"],
                project_id=r["project_id"],
                rule_id=r["rule_id"],
                title=r["title"],
                severity=r["severity"],
                status=r["status"],
                details=r["details"],
                acknowledged_by=r["acknowledged_by"],
                resolved_at=r["resolved_at"],
                created_at=r["created_at"],
            )

    def list_incidents(
        self, project_id: str, status: str | None = None
    ) -> Sequence[IncidentRecord]:
        with self._engine.connect() as conn:
            stmt = sa.select(incident_records).where(
                incident_records.c.project_id == project_id
            )
            if status is not None:
                stmt = stmt.where(incident_records.c.status == status)
            stmt = stmt.order_by(incident_records.c.created_at.desc())

            rows = conn.execute(stmt).mappings().all()
            return [
                IncidentRecord(
                    incident_id=r["incident_id"],
                    project_id=r["project_id"],
                    rule_id=r["rule_id"],
                    title=r["title"],
                    severity=r["severity"],
                    status=r["status"],
                    details=r["details"],
                    acknowledged_by=r["acknowledged_by"],
                    resolved_at=r["resolved_at"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
