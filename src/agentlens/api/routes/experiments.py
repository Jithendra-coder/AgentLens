"""Experimentation API endpoints ."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.experimentation.models import (
    Experiment,
    ExperimentEvaluation,
    ExperimentVariant,
)
from agentlens.experimentation.reporter import ExperimentReporter
from agentlens.experimentation.repository import (
    ExperimentRepository,
    InMemoryExperimentRepository,
)
from agentlens.experimentation.splitter import TrafficSplitter

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class VariantInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    prompt_template: str = Field(default="")
    model_name: str = Field(default="")
    provider_type: str = Field(default="openai")
    traffic_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    is_control: bool = Field(default=False)


class CreateExperimentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    experiment_type: str = Field(default="ab_test", pattern="^(ab_test|shadow|canary)$")
    variants: list[VariantInput] = Field(min_length=1)


class SplitRequest(BaseModel):
    routing_key: str = Field(min_length=1)


class RecordEvaluationRequest(BaseModel):
    variant_id: UUID
    trace_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)


def _exp_repo(request: Request) -> ExperimentRepository:
    repo = getattr(request.app.state.gateway, "experiment_repository", None)
    if repo is None:
        repo = InMemoryExperimentRepository()
        request.app.state.gateway.experiment_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/experiments")
async def create_experiment(
    project_id: str,
    body: CreateExperimentRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _exp_repo(request)
    exp_id = uuid4()

    variants = tuple(
        ExperimentVariant(
            variant_id=uuid4(),
            experiment_id=exp_id,
            name=v.name,
            prompt_template=v.prompt_template,
            model_name=v.model_name,
            provider_type=v.provider_type,
            traffic_weight=v.traffic_weight,
            is_control=v.is_control,
        )
        for v in body.variants
    )

    exp = Experiment(
        experiment_id=exp_id,
        project_id=project_id,
        name=body.name,
        description=body.description,
        experiment_type=body.experiment_type,
        status="running",
        variants=variants,
    )

    saved = repo.save_experiment(exp)

    return JSONResponse(
        status_code=200,
        content={
            "experiment_id": str(saved.experiment_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "description": saved.description,
            "experiment_type": saved.experiment_type,
            "status": saved.status,
            "variants": [
                {
                    "variant_id": str(v.variant_id),
                    "name": v.name,
                    "prompt_template": v.prompt_template,
                    "model_name": v.model_name,
                    "provider_type": v.provider_type,
                    "traffic_weight": v.traffic_weight,
                    "is_control": v.is_control,
                }
                for v in saved.variants
            ],
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/experiments")
async def list_experiments(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _exp_repo(request)
    experiments_list = repo.list_experiments(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "experiments": [
                {
                    "experiment_id": str(e.experiment_id),
                    "project_id": e.project_id,
                    "name": e.name,
                    "description": e.description,
                    "experiment_type": e.experiment_type,
                    "status": e.status,
                    "variants_count": len(e.variants),
                    "created_at": e.created_at.isoformat(),
                }
                for e in experiments_list
            ]
        },
    )


@router.get("/v1/projects/{project_id}/experiments/{experiment_id}")
async def get_experiment_details(
    project_id: str,
    experiment_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _exp_repo(request)
    exp = repo.get_experiment(experiment_id)
    if exp is None or exp.project_id != project_id:
        raise GatewayError(code="not_found", message="Experiment not found.", status_code=404)

    return JSONResponse(
        status_code=200,
        content={
            "experiment_id": str(exp.experiment_id),
            "project_id": exp.project_id,
            "name": exp.name,
            "description": exp.description,
            "experiment_type": exp.experiment_type,
            "status": exp.status,
            "variants": [
                {
                    "variant_id": str(v.variant_id),
                    "name": v.name,
                    "prompt_template": v.prompt_template,
                    "model_name": v.model_name,
                    "provider_type": v.provider_type,
                    "traffic_weight": v.traffic_weight,
                    "is_control": v.is_control,
                }
                for v in exp.variants
            ],
            "created_at": exp.created_at.isoformat(),
        },
    )


@router.delete("/v1/projects/{project_id}/experiments/{experiment_id}")
async def delete_experiment(
    project_id: str,
    experiment_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _exp_repo(request)
    exp = repo.get_experiment(experiment_id)
    if exp is None or exp.project_id != project_id:
        raise GatewayError(code="not_found", message="Experiment not found.", status_code=404)
    deleted = repo.delete_experiment(experiment_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/experiments/{experiment_id}/split")
async def route_traffic_split(
    project_id: str,
    experiment_id: UUID,
    body: SplitRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _exp_repo(request)
    exp = repo.get_experiment(experiment_id)
    if exp is None or exp.project_id != project_id:
        raise GatewayError(code="not_found", message="Experiment not found.", status_code=404)

    selected = TrafficSplitter.select_variant(exp, body.routing_key)

    return JSONResponse(
        status_code=200,
        content={
            "experiment_id": str(exp.experiment_id),
            "selected_variant_id": str(selected.variant_id),
            "variant_name": selected.name,
            "model_name": selected.model_name,
            "prompt_template": selected.prompt_template,
            "is_control": selected.is_control,
        },
    )


@router.post("/v1/projects/{project_id}/experiments/{experiment_id}/evaluations")
async def record_experiment_evaluation(
    project_id: str,
    experiment_id: UUID,
    body: RecordEvaluationRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _exp_repo(request)
    exp = repo.get_experiment(experiment_id)
    if exp is None or exp.project_id != project_id:
        raise GatewayError(code="not_found", message="Experiment not found.", status_code=404)

    evaluation = ExperimentEvaluation(
        eval_id=uuid4(),
        experiment_id=experiment_id,
        variant_id=body.variant_id,
        trace_id=body.trace_id,
        score=body.score,
        cost_usd=body.cost_usd,
        latency_ms=body.latency_ms,
    )
    saved = repo.record_evaluation(evaluation)

    return JSONResponse(
        status_code=200,
        content={
            "eval_id": str(saved.eval_id),
            "experiment_id": str(saved.experiment_id),
            "variant_id": str(saved.variant_id),
            "trace_id": str(saved.trace_id),
            "score": saved.score,
            "cost_usd": saved.cost_usd,
            "latency_ms": saved.latency_ms,
        },
    )


@router.get("/v1/projects/{project_id}/experiments/{experiment_id}/report")
async def get_experiment_report(
    project_id: str,
    experiment_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _exp_repo(request)
    exp = repo.get_experiment(experiment_id)
    if exp is None or exp.project_id != project_id:
        raise GatewayError(code="not_found", message="Experiment not found.", status_code=404)

    evaluations = repo.list_evaluations(experiment_id)
    report = ExperimentReporter.generate_report(exp, evaluations)

    return JSONResponse(
        status_code=200,
        content={
            "experiment_id": str(report.experiment_id),
            "project_id": report.project_id,
            "name": report.name,
            "status": report.status,
            "total_evaluations": report.total_evaluations,
            "variants": [
                {
                    "variant_id": str(v.variant_id),
                    "name": v.name,
                    "is_control": v.is_control,
                    "sample_count": v.sample_count,
                    "mean_score": v.mean_score,
                    "mean_cost_usd": v.mean_cost_usd,
                    "mean_latency_ms": v.mean_latency_ms,
                    "score_delta_pct": v.score_delta_pct,
                    "cost_delta_pct": v.cost_delta_pct,
                    "latency_delta_pct": v.latency_delta_pct,
                }
                for v in report.variants
            ],
        },
    )
