"""PostgreSQL-authoritative M10 policies, runs, and comparison reports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, delete, desc, func, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from agentlens.domain import JSONValue
from agentlens.evaluation.models import evaluation_judge_invocations, evaluation_results
from agentlens.replay.models import ReplayRunStatus
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    dataset_cases,
    regression_case_comparisons,
    regression_metric_comparisons,
    regression_policies,
    regression_runs,
    replay_case_executions,
    replay_runs,
    traces,
)

from .metric_registry import (
    aggregate,
    compatible_measurements,
    extract_case_value,
    finding_keys,
    get_metric,
)
from .models import (
    COMPARISON_ENGINE_VERSION,
    REGRESSION_REPORT_SCHEMA_VERSION,
    CandidateLimitStatus,
    MetricClassification,
    MetricDirection,
    MetricRule,
    RegressionPolicy,
    RegressionRunStatus,
)


class RegressionStorageError(Exception):
    pass


class RegressionNotFoundError(RegressionStorageError):
    pass


class RegressionValidationError(RegressionStorageError):
    pass


class RegressionImmutableError(RegressionStorageError):
    pass


class RegressionIdempotencyConflict(RegressionStorageError):
    pass


class StaleRegressionClaim(RegressionStorageError):
    pass


def request_fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _config_key(value: object) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _json(value: object) -> JSONValue:
    return cast(JSONValue, value)


def _row_dict(row: Mapping[str, object]) -> dict[str, object]:
    return {str(key): value for key, value in row.items()}


@dataclass(frozen=True, slots=True)
class ClaimedRegression:
    run: dict[str, object]
    claim_token: UUID


class PostgresRegressionRepository:
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

    def dispose(self) -> None:
        self.engine.dispose()

    def check_ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(select(func.now()))
            return True
        except SQLAlchemyError:
            return False

    def create_policy(
        self, project_id: str, name: str, description: str, raw_rules: object
    ) -> dict[str, object]:
        if not isinstance(raw_rules, list):
            raise RegressionValidationError("rules must be an array")
        try:
            policy = RegressionPolicy(
                project_id=project_id,
                name=name,
                description=description,
                rules=tuple(MetricRule.from_dict(item) for item in raw_rules),
            )
            for rule in policy.rules:
                if not rule.informational:
                    get_metric(rule.metric_id)
        except (TypeError, ValueError) as exc:
            raise RegressionValidationError(str(exc)) from exc
        now = policy.created_at
        try:
            with self._sessions() as session, session.begin():
                prior = session.execute(
                    select(func.max(regression_policies.c.version)).where(
                        and_(
                            regression_policies.c.project_id == project_id,
                            regression_policies.c.name == name,
                        )
                    )
                ).scalar_one_or_none()
                version = int(prior or 0) + 1
                policy = RegressionPolicy(
                    policy_id=policy.policy_id,
                    project_id=project_id,
                    name=name,
                    description=description,
                    version=version,
                    rules=policy.rules,
                    created_at=now,
                )
                session.execute(
                    regression_policies.insert().values(
                        policy_id=policy.policy_id,
                        project_id=project_id,
                        name=name,
                        description=description,
                        schema_version=policy.schema_version,
                        version=version,
                        rules=[rule.to_dict() for rule in policy.rules],
                        created_at=now,
                    )
                )
        except IntegrityError as exc:
            raise RegressionValidationError("policy version already exists") from exc
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression policy storage is unavailable") from exc
        return self.get_policy(project_id, policy.policy_id)

    def list_policies(self, project_id: str, limit: int = 100) -> tuple[dict[str, object], ...]:
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(regression_policies)
                        .where(regression_policies.c.project_id == project_id)
                        .order_by(
                            desc(regression_policies.c.created_at),
                            desc(regression_policies.c.version),
                        )
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                return tuple(self._policy_dict(cast(Mapping[str, object], row)) for row in rows)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression policy storage is unavailable") from exc

    def get_policy(self, project_id: str, policy_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(regression_policies).where(
                            and_(
                                regression_policies.c.project_id == project_id,
                                regression_policies.c.policy_id == policy_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise RegressionNotFoundError("regression policy not found")
                return self._policy_dict(cast(Mapping[str, object], row))
        except RegressionNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression policy storage is unavailable") from exc

    def create_run(
        self,
        *,
        project_id: str,
        baseline_run_id: UUID,
        candidate_run_id: UUID,
        policy_id: UUID,
        evaluation_plan: Sequence[Mapping[str, object]],
        idempotency_key: str | None,
        request_fingerprint_value: str,
    ) -> dict[str, object]:
        if baseline_run_id == candidate_run_id:
            raise RegressionValidationError("baseline and candidate runs must differ")
        now = datetime.now(UTC)
        key_hash = (
            hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
            if idempotency_key is not None
            else None
        )
        try:
            with self._sessions() as session, session.begin():
                baseline = self._project_run(session, project_id, baseline_run_id)
                candidate = self._project_run(session, project_id, candidate_run_id)
                if baseline is None or candidate is None:
                    raise RegressionNotFoundError("replay run not found")
                if baseline["status"] not in {
                    ReplayRunStatus.SUCCEEDED.value,
                    ReplayRunStatus.FAILED.value,
                    ReplayRunStatus.PARTIALLY_FAILED.value,
                }:
                    raise RegressionValidationError("baseline replay must be terminal")
                if candidate["status"] not in {
                    ReplayRunStatus.SUCCEEDED.value,
                    ReplayRunStatus.FAILED.value,
                    ReplayRunStatus.PARTIALLY_FAILED.value,
                }:
                    raise RegressionValidationError("candidate replay must be terminal")
                for field in ("dataset_id", "dataset_version_id", "dataset_checksum"):
                    if baseline[field] != candidate[field]:
                        raise RegressionValidationError(
                            "baseline and candidate dataset provenance differs"
                        )
                policy_row = (
                    session.execute(
                        select(regression_policies).where(
                            and_(
                                regression_policies.c.policy_id == policy_id,
                                regression_policies.c.project_id == project_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if policy_row is None:
                    raise RegressionNotFoundError("regression policy not found")
                if key_hash is not None:
                    existing = (
                        session.execute(
                            select(regression_runs)
                            .where(
                                and_(
                                    regression_runs.c.project_id == project_id,
                                    regression_runs.c.idempotency_key_hash == key_hash,
                                )
                            )
                            .with_for_update()
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if existing is not None:
                        if existing["request_fingerprint"] != request_fingerprint_value:
                            raise RegressionIdempotencyConflict(
                                "regression idempotency key conflicts"
                            )
                        duplicate = self._run_dict(cast(Mapping[str, object], existing))
                        duplicate["_duplicate"] = True
                        return duplicate
                run_id = uuid4()
                baseline_manifest = cast(dict[str, object], baseline["manifest"])
                candidate_manifest = cast(dict[str, object], candidate["manifest"])
                changed = self._changed_dimensions(baseline_manifest, candidate_manifest)
                session.execute(
                    regression_runs.insert().values(
                        regression_run_id=run_id,
                        project_id=project_id,
                        report_schema_version=REGRESSION_REPORT_SCHEMA_VERSION,
                        baseline_replay_run_id=baseline_run_id,
                        candidate_replay_run_id=candidate_run_id,
                        dataset_id=baseline["dataset_id"],
                        dataset_version_id=baseline["dataset_version_id"],
                        dataset_checksum=baseline["dataset_checksum"],
                        policy_id=policy_id,
                        policy_version=policy_row["version"],
                        evaluation_plan=[dict(item) for item in evaluation_plan],
                        baseline_manifest=baseline_manifest,
                        candidate_manifest=candidate_manifest,
                        changed_dimensions=changed,
                        status=RegressionRunStatus.QUEUED.value,
                        comparison_engine_version=COMPARISON_ENGINE_VERSION,
                        regression_count=0,
                        improvement_count=0,
                        unchanged_count=0,
                        insufficient_data_count=0,
                        incompatible_count=0,
                        has_regressions=0,
                        available_at=now,
                        claimed_by=None,
                        claim_token=None,
                        lease_expires_at=None,
                        idempotency_key_hash=key_hash,
                        request_fingerprint=request_fingerprint_value if key_hash else None,
                        created_at=now,
                    )
                )
                created = self._run_dict(
                    cast(
                        Mapping[str, object],
                        session.execute(
                            select(regression_runs).where(
                                regression_runs.c.regression_run_id == run_id
                            )
                        )
                        .mappings()
                        .one(),
                    )
                )
                created["_duplicate"] = False
                return created
        except (RegressionNotFoundError, RegressionValidationError, RegressionIdempotencyConflict):
            raise
        except IntegrityError as exc:
            raise RegressionStorageError("regression run could not be created") from exc
        except SQLAlchemyError as exc:
            raise RegressionStorageError(f"regression run storage is unavailable: {exc}") from exc

    def list_runs(self, project_id: str, limit: int = 100) -> tuple[dict[str, object], ...]:
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(regression_runs)
                        .where(regression_runs.c.project_id == project_id)
                        .order_by(
                            desc(regression_runs.c.created_at),
                            desc(regression_runs.c.regression_run_id),
                        )
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                return tuple(self._run_dict(cast(Mapping[str, object], row)) for row in rows)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression run storage is unavailable") from exc

    def get_run(self, project_id: str, run_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(regression_runs).where(
                            and_(
                                regression_runs.c.project_id == project_id,
                                regression_runs.c.regression_run_id == run_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise RegressionNotFoundError("regression run not found")
                body = self._run_dict(cast(Mapping[str, object], row))
                body["policy"] = self._policy_dict(
                    cast(
                        Mapping[str, object],
                        session.execute(
                            select(regression_policies).where(
                                regression_policies.c.policy_id == row["policy_id"]
                            )
                        )
                        .mappings()
                        .one(),
                    )
                )
                return body
        except RegressionNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression run storage is unavailable") from exc

    def get_run_any(self, run_id: UUID) -> dict[str, object] | None:
        """Load a run for a worker; the returned row includes its tenant."""
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(regression_runs).where(regression_runs.c.regression_run_id == run_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                body = self._run_dict(cast(Mapping[str, object], row))
                policy = (
                    session.execute(
                        select(regression_policies).where(
                            regression_policies.c.policy_id == row["policy_id"]
                        )
                    )
                    .mappings()
                    .one()
                )
                body["policy"] = self._policy_dict(cast(Mapping[str, object], policy))
                return body
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression run storage is unavailable") from exc

    def list_metrics(self, project_id: str, run_id: UUID) -> tuple[dict[str, object], ...]:
        self._ensure_run(project_id, run_id)
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(regression_metric_comparisons)
                        .where(regression_metric_comparisons.c.regression_run_id == run_id)
                        .order_by(regression_metric_comparisons.c.metric_id)
                    )
                    .mappings()
                    .all()
                )
                return tuple(self._metric_dict(cast(Mapping[str, object], row)) for row in rows)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression metrics are unavailable") from exc

    def list_cases(
        self,
        project_id: str,
        run_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        classification: str | None = None,
    ) -> tuple[dict[str, object], ...]:
        self._ensure_run(project_id, run_id)
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(regression_case_comparisons)
                        .where(regression_case_comparisons.c.regression_run_id == run_id)
                        .order_by(regression_case_comparisons.c.position)
                        .offset(offset)
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                output = tuple(self._case_dict(cast(Mapping[str, object], row)) for row in rows)
                if classification is None:
                    return output
                return tuple(
                    item
                    for item in output
                    if classification == item["status"]
                    or any(
                        comparison.get("classification") == classification
                        for comparison in cast(
                            Sequence[Mapping[str, object]], item["metric_comparisons"]
                        )
                    )
                )
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression cases are unavailable") from exc

    def get_case(self, project_id: str, run_id: UUID, case_id: UUID) -> dict[str, object]:
        self._ensure_run(project_id, run_id)
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(regression_case_comparisons).where(
                            and_(
                                regression_case_comparisons.c.regression_run_id == run_id,
                                regression_case_comparisons.c.case_id == case_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise RegressionNotFoundError("regression case not found")
                return self._case_dict(cast(Mapping[str, object], row))
        except RegressionNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression case is unavailable") from exc

    def dispatchable_run_ids(self, *, now: datetime, limit: int = 100) -> tuple[UUID, ...]:
        current = _utc(now)
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(regression_runs.c.regression_run_id)
                        .where(
                            or_(
                                and_(
                                    regression_runs.c.status.in_(
                                        [
                                            RegressionRunStatus.QUEUED.value,
                                            RegressionRunStatus.WAITING_FOR_EVALUATIONS.value,
                                        ]
                                    ),
                                    regression_runs.c.available_at <= current,
                                ),
                                and_(
                                    regression_runs.c.status.in_(
                                        [
                                            RegressionRunStatus.PREPARING.value,
                                            RegressionRunStatus.RUNNING.value,
                                        ]
                                    ),
                                    regression_runs.c.lease_expires_at <= current,
                                ),
                            )
                        )
                        .order_by(regression_runs.c.available_at, regression_runs.c.created_at)
                        .limit(limit)
                    )
                    .scalars()
                    .all()
                )
                return tuple(cast(UUID, value) for value in rows)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression dispatch state is unavailable") from exc

    def claim_run(
        self, project_id: str, run_id: UUID, worker_id: str, now: datetime, lease_seconds: float
    ) -> ClaimedRegression | None:
        current = _utc(now)
        token = uuid4()
        try:
            with self._sessions() as session, session.begin():
                row = (
                    session.execute(
                        select(regression_runs)
                        .where(
                            and_(
                                regression_runs.c.project_id == project_id,
                                regression_runs.c.regression_run_id == run_id,
                            )
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                if row["status"] == RegressionRunStatus.COMPLETED.value:
                    return None
                if row["status"] == RegressionRunStatus.FAILED.value:
                    return None
                if row["status"] in {
                    RegressionRunStatus.PREPARING.value,
                    RegressionRunStatus.RUNNING.value,
                }:
                    if row["lease_expires_at"] is not None and row["lease_expires_at"] > current:
                        return None
                session.execute(
                    update(regression_runs)
                    .where(regression_runs.c.regression_run_id == run_id)
                    .values(
                        status=RegressionRunStatus.RUNNING.value,
                        claimed_by=worker_id,
                        claim_token=token,
                        lease_expires_at=current + timedelta(seconds=lease_seconds),
                        started_at=row["started_at"] or current,
                    )
                )
                updated = dict(row)
                updated.update(
                    {
                        "status": RegressionRunStatus.RUNNING.value,
                        "claimed_by": worker_id,
                        "claim_token": token,
                    }
                )
                return ClaimedRegression(updated, token)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression claim is unavailable") from exc

    def renew_run(
        self,
        project_id: str,
        run_id: UUID,
        claim_token: UUID,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> bool:
        try:
            with self._sessions() as session, session.begin():
                result = session.execute(
                    update(regression_runs)
                    .where(
                        and_(
                            regression_runs.c.project_id == project_id,
                            regression_runs.c.regression_run_id == run_id,
                            regression_runs.c.claim_token == claim_token,
                            regression_runs.c.claimed_by == worker_id,
                            regression_runs.c.status == RegressionRunStatus.RUNNING.value,
                        )
                    )
                    .values(lease_expires_at=_utc(now) + timedelta(seconds=lease_seconds))
                )
                return bool(int(getattr(result, "rowcount", 0) or 0) == 1)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression lease is unavailable") from exc

    def mark_waiting(
        self, project_id: str, run_id: UUID, claim_token: UUID, *, missing: Sequence[str]
    ) -> bool:
        try:
            with self._sessions() as session, session.begin():
                result = session.execute(
                    update(regression_runs)
                    .where(
                        and_(
                            regression_runs.c.project_id == project_id,
                            regression_runs.c.regression_run_id == run_id,
                            regression_runs.c.claim_token == claim_token,
                        )
                    )
                    .values(
                        status=RegressionRunStatus.WAITING_FOR_EVALUATIONS.value,
                        available_at=datetime.now(UTC) + timedelta(seconds=1),
                        claimed_by=None,
                        claim_token=None,
                        lease_expires_at=None,
                    )
                )
                return bool(int(getattr(result, "rowcount", 0) or 0) == 1)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression wait state is unavailable") from exc

    def fail_run(self, project_id: str, run_id: UUID, claim_token: UUID, reason: str) -> bool:
        try:
            with self._sessions() as session, session.begin():
                result = session.execute(
                    update(regression_runs)
                    .where(
                        and_(
                            regression_runs.c.project_id == project_id,
                            regression_runs.c.regression_run_id == run_id,
                            regression_runs.c.claim_token == claim_token,
                        )
                    )
                    .values(
                        status=RegressionRunStatus.FAILED.value,
                        changed_dimensions={"error": reason},
                        finished_at=datetime.now(UTC),
                        claimed_by=None,
                        claim_token=None,
                        lease_expires_at=None,
                    )
                )
                return bool(int(getattr(result, "rowcount", 0) or 0) == 1)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression failure state is unavailable") from exc

    def required_evaluations(
        self, project_id: str, run_id: UUID
    ) -> tuple[tuple[UUID, str, Mapping[str, object]], ...]:
        run = self.get_run(project_id, run_id)
        plan = cast(Sequence[Mapping[str, object]], run["evaluation_plan"])
        if not plan:
            return ()
        trace_ids = self._run_trace_ids(project_id, run)
        if not trace_ids:
            return ()
        try:
            with self._sessions() as session:
                rows = session.execute(
                    select(
                        evaluation_results.c.trace_id,
                        evaluation_results.c.evaluation_type,
                        evaluation_results.c.config,
                    ).where(
                        and_(
                            evaluation_results.c.project_id == project_id,
                            evaluation_results.c.trace_id.in_(trace_ids),
                        )
                    )
                ).all()
                existing = {
                    (cast(UUID, row[0]), cast(str, row[1]), _config_key(row[2])) for row in rows
                }
                missing: list[tuple[UUID, str, Mapping[str, object]]] = []
                for trace_id in trace_ids:
                    for item in plan:
                        evaluation_type = item.get("evaluation_type")
                        if not isinstance(evaluation_type, str):
                            continue
                        config = item.get("config", {})
                        if not isinstance(config, Mapping):
                            continue
                        if (trace_id, evaluation_type, _config_key(config)) not in existing:
                            missing.append(
                                (trace_id, evaluation_type, cast(Mapping[str, object], config))
                            )
                return tuple(missing)
        except SQLAlchemyError as exc:
            raise RegressionStorageError("evaluation readiness is unavailable") from exc

    def comparison_data(self, project_id: str, run_id: UUID) -> dict[str, object]:
        run = self.get_run(project_id, run_id)
        baseline_id = _uuid(run["baseline_replay_run_id"])
        candidate_id = _uuid(run["candidate_replay_run_id"])
        try:
            with self._sessions() as session:
                case_rows = (
                    session.execute(
                        select(dataset_cases)
                        .where(
                            and_(
                                dataset_cases.c.project_id == project_id,
                                dataset_cases.c.dataset_version_id
                                == _uuid(run["dataset_version_id"]),
                            )
                        )
                        .order_by(dataset_cases.c.position)
                    )
                    .mappings()
                    .all()
                )
                executions = (
                    session.execute(
                        select(replay_case_executions).where(
                            and_(
                                replay_case_executions.c.project_id == project_id,
                                replay_case_executions.c.replay_run_id.in_(
                                    [baseline_id, candidate_id]
                                ),
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
                by_run_case = {
                    (cast(UUID, row["replay_run_id"]), cast(UUID, row["case_id"])): cast(
                        Mapping[str, object], row
                    )
                    for row in executions
                }
                trace_ids = [
                    cast(UUID, row["generated_trace_id"])
                    for row in executions
                    if row["generated_trace_id"] is not None
                ]
                trace_rows = (
                    session.execute(
                        select(traces).where(
                            and_(
                                traces.c.project_id == project_id, traces.c.trace_id.in_(trace_ids)
                            )
                        )
                    )
                    .mappings()
                    .all()
                    if trace_ids
                    else []
                )
                traces_by_id = {
                    cast(UUID, row["trace_id"]): cast(Mapping[str, object], row)
                    for row in trace_rows
                }
                evaluation_rows = (
                    session.execute(
                        select(evaluation_results).where(
                            and_(
                                evaluation_results.c.project_id == project_id,
                                evaluation_results.c.trace_id.in_(trace_ids),
                            )
                        )
                    )
                    .mappings()
                    .all()
                    if trace_ids
                    else []
                )
                result_ids = [cast(UUID, row["result_id"]) for row in evaluation_rows]
                invocation_rows = (
                    session.execute(
                        select(evaluation_judge_invocations).where(
                            and_(
                                evaluation_judge_invocations.c.project_id == project_id,
                                evaluation_judge_invocations.c.result_id.in_(result_ids),
                            )
                        )
                    )
                    .mappings()
                    .all()
                    if result_ids
                    else []
                )
                invocations_by_result: dict[UUID, list[Mapping[str, object]]] = {}
                for row in invocation_rows:
                    invocations_by_result.setdefault(cast(UUID, row["result_id"]), []).append(
                        cast(Mapping[str, object], row)
                    )
                evaluations_by_trace: dict[UUID, list[Mapping[str, object]]] = {}
                for row in evaluation_rows:
                    body = _row_dict(cast(Mapping[str, object], row))
                    body["judge_invocations"] = invocations_by_result.get(
                        cast(UUID, row["result_id"]), []
                    )
                    evaluations_by_trace.setdefault(cast(UUID, row["trace_id"]), []).append(body)
                cases: list[dict[str, object]] = []
                for case in case_rows:
                    case_id = cast(UUID, case["case_id"])
                    left = by_run_case.get((baseline_id, case_id))
                    right = by_run_case.get((candidate_id, case_id))
                    left_trace = (
                        traces_by_id.get(_uuid(left["generated_trace_id"]))
                        if left and left["generated_trace_id"]
                        else None
                    )
                    right_trace = (
                        traces_by_id.get(_uuid(right["generated_trace_id"]))
                        if right and right["generated_trace_id"]
                        else None
                    )
                    left_evals = (
                        evaluations_by_trace.get(_uuid(left["generated_trace_id"]), [])
                        if left and left["generated_trace_id"]
                        else []
                    )
                    right_evals = (
                        evaluations_by_trace.get(_uuid(right["generated_trace_id"]), [])
                        if right and right["generated_trace_id"]
                        else []
                    )
                    cases.append(
                        {
                            "case_id": case_id,
                            "position": case["position"],
                            "baseline_execution": left,
                            "candidate_execution": right,
                            "baseline_trace": left_trace,
                            "candidate_trace": right_trace,
                            "baseline_evaluations": left_evals,
                            "candidate_evaluations": right_evals,
                        }
                    )
                return {"run": run, "cases": cases}
        except SQLAlchemyError as exc:
            raise RegressionStorageError("comparison inputs are unavailable") from exc

    def persist_comparison(
        self,
        project_id: str,
        run_id: UUID,
        claim_token: UUID,
        result: Mapping[str, object],
    ) -> bool:
        now = datetime.now(UTC)
        try:
            with self._sessions() as session, session.begin():
                row = (
                    session.execute(
                        select(regression_runs)
                        .where(
                            and_(
                                regression_runs.c.project_id == project_id,
                                regression_runs.c.regression_run_id == run_id,
                                regression_runs.c.claim_token == claim_token,
                                regression_runs.c.status == RegressionRunStatus.RUNNING.value,
                            )
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return False
                session.execute(
                    delete(regression_metric_comparisons).where(
                        regression_metric_comparisons.c.regression_run_id == run_id
                    )
                )
                session.execute(
                    delete(regression_case_comparisons).where(
                        regression_case_comparisons.c.regression_run_id == run_id
                    )
                )
                for metric in cast(Sequence[Mapping[str, object]], result["metrics"]):
                    session.execute(
                        regression_metric_comparisons.insert().values(
                            comparison_id=uuid4(),
                            regression_run_id=run_id,
                            metric_id=metric["metric_id"],
                            rule_id=metric["rule_id"],
                            baseline_value=metric["baseline_value"],
                            candidate_value=metric["candidate_value"],
                            absolute_delta=metric["absolute_delta"],
                            relative_delta=metric["relative_delta"],
                            direction=metric["direction"],
                            baseline_samples=metric["baseline_samples"],
                            candidate_samples=metric["candidate_samples"],
                            paired_samples=metric["paired_samples"],
                            classification=metric["classification"],
                            candidate_limit_status=metric["candidate_limit_status"],
                            provenance=metric["provenance"],
                            details=metric["details"],
                            created_at=now,
                        )
                    )
                for case in cast(Sequence[Mapping[str, object]], result["cases"]):
                    session.execute(
                        regression_case_comparisons.insert().values(
                            case_comparison_id=uuid4(),
                            regression_run_id=run_id,
                            case_id=case["case_id"],
                            position=case["position"],
                            baseline_execution_id=case["baseline_execution_id"],
                            candidate_execution_id=case["candidate_execution_id"],
                            baseline_trace_id=case["baseline_trace_id"],
                            candidate_trace_id=case["candidate_trace_id"],
                            status=case["status"],
                            metric_comparisons=case["metric_comparisons"],
                            introduced_findings=case["introduced_findings"],
                            resolved_findings=case["resolved_findings"],
                            details=case["details"],
                            created_at=now,
                        )
                    )
                session.execute(
                    update(regression_runs)
                    .where(regression_runs.c.regression_run_id == run_id)
                    .values(
                        status=RegressionRunStatus.COMPLETED.value,
                        regression_count=result["regression_count"],
                        improvement_count=result["improvement_count"],
                        unchanged_count=result["unchanged_count"],
                        insufficient_data_count=result["insufficient_data_count"],
                        incompatible_count=result["incompatible_count"],
                        has_regressions=1
                        if result["regression_count"]
                        or any(
                            metric["candidate_limit_status"] == CandidateLimitStatus.VIOLATED.value
                            for metric in cast(Sequence[Mapping[str, object]], result["metrics"])
                        )
                        else 0,
                        finished_at=now,
                        claimed_by=None,
                        claim_token=None,
                        lease_expires_at=None,
                    )
                )
                return True
        except SQLAlchemyError as exc:
            raise RegressionStorageError("regression report storage is unavailable") from exc

    def _ensure_run(self, project_id: str, run_id: UUID) -> None:
        self.get_run(project_id, run_id)

    @staticmethod
    def _project_run(
        session: Session, project_id: str, run_id: UUID
    ) -> Mapping[str, object] | None:
        row = (
            session.execute(
                select(replay_runs).where(
                    and_(
                        replay_runs.c.project_id == project_id,
                        replay_runs.c.replay_run_id == run_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return cast(Mapping[str, object], row) if row is not None else None

    def _run_trace_ids(self, project_id: str, run: Mapping[str, object]) -> tuple[UUID, ...]:
        with self._sessions() as session:
            rows = (
                session.execute(
                    select(replay_case_executions.c.generated_trace_id).where(
                        and_(
                            replay_case_executions.c.project_id == project_id,
                            replay_case_executions.c.replay_run_id.in_(
                                [
                                    _uuid(run["baseline_replay_run_id"]),
                                    _uuid(run["candidate_replay_run_id"]),
                                ]
                            ),
                            replay_case_executions.c.generated_trace_id.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return tuple(cast(UUID, value) for value in rows)

    @staticmethod
    def _changed_dimensions(left: Mapping[str, object], right: Mapping[str, object]) -> list[str]:
        keys = {str(key) for key in left} | {str(key) for key in right}
        return sorted(
            key for key in keys if left.get(key) != right.get(key) and key != "created_at"
        )

    @staticmethod
    def _policy_dict(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "schema": row["schema_version"],
            "policy_id": str(row["policy_id"]),
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "version": row["version"],
            "rules": row["rules"],
            "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
        }

    @staticmethod
    def _run_dict(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "regression_run_id": str(row["regression_run_id"]),
            "project_id": row["project_id"],
            "report_schema_version": row["report_schema_version"],
            "baseline_replay_run_id": str(row["baseline_replay_run_id"]),
            "candidate_replay_run_id": str(row["candidate_replay_run_id"]),
            "dataset_id": str(row["dataset_id"]),
            "dataset_version_id": str(row["dataset_version_id"]),
            "dataset_checksum": row["dataset_checksum"],
            "policy_id": str(row["policy_id"]),
            "policy_version": row["policy_version"],
            "evaluation_plan": row["evaluation_plan"],
            "baseline_manifest": row["baseline_manifest"],
            "candidate_manifest": row["candidate_manifest"],
            "changed_dimensions": row["changed_dimensions"],
            "status": row["status"],
            "comparison_engine_version": row["comparison_engine_version"],
            "regression_count": row["regression_count"],
            "improvement_count": row["improvement_count"],
            "unchanged_count": row["unchanged_count"],
            "insufficient_data_count": row["insufficient_data_count"],
            "incompatible_count": row["incompatible_count"],
            "has_regressions": bool(row["has_regressions"]),
            "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
            "started_at": _utc(cast(datetime, row["started_at"])).isoformat()
            if row["started_at"]
            else None,
            "finished_at": _utc(cast(datetime, row["finished_at"])).isoformat()
            if row["finished_at"]
            else None,
        }

    @staticmethod
    def _metric_dict(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "comparison_id": str(row["comparison_id"]),
            "metric_id": row["metric_id"],
            "rule_id": row["rule_id"],
            "baseline_value": row["baseline_value"],
            "candidate_value": row["candidate_value"],
            "absolute_delta": row["absolute_delta"],
            "relative_delta": row["relative_delta"],
            "direction": row["direction"],
            "baseline_samples": row["baseline_samples"],
            "candidate_samples": row["candidate_samples"],
            "paired_samples": row["paired_samples"],
            "classification": row["classification"],
            "candidate_limit_status": row["candidate_limit_status"],
            "provenance": row["provenance"],
            "details": row["details"],
        }

    @staticmethod
    def _case_dict(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "case_comparison_id": str(row["case_comparison_id"]),
            "case_id": str(row["case_id"]),
            "position": row["position"],
            "baseline_execution_id": str(row["baseline_execution_id"])
            if row["baseline_execution_id"]
            else None,
            "candidate_execution_id": str(row["candidate_execution_id"])
            if row["candidate_execution_id"]
            else None,
            "baseline_trace_id": str(row["baseline_trace_id"])
            if row["baseline_trace_id"]
            else None,
            "candidate_trace_id": str(row["candidate_trace_id"])
            if row["candidate_trace_id"]
            else None,
            "status": row["status"],
            "metric_comparisons": row["metric_comparisons"],
            "introduced_findings": row["introduced_findings"],
            "resolved_findings": row["resolved_findings"],
            "details": row["details"],
        }


def build_comparison_result(
    data: Mapping[str, object], policy: RegressionPolicy
) -> dict[str, object]:
    """Build a deterministic report payload from one loaded comparison population."""

    cases = cast(Sequence[Mapping[str, object]], data["cases"])
    metrics: list[dict[str, object]] = []
    case_outputs: list[dict[str, object]] = []
    counts = {classification.value: 0 for classification in MetricClassification}
    for rule in policy.rules:
        definition = get_metric(rule.metric_id) if not rule.informational else None
        baseline_values: list[float] = []
        candidate_values: list[float] = []
        paired_values: list[tuple[float, float]] = []
        case_metric_values: list[tuple[Mapping[str, object], float | None, float | None]] = []
        incompatibility: str | None = None
        for case in cases:
            left_evals = cast(Sequence[Mapping[str, object]], case["baseline_evaluations"])
            right_evals = cast(Sequence[Mapping[str, object]], case["candidate_evaluations"])
            if definition is None:
                left_value = right_value = None
            else:
                left_value, _ = extract_case_value(
                    definition,
                    execution=cast(Mapping[str, object], case["baseline_execution"] or {}),
                    trace=cast(Mapping[str, object] | None, case["baseline_trace"]),
                    evaluations=left_evals,
                )
                right_value, _ = extract_case_value(
                    definition,
                    execution=cast(Mapping[str, object], case["candidate_execution"] or {}),
                    trace=cast(Mapping[str, object] | None, case["candidate_trace"]),
                    evaluations=right_evals,
                )
                compatible, reason = compatible_measurements(left_evals, right_evals, definition)
                if not compatible:
                    incompatibility = reason or "measurement provenance differs"
            case_metric_values.append((case, left_value, right_value))
            if left_value is not None:
                baseline_values.append(left_value)
            if right_value is not None:
                candidate_values.append(right_value)
            if left_value is not None and right_value is not None:
                paired_values.append((left_value, right_value))
        baseline_value = aggregate(baseline_values, definition.aggregation) if definition else None
        candidate_value = (
            aggregate(candidate_values, definition.aggregation) if definition else None
        )
        classification, explanation = _classify(
            rule,
            baseline_value,
            candidate_value,
            len(baseline_values),
            len(candidate_values),
            incompatibility,
        )
        absolute_delta = (
            candidate_value - baseline_value
            if baseline_value is not None and candidate_value is not None
            else None
        )
        relative_delta = (
            absolute_delta / abs(baseline_value)
            if absolute_delta is not None and baseline_value is not None and baseline_value != 0
            else None
        )
        limit_status = _limit_status(rule, candidate_value)
        paired_improved = paired_regressed = paired_unchanged = 0
        per_case: list[dict[str, object]] = []
        for case, left_value, right_value in case_metric_values:
            case_classification, _ = _classify(
                rule,
                left_value,
                right_value,
                int(left_value is not None),
                int(right_value is not None),
                incompatibility,
            )
            if case_classification == MetricClassification.IMPROVED.value:
                paired_improved += 1
            elif case_classification == MetricClassification.REGRESSED.value:
                paired_regressed += 1
            elif case_classification == MetricClassification.UNCHANGED.value:
                paired_unchanged += 1
            per_case.append(
                {
                    "case_id": str(case["case_id"]),
                    "baseline_value": left_value,
                    "candidate_value": right_value,
                    "classification": case_classification,
                }
            )
        provenance = _metric_provenance(rule, cases)
        metrics.append(
            {
                "metric_id": rule.metric_id,
                "rule_id": rule.rule_id,
                "baseline_value": baseline_value,
                "candidate_value": candidate_value,
                "absolute_delta": absolute_delta,
                "relative_delta": relative_delta,
                "direction": rule.direction.value if rule.direction else None,
                "baseline_samples": len(baseline_values),
                "candidate_samples": len(candidate_values),
                "paired_samples": len(paired_values),
                "classification": classification,
                "candidate_limit_status": limit_status,
                "provenance": provenance,
                "details": {
                    "explanation": explanation,
                    "cases_improved": paired_improved,
                    "cases_regressed": paired_regressed,
                    "cases_unchanged": paired_unchanged,
                    "per_case": per_case,
                    "unit": definition.unit if definition else "number",
                    "delta_semantics": (
                        "percentage_points"
                        if definition and definition.unit == "rate"
                        else definition.unit
                        if definition
                        else "number"
                    ),
                },
            }
        )
        if classification in counts:
            counts[classification] += 1
    for case_index, case in enumerate(cases):
        baseline_findings = finding_keys(
            cast(Sequence[Mapping[str, object]], case["baseline_evaluations"])
        )
        candidate_findings = finding_keys(
            cast(Sequence[Mapping[str, object]], case["candidate_evaluations"])
        )
        left = cast(Mapping[str, object] | None, case["baseline_execution"])
        right = cast(Mapping[str, object] | None, case["candidate_execution"])
        status = "compared"
        if right is None or right.get("status") != "succeeded":
            status = "candidate_execution_failed"
        elif left is None or left.get("status") != "succeeded":
            status = "baseline_execution_failed"
        case_metric_comparisons: list[Mapping[str, object]] = []
        for comparison in metrics:
            details = cast(Mapping[str, object], comparison["details"])
            case_per_metric = cast(Sequence[Mapping[str, object]], details["per_case"])
            if case_index < len(case_per_metric):
                case_metric_comparisons.append(case_per_metric[case_index])
        comparison_run = cast(Mapping[str, object], data["run"])
        case_outputs.append(
            {
                "case_id": case["case_id"],
                "position": case["position"],
                "baseline_execution_id": left.get("execution_id") if left else None,
                "candidate_execution_id": right.get("execution_id") if right else None,
                "baseline_trace_id": left.get("generated_trace_id") if left else None,
                "candidate_trace_id": right.get("generated_trace_id") if right else None,
                "status": status,
                "metric_comparisons": case_metric_comparisons,
                "introduced_findings": sorted(candidate_findings - baseline_findings),
                "resolved_findings": sorted(baseline_findings - candidate_findings),
                "details": {
                    "baseline_reproducibility": comparison_run["baseline_manifest"],
                    "candidate_reproducibility": comparison_run["candidate_manifest"],
                },
            }
        )
    return {
        "metrics": metrics,
        "cases": case_outputs,
        "regression_count": counts[MetricClassification.REGRESSED.value],
        "improvement_count": counts[MetricClassification.IMPROVED.value],
        "unchanged_count": counts[MetricClassification.UNCHANGED.value],
        "insufficient_data_count": counts[MetricClassification.INSUFFICIENT_DATA.value],
        "incompatible_count": counts[MetricClassification.INCOMPATIBLE.value],
    }


def _classify(
    rule: MetricRule,
    baseline: float | None,
    candidate: float | None,
    baseline_samples: int,
    candidate_samples: int,
    incompatibility: str | None,
) -> tuple[str, str]:
    if rule.informational:
        return (
            MetricClassification.INFORMATIONAL.value,
            "Informational metric; no rule classification requested.",
        )
    if incompatibility:
        return MetricClassification.INCOMPATIBLE.value, incompatibility
    if (
        baseline is None
        or candidate is None
        or baseline_samples < rule.minimum_samples
        or candidate_samples < rule.minimum_samples
    ):
        return (
            MetricClassification.INSUFFICIENT_DATA.value,
            "Metric is unavailable or below minimum sample count.",
        )
    absolute_tolerance = rule.absolute_tolerance or 0.0
    relative_tolerance = abs(baseline) * (rule.relative_tolerance or 0.0)
    tolerance = max(absolute_tolerance, relative_tolerance)
    if rule.direction == MetricDirection.HIGHER_IS_BETTER:
        if candidate < baseline - tolerance:
            classification = MetricClassification.REGRESSED.value
        elif candidate > baseline + tolerance:
            classification = MetricClassification.IMPROVED.value
        else:
            classification = MetricClassification.UNCHANGED.value
    else:
        if candidate > baseline + tolerance:
            classification = MetricClassification.REGRESSED.value
        elif candidate < baseline - tolerance:
            classification = MetricClassification.IMPROVED.value
        else:
            classification = MetricClassification.UNCHANGED.value
    explanation = (
        f"baseline={baseline}; candidate={candidate}; absolute_tolerance={absolute_tolerance}; "
        f"relative_tolerance={rule.relative_tolerance or 0.0}; classification={classification}"
    )
    return classification, explanation


def _limit_status(rule: MetricRule, candidate: float | None) -> str:
    if candidate is None or (rule.candidate_minimum is None and rule.candidate_maximum is None):
        return CandidateLimitStatus.NOT_CONFIGURED.value
    if rule.candidate_minimum is not None and candidate < rule.candidate_minimum:
        return CandidateLimitStatus.VIOLATED.value
    if rule.candidate_maximum is not None and candidate > rule.candidate_maximum:
        return CandidateLimitStatus.VIOLATED.value
    return CandidateLimitStatus.SATISFIED.value


def _metric_provenance(
    rule: MetricRule, cases: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    definition = get_metric(rule.metric_id) if not rule.informational else None
    if definition is None:
        return {"source": "informational"}
    if definition.source != "evaluation":
        return {"source": definition.source, "engine_version": COMPARISON_ENGINE_VERSION}
    values: list[Mapping[str, object]] = []
    for case in cases:
        values.extend(cast(Sequence[Mapping[str, object]], case["baseline_evaluations"]))
        values.extend(cast(Sequence[Mapping[str, object]], case["candidate_evaluations"]))
    first = values[0] if values else {}
    return {
        "source": definition.evaluator_type,
        "evaluator_name": first.get("evaluator_name"),
        "evaluator_version": first.get("evaluator_version"),
        "measurement_spec": "evaluator-defined",
        "judge_provenance": [
            {
                "provider": invocation.get("provider"),
                "model": invocation.get("model"),
                "adapter_version": invocation.get("adapter_version"),
                "prompt_version": invocation.get("prompt_version"),
                "parameters": invocation.get("parameters", {}),
            }
            for invocation in cast(
                Sequence[Mapping[str, object]], first.get("judge_invocations", [])
            )
        ],
    }


__all__ = [
    "ClaimedRegression",
    "PostgresRegressionRepository",
    "RegressionIdempotencyConflict",
    "RegressionImmutableError",
    "RegressionNotFoundError",
    "RegressionStorageError",
    "RegressionValidationError",
    "StaleRegressionClaim",
    "build_comparison_result",
    "request_fingerprint",
]
