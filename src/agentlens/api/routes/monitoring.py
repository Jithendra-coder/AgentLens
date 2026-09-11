"""Continuous production monitoring and health rollup API routes ."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.monitoring.calculator import HealthCalculator
from agentlens.monitoring.models import (
    HealthMetrics,
    HealthSnapshot,
    ProductionMonitor,
)
from agentlens.monitoring.repository import (
    InMemoryMonitoringRepository,
    MonitoringRepository,
)

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class CreateMonitorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    sampling_rate: float = Field(default=0.10, ge=0.0, le=1.0)


class RecordSnapshotRequest(BaseModel):
    mean_quality_score: float = Field(ge=0.0, le=1.0)
    p95_latency_ms: float = Field(ge=0.0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    total_spans_evaluated: int = Field(default=0, ge=0)


def _monitoring_repo(request: Request) -> MonitoringRepository:
    repo = getattr(request.app.state.gateway, "monitoring_repository", None)
    if repo is None:
        repo = InMemoryMonitoringRepository()
        request.app.state.gateway.monitoring_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/monitors")
async def create_monitor(
    project_id: str,
    body: CreateMonitorRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _monitoring_repo(request)
    monitor = ProductionMonitor(
        monitor_id=uuid4(),
        project_id=project_id,
        name=body.name,
        sampling_rate=body.sampling_rate,
        health_status="healthy",
        health_index=100.0,
        is_active=True,
    )
    saved = repo.save_monitor(monitor)

    return JSONResponse(
        status_code=200,
        content={
            "monitor_id": str(saved.monitor_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "sampling_rate": saved.sampling_rate,
            "health_status": saved.health_status,
            "health_index": saved.health_index,
            "is_active": saved.is_active,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/monitors")
async def list_monitors(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _monitoring_repo(request)
    monitors = repo.list_monitors(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "monitors": [
                {
                    "monitor_id": str(m.monitor_id),
                    "project_id": m.project_id,
                    "name": m.name,
                    "sampling_rate": m.sampling_rate,
                    "health_status": m.health_status,
                    "health_index": m.health_index,
                    "is_active": m.is_active,
                    "created_at": m.created_at.isoformat(),
                }
                for m in monitors
            ]
        },
    )


@router.delete("/v1/projects/{project_id}/monitors/{monitor_id}")
async def delete_monitor(
    project_id: str,
    monitor_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _monitoring_repo(request)
    m = repo.get_monitor(monitor_id)
    if m is None or m.project_id != project_id:
        raise GatewayError(code="not_found", message="Monitor not found.", status_code=404)
    deleted = repo.delete_monitor(monitor_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/monitors/{monitor_id}/snapshots")
async def record_snapshot(
    project_id: str,
    monitor_id: UUID,
    body: RecordSnapshotRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _monitoring_repo(request)
    m = repo.get_monitor(monitor_id)
    if m is None or m.project_id != project_id:
        raise GatewayError(code="not_found", message="Monitor not found.", status_code=404)

    metrics = HealthMetrics(
        mean_quality_score=body.mean_quality_score,
        p95_latency_ms=body.p95_latency_ms,
        error_rate=body.error_rate,
        total_spans_evaluated=body.total_spans_evaluated,
    )
    health_idx = HealthCalculator.calculate_health_index(metrics)
    health_stat = HealthCalculator.classify_status(health_idx)

    snapshot = HealthSnapshot(
        snapshot_id=uuid4(),
        monitor_id=monitor_id,
        project_id=project_id,
        health_index=health_idx,
        p95_latency_ms=body.p95_latency_ms,
        mean_quality_score=body.mean_quality_score,
        error_rate=body.error_rate,
        total_spans_evaluated=body.total_spans_evaluated,
        recorded_at=datetime.now(UTC),
    )
    saved = repo.record_snapshot(snapshot)
    repo.update_monitor_health(monitor_id, health_idx, health_stat)

    return JSONResponse(
        status_code=200,
        content={
            "snapshot_id": str(saved.snapshot_id),
            "monitor_id": str(saved.monitor_id),
            "project_id": saved.project_id,
            "health_index": saved.health_index,
            "health_status": health_stat,
            "p95_latency_ms": saved.p95_latency_ms,
            "mean_quality_score": saved.mean_quality_score,
            "error_rate": saved.error_rate,
            "total_spans_evaluated": saved.total_spans_evaluated,
            "recorded_at": saved.recorded_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/monitors/{monitor_id}/snapshots")
async def list_snapshots(
    project_id: str,
    monitor_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _monitoring_repo(request)
    snapshots = repo.list_snapshots(project_id, monitor_id=monitor_id)

    return JSONResponse(
        status_code=200,
        content={
            "snapshots": [
                {
                    "snapshot_id": str(s.snapshot_id),
                    "monitor_id": str(s.monitor_id),
                    "health_index": s.health_index,
                    "p95_latency_ms": s.p95_latency_ms,
                    "mean_quality_score": s.mean_quality_score,
                    "error_rate": s.error_rate,
                    "total_spans_evaluated": s.total_spans_evaluated,
                    "recorded_at": s.recorded_at.isoformat(),
                }
                for s in snapshots
            ]
        },
    )


@router.get("/v1/projects/{project_id}/monitors/health")
async def get_project_health_summary(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _monitoring_repo(request)
    monitors = repo.list_monitors(project_id)
    if not monitors:
        return JSONResponse(
            status_code=200,
            content={
                "project_id": project_id,
                "overall_health_index": 100.0,
                "overall_health_status": "healthy",
                "monitors_count": 0,
                "active_monitors": 0,
            },
        )

    active = [m for m in monitors if m.is_active]
    avg_index = (
        round(sum(m.health_index for m in active) / float(len(active)), 2)
        if active
        else 100.0
    )
    overall_status = HealthCalculator.classify_status(avg_index)

    return JSONResponse(
        status_code=200,
        content={
            "project_id": project_id,
            "overall_health_index": avg_index,
            "overall_health_status": overall_status,
            "monitors_count": len(monitors),
            "active_monitors": len(active),
        },
    )
