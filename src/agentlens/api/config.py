"""Validated configuration for the process-local gateway."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Small explicit gateway configuration with bounded safety defaults."""

    max_request_bytes: int = 2 * 1024 * 1024
    max_batch_size: int = 100
    rate_limit: int = 100
    rate_window_seconds: float = 60.0
    query_default_limit: int = 50
    query_max_limit: int = 200
    environment: str = "development"

    def __post_init__(self) -> None:
        if not isinstance(self.max_request_bytes, int) or isinstance(self.max_request_bytes, bool):
            raise ValueError("max_request_bytes must be a positive integer")
        if self.max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be a positive integer")
        if not isinstance(self.max_batch_size, int) or isinstance(self.max_batch_size, bool):
            raise ValueError("max_batch_size must be a positive integer")
        if self.max_batch_size <= 0:
            raise ValueError("max_batch_size must be a positive integer")
        if not isinstance(self.rate_limit, int) or isinstance(self.rate_limit, bool):
            raise ValueError("rate_limit must be a positive integer")
        if self.rate_limit <= 0:
            raise ValueError("rate_limit must be a positive integer")
        for name in ("query_default_limit", "query_max_limit"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.query_default_limit > self.query_max_limit:
            raise ValueError("query_default_limit cannot exceed query_max_limit")
        if not isinstance(self.rate_window_seconds, (int, float)) or isinstance(
            self.rate_window_seconds, bool
        ):
            raise ValueError("rate_window_seconds must be positive")
        if not math.isfinite(self.rate_window_seconds) or self.rate_window_seconds <= 0:
            raise ValueError("rate_window_seconds must be positive")
        if not isinstance(self.environment, str) or not self.environment.strip():
            raise ValueError("environment must be a non-empty string")
