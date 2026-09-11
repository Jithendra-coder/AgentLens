"""Multi-channel alert routing and storm cooldown enforcement ."""

from __future__ import annotations

import time
from collections.abc import Sequence
from uuid import UUID

from agentlens.alerting.models import (
    AlertRule,
    AlertTriggerEvent,
    DispatchResult,
)


class AlertRouter:
    """Matches events to active rules and enforces cooldown windows to prevent alert storms."""

    def __init__(self) -> None:
        self._last_dispatched: dict[UUID, float] = {}

    def route_event(
        self,
        event: AlertTriggerEvent,
        rules: Sequence[AlertRule],
        current_timestamp: float | None = None,
    ) -> list[DispatchResult]:
        now = current_timestamp if current_timestamp is not None else time.time()
        results: list[DispatchResult] = []

        matching_rules = [
            r
            for r in rules
            if r.project_id == event.project_id
            and r.is_enabled
            and r.trigger_type == event.trigger_type
        ]

        for rule in matching_rules:
            last_time = self._last_dispatched.get(rule.rule_id, 0.0)
            elapsed = now - last_time

            if elapsed < rule.cooldown_seconds:
                remaining = int(rule.cooldown_seconds - elapsed)
                results.append(
                    DispatchResult(
                        rule_id=rule.rule_id,
                        channel_type=rule.channel_type,
                        destination_url=rule.destination_url,
                        dispatched=False,
                        reason=f"Throttled by cooldown window ({remaining}s remaining).",
                    )
                )
            else:
                self._last_dispatched[rule.rule_id] = now
                results.append(
                    DispatchResult(
                        rule_id=rule.rule_id,
                        channel_type=rule.channel_type,
                        destination_url=rule.destination_url,
                        dispatched=True,
                        reason=(
                            f"Successfully dispatched alert to {rule.channel_type.upper()} "
                            f"at {rule.destination_url}."
                        ),
                    )
                )

        return results
