"""Project-scoped replay APIs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.domain import JSONValue
from agentlens.replay.models import ReplayManifest, ReplayMode, ReproducibilityStatus
from agentlens.replay.repository import (
    PostgresReplayRepository,
    ReplayIdempotencyConflict,
    ReplayNotFoundError,
    ReplayStorageError,
    ReplayValidationError,
    request_fingerprint,
)
from agentlens.replay.runtime import ReplayRedisUnavailable

from ..auth import AuthContext
from ..dependencies import require_auth
from ..errors import GatewayError
from .traces import _json_body

router = APIRouter(prefix="/v1")
AUTH_DEPENDENCY = Depends(require_auth)


def _repository(request: Request) -> PostgresReplayRepository:
    repository = request.app.state.gateway.replay_repository
    if repository is None:
        raise GatewayError(
            code="replay_unavailable",
            message="Replay storage is temporarily unavailable.",
            status_code=503,
        )
    return cast(PostgresReplayRepository, repository)


def _uuid(value: object) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise GatewayError(
            code="replay_not_found", message="Replay run was not found.", status_code=404
        ) from None


def _error(exc: Exception) -> GatewayError:
    if isinstance(exc, ReplayNotFoundError):
        return GatewayError(
            code="not_found",
            message="The requested replay resource was not found.",
            status_code=404,
        )
    if isinstance(exc, ReplayIdempotencyConflict):
        return GatewayError(
            code="replay_idempotency_conflict",
            message="Idempotency key was used with a different request.",
            status_code=409,
        )
    if isinstance(exc, ReplayValidationError):
        return GatewayError(code="invalid_replay", message=str(exc), status_code=422)
    if isinstance(exc, ReplayStorageError):
        return GatewayError(
            code="replay_unavailable",
            message="Replay storage is temporarily unavailable.",
            status_code=503,
        )
    return GatewayError(
        code="replay_unavailable",
        message="Replay runtime is temporarily unavailable.",
        status_code=503,
    )


def _manifest(
    payload: Mapping[str, object],
    *,
    version_id: UUID,
    checksum: str,
    profile_id: str,
    target_version: str,
    mode: ReplayMode,
) -> ReplayManifest:
    raw = payload.get("manifest", {})
    if not isinstance(raw, Mapping):
        raise GatewayError(
            code="invalid_replay", message="manifest must be a JSON object.", status_code=422
        )
    status_value = raw.get("reproducibility_status", "partial")
    try:
        status = ReproducibilityStatus(str(status_value))
    except ValueError:
        raise GatewayError(
            code="invalid_replay", message="reproducibility_status is invalid.", status_code=422
        ) from None

    def mapping(name: str) -> Mapping[str, JSONValue]:
        value = raw.get(name, {})
        if not isinstance(value, Mapping):
            raise GatewayError(
                code="invalid_replay",
                message=f"manifest.{name} must be an object.",
                status_code=422,
            )
        return cast(Mapping[str, JSONValue], value)

    def strings(name: str) -> tuple[str, ...]:
        value = raw.get(name, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise GatewayError(
                code="invalid_replay",
                message=f"manifest.{name} must be an array of strings.",
                status_code=422,
            )
        return tuple(value)

    reason = raw.get("best_effort_reason")
    if reason is not None and not isinstance(reason, str):
        raise GatewayError(
            code="invalid_replay", message="best_effort_reason is invalid.", status_code=422
        )
    try:
        return ReplayManifest(
            dataset_version_id=version_id,
            dataset_checksum=checksum,
            target_profile_id=profile_id,
            target_version=target_version,
            replay_mode=mode,
            reproducibility_status=status,
            application=mapping("application"),
            prompt=mapping("prompt"),
            model=mapping("model"),
            retriever=mapping("retriever"),
            tools=mapping("tools"),
            environment=mapping("environment"),
            changed_dimensions=strings("changed_dimensions"),
            unknown_fields=strings("unknown_fields"),
            best_effort_reason=reason,
        )
    except ValueError as exc:
        raise GatewayError(code="invalid_replay", message=str(exc), status_code=422) from None


@router.get("/replay-target-profiles")
async def list_target_profiles(
    request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    profiles = request.app.state.gateway.replay_target_registry.list(context.project_id)
    return JSONResponse(
        status_code=200,
        content={
            "items": [
                {
                    "profile_id": item.profile_id,
                    "name": item.name,
                    "target_type": item.target_type,
                    "version": item.version,
                    "safety_class": item.safety_class,
                    "configuration_reference": item.configuration_reference,
                }
                for item in profiles
            ]
        },
    )


@router.post("/replay-runs", status_code=202)
async def create_replay(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_replay", message="Replay body is invalid.", status_code=422
        )
    version_id = _uuid(payload.get("dataset_version_id"))
    profile_id = payload.get("target_profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        raise GatewayError(
            code="invalid_replay", message="target_profile_id is required.", status_code=422
        )
    try:
        mode = ReplayMode(str(payload.get("replay_mode", "best_effort")))
    except ValueError:
        raise GatewayError(
            code="invalid_replay", message="replay_mode is invalid.", status_code=422
        ) from None
    profile_item = request.app.state.gateway.replay_target_registry.get(
        context.project_id, profile_id
    )
    if profile_item is None:
        raise GatewayError(
            code="invalid_replay", message="Target profile is not authorized.", status_code=422
        )
    profile, _ = profile_item
    if profile.safety_class == "side_effectful":
        raise GatewayError(
            code="unsafe_target",
            message="Side-effectful targets are not allowed for replay.",
            status_code=422,
        )
    max_concurrency = payload.get("max_concurrency", 4)
    max_attempts = payload.get("max_attempts", 2)
    timeout_seconds = payload.get("timeout_seconds", 10.0)
    if (
        not isinstance(max_concurrency, int)
        or isinstance(max_concurrency, bool)
        or not 1 <= max_concurrency <= 32
        or not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or not 1 <= max_attempts <= 5
        or not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not 0 < float(timeout_seconds) <= 300
    ):
        raise GatewayError(
            code="invalid_replay", message="Execution options are invalid.", status_code=422
        )
    repository = _repository(request)
    try:
        version = repository.get_version(context.project_id, version_id)
        if version["status"] != "finalized" or not isinstance(version.get("content_checksum"), str):
            raise ReplayValidationError("replay requires a finalized dataset version")
        manifest = _manifest(
            cast(Mapping[str, object], payload),
            version_id=version_id,
            checksum=cast(str, version["content_checksum"]),
            profile_id=profile.profile_id,
            target_version=profile.version,
            mode=mode,
        )
        fingerprint_body = {
            "dataset_version_id": str(version_id),
            "target_profile_id": profile.profile_id,
            "replay_mode": mode.value,
            # Creation time belongs in the immutable persisted manifest, not in
            # the idempotency fingerprint for an otherwise identical request.
            "manifest": {
                key: value for key, value in manifest.to_dict().items() if key != "created_at"
            },
            "max_concurrency": max_concurrency,
            "timeout_seconds": float(timeout_seconds),
            "max_attempts": max_attempts,
        }
        creation = repository.create_replay(
            project_id=context.project_id,
            version_id=version_id,
            target_profile_id=profile.profile_id,
            target_name=profile.name,
            target_type=profile.target_type,
            target_version=profile.version,
            manifest=manifest,
            max_concurrency=max_concurrency,
            timeout_seconds=float(timeout_seconds),
            max_attempts=max_attempts,
            idempotency_key=request.headers.get("idempotency-key"),
            request_fingerprint_value=request_fingerprint(fingerprint_body),
        )
        if not creation.duplicate:
            for execution_id in creation.execution_ids:
                try:
                    request.app.state.gateway.replay_dispatcher.dispatch(execution_id)
                except ReplayRedisUnavailable:
                    break
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    body = repository.get_run(context.project_id, UUID(str(creation.run["replay_run_id"])))
    body.pop("executions", None)
    body["request_id"] = request.state.request_id
    return JSONResponse(status_code=202, content=body)


@router.get("/replay-runs")
async def list_replays(
    request: Request, limit: int = 100, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    if limit <= 0 or limit > 100:
        raise GatewayError(
            code="invalid_replay", message="limit must be between 1 and 100.", status_code=422
        )
    try:
        items = _repository(request).list_runs(context.project_id, limit)
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": list(items)})


@router.get("/replay-runs/{run_id}")
async def get_replay(
    run_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_run(context.project_id, _uuid(run_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.get("/replay-runs/{run_id}/cases")
async def list_replay_cases(
    run_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_run(context.project_id, _uuid(run_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": body.get("executions", [])})


@router.get("/replay-runs/{run_id}/cases/{execution_id}")
async def get_replay_case(
    run_id: str, execution_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_execution(
            context.project_id, _uuid(run_id), _uuid(execution_id)
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)
