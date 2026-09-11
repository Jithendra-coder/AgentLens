"""Production regression worker entry point: ``python -m agentlens.regression_worker``."""

from __future__ import annotations

import logging

from agentlens.config import AgentLensSettings
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.handlers import HandlerRegistry
from agentlens.evaluation.redis import RedisDispatcher
from agentlens.evaluation.repository import PostgresEvaluationJobRepository
from agentlens.evaluation.result_repository import PostgresEvaluationResultRepository
from agentlens.lifecycle import LifecycleCoordinator
from agentlens.logging import configure_logging
from agentlens.regression.repository import PostgresRegressionRepository
from agentlens.regression.runtime import (
    RedisRegressionDispatcher,
    RegressionRuntimeConfig,
    RegressionWorker,
)
from agentlens.storage import DatabaseConfig
from agentlens.storage.heartbeats import WorkerHeartbeat, WorkerHeartbeatRepository

logger = logging.getLogger("agentlens.regression_worker")


def main() -> int:
    settings = AgentLensSettings.load_from_env()
    configure_logging(
        log_level=settings.server.log_level,
        json_format=(settings.server.log_format == "json"),
    )
    logger.info("regression_worker_starting", extra={"settings": settings.to_safe_dict()})

    database = DatabaseConfig(settings.database.url)
    redis_url = settings.redis.url or "redis://127.0.0.1:56379/0"
    evaluation_config = EvaluationRuntimeConfig(
        redis_url=redis_url,
        lease_seconds=settings.worker.lease_duration_seconds,
        worker_poll_timeout=int(settings.worker.poll_interval_seconds),
    )
    regression_config = RegressionRuntimeConfig(
        redis_url=redis_url,
        lease_seconds=settings.worker.lease_duration_seconds,
        worker_poll_timeout=int(settings.worker.poll_interval_seconds),
    )
    regression_repository = PostgresRegressionRepository(database)
    evaluation_job_repository = PostgresEvaluationJobRepository(
        database, engine=regression_repository.engine
    )
    evaluation_result_repository = PostgresEvaluationResultRepository(
        database, engine=regression_repository.engine
    )
    evaluation_dispatcher = RedisDispatcher(evaluation_config)
    regression_dispatcher = RedisRegressionDispatcher(regression_config)
    worker = RegressionWorker(
        repository=regression_repository,
        evaluation_job_repository=evaluation_job_repository,
        evaluation_result_repository=evaluation_result_repository,
        evaluation_dispatcher=evaluation_dispatcher,
        dispatcher=regression_dispatcher,
        handler_registry=HandlerRegistry(),
        evaluation_config=evaluation_config,
        config=regression_config,
    )
    heartbeat = WorkerHeartbeat(
        WorkerHeartbeatRepository(database, engine=regression_repository.engine),
        worker_id=worker.worker_id,
        worker_type="regression",
        interval_seconds=settings.worker.heartbeat_interval_seconds,
    )

    lifecycle = LifecycleCoordinator(
        shutdown_timeout_seconds=settings.worker.shutdown_timeout_seconds
    )
    lifecycle.on_shutdown(worker.stop)
    lifecycle.on_shutdown(heartbeat.stop)
    lifecycle.on_shutdown(regression_dispatcher.close)
    lifecycle.on_shutdown(evaluation_dispatcher.close)
    lifecycle.on_shutdown(regression_repository.dispose)
    lifecycle.install_signal_handlers()

    try:
        heartbeat.start()
        worker.run_forever()
    finally:
        lifecycle.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
