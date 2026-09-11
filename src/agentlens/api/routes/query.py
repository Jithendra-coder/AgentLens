"""Project-scoped trace detail and summary query endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.domain import Status
from agentlens.storage.contracts import StorageUnavailableError
from agentlens.storage.repository import (
    InvalidCursorError,
    TraceQuery,
    TraceQueryRepository,
    TraceSummary,
)

from ..auth import AuthContext
from ..dependencies import require_auth
from ..errors import GatewayError

router = APIRouter(prefix="/v1")
AUTH_DEPENDENCY = Depends(require_auth)


def _repository(request: Request) -> TraceQueryRepository:
    repository = request.app.state.gateway.repository
    if not callable(getattr(repository, "get_trace", None)) or not callable(
        getattr(repository, "query_traces", None)
    ):
        raise GatewayError(
            code="query_unavailable",
            message="Trace query is not configured.",
            status_code=503,
        )
    return cast(TraceQueryRepository, repository)


def _invalid_query(message: str = "Trace query is invalid.") -> GatewayError:
    return GatewayError(code="invalid_query", message=message, status_code=400)


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _invalid_query("Trace time filters must be valid ISO-8601 timestamps.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _invalid_query("Trace time filters must include a timezone.")
    return parsed.astimezone(UTC)


def _summary_json(summary: TraceSummary) -> dict[str, object]:
    return {
        "trace_id": str(summary.trace_id),
        "name": summary.name,
        "session_id": summary.session_id,
        "status": summary.status,
        "started_at": summary.started_at.isoformat(),
        "ended_at": (summary.ended_at.isoformat() if summary.ended_at is not None else None),
        "duration": summary.duration_seconds,
        "span_count": summary.span_count,
        "event_count": summary.event_count,
    }


@router.get("/traces/{trace_id}")
async def get_trace(
    request: Request,
    trace_id: str,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    try:
        parsed_trace_id = UUID(trace_id)
    except (ValueError, AttributeError):
        raise _invalid_query("trace_id must be a valid UUID.") from None
    try:
        trace = _repository(request).get_trace(context.project_id, parsed_trace_id)
    except StorageUnavailableError:
        raise GatewayError(
            code="query_unavailable",
            message="Trace query is temporarily unavailable.",
            status_code=503,
        ) from None
    if trace is None:
        raise GatewayError(
            code="trace_not_found",
            message="Trace was not found.",
            status_code=404,
        )
    return JSONResponse(status_code=200, content=trace.to_dict())


@router.get("/traces")
async def list_traces(
    request: Request,
    started_from: str | None = None,
    started_to: str | None = None,
    status: str | None = None,
    name: str | None = None,
    session_id: str | None = None,
    span_type: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    config = request.app.state.gateway.config
    if limit is None:
        page_limit = config.query_default_limit
    elif limit <= 0 or limit > config.query_max_limit:
        raise _invalid_query("limit must be between 1 and the configured maximum.")
    else:
        page_limit = limit
    if status is not None:
        try:
            Status(status)
        except ValueError:
            raise _invalid_query("status must be one of: unset, ok, error.") from None
    if name is not None and not name:
        raise _invalid_query("name must not be empty.")
    if session_id is not None and not session_id:
        raise _invalid_query("session_id must not be empty.")
    if span_type is not None and not span_type.strip():
        raise _invalid_query("span_type must not be empty.")
    query = TraceQuery(
        started_from=_parse_time(started_from),
        started_to=_parse_time(started_to),
        status=status,
        name=name,
        session_id=session_id,
        span_type=span_type,
        limit=page_limit,
        cursor=cursor,
    )
    if query.started_from is not None and query.started_to is not None:
        if query.started_from > query.started_to:
            raise _invalid_query("started_from cannot be after started_to.")
    try:
        page = _repository(request).query_traces(context.project_id, query)
    except InvalidCursorError:
        raise GatewayError(
            code="invalid_cursor",
            message="Trace cursor is invalid.",
            status_code=400,
        ) from None
    except StorageUnavailableError:
        raise GatewayError(
            code="query_unavailable",
            message="Trace query is temporarily unavailable.",
            status_code=503,
        ) from None
    return JSONResponse(
        status_code=200,
        content={
            "items": [_summary_json(item) for item in page.items],
            "next_cursor": page.next_cursor,
        },
    )
