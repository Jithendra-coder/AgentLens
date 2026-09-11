"""PostgreSQL repository for immutable evaluation results and atomic job completion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from agentlens.domain.types import JSONValue, thaw_payload
from agentlens.storage.config import DatabaseConfig

from .errors import JobStorageUnavailable, StaleClaimError
from .models import (
    evaluation_job_attempts,
    evaluation_jobs,
    evaluation_judge_invocations,
    evaluation_results,
)
from .results import (
    RESULT_SCHEMA_VERSION,
    EvaluationFinding,
    EvaluationMode,
    EvaluationResult,
    EvaluationResultPayload,
    JudgeInvocation,
    ResultStatus,
    canonical_json_fingerprint,
)
from .types import AttemptOutcome, JobState


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EvaluationResultSummary:
    result_id: UUID
    job_id: UUID
    evaluation_type: str
    evaluator_name: str
    evaluator_version: str
    evaluation_mode: EvaluationMode
    result_status: ResultStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EvaluationResultListItem:
    result_id: UUID
    trace_id: UUID
    evaluation_type: str
    evaluator_name: str
    evaluator_version: str
    evaluation_mode: EvaluationMode
    result_status: ResultStatus
    created_at: datetime


class EvaluationResultRepository(Protocol):
    def complete_success_with_result(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        evaluator_name: str,
        evaluator_version: str,
        normalized_config: Mapping[str, JSONValue],
        trace_fingerprint: str,
        payload: EvaluationResultPayload,
        now: datetime,
        duration_seconds: float,
    ) -> EvaluationResult: ...

    def get_result(self, project_id: str, result_id: UUID) -> EvaluationResult | None: ...

    def get_result_for_job(self, project_id: str, job_id: UUID) -> EvaluationResult | None: ...

    def list_results(
        self, project_id: str, trace_id: UUID, limit: int
    ) -> tuple[EvaluationResultSummary, ...]: ...

    def list_results_in_window(
        self,
        project_id: str,
        started_at: datetime,
        ended_at: datetime,
        evaluation_type: str | None,
        result_status: str | None,
        limit: int,
    ) -> tuple[EvaluationResultListItem, ...]: ...

    def check_ready(self) -> bool: ...

    def dispose(self) -> None: ...


class PostgresEvaluationResultRepository:
    """Append-only result storage sharing the PostgreSQL engine boundary."""

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

    def complete_success_with_result(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        evaluator_name: str,
        evaluator_version: str,
        normalized_config: Mapping[str, JSONValue],
        trace_fingerprint: str,
        payload: EvaluationResultPayload,
        now: datetime,
        duration_seconds: float,
    ) -> EvaluationResult:
        current = _utc(now)
        config = cast(dict[str, JSONValue], dict(normalized_config))
        config_fingerprint = canonical_json_fingerprint(config)
        try:
            with self._sessions() as session:
                with session.begin():
                    job = (
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
                    if job is None:
                        raise StaleClaimError("job claim is no longer current")
                    result_id = uuid4()
                    result = EvaluationResult(
                        result_id=result_id,
                        result_schema_version=RESULT_SCHEMA_VERSION,
                        project_id=cast(str, job["project_id"]),
                        trace_id=cast(UUID, job["trace_id"]),
                        job_id=job_id,
                        evaluation_type=cast(str, job["evaluation_type"]),
                        evaluator_name=evaluator_name,
                        evaluator_version=evaluator_version,
                        evaluation_mode=payload.evaluation_mode,
                        result_status=cast(ResultStatus, payload.result_status),
                        created_at=current,
                        config=config,
                        config_fingerprint=config_fingerprint,
                        trace_fingerprint=trace_fingerprint,
                        metrics=cast(
                            Mapping[str, JSONValue],
                            thaw_payload(payload.metrics),
                        ),
                        findings=tuple(payload.findings),
                        evidence=cast(
                            Mapping[str, JSONValue],
                            thaw_payload(payload.evidence),
                        ),
                        judge_invocations=tuple(payload.judge_invocations),
                    )
                    session.execute(
                        evaluation_results.insert().values(
                            result_id=result.result_id,
                            result_schema_version=result.result_schema_version,
                            project_id=result.project_id,
                            trace_id=result.trace_id,
                            job_id=result.job_id,
                            evaluation_type=result.evaluation_type,
                            evaluator_name=result.evaluator_name,
                            evaluator_version=result.evaluator_version,
                            evaluation_mode=EvaluationMode(result.evaluation_mode).value,
                            result_status=result.result_status.value,
                            created_at=result.created_at,
                            config=cast(dict[str, JSONValue], thaw_payload(result.config)),
                            config_fingerprint=result.config_fingerprint,
                            trace_fingerprint=result.trace_fingerprint,
                            metrics=cast(dict[str, JSONValue], thaw_payload(result.metrics)),
                            findings=[finding.to_dict() for finding in result.findings],
                            evidence=cast(dict[str, JSONValue], thaw_payload(result.evidence)),
                        )
                    )
                    for invocation in result.judge_invocations:
                        session.execute(
                            evaluation_judge_invocations.insert().values(
                                invocation_id=invocation.invocation_id,
                                project_id=result.project_id,
                                result_id=result.result_id,
                                job_id=result.job_id,
                                judge_profile=invocation.judge_profile,
                                provider=invocation.provider,
                                model=invocation.model,
                                adapter_version=invocation.adapter_version,
                                prompt_version=invocation.prompt_version,
                                parameters=cast(
                                    dict[str, JSONValue],
                                    thaw_payload(invocation.parameters),
                                ),
                                request_fingerprint=invocation.request_fingerprint,
                                response_fingerprint=invocation.response_fingerprint,
                                started_at=invocation.started_at,
                                ended_at=invocation.ended_at,
                                status=invocation.status,
                                token_usage=(
                                    cast(dict[str, JSONValue], thaw_payload(invocation.token_usage))
                                    if invocation.token_usage is not None
                                    else None
                                ),
                            )
                        )
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
                            outcome=AttemptOutcome.SUCCEEDED.value,
                            error_code=None,
                            safe_error_message=None,
                            duration_seconds=max(0.0, duration_seconds),
                        )
                    )
                    session.execute(
                        update(evaluation_jobs)
                        .where(evaluation_jobs.c.job_id == job_id)
                        .values(
                            state=JobState.SUCCEEDED.value,
                            updated_at=current,
                            available_at=current,
                            claimed_by=None,
                            claim_token=None,
                            lease_expires_at=None,
                        )
                    )
                    return result
        except StaleClaimError:
            raise
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation result storage is unavailable") from exc

    def get_result(self, project_id: str, result_id: UUID) -> EvaluationResult | None:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(evaluation_results).where(
                            and_(
                                evaluation_results.c.project_id == project_id,
                                evaluation_results.c.result_id == result_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                invocations = (
                    session.execute(
                        select(evaluation_judge_invocations)
                        .where(
                            and_(
                                evaluation_judge_invocations.c.project_id == project_id,
                                evaluation_judge_invocations.c.result_id == result_id,
                            )
                        )
                        .order_by(evaluation_judge_invocations.c.started_at)
                    )
                    .mappings()
                    .all()
                )
                return self._result(
                    cast(Mapping[str, object], row),
                    tuple(
                        self._invocation(cast(Mapping[str, object], item)) for item in invocations
                    ),
                )
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation result storage is unavailable") from exc

    def get_result_for_job(self, project_id: str, job_id: UUID) -> EvaluationResult | None:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(evaluation_results).where(
                            and_(
                                evaluation_results.c.project_id == project_id,
                                evaluation_results.c.job_id == job_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                invocations = (
                    session.execute(
                        select(evaluation_judge_invocations)
                        .where(
                            and_(
                                evaluation_judge_invocations.c.project_id == project_id,
                                evaluation_judge_invocations.c.result_id == row["result_id"],
                            )
                        )
                        .order_by(evaluation_judge_invocations.c.started_at)
                    )
                    .mappings()
                    .all()
                )
                return self._result(
                    cast(Mapping[str, object], row),
                    tuple(
                        self._invocation(cast(Mapping[str, object], item)) for item in invocations
                    ),
                )
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation result storage is unavailable") from exc

    def list_results(
        self, project_id: str, trace_id: UUID, limit: int
    ) -> tuple[EvaluationResultSummary, ...]:
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(evaluation_results)
                        .where(
                            and_(
                                evaluation_results.c.project_id == project_id,
                                evaluation_results.c.trace_id == trace_id,
                            )
                        )
                        .order_by(
                            evaluation_results.c.created_at.desc(),
                            evaluation_results.c.result_id.desc(),
                        )
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                return tuple(
                    EvaluationResultSummary(
                        result_id=cast(UUID, row["result_id"]),
                        job_id=cast(UUID, row["job_id"]),
                        evaluation_type=cast(str, row["evaluation_type"]),
                        evaluator_name=cast(str, row["evaluator_name"]),
                        evaluator_version=cast(str, row["evaluator_version"]),
                        evaluation_mode=EvaluationMode(cast(str, row["evaluation_mode"])),
                        result_status=ResultStatus(cast(str, row["result_status"])),
                        created_at=_utc(cast(datetime, row["created_at"])),
                    )
                    for row in rows
                )
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation result storage is unavailable") from exc

    def list_results_in_window(
        self,
        project_id: str,
        started_at: datetime,
        ended_at: datetime,
        evaluation_type: str | None,
        result_status: str | None,
        limit: int,
    ) -> tuple[EvaluationResultListItem, ...]:
        conditions = [
            evaluation_results.c.project_id == project_id,
            evaluation_results.c.created_at >= _utc(started_at),
            evaluation_results.c.created_at < _utc(ended_at),
        ]
        if evaluation_type is not None:
            conditions.append(evaluation_results.c.evaluation_type == evaluation_type)
        if result_status is not None:
            conditions.append(evaluation_results.c.result_status == result_status)
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(evaluation_results)
                        .where(and_(*conditions))
                        .order_by(
                            evaluation_results.c.created_at.desc(),
                            evaluation_results.c.result_id.desc(),
                        )
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                return tuple(
                    EvaluationResultListItem(
                        result_id=cast(UUID, row["result_id"]),
                        trace_id=cast(UUID, row["trace_id"]),
                        evaluation_type=cast(str, row["evaluation_type"]),
                        evaluator_name=cast(str, row["evaluator_name"]),
                        evaluator_version=cast(str, row["evaluator_version"]),
                        evaluation_mode=EvaluationMode(cast(str, row["evaluation_mode"])),
                        result_status=ResultStatus(cast(str, row["result_status"])),
                        created_at=_utc(cast(datetime, row["created_at"])),
                    )
                    for row in rows
                )
        except SQLAlchemyError as exc:
            raise JobStorageUnavailable("durable evaluation result storage is unavailable") from exc

    @staticmethod
    def _result(
        row: Mapping[str, object], invocations: tuple[JudgeInvocation, ...] = ()
    ) -> EvaluationResult:
        raw_findings = cast(list[Mapping[str, object]], row["findings"])
        findings = tuple(
            EvaluationFinding(
                code=cast(str, finding["code"]),
                severity=cast(str, finding["severity"]),
                message=cast(str, finding["message"]),
                evidence=cast(Mapping[str, JSONValue], finding.get("evidence", {})),
            )
            for finding in raw_findings
        )
        return EvaluationResult(
            result_id=cast(UUID, row["result_id"]),
            result_schema_version=cast(str, row["result_schema_version"]),
            project_id=cast(str, row["project_id"]),
            trace_id=cast(UUID, row["trace_id"]),
            job_id=cast(UUID, row["job_id"]),
            evaluation_type=cast(str, row["evaluation_type"]),
            evaluator_name=cast(str, row["evaluator_name"]),
            evaluator_version=cast(str, row["evaluator_version"]),
            evaluation_mode=EvaluationMode(cast(str, row["evaluation_mode"])),
            result_status=ResultStatus(cast(str, row["result_status"])),
            created_at=_utc(cast(datetime, row["created_at"])),
            config=cast(Mapping[str, JSONValue], row["config"]),
            config_fingerprint=cast(str, row["config_fingerprint"]),
            trace_fingerprint=cast(str, row["trace_fingerprint"]),
            metrics=cast(Mapping[str, JSONValue], row["metrics"]),
            findings=findings,
            evidence=cast(Mapping[str, JSONValue], row["evidence"]),
            judge_invocations=invocations,
        )

    @staticmethod
    def _invocation(row: Mapping[str, object]) -> JudgeInvocation:
        return JudgeInvocation(
            invocation_id=cast(UUID, row["invocation_id"]),
            judge_profile=cast(str, row["judge_profile"]),
            provider=cast(str, row["provider"]),
            model=cast(str, row["model"]),
            adapter_version=cast(str, row["adapter_version"]),
            prompt_version=cast(str, row["prompt_version"]),
            parameters=cast(Mapping[str, JSONValue], row["parameters"]),
            request_fingerprint=cast(str, row["request_fingerprint"]),
            response_fingerprint=cast(str, row["response_fingerprint"]),
            started_at=_utc(cast(datetime, row["started_at"])),
            ended_at=_utc(cast(datetime, row["ended_at"])),
            status=cast(str, row["status"]),
            token_usage=(
                cast(Mapping[str, JSONValue], row["token_usage"])
                if row["token_usage"] is not None
                else None
            ),
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
    "EvaluationResultRepository",
    "EvaluationResultListItem",
    "EvaluationResultSummary",
    "PostgresEvaluationResultRepository",
]
