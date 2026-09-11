"""Redis wakeup transport; PostgreSQL remains the durable source of truth."""

from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

import redis

from .config import EvaluationRuntimeConfig
from .errors import RedisUnavailableError


class EvaluationDispatcher(Protocol):
    def dispatch(self, job_id: UUID) -> None: ...

    def receive(self, timeout: int) -> UUID | None: ...

    def check_ready(self) -> bool: ...

    def close(self) -> None: ...


class UnavailableDispatcher:
    """Used when the gateway has no Redis configuration; jobs stay durable and queued."""

    def dispatch(self, job_id: UUID) -> None:
        del job_id
        raise RedisUnavailableError("evaluation dispatch is unavailable")

    def receive(self, timeout: int) -> UUID | None:
        del timeout
        raise RedisUnavailableError("evaluation dispatch is unavailable")

    def check_ready(self) -> bool:
        return False

    def close(self) -> None:
        return None


class RedisDispatcher:
    """Versioned Redis list carrying only a UUID wakeup payload."""

    def __init__(self, config: EvaluationRuntimeConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._client = client or redis.Redis.from_url(
            config.redis_url,
            socket_connect_timeout=config.redis_connect_timeout,
            socket_timeout=config.redis_socket_timeout,
            health_check_interval=30,
            decode_responses=True,
        )

    def dispatch(self, job_id: UUID) -> None:
        payload = json.dumps({"job_id": str(job_id)}, separators=(",", ":"))
        try:
            self._client.rpush(self.config.queue_name, payload)
        except redis.RedisError as exc:
            raise RedisUnavailableError("evaluation dispatch is unavailable") from exc

    def receive(self, timeout: int) -> UUID | None:
        try:
            item = (
                self._client.lpop(self.config.queue_name)
                if timeout <= 0
                else self._client.blpop([self.config.queue_name], timeout=timeout)
            )
        except redis.RedisError as exc:
            raise RedisUnavailableError("evaluation dispatch is unavailable") from exc
        if item is None:
            return None
        payload = item[1] if isinstance(item, (tuple, list)) and len(item) == 2 else item
        try:
            decoded = json.loads(str(payload))
            if not isinstance(decoded, dict):
                return None
            return UUID(str(decoded["job_id"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def check_ready(self) -> bool:
        try:
            return bool(self._client.ping())
        except redis.RedisError:
            return False

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def __repr__(self) -> str:
        return f"RedisDispatcher(queue_name={self.config.queue_name!r}, redis_url='<redacted>')"


class RecoveryDispatcher:
    """Re-publishes durable queued, retry-ready, and expired jobs after outages."""

    def __init__(self, repository: Any, dispatcher: EvaluationDispatcher) -> None:
        self.repository = repository
        self.dispatcher = dispatcher

    def dispatch_ready(self, *, now: Any, limit: int) -> int:
        count = 0
        for job_id in self.repository.dispatchable_job_ids(now=now, limit=limit):
            self.dispatcher.dispatch(job_id)
            count += 1
        return count


__all__ = [
    "EvaluationDispatcher",
    "RedisDispatcher",
    "RecoveryDispatcher",
    "UnavailableDispatcher",
]
