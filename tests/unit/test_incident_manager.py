"""Unit tests  IncidentManager lifecycle transitions."""

from __future__ import annotations

import pytest

from agentlens.alerting.manager import IncidentManager
from agentlens.alerting.models import IncidentRecord


def test_incident_manager_lifecycle_transitions() -> None:
    inc = IncidentRecord(
        project_id="proj-inc-test",
        title="Degraded Model Routing",
        details="Cost tier exceeding budget",
        severity="P2",
        status="open",
    )
    assert inc.status == "open"
    assert inc.acknowledged_by is None
    assert inc.resolved_at is None

    # Transition to acknowledged
    ack = IncidentManager.update_status(inc, "acknowledged", user="alice@agentlens.io")
    assert ack.status == "acknowledged"
    assert ack.acknowledged_by == "alice@agentlens.io"
    assert ack.resolved_at is None

    # Transition to resolved
    res = IncidentManager.update_status(ack, "resolved")
    assert res.status == "resolved"
    assert res.resolved_at is not None

    # Invalid status handling
    with pytest.raises(ValueError, match="Invalid incident status"):
        IncidentManager.update_status(res, "unknown_status")
