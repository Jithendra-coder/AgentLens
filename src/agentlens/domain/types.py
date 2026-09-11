"""Shared canonical types and validation helpers for the canonical domain model."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TypeAlias, cast
from uuid import UUID

from agentlens.exceptions import (
    SerializationError,
    UnsupportedSchemaError,
    ValidationError,
)

TRACE_SCHEMA_VERSION = "agentlens-trace-v1"

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
FrozenJSONValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | tuple["FrozenJSONValue", ...]
    | Mapping[str, "FrozenJSONValue"]
)


class Status(StrEnum):
    """Minimal observed execution status vocabulary."""

    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class SpanType(StrEnum):
    """Common span types; arbitrary non-empty strings remain supported."""

    AGENT = "agent"
    LLM = "llm"
    RETRIEVAL = "retrieval"
    EMBEDDING = "embedding"
    TOOL = "tool"
    MCP = "mcp"
    HTTP = "http"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


def utc_now() -> datetime:
    """Return an aware UTC timestamp for convenient domain defaults."""

    return datetime.now(UTC)


def normalize_uuid(value: UUID | str, field_name: str) -> UUID:
    """Normalize a UUID object or UUID string, rejecting malformed input."""

    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a UUID or UUID string")
    try:
        return UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationError(f"{field_name} must be a valid UUID") from exc


def normalize_optional_uuid(value: UUID | str | None, field_name: str) -> UUID | None:
    """Normalize an optional UUID value."""

    if value is None:
        return None
    return normalize_uuid(value, field_name)


def normalize_datetime(value: datetime, field_name: str) -> datetime:
    """Normalize an aware datetime to UTC and reject naive values."""

    if not isinstance(value, datetime):
        raise ValidationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def parse_datetime(value: object, field_name: str) -> datetime:
    """Parse an ISO-8601 timestamp and normalize it to UTC."""

    if not isinstance(value, str):
        raise SerializationError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SerializationError(f"{field_name} must be a valid ISO-8601 timestamp") from exc
    try:
        return normalize_datetime(parsed, field_name)
    except ValidationError as exc:
        raise SerializationError(str(exc)) from exc


def normalize_status(value: Status | str, field_name: str = "status") -> Status:
    """Normalize a status and reject values outside the canonical vocabulary."""

    if isinstance(value, Status):
        return value
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a valid status")
    try:
        return Status(value)
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be one of: unset, ok, error") from exc


def normalize_span_type(value: SpanType | str, field_name: str = "span_type") -> str:
    """Normalize known span types while allowing future custom type strings."""

    normalized = value.value if isinstance(value, SpanType) else value
    if not isinstance(normalized, str) or not normalized.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return normalized.strip()


def validate_json_value(value: object, path: str = "value") -> None:
    """Validate a strict JSON-safe value without coercing unsupported objects."""

    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(f"{path} must contain only finite numbers")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationError(f"{path} must use string mapping keys")
            validate_json_value(item, f"{path}.{key}")
        return
    raise ValidationError(f"{path} contains an unsupported JSON value")


def freeze_json(value: object, path: str = "value") -> FrozenJSONValue:
    """Copy a JSON-safe value into recursively immutable containers."""

    validate_json_value(value, path)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return tuple(freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value))
    if isinstance(value, Mapping):
        frozen = {key: freeze_json(item, f"{path}.{key}") for key, item in value.items()}
        return cast(FrozenJSONValue, MappingProxyType(frozen))
    raise ValidationError(f"{path} contains an unsupported JSON value")


def thaw_json(value: FrozenJSONValue) -> JSONValue:
    """Return a fresh ordinary JSON-compatible copy of frozen data."""

    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def freeze_payload(value: object, path: str) -> FrozenJSONValue:
    """Validate and freeze a nullable payload or attribute mapping."""

    return freeze_json(value, path)


def thaw_payload(value: object) -> JSONValue:
    """Thaw an internally frozen payload for a caller-owned result."""

    return thaw_json(cast(FrozenJSONValue, value))


def require_mapping(value: object, field_name: str = "payload") -> Mapping[str, object]:
    """Require a JSON object-like mapping for deserialization."""

    if not isinstance(value, Mapping):
        raise SerializationError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise SerializationError(f"{field_name} must use string keys")
    return cast(Mapping[str, object], value)


def required_field(data: Mapping[str, object], field_name: str) -> object:
    """Read a required field with a stable serialization error."""

    if field_name not in data:
        raise SerializationError(f"missing required field: {field_name}")
    return data[field_name]


def optional_field(data: Mapping[str, object], field_name: str, default: object = None) -> object:
    """Read an optional field without changing its value."""

    return data[field_name] if field_name in data else default


def parse_json_object(value: object, field_name: str) -> Mapping[str, object]:
    """Parse an object field while retaining JSON-safe validation."""

    mapping = require_mapping(value, field_name)
    try:
        validate_json_value(dict(mapping), field_name)
    except ValidationError as exc:
        raise SerializationError(str(exc)) from exc
    return mapping


def dumps_json(value: object) -> str:
    """Encode canonical JSON and translate unexpected encoder failures."""

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SerializationError("canonical data could not be encoded as JSON") from exc


def loads_json(value: str) -> object:
    """Decode JSON text and expose malformed input as a domain error."""

    if not isinstance(value, str):
        raise SerializationError("JSON input must be a string")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise SerializationError("invalid JSON") from exc


def check_schema_version(value: object) -> str:
    """Require the one schema version supported."""

    if not isinstance(value, str):
        raise SerializationError("schema_version must be a string")
    if value != TRACE_SCHEMA_VERSION:
        raise UnsupportedSchemaError(f"unsupported trace schema: {value}")
    return value


__all__ = (
    "FrozenJSONValue",
    "JSONValue",
    "SPAN_TYPES",
    "Status",
    "SpanType",
    "TRACE_SCHEMA_VERSION",
    "check_schema_version",
    "dumps_json",
    "freeze_payload",
    "loads_json",
    "normalize_datetime",
    "normalize_optional_uuid",
    "normalize_span_type",
    "normalize_status",
    "normalize_uuid",
    "optional_field",
    "parse_datetime",
    "parse_json_object",
    "required_field",
    "thaw_payload",
    "utc_now",
    "validate_json_value",
)


SPAN_TYPES = frozenset(item.value for item in SpanType)
