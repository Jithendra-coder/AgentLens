"""Production replay worker entry point: ``python -m agentlens.replay_worker``."""

from __future__ import annotations

import logging

from agentlens.config import AgentLensSettings
from agentlens.lifecycle import LifecycleCoordinator
from agentlens.logging import configure_logging
from agentlens.replay.repository import PostgresReplayRepository
from agentlens.replay.runtime import RedisReplayDispatcher, ReplayRuntimeConfig, ReplayWorker
from agentlens.replay.targets import (
    LOCAL_TARGET_PROFILE_ID,
    LocalEchoReplayTarget,
    ReplayTargetProfile,
    TrustedReplayTargetRegistry,
)
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.heartbeats import WorkerHeartbeat, WorkerHeartbeatRepository

logger = logging.getLogger("agentlens.replay_worker")


def main() -> int:
    settings = AgentLensSettings.load_from_env()
    configure_logging(
        log_level=settings.server.log_level,
        json_format=(settings.server.log_format == "json"),
    )
    logger.info("replay_worker_starting", extra={"settings": settings.to_safe_dict()})

    database = DatabaseConfig(settings.database.url)
    runtime = ReplayRuntimeConfig(
        redis_url=settings.redis.url or "redis://127.0.0.1:56379/0",
        lease_seconds=settings.worker.lease_duration_seconds,
        worker_poll_timeout=int(settings.worker.poll_interval_seconds),
    )
    registry = TrustedReplayTargetRegistry()
    registry.register(
        ReplayTargetProfile(
            profile_id=LOCAL_TARGET_PROFILE_ID,
            name="Local Echo (test only)",
            target_type="local_echo",
            version="1",
            safety_class="sandbox",
        ),
        LocalEchoReplayTarget(),
    )
    repository = PostgresReplayRepository(database)
    trace_repository = PostgresTraceRepository(database, engine=repository.engine)
    dispatcher = RedisReplayDispatcher(runtime)
    worker = ReplayWorker(
        repository=repository,
        trace_repository=trace_repository,
        dispatcher=dispatcher,
        registry=registry,
        config=runtime,
    )
    heartbeat = WorkerHeartbeat(
        WorkerHeartbeatRepository(database, engine=trace_repository.engine),
        worker_id=worker.worker_id,
        worker_type="replay",
        interval_seconds=settings.worker.heartbeat_interval_seconds,
    )

    lifecycle = LifecycleCoordinator(
        shutdown_timeout_seconds=settings.worker.shutdown_timeout_seconds
    )
    lifecycle.on_shutdown(worker.stop)
    lifecycle.on_shutdown(heartbeat.stop)
    lifecycle.on_shutdown(dispatcher.close)
    lifecycle.on_shutdown(trace_repository.dispose)
    lifecycle.install_signal_handlers()

    try:
        heartbeat.start()
        worker.run_forever()
    finally:
        lifecycle.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
