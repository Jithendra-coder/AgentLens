"""Recoverable Redis dispatch and bounded replay worker."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import redis

from agentlens.domain import JSONValue
from agentlens.domain.types import validate_json_value
from agentlens.storage.contracts import canonical_fingerprint
from agentlens.storage.repository import TraceQueryRepository

from .models import ReplayTargetResponse
from .repository import ClaimedExecution, PostgresReplayRepository, ReplayStorageError
from .targets import ReplayExecutionContext, ReplayTargetError, TrustedReplayTargetRegistry


class ReplayRedisUnavailable(Exception):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class ReplayRuntimeConfig:
    redis_url: str = "redis://127.0.0.1:56379/0"
    queue_name: str = "agentlens:replay:v1"
    redis_connect_timeout: float = 2.0
    redis_socket_timeout: float = 2.0
    lease_seconds: float = 30.0
    heartbeat_seconds: float = 10.0
    default_timeout_seconds: float = 10.0
    default_max_attempts: int = 2
    worker_poll_timeout: int = 1
    recovery_batch_size: int = 100
    max_concurrency: int = 8

    def __post_init__(self) -> None:
        if not self.redis_url or not self.queue_name:
            raise ValueError("redis_url and queue_name are required")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("heartbeat_seconds must be shorter than lease_seconds")
        if not 1 <= self.max_concurrency <= 32:
            raise ValueError("max_concurrency must be between 1 and 32")

    def __repr__(self) -> str:
        return f"ReplayRuntimeConfig(redis_url='<redacted>', queue_name={self.queue_name!r})"


class ReplayDispatcher(Protocol):
    def dispatch(self, execution_id: UUID) -> None: ...

    def receive(self, timeout: int) -> UUID | None: ...

    def check_ready(self) -> bool: ...

    def close(self) -> None: ...


class UnavailableReplayDispatcher:
    def dispatch(self, execution_id: UUID) -> None:
        del execution_id
        raise ReplayRedisUnavailable("replay dispatch is unavailable")

    def receive(self, timeout: int) -> UUID | None:
        del timeout
        raise ReplayRedisUnavailable("replay dispatch is unavailable")

    def check_ready(self) -> bool:
        return False

    def close(self) -> None:
        return None


class RedisReplayDispatcher:
    def __init__(self, config: ReplayRuntimeConfig, *, client: Any | None = None) -> None:
        self.config = config
        self._client = client or redis.Redis.from_url(
            config.redis_url,
            socket_connect_timeout=config.redis_connect_timeout,
            socket_timeout=config.redis_socket_timeout,
            health_check_interval=30,
            decode_responses=True,
        )

    def dispatch(self, execution_id: UUID) -> None:
        try:
            self._client.rpush(
                self.config.queue_name,
                json.dumps({"execution_id": str(execution_id)}, separators=(",", ":")),
            )
        except redis.RedisError as exc:
            raise ReplayRedisUnavailable("replay dispatch is unavailable") from exc

    def receive(self, timeout: int) -> UUID | None:
        try:
            item = (
                self._client.lpop(self.config.queue_name)
                if timeout <= 0
                else self._client.blpop([self.config.queue_name], timeout=timeout)
            )
        except redis.RedisError as exc:
            raise ReplayRedisUnavailable("replay dispatch is unavailable") from exc
        if item is None:
            return None
        payload = item[1] if isinstance(item, (tuple, list)) and len(item) == 2 else item
        try:
            body = json.loads(str(payload))
            return UUID(str(body["execution_id"])) if isinstance(body, dict) else None
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


class ReplayRecoveryDispatcher:
    def __init__(self, repository: PostgresReplayRepository, dispatcher: ReplayDispatcher) -> None:
        self.repository = repository
        self.dispatcher = dispatcher

    def dispatch_ready(self, *, now: datetime, limit: int) -> int:
        count = 0
        for execution_id in self.repository.dispatchable_execution_ids(now=now, limit=limit):
            self.dispatcher.dispatch(execution_id)
            count += 1
        return count


class ReplayWorker:
    def __init__(
        self,
        *,
        repository: PostgresReplayRepository,
        trace_repository: TraceQueryRepository,
        dispatcher: ReplayDispatcher,
        registry: TrustedReplayTargetRegistry,
        config: ReplayRuntimeConfig | None = None,
        worker_label: str = "agentlens-replay-worker",
    ) -> None:
        self.repository = repository
        self.trace_repository = trace_repository
        self.dispatcher = dispatcher
        self.registry = registry
        self.config = config or ReplayRuntimeConfig()
        self.worker_id = f"{worker_label}-{uuid4()}"
        self._stop = threading.Event()

    def recover_once(self) -> int:
        try:
            return ReplayRecoveryDispatcher(self.repository, self.dispatcher).dispatch_ready(
                now=datetime.now(UTC), limit=self.config.recovery_batch_size
            )
        except ReplayRedisUnavailable:
            return 0

    def run_once(self) -> bool:
        execution_id = self.dispatcher.receive(self.config.worker_poll_timeout)
        if execution_id is None:
            return False
        return self.process_execution(execution_id)

    def run_batch(self) -> int:
        first = self.dispatcher.receive(self.config.worker_poll_timeout)
        if first is None:
            return 0
        ids = [first]
        for _ in range(self.config.max_concurrency - 1):
            next_id = self.dispatcher.receive(0)
            if next_id is None:
                break
            ids.append(next_id)
        with ThreadPoolExecutor(max_workers=min(self.config.max_concurrency, len(ids))) as executor:
            return sum(executor.map(self.process_execution, ids))

    def process_execution(self, execution_id: UUID) -> bool:
        claimed = self.repository.claim_execution(
            execution_id, self.worker_id, datetime.now(UTC), self.config.lease_seconds
        )
        if claimed is None:
            return False
        started = time.monotonic()
        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat,
            args=(claimed, stop),
            daemon=True,
            name="agentlens-replay-lease-heartbeat",
        )
        heartbeat.start()
        try:
            profile_id = str(claimed.run["target_profile_id"])
            target_item = self.registry.get(str(claimed.run["project_id"]), profile_id)
            if target_item is None:
                self._failure(claimed, "unknown_target_profile", False, started)
                return True
            profile, target = target_item
            if profile.safety_class == "side_effectful":
                self._failure(claimed, "side_effectful_target_rejected", False, started)
                return True
            context = ReplayExecutionContext(
                project_id=str(claimed.run["project_id"]),
                replay_run_id=cast(UUID, claimed.run["replay_run_id"]),
                execution_id=cast(UUID, claimed.execution["execution_id"]),
                case_id=claimed.case.case_id,
                correlation_id=str(claimed.execution["execution_id"]),
            )
            response = self._execute(
                target,
                claimed.case.input,
                context,
                float(cast(float, claimed.run["timeout_seconds"])),
            )
            if not isinstance(response, ReplayTargetResponse):
                self._failure(claimed, "invalid_target_response", False, started)
                return True
            validate_json_value(response.output, "target output")
            trace_id: UUID | None = None
            if response.trace is not None:
                if response.trace.project_id != str(claimed.run["project_id"]):
                    self._failure(claimed, "target_trace_project_mismatch", False, started)
                    return True
                self.trace_repository.ingest(response.trace)
                trace_id = cast(UUID, response.trace.trace_id)
            request_hash = hashlib.sha256(
                json.dumps(
                    {"case_id": str(claimed.case.case_id), "input": claimed.case.input},
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            output_hash = (
                canonical_fingerprint(response.trace)
                if response.trace
                else hashlib.sha256(
                    json.dumps(
                        response.output, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode("utf-8")
                ).hexdigest()
            )
            self.repository.complete_success(
                execution_id=cast(UUID, claimed.execution["execution_id"]),
                claim_token=claimed.claim_token,
                attempt_number=claimed.attempt_number,
                output=response.output,
                request_fingerprint_value=request_hash,
                response_fingerprint=output_hash,
                generated_trace_id=trace_id,
                now=datetime.now(UTC),
                duration_seconds=time.monotonic() - started,
            )
            try:
                from agentlens.telemetry import get_metrics_registry

                get_metrics_registry().record_worker_job(
                    "replay", "success", time.monotonic() - started
                )
            except Exception:
                pass
            return True
        except ReplayTargetError as exc:
            self._failure(claimed, exc.code, exc.retryable, started)
            return True
        except FutureTimeoutError:
            self._failure(claimed, "timeout", True, started)
            return True
        except (ValueError, TypeError, json.JSONDecodeError):
            self._failure(claimed, "invalid_target_response", False, started)
            return True
        except Exception:
            self._failure(claimed, "target_unavailable", True, started)
            return True
        finally:
            stop.set()
            heartbeat.join(timeout=max(0.1, self.config.heartbeat_seconds))

    def _execute(
        self, target: Any, input_value: JSONValue, context: ReplayExecutionContext, timeout: float
    ) -> Any:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agentlens-replay-target")
        future = executor.submit(target.execute, input_value, context)
        try:
            result = future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        except Exception:
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=True)
            return result

    def _failure(
        self, claimed: ClaimedExecution, code: str, retryable: bool, started: float
    ) -> None:
        try:
            self.repository.record_failure(
                execution_id=cast(UUID, claimed.execution["execution_id"]),
                claim_token=claimed.claim_token,
                attempt_number=claimed.attempt_number,
                error_code=code,
                safe_message="Replay target execution failed.",
                retryable=retryable,
                max_attempts=int(cast(int, claimed.run["max_attempts"])),
                now=datetime.now(UTC),
                duration_seconds=time.monotonic() - started,
            )
            try:
                from agentlens.telemetry import get_metrics_registry

                get_metrics_registry().record_worker_job(
                    "replay", "failed", time.monotonic() - started
                )
                if retryable:
                    get_metrics_registry().record_worker_retry("replay")
            except Exception:
                pass
        except ReplayStorageError:
            return

    def _heartbeat(self, claimed: ClaimedExecution, stop: threading.Event) -> None:
        while not stop.wait(self.config.heartbeat_seconds):
            try:
                if not self.repository.renew_execution(
                    cast(UUID, claimed.execution["execution_id"]),
                    claimed.claim_token,
                    self.worker_id,
                    datetime.now(UTC),
                    self.config.lease_seconds,
                ):
                    return
            except ReplayStorageError:
                return

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.recover_once()
                self.run_batch()
            except ReplayRedisUnavailable:
                self._stop.wait(1.0)


__all__ = [
    "RedisReplayDispatcher",
    "ReplayDispatcher",
    "ReplayRecoveryDispatcher",
    "ReplayRedisUnavailable",
    "ReplayRuntimeConfig",
    "ReplayWorker",
    "UnavailableReplayDispatcher",
]
