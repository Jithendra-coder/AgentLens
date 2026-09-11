"""Project-scoped dataset and version APIs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from agentlens.domain import JSONValue
from agentlens.domain.types import thaw_payload
from agentlens.replay.repository import (
    PostgresReplayRepository,
    ReplayImmutableError,
    ReplayNotFoundError,
    ReplayValidationError,
)
from agentlens.storage.contracts import canonical_fingerprint

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
            code="dataset_unavailable",
            message="Dataset storage is temporarily unavailable.",
            status_code=503,
        )
    return cast(PostgresReplayRepository, repository)


def _uuid(value: str, code: str = "not_found") -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise GatewayError(
            code=code, message="The requested resource was not found.", status_code=404
        ) from None


def _error(exc: Exception) -> GatewayError:
    if isinstance(exc, ReplayNotFoundError):
        return GatewayError(
            code="not_found", message="The requested resource was not found.", status_code=404
        )
    if isinstance(exc, ReplayImmutableError):
        return GatewayError(
            code="dataset_version_immutable",
            message="Finalized dataset versions are immutable.",
            status_code=409,
        )
    if isinstance(exc, ReplayValidationError):
        return GatewayError(code="invalid_dataset", message=str(exc), status_code=422)
    return GatewayError(
        code="dataset_unavailable",
        message="Dataset storage is temporarily unavailable.",
        status_code=503,
    )


def _required_text(payload: Mapping[str, object], name: str, maximum: int) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise GatewayError(code="invalid_dataset", message=f"{name} is invalid.", status_code=422)
    return value.strip()


def _mapping(payload: Mapping[str, object], name: str) -> Mapping[str, JSONValue]:
    value = payload.get(name, {})
    if not isinstance(value, dict):
        raise GatewayError(
            code="invalid_dataset", message=f"{name} must be a JSON object.", status_code=422
        )
    return cast(Mapping[str, JSONValue], value)


@router.post("/datasets", status_code=201)
async def create_dataset(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_dataset", message="Dataset body is invalid.", status_code=422
        )
    name = _required_text(payload, "name", 255)
    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        raise GatewayError(
            code="invalid_dataset", message="description is invalid.", status_code=422
        )
    try:
        body = _repository(request).create_dataset(context.project_id, name, description)
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=201, content=body)


@router.get("/datasets")
async def list_datasets(request: Request, context: AuthContext = AUTH_DEPENDENCY) -> JSONResponse:
    try:
        items = _repository(request).list_datasets(context.project_id)
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content={"items": list(items)})


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_dataset(context.project_id, _uuid(dataset_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.patch("/datasets/{dataset_id}")
async def update_dataset(
    dataset_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_dataset", message="Dataset body is invalid.", status_code=422
        )
    name = _required_text(payload, "name", 255)
    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        raise GatewayError(
            code="invalid_dataset", message="description is invalid.", status_code=422
        )
    try:
        body = _repository(request).update_dataset(
            context.project_id, _uuid(dataset_id), name, description
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.post("/datasets/{dataset_id}/versions", status_code=201)
async def create_version(
    dataset_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_dataset", message="Version body is invalid.", status_code=422
        )
    try:
        body = _repository(request).create_draft_version(
            context.project_id, _uuid(dataset_id), _mapping(payload, "source_metadata")
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=201, content=body)


@router.post("/datasets/{dataset_id}/versions/import", status_code=201)
async def import_version(
    dataset_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_dataset", message="Dataset export is invalid.", status_code=422
        )
    try:
        body = _repository(request).import_version(context.project_id, _uuid(dataset_id), payload)
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=201, content=body)


@router.get("/dataset-versions/{version_id}")
async def get_version(
    version_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).get_version(context.project_id, _uuid(version_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.get("/dataset-versions/{version_id}/export")
async def export_version(
    version_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).export_version(context.project_id, _uuid(version_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.post("/dataset-versions/{version_id}/cases", status_code=201)
async def add_case(
    version_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict) or "input" not in payload:
        raise GatewayError(
            code="invalid_dataset", message="A case name and input are required.", status_code=422
        )
    name = _required_text(payload, "name", 255)
    tags = payload.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise GatewayError(
            code="invalid_dataset", message="tags must be an array of strings.", status_code=422
        )
    try:
        case = _repository(request).add_case(
            context.project_id,
            _uuid(version_id),
            name=name,
            input_value=cast(JSONValue, payload["input"]),
            metadata=_mapping(payload, "metadata"),
            source=_mapping(payload, "source"),
            ground_truth=cast(JSONValue | None, payload.get("ground_truth")),
            tags=tags,
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=201, content=case.to_dict())


@router.patch("/dataset-versions/{version_id}/cases/{case_id}")
async def update_case(
    version_id: str, case_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(code="invalid_dataset", message="Case body is invalid.", status_code=422)
    try:
        case = _repository(request).update_case(
            context.project_id,
            _uuid(version_id),
            _uuid(case_id),
            cast(Mapping[str, object], payload),
        )
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=case.to_dict())


@router.delete("/dataset-versions/{version_id}/cases/{case_id}", status_code=204)
async def delete_case(
    version_id: str, case_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        _repository(request).remove_case(context.project_id, _uuid(version_id), _uuid(case_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=204, content=None)


@router.post("/dataset-versions/{version_id}/finalize")
async def finalize_version(
    version_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    try:
        body = _repository(request).finalize_version(context.project_id, _uuid(version_id))
    except GatewayError:
        raise
    except Exception as exc:
        raise _error(exc) from None
    return JSONResponse(status_code=200, content=body)


@router.post("/dataset-versions/{version_id}/cases/from-trace", status_code=201)
async def add_case_from_trace(
    version_id: str, request: Request, context: AuthContext = AUTH_DEPENDENCY
) -> JSONResponse:
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        raise GatewayError(
            code="invalid_dataset",
            message="Trace extraction configuration is invalid.",
            status_code=422,
        )
    trace_id = payload.get("trace_id")
    span_id = payload.get("span_id")
    input_field = payload.get("input_field")
    if (
        not isinstance(trace_id, str)
        or not isinstance(span_id, str)
        or input_field not in {"input", "output"}
    ):
        raise GatewayError(
            code="invalid_dataset",
            message="trace_id, span_id, and input_field are required.",
            status_code=422,
        )
    try:
        parsed_trace = _uuid(trace_id, "trace_not_found")
        trace = request.app.state.gateway.repository.get_trace(context.project_id, parsed_trace)
        if trace is None:
            raise GatewayError(
                code="trace_not_found", message="Trace was not found.", status_code=404
            )
        span = next((item for item in trace.spans if str(item.span_id) == span_id), None)
        if span is None:
            raise GatewayError(
                code="trace_not_found", message="Trace span was not found.", status_code=404
            )
        value = thaw_payload(getattr(span, cast(str, input_field)))
        if value is None and input_field == "input":
            raise GatewayError(
                code="invalid_dataset", message="Selected trace field is empty.", status_code=422
            )
        name = _required_text(payload, "name", 255)
        tags = payload.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise GatewayError(
                code="invalid_dataset", message="tags must be an array of strings.", status_code=422
            )
        source = {
            "kind": "trace",
            "trace_id": str(trace.trace_id),
            "trace_fingerprint": canonical_fingerprint(trace),
            "trace_created_at": trace.started_at.isoformat(),
            "span_id": span_id,
            "extraction": {"input_field": input_field},
        }
        case = _repository(request).add_case(
            context.project_id,
            _uuid(version_id),
            name=name,
            input_value=value,
            metadata=_mapping(payload, "metadata"),
            source=source,
            ground_truth=cast(JSONValue | None, payload.get("ground_truth")),
            tags=tags,
        )
    except GatewayError:
        raise
    except Exception as exc:
        print("Trace case error", repr(exc))
        raise _error(exc) from None
    return JSONResponse(status_code=201, content=case.to_dict())
