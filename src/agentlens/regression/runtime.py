"""Redis wakeups and a durable M10 comparison worker."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import redis

from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.errors import JobIdempotencyConflict, RedisUnavailableError
from agentlens.evaluation.handlers import HandlerRegistry
from agentlens.evaluation.redis import EvaluationDispatcher
from agentlens.evaluation.repository import (
    PostgresEvaluationJobRepository,
)
from agentlens.evaluation.repository import (
    request_fingerprint as evaluation_request_fingerprint,
)
from agentlens.evaluation.result_repository import PostgresEvaluationResultRepository

from .models import RegressionPolicy
from .repository import (
    PostgresRegressionRepository,
    build_comparison_result,
)


class RegressionRedisUnavailable(Exception):
    """Redis is a wakeup transport; PostgreSQL remains authoritative."""


@dataclass(frozen=True, slots=True, repr=False)
class RegressionRuntimeConfig:
    redis_url: str = "redis://127.0.0.1:56379/0"
    queue_name: str = "agentlens:regression:v1"
    redis_connect_timeout: float = 2.0
    redis_socket_timeout: float = 2.0
    lease_seconds: float = 30.0
    heartbeat_seconds: float = 10.0
    default_timeout_seconds: float = 5.0
    default_max_attempts: int = 3
    worker_poll_timeout: int = 1
    recovery_batch_size: int = 100

    def __post_init__(self) -> None:
        if not self.redis_url or not self.queue_name:
            raise ValueError("redis_url and queue_name are required")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("heartbeat_seconds must be shorter than lease_seconds")

    def __repr__(self) -> str:
        return f"RegressionRuntimeConfig(redis_url='<redacted>', queue_name={self.queue_name!r})"


class RegressionDispatcher(Protocol):
    def dispatch(self, regression_run_id: UUID) -> None: ...

    def receive(self, timeout: int) -> UUID | None: ...

    def check_ready(self) -> bool: ...

    def close(self) -> None: ...


class UnavailableRegressionDispatcher:
    def dispatch(self, regression_run_id: UUID) -> None:
        del regression_run_id
        raise RegressionRedisUnavailable("regression dispatch is unavailable")

    def receive(self, timeout: int) -> UUID | None:
        del timeout
        raise RegressionRedisUnavailable("regression dispatch is unavailable")

    def check_ready(self) -> bool:
        return False

    def close(self) -> None:
        return None


class RedisRegressionDispatcher:
    def __init__(self, config: RegressionRuntimeConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._client = client or redis.Redis.from_url(
            config.redis_url,
            socket_connect_timeout=config.redis_connect_timeout,
            socket_timeout=config.redis_socket_timeout,
            health_check_interval=30,
            decode_responses=True,
        )

    def dispatch(self, regression_run_id: UUID) -> None:
        try:
            self._client.rpush(
                self.config.queue_name,
                json.dumps({"regression_run_id": str(regression_run_id)}, separators=(",", ":")),
            )
        except redis.RedisError as exc:
            raise RegressionRedisUnavailable("regression dispatch is unavailable") from exc

    def receive(self, timeout: int) -> UUID | None:
        try:
            item = (
                self._client.lpop(self.config.queue_name)
                if timeout <= 0
                else self._client.blpop([self.config.queue_name], timeout=timeout)
            )
        except redis.RedisError as exc:
            raise RegressionRedisUnavailable("regression dispatch is unavailable") from exc
        if item is None:
            return None
        payload = item[1] if isinstance(item, (tuple, list)) and len(item) == 2 else item
        try:
            body = json.loads(str(payload))
            return UUID(str(body["regression_run_id"])) if isinstance(body, dict) else None
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


class RegressionRecoveryDispatcher:
    def __init__(
        self, repository: PostgresRegressionRepository, dispatcher: RegressionDispatcher
    ) -> None:
        self.repository = repository
        self.dispatcher = dispatcher

    def dispatch_ready(self, *, now: datetime, limit: int) -> int:
        count = 0
        for run_id in self.repository.dispatchable_run_ids(now=now, limit=limit):
            self.dispatcher.dispatch(run_id)
            count += 1
        return count


class RegressionWorker:
    def __init__(
        self,
        *,
        repository: PostgresRegressionRepository,
        evaluation_job_repository: PostgresEvaluationJobRepository,
        evaluation_result_repository: PostgresEvaluationResultRepository,
        evaluation_dispatcher: EvaluationDispatcher,
        dispatcher: RegressionDispatcher,
        handler_registry: HandlerRegistry | None = None,
        evaluation_config: EvaluationRuntimeConfig | None = None,
        config: RegressionRuntimeConfig | None = None,
        worker_label: str = "agentlens-regression-worker",
    ) -> None:
        self.repository = repository
        self.evaluation_job_repository = evaluation_job_repository
        self.evaluation_result_repository = evaluation_result_repository
        self.evaluation_dispatcher = evaluation_dispatcher
        self.dispatcher = dispatcher
        self.handler_registry = handler_registry or HandlerRegistry()
        self.evaluation_config = evaluation_config or EvaluationRuntimeConfig()
        self.config = config or RegressionRuntimeConfig()
        self.worker_id = f"{worker_label}-{uuid4()}"
        self._stop = threading.Event()

    def recover_once(self) -> int:
        try:
            return RegressionRecoveryDispatcher(self.repository, self.dispatcher).dispatch_ready(
                now=datetime.now(UTC), limit=self.config.recovery_batch_size
            )
        except RegressionRedisUnavailable:
            return 0

    def run_once(self) -> bool:
        run_id = self.dispatcher.receive(self.config.worker_poll_timeout)
        if run_id is None:
            return False
        return self.process_run(run_id)

    def process_run(self, run_id: UUID) -> bool:
        run = self.repository.get_run_any(run_id)
        if run is None:
            return False
        project_id = str(run["project_id"])
        claimed = self.repository.claim_run(
            project_id,
            run_id,
            self.worker_id,
            datetime.now(UTC),
            self.config.lease_seconds,
        )
        if claimed is None:
            return False
        started = time.monotonic()
        try:
            missing = self.repository.required_evaluations(project_id, run_id)
            if missing:
                self._dispatch_evaluations(project_id, run_id, missing)
                self.repository.mark_waiting(
                    project_id,
                    run_id,
                    claimed.claim_token,
                    missing=[
                        f"{trace_id}:{evaluation_type}" for trace_id, evaluation_type, _ in missing
                    ],
                )
                return True
            raw_policy = run["policy_body"]
            policy_body = (
                cast(Mapping[str, object], raw_policy) if isinstance(raw_policy, Mapping) else {}
            )
            policy = RegressionPolicy.from_dict(
                {
                    "schema": policy_body.get("schema"),
                    "rules": policy_body.get("rules", []),
                },
                policy_id=UUID(str(run["policy_id"])),
                project_id=project_id,
                name=str(policy_body.get("name", "policy")),
                description=str(policy_body.get("description", "")),
                version=int(cast(int, run["policy_version"])),
            )
            result = build_comparison_result(
                self.repository.comparison_data(project_id, run_id), policy
            )
            success = self.repository.persist_comparison(
                project_id, run_id, claimed.claim_token, result
            )
            try:
                from agentlens.telemetry import get_metrics_registry

                get_metrics_registry().record_worker_job(
                    "regression", "success", time.monotonic() - started
                )
            except Exception:
                pass
            return success
        except Exception as exc:
            self.repository.fail_run(project_id, run_id, claimed.claim_token, str(exc)[:1000])
            try:
                from agentlens.telemetry import get_metrics_registry

                get_metrics_registry().record_worker_job(
                    "regression", "failed", time.monotonic() - started
                )
            except Exception:
                pass
            return True

    def _dispatch_evaluations(
        self,
        project_id: str,
        run_id: UUID,
        missing: tuple[tuple[UUID, str, Any], ...],
    ) -> None:
        for trace_id, evaluation_type, config in missing:
            if evaluation_type not in self.handler_registry.public_types():
                raise ValueError(f"unsupported evaluation type: {evaluation_type}")
            handler = self.handler_registry.get(evaluation_type)
            normalized = handler.normalize_config(config)
            normalized_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            key_value = f"regression:{run_id}:{trace_id}:{evaluation_type}:{normalized_json}"
            key_hash = hashlib.sha256(key_value.encode()).hexdigest()
            fingerprint = evaluation_request_fingerprint(
                evaluation_type,
                normalized,
                0,
                self.evaluation_config.default_timeout_seconds,
                self.evaluation_config.default_max_attempts,
            )
            try:
                creation = self.evaluation_job_repository.create_job(
                    project_id=project_id,
                    trace_id=trace_id,
                    evaluation_type=evaluation_type,
                    config=normalized,
                    priority=0,
                    timeout_seconds=self.evaluation_config.default_timeout_seconds,
                    max_attempts=self.evaluation_config.default_max_attempts,
                    idempotency_key_hash=key_hash,
                    request_fingerprint_value=fingerprint,
                )
            except JobIdempotencyConflict:
                continue
            try:
                self.evaluation_dispatcher.dispatch(creation.job.job_id)
            except RedisUnavailableError:
                continue

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.recover_once()
                self.run_once()
            except RegressionRedisUnavailable:
                self._stop.wait(1.0)


__all__ = [
    "RedisRegressionDispatcher",
    "RegressionDispatcher",
    "RegressionRecoveryDispatcher",
    "RegressionRedisUnavailable",
    "RegressionRuntimeConfig",
    "RegressionWorker",
    "UnavailableRegressionDispatcher",
]
