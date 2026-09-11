"""Deterministic process-local fixed-window rate limiting."""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import redis


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int | None = None


class InMemoryRateLimiter:
    """Per-key fixed-window limiter; replicas do not share this state."""

    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(max_requests, int) or isinstance(max_requests, bool) or max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if (
            not isinstance(window_seconds, (int, float))
            or isinstance(window_seconds, bool)
            or not math.isfinite(window_seconds)
            or window_seconds <= 0
        ):
            raise ValueError("window_seconds must be positive")
        self.max_requests = max_requests
        self.window_seconds = float(window_seconds)
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.RLock()

    def allow(self, key_id: str) -> RateLimitDecision:
        """Consume one request for a key and return a deterministic decision."""

        now = float(self._clock())
        with self._lock:
            window_start, count = self._windows.get(key_id, (now, 0))
            if now - window_start >= self.window_seconds:
                window_start, count = now, 0
            if count >= self.max_requests:
                remaining = max(0.0, self.window_seconds - (now - window_start))
                return RateLimitDecision(False, max(1, int(remaining + 0.999)))
            self._windows[key_id] = (window_start, count + 1)
            return RateLimitDecision(True)

    @property
    def health(self) -> str:
        return "local"


class RedisRateLimiter:
    """Shared fixed-window limiter with a bounded local fallback.

    The Redis key contains only a one-way key-id digest.  ``INCR`` and the
    first-request ``EXPIRE`` are one Lua operation, so separate API instances
    cannot admit more than the configured window budget between them.
    """

    _SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return {count, redis.call('TTL', KEYS[1])}
    """

    def __init__(
        self,
        *,
        redis_url: str,
        max_requests: int,
        window_seconds: float,
        connect_timeout: float = 0.25,
        socket_timeout: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = float(window_seconds)
        self._fallback = InMemoryRateLimiter(
            max_requests=max_requests, window_seconds=window_seconds, clock=clock
        )
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=connect_timeout,
            socket_timeout=socket_timeout,
            health_check_interval=30,
        )
        self._script = self._client.register_script(self._SCRIPT)
        self._state = "degraded"
        self._state_lock = threading.Lock()

    @property
    def health(self) -> str:
        with self._state_lock:
            return self._state

    def check_ready(self) -> bool:
        try:
            self._client.ping()
        except Exception:
            self._set_state("degraded")
            return False
        self._set_state("shared")
        return True

    def allow(self, key_id: str) -> RateLimitDecision:
        digest = hashlib.sha256(key_id.encode("utf-8")).hexdigest()
        key = f"agentlens:ratelimit:{digest}"
        try:
            raw = self._script(
                keys=[key],
                args=[max(1, math.ceil(self.window_seconds))],
            )
            count, ttl = (int(value) for value in raw)
            self._set_state("shared")
            if count > self.max_requests:
                return RateLimitDecision(False, max(1, ttl))
            return RateLimitDecision(True)
        except Exception:
            self._set_state("degraded")
            return self._fallback.allow(key_id)

    def _set_state(self, value: str) -> None:
        with self._state_lock:
            self._state = value
