"""Project-scoped, bounded analytics and read-only runtime endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.analytics.hotspots import aggregate_project_hotspots
from agentlens.analytics.profiler import profile_trace
from agentlens.analytics.repository import (
    AnalyticsRepository,
    AnalyticsWindow,
    EvaluationAnalytics,
    OverviewAnalytics,
    TimeseriesPoint,
)
from agentlens.storage.contracts import StorageUnavailableError

from ..auth import AuthContext
from ..dependencies import require_auth
from ..errors import GatewayError

router = APIRouter()
AUTH_DEPENDENCY = Depends(require_auth)
WINDOWS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
MAX_LIMIT = 100


def _repository(request: Request) -> AnalyticsRepository:
    repository = request.app.state.gateway.analytics_repository
    if repository is None or not callable(getattr(repository, "overview", None)):
        raise GatewayError(
            code="analytics_unavailable",
            message="Analytics is not configured.",
            status_code=503,
        )
    return cast(AnalyticsRepository, repository)


def _invalid(message: str) -> GatewayError:
    return GatewayError(code="invalid_analytics_query", message=message, status_code=400)


def _parse_timestamp(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _invalid(f"{field} must be a valid ISO-8601 timestamp.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _invalid(f"{field} must include a timezone.")
    return parsed.astimezone(UTC)


def _window(window: str | None, start: str | None, end: str | None) -> AnalyticsWindow:
    parsed_start = _parse_timestamp(start, "start")
    parsed_end = _parse_timestamp(end, "end")
    if parsed_start is not None or parsed_end is not None:
        if parsed_start is None or parsed_end is None:
            raise _invalid("start and end must be provided together.")
        try:
            return AnalyticsWindow(parsed_start, parsed_end)
        except ValueError as exc:
            raise _invalid(str(exc)) from None
    selected = window or "24h"
    if selected not in WINDOWS:
        raise _invalid("window must be one of: 1h, 24h, 7d, or explicit start/end.")
    end_at = datetime.now(UTC)
    return AnalyticsWindow(end_at - WINDOWS[selected], end_at)


def _limit(value: int | None) -> int:
    selected = value if value is not None else 20
    if selected <= 0 or selected > MAX_LIMIT:
        raise _invalid(f"limit must be between 1 and {MAX_LIMIT}.")
    return selected


def _trace_json(summary: Any) -> dict[str, object]:
    return {
        "trace_id": str(summary.trace_id),
        "name": summary.name,
        "session_id": summary.session_id,
        "status": summary.status,
        "started_at": summary.started_at.isoformat(),
        "ended_at": summary.ended_at.isoformat() if summary.ended_at else None,
        "duration_ms": round(summary.duration_seconds * 1000, 3)
        if summary.duration_seconds is not None
        else None,
        "span_count": summary.span_count,
        "event_count": summary.event_count,
    }


def _finding_json(finding: Any) -> dict[str, object]:
    return {
        "result_id": str(finding.result_id),
        "trace_id": str(finding.trace_id),
        "evaluation_type": finding.evaluation_type,
        "code": finding.code,
        "severity": finding.severity,
        "message": finding.message,
        "created_at": finding.created_at.isoformat(),
    }


def _overview_json(value: OverviewAnalytics) -> dict[str, object]:
    return {
        "window": {"start": value.window.start.isoformat(), "end": value.window.end.isoformat()},
        "traces": {
            "count": value.trace_count,
            "completed_count": value.completed_trace_count,
            "error_count": value.error_trace_count,
            "error_rate": value.error_rate,
        },
        "latency_ms": {
            "p50": value.latency_p50_ms,
            "p95": value.latency_p95_ms,
            "p99": value.latency_p99_ms,
        },
        "reported_tokens": {
            "spans_with_usage": value.reported_tokens.spans_with_usage,
            "input": value.reported_tokens.input_tokens,
            "output": value.reported_tokens.output_tokens,
            "total": value.reported_tokens.total_tokens,
        },
        "evaluations": {
            "count": value.evaluation_count,
            "status_counts": dict(value.evaluation_status_counts),
        },
        "findings": {"counts": dict(value.finding_counts)},
        "recent_traces": [_trace_json(item) for item in value.recent_traces],
        "recent_findings": [_finding_json(item) for item in value.recent_findings],
    }


def _timeseries_json(value: tuple[TimeseriesPoint, ...]) -> dict[str, object]:
    return {
        "items": [
            {
                "bucket_start": item.bucket_start.isoformat(),
                "trace_count": item.trace_count,
                "error_count": item.error_count,
                "completed_count": item.completed_count,
                "average_latency_ms": item.average_latency_ms,
                "reported_total_tokens": item.reported_total_tokens,
            }
            for item in value
        ]
    }


def _evaluation_json(value: EvaluationAnalytics) -> dict[str, object]:
    return {
        "window": {"start": value.window.start.isoformat(), "end": value.window.end.isoformat()},
        "groups": [
            {
                "evaluation_type": group.evaluation_type,
                "evaluator_name": group.evaluator_name,
                "evaluator_version": group.evaluator_version,
                "evaluation_mode": group.evaluation_mode,
                "config_fingerprint": group.config_fingerprint,
                "judge_profile": group.judge_profile,
                "provider": group.provider,
                "model": group.model,
                "prompt_version": group.prompt_version,
                "result_count": group.result_count,
                "status_counts": dict(group.status_counts),
            }
            for group in value.groups
        ],
        "finding_counts": dict(value.finding_counts),
    }


@router.get("/v1/analytics/overview")
async def overview(
    request: Request,
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    analytics_window = _window(window, start, end)
    selected_limit = _limit(limit)
    try:
        result = _repository(request).overview(context.project_id, analytics_window, selected_limit)
    except StorageUnavailableError:
        raise GatewayError(
            code="analytics_unavailable",
            message="Analytics is temporarily unavailable.",
            status_code=503,
        ) from None
    return JSONResponse(status_code=200, content=_overview_json(result))


@router.get("/v1/analytics/timeseries")
async def timeseries(
    request: Request,
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    analytics_window = _window(window, start, end)
    try:
        result = _repository(request).timeseries(context.project_id, analytics_window)
    except StorageUnavailableError:
        raise GatewayError(
            code="analytics_unavailable",
            message="Analytics is temporarily unavailable.",
            status_code=503,
        ) from None
    return JSONResponse(status_code=200, content=_timeseries_json(result))


@router.get("/v1/analytics/evaluations")
async def evaluations(
    request: Request,
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    evaluation_type: str | None = None,
    result_status: str | None = None,
    limit: int | None = None,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    analytics_window = _window(window, start, end)
    selected_limit = _limit(limit)
    for name, value in (("evaluation_type", evaluation_type), ("result_status", result_status)):
        if value is not None and (not value or len(value) > 255):
            raise _invalid(f"{name} must be a non-empty bounded value.")
    try:
        result = _repository(request).evaluations(
            context.project_id,
            analytics_window,
            evaluation_type,
            result_status,
            selected_limit,
        )
    except StorageUnavailableError:
        raise GatewayError(
            code="analytics_unavailable",
            message="Analytics is temporarily unavailable.",
            status_code=503,
        ) from None
    return JSONResponse(status_code=200, content=_evaluation_json(result))


@router.get("/v1/runtime/summary")
async def runtime_summary(
    request: Request,
    limit: int | None = None,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    selected_limit = _limit(limit)
    gateway = request.app.state.gateway
    repository = _repository(request)
    try:
        raw = repository.runtime_jobs(context.project_id, selected_limit)
        database_ready = bool(getattr(gateway.repository, "check_ready", lambda: False)())
        redis_ready = bool(getattr(gateway.dispatcher, "check_ready", lambda: False)())
    except StorageUnavailableError:
        raise GatewayError(
            code="runtime_unavailable",
            message="Runtime summary is temporarily unavailable.",
            status_code=503,
        ) from None
    data = raw
    failures = cast(tuple[Any, ...], data["recent_failures"])
    workers = cast(tuple[Mapping[str, Any], ...], data.get("workers", ()))
    worker_health = "not_available"
    if workers:
        worker_health = (
            "healthy" if any(item.get("health") == "healthy" for item in workers) else "stale"
        )
    return JSONResponse(
        status_code=200,
        content={
            "job_state_counts": dict(cast(dict[str, int], data["job_state_counts"])),
            "recent_failures": [
                {
                    "job_id": str(item.job_id),
                    "evaluation_type": item.evaluation_type,
                    "state": item.state,
                    "error_code": item.error_code,
                    "message": item.message,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in failures
            ],
            "database": "ok" if database_ready else "unavailable",
            "redis": "ok" if redis_ready else "unavailable",
            "worker": worker_health,
            "workers": [
                {
                    "worker_id": str(item["worker_id"]),
                    "worker_type": str(item["worker_type"]),
                    "started_at": cast(Any, item["started_at"]).isoformat(),
                    "last_seen": cast(Any, item["last_seen"]).isoformat(),
                    "state": str(item["state"]),
                    "health": str(item["health"]),
                }
                for item in workers
            ],
            "read_only": True,
        },
    )


def _lookup_trace(repo: Any, project_id: str, trace_id: UUID) -> Any | None:
    if repo is None:
        return None
    if hasattr(repo, "get_trace") and callable(repo.get_trace):
        return repo.get_trace(project_id, trace_id)
    if hasattr(repo, "get") and callable(repo.get):
        return repo.get(project_id, trace_id)
    return None


def _list_traces_for_hotspots(repo: Any, project_id: str, limit: int = 50) -> list[Any]:
    if repo is None:
        return []
    if hasattr(repo, "list_traces") and callable(repo.list_traces):
        return list(repo.list_traces(project_id, limit=limit))
    if hasattr(repo, "traces"):
        return [t for t in repo.traces if getattr(t, "project_id", "") == project_id][:limit]
    return []


@router.get("/v1/traces/{trace_id}/profile")
async def get_trace_profile(
    trace_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    repo = getattr(request.app.state.gateway, "repository", None)
    trace = _lookup_trace(repo, context.project_id, trace_id)
    if trace is None:
        raise GatewayError(code="not_found", message="Trace not found.", status_code=404)
    profile = profile_trace(trace)
    return JSONResponse(
        status_code=200,
        content={
            "trace_id": str(profile.trace_id),
            "total_duration_ms": profile.total_duration_ms,
            "critical_path_span_ids": [str(sid) for sid in profile.critical_path_span_ids],
            "critical_path_duration_ms": profile.critical_path_duration_ms,
            "latency_breakdown": {
                "llm_time_ms": profile.latency_breakdown.llm_time_ms,
                "tool_time_ms": profile.latency_breakdown.tool_time_ms,
                "network_time_ms": profile.latency_breakdown.network_time_ms,
                "overhead_time_ms": profile.latency_breakdown.overhead_time_ms,
                "total_duration_ms": profile.latency_breakdown.total_duration_ms,
                "llm_percentage": round(profile.latency_breakdown.llm_percentage, 1),
                "tool_percentage": round(profile.latency_breakdown.tool_percentage, 1),
                "overhead_percentage": round(profile.latency_breakdown.overhead_percentage, 1),
            },
            "token_breakdown": {
                "prompt_tokens": profile.prompt_tokens,
                "completion_tokens": profile.completion_tokens,
                "total_tokens": profile.total_tokens,
            },
            "span_profiles": [
                {
                    "span_id": str(sp.span_id),
                    "name": sp.name,
                    "span_type": sp.span_type,
                    "category": sp.category,
                    "duration_ms": sp.duration_ms,
                    "self_time_ms": sp.self_time_ms,
                    "is_critical_path": sp.is_critical_path,
                    "parent_span_id": str(sp.parent_span_id) if sp.parent_span_id else None,
                    "child_span_ids": [str(cid) for cid in sp.child_span_ids],
                    "tokens": sp.total_tokens,
                }
                for sp in profile.span_profiles
            ],
            "hotspots": [
                {
                    "span_id": str(h.span_id),
                    "name": h.name,
                    "hotspot_type": h.hotspot_type,
                    "severity": h.severity,
                    "description": h.description,
                    "impact_percentage": h.impact_percentage,
                }
                for h in profile.hotspots
            ],
        },
    )


@router.get("/v1/analytics/hotspots")
async def get_project_hotspots(
    request: Request,
    limit: int = 50,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    repo = getattr(request.app.state.gateway, "repository", None)
    traces = _list_traces_for_hotspots(repo, context.project_id, limit=min(limit, 100))
    summary = aggregate_project_hotspots(context.project_id, traces)
    return JSONResponse(
        status_code=200,
        content={
            "project_id": summary.project_id,
            "analyzed_traces_count": summary.analyzed_traces_count,
            "slowest_tools": [
                {
                    "tool_name": t.tool_name,
                    "call_count": t.call_count,
                    "avg_duration_ms": t.avg_duration_ms,
                    "p95_duration_ms": t.p95_duration_ms,
                    "max_duration_ms": t.max_duration_ms,
                    "error_rate": t.error_rate,
                }
                for t in summary.slowest_tools
            ],
            "heaviest_token_spans": [
                {
                    "name": s.name,
                    "call_count": s.call_count,
                    "total_tokens": s.total_tokens,
                    "avg_tokens": s.avg_tokens,
                    "avg_prompt_tokens": s.avg_prompt_tokens,
                    "avg_completion_tokens": s.avg_completion_tokens,
                }
                for s in summary.heaviest_token_spans
            ],
            "top_errors": [
                {
                    "error_message": e.error_message,
                    "occurrences": e.occurrences,
                    "affected_span_types": list(e.affected_span_types),
                }
                for e in summary.top_errors
            ],
        },
    )
