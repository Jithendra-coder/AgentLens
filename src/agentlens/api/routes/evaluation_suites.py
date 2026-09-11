"""Evaluation suites and composite quality metric API endpoints ."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.evaluation.composite import (
    EvaluationSuite,
    EvaluatorConfigRef,
)
from agentlens.evaluation.orchestrator import EvaluationSuiteOrchestrator
from agentlens.evaluation.suite_repository import EvaluationSuiteRepository

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class EvaluatorInput(BaseModel):
    evaluator_name: str = Field(min_length=1, max_length=128)
    evaluator_version: str = Field(default="1.0.0", max_length=32)
    evaluator_type: str = Field(default="deterministic", max_length=32)
    weight: float = Field(default=1.0, gt=0.0)
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    parameters: dict[str, Any] = Field(default_factory=dict)


class CreateSuiteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    passing_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    evaluators: list[EvaluatorInput] = Field(min_length=1)


class RunSuiteRequest(BaseModel):
    trace_id: UUID


def _suite_repo(request: Request) -> EvaluationSuiteRepository:
    repo = getattr(request.app.state.gateway, "suite_repository", None)
    if repo is None:
        raise GatewayError(
            code="suite_repository_unavailable",
            message="Evaluation suite repository is not configured.",
            status_code=503,
        )
    return cast(EvaluationSuiteRepository, repo)


def _suite_json(suite: EvaluationSuite) -> dict[str, Any]:
    return {
        "suite_id": str(suite.suite_id),
        "project_id": suite.project_id,
        "name": suite.name,
        "description": suite.description,
        "passing_threshold": suite.passing_threshold,
        "evaluators": [
            {
                "evaluator_name": ev.evaluator_name,
                "evaluator_version": ev.evaluator_version,
                "evaluator_type": ev.evaluator_type,
                "weight": ev.weight,
                "threshold": ev.threshold,
                "parameters": ev.parameters,
            }
            for ev in suite.evaluators
        ],
        "created_at": suite.created_at.isoformat(),
        "updated_at": suite.updated_at.isoformat(),
    }


@router.post("/v1/projects/{project_id}/evaluation-suites")
async def create_evaluation_suite(
    project_id: str,
    body: CreateSuiteRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _suite_repo(request)
    evaluators = [
        EvaluatorConfigRef(
            evaluator_name=ev.evaluator_name,
            evaluator_version=ev.evaluator_version,
            evaluator_type=ev.evaluator_type,
            weight=ev.weight,
            threshold=ev.threshold,
            parameters=ev.parameters,
        )
        for ev in body.evaluators
    ]
    suite = EvaluationSuite(
        suite_id=uuid4(),
        project_id=project_id,
        name=body.name,
        description=body.description,
        passing_threshold=body.passing_threshold,
        evaluators=tuple(evaluators),
    )
    saved = repo.create_suite(suite)
    return JSONResponse(status_code=200, content=_suite_json(saved))


@router.get("/v1/projects/{project_id}/evaluation-suites")
async def list_evaluation_suites(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _suite_repo(request)
    suites = repo.list_suites(project_id)
    return JSONResponse(
        status_code=200,
        content={"suites": [_suite_json(s) for s in suites]},
    )


@router.get("/v1/projects/{project_id}/evaluation-suites/{suite_id}")
async def get_evaluation_suite(
    project_id: str,
    suite_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _suite_repo(request)
    suite = repo.get_suite(suite_id)
    if suite is None or suite.project_id != project_id:
        raise GatewayError(code="not_found", message="Suite not found.", status_code=404)
    return JSONResponse(status_code=200, content=_suite_json(suite))


@router.delete("/v1/projects/{project_id}/evaluation-suites/{suite_id}")
async def delete_evaluation_suite(
    project_id: str,
    suite_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _suite_repo(request)
    suite = repo.get_suite(suite_id)
    if suite is None or suite.project_id != project_id:
        raise GatewayError(code="not_found", message="Suite not found.", status_code=404)
    deleted = repo.delete_suite(suite_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/evaluation-suites/{suite_id}/run")
async def run_evaluation_suite(
    project_id: str,
    suite_id: UUID,
    body: RunSuiteRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _suite_repo(request)
    suite = repo.get_suite(suite_id)
    if suite is None or suite.project_id != project_id:
        raise GatewayError(code="not_found", message="Suite not found.", status_code=404)

    trace_repo = getattr(request.app.state.gateway, "repository", None)
    trace = None
    if trace_repo is not None:
        if hasattr(trace_repo, "get_trace") and callable(trace_repo.get_trace):
            trace = trace_repo.get_trace(project_id, body.trace_id)
        elif hasattr(trace_repo, "get") and callable(trace_repo.get):
            trace = trace_repo.get(project_id, body.trace_id)

    if trace is None:
        raise GatewayError(code="not_found", message="Trace not found.", status_code=404)

    semantic_judge = getattr(request.app.state.gateway, "semantic_judge", None)
    custom_repo = getattr(request.app.state.gateway, "custom_evaluator_repository", None)
    orchestrator = EvaluationSuiteOrchestrator(
        semantic_judge=semantic_judge,
        custom_evaluator_repo=custom_repo,
    )
    result = orchestrator.evaluate_suite(suite, trace)
    repo.store_result(result)

    return JSONResponse(
        status_code=200,
        content={
            "composite_result_id": str(result.composite_result_id),
            "suite_id": str(result.suite_id),
            "project_id": result.project_id,
            "trace_id": str(result.trace_id),
            "aggregate_score": result.aggregate_score,
            "passed": result.passed,
            "metric_scores": [
                {
                    "evaluator_name": m.evaluator_name,
                    "evaluator_version": m.evaluator_version,
                    "evaluator_type": m.evaluator_type,
                    "raw_score": m.raw_score,
                    "weight": m.weight,
                    "weighted_score": m.weighted_score,
                    "threshold": m.threshold,
                    "passed": m.passed,
                    "details": m.details,
                }
                for m in result.metric_scores
            ],
            "created_at": result.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/evaluation-suites/{suite_id}/results")
async def list_evaluation_suite_results(
    project_id: str,
    suite_id: UUID,
    request: Request,
    limit: int = 50,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _suite_repo(request)
    results = repo.list_results(project_id, suite_id=suite_id, limit=min(limit, 100))
    return JSONResponse(
        status_code=200,
        content={
            "results": [
                {
                    "composite_result_id": str(r.composite_result_id),
                    "suite_id": str(r.suite_id),
                    "project_id": r.project_id,
                    "trace_id": str(r.trace_id),
                    "aggregate_score": r.aggregate_score,
                    "passed": r.passed,
                    "metric_scores": [
                        {
                            "evaluator_name": m.evaluator_name,
                            "evaluator_version": m.evaluator_version,
                            "evaluator_type": m.evaluator_type,
                            "raw_score": m.raw_score,
                            "weight": m.weight,
                            "weighted_score": m.weighted_score,
                            "threshold": m.threshold,
                            "passed": m.passed,
                            "details": m.details,
                        }
                        for m in r.metric_scores
                    ],
                    "created_at": r.created_at.isoformat(),
                }
                for r in results
            ]
        },
    )
