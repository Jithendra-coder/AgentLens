"""Unit tests for InMemoryGovernanceRepository lifecycle."""

from __future__ import annotations

from uuid import uuid4

from agentlens.governance.models import RetentionPolicy
from agentlens.governance.repository import InMemoryGovernanceRepository


def test_in_memory_governance_repository_lifecycle() -> None:
    repo = InMemoryGovernanceRepository()
    project_id = "proj-gov-repo"

    # 1. Append audit events
    ev1 = repo.append_audit_event(
        project_id=project_id,
        actor_id="admin@agentlens.io",
        action="policy.create",
        resource_type="retention_policy",
        resource_id="pol-1",
        payload='{"days":90}',
    )
    ev2 = repo.append_audit_event(
        project_id=project_id,
        actor_id="admin@agentlens.io",
        action="policy.update",
        resource_type="retention_policy",
        resource_id="pol-1",
        payload='{"days":180}',
    )

    events = repo.list_audit_events(project_id)
    assert len(events) == 2
    assert events[1].event_hash == ev2.event_hash
    assert events[1].previous_event_hash == ev1.event_hash

    # 2. Retention policies lifecycle
    pol_id = uuid4()
    pol = RetentionPolicy(
        policy_id=pol_id,
        project_id=project_id,
        name="HIPAA 180-Day Telemetry",
        retention_days=180,
    )
    repo.save_retention_policy(pol)

    fetched_p = repo.get_retention_policy(pol_id)
    assert fetched_p is not None
    assert fetched_p.name == "HIPAA 180-Day Telemetry"

    policies = repo.list_retention_policies(project_id)
    assert len(policies) == 1

    assert repo.delete_retention_policy(pol_id) is True
    assert repo.get_retention_policy(pol_id) is None
