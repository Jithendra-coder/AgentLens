"""Configuration for PostgreSQL-backed jobs and Redis wakeups."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationRuntimeConfig:
    redis_url: str = "redis://127.0.0.1:56379/0"
    queue_name: str = "agentlens:evaluation:v1"
    redis_connect_timeout: float = 2.0
    redis_socket_timeout: float = 2.0
    lease_seconds: float = 30.0
    heartbeat_seconds: float = 10.0
    default_timeout_seconds: float = 5.0
    default_max_attempts: int = 3
    retry_base_seconds: float = 1.0
    retry_max_seconds: float = 60.0
    worker_poll_timeout: int = 1
    recovery_batch_size: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.redis_url, str) or not self.redis_url:
            raise ValueError("redis_url must be a non-empty string")
        if not isinstance(self.queue_name, str) or not self.queue_name:
            raise ValueError("queue_name must be a non-empty string")
        for name in (
            "redis_connect_timeout",
            "redis_socket_timeout",
            "lease_seconds",
            "heartbeat_seconds",
            "default_timeout_seconds",
            "retry_base_seconds",
            "retry_max_seconds",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not isfinite(float(value)) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("heartbeat_seconds must be shorter than lease_seconds")
        if (
            not isinstance(self.default_max_attempts, int)
            or not 1 <= self.default_max_attempts <= 10
        ):
            raise ValueError("default_max_attempts must be between 1 and 10")
        if self.default_timeout_seconds > self.lease_seconds:
            raise ValueError("default_timeout_seconds must not exceed lease_seconds")
        if not isinstance(self.worker_poll_timeout, int) or not 0 <= self.worker_poll_timeout <= 60:
            raise ValueError("worker_poll_timeout must be between 0 and 60")
        if (
            not isinstance(self.recovery_batch_size, int)
            or not 1 <= self.recovery_batch_size <= 1000
        ):
            raise ValueError("recovery_batch_size must be between 1 and 1000")

    def __repr__(self) -> str:
        return (
            "EvaluationRuntimeConfig(redis_url='<redacted>', "
            f"queue_name={self.queue_name!r}, lease_seconds={self.lease_seconds!r}, "
            f"default_timeout_seconds={self.default_timeout_seconds!r})"
        )
