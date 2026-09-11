"""Persistence protocol and implementations for audit events and retention policies ."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

import sqlalchemy as sa

from agentlens.governance.chain import AuditHashChain
from agentlens.governance.models import (
    AuditEvent,
    RetentionPolicy,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    compliance_audit_events,
    retention_policies,
)


class GovernanceRepository(Protocol):
    """Protocol for persisting compliance audit hash chains and retention policies."""

    def append_audit_event(
        self,
        project_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: str,
    ) -> AuditEvent: ...

    def list_audit_events(self, project_id: str) -> Sequence[AuditEvent]: ...

    def save_retention_policy(self, policy: RetentionPolicy) -> RetentionPolicy: ...

    def get_retention_policy(self, policy_id: UUID) -> RetentionPolicy | None: ...

    def list_retention_policies(self, project_id: str) -> Sequence[RetentionPolicy]: ...

    def delete_retention_policy(self, policy_id: UUID) -> bool: ...


class InMemoryGovernanceRepository:
    """In-memory governance and compliance repository."""

    def __init__(self) -> None:
        self._audit_events: dict[str, list[AuditEvent]] = {}
        self._policies: dict[UUID, RetentionPolicy] = {}

    def append_audit_event(
        self,
        project_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: str,
    ) -> AuditEvent:
        events = self._audit_events.setdefault(project_id, [])
        last_ev = events[-1] if events else None

        ev = AuditHashChain.build_next_event(
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
            last_event=last_ev,
        )
        events.append(ev)
        return ev

    def list_audit_events(self, project_id: str) -> Sequence[AuditEvent]:
        return list(self._audit_events.get(project_id, []))

    def save_retention_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        self._policies[policy.policy_id] = policy
        return policy

    def get_retention_policy(self, policy_id: UUID) -> RetentionPolicy | None:
        return self._policies.get(policy_id)

    def list_retention_policies(self, project_id: str) -> Sequence[RetentionPolicy]:
        return [p for p in self._policies.values() if p.project_id == project_id]

    def delete_retention_policy(self, policy_id: UUID) -> bool:
        return self._policies.pop(policy_id, None) is not None


class PostgresGovernanceRepository:
    """PostgreSQL implementation of GovernanceRepository."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._engine = sa.create_engine(config.url)

    def append_audit_event(
        self,
        project_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: str,
    ) -> AuditEvent:
        with self._engine.begin() as conn:
            # Fetch last event for project
            last_r = conn.execute(
                sa.select(compliance_audit_events)
                .where(compliance_audit_events.c.project_id == project_id)
                .order_by(compliance_audit_events.c.timestamp.desc())
            ).mappings().first()

            last_event = (
                AuditEvent(
                    event_id=last_r["event_id"],
                    project_id=last_r["project_id"],
                    actor_id=last_r["actor_id"],
                    action=last_r["action"],
                    resource_type=last_r["resource_type"],
                    resource_id=last_r["resource_id"],
                    payload_hash=last_r["payload_hash"],
                    previous_event_hash=last_r["previous_event_hash"],
                    event_hash=last_r["event_hash"],
                    timestamp=last_r["timestamp"],
                )
                if last_r
                else None
            )

            ev = AuditHashChain.build_next_event(
                project_id=project_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload,
                last_event=last_event,
            )

            conn.execute(
                sa.insert(compliance_audit_events).values(
                    event_id=ev.event_id,
                    project_id=ev.project_id,
                    actor_id=ev.actor_id,
                    action=ev.action,
                    resource_type=ev.resource_type,
                    resource_id=ev.resource_id,
                    payload_hash=ev.payload_hash,
                    previous_event_hash=ev.previous_event_hash,
                    event_hash=ev.event_hash,
                    timestamp=ev.timestamp,
                )
            )
            return ev

    def list_audit_events(self, project_id: str) -> Sequence[AuditEvent]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(compliance_audit_events)
                .where(compliance_audit_events.c.project_id == project_id)
                .order_by(compliance_audit_events.c.timestamp.asc())
            ).mappings().all()
            return [
                AuditEvent(
                    event_id=r["event_id"],
                    project_id=r["project_id"],
                    actor_id=r["actor_id"],
                    action=r["action"],
                    resource_type=r["resource_type"],
                    resource_id=r["resource_id"],
                    payload_hash=r["payload_hash"],
                    previous_event_hash=r["previous_event_hash"],
                    event_hash=r["event_hash"],
                    timestamp=r["timestamp"],
                )
                for r in rows
            ]

    def save_retention_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        with self._engine.begin() as conn:
            conn.execute(
                sa.insert(retention_policies).values(
                    policy_id=policy.policy_id,
                    project_id=policy.project_id,
                    name=policy.name,
                    retention_days=policy.retention_days,
                    auto_redact_pii=policy.auto_redact_pii,
                    is_active=policy.is_active,
                    created_at=policy.created_at,
                )
            )
        return policy

    def get_retention_policy(self, policy_id: UUID) -> RetentionPolicy | None:
        with self._engine.connect() as conn:
            r = conn.execute(
                sa.select(retention_policies).where(
                    retention_policies.c.policy_id == policy_id
                )
            ).mappings().first()
            if r is None:
                return None
            return RetentionPolicy(
                policy_id=r["policy_id"],
                project_id=r["project_id"],
                name=r["name"],
                retention_days=int(r["retention_days"]),
                auto_redact_pii=bool(r["auto_redact_pii"]),
                is_active=bool(r["is_active"]),
                created_at=r["created_at"],
            )

    def list_retention_policies(self, project_id: str) -> Sequence[RetentionPolicy]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(retention_policies).where(
                    retention_policies.c.project_id == project_id
                )
            ).mappings().all()
            return [
                RetentionPolicy(
                    policy_id=r["policy_id"],
                    project_id=r["project_id"],
                    name=r["name"],
                    retention_days=int(r["retention_days"]),
                    auto_redact_pii=bool(r["auto_redact_pii"]),
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def delete_retention_policy(self, policy_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                sa.delete(retention_policies).where(
                    retention_policies.c.policy_id == policy_id
                )
            )
            return bool(res.rowcount > 0)
