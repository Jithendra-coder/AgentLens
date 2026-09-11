"""Custom evaluator plugin domain models and typed evaluation context ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from agentlens.domain import Span, Trace


@dataclass(frozen=True, slots=True)
class SpanContextView:
    """Read-only view of a trace span passed into custom evaluators."""

    span_id: str
    name: str
    span_type: str
    status: str
    started_at: str
    ended_at: str | None
    attributes: dict[str, Any] = field(default_factory=dict)
    input: Any = None
    output: Any = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_span(cls, span: Span) -> SpanContextView:
        err_dict = None
        if span.error is not None:
            err_dict = {
                "error_type": span.error.error_type,
                "message": span.error.message,
            }
        return cls(
            span_id=str(span.span_id),
            name=span.name,
            span_type=str(span.span_type),
            status=str(span.status),
            started_at=span.started_at.isoformat(),
            ended_at=span.ended_at.isoformat() if span.ended_at is not None else None,
            attributes=dict(span.attributes or {}),
            input=span.input,
            output=span.output,
            error=err_dict,
        )


@dataclass(frozen=True, slots=True)
class EvaluatorContext:
    """Safe, structured execution context provided to custom evaluator plugins."""

    trace_id: str
    project_id: str
    name: str
    status: str
    started_at: str
    ended_at: str | None
    attributes: dict[str, Any] = field(default_factory=dict)
    spans: list[SpanContextView] = field(default_factory=list)

    @classmethod
    def from_trace(cls, trace: Trace) -> EvaluatorContext:
        return cls(
            trace_id=str(trace.trace_id),
            project_id=trace.project_id,
            name=trace.name,
            status=str(trace.status),
            started_at=trace.started_at.isoformat(),
            ended_at=trace.ended_at.isoformat() if trace.ended_at is not None else None,
            attributes=dict(trace.attributes or {}),
            spans=[SpanContextView.from_span(s) for s in trace.spans],
        )


@dataclass(frozen=True, slots=True)
class CustomEvaluationOutput:
    """Structured evaluation output returned by a custom evaluator plugin."""

    score: float
    passed: bool
    findings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            msg = f"Custom evaluator score must be between 0.0 and 1.0, got {self.score}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class CustomEvaluatorPlugin:
    """Metadata and code representation of a custom evaluator plugin."""

    plugin_id: UUID = field(default_factory=uuid4)
    project_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    evaluator_type: str = "deterministic"
    description: str | None = None
    code_body: str = ""
    schema_parameters: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
