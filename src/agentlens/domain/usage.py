"""Provider-neutral token usage metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from agentlens.exceptions import SerializationError, ValidationError

from .types import JSONValue, freeze_payload, optional_field, parse_json_object, thaw_payload


@dataclass(frozen=True, slots=True)
class Usage:
    """Observed token counts without provider-specific assumptions."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    attributes: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_tokens",
            "reasoning_tokens",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValidationError(f"{field_name} must be a non-negative integer")
        object.__setattr__(self, "attributes", freeze_payload(self.attributes, "attributes"))

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a fresh JSON-compatible representation."""

        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "attributes": thaw_payload(self.attributes),
        }

    @classmethod
    def from_dict(cls, value: object) -> Usage:
        """Reconstruct usage metadata from a JSON object."""

        data = parse_json_object(value, "usage")
        token_values: dict[str, int | None] = {}
        for field_name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_tokens",
            "reasoning_tokens",
        ):
            raw = optional_field(data, field_name)
            if raw is not None and (isinstance(raw, bool) or not isinstance(raw, int) or raw < 0):
                raise SerializationError(f"usage.{field_name} must be a non-negative integer")
            token_values[field_name] = raw
        attributes = optional_field(data, "attributes", {})
        if not isinstance(attributes, Mapping):
            raise SerializationError("usage.attributes must be an object")
        return cls(attributes=attributes, **token_values)

    def __repr__(self) -> str:
        return (
            "Usage("
            f"input_tokens={self.input_tokens}, output_tokens={self.output_tokens}, "
            f"total_tokens={self.total_tokens})"
        )


__all__ = ("Usage",)
