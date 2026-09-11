"""PostgreSQL-authoritative job ledger with atomic claims and lease fencing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import traces

from .errors import (
    JobIdempotencyConflict,
    JobStorageUnavailable,
    StaleClaimError,
    TraceNotFoundError,
)
from .models import evaluation_job_attempts, evaluation_jobs
from .types import (
    JOB_SCHEMA_VERSION,
    AttemptOutcome,
    ClaimedJob,
    EvaluationAttempt,
    EvaluationJob,
    JobCreation,
    JobFailure,
    JobState,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def hash_idempotency_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_fingerprint(
    evaluation_type: str,
    config: Mapping[str, object],
    priority: int,
    timeout_seconds: float,
    max_attempts: int,
) -> str:
    canonical = json.dumps(
        {
            "config": config,
            "evaluation_type": evaluation_type,
            "max_attempts": max_attempts,
            "priority": priority,
            "timeout_seconds": timeout_seconds,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EvaluationJobRepository(Protocol):
    def create_job(
        self,
        *,
        project_id: str,
        trace_id: UUID,
        evaluation_type: str,
        config: Mapping[str, object],
        priority: int,
        timeout_seconds: float,
        max_attempts: int,
        idempotency_key_hash: str | None = None,
        request_fingerprint_value: str | None = None,
        now: datetime | None = None,
    ) -> JobCreation: ...

    def get_job(self, project_id: str, job_id: UUID) -> EvaluationJob | None: ...

    def claim_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> ClaimedJob | None: ...

    def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> ClaimedJob | None: ...

    def dispatchable_job_ids(self, *, now: datetime, limit: int) -> tuple[UUID, ...]: ...

    def renew_lease(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> bool: ...

    def complete_success(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        now: datetime,
        duration_seconds: float,
    ) -> None: ...

    def record_failure(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        now: datetime,
        error_code: str,
        safe_error_message: str,
        retryable: bool,
        retry_delay_seconds: float,
        duration_seconds: float,
    ) -> JobFailure: ...

    def get_attempts(self, job_id: UUID) -> tuple[EvaluationAttempt, ...]: ...

    def check_ready(self) -> bool: ...

    def dispose(self) -> None: ...


class PostgresEvaluationJobRepository:
    """Durable repository; Redis is deliberately outside this authority boundary."""

    def __init__(self, config: DatabaseConfig, *, engine: Engine | None = None) -> None:
        self.config = config
        self.engine = engine or create_engine(
            config.sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
            connect_args={
                "connect_timeout": config.connect_timeout,
                "options": f"-c statement_timeout={config.statement_timeout_ms}",
            },
        )
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_job(
        self,
        *,
        project_id: str,
        trace_id: UUID,
        evaluation_type: str,
        config: Mapping[str, object],
        priority: int,
        timeout_seconds: float,
        max_attempts: int,
        idempotency_key_hash: str | None = None,
        request_fingerprint_value: str | None = None,
        now: datetime | None = None,
    ) -> JobCreation:
        created = _utc(now or datetime.now(UTC))
        try:
            with self._sessions() as session:
                with session.begin():
                    trace_exists = session.execute(
                        select(traces.c.trace_id).where(
                            and_(
                                traces.c.project_id == project_id,
                                traces.c.trace_id == trace_id,
                            )
                        )
                    ).scalar_one_or_none()
                    if trace_exists is None:
                        raise TraceNotFoundError("trace not found")
                    if idempotency_key_hash is not None:
                        existing = (
                            session.execute(
                                select(evaluation_jobs)
                                .where(
                                    and_(
                                        evaluation_jobs.c.project_id == project_id,
                                        evaluation_jobs.c.idempotency_key_hash
                                        == idempotency_key_hash,
                                    )
                                )
                                .with_for_update()
                            )
                            .mappings()
                            .one_or_none()
                        )
                        if existing is not None:
                            if existing["request_fingerprint"] != request_fingerprint_value:
                                raise JobIdempotencyConflict("idempotency key conflicts")
                            return JobCreation(
                                self._job(cast(Mapping[str, object], existing)),
                                duplicate=True,
                            )
                    job_id = uuid4()
                    inserted_id = session.execute(
                        pg_insert(evaluation_jobs)
                        .values(
                            job_id=job_id,
                            job_schema_version=JOB_SCHEMA_VERSION,
                            project_id=project_id,
                            trace_id=trace_id,
                            evaluation_type=evaluation_type,
                            config=dict(config),
                            state=JobState.QUEUED.value,
                            priority=priority,
                            created_at=created,
                            updated_at=created,
                            available_at=created,
                            attempt_count=0,
                            max_attempts=max_attempts,
                            timeout_seconds=timeout_seconds,
                            claimed_by=None,
                            claim_token=None,
                            lease_expires_at=None,
                            last_error_code=None,
                            last_error_message=None,
                            idempotency_key_hash=idempotency_key_hash,
                            request_fingerprint=request_fingerprint_value,
                        )
                        .on_conflict_do_nothing()
                        .returning(evaluation_jobs.c.job_id)
                    ).scalar_one_or_none()
                    if inserted_id is None:
                        if idempotency_key_hash is None:
                            raise JobStorageUnavailable("evaluation job identity conflict")
                        existing = (
                            session.execute(
                                select(evaluation_jobs)
                                .where(
                                    and_(
                                        evaluation_jobs.c.project_id == project_id,
                                        evaluation_jobs.c.idempotency_key_hash
                                        == idempotency_key_hash,
                                    )
                                )
                                .with_for_update()
                            )
                            .mappings()
                            .one_or_none()
                        )
                        if existing is None:
                            raise JobStorageUnavailable("evaluation job identity conflict")
                        if existing["request_fingerprint"] != request_fingerprint_value:
                            raise JobIdempotencyConflict("idempotency key conflicts")
                        return JobCreation(
                            self._job(cast(Mapping[str, object], existing)),
                            duplicate=True,
                        )
                    job_id = cast(UUID, inserted_id)
                    row = (
                        session.execute(
                            select(evaluation_jobs).where(evaluation_jobs.c.job_id == job_id)
                        )
                        .mappings()
                        .one()
                    )
                    return JobCreation(
                        self._job(cast(Mapping[str, object], row)),
                        duplicate=False,
                    )
        except (TraceNotFoundError, JobIdempotencyConflict):
            raise
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    def get_job(self, project_id: str, job_id: UUID) -> EvaluationJob | None:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(evaluation_jobs).where(
                            and_(
                                evaluation_jobs.c.project_id == project_id,
                                evaluation_jobs.c.job_id == job_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                return self._job(cast(Mapping[str, object], row)) if row is not None else None
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    def claim_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> ClaimedJob | None:
        return self._claim(
            worker_id=worker_id,
            now=_utc(now),
            lease_seconds=lease_seconds,
            job_id=job_id,
        )

    def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> ClaimedJob | None:
        return self._claim(
            worker_id=worker_id,
            now=_utc(now),
            lease_seconds=lease_seconds,
            job_id=None,
        )

    def _claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
        job_id: UUID | None,
    ) -> ClaimedJob | None:
        if not worker_id or len(worker_id) > 255:
            raise ValueError("worker_id must be a non-empty bounded string")
        lease_expires = now + timedelta(seconds=lease_seconds)
        ready = and_(
            evaluation_jobs.c.state.in_([JobState.QUEUED.value, JobState.RETRY_WAIT.value]),
            evaluation_jobs.c.available_at <= now,
        )
        expired = and_(
            evaluation_jobs.c.state == JobState.RUNNING.value,
            evaluation_jobs.c.lease_expires_at <= now,
        )
        conditions = [or_(ready, expired)]
        if job_id is not None:
            conditions.append(evaluation_jobs.c.job_id == job_id)
        try:
            with self._sessions() as session:
                with session.begin():
                    row = (
                        session.execute(
                            select(evaluation_jobs)
                            .where(and_(*conditions))
                            .order_by(
                                evaluation_jobs.c.priority.desc(),
                                evaluation_jobs.c.available_at,
                                evaluation_jobs.c.created_at,
                            )
                            .limit(1)
                            .with_for_update(skip_locked=True)
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if row is None:
                        return None
                    previous_attempt = cast(int, row["attempt_count"])
                    if row["state"] == JobState.RUNNING.value and previous_attempt:
                        session.execute(
                            update(evaluation_job_attempts)
                            .where(
                                and_(
                                    evaluation_job_attempts.c.job_id == row["job_id"],
                                    evaluation_job_attempts.c.attempt_number == previous_attempt,
                                    evaluation_job_attempts.c.finished_at.is_(None),
                                )
                            )
                            .values(
                                finished_at=now,
                                outcome=AttemptOutcome.LEASE_EXPIRED.value,
                                error_code="lease_expired",
                                safe_error_message="Worker lease expired before completion.",
                                duration_seconds=None,
                            )
                        )
                        if previous_attempt >= cast(int, row["max_attempts"]):
                            session.execute(
                                update(evaluation_jobs)
                                .where(evaluation_jobs.c.job_id == row["job_id"])
                                .values(
                                    state=JobState.DEAD_LETTER.value,
                                    available_at=now,
                                    updated_at=now,
                                    claimed_by=None,
                                    claim_token=None,
                                    lease_expires_at=None,
                                    last_error_code="lease_expired",
                                    last_error_message="Worker lease expired before completion.",
                                )
                            )
                            return None
                    attempt_number = previous_attempt + 1
                    token = uuid4()
                    session.execute(
                        update(evaluation_jobs)
                        .where(evaluation_jobs.c.job_id == row["job_id"])
                        .values(
                            state=JobState.RUNNING.value,
                            attempt_count=attempt_number,
                            claimed_by=worker_id,
                            claim_token=token,
                            lease_expires_at=lease_expires,
                            updated_at=now,
                        )
                    )
                    session.execute(
                        evaluation_job_attempts.insert().values(
                            attempt_id=uuid4(),
                            job_id=row["job_id"],
                            attempt_number=attempt_number,
                            worker_id=worker_id,
                            started_at=now,
                            finished_at=None,
                            outcome=AttemptOutcome.RUNNING.value,
                            error_code=None,
                            safe_error_message=None,
                            duration_seconds=None,
                        )
                    )
                    updated = dict(row)
                    updated.update(
                        {
                            "state": JobState.RUNNING.value,
                            "attempt_count": attempt_number,
                            "claimed_by": worker_id,
                            "claim_token": token,
                            "lease_expires_at": lease_expires,
                            "updated_at": now,
                        }
                    )
                    return ClaimedJob(
                        job=self._job(updated),
                        attempt_number=attempt_number,
                        claim_token=token,
                    )
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    def dispatchable_job_ids(self, *, now: datetime, limit: int) -> tuple[UUID, ...]:
        current = _utc(now)
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(evaluation_jobs.c.job_id)
                        .where(
                            or_(
                                and_(
                                    evaluation_jobs.c.state.in_(
                                        [JobState.QUEUED.value, JobState.RETRY_WAIT.value]
                                    ),
                                    evaluation_jobs.c.available_at <= current,
                                ),
                                and_(
                                    evaluation_jobs.c.state == JobState.RUNNING.value,
                                    evaluation_jobs.c.lease_expires_at <= current,
                                ),
                            )
                        )
                        .order_by(
                            evaluation_jobs.c.priority.desc(),
                            evaluation_jobs.c.available_at,
                            evaluation_jobs.c.created_at,
                        )
                        .limit(limit)
                    )
                    .scalars()
                    .all()
                )
                return tuple(cast(UUID, value) for value in rows)
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    def renew_lease(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> bool:
        current = _utc(now)
        try:
            with self._sessions() as session:
                with session.begin():
                    result = session.execute(
                        update(evaluation_jobs)
                        .where(
                            and_(
                                evaluation_jobs.c.job_id == job_id,
                                evaluation_jobs.c.state == JobState.RUNNING.value,
                                evaluation_jobs.c.claim_token == claim_token,
                                evaluation_jobs.c.claimed_by == worker_id,
                                evaluation_jobs.c.lease_expires_at > current,
                            )
                        )
                        .values(
                            lease_expires_at=current + timedelta(seconds=lease_seconds),
                            updated_at=current,
                        )
                    )
                    return bool(int(getattr(result, "rowcount", 0) or 0) == 1)
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    def complete_success(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        now: datetime,
        duration_seconds: float,
    ) -> None:
        self._finish(
            job_id=job_id,
            claim_token=claim_token,
            attempt_number=attempt_number,
            now=_utc(now),
            outcome=AttemptOutcome.SUCCEEDED,
            state=JobState.SUCCEEDED,
            error_code=None,
            safe_error_message=None,
            duration_seconds=duration_seconds,
        )

    def record_failure(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        now: datetime,
        error_code: str,
        safe_error_message: str,
        retryable: bool,
        retry_delay_seconds: float,
        duration_seconds: float,
    ) -> JobFailure:
        current = _utc(now)
        terminal = not retryable
        try:
            with self._sessions() as session:
                with session.begin():
                    row = self._owned_job(session, job_id, claim_token, attempt_number)
                    if terminal or cast(int, row["attempt_count"]) >= cast(
                        int, row["max_attempts"]
                    ):
                        state = JobState.DEAD_LETTER
                        retry_at = None
                        outcome = AttemptOutcome.DEAD_LETTER
                    else:
                        state = JobState.RETRY_WAIT
                        retry_at = current + timedelta(seconds=max(0.0, retry_delay_seconds))
                        outcome = AttemptOutcome.RETRY_WAIT
                    session.execute(
                        update(evaluation_job_attempts)
                        .where(
                            and_(
                                evaluation_job_attempts.c.job_id == job_id,
                                evaluation_job_attempts.c.attempt_number == attempt_number,
                                evaluation_job_attempts.c.finished_at.is_(None),
                            )
                        )
                        .values(
                            finished_at=current,
                            outcome=outcome.value,
                            error_code=error_code[:128],
                            safe_error_message=safe_error_message[:1024],
                            duration_seconds=max(0.0, duration_seconds),
                        )
                    )
                    session.execute(
                        update(evaluation_jobs)
                        .where(evaluation_jobs.c.job_id == job_id)
                        .values(
                            state=state.value,
                            available_at=retry_at or current,
                            updated_at=current,
                            claimed_by=None,
                            claim_token=None,
                            lease_expires_at=None,
                            last_error_code=error_code[:128],
                            last_error_message=safe_error_message[:1024],
                        )
                    )
                    return JobFailure(state=state, retry_at=retry_at)
        except StaleClaimError:
            raise
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    def _owned_job(
        self,
        session: Session,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
    ) -> Mapping[str, object]:
        row = (
            session.execute(
                select(evaluation_jobs)
                .where(
                    and_(
                        evaluation_jobs.c.job_id == job_id,
                        evaluation_jobs.c.claim_token == claim_token,
                        evaluation_jobs.c.state == JobState.RUNNING.value,
                        evaluation_jobs.c.attempt_count == attempt_number,
                    )
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise StaleClaimError("job claim is no longer current")
        return cast(Mapping[str, object], row)

    def _finish(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        now: datetime,
        outcome: AttemptOutcome,
        state: JobState,
        error_code: str | None,
        safe_error_message: str | None,
        duration_seconds: float,
    ) -> None:
        try:
            with self._sessions() as session:
                with session.begin():
                    self._owned_job(session, job_id, claim_token, attempt_number)
                    session.execute(
                        update(evaluation_job_attempts)
                        .where(
                            and_(
                                evaluation_job_attempts.c.job_id == job_id,
                                evaluation_job_attempts.c.attempt_number == attempt_number,
                                evaluation_job_attempts.c.finished_at.is_(None),
                            )
                        )
                        .values(
                            finished_at=now,
                            outcome=outcome.value,
                            error_code=error_code,
                            safe_error_message=safe_error_message,
                            duration_seconds=max(0.0, duration_seconds),
                        )
                    )
                    session.execute(
                        update(evaluation_jobs)
                        .where(evaluation_jobs.c.job_id == job_id)
                        .values(
                            state=state.value,
                            updated_at=now,
                            available_at=now,
                            claimed_by=None,
                            claim_token=None,
                            lease_expires_at=None,
                        )
                    )
        except StaleClaimError:
            raise
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    def get_attempts(self, job_id: UUID) -> tuple[EvaluationAttempt, ...]:
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(evaluation_job_attempts)
                        .where(evaluation_job_attempts.c.job_id == job_id)
                        .order_by(evaluation_job_attempts.c.attempt_number)
                    )
                    .mappings()
                    .all()
                )
                return tuple(self._attempt(cast(Mapping[str, object], row)) for row in rows)
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation storage is unavailable") from exc

    @staticmethod
    def _job(row: Mapping[str, object]) -> EvaluationJob:
        config = row["config"]
        return EvaluationJob(
            job_id=cast(UUID, row["job_id"]),
            job_schema_version=cast(str, row["job_schema_version"]),
            project_id=cast(str, row["project_id"]),
            trace_id=cast(UUID, row["trace_id"]),
            evaluation_type=cast(str, row["evaluation_type"]),
            config=cast(Mapping[str, object], config),
            state=JobState(cast(str, row["state"])),
            priority=cast(int, row["priority"]),
            created_at=_utc(cast(datetime, row["created_at"])),
            updated_at=_utc(cast(datetime, row["updated_at"])),
            available_at=_utc(cast(datetime, row["available_at"])),
            attempt_count=cast(int, row["attempt_count"]),
            max_attempts=cast(int, row["max_attempts"]),
            timeout_seconds=cast(float, row["timeout_seconds"]),
            claimed_by=cast(str | None, row["claimed_by"]),
            claim_token=cast(UUID | None, row["claim_token"]),
            lease_expires_at=(
                _utc(cast(datetime, row["lease_expires_at"]))
                if row["lease_expires_at"] is not None
                else None
            ),
            last_error_code=cast(str | None, row["last_error_code"]),
        )

    @staticmethod
    def _attempt(row: Mapping[str, object]) -> EvaluationAttempt:
        return EvaluationAttempt(
            attempt_id=cast(UUID, row["attempt_id"]),
            job_id=cast(UUID, row["job_id"]),
            attempt_number=cast(int, row["attempt_number"]),
            worker_id=cast(str, row["worker_id"]),
            started_at=_utc(cast(datetime, row["started_at"])),
            finished_at=(
                _utc(cast(datetime, row["finished_at"])) if row["finished_at"] is not None else None
            ),
            outcome=AttemptOutcome(cast(str, row["outcome"])),
            error_code=cast(str | None, row["error_code"]),
            safe_error_message=cast(str | None, row["safe_error_message"]),
            duration_seconds=cast(float | None, row["duration_seconds"]),
        )

    def check_ready(self) -> bool:
        try:
            with self._sessions() as session:
                session.execute(select(1)).scalar_one()
            return True
        except SQLAlchemyError:
            return False

    def dispose(self) -> None:
        self.engine.dispose()


__all__ = [
    "EvaluationJobRepository",
    "PostgresEvaluationJobRepository",
    "hash_idempotency_key",
    "request_fingerprint",
]
