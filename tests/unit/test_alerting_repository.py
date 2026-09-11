"""Unit tests for InMemoryAlertingRepository lifecycle."""

from __future__ import annotations

from uuid import uuid4

from agentlens.alerting.models import AlertRule, IncidentRecord
from agentlens.alerting.repository import InMemoryAlertingRepository


def test_in_memory_alerting_repository_lifecycle() -> None:
    repo = InMemoryAlertingRepository()
    rule_id = uuid4()
    rule = AlertRule(
        rule_id=rule_id,
        project_id="proj-repo-test",
        name="PagerDuty P1 Escalation",
        trigger_type="health_critical",
        channel_type="pagerduty",
        destination_url="https://events.pagerduty.com/v2/enqueue",
    )

    # 1. Save & get rule
    saved_r = repo.save_rule(rule)
    assert saved_r.rule_id == rule_id

    fetched_r = repo.get_rule(rule_id)
    assert fetched_r is not None
    assert fetched_r.channel_type == "pagerduty"

    # 2. List rules
    rules = repo.list_rules("proj-repo-test")
    assert len(rules) == 1

    # 3. Incidents lifecycle
    inc_id = uuid4()
    inc = IncidentRecord(
        incident_id=inc_id,
        project_id="proj-repo-test",
        title="High Error Outage",
        details="500 Internal Errors > 15%",
        severity="P1",
        status="open",
    )
    repo.save_incident(inc)

    fetched_i = repo.get_incident(inc_id)
    assert fetched_i is not None
    assert fetched_i.severity == "P1"

    incidents = repo.list_incidents("proj-repo-test", status="open")
    assert len(incidents) == 1

    # 4. Delete rule
    assert repo.delete_rule(rule_id) is True
    assert repo.get_rule(rule_id) is None
