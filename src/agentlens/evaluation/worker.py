"""Sequential, multi-process-safe evaluation worker."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from agentlens.domain import Trace
from agentlens.domain.types import JSONValue
from agentlens.storage.contracts import canonical_fingerprint
from agentlens.storage.repository import TraceQueryRepository

from .config import EvaluationRuntimeConfig
from .errors import (
    EvaluationTimeoutError,
    HandlerExecutionError,
    JudgeError,
    RedisUnavailableError,
    ResultPersistenceUnavailable,
    StaleClaimError,
    UnknownHandlerError,
)
from .handlers import EvaluationHandler, HandlerRegistry
from .redis import EvaluationDispatcher, RecoveryDispatcher
from .repository import EvaluationJobRepository
from .result_repository import EvaluationResultRepository
from .results import EvaluationResultPayload
from .types import ClaimedJob

Clock = Callable[[], datetime]


class EvaluationWorker:
    """Claims one job at a time and fences late completion with a claim token.

    Handler timeouts are cooperative at the Python thread boundary. A timed-out
    handler is never allowed to commit because its claim is fenced; Python cannot
    safely hard-kill an arbitrary running thread.
    """

    def __init__(
        self,
        *,
        repository: EvaluationJobRepository,
        trace_repository: TraceQueryRepository,
        dispatcher: EvaluationDispatcher,
        result_repository: EvaluationResultRepository | None = None,
        registry: HandlerRegistry | None = None,
        config: EvaluationRuntimeConfig | None = None,
        worker_label: str = "agentlens-worker",
        clock: Clock | None = None,
    ) -> None:
        self.repository = repository
        self.trace_repository = trace_repository
        self.dispatcher = dispatcher
        self.result_repository = result_repository
        self.registry = registry or HandlerRegistry()
        self.config = config or EvaluationRuntimeConfig()
        if not worker_label or len(worker_label) > 200:
            raise ValueError("worker_label must be a non-empty bounded string")
        self.worker_id = f"{worker_label}-{uuid4()}"
        self._clock = clock or (lambda: datetime.now(UTC))
        self._stop = threading.Event()
        self._last_heartbeat = self._clock()
        self._jobs_completed = 0

    def now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def heartbeat(self) -> None:
        self._last_heartbeat = self.now()

    def health(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "last_heartbeat": self._last_heartbeat.isoformat(),
            "jobs_completed": self._jobs_completed,
            "stopping": self._stop.is_set(),
        }

    def recover_once(self) -> int:
        self.heartbeat()
        recovery = RecoveryDispatcher(self.repository, self.dispatcher)
        return recovery.dispatch_ready(
            now=self.now(),
            limit=self.config.recovery_batch_size,
        )

    def run_once(self) -> bool:
        self.heartbeat()
        job_id = self.dispatcher.receive(self.config.worker_poll_timeout)
        if job_id is None:
            return False
        return self.process_job(job_id)

    def process_job(self, job_id: UUID) -> bool:
        claimed = self.repository.claim_job(
            job_id=job_id,
            worker_id=self.worker_id,
            now=self.now(),
            lease_seconds=self.config.lease_seconds,
        )
        if claimed is None:
            return False
        started = time.monotonic()
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._renew_until_done,
            args=(claimed.job.job_id, claimed.claim_token, heartbeat_stop),
            daemon=True,
            name="agentlens-lease-heartbeat",
        )
        heartbeat_thread.start()
        try:
            trace = self.trace_repository.get_trace(claimed.job.project_id, claimed.job.trace_id)
            if trace is None:
                self._failure(
                    claimed,
                    started,
                    error_code="trace_not_found",
                    safe_error_message="Referenced trace is unavailable.",
                    retryable=False,
                )
                return True
            handler = self.registry.get(claimed.job.evaluation_type)
            normalized_config: Mapping[str, JSONValue]
            if hasattr(handler, "normalize_config"):
                normalized_config = handler.normalize_config(claimed.job.config)
            else:
                normalized_config = cast(Mapping[str, JSONValue], claimed.job.config)
            payload = self._execute(
                handler,
                trace,
                normalized_config,
                claimed.job.timeout_seconds,
            )
            try:
                if payload is None:
                    self.repository.complete_success(
                        job_id=claimed.job.job_id,
                        claim_token=claimed.claim_token,
                        attempt_number=claimed.attempt_number,
                        now=self.now(),
                        duration_seconds=time.monotonic() - started,
                    )
                else:
                    if self.result_repository is None:
                        raise ResultPersistenceUnavailable("result repository is not configured")
                    self.result_repository.complete_success_with_result(
                        job_id=claimed.job.job_id,
                        claim_token=claimed.claim_token,
                        attempt_number=claimed.attempt_number,
                        evaluator_name=handler.evaluator_name,
                        evaluator_version=handler.evaluator_version,
                        normalized_config=normalized_config,
                        trace_fingerprint=canonical_fingerprint(trace),
                        payload=payload,
                        now=self.now(),
                        duration_seconds=time.monotonic() - started,
                    )
            except StaleClaimError:
                return True
            self._jobs_completed += 1
            try:
                from agentlens.telemetry import get_metrics_registry

                get_metrics_registry().record_worker_job(
                    "evaluation", "success", time.monotonic() - started
                )
            except Exception:
                pass
            return True
        except UnknownHandlerError:
            self._failure(
                claimed,
                started,
                error_code="unknown_handler",
                safe_error_message="Evaluation handler is not registered.",
                retryable=False,
            )
            return True
        except ValueError:
            self._failure(
                claimed,
                started,
                error_code="invalid_input",
                safe_error_message="Evaluation configuration is invalid.",
                retryable=False,
            )
            return True
        except EvaluationTimeoutError:
            self._failure(
                claimed,
                started,
                error_code="timeout",
                safe_error_message="Evaluation handler exceeded its timeout.",
                retryable=True,
            )
            return True
        except HandlerExecutionError as exc:
            self._failure(
                claimed,
                started,
                error_code=exc.code,
                safe_error_message="Evaluation handler failed.",
                retryable=exc.retryable,
            )
            return True
        except JudgeError as exc:
            self._failure(
                claimed,
                started,
                error_code=exc.code,
                safe_error_message="Semantic judge evaluation failed.",
                retryable=exc.retryable,
            )
            return True
        except ResultPersistenceUnavailable:
            self._failure(
                claimed,
                started,
                error_code="result_storage_unavailable",
                safe_error_message="Evaluation result storage is unavailable.",
                retryable=True,
            )
            return True
        except Exception:
            self._failure(
                claimed,
                started,
                error_code="handler_error",
                safe_error_message="Evaluation handler failed.",
                retryable=True,
            )
            return True
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=max(0.1, self.config.heartbeat_seconds))

    def _execute(
        self,
        handler: EvaluationHandler,
        trace: Trace,
        config: Mapping[str, JSONValue],
        timeout_seconds: float,
    ) -> EvaluationResultPayload | None:
        evaluator = handler.evaluate
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agentlens-evaluation")
        future = executor.submit(evaluator, trace, config)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise EvaluationTimeoutError("timeout") from None
        except Exception:
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=True)

    def _renew_until_done(self, job_id: UUID, claim_token: UUID, stop: threading.Event) -> None:
        while not stop.wait(self.config.heartbeat_seconds):
            self.heartbeat()
            try:
                if not self.repository.renew_lease(
                    job_id=job_id,
                    claim_token=claim_token,
                    worker_id=self.worker_id,
                    now=self.now(),
                    lease_seconds=self.config.lease_seconds,
                ):
                    return
            except Exception:
                return

    def _failure(
        self,
        claimed: ClaimedJob,
        started: float,
        *,
        error_code: str,
        safe_error_message: str,
        retryable: bool,
    ) -> None:
        claim = claimed
        try:
            self.repository.record_failure(
                job_id=claim.job.job_id,
                claim_token=claim.claim_token,
                attempt_number=claim.attempt_number,
                now=self.now(),
                error_code=error_code,
                safe_error_message=safe_error_message,
                retryable=retryable,
                retry_delay_seconds=min(
                    self.config.retry_max_seconds,
                    self.config.retry_base_seconds * (2 ** (claim.attempt_number - 1)),
                ),
                duration_seconds=time.monotonic() - started,
            )
            try:
                from agentlens.telemetry import get_metrics_registry

                get_metrics_registry().record_worker_job(
                    "evaluation", "failed", time.monotonic() - started
                )
                if retryable:
                    get_metrics_registry().record_worker_retry("evaluation")
            except Exception:
                pass
        except StaleClaimError:
            return

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.recover_once()
                self.run_once()
            except RedisUnavailableError:
                self._stop.wait(1.0)


__all__ = ["EvaluationWorker"]
