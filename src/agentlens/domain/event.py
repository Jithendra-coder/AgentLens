"""Canonical point-in-time execution events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from agentlens.exceptions import SerializationError, ValidationError

from .types import (
    JSONValue,
    freeze_payload,
    normalize_datetime,
    normalize_optional_uuid,
    normalize_uuid,
    optional_field,
    parse_datetime,
    parse_json_object,
    required_field,
    thaw_payload,
    utc_now,
)


@dataclass(frozen=True, slots=True)
class Event:
    """A point-in-time occurrence attached to a trace or span."""

    event_id: UUID | str = field(default_factory=uuid4)
    trace_id: UUID | str = field(default_factory=uuid4)
    name: str = ""
    timestamp: datetime = field(default_factory=utc_now)
    span_id: UUID | str | None = None
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", normalize_uuid(self.event_id, "event_id"))
        object.__setattr__(self, "trace_id", normalize_uuid(self.trace_id, "trace_id"))
        object.__setattr__(
            self,
            "span_id",
            normalize_optional_uuid(self.span_id, "span_id"),
        )
        if not isinstance(self.name, str):
            raise ValidationError("name must be a string")
        object.__setattr__(self, "timestamp", normalize_datetime(self.timestamp, "timestamp"))
        object.__setattr__(self, "attributes", freeze_payload(self.attributes, "attributes"))

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a fresh JSON-compatible representation."""

        return {
            "event_id": str(self.event_id),
            "trace_id": str(self.trace_id),
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "span_id": str(self.span_id) if self.span_id is not None else None,
            "attributes": thaw_payload(self.attributes),
        }

    @classmethod
    def from_dict(cls, value: object) -> Event:
        """Reconstruct an event from a JSON-compatible object."""

        data = parse_json_object(value, "event")
        event_id = required_field(data, "event_id")
        trace_id = required_field(data, "trace_id")
        name = required_field(data, "name")
        timestamp = required_field(data, "timestamp")
        if not isinstance(event_id, str) or not isinstance(trace_id, str):
            raise SerializationError("event IDs must be UUID strings")
        if not isinstance(name, str):
            raise SerializationError("event.name must be a string")
        span_id = optional_field(data, "span_id")
        if span_id is not None and not isinstance(span_id, str):
            raise SerializationError("event.span_id must be a UUID string or None")
        attributes = required_field(data, "attributes")
        if not isinstance(attributes, Mapping):
            raise SerializationError("event.attributes must be an object")
        return cls(
            event_id=event_id,
            trace_id=trace_id,
            name=name,
            timestamp=parse_datetime(timestamp, "event.timestamp"),
            span_id=span_id,
            attributes=attributes,
        )

    def __repr__(self) -> str:
        return f"Event(event_id={self.event_id}, name={self.name!r})"


__all__ = ("Event",)
