"""PostgreSQL-backed dashboard analytics with explicit project boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from agentlens.storage.config import DatabaseConfig
from agentlens.storage.contracts import StorageUnavailableError
from agentlens.storage.repository import TraceSummary


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _number(value: object) -> float | None:
    if value is None:
        return None
    return float(cast(float, value))


def _integer(value: object) -> int | None:
    if value is None:
        return None
    return int(cast(int, value))


@dataclass(frozen=True, slots=True)
class AnalyticsWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = _utc(self.start)
        end = _utc(self.end)
        if start >= end:
            raise ValueError("analytics start must be before end")
        if end - start > timedelta(days=31):
            raise ValueError("analytics windows are limited to 31 days")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)


@dataclass(frozen=True, slots=True)
class TokenTotals:
    spans_with_usage: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True, slots=True)
class FindingSummary:
    result_id: UUID
    trace_id: UUID
    evaluation_type: str
    code: str
    severity: str
    message: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OverviewAnalytics:
    window: AnalyticsWindow
    trace_count: int
    completed_trace_count: int
    error_trace_count: int
    error_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None
    reported_tokens: TokenTotals
    evaluation_count: int
    evaluation_status_counts: Mapping[str, int]
    finding_counts: Mapping[str, int]
    recent_traces: tuple[TraceSummary, ...]
    recent_findings: tuple[FindingSummary, ...]


@dataclass(frozen=True, slots=True)
class TimeseriesPoint:
    bucket_start: datetime
    trace_count: int
    error_count: int
    completed_count: int
    average_latency_ms: float | None
    reported_total_tokens: int | None


@dataclass(frozen=True, slots=True)
class EvaluationGroup:
    evaluation_type: str
    evaluator_name: str
    evaluator_version: str
    evaluation_mode: str
    config_fingerprint: str
    judge_profile: str | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    result_count: int
    status_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class EvaluationAnalytics:
    window: AnalyticsWindow
    groups: tuple[EvaluationGroup, ...]
    finding_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class RuntimeFailure:
    job_id: UUID
    evaluation_type: str
    state: str
    error_code: str | None
    message: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeSummary:
    job_state_counts: Mapping[str, int]
    recent_failures: tuple[RuntimeFailure, ...]
    database_status: str
    redis_status: str
    worker_status: str


class AnalyticsRepository(Protocol):
    def overview(
        self, project_id: str, window: AnalyticsWindow, limit: int
    ) -> OverviewAnalytics: ...

    def timeseries(
        self, project_id: str, window: AnalyticsWindow
    ) -> tuple[TimeseriesPoint, ...]: ...

    def evaluations(
        self,
        project_id: str,
        window: AnalyticsWindow,
        evaluation_type: str | None,
        result_status: str | None,
        limit: int,
    ) -> EvaluationAnalytics: ...

    def runtime_jobs(self, project_id: str, limit: int) -> Mapping[str, object]: ...

    def check_ready(self) -> bool: ...

    def dispose(self) -> None: ...


class PostgresAnalyticsRepository:
    """Read-only analytics queries sharing the trace repository's engine."""

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

    def overview(self, project_id: str, window: AnalyticsWindow, limit: int) -> OverviewAnalytics:
        try:
            with self._sessions() as session:
                params = self._params(project_id, window)
                stats = (
                    session.execute(
                        text(
                            """
                        SELECT
                          COUNT(*) AS trace_count,
                          COUNT(*) FILTER (WHERE ended_at IS NOT NULL) AS completed_count,
                          COUNT(*) FILTER (WHERE status = 'error') AS error_count,
                          percentile_cont(0.50) WITHIN GROUP (
                            ORDER BY EXTRACT(EPOCH FROM (ended_at - started_at))
                          ) FILTER (WHERE ended_at IS NOT NULL) AS p50_seconds,
                          percentile_cont(0.95) WITHIN GROUP (
                            ORDER BY EXTRACT(EPOCH FROM (ended_at - started_at))
                          ) FILTER (WHERE ended_at IS NOT NULL) AS p95_seconds,
                          percentile_cont(0.99) WITHIN GROUP (
                            ORDER BY EXTRACT(EPOCH FROM (ended_at - started_at))
                          ) FILTER (WHERE ended_at IS NOT NULL) AS p99_seconds
                        FROM traces
                        WHERE project_id = :project_id
                          AND started_at >= :start_at AND started_at < :end_at
                        """
                        ),
                        params,
                    )
                    .mappings()
                    .one()
                )
                usage = (
                    session.execute(
                        text(
                            """
                        SELECT
                          COUNT(*) FILTER (WHERE s.usage IS NOT NULL) AS spans_with_usage,
                          SUM(NULLIF(s.usage->>'input_tokens', '')::bigint) AS input_tokens,
                          SUM(NULLIF(s.usage->>'output_tokens', '')::bigint) AS output_tokens,
                          SUM(NULLIF(s.usage->>'total_tokens', '')::bigint) AS total_tokens
                        FROM spans s
                        JOIN traces t ON t.project_id = s.project_id AND t.trace_id = s.trace_id
                        WHERE s.project_id = :project_id
                          AND t.started_at >= :start_at AND t.started_at < :end_at
                        """
                        ),
                        params,
                    )
                    .mappings()
                    .one()
                )
                status_rows = (
                    session.execute(
                        text(
                            """
                        SELECT result_status, COUNT(*) AS count
                        FROM evaluation_results
                        WHERE project_id = :project_id
                          AND created_at >= :start_at AND created_at < :end_at
                        GROUP BY result_status
                        ORDER BY result_status
                        """
                        ),
                        params,
                    )
                    .mappings()
                    .all()
                )
                finding_rows = (
                    session.execute(
                        text(
                            """
                        SELECT finding->>'code' AS code, COUNT(*) AS count
                        FROM evaluation_results r
                        CROSS JOIN LATERAL jsonb_array_elements(r.findings) AS finding
                        WHERE r.project_id = :project_id
                          AND r.created_at >= :start_at AND r.created_at < :end_at
                        GROUP BY finding->>'code'
                        ORDER BY count DESC, code
                        LIMIT :limit
                        """
                        ),
                        {**params, "limit": limit},
                    )
                    .mappings()
                    .all()
                )
                recent_traces = (
                    session.execute(
                        text(
                            """
                        SELECT trace_id, name, session_id, status, started_at, ended_at,
                               span_count, event_count
                        FROM traces
                        WHERE project_id = :project_id
                          AND started_at >= :start_at AND started_at < :end_at
                        ORDER BY started_at DESC, trace_id DESC
                        LIMIT :limit
                        """
                        ),
                        {**params, "limit": limit},
                    )
                    .mappings()
                    .all()
                )
                recent_findings = (
                    session.execute(
                        text(
                            """
                        SELECT r.result_id, r.trace_id, r.evaluation_type,
                               finding->>'code' AS code,
                               finding->>'severity' AS severity,
                               LEFT(COALESCE(finding->>'message', ''), 512) AS message,
                               r.created_at
                        FROM evaluation_results r
                        CROSS JOIN LATERAL jsonb_array_elements(r.findings) AS finding
                        WHERE r.project_id = :project_id
                          AND r.created_at >= :start_at AND r.created_at < :end_at
                        ORDER BY r.created_at DESC, r.result_id DESC
                        LIMIT :limit
                        """
                        ),
                        {**params, "limit": limit},
                    )
                    .mappings()
                    .all()
                )
                trace_count = int(cast(int, stats["trace_count"]))
                completed_count = int(cast(int, stats["completed_count"]))
                error_count = int(cast(int, stats["error_count"]))
                return OverviewAnalytics(
                    window=window,
                    trace_count=trace_count,
                    completed_trace_count=completed_count,
                    error_trace_count=error_count,
                    error_rate=(error_count / trace_count if trace_count else None),
                    latency_p50_ms=self._milliseconds(stats["p50_seconds"]),
                    latency_p95_ms=self._milliseconds(stats["p95_seconds"]),
                    latency_p99_ms=self._milliseconds(stats["p99_seconds"]),
                    reported_tokens=TokenTotals(
                        spans_with_usage=int(cast(int, usage["spans_with_usage"])),
                        input_tokens=_integer(usage["input_tokens"]),
                        output_tokens=_integer(usage["output_tokens"]),
                        total_tokens=_integer(usage["total_tokens"]),
                    ),
                    evaluation_count=sum(int(cast(int, row["count"])) for row in status_rows),
                    evaluation_status_counts={
                        cast(str, row["result_status"]): int(cast(int, row["count"]))
                        for row in status_rows
                    },
                    finding_counts={
                        cast(str, row["code"]): int(cast(int, row["count"]))
                        for row in finding_rows
                        if row["code"] is not None
                    },
                    recent_traces=tuple(
                        self._trace_summary(cast(Mapping[str, object], row))
                        for row in recent_traces
                    ),
                    recent_findings=tuple(
                        self._finding_summary(cast(Mapping[str, object], row))
                        for row in recent_findings
                    ),
                )
        except SQLAlchemyError as exc:
            raise StorageUnavailableError("analytics storage is unavailable") from exc

    def timeseries(self, project_id: str, window: AnalyticsWindow) -> tuple[TimeseriesPoint, ...]:
        bucket = self._bucket(window)
        try:
            with self._sessions() as session:
                rows = (
                    session.execute(
                        text(
                            f"""
                        SELECT date_trunc('{bucket}', started_at) AS bucket_start,
                               COUNT(*) AS trace_count,
                               COUNT(*) FILTER (WHERE status = 'error') AS error_count,
                               COUNT(*) FILTER (WHERE ended_at IS NOT NULL) AS completed_count,
                               AVG(EXTRACT(EPOCH FROM (ended_at - started_at)))
                                 FILTER (WHERE ended_at IS NOT NULL) AS average_seconds,
                               SUM(NULLIF((
                                 SELECT SUM(NULLIF(s.usage->>'total_tokens', '')::bigint)
                                 FROM spans s
                                 WHERE s.project_id = traces.project_id
                                   AND s.trace_id = traces.trace_id
                               )::text, '')::bigint) AS reported_total_tokens
                        FROM traces
                        WHERE project_id = :project_id
                          AND started_at >= :start_at AND started_at < :end_at
                        GROUP BY bucket_start
                        ORDER BY bucket_start
                        """
                        ),
                        self._params(project_id, window),
                    )
                    .mappings()
                    .all()
                )
                return tuple(
                    TimeseriesPoint(
                        bucket_start=_utc(cast(datetime, row["bucket_start"])),
                        trace_count=int(cast(int, row["trace_count"])),
                        error_count=int(cast(int, row["error_count"])),
                        completed_count=int(cast(int, row["completed_count"])),
                        average_latency_ms=self._milliseconds(row["average_seconds"]),
                        reported_total_tokens=_integer(row["reported_total_tokens"]),
                    )
                    for row in rows
                )
        except SQLAlchemyError as exc:
            raise StorageUnavailableError("analytics storage is unavailable") from exc

    def evaluations(
        self,
        project_id: str,
        window: AnalyticsWindow,
        evaluation_type: str | None,
        result_status: str | None,
        limit: int,
    ) -> EvaluationAnalytics:
        filters = ""
        params: dict[str, object] = {**self._params(project_id, window), "limit": limit}
        if evaluation_type is not None:
            filters += " AND r.evaluation_type = :evaluation_type"
            params["evaluation_type"] = evaluation_type
        if result_status is not None:
            filters += " AND r.result_status = :result_status"
            params["result_status"] = result_status
        try:
            with self._sessions() as session:
                group_rows = (
                    session.execute(
                        text(
                            f"""
                        SELECT r.evaluation_type, r.evaluator_name, r.evaluator_version,
                               r.evaluation_mode, r.config_fingerprint,
                               i.judge_profile, i.provider, i.model, i.prompt_version,
                               COUNT(DISTINCT r.result_id) AS result_count,
                               COUNT(DISTINCT r.result_id) FILTER (
                                 WHERE r.result_status = 'completed'
                               ) AS completed_count,
                               COUNT(DISTINCT r.result_id) FILTER (
                                 WHERE r.result_status = 'not_applicable'
                               ) AS not_applicable_count,
                               COUNT(DISTINCT r.result_id) FILTER (
                                 WHERE r.result_status = 'invalid_input'
                               ) AS invalid_count
                        FROM evaluation_results r
                        LEFT JOIN evaluation_judge_invocations i
                          ON i.project_id = r.project_id AND i.result_id = r.result_id
                        WHERE r.project_id = :project_id
                          AND r.created_at >= :start_at AND r.created_at < :end_at
                          {filters}
                        GROUP BY r.evaluation_type, r.evaluator_name, r.evaluator_version,
                                 r.evaluation_mode, r.config_fingerprint,
                                 i.judge_profile, i.provider, i.model, i.prompt_version
                        ORDER BY result_count DESC, r.evaluation_type, r.evaluator_version
                        LIMIT :limit
                        """
                        ),
                        params,
                    )
                    .mappings()
                    .all()
                )
                finding_rows = (
                    session.execute(
                        text(
                            f"""
                        SELECT finding->>'code' AS code, COUNT(*) AS count
                        FROM evaluation_results r
                        CROSS JOIN LATERAL jsonb_array_elements(r.findings) AS finding
                        WHERE r.project_id = :project_id
                          AND r.created_at >= :start_at AND r.created_at < :end_at
                          {filters}
                        GROUP BY finding->>'code'
                        ORDER BY count DESC, code
                        LIMIT :limit
                        """
                        ),
                        params,
                    )
                    .mappings()
                    .all()
                )
                groups = tuple(
                    EvaluationGroup(
                        evaluation_type=cast(str, row["evaluation_type"]),
                        evaluator_name=cast(str, row["evaluator_name"]),
                        evaluator_version=cast(str, row["evaluator_version"]),
                        evaluation_mode=cast(str, row["evaluation_mode"]),
                        config_fingerprint=cast(str, row["config_fingerprint"]),
                        judge_profile=cast(str | None, row["judge_profile"]),
                        provider=cast(str | None, row["provider"]),
                        model=cast(str | None, row["model"]),
                        prompt_version=cast(str | None, row["prompt_version"]),
                        result_count=int(cast(int, row["result_count"])),
                        status_counts={
                            status: count
                            for status, count in (
                                ("completed", int(cast(int, row["completed_count"]))),
                                (
                                    "not_applicable",
                                    int(cast(int, row["not_applicable_count"])),
                                ),
                                ("invalid_input", int(cast(int, row["invalid_count"]))),
                            )
                            if count
                        },
                    )
                    for row in group_rows
                )
                return EvaluationAnalytics(
                    window=window,
                    groups=groups,
                    finding_counts={
                        cast(str, row["code"]): int(cast(int, row["count"]))
                        for row in finding_rows
                        if row["code"] is not None
                    },
                )
        except SQLAlchemyError as exc:
            raise StorageUnavailableError("analytics storage is unavailable") from exc

    def runtime_jobs(self, project_id: str, limit: int) -> Mapping[str, object]:
        try:
            with self._sessions() as session:
                count_rows = (
                    session.execute(
                        text(
                            """
                        SELECT state, COUNT(*) AS count
                        FROM evaluation_jobs
                        WHERE project_id = :project_id
                        GROUP BY state
                        ORDER BY state
                        """
                        ),
                        {"project_id": project_id},
                    )
                    .mappings()
                    .all()
                )
                failures = (
                    session.execute(
                        text(
                            """
                        SELECT job_id, evaluation_type, state, last_error_code,
                               last_error_message, updated_at
                        FROM evaluation_jobs
                        WHERE project_id = :project_id
                          AND state IN ('retry_wait', 'failed', 'dead_letter')
                        ORDER BY updated_at DESC, job_id DESC
                        LIMIT :limit
                        """
                        ),
                        {"project_id": project_id, "limit": limit},
                    )
                    .mappings()
                    .all()
                )
                workers = (
                    session.execute(
                        text(
                            """
                        SELECT worker_id, worker_type, started_at, last_seen, state,
                               CASE
                                 WHEN state = 'running'
                                  AND last_seen >= now() - (30 * interval '1 second')
                                 THEN 'healthy' ELSE 'stale'
                               END AS health
                        FROM worker_heartbeats
                        ORDER BY last_seen DESC, worker_id
                        LIMIT 50
                        """
                        )
                    )
                    .mappings()
                    .all()
                )
                return {
                    "job_state_counts": {
                        cast(str, row["state"]): int(cast(int, row["count"])) for row in count_rows
                    },
                    "recent_failures": tuple(
                        RuntimeFailure(
                            job_id=cast(UUID, row["job_id"]),
                            evaluation_type=cast(str, row["evaluation_type"]),
                            state=cast(str, row["state"]),
                            error_code=cast(str | None, row["last_error_code"]),
                            message=cast(str | None, row["last_error_message"]),
                            updated_at=_utc(cast(datetime, row["updated_at"])),
                        )
                        for row in failures
                    ),
                    "workers": tuple(dict(row) for row in workers),
                }
        except SQLAlchemyError as exc:
            raise StorageUnavailableError("analytics storage is unavailable") from exc

    def check_ready(self) -> bool:
        try:
            with self._sessions() as session:
                session.execute(text("SELECT 1")).scalar_one()
            return True
        except SQLAlchemyError:
            return False

    def dispose(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _params(project_id: str, window: AnalyticsWindow) -> dict[str, object]:
        return {"project_id": project_id, "start_at": window.start, "end_at": window.end}

    @staticmethod
    def _bucket(window: AnalyticsWindow) -> str:
        seconds = (window.end - window.start).total_seconds()
        if seconds <= 2 * 60 * 60:
            return "minute"
        if seconds <= 2 * 24 * 60 * 60:
            return "hour"
        return "day"

    @staticmethod
    def _milliseconds(value: object) -> float | None:
        number = _number(value)
        return round(number * 1000, 3) if number is not None else None

    @staticmethod
    def _trace_summary(row: Mapping[str, object]) -> TraceSummary:
        started_at = _utc(cast(datetime, row["started_at"]))
        ended_value = row["ended_at"]
        ended_at = _utc(cast(datetime, ended_value)) if ended_value is not None else None
        duration = (ended_at - started_at).total_seconds() if ended_at is not None else None
        return TraceSummary(
            trace_id=cast(UUID, row["trace_id"]),
            name=cast(str, row["name"]),
            session_id=cast(str | None, row["session_id"]),
            status=cast(str, row["status"]),
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            span_count=int(cast(int, row["span_count"])),
            event_count=int(cast(int, row["event_count"])),
        )

    @staticmethod
    def _finding_summary(row: Mapping[str, object]) -> FindingSummary:
        return FindingSummary(
            result_id=cast(UUID, row["result_id"]),
            trace_id=cast(UUID, row["trace_id"]),
            evaluation_type=cast(str, row["evaluation_type"]),
            code=cast(str, row["code"]),
            severity=cast(str, row["severity"]),
            message=cast(str, row["message"]),
            created_at=_utc(cast(datetime, row["created_at"])),
        )


class InMemoryAnalyticsRepository:
    """Thread-safe in-memory analytics calculation over sink traces."""

    def __init__(self, sink: Any = None) -> None:
        self.sink = sink

    def _get_traces(self, project_id: str, window: AnalyticsWindow) -> list[Any]:
        if self.sink is None or not hasattr(self.sink, "_records"):
            return []
        records = getattr(self.sink, "_records", {})
        traces = []
        for (p_id, _), (_, trace) in list(records.items()):
            if p_id == project_id:
                traces.append(trace)
        return traces

    def overview(self, project_id: str, window: AnalyticsWindow, limit: int) -> OverviewAnalytics:
        traces = self._get_traces(project_id, window)
        trace_count = len(traces)
        completed_count = sum(1 for t in traces if getattr(t, "ended_at", None) is not None)
        error_count = sum(1 for t in traces if getattr(t, "status", "") == "error")
        error_rate = (error_count / trace_count) if trace_count > 0 else 0.0

        durations_ms = []
        in_tok = 0
        out_tok = 0
        spans_with_usage = 0

        for t in traces:
            if getattr(t, "ended_at", None) and getattr(t, "started_at", None):
                durations_ms.append((t.ended_at - t.started_at).total_seconds() * 1000)
            for s in getattr(t, "spans", ()):
                usage = getattr(s, "usage", None)
                if usage is not None:
                    spans_with_usage += 1
                    in_tok += getattr(usage, "input_tokens", 0) or 0
                    out_tok += getattr(usage, "output_tokens", 0) or 0

        durations_ms.sort()
        n = len(durations_ms)
        p50 = durations_ms[int(n * 0.50)] if n else None
        p95 = durations_ms[int(n * 0.95)] if n else None
        p99 = durations_ms[int(n * 0.99)] if n else None

        tokens = TokenTotals(
            spans_with_usage=spans_with_usage,
            input_tokens=in_tok or None,
            output_tokens=out_tok or None,
            total_tokens=(in_tok + out_tok) or None,
        )

        recent_traces = []
        for t in sorted(traces, key=lambda x: getattr(x, "started_at", datetime.min), reverse=True)[:limit]:
            s_at = getattr(t, "started_at", datetime.now(UTC))
            e_at = getattr(t, "ended_at", None)
            dur = (e_at - s_at).total_seconds() if e_at else None
            recent_traces.append(
                TraceSummary(
                    trace_id=t.trace_id,
                    name=t.name,
                    session_id=getattr(t, "session_id", None),
                    status=t.status,
                    started_at=s_at,
                    ended_at=e_at,
                    duration_seconds=dur,
                    span_count=len(getattr(t, "spans", ())),
                    event_count=0,
                )
            )

        return OverviewAnalytics(
            window=window,
            trace_count=trace_count,
            completed_trace_count=completed_count,
            error_trace_count=error_count,
            error_rate=round(error_rate, 4) if trace_count else None,
            latency_p50_ms=round(p50, 1) if p50 is not None else None,
            latency_p95_ms=round(p95, 1) if p95 is not None else None,
            latency_p99_ms=round(p99, 1) if p99 is not None else None,
            reported_tokens=tokens,
            evaluation_count=0,
            evaluation_status_counts={},
            finding_counts={},
            recent_traces=tuple(recent_traces),
            recent_findings=(),
        )

    def timeseries(self, project_id: str, window: AnalyticsWindow) -> tuple[TimeseriesPoint, ...]:
        traces = self._get_traces(project_id, window)
        if not traces:
            return ()
        durations = [
            (t.ended_at - t.started_at).total_seconds() * 1000
            for t in traces
            if getattr(t, "ended_at", None) and getattr(t, "started_at", None)
        ]
        avg_lat = sum(durations) / len(durations) if durations else 0.0
        total_tokens = sum(
            int(getattr(s.usage, "total_tokens", 0) or 0)
            for t in traces
            for s in getattr(t, "spans", ())
            if getattr(s, "usage", None)
        )
        pt = TimeseriesPoint(
            bucket_start=window.start,
            trace_count=len(traces),
            error_count=sum(1 for t in traces if getattr(t, "status", "") == "error"),
            completed_count=sum(1 for t in traces if getattr(t, "ended_at", None) is not None),
            average_latency_ms=round(avg_lat, 1),
            reported_total_tokens=total_tokens,
        )
        return (pt,)

    def evaluations(self, project_id: str, window: AnalyticsWindow, evaluation_type: str | None, result_status: str | None, limit: int) -> EvaluationAnalytics:
        return EvaluationAnalytics(window=window, groups=(), finding_counts={})

    def runtime_jobs(self, project_id: str, limit: int) -> Mapping[str, object]:
        return {"job_state_counts": {}, "recent_failures": (), "workers": ()}

    def check_ready(self) -> bool:
        return True

    def dispose(self) -> None:
        pass


__all__ = [
    "AnalyticsRepository",
    "AnalyticsWindow",
    "EvaluationAnalytics",
    "EvaluationGroup",
    "FindingSummary",
    "InMemoryAnalyticsRepository",
    "OverviewAnalytics",
    "PostgresAnalyticsRepository",
    "RuntimeFailure",
    "RuntimeSummary",
    "TimeseriesPoint",
    "TokenTotals",
]
