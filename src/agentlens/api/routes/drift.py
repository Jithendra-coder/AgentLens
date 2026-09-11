"""Quality baselines and drift detection API routes ."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.regression.drift.detector import DriftDetector
from agentlens.regression.drift.models import (
    DriftObservation,
    QualityBaseline,
)
from agentlens.regression.drift.repository import (
    DriftRepository,
    InMemoryDriftRepository,
)

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class CreateBaselineRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    metric_name: str = Field(
        min_length=1, max_length=64, pattern="^(quality_score|latency_ms|cost_usd)$"
    )
    baseline_mean: float = Field(ge=0.0)
    baseline_std: float = Field(default=0.05, ge=0.0)
    window_size: int = Field(default=50, ge=1, le=10000)


class DetectDriftRequest(BaseModel):
    baseline_id: UUID
    observed_values: list[float] = Field(min_length=1)
    z_alert_threshold: float = Field(default=2.0, ge=0.5, le=10.0)


def _drift_repo(request: Request) -> DriftRepository:
    repo = getattr(request.app.state.gateway, "drift_repository", None)
    if repo is None:
        repo = InMemoryDriftRepository()
        request.app.state.gateway.drift_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/drift/baselines")
async def create_baseline(
    project_id: str,
    body: CreateBaselineRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _drift_repo(request)
    baseline = QualityBaseline(
        baseline_id=uuid4(),
        project_id=project_id,
        name=body.name,
        metric_name=body.metric_name,
        baseline_mean=body.baseline_mean,
        baseline_std=body.baseline_std,
        window_size=body.window_size,
    )
    saved = repo.save_baseline(baseline)

    return JSONResponse(
        status_code=200,
        content={
            "baseline_id": str(saved.baseline_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "metric_name": saved.metric_name,
            "baseline_mean": saved.baseline_mean,
            "baseline_std": saved.baseline_std,
            "window_size": saved.window_size,
            "status": saved.status,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/drift/baselines")
async def list_baselines(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _drift_repo(request)
    baselines = repo.list_baselines(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "baselines": [
                {
                    "baseline_id": str(b.baseline_id),
                    "project_id": b.project_id,
                    "name": b.name,
                    "metric_name": b.metric_name,
                    "baseline_mean": b.baseline_mean,
                    "baseline_std": b.baseline_std,
                    "window_size": b.window_size,
                    "status": b.status,
                    "created_at": b.created_at.isoformat(),
                }
                for b in baselines
            ]
        },
    )


@router.delete("/v1/projects/{project_id}/drift/baselines/{baseline_id}")
async def delete_baseline(
    project_id: str,
    baseline_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _drift_repo(request)
    b = repo.get_baseline(baseline_id)
    if b is None or b.project_id != project_id:
        raise GatewayError(code="not_found", message="Baseline not found.", status_code=404)
    deleted = repo.delete_baseline(baseline_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/drift/detect")
async def detect_drift(
    project_id: str,
    body: DetectDriftRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _drift_repo(request)
    baseline = repo.get_baseline(body.baseline_id)
    if baseline is None or baseline.project_id != project_id:
        raise GatewayError(code="not_found", message="Baseline not found.", status_code=404)

    eval_result = DriftDetector.evaluate_drift(
        baseline,
        body.observed_values,
        z_alert_threshold=body.z_alert_threshold,
    )

    observation = DriftObservation(
        drift_id=uuid4(),
        baseline_id=baseline.baseline_id,
        project_id=project_id,
        observed_mean=eval_result.observed_mean,
        z_score=eval_result.z_score,
        drift_magnitude_pct=eval_result.drift_magnitude_pct,
        drift_type=eval_result.drift_type,
        is_alert=eval_result.is_alert,
        observed_at=datetime.now(UTC),
    )
    repo.record_observation(observation)

    return JSONResponse(
        status_code=200,
        content={
            "drift_id": str(observation.drift_id),
            "baseline_id": str(eval_result.baseline_id),
            "baseline_name": eval_result.baseline_name,
            "metric_name": eval_result.metric_name,
            "observed_mean": eval_result.observed_mean,
            "baseline_mean": eval_result.baseline_mean,
            "z_score": eval_result.z_score,
            "drift_magnitude_pct": eval_result.drift_magnitude_pct,
            "drift_type": eval_result.drift_type,
            "is_alert": eval_result.is_alert,
            "reason": eval_result.reason,
            "observed_at": observation.observed_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/drift/observations")
async def list_observations(
    project_id: str,
    request: Request,
    baseline_id: UUID | None = None,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _drift_repo(request)
    observations = repo.list_observations(project_id, baseline_id=baseline_id)

    return JSONResponse(
        status_code=200,
        content={
            "observations": [
                {
                    "drift_id": str(o.drift_id),
                    "baseline_id": str(o.baseline_id),
                    "project_id": o.project_id,
                    "observed_mean": o.observed_mean,
                    "z_score": o.z_score,
                    "drift_magnitude_pct": o.drift_magnitude_pct,
                    "drift_type": o.drift_type,
                    "is_alert": o.is_alert,
                    "observed_at": o.observed_at.isoformat(),
                }
                for o in observations
            ]
        },
    )
