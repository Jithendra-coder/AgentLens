"""Unit tests for AuditHashChain cryptographic chaining and tamper detection."""

from __future__ import annotations

from datetime import UTC, datetime

from agentlens.governance.chain import GENESIS_HASH, AuditHashChain
from agentlens.governance.models import AuditEvent


def test_audit_hash_chain_creation_and_tamper_detection() -> None:
    project_id = "proj-gov-test"
    t1 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 31, 12, 1, 0, tzinfo=UTC)
    t3 = datetime(2026, 8, 31, 12, 2, 0, tzinfo=UTC)

    # 1. Build chain of 3 events
    ev1 = AuditHashChain.build_next_event(
        project_id=project_id,
        actor_id="admin@agentlens.io",
        action="user.create",
        resource_type="user",
        resource_id="user-123",
        payload='{"role":"developer"}',
        timestamp=t1,
    )
    assert ev1.previous_event_hash == GENESIS_HASH

    ev2 = AuditHashChain.build_next_event(
        project_id=project_id,
        actor_id="admin@agentlens.io",
        action="secret.create",
        resource_type="secret",
        resource_id="sec-456",
        payload='{"key_name":"OPENAI_KEY"}',
        last_event=ev1,
        timestamp=t2,
    )
    assert ev2.previous_event_hash == ev1.event_hash

    ev3 = AuditHashChain.build_next_event(
        project_id=project_id,
        actor_id="developer@agentlens.io",
        action="experiment.run",
        resource_type="experiment",
        resource_id="exp-789",
        payload='{"variant":"v2"}',
        last_event=ev2,
        timestamp=t3,
    )
    assert ev3.previous_event_hash == ev2.event_hash

    # 2. Verify untampered chain
    valid_res = AuditHashChain.verify_chain(project_id, [ev1, ev2, ev3])
    assert valid_res.is_valid is True
    assert valid_res.total_events == 3
    assert valid_res.compromised_event_id is None

    # 3. Simulate tampering with event 2 payload hash
    tampered_ev2 = AuditEvent(
        event_id=ev2.event_id,
        project_id=ev2.project_id,
        actor_id=ev2.actor_id,
        action=ev2.action,
        resource_type=ev2.resource_type,
        resource_id=ev2.resource_id,
        payload_hash="tampered_hash_0000000000000000000000000000000000000000000000000000",
        previous_event_hash=ev2.previous_event_hash,
        event_hash=ev2.event_hash,
        timestamp=ev2.timestamp,
    )

    invalid_res = AuditHashChain.verify_chain(project_id, [ev1, tampered_ev2, ev3])
    assert invalid_res.is_valid is False
    assert invalid_res.compromised_event_id == ev2.event_id
    assert "Data tampering detected" in invalid_res.reason
