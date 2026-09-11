"""Trusted replay target boundary and safe deterministic local target."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from agentlens.domain import JSONValue, Span, Status, Trace
from agentlens.domain.types import SpanType

from .models import ReplayTargetResponse

LOCAL_TARGET_PROFILE_ID = "target-local-echo-v1"


@dataclass(frozen=True, slots=True)
class ReplayExecutionContext:
    project_id: str
    replay_run_id: UUID
    execution_id: UUID
    case_id: UUID
    correlation_id: str


@dataclass(frozen=True, slots=True)
class ReplayTargetProfile:
    profile_id: str
    name: str
    target_type: str
    version: str
    safety_class: str
    project_id: str | None = None
    configuration_reference: str = "operator-configured"

    def __post_init__(self) -> None:
        if not self.profile_id or len(self.profile_id) > 255:
            raise ValueError("profile_id must be non-empty and bounded")
        if self.safety_class not in {"read_only", "sandbox", "side_effectful"}:
            raise ValueError("unsupported target safety class")


class ReplayTarget(Protocol):
    def execute(
        self,
        case_input: JSONValue,
        context: ReplayExecutionContext,
    ) -> ReplayTargetResponse: ...


class ReplayTargetError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class TrustedReplayTargetRegistry:
    """Operator-populated registry; tenant requests can only select a profile ID."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[ReplayTargetProfile, ReplayTarget]] = {}

    def register(self, profile: ReplayTargetProfile, target: ReplayTarget) -> None:
        if not callable(getattr(target, "execute", None)):
            raise ValueError("target must implement execute")
        self._items[profile.profile_id] = (profile, target)

    def get(
        self, project_id: str, profile_id: str
    ) -> tuple[ReplayTargetProfile, ReplayTarget] | None:
        item = self._items.get(profile_id)
        if item is None or item[0].project_id not in {None, project_id}:
            return None
        return item

    def list(self, project_id: str) -> tuple[ReplayTargetProfile, ...]:
        return tuple(
            profile
            for profile, _ in self._items.values()
            if profile.project_id in {None, project_id}
        )


class LocalEchoReplayTarget:
    """Deterministic in-process test target; it is not a production AI adapter."""

    def execute(
        self, case_input: JSONValue, context: ReplayExecutionContext
    ) -> ReplayTargetResponse:
        behavior: Mapping[str, object] = {}
        if isinstance(case_input, dict) and isinstance(case_input.get("__replay_behavior"), dict):
            behavior = cast(Mapping[str, object], case_input["__replay_behavior"])
        mode = behavior.get("mode", "success")
        if mode == "delay":
            seconds = behavior.get("seconds", 0.1)
            if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
                raise ReplayTargetError("invalid_target_input")
            time.sleep(max(0.0, min(float(seconds), 60.0)))
        if mode == "error":
            raise ReplayTargetError(
                "temporary_target_failure" if behavior.get("temporary") else "target_error",
                retryable=bool(behavior.get("temporary")),
            )
        if mode == "malformed":
            return cast(ReplayTargetResponse, object())
        output = case_input
        if isinstance(case_input, dict) and "__replay_output" in case_input:
            output = case_input["__replay_output"]
        started = datetime.now(UTC)
        trace_id = uuid4()
        ended = datetime.now(UTC)
        trace = Trace(
            trace_id=trace_id,
            project_id=context.project_id,
            name="replay-local-echo",
            started_at=started,
            ended_at=ended,
            status=Status.OK,
            attributes={
                "agentlens.replay_run_id": str(context.replay_run_id),
                "agentlens.replay_execution_id": str(context.execution_id),
                "agentlens.replay_case_id": str(context.case_id),
            },
            spans=(
                Span(
                    trace_id=trace_id,
                    span_type=SpanType.AGENT,
                    name="local-echo",
                    started_at=started,
                    ended_at=ended,
                    status=Status.OK,
                    input=case_input,
                    output=output,
                    attributes={"agentlens.replay_correlation_id": context.correlation_id},
                ),
            ),
        )
        return ReplayTargetResponse(output=output, trace=trace)


__all__ = [
    "LOCAL_TARGET_PROFILE_ID",
    "LocalEchoReplayTarget",
    "ReplayExecutionContext",
    "ReplayTarget",
    "ReplayTargetError",
    "ReplayTargetProfile",
    "TrustedReplayTargetRegistry",
]
