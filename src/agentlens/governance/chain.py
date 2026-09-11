"""Cryptographic SHA-256 audit hash chaining and verification ."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from agentlens.governance.models import (
    AuditChainVerificationResult,
    AuditEvent,
)

GENESIS_HASH = "0" * 64


class AuditHashChain:
    """Computes and cryptographically verifies immutable audit hash chains."""

    @staticmethod
    def compute_payload_hash(payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_event_hash(
        previous_event_hash: str,
        project_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload_hash: str,
        timestamp_iso: str,
    ) -> str:
        material = (
            f"{previous_event_hash}|{project_id}|{actor_id}|{action}|"
            f"{resource_type}|{resource_id}|{payload_hash}|{timestamp_iso}"
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def build_next_event(
        project_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: str,
        last_event: AuditEvent | None = None,
        event_id: UUID | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        prev_hash = last_event.event_hash if last_event else GENESIS_HASH
        ts = timestamp or datetime.now(UTC)
        p_hash = AuditHashChain.compute_payload_hash(payload)
        ev_hash = AuditHashChain.compute_event_hash(
            prev_hash,
            project_id,
            actor_id,
            action,
            resource_type,
            resource_id,
            p_hash,
            ts.isoformat(),
        )

        return AuditEvent(
            event_id=event_id or uuid4(),
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_hash=p_hash,
            previous_event_hash=prev_hash,
            event_hash=ev_hash,
            timestamp=ts,
        )

    @staticmethod
    def verify_chain(
        project_id: str,
        events: Sequence[AuditEvent],
    ) -> AuditChainVerificationResult:
        if not events:
            return AuditChainVerificationResult(
                project_id=project_id,
                total_events=0,
                is_valid=True,
                reason="Empty audit trail is valid.",
            )

        # Sort ascending by timestamp
        sorted_events = sorted(events, key=lambda x: x.timestamp)
        expected_prev = GENESIS_HASH

        for ev in sorted_events:
            # 1. Verify previous link pointer
            if ev.previous_event_hash != expected_prev:
                return AuditChainVerificationResult(
                    project_id=project_id,
                    total_events=len(events),
                    is_valid=False,
                    compromised_event_id=ev.event_id,
                    reason=(
                        f"Hash link broken at event {ev.event_id}: expected prev {expected_prev}, "
                        f"got {ev.previous_event_hash}."
                    ),
                )

            # 2. Recompute current hash
            recomputed = AuditHashChain.compute_event_hash(
                ev.previous_event_hash,
                ev.project_id,
                ev.actor_id,
                ev.action,
                ev.resource_type,
                ev.resource_id,
                ev.payload_hash,
                ev.timestamp.isoformat(),
            )
            if recomputed != ev.event_hash:
                return AuditChainVerificationResult(
                    project_id=project_id,
                    total_events=len(events),
                    is_valid=False,
                    compromised_event_id=ev.event_id,
                    reason=(
                        f"Data tampering detected at event {ev.event_id}: "
                        f"recomputed hash {recomputed} does not match {ev.event_hash}."
                    ),
                )

            expected_prev = ev.event_hash

        return AuditChainVerificationResult(
            project_id=project_id,
            total_events=len(events),
            is_valid=True,
            reason="Cryptographic hash chain is fully verified and unbroken.",
        )
