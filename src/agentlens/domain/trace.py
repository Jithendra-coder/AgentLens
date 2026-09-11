"""Canonical traces and whole-trace structural validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from agentlens.exceptions import SerializationError, UnsupportedSchemaError, ValidationError

from .event import Event
from .span import Span
from .types import (
    TRACE_SCHEMA_VERSION,
    JSONValue,
    Status,
    check_schema_version,
    dumps_json,
    freeze_payload,
    loads_json,
    normalize_datetime,
    normalize_status,
    normalize_uuid,
    optional_field,
    parse_datetime,
    parse_json_object,
    required_field,
    thaw_payload,
    utc_now,
)


@dataclass(frozen=True, slots=True)
class Trace:
    """One logical observed execution with spans and point-in-time events."""

    schema_version: str = TRACE_SCHEMA_VERSION
    trace_id: UUID | str = field(default_factory=uuid4)
    project_id: str = ""
    session_id: str | None = None
    name: str = ""
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    status: Status | str = Status.UNSET
    spans: Sequence[Span] = field(default_factory=tuple)
    events: Sequence[Event] = field(default_factory=tuple)
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != TRACE_SCHEMA_VERSION:
            raise UnsupportedSchemaError(f"unsupported trace schema: {self.schema_version}")
        object.__setattr__(self, "trace_id", normalize_uuid(self.trace_id, "trace_id"))
        if not isinstance(self.project_id, str):
            raise ValidationError("project_id must be a string")
        if self.session_id is not None and not isinstance(self.session_id, str):
            raise ValidationError("session_id must be a string or None")
        if not isinstance(self.name, str):
            raise ValidationError("name must be a string")
        object.__setattr__(self, "started_at", normalize_datetime(self.started_at, "started_at"))
        if self.ended_at is not None:
            ended_at = normalize_datetime(self.ended_at, "ended_at")
            if ended_at < self.started_at:
                raise ValidationError("ended_at must be greater than or equal to started_at")
            object.__setattr__(self, "ended_at", ended_at)
        object.__setattr__(self, "status", normalize_status(self.status))
        try:
            spans = tuple(self.spans)
            events = tuple(self.events)
        except TypeError as exc:
            raise ValidationError("spans and events must be iterable") from exc
        if any(not isinstance(span, Span) for span in spans):
            raise ValidationError("spans must contain only Span instances")
        if any(not isinstance(event, Event) for event in events):
            raise ValidationError("events must contain only Event instances")
        object.__setattr__(self, "spans", spans)
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "attributes", freeze_payload(self.attributes, "attributes"))
        self.validate()

    def validate(self) -> None:
        """Validate IDs, references, graph structure, and temporal invariants."""

        trace_id = cast(UUID, self.trace_id)
        spans_by_id: dict[UUID, Span] = {}
        for span in self.spans:
            span_trace_id = cast(UUID, span.trace_id)
            span_id = cast(UUID, span.span_id)
            if span_trace_id != trace_id:
                raise ValidationError("every span must belong to the containing trace")
            if span_id in spans_by_id:
                raise ValidationError(f"duplicate span_id: {span_id}")
            spans_by_id[span_id] = span

        events_by_id: dict[UUID, Event] = {}
        for event in self.events:
            event_trace_id = cast(UUID, event.trace_id)
            event_id = cast(UUID, event.event_id)
            event_span_id = cast(UUID | None, event.span_id)
            if event_trace_id != trace_id:
                raise ValidationError("every event must belong to the containing trace")
            if event_id in events_by_id:
                raise ValidationError(f"duplicate event_id: {event_id}")
            events_by_id[event_id] = event
            if event_span_id is not None and event_span_id not in spans_by_id:
                raise ValidationError(f"event references unknown span_id: {event_span_id}")

        parents: dict[UUID, UUID | None] = {}
        for span in self.spans:
            span_id = cast(UUID, span.span_id)
            parent_id = cast(UUID | None, span.parent_span_id)
            if parent_id == span_id:
                raise ValidationError(f"span cannot parent itself: {span_id}")
            if parent_id is not None and parent_id not in spans_by_id:
                raise ValidationError(f"span references unknown parent_span_id: {parent_id}")
            parents[span_id] = parent_id

        processed: set[UUID] = set()
        for span_id in parents:
            current: UUID | None = span_id
            path: set[UUID] = set()
            while current is not None and current not in processed:
                if current in path:
                    raise ValidationError("span parent cycle detected")
                path.add(current)
                current = parents[current]
            processed.update(path)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a fresh deterministic JSON-compatible representation."""

        return {
            "schema_version": self.schema_version,
            "trace_id": str(self.trace_id),
            "project_id": self.project_id,
            "session_id": self.session_id,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at is not None else None,
            "status": cast(Status, self.status).value,
            "spans": [span.to_dict() for span in self.spans],
            "events": [event.to_dict() for event in self.events],
            "attributes": thaw_payload(self.attributes),
        }

    def to_json(self) -> str:
        """Serialize this trace as deterministic JSON text."""

        return dumps_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> Trace:
        """Reconstruct and validate a trace from a JSON-compatible object."""

        data = parse_json_object(value, "trace")
        schema_version = check_schema_version(required_field(data, "schema_version"))
        trace_id = required_field(data, "trace_id")
        project_id = required_field(data, "project_id")
        name = required_field(data, "name")
        started_at = required_field(data, "started_at")
        if not isinstance(trace_id, str):
            raise SerializationError("trace_id must be a UUID string")
        if not isinstance(project_id, str):
            raise SerializationError("project_id must be a string")
        if not isinstance(name, str):
            raise SerializationError("trace.name must be a string")
        session_id = optional_field(data, "session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise SerializationError("session_id must be a string or None")
        ended_at = optional_field(data, "ended_at")
        if ended_at is not None and not isinstance(ended_at, str):
            raise SerializationError("trace.ended_at must be an ISO-8601 string or None")
        status = required_field(data, "status")
        if not isinstance(status, str):
            raise SerializationError("trace.status must be a string")
        spans_value = required_field(data, "spans")
        events_value = required_field(data, "events")
        if not isinstance(spans_value, list) or not isinstance(events_value, list):
            raise SerializationError("trace.spans and trace.events must be arrays")
        attributes = required_field(data, "attributes")
        if not isinstance(attributes, Mapping):
            raise SerializationError("trace.attributes must be an object")
        return cls(
            schema_version=schema_version,
            trace_id=trace_id,
            project_id=project_id,
            session_id=session_id,
            name=name,
            started_at=parse_datetime(started_at, "trace.started_at"),
            ended_at=parse_datetime(ended_at, "trace.ended_at") if ended_at is not None else None,
            status=status,
            spans=tuple(Span.from_dict(item) for item in spans_value),
            events=tuple(Event.from_dict(item) for item in events_value),
            attributes=attributes,
        )

    @classmethod
    def from_json(cls, value: str) -> Trace:
        """Deserialize and validate deterministic JSON text."""

        return cls.from_dict(loads_json(value))

    def __repr__(self) -> str:
        return (
            f"Trace(trace_id={self.trace_id}, name={self.name!r}, "
            f"spans={len(self.spans)}, events={len(self.events)})"
        )


__all__ = ("Trace",)
