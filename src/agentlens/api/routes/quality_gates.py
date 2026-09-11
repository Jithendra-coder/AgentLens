"""Project-scoped quality-gate policy and decision APIs."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.quality_gates.repository import (
    PostgresQualityGateRepository,
    QualityGateIdempotencyConflict,
    QualityGateNotFoundError,
    QualityGateStorageError,
    QualityGateValidationError,
    request_fingerprint,
)

from ..auth import AuthContext
from ..dependencies import require_auth
from ..errors import GatewayError
from .traces import _json_body

router = APIRouter(prefix="/v1")
AUTH_DEPENDENCY = Depends(require_auth)


def _repository(request: Request) -> PostgresQualityGateRepository:
    repository = request.app.state.gateway.quality_gate_repository
    if repository is None:
        raise GatewayError(
            code="quality_gate_unavailable",
            message="Quality gate storage is temporarily unavailable.",
            status_code=503,
        )
    return cast(PostgresQualityGateRepository, repository)


def _uuid(value: object, resource: str) -> UUID:
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        raise GatewayError(
            code="not_found", message=f"The {resource} was not found.", status_code=404
        ) from None


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise GatewayError(
            code="invalid_quality_gate", message=f"{field} is invalid.", status_code=422
        )
    return value.strip()


def _error(exc: Exception) -> GatewayError:
    if isinstance(exc, QualityGateNotFoundError):
        return GatewayError(
            code="not_found",
            message="The requested quality gate resource was not found.",
            status_code=404,
        )
    if isinstance(exc, QualityGateIdempotencyConflict):
        return GatewayError(
            code="quality_gate_idempotency_conflict",
            message="Idempotency key was used with a different request.",
            status_code=409,
        )
    if isinstance(exc, QualityGateValidationError):
        return GatewayError(code="invalid_quality_gate", message=str(exc), status_code=422)
    if isinstance(exc, QualityGateStorageError):
        return GatewayError(
            code="quality_gate_unavailable",
            message="Quality gate storage is temporarily unavailable.",
            status_code=503,
        )
    return GatewayError(
        code="quality_gate_unavailable",
        message="Quality gate runtime is temporarily unavailable.",
        status_code=503,
    )


@router.post("/quality-gate-policies", status_code=201)
async def create_policy(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_quality_gate", message="Policy body is invalid.", status_code=422
        )
    name = _text(payload.get("name"), "name", 255)
    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        raise GatewayError(
            code="invalid_quality_gate", message="description is invalid.", status_code=422
        )
    try:
        body = _repository(request).create_policy(
            context.project_id,
            name,
            description,
            payload.get("rules", []),
            payload.get("required_metrics"),
        )
    except Exception as exc:
        raise _error(exc) from None
    body["request_id"] = request.state.request_id
    return JSONResponse(status_code=201, content=body)


@router.get("/quality-gate-policies")
async def list_policies(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    try:
        items = _repository(request).list_policies(context.project_id, 100)
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": list(items)})


@router.get("/quality-gate-policies/{policy_id}")
async def get_policy(
    policy_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_policy(
            context.project_id, _uuid(policy_id, "quality gate policy")
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.post("/quality-gate-decisions", status_code=201)
async def create_decision(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_quality_gate", message="Decision body is invalid.", status_code=422
        )
    regression_run_id = _uuid(payload.get("regression_run_id"), "regression run")
    policy_id = _uuid(
        payload.get("gate_policy_id", payload.get("policy_id")), "quality gate policy"
    )
    key = request.headers.get("idempotency-key")
    if key is not None and (not key or len(key) > 255):
        raise GatewayError(
            code="invalid_quality_gate", message="Idempotency key is invalid.", status_code=422
        )
    fingerprint = request_fingerprint(
        {"regression_run_id": str(regression_run_id), "gate_policy_id": str(policy_id)}
    )
    try:
        body = _repository(request).create_decision(
            project_id=context.project_id,
            regression_run_id=regression_run_id,
            gate_policy_id=policy_id,
            idempotency_key=key,
            request_fingerprint_value=fingerprint,
        )
        duplicate = bool(body.pop("_duplicate", False))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    body["request_id"] = request.state.request_id
    body["duplicate"] = duplicate
    return JSONResponse(status_code=201, content=body)


@router.get("/quality-gate-decisions")
async def list_decisions(
    request: Request,
    status: str | None = None,
    policy: str | None = None,
    regression_run: str | None = None,
    limit: int = 100,
    context: AuthContext = AUTH_DEPENDENCY,
) -> JSONResponse:
    if not 1 <= limit <= 100:
        raise GatewayError(
            code="invalid_quality_gate", message="limit is invalid.", status_code=422
        )
    if status not in {None, "passed", "failed", "indeterminate", "error"}:
        raise GatewayError(
            code="invalid_quality_gate", message="status is invalid.", status_code=422
        )
    try:
        policy_id = _uuid(policy, "quality gate policy") if policy else None
        run_id = _uuid(regression_run, "regression run") if regression_run else None
        items = _repository(request).list_decisions(
            context.project_id,
            limit=limit,
            status=status,
            policy_id=policy_id,
            regression_run_id=run_id,
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": list(items), "limit": limit})


@router.get("/quality-gate-decisions/{decision_id}")
async def get_decision(
    decision_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_decision(
            context.project_id, _uuid(decision_id, "quality gate decision")
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


__all__ = ["router"]
