"""Stable transport error types and safe response translation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GatewayError(Exception):
    code: str
    message: str
    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


def error_response_body(error: GatewayError, request_id: str) -> dict[str, object]:
    """Build the small non-sensitive error contract."""

    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "request_id": request_id,
        }
    }
