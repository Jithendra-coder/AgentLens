"""Project-scoped asynchronous evaluation job APIs."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.analytics.repository import AnalyticsWindow
from agentlens.evaluation.errors import (
    JobIdempotencyConflict,
    JobStorageUnavailable,
    RedisUnavailableError,
    TraceNotFoundError,
)
from agentlens.evaluation.repository import hash_idempotency_key, request_fingerprint
from agentlens.evaluation.result_repository import (
    EvaluationResultListItem,
    EvaluationResultSummary,
)
from agentlens.evaluation.results import ResultStatus
from agentlens.evaluation.types import EvaluationJob

from ..auth import AuthContext
from ..dependencies import require_auth
from ..errors import GatewayError
from .traces import _json_body

router = APIRouter(prefix="/v1")
AUTH_DEPENDENCY = Depends(require_auth)


def _invalid(message: str = "Evaluation request is invalid.") -> GatewayError:
    return GatewayError(code="invalid_evaluation", message=message, status_code=422)


def _job_body(
    request: Request,
    job: EvaluationJob,
    result_id: UUID | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "request_id": request.state.request_id,
        "job_id": str(job.job_id),
        "trace_id": str(job.trace_id),
        "state": job.state.value,
        "evaluation_type": job.evaluation_type,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "available_at": job.available_at.isoformat(),
        "last_error_code": job.last_error_code,
    }
    if result_id is not None:
        body["result_id"] = str(result_id)
    return body


def _require_runtime(request: Request) -> tuple[Any, Any, Any]:
    gateway = request.app.state.gateway
    if gateway.job_repository is None or not callable(
        getattr(gateway.job_repository, "create_job", None)
    ):
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation runtime is temporarily unavailable.",
            status_code=503,
        )
    if not callable(getattr(gateway.repository, "get_trace", None)):
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation runtime is temporarily unavailable.",
            status_code=503,
        )
    return gateway.job_repository, gateway.dispatcher, gateway.result_repository


def _require_result_runtime(request: Request) -> Any:
    repository = request.app.state.gateway.result_repository
    if repository is None or not callable(getattr(repository, "get_result", None)):
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation result storage is temporarily unavailable.",
            status_code=503,
        )
    return repository


def _result_summary(summary: EvaluationResultSummary) -> dict[str, object]:
    return {
        "result_id": str(summary.result_id),
        "job_id": str(summary.job_id),
        "evaluation_type": summary.evaluation_type,
        "evaluator_name": summary.evaluator_name,
        "evaluator_version": summary.evaluator_version,
        "evaluation_mode": summary.evaluation_mode.value,
        "result_status": summary.result_status.value,
        "created_at": summary.created_at.isoformat(),
    }


def _result_item(item: EvaluationResultListItem) -> dict[str, object]:
    return {
        "result_id": str(item.result_id),
        "trace_id": str(item.trace_id),
        "evaluation_type": item.evaluation_type,
        "evaluator_name": item.evaluator_name,
        "evaluator_version": item.evaluator_version,
        "evaluation_mode": item.evaluation_mode.value,
        "result_status": item.result_status.value,
        "created_at": item.created_at.isoformat(),
    }


def _result_window(window: str | None, start: str | None, end: str | None) -> AnalyticsWindow:
    if start is not None or end is not None:
        if start is None or end is None:
            raise _invalid("start and end must be provided together.")
        try:
            start_at = datetime.fromisoformat(start)
            end_at = datetime.fromisoformat(end)
        except ValueError:
            raise _invalid("start and end must be valid ISO-8601 timestamps.") from None
        if (
            start_at.tzinfo is None
            or start_at.utcoffset() is None
            or end_at.tzinfo is None
            or end_at.utcoffset() is None
        ):
            raise _invalid("start and end must include a timezone.")
        try:
            return AnalyticsWindow(start_at.astimezone(UTC), end_at.astimezone(UTC))
        except ValueError as exc:
            raise _invalid(str(exc)) from None
    durations = {"1h": timedelta(hours=1), "24h": timedelta(days=1), "7d": timedelta(days=7)}
    selected = window or "24h"
    if selected not in durations:
        raise _invalid("window must be one of: 1h, 24h, or 7d.")
    end_at = datetime.now(UTC)
    return AnalyticsWindow(end_at - durations[selected], end_at)


def _parse_request(
    request: Request,
    payload: object,
) -> tuple[str, Mapping[str, object], int, float, int]:
    if not isinstance(payload, dict):
        raise _invalid()
    evaluation_type = payload.get("evaluation_type")
    config = payload.get("config", {})
    if (
        not isinstance(evaluation_type, str)
        or not evaluation_type.strip()
        or len(evaluation_type) > 255
    ):
        raise _invalid()
    if not isinstance(config, dict):
        raise _invalid()
    try:
        json.dumps(config, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _invalid() from None
    runtime = request.app.state.gateway.runtime_config
    timeout_seconds = payload.get(
        "timeout_seconds",
        runtime.default_timeout_seconds if runtime is not None else 5.0,
    )
    max_attempts = payload.get(
        "max_attempts",
        runtime.default_max_attempts if runtime is not None else 3,
    )
    priority = payload.get("priority", 0)
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not math.isfinite(float(timeout_seconds))
        or not 0 < float(timeout_seconds) <= 3600
        or runtime is not None
        and float(timeout_seconds) > runtime.lease_seconds
    ):
        raise _invalid()
    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or not 1 <= max_attempts <= 10
    ):
        raise _invalid()
    if not isinstance(priority, int) or isinstance(priority, bool) or not -1000 <= priority <= 1000:
        raise _invalid()
    return (
        evaluation_type,
        cast(Mapping[str, object], config),
        priority,
        float(timeout_seconds),
        max_attempts,
    )


@router.post("/traces/{trace_id}/evaluations", status_code=202)
async def create_evaluation(
    trace_id: str,
    request: Request,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    try:
        parsed_trace_id = UUID(trace_id)
    except ValueError:
        raise GatewayError(
            code="trace_not_found",
            message="Trace was not found.",
            status_code=404,
        ) from None
    repository, dispatcher, _ = _require_runtime(request)
    evaluation_type, config, priority, timeout_seconds, max_attempts = _parse_request(
        request,
        await _json_body(request),
    )
    registry = request.app.state.gateway.handler_registry
    if evaluation_type != "noop" and evaluation_type not in registry.public_types():
        raise GatewayError(
            code="unsupported_evaluation_type",
            message="Evaluation type is not supported.",
            status_code=422,
        )
    try:
        config = registry.get(evaluation_type).normalize_config(config)
    except ValueError:
        raise _invalid("Evaluation configuration is invalid.") from None
    key = request.headers.get("idempotency-key")
    if key is not None and (not key or len(key) > 255):
        raise _invalid()
    key_hash = hash_idempotency_key(key) if key is not None else None
    fingerprint = request_fingerprint(
        evaluation_type,
        config,
        priority,
        timeout_seconds,
        max_attempts,
    )
    try:
        creation = repository.create_job(
            project_id=context.project_id,
            trace_id=parsed_trace_id,
            evaluation_type=evaluation_type,
            config=config,
            priority=priority,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            idempotency_key_hash=key_hash,
            request_fingerprint_value=fingerprint if key_hash is not None else None,
        )
    except TraceNotFoundError:
        raise GatewayError(
            code="trace_not_found",
            message="Trace was not found.",
            status_code=404,
        ) from None
    except JobIdempotencyConflict:
        raise GatewayError(
            code="job_idempotency_conflict",
            message="Idempotency key was used with a different request.",
            status_code=409,
        ) from None
    except JobStorageUnavailable:
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation runtime is temporarily unavailable.",
            status_code=503,
        ) from None
    try:
        dispatcher.dispatch(creation.job.job_id)
    except RedisUnavailableError:
        pass
    return JSONResponse(status_code=202, content=_job_body(request, creation.job))


@router.get("/evaluation-jobs/{job_id}")
async def get_evaluation_job(
    job_id: str,
    request: Request,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    repository, _, result_repository = _require_runtime(request)
    try:
        parsed_job_id = UUID(job_id)
    except ValueError:
        raise GatewayError(
            code="job_not_found",
            message="Evaluation job was not found.",
            status_code=404,
        ) from None
    try:
        job = repository.get_job(context.project_id, parsed_job_id)
    except JobStorageUnavailable:
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation runtime is temporarily unavailable.",
            status_code=503,
        ) from None
    if job is None:
        raise GatewayError(
            code="job_not_found",
            message="Evaluation job was not found.",
            status_code=404,
        )
    result_id = None
    if job.state.value == "succeeded" and callable(
        getattr(result_repository, "get_result_for_job", None)
    ):
        try:
            result = result_repository.get_result_for_job(context.project_id, parsed_job_id)
        except JobStorageUnavailable:
            raise GatewayError(
                code="evaluation_unavailable",
                message="Evaluation runtime is temporarily unavailable.",
                status_code=503,
            ) from None
        result_id = result.result_id if result is not None else None
    return JSONResponse(status_code=200, content=_job_body(request, job, result_id))


@router.get("/evaluation-results")
async def list_evaluation_results_in_window(
    request: Request,
    window: str | None = None,
    start: str | None = None,
    end: str | None = None,
    evaluation_type: str | None = None,
    result_status: str | None = None,
    limit: int = 50,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    if limit <= 0 or limit > 100:
        raise _invalid("limit must be between 1 and 100.")
    if evaluation_type is not None and (not evaluation_type or len(evaluation_type) > 255):
        raise _invalid()
    if result_status is not None:
        try:
            ResultStatus(result_status)
        except ValueError:
            raise _invalid("result_status is invalid.") from None
    analytics_window = _result_window(window, start, end)
    repository = _require_result_runtime(request)
    try:
        items = repository.list_results_in_window(
            context.project_id,
            analytics_window.start,
            analytics_window.end,
            evaluation_type,
            result_status,
            limit,
        )
    except JobStorageUnavailable:
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation result storage is temporarily unavailable.",
            status_code=503,
        ) from None
    return JSONResponse(
        status_code=200,
        content={
            "window": {
                "start": analytics_window.start.isoformat(),
                "end": analytics_window.end.isoformat(),
            },
            "items": [_result_item(item) for item in items],
        },
    )


@router.get("/evaluation-results/{result_id}")
async def get_evaluation_result(
    result_id: str,
    request: Request,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    repository = _require_result_runtime(request)
    try:
        parsed_result_id = UUID(result_id)
    except ValueError:
        raise GatewayError(
            code="result_not_found",
            message="Evaluation result was not found.",
            status_code=404,
        ) from None
    try:
        result = repository.get_result(context.project_id, parsed_result_id)
    except JobStorageUnavailable:
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation result storage is temporarily unavailable.",
            status_code=503,
        ) from None
    if result is None:
        raise GatewayError(
            code="result_not_found",
            message="Evaluation result was not found.",
            status_code=404,
        )
    return JSONResponse(status_code=200, content=result.to_dict())


@router.get("/traces/{trace_id}/evaluation-results")
async def list_evaluation_results(
    trace_id: str,
    request: Request,
    limit: int = 50,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    repository = getattr(request.app.state.gateway, "result_repository", None)
    if repository is None or not callable(getattr(repository, "get_result", None)):
        return JSONResponse(status_code=200, content={"items": []})
    if limit <= 0 or limit > 200:
        raise _invalid("limit must be between 1 and 200.")
    try:
        parsed_trace_id = UUID(trace_id)
    except ValueError:
        raise GatewayError(
            code="trace_not_found",
            message="Trace was not found.",
            status_code=404,
        ) from None
    trace_repository = request.app.state.gateway.repository
    try:
        trace = trace_repository.get_trace(context.project_id, parsed_trace_id)
    except Exception:
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation result storage is temporarily unavailable.",
            status_code=503,
        ) from None
    if trace is None:
        raise GatewayError(
            code="trace_not_found",
            message="Trace was not found.",
            status_code=404,
        )
    try:
        summaries = repository.list_results(context.project_id, parsed_trace_id, limit)
    except JobStorageUnavailable:
        raise GatewayError(
            code="evaluation_unavailable",
            message="Evaluation result storage is temporarily unavailable.",
            status_code=503,
        ) from None
    return JSONResponse(
        status_code=200,
        content={"items": [_result_summary(summary) for summary in summaries]},
    )
