"""Canonical trace snapshot ingestion routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.domain import Trace
from agentlens.exceptions import SerializationError, UnsupportedSchemaError, ValidationError

from ..auth import AuthContext
from ..dependencies import require_auth
from ..errors import GatewayError
from ..sink import TraceConflictError

router = APIRouter(prefix="/v1")
AUTH_DEPENDENCY = Depends(require_auth)


def _content_type_is_json(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    return content_type.lower().split(";", 1)[0].strip() == "application/json"


async def _json_body(request: Request) -> object:
    if not _content_type_is_json(request):
        raise GatewayError(
            code="unsupported_media_type",
            message="Content-Type must be application/json.",
            status_code=415,
        )
    try:
        return await request.json()
    except Exception:
        raise GatewayError(
            code="invalid_json",
            message="Request body is not valid JSON.",
            status_code=400,
        ) from None


def _reconstruct(value: object) -> Trace:
    try:
        return Trace.from_dict(value)
    except UnsupportedSchemaError:
        raise GatewayError(
            code="unsupported_schema",
            message="Trace schema is not supported.",
            status_code=422,
        ) from None
    except (SerializationError, ValidationError, TypeError, ValueError):
        raise GatewayError(
            code="invalid_trace",
            message="Trace payload is invalid.",
            status_code=422,
        ) from None


def _authorize(context: AuthContext, trace: Trace) -> None:
    if trace.project_id != context.project_id:
        raise GatewayError(
            code="project_forbidden",
            message="Trace project is not authorized for this key.",
            status_code=403,
        )


@router.post("/traces", status_code=202)
async def ingest_trace(
    request: Request,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    payload = await _json_body(request)
    trace = _reconstruct(payload)
    _authorize(context, trace)
    try:
        result = request.app.state.gateway.sink.ingest(trace)
    except TraceConflictError:
        raise GatewayError(
            code="trace_conflict",
            message="Trace identity conflicts with previously accepted content.",
            status_code=409,
        ) from None
    except Exception:
        raise GatewayError(
            code="ingestion_unavailable",
            message="Trace ingestion is temporarily unavailable.",
            status_code=503,
        ) from None
    return JSONResponse(
        status_code=202,
        content={
            "request_id": request.state.request_id,
            "trace_id": str(result.trace_id),
            "status": "accepted",
            "duplicate": result.duplicate,
        },
    )


@router.post("/traces/batch", status_code=202)
async def ingest_batch(
    request: Request,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict) or not isinstance(payload.get("traces"), list):
        raise GatewayError(
            code="invalid_batch",
            message="Batch body must contain a traces array.",
            status_code=400,
        )
    raw_traces = payload["traces"]
    if not raw_traces:
        raise GatewayError(
            code="invalid_batch",
            message="Batch must contain at least one trace.",
            status_code=400,
        )
    if len(raw_traces) > request.app.state.gateway.config.max_batch_size:
        raise GatewayError(
            code="batch_too_large",
            message="Batch exceeds the configured trace limit.",
            status_code=413,
        )
    traces: list[Trace] = []
    seen_ids: set[object] = set()
    for raw_trace in raw_traces:
        trace = _reconstruct(raw_trace)
        if trace.trace_id in seen_ids:
            raise GatewayError(
                code="duplicate_trace_id",
                message="Batch contains duplicate trace IDs.",
                status_code=400,
            )
        seen_ids.add(trace.trace_id)
        _authorize(context, trace)
        traces.append(trace)
    try:
        results = request.app.state.gateway.sink.ingest_many(traces)
    except TraceConflictError:
        raise GatewayError(
            code="trace_conflict",
            message="Batch contains a conflicting trace identity.",
            status_code=409,
        ) from None
    except Exception:
        raise GatewayError(
            code="ingestion_unavailable",
            message="Trace ingestion is temporarily unavailable.",
            status_code=503,
        ) from None
    duplicate_count = sum(result.duplicate for result in results)
    return JSONResponse(
        status_code=202,
        content={
            "request_id": request.state.request_id,
            "status": "accepted",
            "accepted_count": len(results) - duplicate_count,
            "duplicate_count": duplicate_count,
            "trace_ids": [str(result.trace_id) for result in results],
        },
    )
