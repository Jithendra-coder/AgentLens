"""M12 shared coordination and durable operational worker evidence."""

from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest

from agentlens.api.rate_limit import RedisRateLimiter
from agentlens.storage import DatabaseConfig
from agentlens.storage.heartbeats import WorkerHeartbeat, WorkerHeartbeatRepository

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL,
    reason="runtime tests require PostgreSQL and Redis",
)


def test_two_instances_share_the_atomic_rate_window() -> None:
    assert REDIS_URL is not None
    first = RedisRateLimiter(redis_url=REDIS_URL, max_requests=3, window_seconds=60)
    second = RedisRateLimiter(redis_url=REDIS_URL, max_requests=3, window_seconds=60)
    key_id = f"m12-test-{uuid4()}"
    decisions = [
        first.allow(key_id).allowed,
        second.allow(key_id).allowed,
        first.allow(key_id).allowed,
        second.allow(key_id).allowed,
    ]
    assert decisions == [True, True, True, False]
    assert first.health == second.health == "shared"


def test_worker_heartbeat_touches_and_marks_stopped() -> None:
    assert DATABASE_URL is not None
    config = DatabaseConfig(DATABASE_URL)
    repository = WorkerHeartbeatRepository(config)
    worker_id = f"m12-test-worker-{uuid4()}"
    heartbeat = WorkerHeartbeat(
        repository,
        worker_id=worker_id,
        worker_type="evaluation",
        interval_seconds=1,
    )
    try:
        heartbeat.start()
        time.sleep(1.2)
        running = [row for row in repository.list() if row["worker_id"] == worker_id]
        assert running and running[0]["state"] == "running"
        assert running[0]["health"] == "healthy"
    finally:
        heartbeat.stop()
    stopped = [row for row in repository.list() if row["worker_id"] == worker_id]
    assert stopped and stopped[0]["state"] == "stopped"
