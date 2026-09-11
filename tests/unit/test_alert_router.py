"""Unit tests  AlertRouter and cooldown throttling."""

from __future__ import annotations

from uuid import uuid4

from agentlens.alerting.models import AlertRule, AlertTriggerEvent
from agentlens.alerting.router import AlertRouter


def test_alert_router_matching_and_cooldown() -> None:
    router = AlertRouter()
    rule_id = uuid4()
    rule = AlertRule(
        rule_id=rule_id,
        project_id="proj-alert-unit",
        name="Slack P1 Webhook",
        trigger_type="drift_alert",
        channel_type="slack",
        destination_url="https://hooks.slack.com/services/test",
        cooldown_seconds=60,
    )

    event = AlertTriggerEvent(
        project_id="proj-alert-unit",
        trigger_type="drift_alert",
        title="Quality Drop Detected",
        details="Z-score -2.85 breach",
    )

    # 1. First dispatch at t = 1000 -> Should succeed
    res1 = router.route_event(event, [rule], current_timestamp=1000.0)
    assert len(res1) == 1
    assert res1[0].dispatched is True
    assert "Successfully dispatched" in res1[0].reason

    # 2. Second dispatch at t = 1020 (< 60s cooldown) -> Should throttle
    res2 = router.route_event(event, [rule], current_timestamp=1020.0)
    assert len(res2) == 1
    assert res2[0].dispatched is False
    assert "Throttled by cooldown" in res2[0].reason

    # 3. Third dispatch at t = 1070 (>= 60s cooldown) -> Should succeed
    res3 = router.route_event(event, [rule], current_timestamp=1070.0)
    assert len(res3) == 1
    assert res3[0].dispatched is True
