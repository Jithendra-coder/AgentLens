"""Automated root-cause analysis (RCA) and failure clustering API routes ."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.rca.engine import DiagnosticEngine
from agentlens.rca.models import (
    DiagnosticInput,
    RCAReport,
)
from agentlens.rca.repository import (
    InMemoryRCARepository,
    RCARepository,
)

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class DiagnoseRequest(BaseModel):
    error_message: str | None = Field(default=None, max_length=4096)
    http_status: int | None = Field(default=None, ge=100, le=599)
    latency_ms: float | None = Field(default=None, ge=0.0)
    total_tokens: int | None = Field(default=None, ge=0)
    prompt_text: str | None = Field(default=None, max_length=16384)
    eval_score: float | None = Field(default=None, ge=0.0, le=1.0)
    trace_id: UUID | None = Field(default=None)
    incident_id: UUID | None = Field(default=None)


def _rca_repo(request: Request) -> RCARepository:
    repo = getattr(request.app.state.gateway, "rca_repository", None)
    if repo is None:
        repo = InMemoryRCARepository()
        request.app.state.gateway.rca_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/rca/diagnose")
async def perform_rca_diagnosis(
    project_id: str,
    body: DiagnoseRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _rca_repo(request)

    diag_input = DiagnosticInput(
        project_id=project_id,
        error_message=body.error_message,
        http_status=body.http_status,
        latency_ms=body.latency_ms,
        total_tokens=body.total_tokens,
        prompt_text=body.prompt_text,
        eval_score=body.eval_score,
        trace_id=body.trace_id,
        incident_id=body.incident_id,
    )

    result = DiagnosticEngine.diagnose(diag_input)

    report = RCAReport(
        rca_id=uuid4(),
        project_id=project_id,
        trace_id=body.trace_id,
        incident_id=body.incident_id,
        failure_category=result.failure_category,
        root_cause_summary=result.root_cause_summary,
        confidence_score=result.confidence_score,
        recommended_action=result.recommended_action,
    )
    saved = repo.save_report(report)

    # Cluster if error message provided
    if body.error_message:
        repo.record_failure_cluster(project_id, body.error_message)

    return JSONResponse(
        status_code=200,
        content={
            "rca_id": str(saved.rca_id),
            "project_id": saved.project_id,
            "trace_id": str(saved.trace_id) if saved.trace_id else None,
            "incident_id": str(saved.incident_id) if saved.incident_id else None,
            "failure_category": saved.failure_category,
            "root_cause_summary": saved.root_cause_summary,
            "confidence_score": saved.confidence_score,
            "recommended_action": saved.recommended_action,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/rca/reports")
async def list_rca_reports(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _rca_repo(request)
    reports = repo.list_reports(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "reports": [
                {
                    "rca_id": str(r.rca_id),
                    "project_id": r.project_id,
                    "trace_id": str(r.trace_id) if r.trace_id else None,
                    "incident_id": str(r.incident_id) if r.incident_id else None,
                    "failure_category": r.failure_category,
                    "root_cause_summary": r.root_cause_summary,
                    "confidence_score": r.confidence_score,
                    "recommended_action": r.recommended_action,
                    "created_at": r.created_at.isoformat(),
                }
                for r in reports
            ]
        },
    )


@router.get("/v1/projects/{project_id}/rca/reports/{rca_id}")
async def get_rca_report(
    project_id: str,
    rca_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _rca_repo(request)
    report = repo.get_report(rca_id)
    if report is None or report.project_id != project_id:
        raise GatewayError(code="not_found", message="RCA report not found.", status_code=404)

    return JSONResponse(
        status_code=200,
        content={
            "rca_id": str(report.rca_id),
            "project_id": report.project_id,
            "trace_id": str(report.trace_id) if report.trace_id else None,
            "incident_id": str(report.incident_id) if report.incident_id else None,
            "failure_category": report.failure_category,
            "root_cause_summary": report.root_cause_summary,
            "confidence_score": report.confidence_score,
            "recommended_action": report.recommended_action,
            "created_at": report.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/rca/clusters")
async def list_failure_clusters(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _rca_repo(request)
    clusters = repo.list_clusters(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "clusters": [
                {
                    "cluster_id": str(c.cluster_id),
                    "project_id": c.project_id,
                    "name": c.name,
                    "failure_pattern": c.failure_pattern,
                    "occurrences_count": c.occurrences_count,
                    "first_seen": c.first_seen.isoformat(),
                    "last_seen": c.last_seen.isoformat(),
                }
                for c in clusters
            ]
        },
    )
