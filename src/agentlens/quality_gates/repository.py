"""PostgreSQL persistence for immutable M11 policies and decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, create_engine, desc, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    quality_gate_decisions,
    quality_gate_policies,
    regression_case_comparisons,
    regression_metric_comparisons,
    regression_runs,
)

from .engine import evaluate_gate
from .models import (
    GATE_POLICY_SCHEMA_VERSION,
    GateSourceType,
    QualityGatePolicy,
)


class QualityGateStorageError(Exception):
    """Expected durable storage failure."""


class QualityGateNotFoundError(QualityGateStorageError):
    pass


class QualityGateValidationError(QualityGateStorageError):
    pass


class QualityGateIdempotencyConflict(QualityGateStorageError):
    pass


def request_fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _policy_body(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema": row["schema_version"],
        "gate_policy_id": str(row["gate_policy_id"]),
        "project_id": row["project_id"],
        "name": row["name"],
        "description": row["description"],
        "version": row["version"],
        "rules": row["rules"],
        "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
        "content_fingerprint": row["content_fingerprint"],
    }


def _decision_body(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "decision_id": str(row["gate_decision_id"]),
        "gate_decision_id": str(row["gate_decision_id"]),
        "project_id": row["project_id"],
        "regression_run_id": str(row["regression_run_id"]),
        "gate_policy_id": str(row["gate_policy_id"]),
        "gate_policy_version": row["gate_policy_version"],
        "gate_policy_fingerprint": row["gate_policy_fingerprint"],
        "decision_schema_version": row["decision_schema_version"],
        "status": row["status"],
        "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
        "completed_at": _utc(cast(datetime, row["completed_at"])).isoformat(),
        "blocking_failure_count": row["blocking_failure_count"],
        "advisory_failure_count": row["advisory_failure_count"],
        "indeterminate_count": row["indeterminate_count"],
        "blocking_failures": row["blocking_failure_count"],
        "advisories": row["advisory_failure_count"],
        "indeterminate": row["indeterminate_count"],
        "rule_results": row["rule_results"],
        "dataset_id": str(row["dataset_id"]),
        "dataset_version_id": str(row["dataset_version_id"]),
        "dataset_checksum": row["dataset_checksum"],
        "baseline_replay_run_id": str(row["baseline_replay_run_id"]),
        "candidate_replay_run_id": str(row["candidate_replay_run_id"]),
        "regression_report_schema": row["regression_report_schema"],
        "regression_report_fingerprint": row["regression_report_fingerprint"],
        "comparison_engine_version": row["comparison_engine_version"],
        "quality_gate_engine_version": row["quality_gate_engine_version"],
        "evaluation_fingerprint": row["evaluation_fingerprint"],
    }


class PostgresQualityGateRepository:
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
        self,
        project_id: str,
        name: str,
        description: str,
        raw_rules: object,
        required_metrics: object = None,
    ) -> dict[str, object]:
        try:
            body: dict[str, object] = {"rules": raw_rules}
            if required_metrics is not None:
                body["required_metrics"] = required_metrics
            policy = QualityGatePolicy.from_dict(
                body, project_id=project_id, name=name, description=description
            )
            self._validate_trusted_rules(policy)
        except (TypeError, ValueError) as exc:
            raise QualityGateValidationError(str(exc)) from exc
        try:
            with self._sessions() as session, session.begin():
                prior = session.execute(
                    select(func.max(quality_gate_policies.c.version)).where(
                        and_(
                            quality_gate_policies.c.project_id == project_id,
                            quality_gate_policies.c.name == name,
                        )
                    )
                ).scalar_one_or_none()
                version = int(prior or 0) + 1
                policy = QualityGatePolicy(
                    gate_policy_id=policy.gate_policy_id,
                    project_id=project_id,
                    name=name,
                    description=description,
                    version=version,
                    rules=policy.rules,
                    created_at=policy.created_at,
                )
                session.execute(
                    quality_gate_policies.insert().values(
                        gate_policy_id=policy.gate_policy_id,
                        project_id=project_id,
                        name=name,
                        description=description,
                        schema_version=GATE_POLICY_SCHEMA_VERSION,
                        version=version,
                        rules=[rule.to_dict() for rule in policy.rules],
                        content_fingerprint=policy.content_fingerprint(),
                        created_at=policy.created_at,
                    )
                )
        except IntegrityError as exc:
            raise QualityGateValidationError("quality gate policy version already exists") from exc
        except SQLAlchemyError as exc:
            raise QualityGateStorageError("quality gate policy storage is unavailable") from exc
        return self.get_policy(project_id, policy.gate_policy_id)

    @staticmethod
    def _validate_trusted_rules(policy: QualityGatePolicy) -> None:
        from agentlens.regression.metric_registry import get_metric

        for rule in policy.rules:
            if rule.source_type in {
                GateSourceType.METRIC_CLASSIFICATION,
                GateSourceType.CANDIDATE_LIMIT,
                GateSourceType.REQUIRED_METRIC_AVAILABILITY,
            }:
                assert rule.metric_id is not None
                get_metric(rule.metric_id)
            if rule.source_type is GateSourceType.REGRESSION_COUNT:
                for metric_id in rule.metric_ids:
                    get_metric(metric_id)

    def list_policies(self, project_id: str, limit: int = 100) -> tuple[dict[str, object], ...]:
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(quality_gate_policies)
                        .where(quality_gate_policies.c.project_id == project_id)
                        .order_by(
                            desc(quality_gate_policies.c.created_at),
                            desc(quality_gate_policies.c.version),
                        )
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                return tuple(_policy_body(cast(Mapping[str, object], row)) for row in rows)
        except SQLAlchemyError as exc:
            raise QualityGateStorageError("quality gate policy storage is unavailable") from exc

    def get_policy(self, project_id: str, policy_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(quality_gate_policies).where(
                            and_(
                                quality_gate_policies.c.project_id == project_id,
                                quality_gate_policies.c.gate_policy_id == policy_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise QualityGateNotFoundError("quality gate policy not found")
                return _policy_body(cast(Mapping[str, object], row))
        except QualityGateNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise QualityGateStorageError("quality gate policy storage is unavailable") from exc

    def create_decision(
        self,
        *,
        project_id: str,
        regression_run_id: UUID,
        gate_policy_id: UUID,
        idempotency_key: str | None,
        request_fingerprint_value: str,
    ) -> dict[str, object]:
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest() if idempotency_key else None
        try:
            with self._sessions() as session, session.begin():
                policy_row = (
                    session.execute(
                        select(quality_gate_policies).where(
                            and_(
                                quality_gate_policies.c.project_id == project_id,
                                quality_gate_policies.c.gate_policy_id == gate_policy_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                run_row = (
                    session.execute(
                        select(regression_runs).where(
                            and_(
                                regression_runs.c.project_id == project_id,
                                regression_runs.c.regression_run_id == regression_run_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if policy_row is None or run_row is None:
                    raise QualityGateNotFoundError("quality gate resource not found")
                if key_hash is not None:
                    existing = (
                        session.execute(
                            select(quality_gate_decisions)
                            .where(
                                and_(
                                    quality_gate_decisions.c.project_id == project_id,
                                    quality_gate_decisions.c.idempotency_key_hash == key_hash,
                                )
                            )
                            .with_for_update()
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if existing is not None:
                        if existing["request_fingerprint"] != request_fingerprint_value:
                            raise QualityGateIdempotencyConflict(
                                "quality gate idempotency key conflicts"
                            )
                        duplicate = _decision_body(cast(Mapping[str, object], existing))
                        duplicate["_duplicate"] = True
                        return duplicate
                if run_row["status"] != "completed":
                    raise QualityGateValidationError(
                        "regression report is not complete; quality gate evaluation is not ready"
                    )
                metric_rows = (
                    session.execute(
                        select(regression_metric_comparisons)
                        .where(
                            regression_metric_comparisons.c.regression_run_id == regression_run_id
                        )
                        .order_by(regression_metric_comparisons.c.metric_id)
                    )
                    .mappings()
                    .all()
                )
                case_rows = (
                    session.execute(
                        select(regression_case_comparisons)
                        .where(regression_case_comparisons.c.regression_run_id == regression_run_id)
                        .order_by(regression_case_comparisons.c.position)
                    )
                    .mappings()
                    .all()
                )
                run = self._run_body(cast(Mapping[str, object], run_row))
                metrics = [
                    self._metric_body(cast(Mapping[str, object], row)) for row in metric_rows
                ]
                cases = [
                    {"case_id": str(row["case_id"]), "status": row["status"]} for row in case_rows
                ]
                policy = QualityGatePolicy.from_dict(
                    {"rules": policy_row["rules"]},
                    gate_policy_id=_uuid(policy_row["gate_policy_id"]),
                    project_id=project_id,
                    name=str(policy_row["name"]),
                    description=str(policy_row["description"]),
                    version=int(cast(Any, policy_row["version"])),
                    created_at=cast(datetime, policy_row["created_at"]),
                )
                self._validate_trusted_rules(policy)
                decision = evaluate_gate({"run": run, "metrics": metrics, "cases": cases}, policy)
                values = {
                    "gate_decision_id": _uuid(decision["gate_decision_id"]),
                    "project_id": project_id,
                    "regression_run_id": regression_run_id,
                    "gate_policy_id": gate_policy_id,
                    "gate_policy_version": decision["gate_policy_version"],
                    "gate_policy_fingerprint": decision["gate_policy_fingerprint"],
                    "decision_schema_version": decision["decision_schema_version"],
                    "status": decision["status"],
                    "created_at": datetime.fromisoformat(str(decision["created_at"])),
                    "completed_at": datetime.fromisoformat(str(decision["completed_at"])),
                    "blocking_failure_count": decision["blocking_failure_count"],
                    "advisory_failure_count": decision["advisory_failure_count"],
                    "indeterminate_count": decision["indeterminate_count"],
                    "rule_results": decision["rule_results"],
                    "dataset_id": _uuid(run["dataset_id"]),
                    "dataset_version_id": _uuid(run["dataset_version_id"]),
                    "dataset_checksum": run["dataset_checksum"],
                    "baseline_replay_run_id": _uuid(run["baseline_replay_run_id"]),
                    "candidate_replay_run_id": _uuid(run["candidate_replay_run_id"]),
                    "regression_report_schema": run["report_schema_version"],
                    "regression_report_fingerprint": decision["regression_report_fingerprint"],
                    "comparison_engine_version": run["comparison_engine_version"],
                    "quality_gate_engine_version": decision["quality_gate_engine_version"],
                    "evaluation_fingerprint": decision["evaluation_fingerprint"],
                    "idempotency_key_hash": key_hash,
                    "request_fingerprint": request_fingerprint_value if key_hash else None,
                }
                session.execute(quality_gate_decisions.insert().values(**values))
                created = (
                    session.execute(
                        select(quality_gate_decisions).where(
                            quality_gate_decisions.c.gate_decision_id == values["gate_decision_id"]
                        )
                    )
                    .mappings()
                    .one()
                )
                body = _decision_body(cast(Mapping[str, object], created))
                body["_duplicate"] = False
                return body
        except (
            QualityGateNotFoundError,
            QualityGateValidationError,
            QualityGateIdempotencyConflict,
        ):
            raise
        except IntegrityError as exc:
            raise QualityGateStorageError("quality gate decision could not be created") from exc
        except SQLAlchemyError as exc:
            raise QualityGateStorageError("quality gate decision storage is unavailable") from exc

    def get_decision(self, project_id: str, decision_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(quality_gate_decisions).where(
                            and_(
                                quality_gate_decisions.c.project_id == project_id,
                                quality_gate_decisions.c.gate_decision_id == decision_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise QualityGateNotFoundError("quality gate decision not found")
                return _decision_body(cast(Mapping[str, object], row))
        except QualityGateNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise QualityGateStorageError("quality gate decision storage is unavailable") from exc

    def list_decisions(
        self,
        project_id: str,
        *,
        limit: int = 100,
        status: str | None = None,
        policy_id: UUID | None = None,
        regression_run_id: UUID | None = None,
    ) -> tuple[dict[str, object], ...]:
        try:
            with self._sessions() as session:
                conditions = [quality_gate_decisions.c.project_id == project_id]
                if status is not None:
                    conditions.append(quality_gate_decisions.c.status == status)
                if policy_id is not None:
                    conditions.append(quality_gate_decisions.c.gate_policy_id == policy_id)
                if regression_run_id is not None:
                    conditions.append(
                        quality_gate_decisions.c.regression_run_id == regression_run_id
                    )
                rows = (
                    session.execute(
                        select(quality_gate_decisions)
                        .where(and_(*conditions))
                        .order_by(
                            desc(quality_gate_decisions.c.created_at),
                            desc(quality_gate_decisions.c.gate_decision_id),
                        )
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                return tuple(_decision_body(cast(Mapping[str, object], row)) for row in rows)
        except SQLAlchemyError as exc:
            raise QualityGateStorageError("quality gate decision storage is unavailable") from exc

    @staticmethod
    def _run_body(row: Mapping[str, object]) -> dict[str, object]:
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
            "baseline_manifest": row["baseline_manifest"],
            "candidate_manifest": row["candidate_manifest"],
            "status": row["status"],
            "comparison_engine_version": row["comparison_engine_version"],
            "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
            "finished_at": _utc(cast(datetime, row["finished_at"])).isoformat()
            if row["finished_at"]
            else None,
        }

    @staticmethod
    def _metric_body(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "comparison_id": str(row["comparison_id"]),
            "metric_id": row["metric_id"],
            "rule_id": row["rule_id"],
            "baseline_value": row["baseline_value"],
            "candidate_value": row["candidate_value"],
            "absolute_delta": row["absolute_delta"],
            "relative_delta": row["relative_delta"],
            "classification": row["classification"],
            "candidate_limit_status": row["candidate_limit_status"],
            "baseline_samples": row["baseline_samples"],
            "candidate_samples": row["candidate_samples"],
            "provenance": row["provenance"],
        }


__all__ = [
    "PostgresQualityGateRepository",
    "QualityGateIdempotencyConflict",
    "QualityGateNotFoundError",
    "QualityGateStorageError",
    "QualityGateValidationError",
    "request_fingerprint",
]
