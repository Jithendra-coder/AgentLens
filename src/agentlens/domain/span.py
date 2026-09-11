"""Canonical timed execution spans."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from agentlens.exceptions import SerializationError, ValidationError

from .error import ErrorInfo
from .types import (
    JSONValue,
    SpanType,
    Status,
    freeze_payload,
    normalize_datetime,
    normalize_optional_uuid,
    normalize_span_type,
    normalize_status,
    normalize_uuid,
    optional_field,
    parse_datetime,
    parse_json_object,
    required_field,
    thaw_payload,
    utc_now,
)
from .usage import Usage


@dataclass(frozen=True, slots=True)
class Span:
    """A timed operation belonging to one trace."""

    span_id: UUID | str = field(default_factory=uuid4)
    trace_id: UUID | str = field(default_factory=uuid4)
    parent_span_id: UUID | str | None = None
    span_type: SpanType | str = SpanType.CUSTOM
    name: str = ""
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    status: Status | str = Status.UNSET
    input: JSONValue | None = None
    output: JSONValue | None = None
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)
    usage: Usage | None = None
    error: ErrorInfo | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "span_id", normalize_uuid(self.span_id, "span_id"))
        object.__setattr__(self, "trace_id", normalize_uuid(self.trace_id, "trace_id"))
        object.__setattr__(
            self,
            "parent_span_id",
            normalize_optional_uuid(self.parent_span_id, "parent_span_id"),
        )
        object.__setattr__(self, "span_type", normalize_span_type(self.span_type))
        if not isinstance(self.name, str):
            raise ValidationError("name must be a string")
        object.__setattr__(self, "started_at", normalize_datetime(self.started_at, "started_at"))
        if self.ended_at is not None:
            ended_at = normalize_datetime(self.ended_at, "ended_at")
            if ended_at < self.started_at:
                raise ValidationError("ended_at must be greater than or equal to started_at")
            object.__setattr__(self, "ended_at", ended_at)
        object.__setattr__(self, "status", normalize_status(self.status))
        object.__setattr__(self, "input", freeze_payload(self.input, "input"))
        object.__setattr__(self, "output", freeze_payload(self.output, "output"))
        object.__setattr__(self, "attributes", freeze_payload(self.attributes, "attributes"))
        if self.usage is not None and not isinstance(self.usage, Usage):
            raise ValidationError("usage must be a Usage instance or None")
        if self.error is not None and not isinstance(self.error, ErrorInfo):
            raise ValidationError("error must be an ErrorInfo instance or None")

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a fresh JSON-compatible representation."""

        return {
            "span_id": str(self.span_id),
            "trace_id": str(self.trace_id),
            "parent_span_id": str(self.parent_span_id) if self.parent_span_id else None,
            "span_type": self.span_type,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at is not None else None,
            "status": cast(Status, self.status).value,
            "input": thaw_payload(self.input),
            "output": thaw_payload(self.output),
            "attributes": thaw_payload(self.attributes),
            "usage": self.usage.to_dict() if self.usage is not None else None,
            "error": self.error.to_dict() if self.error is not None else None,
        }

    @classmethod
    def from_dict(cls, value: object) -> Span:
        """Reconstruct a span from a JSON-compatible object."""

        data = parse_json_object(value, "span")
        span_id = required_field(data, "span_id")
        trace_id = required_field(data, "trace_id")
        span_type = required_field(data, "span_type")
        name = required_field(data, "name")
        started_at = required_field(data, "started_at")
        if not isinstance(span_id, str) or not isinstance(trace_id, str):
            raise SerializationError("span IDs must be UUID strings")
        if not isinstance(span_type, str):
            raise SerializationError("span.span_type must be a string")
        if not isinstance(name, str):
            raise SerializationError("span.name must be a string")
        parent_span_id = optional_field(data, "parent_span_id")
        if parent_span_id is not None and not isinstance(parent_span_id, str):
            raise SerializationError("span.parent_span_id must be a UUID string or None")
        ended_at = optional_field(data, "ended_at")
        if ended_at is not None and not isinstance(ended_at, str):
            raise SerializationError("span.ended_at must be an ISO-8601 string or None")
        status = required_field(data, "status")
        if not isinstance(status, str):
            raise SerializationError("span.status must be a string")
        attributes = required_field(data, "attributes")
        if not isinstance(attributes, Mapping):
            raise SerializationError("span.attributes must be an object")
        usage_value = optional_field(data, "usage")
        error_value = optional_field(data, "error")
        usage = Usage.from_dict(usage_value) if usage_value is not None else None
        error = ErrorInfo.from_dict(error_value) if error_value is not None else None
        return cls(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            span_type=span_type,
            name=name,
            started_at=parse_datetime(started_at, "span.started_at"),
            ended_at=parse_datetime(ended_at, "span.ended_at") if ended_at is not None else None,
            status=status,
            input=cast(JSONValue | None, optional_field(data, "input")),
            output=cast(JSONValue | None, optional_field(data, "output")),
            attributes=attributes,
            usage=usage,
            error=error,
        )

    def __repr__(self) -> str:
        return f"Span(span_id={self.span_id}, span_type={self.span_type!r}, name={self.name!r})"


__all__ = ("Span",)
