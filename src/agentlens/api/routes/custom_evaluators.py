"""Custom Evaluator Plugin API endpoints ."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.evaluation.plugins.models import CustomEvaluatorPlugin, EvaluatorContext
from agentlens.evaluation.plugins.repository import CustomEvaluatorRepository
from agentlens.evaluation.plugins.sandbox import execute_custom_evaluator

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class RegisterPluginRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(default="1.0.0", max_length=32)
    evaluator_type: str = Field(default="deterministic", max_length=32)
    description: str | None = Field(default=None, max_length=1024)
    code_body: str = Field(min_length=1)
    schema_parameters: dict[str, Any] = Field(default_factory=dict)


class TestPluginRequest(BaseModel):
    trace_id: UUID
    parameters: dict[str, Any] = Field(default_factory=dict)


def _custom_repo(request: Request) -> CustomEvaluatorRepository:
    repo = getattr(request.app.state.gateway, "custom_evaluator_repository", None)
    if repo is None:
        raise GatewayError(
            code="custom_evaluator_repo_unavailable",
            message="Custom evaluator repository is not configured.",
            status_code=503,
        )
    return cast(CustomEvaluatorRepository, repo)


def _plugin_json(plugin: CustomEvaluatorPlugin) -> dict[str, Any]:
    return {
        "plugin_id": str(plugin.plugin_id),
        "project_id": plugin.project_id,
        "name": plugin.name,
        "version": plugin.version,
        "evaluator_type": plugin.evaluator_type,
        "description": plugin.description,
        "code_body": plugin.code_body,
        "schema_parameters": plugin.schema_parameters,
        "created_at": plugin.created_at.isoformat(),
        "updated_at": plugin.updated_at.isoformat(),
    }


@router.post("/v1/projects/{project_id}/custom-evaluators")
async def register_custom_evaluator(
    project_id: str,
    body: RegisterPluginRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _custom_repo(request)
    plugin = CustomEvaluatorPlugin(
        plugin_id=uuid4(),
        project_id=project_id,
        name=body.name,
        version=body.version,
        evaluator_type=body.evaluator_type,
        description=body.description,
        code_body=body.code_body,
        schema_parameters=body.schema_parameters,
    )
    saved = repo.save_plugin(plugin)
    return JSONResponse(status_code=200, content=_plugin_json(saved))


@router.get("/v1/projects/{project_id}/custom-evaluators")
async def list_custom_evaluators(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _custom_repo(request)
    plugins = repo.list_plugins(project_id)
    return JSONResponse(
        status_code=200,
        content={"custom_evaluators": [_plugin_json(p) for p in plugins]},
    )


@router.get("/v1/projects/{project_id}/custom-evaluators/{plugin_id}")
async def get_custom_evaluator(
    project_id: str,
    plugin_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _custom_repo(request)
    plugin = repo.get_plugin(plugin_id)
    if plugin is None or plugin.project_id != project_id:
        raise GatewayError(code="not_found", message="Custom evaluator not found.", status_code=404)
    return JSONResponse(status_code=200, content=_plugin_json(plugin))


@router.delete("/v1/projects/{project_id}/custom-evaluators/{plugin_id}")
async def delete_custom_evaluator(
    project_id: str,
    plugin_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _custom_repo(request)
    plugin = repo.get_plugin(plugin_id)
    if plugin is None or plugin.project_id != project_id:
        raise GatewayError(code="not_found", message="Custom evaluator not found.", status_code=404)
    deleted = repo.delete_plugin(plugin_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/custom-evaluators/{plugin_id}/test")
async def test_custom_evaluator(
    project_id: str,
    plugin_id: UUID,
    body: TestPluginRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _custom_repo(request)
    plugin = repo.get_plugin(plugin_id)
    if plugin is None or plugin.project_id != project_id:
        raise GatewayError(code="not_found", message="Custom evaluator not found.", status_code=404)

    trace_repo = getattr(request.app.state.gateway, "repository", None)
    trace = None
    if trace_repo is not None:
        if hasattr(trace_repo, "get_trace") and callable(trace_repo.get_trace):
            trace = trace_repo.get_trace(project_id, body.trace_id)
        elif hasattr(trace_repo, "get") and callable(trace_repo.get):
            trace = trace_repo.get(project_id, body.trace_id)

    if trace is None:
        raise GatewayError(code="not_found", message="Trace not found.", status_code=404)

    ctx = EvaluatorContext.from_trace(trace)
    result = execute_custom_evaluator(
        plugin.code_body,
        ctx,
        parameters=body.parameters,
    )

    return JSONResponse(
        status_code=200,
        content={
            "score": result.score,
            "passed": result.passed,
            "findings": result.findings,
            "details": result.details,
        },
    )
