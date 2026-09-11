"""Synchronous PostgreSQL repository for canonical traces."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import and_, create_engine, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from agentlens.domain import Trace

from .config import DatabaseConfig
from .contracts import (
    IngestionResult,
    StorageUnavailableError,
    TraceConflictError,
    canonical_fingerprint,
)
from .models import events, spans, traces


class InvalidCursorError(ValueError):
    """Raised when a query cursor is malformed, tampered with, or mis-scoped."""


@dataclass(frozen=True, slots=True)
class TraceQuery:
    started_from: datetime | None = None
    started_to: datetime | None = None
    status: str | None = None
    name: str | None = None
    session_id: str | None = None
    span_type: str | None = None
    limit: int = 50
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class TraceSummary:
    trace_id: UUID
    name: str
    session_id: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None
    span_count: int
    event_count: int


@dataclass(frozen=True, slots=True)
class TracePage:
    items: tuple[TraceSummary, ...]
    next_cursor: str | None


class TraceQueryRepository(Protocol):
    """Repository boundary consumed by the API, not SQLAlchemy rows."""

    def ingest(self, trace: Trace) -> IngestionResult:
        """Persist one canonical trace transactionally."""

    def ingest_many(self, traces: Sequence[Trace]) -> tuple[IngestionResult, ...]:
        """Persist a validated batch in one transaction."""

    def get_trace(self, project_id: str, trace_id: UUID) -> Trace | None:
        """Load one trace within a project boundary."""

    def query_traces(self, project_id: str, query: TraceQuery) -> TracePage:
        """Return bounded summaries within a project boundary."""

    def check_ready(self) -> bool:
        """Run a cheap connectivity check."""

    def dispose(self) -> None:
        """Release the repository engine and its pool."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat() if value is not None else None


def _trace_row_values(trace: Trace, fingerprint: str) -> dict[str, object]:
    data = trace.to_dict()
    return {
        "project_id": trace.project_id,
        "trace_id": cast(UUID, trace.trace_id),
        "session_id": data["session_id"],
        "name": trace.name,
        "schema_version": data["schema_version"],
        "status": data["status"],
        "started_at": _utc(trace.started_at),
        "ended_at": _utc(trace.ended_at) if trace.ended_at is not None else None,
        "fingerprint": fingerprint,
        "ingested_at": datetime.now(UTC),
        "attributes": data["attributes"],
        "span_count": len(trace.spans),
        "event_count": len(trace.events),
    }


def _span_row_values(trace: Trace) -> list[dict[str, object]]:
    project_id = trace.project_id
    trace_id = cast(UUID, trace.trace_id)
    rows: list[dict[str, object]] = []
    for position, span in enumerate(trace.spans):
        data = span.to_dict()
        rows.append(
            {
                "project_id": project_id,
                "trace_id": trace_id,
                "span_id": cast(UUID, span.span_id),
                "position": position,
                "parent_span_id": cast(UUID | None, span.parent_span_id),
                "span_type": data["span_type"],
                "name": span.name,
                "status": data["status"],
                "started_at": _utc(span.started_at),
                "ended_at": _utc(span.ended_at) if span.ended_at is not None else None,
                "input": data["input"],
                "output": data["output"],
                "attributes": data["attributes"],
                "usage": data["usage"],
                "error": data["error"],
            }
        )
    return rows


def _event_row_values(trace: Trace) -> list[dict[str, object]]:
    project_id = trace.project_id
    trace_id = cast(UUID, trace.trace_id)
    rows: list[dict[str, object]] = []
    for position, event in enumerate(trace.events):
        rows.append(
            {
                "project_id": project_id,
                "trace_id": trace_id,
                "event_id": cast(UUID, event.event_id),
                "position": position,
                "span_id": cast(UUID | None, event.span_id),
                "name": event.name,
                "timestamp": _utc(event.timestamp),
                "attributes": event.to_dict()["attributes"],
            }
        )
    return rows


def _cursor_payload(project_id: str, started_at: datetime, trace_id: UUID) -> bytes:
    return json.dumps(
        {"project_id": project_id, "started_at": _iso(started_at), "trace_id": str(trace_id)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class _CursorCodec:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def encode(self, project_id: str, started_at: datetime, trace_id: UUID) -> str:
        payload = _cursor_payload(project_id, started_at, trace_id)
        signature = hmac.new(self._secret, payload, hashlib.sha256).hexdigest().encode("ascii")
        token = base64.urlsafe_b64encode(payload + b"." + signature)
        return token.decode("ascii").rstrip("=")

    def decode(self, token: str, project_id: str) -> tuple[datetime, UUID]:
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise InvalidCursorError("invalid cursor")
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            payload, supplied = decoded.rsplit(b".", 1)
            expected = hmac.new(self._secret, payload, hashlib.sha256).hexdigest().encode("ascii")
            if not hmac.compare_digest(supplied, expected):
                raise InvalidCursorError("invalid cursor")
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict) or data.get("project_id") != project_id:
                raise InvalidCursorError("invalid cursor")
            started_at = datetime.fromisoformat(cast(str, data["started_at"]))
            if started_at.tzinfo is None or started_at.utcoffset() is None:
                raise InvalidCursorError("invalid cursor")
            trace_id = UUID(cast(str, data["trace_id"]))
            return _utc(started_at), trace_id
        except InvalidCursorError:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidCursorError("invalid cursor") from exc


class PostgresTraceRepository:
    """Thread-safe synchronous SQLAlchemy repository backed by PostgreSQL."""

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
        self._cursor = _CursorCodec(config.cursor_secret)

    def ingest(self, trace: Trace) -> IngestionResult:
        return self.ingest_many((trace,))[0]

    def ingest_many(self, trace_values: Sequence[Trace]) -> tuple[IngestionResult, ...]:
        if not trace_values:
            return ()
        if len({(trace.project_id, trace.trace_id) for trace in trace_values}) != len(trace_values):
            raise ValueError("batch contains duplicate trace identities")
        try:
            with self._sessions() as session:
                with session.begin():
                    return self._ingest_many_transaction(session, trace_values)
        except (TraceConflictError, ValueError):
            raise
        except SQLAlchemyError as exc:
            raise StorageUnavailableError("durable trace storage is unavailable") from exc

    def _ingest_many_transaction(
        self,
        session: Session,
        trace_values: Sequence[Trace],
    ) -> tuple[IngestionResult, ...]:
        results: list[IngestionResult] = []
        new_traces: list[Trace] = []
        for trace in trace_values:
            fingerprint = canonical_fingerprint(trace)
            statement = (
                pg_insert(traces)
                .values(_trace_row_values(trace, fingerprint))
                .on_conflict_do_nothing(index_elements=[traces.c.project_id, traces.c.trace_id])
                .returning(traces.c.trace_id)
            )
            inserted = session.execute(statement).scalar_one_or_none() is not None
            if inserted:
                new_traces.append(trace)
            else:
                existing = session.execute(
                    select(traces.c.fingerprint)
                    .where(
                        and_(
                            traces.c.project_id == trace.project_id,
                            traces.c.trace_id == cast(UUID, trace.trace_id),
                        )
                    )
                    .with_for_update()
                ).scalar_one()
                if existing != fingerprint:
                    raise TraceConflictError("trace identity has conflicting content")
            results.append(
                IngestionResult(
                    trace_id=cast(UUID, trace.trace_id),
                    duplicate=not inserted,
                    fingerprint=fingerprint,
                )
            )
        for trace in new_traces:
            span_values = _span_row_values(trace)
            event_values = _event_row_values(trace)
            if span_values:
                session.execute(spans.insert(), span_values)
            if event_values:
                session.execute(events.insert(), event_values)
        return tuple(results)

    def get_trace(self, project_id: str, trace_id: UUID) -> Trace | None:
        try:
            with self._sessions() as session:
                trace_row = (
                    session.execute(
                        select(traces).where(
                            and_(traces.c.project_id == project_id, traces.c.trace_id == trace_id)
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if trace_row is None:
                    return None
                span_rows = (
                    session.execute(
                        select(spans)
                        .where(and_(spans.c.project_id == project_id, spans.c.trace_id == trace_id))
                        .order_by(spans.c.position)
                    )
                    .mappings()
                    .all()
                )
                event_rows = (
                    session.execute(
                        select(events)
                        .where(
                            and_(events.c.project_id == project_id, events.c.trace_id == trace_id)
                        )
                        .order_by(events.c.position)
                    )
                    .mappings()
                    .all()
                )
                return self._reconstruct(trace_row, span_rows, event_rows)
        except SQLAlchemyError as exc:
            raise StorageUnavailableError("durable trace storage is unavailable") from exc

    def _reconstruct(
        self,
        trace_row: object,
        span_rows: Sequence[object],
        event_rows: Sequence[object],
    ) -> Trace:
        trace_mapping = cast(dict[str, object], trace_row)
        spans_data = [
            {
                "span_id": str(row["span_id"]),
                "trace_id": str(row["trace_id"]),
                "parent_span_id": str(row["parent_span_id"]) if row["parent_span_id"] else None,
                "span_type": row["span_type"],
                "name": row["name"],
                "started_at": _iso(cast(datetime, row["started_at"])),
                "ended_at": _iso(cast(datetime | None, row["ended_at"])),
                "status": row["status"],
                "input": row["input"],
                "output": row["output"],
                "attributes": row["attributes"],
                "usage": row["usage"],
                "error": row["error"],
            }
            for row in (cast(dict[str, object], item) for item in span_rows)
        ]
        events_data = [
            {
                "event_id": str(row["event_id"]),
                "trace_id": str(row["trace_id"]),
                "name": row["name"],
                "timestamp": _iso(cast(datetime, row["timestamp"])),
                "span_id": str(row["span_id"]) if row["span_id"] else None,
                "attributes": row["attributes"],
            }
            for row in (cast(dict[str, object], item) for item in event_rows)
        ]
        return Trace.from_dict(
            {
                "schema_version": trace_mapping["schema_version"],
                "trace_id": str(trace_mapping["trace_id"]),
                "project_id": trace_mapping["project_id"],
                "session_id": trace_mapping["session_id"],
                "name": trace_mapping["name"],
                "started_at": _iso(cast(datetime, trace_mapping["started_at"])),
                "ended_at": _iso(cast(datetime | None, trace_mapping["ended_at"])),
                "status": trace_mapping["status"],
                "spans": spans_data,
                "events": events_data,
                "attributes": trace_mapping["attributes"],
            }
        )

    def query_traces(self, project_id: str, query: TraceQuery) -> TracePage:
        try:
            with self._sessions() as session:
                conditions = [traces.c.project_id == project_id]
                if query.started_from is not None:
                    conditions.append(traces.c.started_at >= _utc(query.started_from))
                if query.started_to is not None:
                    conditions.append(traces.c.started_at <= _utc(query.started_to))
                if query.status is not None:
                    conditions.append(traces.c.status == query.status)
                if query.name is not None:
                    conditions.append(traces.c.name == query.name)
                if query.session_id is not None:
                    conditions.append(traces.c.session_id == query.session_id)
                if query.span_type is not None:
                    conditions.append(
                        select(spans.c.span_id)
                        .where(
                            and_(
                                spans.c.project_id == project_id,
                                spans.c.trace_id == traces.c.trace_id,
                                spans.c.span_type == query.span_type,
                            )
                        )
                        .exists()
                    )
                if query.cursor is not None:
                    cursor_started, cursor_trace_id = self._cursor.decode(query.cursor, project_id)
                    conditions.append(
                        or_(
                            traces.c.started_at < cursor_started,
                            and_(
                                traces.c.started_at == cursor_started,
                                traces.c.trace_id < cursor_trace_id,
                            ),
                        )
                    )
                rows = (
                    session.execute(
                        select(traces)
                        .where(and_(*conditions))
                        .order_by(traces.c.started_at.desc(), traces.c.trace_id.desc())
                        .limit(query.limit + 1)
                    )
                    .mappings()
                    .all()
                )
                has_more = len(rows) > query.limit
                page_rows = rows[: query.limit]
                items = tuple(self._summary(row) for row in page_rows)
                next_cursor = None
                if has_more and page_rows:
                    last = page_rows[-1]
                    next_cursor = self._cursor.encode(
                        project_id,
                        cast(datetime, last["started_at"]),
                        cast(UUID, last["trace_id"]),
                    )
                return TracePage(items=items, next_cursor=next_cursor)
        except InvalidCursorError:
            raise
        except SQLAlchemyError as exc:
            raise StorageUnavailableError("durable trace storage is unavailable") from exc

    @staticmethod
    def _summary(row: object) -> TraceSummary:
        data = cast(dict[str, object], row)
        started_at = _utc(cast(datetime, data["started_at"]))
        ended_at_value = data["ended_at"]
        ended_at = _utc(cast(datetime, ended_at_value)) if ended_at_value else None
        duration = (ended_at - started_at).total_seconds() if ended_at is not None else None
        return TraceSummary(
            trace_id=cast(UUID, data["trace_id"]),
            name=cast(str, data["name"]),
            session_id=cast(str | None, data["session_id"]),
            status=cast(str, data["status"]),
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            span_count=cast(int, data["span_count"]),
            event_count=cast(int, data["event_count"]),
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
