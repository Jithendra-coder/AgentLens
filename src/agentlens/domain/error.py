"""Structured observed error metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from agentlens.exceptions import SerializationError, ValidationError

from .types import JSONValue, freeze_payload, optional_field, parse_json_object, thaw_payload


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    """Observed failure information, distinct from derived evaluation findings."""

    error_type: str
    message: str
    code: str | None = None
    traceback: str | None = None
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.error_type, str):
            raise ValidationError("error_type must be a string")
        if not isinstance(self.message, str):
            raise ValidationError("message must be a string")
        for field_name in ("code", "traceback"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise ValidationError(f"{field_name} must be a string or None")
        object.__setattr__(self, "attributes", freeze_payload(self.attributes, "attributes"))

    @property
    def stack(self) -> str | None:
        """Compatibility alias for callers that call a traceback a stack."""

        return self.traceback

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a fresh JSON-compatible representation."""

        return {
            "error_type": self.error_type,
            "message": self.message,
            "code": self.code,
            "traceback": self.traceback,
            "attributes": thaw_payload(self.attributes),
        }

    @classmethod
    def from_dict(cls, value: object) -> ErrorInfo:
        """Reconstruct observed error metadata from a JSON object."""

        data = parse_json_object(value, "error")
        error_type = data.get("error_type")
        message = data.get("message")
        if not isinstance(error_type, str) or not isinstance(message, str):
            raise SerializationError("error requires string error_type and message")
        code = optional_field(data, "code")
        traceback = optional_field(data, "traceback")
        if code is not None and not isinstance(code, str):
            raise SerializationError("error.code must be a string or None")
        if traceback is not None and not isinstance(traceback, str):
            raise SerializationError("error.traceback must be a string or None")
        attributes = optional_field(data, "attributes", {})
        if not isinstance(attributes, Mapping):
            raise SerializationError("error.attributes must be an object")
        return cls(
            error_type=error_type,
            message=message,
            code=code,
            traceback=traceback,
            attributes=attributes,
        )

    def __repr__(self) -> str:
        return f"ErrorInfo(error_type={self.error_type!r}, code={self.code!r})"


__all__ = ("ErrorInfo",)
