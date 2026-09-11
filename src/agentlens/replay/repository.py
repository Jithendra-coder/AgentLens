"""PostgreSQL-authoritative dataset and replay ledger."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, desc, func, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from agentlens.domain import JSONValue
from agentlens.domain.types import validate_json_value
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import (
    dataset_cases,
    dataset_versions,
    datasets,
    replay_attempts,
    replay_case_executions,
    replay_runs,
)

from .models import (
    DatasetCase,
    DatasetVersionStatus,
    ReplayManifest,
    ReplayRunStatus,
    canonical_case_checksum,
)


class ReplayStorageError(Exception):
    """Expected durable storage failure."""


class ReplayNotFoundError(ReplayStorageError):
    pass


class ReplayImmutableError(ReplayStorageError):
    pass


class ReplayIdempotencyConflict(ReplayStorageError):
    pass


class ReplayValidationError(ReplayStorageError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json(value: object, field_name: str) -> JSONValue:
    validate_json_value(value, field_name)
    return cast(JSONValue, value)


def request_fingerprint(value: Mapping[str, object]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def hash_idempotency_key(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None


def _case(row: Any) -> DatasetCase:
    return DatasetCase(
        case_id=cast(UUID, row["case_id"]),
        name=cast(str, row["name"]),
        input=cast(JSONValue, row["input"]),
        metadata=cast(Mapping[str, JSONValue], row["metadata"]),
        source=cast(Mapping[str, JSONValue], row["source"]),
        ground_truth=cast(JSONValue | None, row["ground_truth"]),
        tags=tuple(cast(list[str], row["tags"])),
        position=cast(int, row["position"]),
    )


def _case_body(value: DatasetCase) -> dict[str, object]:
    return cast(dict[str, object], value.to_dict())


@dataclass(frozen=True, slots=True)
class ReplayCreation:
    run: dict[str, object]
    execution_ids: tuple[UUID, ...]
    duplicate: bool


@dataclass(frozen=True, slots=True)
class ClaimedExecution:
    execution: dict[str, object]
    run: dict[str, object]
    case: DatasetCase
    claim_token: UUID
    attempt_number: int


class PostgresReplayRepository:
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

    def check_ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(select(func.now()))
            return True
        except SQLAlchemyError:
            return False

    def dispose(self) -> None:
        self.engine.dispose()

    def create_dataset(self, project_id: str, name: str, description: str) -> dict[str, object]:
        now = datetime.now(UTC)
        dataset_id = uuid4()
        try:
            with self._sessions() as session, session.begin():
                session.execute(
                    datasets.insert().values(
                        dataset_id=dataset_id,
                        project_id=project_id,
                        name=name,
                        description=description,
                        created_at=now,
                        updated_at=now,
                    )
                )
        except IntegrityError as exc:
            raise ReplayValidationError("dataset name already exists") from exc
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc
        return self.get_dataset(project_id, dataset_id)

    def list_datasets(self, project_id: str) -> tuple[dict[str, object], ...]:
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(datasets)
                        .where(datasets.c.project_id == project_id)
                        .order_by(desc(datasets.c.updated_at))
                    )
                    .mappings()
                    .all()
                )
                result: list[dict[str, object]] = []
                for row in rows:
                    latest = (
                        session.execute(
                            select(dataset_versions)
                            .where(dataset_versions.c.dataset_id == row["dataset_id"])
                            .order_by(desc(dataset_versions.c.version_number))
                            .limit(1)
                        )
                        .mappings()
                        .one_or_none()
                    )
                    result.append(self._dataset_dict(row, latest))
                return tuple(result)
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc

    def get_dataset(self, project_id: str, dataset_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(datasets).where(
                            and_(
                                datasets.c.dataset_id == dataset_id,
                                datasets.c.project_id == project_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ReplayNotFoundError("dataset not found")
                versions = (
                    session.execute(
                        select(dataset_versions)
                        .where(dataset_versions.c.dataset_id == dataset_id)
                        .order_by(desc(dataset_versions.c.version_number))
                    )
                    .mappings()
                    .all()
                )
                body = self._dataset_dict(row, versions[0] if versions else None)
                body["versions"] = [self._version_dict(version) for version in versions]
                return body
        except ReplayNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc

    def update_dataset(
        self, project_id: str, dataset_id: UUID, name: str, description: str
    ) -> dict[str, object]:
        try:
            with self._sessions() as session, session.begin():
                result = session.execute(
                    update(datasets)
                    .where(
                        and_(
                            datasets.c.dataset_id == dataset_id, datasets.c.project_id == project_id
                        )
                    )
                    .values(name=name, description=description, updated_at=datetime.now(UTC))
                )
                if int(cast(Any, result).rowcount or 0) != 1:
                    raise ReplayNotFoundError("dataset not found")
        except ReplayNotFoundError:
            raise
        except IntegrityError as exc:
            raise ReplayValidationError("dataset name already exists") from exc
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc
        return self.get_dataset(project_id, dataset_id)

    def create_draft_version(
        self, project_id: str, dataset_id: UUID, source_metadata: Mapping[str, JSONValue]
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        _json(dict(source_metadata), "source_metadata")
        try:
            with self._sessions() as session, session.begin():
                dataset = (
                    session.execute(
                        select(datasets).where(
                            and_(
                                datasets.c.dataset_id == dataset_id,
                                datasets.c.project_id == project_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if dataset is None:
                    raise ReplayNotFoundError("dataset not found")
                latest = session.execute(
                    select(func.max(dataset_versions.c.version_number)).where(
                        dataset_versions.c.dataset_id == dataset_id
                    )
                ).scalar_one()
                version = int(latest or 0) + 1
                version_id = uuid4()
                session.execute(
                    dataset_versions.insert().values(
                        dataset_version_id=version_id,
                        dataset_id=dataset_id,
                        project_id=project_id,
                        version_number=version,
                        status=DatasetVersionStatus.DRAFT.value,
                        source_metadata=dict(source_metadata),
                        case_count=0,
                        content_checksum=None,
                        created_at=now,
                        finalized_at=None,
                    )
                )
        except ReplayNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc
        return self.get_version(project_id, version_id)

    def get_version(self, project_id: str, version_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(dataset_versions).where(
                            and_(
                                dataset_versions.c.dataset_version_id == version_id,
                                dataset_versions.c.project_id == project_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ReplayNotFoundError("dataset version not found")
                case_rows = (
                    session.execute(
                        select(dataset_cases)
                        .where(dataset_cases.c.dataset_version_id == version_id)
                        .order_by(dataset_cases.c.position)
                    )
                    .mappings()
                    .all()
                )
                body = self._version_dict(row)
                body["cases"] = [_case_body(_case(case_row)) for case_row in case_rows]
                return body
        except ReplayNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc

    def add_case(
        self,
        project_id: str,
        version_id: UUID,
        *,
        case_id: UUID | None = None,
        name: str,
        input_value: JSONValue,
        metadata: Mapping[str, JSONValue],
        source: Mapping[str, JSONValue],
        ground_truth: JSONValue | None,
        tags: Sequence[str],
    ) -> DatasetCase:
        validate_json_value(input_value, "input")
        case = DatasetCase(
            case_id=case_id or uuid4(),
            name=name,
            input=input_value,
            metadata=metadata,
            source=source,
            ground_truth=ground_truth,
            tags=tuple(tags),
            position=0,
        )
        try:
            with self._sessions() as session, session.begin():
                version = (
                    session.execute(
                        select(dataset_versions)
                        .where(
                            and_(
                                dataset_versions.c.dataset_version_id == version_id,
                                dataset_versions.c.project_id == project_id,
                            )
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if version is None:
                    raise ReplayNotFoundError("dataset version not found")
                if version["status"] != DatasetVersionStatus.DRAFT.value:
                    raise ReplayImmutableError("finalized dataset versions are immutable")
                max_position = session.execute(
                    select(func.max(dataset_cases.c.position)).where(
                        dataset_cases.c.dataset_version_id == version_id
                    )
                ).scalar_one()
                position = (int(max_position) if max_position is not None else -1) + 1
                case = DatasetCase(
                    case_id=case.case_id,
                    name=case.name,
                    input=case.input,
                    metadata=case.metadata,
                    source=case.source,
                    ground_truth=case.ground_truth,
                    tags=case.tags,
                    position=position,
                )
                session.execute(
                    dataset_cases.insert().values(
                        case_id=case.case_id,
                        dataset_version_id=version_id,
                        project_id=project_id,
                        position=position,
                        name=case.name,
                        input=case.input,
                        metadata=dict(case.metadata),
                        source=dict(case.source),
                        ground_truth=case.ground_truth,
                        tags=list(case.tags),
                    )
                )
                session.execute(
                    update(dataset_versions)
                    .where(dataset_versions.c.dataset_version_id == version_id)
                    .values(case_count=position + 1)
                )
        except (ReplayNotFoundError, ReplayImmutableError):
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc
        return case

    def update_case(
        self,
        project_id: str,
        version_id: UUID,
        case_id: UUID,
        values: Mapping[str, object],
    ) -> DatasetCase:
        allowed = {"name", "input", "metadata", "source", "ground_truth", "tags"}
        if any(key not in allowed for key in values):
            raise ReplayValidationError("unsupported case field")
        try:
            with self._sessions() as session, session.begin():
                version = session.execute(
                    select(dataset_versions.c.status).where(
                        and_(
                            dataset_versions.c.dataset_version_id == version_id,
                            dataset_versions.c.project_id == project_id,
                        )
                    )
                ).scalar_one_or_none()
                if version is None:
                    raise ReplayNotFoundError("dataset version not found")
                if version != DatasetVersionStatus.DRAFT.value:
                    raise ReplayImmutableError("finalized dataset versions are immutable")
                row = (
                    session.execute(
                        select(dataset_cases).where(
                            and_(
                                dataset_cases.c.case_id == case_id,
                                dataset_cases.c.dataset_version_id == version_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ReplayNotFoundError("dataset case not found")
                current = _case(row).to_dict()
                current.update(cast(Mapping[str, JSONValue], values))
                updated = DatasetCase(
                    case_id=case_id,
                    name=cast(str, current["name"]),
                    input=current["input"],
                    metadata=cast(Mapping[str, JSONValue], current["metadata"]),
                    source=cast(Mapping[str, JSONValue], current["source"]),
                    ground_truth=current["ground_truth"],
                    tags=tuple(cast(list[str], current["tags"])),
                    position=cast(int, current["position"]),
                )
                session.execute(
                    update(dataset_cases)
                    .where(dataset_cases.c.case_id == case_id)
                    .values(
                        name=updated.name,
                        input=updated.input,
                        metadata=dict(updated.metadata),
                        source=dict(updated.source),
                        ground_truth=updated.ground_truth,
                        tags=list(updated.tags),
                    )
                )
        except (ReplayNotFoundError, ReplayImmutableError, ReplayValidationError, ValueError):
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc
        return updated

    def remove_case(self, project_id: str, version_id: UUID, case_id: UUID) -> None:
        try:
            with self._sessions() as session, session.begin():
                version = session.execute(
                    select(dataset_versions.c.status).where(
                        and_(
                            dataset_versions.c.dataset_version_id == version_id,
                            dataset_versions.c.project_id == project_id,
                        )
                    )
                ).scalar_one_or_none()
                if version is None:
                    raise ReplayNotFoundError("dataset version not found")
                if version != DatasetVersionStatus.DRAFT.value:
                    raise ReplayImmutableError("finalized dataset versions are immutable")
                result = session.execute(
                    dataset_cases.delete().where(
                        and_(
                            dataset_cases.c.case_id == case_id,
                            dataset_cases.c.dataset_version_id == version_id,
                        )
                    )
                )
                if int(cast(Any, result).rowcount or 0) != 1:
                    raise ReplayNotFoundError("dataset case not found")
                count = session.execute(
                    select(func.count())
                    .select_from(dataset_cases)
                    .where(dataset_cases.c.dataset_version_id == version_id)
                ).scalar_one()
                session.execute(
                    update(dataset_versions)
                    .where(dataset_versions.c.dataset_version_id == version_id)
                    .values(case_count=count)
                )
        except (ReplayNotFoundError, ReplayImmutableError):
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc

    def finalize_version(self, project_id: str, version_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session, session.begin():
                version = (
                    session.execute(
                        select(dataset_versions)
                        .where(
                            and_(
                                dataset_versions.c.dataset_version_id == version_id,
                                dataset_versions.c.project_id == project_id,
                            )
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if version is None:
                    raise ReplayNotFoundError("dataset version not found")
                if version["status"] != DatasetVersionStatus.DRAFT.value:
                    return self.get_version(project_id, version_id)
                rows = (
                    session.execute(
                        select(dataset_cases)
                        .where(dataset_cases.c.dataset_version_id == version_id)
                        .order_by(dataset_cases.c.position)
                    )
                    .mappings()
                    .all()
                )
                cases = tuple(_case(row) for row in rows)
                checksum = canonical_case_checksum(cases)
                session.execute(
                    update(dataset_versions)
                    .where(dataset_versions.c.dataset_version_id == version_id)
                    .values(
                        status=DatasetVersionStatus.FINALIZED.value,
                        case_count=len(cases),
                        content_checksum=checksum,
                        finalized_at=datetime.now(UTC),
                    )
                )
        except (ReplayNotFoundError, ReplayImmutableError):
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("dataset storage is unavailable") from exc
        return self.get_version(project_id, version_id)

    def export_version(self, project_id: str, version_id: UUID) -> dict[str, object]:
        version = self.get_version(project_id, version_id)
        if version["status"] != DatasetVersionStatus.FINALIZED.value:
            raise ReplayValidationError("only finalized versions can be exported")
        return {
            "schema": "agentlens-dataset-v1",
            "dataset": {
                "dataset_id": version["dataset_id"],
                "project_id": project_id,
            },
            "version": {
                "version_number": version["version_number"],
                "source_metadata": version["source_metadata"],
                "case_count": version["case_count"],
                "content_checksum": version["content_checksum"],
            },
            "cases": version["cases"],
        }

    def import_version(
        self, project_id: str, dataset_id: UUID, payload: Mapping[str, object]
    ) -> dict[str, object]:
        if payload.get("schema") != "agentlens-dataset-v1":
            raise ReplayValidationError("unsupported dataset schema")
        cases_value = payload.get("cases")
        version_value = payload.get("version")
        if not isinstance(cases_value, list) or not isinstance(version_value, Mapping):
            raise ReplayValidationError("dataset export is malformed")
        seen: set[UUID] = set()
        parsed: list[DatasetCase] = []
        for raw in cases_value:
            if not isinstance(raw, Mapping):
                raise ReplayValidationError("dataset case is malformed")
            try:
                case_id = UUID(str(raw["case_id"]))
                if case_id in seen:
                    raise ReplayValidationError("dataset export contains duplicate case IDs")
                seen.add(case_id)
                parsed.append(
                    DatasetCase(
                        case_id=case_id,
                        name=cast(str, raw["name"]),
                        input=cast(JSONValue, raw["input"]),
                        metadata=cast(Mapping[str, JSONValue], raw.get("metadata", {})),
                        source=cast(Mapping[str, JSONValue], raw.get("source", {})),
                        ground_truth=cast(JSONValue | None, raw.get("ground_truth")),
                        tags=tuple(cast(list[str], raw.get("tags", []))),
                        position=int(raw["position"]),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ReplayValidationError("dataset export contains an invalid case") from exc
        parsed.sort(key=lambda item: item.position)
        if [item.position for item in parsed] != list(range(len(parsed))):
            raise ReplayValidationError("dataset case ordering is invalid")
        supplied = version_value.get("content_checksum")
        checksum = canonical_case_checksum(parsed)
        if supplied is not None and supplied != checksum:
            raise ReplayValidationError("dataset checksum is corrupt")
        draft = self.create_draft_version(
            project_id,
            dataset_id,
            cast(Mapping[str, JSONValue], version_value.get("source_metadata", {})),
        )
        for item in parsed:
            self.add_case(
                project_id,
                cast(UUID, draft["dataset_version_id"]),
                name=item.name,
                input_value=item.input,
                metadata=item.metadata,
                source=item.source,
                ground_truth=item.ground_truth,
                tags=item.tags,
            )
        return self.get_version(project_id, cast(UUID, draft["dataset_version_id"]))

    def create_replay(
        self,
        *,
        project_id: str,
        version_id: UUID,
        target_profile_id: str,
        target_name: str,
        target_type: str,
        target_version: str,
        manifest: ReplayManifest,
        max_concurrency: int,
        timeout_seconds: float,
        max_attempts: int,
        idempotency_key: str | None,
        request_fingerprint_value: str,
    ) -> ReplayCreation:
        key_hash = hash_idempotency_key(idempotency_key)
        now = datetime.now(UTC)
        try:
            with self._sessions() as session, session.begin():
                version = (
                    session.execute(
                        select(dataset_versions).where(
                            and_(
                                dataset_versions.c.dataset_version_id == version_id,
                                dataset_versions.c.project_id == project_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if version is None or version["status"] != DatasetVersionStatus.FINALIZED.value:
                    raise ReplayNotFoundError("finalized dataset version not found")
                if version["content_checksum"] != manifest.dataset_checksum:
                    raise ReplayValidationError("dataset checksum does not match finalized version")
                if key_hash is not None:
                    existing = (
                        session.execute(
                            select(replay_runs).where(
                                and_(
                                    replay_runs.c.project_id == project_id,
                                    replay_runs.c.idempotency_key_hash == key_hash,
                                )
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if existing is not None:
                        if existing["request_fingerprint"] != request_fingerprint_value:
                            raise ReplayIdempotencyConflict("idempotency key conflicts")
                        existing_execution_ids = tuple(
                            cast(UUID, item)
                            for item in session.execute(
                                select(replay_case_executions.c.execution_id)
                                .where(
                                    replay_case_executions.c.replay_run_id
                                    == existing["replay_run_id"]
                                )
                                .order_by(replay_case_executions.c.position)
                            )
                            .scalars()
                            .all()
                        )
                        return ReplayCreation(
                            self._run_dict(existing), existing_execution_ids, True
                        )
                cases = (
                    session.execute(
                        select(dataset_cases)
                        .where(dataset_cases.c.dataset_version_id == version_id)
                        .order_by(dataset_cases.c.position)
                    )
                    .mappings()
                    .all()
                )
                run_id = uuid4()
                run_values = {
                    "replay_run_id": run_id,
                    "project_id": project_id,
                    "dataset_id": version["dataset_id"],
                    "dataset_version_id": version_id,
                    "dataset_checksum": manifest.dataset_checksum,
                    "target_profile_id": target_profile_id,
                    "target_name": target_name,
                    "target_type": target_type,
                    "target_version": target_version,
                    "replay_mode": manifest.replay_mode.value,
                    "reproducibility_status": manifest.reproducibility_status.value,
                    "status": ReplayRunStatus.QUEUED.value,
                    "manifest": manifest.to_dict(),
                    "max_concurrency": max_concurrency,
                    "timeout_seconds": timeout_seconds,
                    "max_attempts": max_attempts,
                    "case_count": len(cases),
                    "completed_count": 0,
                    "succeeded_count": 0,
                    "failed_count": 0,
                    "idempotency_key_hash": key_hash,
                    "request_fingerprint": request_fingerprint_value if key_hash else None,
                    "created_at": now,
                    "started_at": None,
                    "finished_at": None,
                }
                session.execute(replay_runs.insert().values(**run_values))
                execution_ids: list[UUID] = []
                for case_row in cases:
                    execution_id = uuid4()
                    execution_ids.append(execution_id)
                    session.execute(
                        replay_case_executions.insert().values(
                            execution_id=execution_id,
                            project_id=project_id,
                            replay_run_id=run_id,
                            case_id=case_row["case_id"],
                            position=case_row["position"],
                            status="queued",
                            available_at=now,
                            started_at=None,
                            finished_at=None,
                            attempt_count=0,
                            claimed_by=None,
                            claim_token=None,
                            lease_expires_at=None,
                            target_request_fingerprint=None,
                            target_response_fingerprint=None,
                            output=None,
                            safe_error=None,
                            generated_trace_id=None,
                        )
                    )
                return ReplayCreation(self._run_dict(run_values), tuple(execution_ids), False)
        except (ReplayNotFoundError, ReplayValidationError, ReplayIdempotencyConflict):
            raise
        except IntegrityError as exc:
            raise ReplayIdempotencyConflict("idempotency key conflicts") from exc
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def list_runs(self, project_id: str, limit: int = 100) -> tuple[dict[str, object], ...]:
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(replay_runs)
                        .where(replay_runs.c.project_id == project_id)
                        .order_by(desc(replay_runs.c.created_at))
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
                return tuple(self._run_dict(row) for row in rows)
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def get_run(self, project_id: str, run_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(replay_runs).where(
                            and_(
                                replay_runs.c.replay_run_id == run_id,
                                replay_runs.c.project_id == project_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ReplayNotFoundError("replay run not found")
                body = self._run_dict(row)
                body["executions"] = [
                    self._execution_dict(item)
                    for item in session.execute(
                        select(replay_case_executions)
                        .where(replay_case_executions.c.replay_run_id == run_id)
                        .order_by(replay_case_executions.c.position)
                    )
                    .mappings()
                    .all()
                ]
                return body
        except ReplayNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def get_execution(self, project_id: str, run_id: UUID, execution_id: UUID) -> dict[str, object]:
        try:
            with self._sessions() as session:
                row = (
                    session.execute(
                        select(replay_case_executions).where(
                            and_(
                                replay_case_executions.c.execution_id == execution_id,
                                replay_case_executions.c.replay_run_id == run_id,
                                replay_case_executions.c.project_id == project_id,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise ReplayNotFoundError("replay execution not found")
                body = self._execution_dict(row)
                body["attempts"] = [
                    dict(item)
                    for item in session.execute(
                        select(replay_attempts)
                        .where(replay_attempts.c.execution_id == execution_id)
                        .order_by(replay_attempts.c.attempt_number)
                    )
                    .mappings()
                    .all()
                ]
                return body
        except ReplayNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def dispatchable_execution_ids(self, *, now: datetime, limit: int) -> tuple[UUID, ...]:
        current = _utc(now)
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        select(replay_case_executions.c.execution_id)
                        .where(
                            or_(
                                and_(
                                    replay_case_executions.c.status.in_(["queued", "retry_wait"]),
                                    replay_case_executions.c.available_at <= current,
                                ),
                                and_(
                                    replay_case_executions.c.status == "running",
                                    replay_case_executions.c.lease_expires_at <= current,
                                ),
                            )
                        )
                        .order_by(
                            replay_case_executions.c.available_at, replay_case_executions.c.position
                        )
                        .limit(limit)
                    )
                    .scalars()
                    .all()
                )
                return tuple(cast(UUID, value) for value in rows)
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def claim_execution(
        self, execution_id: UUID, worker_id: str, now: datetime, lease_seconds: float
    ) -> ClaimedExecution | None:
        current = _utc(now)
        try:
            with self._sessions() as session, session.begin():
                row = (
                    session.execute(
                        select(replay_case_executions)
                        .where(replay_case_executions.c.execution_id == execution_id)
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    return None
                if row["status"] in {"succeeded", "failed"}:
                    return None
                if (
                    row["status"] == "running"
                    and row["lease_expires_at"] is not None
                    and row["lease_expires_at"] > current
                ):
                    return None
                run = (
                    session.execute(
                        select(replay_runs)
                        .where(replay_runs.c.replay_run_id == row["replay_run_id"])
                        .with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                case_row = (
                    session.execute(
                        select(dataset_cases).where(dataset_cases.c.case_id == row["case_id"])
                    )
                    .mappings()
                    .one_or_none()
                )
                if run is None or case_row is None:
                    return None
                token = uuid4()
                attempt = int(row["attempt_count"]) + 1
                lease_expires = current + timedelta(seconds=lease_seconds)
                session.execute(
                    update(replay_case_executions)
                    .where(replay_case_executions.c.execution_id == execution_id)
                    .values(
                        status="running",
                        started_at=row["started_at"] or current,
                        attempt_count=attempt,
                        claimed_by=worker_id,
                        claim_token=token,
                        lease_expires_at=lease_expires,
                    )
                )
                session.execute(
                    update(replay_runs)
                    .where(replay_runs.c.replay_run_id == row["replay_run_id"])
                    .values(
                        status=ReplayRunStatus.RUNNING.value,
                        started_at=run["started_at"] or current,
                    )
                )
                session.execute(
                    replay_attempts.insert().values(
                        attempt_id=uuid4(),
                        execution_id=execution_id,
                        attempt_number=attempt,
                        started_at=current,
                        finished_at=None,
                        outcome="running",
                        error_code=None,
                        safe_error_message=None,
                        duration_seconds=None,
                    )
                )
                updated = dict(row)
                updated.update(
                    {
                        "status": "running",
                        "attempt_count": attempt,
                        "claim_token": token,
                        "claimed_by": worker_id,
                    }
                )
                return ClaimedExecution(updated, dict(run), _case(case_row), token, attempt)
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def renew_execution(
        self,
        execution_id: UUID,
        claim_token: UUID,
        worker_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> bool:
        try:
            with self._sessions() as session, session.begin():
                result = session.execute(
                    update(replay_case_executions)
                    .where(
                        and_(
                            replay_case_executions.c.execution_id == execution_id,
                            replay_case_executions.c.claim_token == claim_token,
                            replay_case_executions.c.claimed_by == worker_id,
                            replay_case_executions.c.status == "running",
                        )
                    )
                    .values(lease_expires_at=_utc(now) + timedelta(seconds=lease_seconds))
                )
                return bool(int(cast(Any, result).rowcount or 0) == 1)
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def complete_success(
        self,
        *,
        execution_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        output: JSONValue,
        request_fingerprint_value: str,
        response_fingerprint: str,
        generated_trace_id: UUID | None,
        now: datetime,
        duration_seconds: float,
    ) -> bool:
        return self._finish(
            execution_id=execution_id,
            claim_token=claim_token,
            attempt_number=attempt_number,
            status="succeeded",
            output=output,
            safe_error=None,
            request_fingerprint_value=request_fingerprint_value,
            response_fingerprint=response_fingerprint,
            generated_trace_id=generated_trace_id,
            now=now,
            duration_seconds=duration_seconds,
            retry_at=None,
            error_code=None,
        )

    def record_failure(
        self,
        *,
        execution_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        error_code: str,
        safe_message: str,
        retryable: bool,
        max_attempts: int,
        now: datetime,
        duration_seconds: float,
    ) -> bool:
        status = "retry_wait" if retryable and attempt_number < max_attempts else "failed"
        retry_at = (
            _utc(now) + timedelta(seconds=min(30.0, float(2 ** max(0, attempt_number - 1))))
            if status == "retry_wait"
            else None
        )
        return self._finish(
            execution_id=execution_id,
            claim_token=claim_token,
            attempt_number=attempt_number,
            status=status,
            output=None,
            safe_error={"code": error_code, "message": safe_message},
            request_fingerprint_value=None,
            response_fingerprint=None,
            generated_trace_id=None,
            now=now,
            duration_seconds=duration_seconds,
            retry_at=retry_at,
            error_code=error_code,
        )

    def _finish(
        self,
        *,
        execution_id: UUID,
        claim_token: UUID,
        attempt_number: int,
        status: str,
        output: JSONValue | None,
        safe_error: Mapping[str, JSONValue] | None,
        request_fingerprint_value: str | None,
        response_fingerprint: str | None,
        generated_trace_id: UUID | None,
        now: datetime,
        duration_seconds: float,
        retry_at: datetime | None,
        error_code: str | None,
    ) -> bool:
        current = _utc(now)
        try:
            with self._sessions() as session, session.begin():
                row = (
                    session.execute(
                        select(replay_case_executions)
                        .where(
                            and_(
                                replay_case_executions.c.execution_id == execution_id,
                                replay_case_executions.c.claim_token == claim_token,
                                replay_case_executions.c.status == "running",
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
                    update(replay_case_executions)
                    .where(replay_case_executions.c.execution_id == execution_id)
                    .values(
                        status=status,
                        available_at=retry_at or current,
                        finished_at=current if status in {"succeeded", "failed"} else None,
                        claimed_by=None,
                        claim_token=None,
                        lease_expires_at=None,
                        target_request_fingerprint=request_fingerprint_value,
                        target_response_fingerprint=response_fingerprint,
                        output=output,
                        safe_error=dict(safe_error) if safe_error else None,
                        generated_trace_id=generated_trace_id,
                    )
                )
                session.execute(
                    update(replay_attempts)
                    .where(
                        and_(
                            replay_attempts.c.execution_id == execution_id,
                            replay_attempts.c.attempt_number == attempt_number,
                        )
                    )
                    .values(
                        finished_at=current,
                        outcome=status,
                        error_code=error_code,
                        safe_error_message=cast(str | None, safe_error.get("message"))
                        if safe_error
                        else None,
                        duration_seconds=duration_seconds,
                    )
                )
                # Serialize the small run-level progress/finalization update so
                # concurrent case completions cannot both observe "running".
                session.execute(
                    select(replay_runs.c.replay_run_id)
                    .where(replay_runs.c.replay_run_id == row["replay_run_id"])
                    .with_for_update()
                ).scalar_one()
                self._refresh_run(session, cast(UUID, row["replay_run_id"]), current)
                return True
        except SQLAlchemyError as exc:
            raise ReplayStorageError("replay storage is unavailable") from exc

    def _refresh_run(self, session: Session, run_id: UUID, now: datetime) -> None:
        rows = (
            session.execute(
                select(replay_case_executions.c.status).where(
                    replay_case_executions.c.replay_run_id == run_id
                )
            )
            .scalars()
            .all()
        )
        succeeded = sum(item == "succeeded" for item in rows)
        failed = sum(item == "failed" for item in rows)
        completed = succeeded + failed
        values: dict[str, object] = {
            "completed_count": completed,
            "succeeded_count": succeeded,
            "failed_count": failed,
        }
        if completed == len(rows) and rows:
            values["status"] = (
                ReplayRunStatus.SUCCEEDED.value
                if failed == 0
                else ReplayRunStatus.FAILED.value
                if succeeded == 0
                else ReplayRunStatus.PARTIALLY_FAILED.value
            )
            values["finished_at"] = now
        else:
            values["status"] = ReplayRunStatus.RUNNING.value
        session.execute(
            update(replay_runs).where(replay_runs.c.replay_run_id == run_id).values(**values)
        )

    @staticmethod
    def _dataset_dict(row: Any, latest: Any) -> dict[str, object]:
        latest_body = None
        if latest is not None:
            latest_body = {
                "dataset_version_id": str(latest["dataset_version_id"]),
                "version_number": latest["version_number"],
                "status": latest["status"],
                "case_count": latest["case_count"],
                "content_checksum": latest["content_checksum"],
            }
        return {
            "dataset_id": str(row["dataset_id"]),
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
            "updated_at": _utc(cast(datetime, row["updated_at"])).isoformat(),
            "latest_version": latest_body,
        }

    @staticmethod
    def _version_dict(row: Any) -> dict[str, object]:
        return {
            "dataset_version_id": str(row["dataset_version_id"]),
            "dataset_id": str(row["dataset_id"]),
            "project_id": row["project_id"],
            "version_number": row["version_number"],
            "status": row["status"],
            "source_metadata": row["source_metadata"],
            "case_count": row["case_count"],
            "content_checksum": row["content_checksum"],
            "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
            "finalized_at": _utc(cast(datetime, row["finalized_at"])).isoformat()
            if row["finalized_at"]
            else None,
        }

    @staticmethod
    def _run_dict(row: Any) -> dict[str, object]:
        return {
            "replay_run_id": str(row["replay_run_id"]),
            "project_id": row["project_id"],
            "dataset_id": str(row["dataset_id"]),
            "dataset_version_id": str(row["dataset_version_id"]),
            "dataset_checksum": row["dataset_checksum"],
            "target_profile_id": row["target_profile_id"],
            "target_name": row["target_name"],
            "target_type": row["target_type"],
            "target_version": row["target_version"],
            "replay_mode": row["replay_mode"],
            "reproducibility_status": row["reproducibility_status"],
            "status": row["status"],
            "manifest": row["manifest"],
            "max_concurrency": row["max_concurrency"],
            "timeout_seconds": row["timeout_seconds"],
            "max_attempts": row["max_attempts"],
            "case_count": row["case_count"],
            "completed_count": row["completed_count"],
            "succeeded_count": row["succeeded_count"],
            "failed_count": row["failed_count"],
            "created_at": _utc(cast(datetime, row["created_at"])).isoformat(),
            "started_at": _utc(cast(datetime, row["started_at"])).isoformat()
            if row["started_at"]
            else None,
            "finished_at": _utc(cast(datetime, row["finished_at"])).isoformat()
            if row["finished_at"]
            else None,
        }

    @staticmethod
    def _execution_dict(row: Any) -> dict[str, object]:
        return {
            "execution_id": str(row["execution_id"]),
            "replay_run_id": str(row["replay_run_id"]),
            "case_id": str(row["case_id"]),
            "position": row["position"],
            "status": row["status"],
            "attempt_count": row["attempt_count"],
            "started_at": _utc(cast(datetime, row["started_at"])).isoformat()
            if row["started_at"]
            else None,
            "finished_at": _utc(cast(datetime, row["finished_at"])).isoformat()
            if row["finished_at"]
            else None,
            "target_request_fingerprint": row["target_request_fingerprint"],
            "target_response_fingerprint": row["target_response_fingerprint"],
            "output": row["output"],
            "safe_error": row["safe_error"],
            "generated_trace_id": str(row["generated_trace_id"])
            if row["generated_trace_id"]
            else None,
        }


__all__ = [
    "ClaimedExecution",
    "PostgresReplayRepository",
    "ReplayCreation",
    "ReplayIdempotencyConflict",
    "ReplayImmutableError",
    "ReplayNotFoundError",
    "ReplayStorageError",
    "ReplayValidationError",
    "hash_idempotency_key",
    "request_fingerprint",
]
