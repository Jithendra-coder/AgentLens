"""Project-scoped regression policy and report APIs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.evaluation.handlers import HandlerRegistry
from agentlens.regression.repository import (
    PostgresRegressionRepository,
    RegressionIdempotencyConflict,
    RegressionNotFoundError,
    RegressionStorageError,
    RegressionValidationError,
    request_fingerprint,
)
from agentlens.regression.runtime import RegressionRedisUnavailable

from ..auth import AuthContext
from ..dependencies import require_auth
from ..errors import GatewayError
from .traces import _json_body

router = APIRouter(prefix="/v1")
AUTH_DEPENDENCY = Depends(require_auth)


def _repository(request: Request) -> PostgresRegressionRepository:
    repository = request.app.state.gateway.regression_repository
    if repository is None:
        raise GatewayError(
            code="regression_unavailable",
            message="Regression storage is temporarily unavailable.",
            status_code=503,
        )
    return cast(PostgresRegressionRepository, repository)


def _uuid(value: object, resource: str = "regression resource") -> UUID:
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        raise GatewayError(
            code="not_found", message=f"The {resource} was not found.", status_code=404
        ) from None


def _error(exc: Exception) -> GatewayError:
    if isinstance(exc, RegressionNotFoundError):
        return GatewayError(
            code="not_found",
            message="The requested regression resource was not found.",
            status_code=404,
        )
    if isinstance(exc, RegressionIdempotencyConflict):
        return GatewayError(
            code="regression_idempotency_conflict",
            message="Idempotency key was used with a different request.",
            status_code=409,
        )
    if isinstance(exc, RegressionValidationError):
        return GatewayError(code="invalid_regression", message=str(exc), status_code=422)
    if isinstance(exc, RegressionStorageError):
        return GatewayError(
            code="regression_unavailable",
            message="Regression storage is temporarily unavailable.",
            status_code=503,
        )
    return GatewayError(
        code="regression_unavailable",
        message="Regression runtime is temporarily unavailable.",
        status_code=503,
    )


def _validate_text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise GatewayError(
            code="invalid_regression", message=f"{field} is invalid.", status_code=422
        )
    return value.strip()


def _plan(
    payload: Mapping[str, object], registry: HandlerRegistry
) -> tuple[Mapping[str, object], ...]:
    raw = payload.get("evaluation_plan", [])
    if isinstance(raw, dict):
        required = raw.get("required_metrics", [])
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
            raise GatewayError(
                code="invalid_regression",
                message="required_metrics must be an array of strings.",
                status_code=422,
            )
        raw = [{"evaluation_type": item, "config": {}} for item in required]
    if not isinstance(raw, list):
        raise GatewayError(
            code="invalid_regression", message="evaluation_plan must be an array.", status_code=422
        )
    supported = set(registry.public_types())
    output: list[Mapping[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise GatewayError(
                code="invalid_regression",
                message="evaluation_plan entries must be objects.",
                status_code=422,
            )
        evaluation_type = item.get("evaluation_type")
        config = item.get("config", {})
        if not isinstance(evaluation_type, str) or evaluation_type not in supported:
            raise GatewayError(
                code="invalid_regression",
                message="evaluation type is not supported.",
                status_code=422,
            )
        if not isinstance(config, dict):
            raise GatewayError(
                code="invalid_regression",
                message="evaluation config must be an object.",
                status_code=422,
            )
        if set(item) - {"evaluation_type", "config"}:
            raise GatewayError(
                code="invalid_regression",
                message="evaluation_plan contains unknown fields.",
                status_code=422,
            )
        try:
            json.dumps(config, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError):
            raise GatewayError(
                code="invalid_regression",
                message="evaluation config is not valid JSON.",
                status_code=422,
            ) from None
        normalized = registry.get(evaluation_type).normalize_config(config)
        output.append({"evaluation_type": evaluation_type, "config": dict(normalized)})
    return tuple(output)


@router.post("/regression-policies", status_code=201)
async def create_policy(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_regression", message="Policy body is invalid.", status_code=422
        )
    name = _validate_text(payload.get("name"), "name", 255)
    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        raise GatewayError(
            code="invalid_regression", message="description is invalid.", status_code=422
        )
    try:
        body = _repository(request).create_policy(
            context.project_id, name, description, payload.get("rules")
        )
    except Exception as exc:
        raise _error(exc) from None
    body["request_id"] = request.state.request_id
    return JSONResponse(status_code=201, content=body)


@router.get("/regression-policies")
async def list_policies(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    try:
        items = _repository(request).list_policies(context.project_id, 100)
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": list(items)})


@router.get("/regression-policies/{policy_id}")
async def get_policy(
    policy_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_policy(
            context.project_id, _uuid(policy_id, "regression policy")
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.post("/regression-runs", status_code=202)
async def create_run(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_regression", message="Regression body is invalid.", status_code=422
        )
    baseline_id = _uuid(payload.get("baseline_replay_run_id"), "baseline replay run")
    candidate_id = _uuid(payload.get("candidate_replay_run_id"), "candidate replay run")
    policy_id = _uuid(payload.get("policy_id"), "regression policy")
    plan = _plan(payload, request.app.state.gateway.handler_registry)
    fingerprint_body = {
        "baseline_replay_run_id": str(baseline_id),
        "candidate_replay_run_id": str(candidate_id),
        "policy_id": str(policy_id),
        "evaluation_plan": [dict(item) for item in plan],
    }
    key = request.headers.get("idempotency-key")
    if key is not None and (not key or len(key) > 255):
        raise GatewayError(
            code="invalid_regression", message="Idempotency key is invalid.", status_code=422
        )
    try:
        body = _repository(request).create_run(
            project_id=context.project_id,
            baseline_run_id=baseline_id,
            candidate_run_id=candidate_id,
            policy_id=policy_id,
            evaluation_plan=plan,
            idempotency_key=key,
            request_fingerprint_value=request_fingerprint(fingerprint_body),
        )
        duplicate = bool(body.pop("_duplicate", False))
        if body["status"] == "queued":
            try:
                request.app.state.gateway.regression_dispatcher.dispatch(
                    UUID(str(body["regression_run_id"]))
                )
            except RegressionRedisUnavailable:
                pass
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    body["request_id"] = request.state.request_id
    body["duplicate"] = duplicate
    return JSONResponse(status_code=202, content=body)


@router.get("/regression-runs")
async def list_runs(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    try:
        items = _repository(request).list_runs(context.project_id, 100)
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": list(items)})


@router.get("/regression-runs/{run_id}")
async def get_run(
    run_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_run(context.project_id, _uuid(run_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.get("/regression-runs/{run_id}/metrics")
async def list_metrics(
    run_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        items = _repository(request).list_metrics(context.project_id, _uuid(run_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": list(items)})


@router.get("/regression-runs/{run_id}/cases")
async def list_cases(
    run_id: str,
    request: Request,
    limit: int = 50,
    offset: int = 0,
    classification: str | None = None,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    if not 1 <= limit <= 100 or offset < 0:
        raise GatewayError(
            code="invalid_regression", message="limit or offset is invalid.", status_code=422
        )
    if classification not in {
        None,
        "compared",
        "candidate_execution_failed",
        "baseline_execution_failed",
        "improved",
        "unchanged",
        "regressed",
        "insufficient_data",
        "incompatible",
        "informational",
    }:
        raise GatewayError(
            code="invalid_regression", message="classification is invalid.", status_code=422
        )
    try:
        items = _repository(request).list_cases(
            context.project_id,
            _uuid(run_id),
            limit=limit,
            offset=offset,
            classification=classification,
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(
        status_code=200, content={"items": list(items), "limit": limit, "offset": offset}
    )


@router.get("/regression-runs/{run_id}/cases/{case_id}")
async def get_case(
    run_id: str, case_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_case(
            context.project_id, _uuid(run_id), _uuid(case_id, "regression case")
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)
