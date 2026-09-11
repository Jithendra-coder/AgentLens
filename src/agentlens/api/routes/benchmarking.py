"""Benchmarking and qualification API endpoints ."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.benchmarking.models import (
    ModelBenchmark,
    ModelBenchmarkRun,
)
from agentlens.benchmarking.pareto import ParetoOptimizer
from agentlens.benchmarking.qualifier import QualificationGate
from agentlens.benchmarking.repository import (
    BenchmarkRepository,
    InMemoryBenchmarkRepository,
)

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class CreateBenchmarkRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)


class RecordRunRequest(BaseModel):
    model_name: str = Field(min_length=1, max_length=128)
    provider_type: str = Field(default="openai", max_length=64)
    overall_score: float = Field(ge=0.0, le=1.0)
    mean_latency_ms: float = Field(ge=0.0)
    mean_cost_usd: float = Field(default=0.0, ge=0.0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    status: str = Field(default="completed", pattern="^(completed|failed)$")


class EvaluateQualificationRequest(BaseModel):
    run_id: UUID
    min_required_score: float = Field(default=0.80, ge=0.0, le=1.0)
    max_latency_ms: float = Field(default=3000.0, ge=0.0)
    min_pass_rate: float = Field(default=0.80, ge=0.0, le=1.0)


def _benchmark_repo(request: Request) -> BenchmarkRepository:
    repo = getattr(request.app.state.gateway, "benchmark_repository", None)
    if repo is None:
        repo = InMemoryBenchmarkRepository()
        request.app.state.gateway.benchmark_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/benchmarks")
async def create_benchmark(
    project_id: str,
    body: CreateBenchmarkRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    benchmark = ModelBenchmark(
        benchmark_id=uuid4(),
        project_id=project_id,
        name=body.name,
        description=body.description,
    )
    saved = repo.save_benchmark(benchmark)

    return JSONResponse(
        status_code=200,
        content={
            "benchmark_id": str(saved.benchmark_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "description": saved.description,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/benchmarks")
async def list_benchmarks(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    benchmarks = repo.list_benchmarks(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "benchmarks": [
                {
                    "benchmark_id": str(b.benchmark_id),
                    "project_id": b.project_id,
                    "name": b.name,
                    "description": b.description,
                    "created_at": b.created_at.isoformat(),
                }
                for b in benchmarks
            ]
        },
    )


@router.delete("/v1/projects/{project_id}/benchmarks/{benchmark_id}")
async def delete_benchmark(
    project_id: str,
    benchmark_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    b = repo.get_benchmark(benchmark_id)
    if b is None or b.project_id != project_id:
        raise GatewayError(code="not_found", message="Benchmark not found.", status_code=404)
    deleted = repo.delete_benchmark(benchmark_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/benchmarks/{benchmark_id}/runs")
async def record_benchmark_run(
    project_id: str,
    benchmark_id: UUID,
    body: RecordRunRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    b = repo.get_benchmark(benchmark_id)
    if b is None or b.project_id != project_id:
        raise GatewayError(code="not_found", message="Benchmark not found.", status_code=404)

    run = ModelBenchmarkRun(
        run_id=uuid4(),
        benchmark_id=benchmark_id,
        project_id=project_id,
        model_name=body.model_name,
        provider_type=body.provider_type,
        overall_score=body.overall_score,
        mean_latency_ms=body.mean_latency_ms,
        mean_cost_usd=body.mean_cost_usd,
        pass_rate=body.pass_rate,
        status=body.status,
        completed_at=datetime.now(UTC),
    )
    saved = repo.record_run(run)

    return JSONResponse(
        status_code=200,
        content={
            "run_id": str(saved.run_id),
            "benchmark_id": str(saved.benchmark_id),
            "project_id": saved.project_id,
            "model_name": saved.model_name,
            "provider_type": saved.provider_type,
            "overall_score": saved.overall_score,
            "mean_latency_ms": saved.mean_latency_ms,
            "mean_cost_usd": saved.mean_cost_usd,
            "pass_rate": saved.pass_rate,
            "status": saved.status,
            "started_at": saved.started_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/benchmarks/{benchmark_id}/runs")
async def list_benchmark_runs(
    project_id: str,
    benchmark_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    runs = repo.list_runs(project_id, benchmark_id=benchmark_id)

    return JSONResponse(
        status_code=200,
        content={
            "runs": [
                {
                    "run_id": str(r.run_id),
                    "benchmark_id": str(r.benchmark_id),
                    "model_name": r.model_name,
                    "provider_type": r.provider_type,
                    "overall_score": r.overall_score,
                    "mean_latency_ms": r.mean_latency_ms,
                    "mean_cost_usd": r.mean_cost_usd,
                    "pass_rate": r.pass_rate,
                    "status": r.status,
                    "started_at": r.started_at.isoformat(),
                }
                for r in runs
            ]
        },
    )


@router.get("/v1/projects/{project_id}/benchmarks/pareto")
async def get_pareto_frontier(
    project_id: str,
    request: Request,
    benchmark_id: UUID | None = None,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    runs = repo.list_runs(project_id, benchmark_id=benchmark_id)

    optimizer = ParetoOptimizer()
    report = optimizer.compute_frontier(project_id, benchmark_id, runs)

    return JSONResponse(
        status_code=200,
        content={
            "project_id": report.project_id,
            "benchmark_id": str(report.benchmark_id) if report.benchmark_id else None,
            "points": [
                {
                    "model_name": p.model_name,
                    "provider_type": p.provider_type,
                    "quality_score": p.quality_score,
                    "cost_per_1k": p.cost_per_1k,
                    "latency_ms": p.latency_ms,
                    "is_optimal": p.is_optimal,
                }
                for p in report.points
            ],
        },
    )


@router.post("/v1/projects/{project_id}/qualifications/evaluate")
async def evaluate_and_save_qualification(
    project_id: str,
    body: EvaluateQualificationRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    runs = repo.list_runs(project_id)
    run = next((r for r in runs if r.run_id == body.run_id), None)
    if run is None:
        raise GatewayError(code="not_found", message="Benchmark run not found.", status_code=404)

    qual = QualificationGate.evaluate(
        run,
        min_required_score=body.min_required_score,
        max_latency_ms=body.max_latency_ms,
        min_pass_rate=body.min_pass_rate,
    )
    saved = repo.save_qualification(qual)

    return JSONResponse(
        status_code=200,
        content={
            "qualification_id": str(saved.qualification_id),
            "project_id": saved.project_id,
            "model_name": saved.model_name,
            "provider_type": saved.provider_type,
            "is_qualified": saved.is_qualified,
            "min_required_score": saved.min_required_score,
            "latest_run_id": str(saved.latest_run_id) if saved.latest_run_id else None,
            "updated_at": saved.updated_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/qualifications")
async def list_qualifications(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _benchmark_repo(request)
    quals = repo.list_qualifications(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "qualifications": [
                {
                    "qualification_id": str(q.qualification_id),
                    "project_id": q.project_id,
                    "model_name": q.model_name,
                    "provider_type": q.provider_type,
                    "is_qualified": q.is_qualified,
                    "min_required_score": q.min_required_score,
                    "latest_run_id": str(q.latest_run_id) if q.latest_run_id else None,
                    "updated_at": q.updated_at.isoformat(),
                }
                for q in quals
            ]
        },
    )
