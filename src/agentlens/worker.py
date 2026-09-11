"""Production evaluation worker entry point: ``python -m agentlens.worker``."""

from __future__ import annotations

import logging

from agentlens.config import AgentLensSettings
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.handlers import HandlerRegistry
from agentlens.evaluation.redis import RedisDispatcher
from agentlens.evaluation.repository import PostgresEvaluationJobRepository
from agentlens.evaluation.result_repository import PostgresEvaluationResultRepository
from agentlens.evaluation.worker import EvaluationWorker
from agentlens.lifecycle import LifecycleCoordinator
from agentlens.logging import configure_logging
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.heartbeats import WorkerHeartbeat, WorkerHeartbeatRepository
from agentlens.storage.repository import PostgresTraceRepository

logger = logging.getLogger("agentlens.worker")


def main() -> int:
    settings = AgentLensSettings.load_from_env()
    configure_logging(
        log_level=settings.server.log_level,
        json_format=(settings.server.log_format == "json"),
    )
    logger.info("evaluation_worker_starting", extra={"settings": settings.to_safe_dict()})

    runtime = EvaluationRuntimeConfig(
        redis_url=settings.redis.url or "redis://127.0.0.1:56379/0",
        lease_seconds=settings.worker.lease_duration_seconds,
        worker_poll_timeout=int(settings.worker.poll_interval_seconds),
    )
    database = DatabaseConfig(settings.database.url)
    trace_repository = PostgresTraceRepository(database)
    job_repository = PostgresEvaluationJobRepository(database, engine=trace_repository.engine)
    result_repository = PostgresEvaluationResultRepository(database, engine=trace_repository.engine)
    dispatcher = RedisDispatcher(runtime)
    worker = EvaluationWorker(
        repository=job_repository,
        trace_repository=trace_repository,
        dispatcher=dispatcher,
        result_repository=result_repository,
        registry=HandlerRegistry(),
        config=runtime,
    )
    heartbeat = WorkerHeartbeat(
        WorkerHeartbeatRepository(database, engine=trace_repository.engine),
        worker_id=worker.worker_id,
        worker_type="evaluation",
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
