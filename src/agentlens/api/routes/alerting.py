"""Multi-channel alerting and incident intelligence API routes ."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.alerting.manager import IncidentManager
from agentlens.alerting.models import (
    AlertRule,
    AlertTriggerEvent,
    IncidentRecord,
)
from agentlens.alerting.repository import (
    AlertingRepository,
    InMemoryAlertingRepository,
)
from agentlens.alerting.router import AlertRouter
from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class CreateAlertRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    trigger_type: str = Field(
        min_length=1,
        max_length=64,
        pattern="^(drift_alert|health_critical|budget_exhausted|quality_gate_fail)$",
    )
    channel_type: str = Field(
        min_length=1,
        max_length=32,
        pattern="^(slack|pagerduty|webhook|email)$",
    )
    destination_url: str = Field(min_length=1, max_length=1024)
    cooldown_seconds: int = Field(default=300, ge=0, le=86400)


class TriggerIncidentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    details: str = Field(min_length=1, max_length=4096)
    trigger_type: str = Field(
        min_length=1,
        max_length=64,
        pattern="^(drift_alert|health_critical|budget_exhausted|quality_gate_fail)$",
    )
    severity: str = Field(default="P2", pattern="^(P1|P2|P3)$")


class UpdateIncidentStatusRequest(BaseModel):
    status: str = Field(pattern="^(open|acknowledged|resolved)$")
    user: str | None = Field(default=None, max_length=255)


def _alerting_repo(request: Request) -> AlertingRepository:
    repo = getattr(request.app.state.gateway, "alerting_repository", None)
    if repo is None:
        repo = InMemoryAlertingRepository()
        request.app.state.gateway.alerting_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/alerts/rules")
async def create_alert_rule(
    project_id: str,
    body: CreateAlertRuleRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _alerting_repo(request)
    rule = AlertRule(
        rule_id=uuid4(),
        project_id=project_id,
        name=body.name,
        trigger_type=body.trigger_type,
        channel_type=body.channel_type,
        destination_url=body.destination_url,
        cooldown_seconds=body.cooldown_seconds,
        is_enabled=True,
    )
    saved = repo.save_rule(rule)

    return JSONResponse(
        status_code=200,
        content={
            "rule_id": str(saved.rule_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "trigger_type": saved.trigger_type,
            "channel_type": saved.channel_type,
            "destination_url": saved.destination_url,
            "cooldown_seconds": saved.cooldown_seconds,
            "is_enabled": saved.is_enabled,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/alerts/rules")
async def list_alert_rules(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _alerting_repo(request)
    rules = repo.list_rules(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "rules": [
                {
                    "rule_id": str(r.rule_id),
                    "project_id": r.project_id,
                    "name": r.name,
                    "trigger_type": r.trigger_type,
                    "channel_type": r.channel_type,
                    "destination_url": r.destination_url,
                    "cooldown_seconds": r.cooldown_seconds,
                    "is_enabled": r.is_enabled,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rules
            ]
        },
    )


@router.delete("/v1/projects/{project_id}/alerts/rules/{rule_id}")
async def delete_alert_rule(
    project_id: str,
    rule_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _alerting_repo(request)
    r = repo.get_rule(rule_id)
    if r is None or r.project_id != project_id:
        raise GatewayError(code="not_found", message="Alert rule not found.", status_code=404)
    deleted = repo.delete_rule(rule_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/alerts/incidents")
async def trigger_incident(
    project_id: str,
    body: TriggerIncidentRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _alerting_repo(request)
    rules = repo.list_rules(project_id)

    incident = IncidentRecord(
        incident_id=uuid4(),
        project_id=project_id,
        title=body.title,
        details=body.details,
        severity=body.severity,
        status="open",
    )
    saved_incident = repo.save_incident(incident)

    # Route alerts
    alert_router = AlertRouter()
    event = AlertTriggerEvent(
        project_id=project_id,
        trigger_type=body.trigger_type,
        title=body.title,
        details=body.details,
        severity=body.severity,
    )
    dispatch_results = alert_router.route_event(event, rules)

    return JSONResponse(
        status_code=200,
        content={
            "incident_id": str(saved_incident.incident_id),
            "project_id": saved_incident.project_id,
            "title": saved_incident.title,
            "details": saved_incident.details,
            "severity": saved_incident.severity,
            "status": saved_incident.status,
            "created_at": saved_incident.created_at.isoformat(),
            "dispatches": [
                {
                    "rule_id": str(d.rule_id),
                    "channel_type": d.channel_type,
                    "destination_url": d.destination_url,
                    "dispatched": d.dispatched,
                    "reason": d.reason,
                }
                for d in dispatch_results
            ],
        },
    )


@router.get("/v1/projects/{project_id}/alerts/incidents")
async def list_incidents(
    project_id: str,
    request: Request,
    status: str | None = None,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _alerting_repo(request)
    incidents = repo.list_incidents(project_id, status=status)

    return JSONResponse(
        status_code=200,
        content={
            "incidents": [
                {
                    "incident_id": str(i.incident_id),
                    "project_id": i.project_id,
                    "title": i.title,
                    "details": i.details,
                    "severity": i.severity,
                    "status": i.status,
                    "acknowledged_by": i.acknowledged_by,
                    "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
                    "created_at": i.created_at.isoformat(),
                }
                for i in incidents
            ]
        },
    )


@router.patch("/v1/projects/{project_id}/alerts/incidents/{incident_id}")
async def update_incident_status(
    project_id: str,
    incident_id: UUID,
    body: UpdateIncidentStatusRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _alerting_repo(request)
    incident = repo.get_incident(incident_id)
    if incident is None or incident.project_id != project_id:
        raise GatewayError(code="not_found", message="Incident not found.", status_code=404)

    updated = IncidentManager.update_status(incident, body.status, user=body.user)
    saved = repo.save_incident(updated)

    return JSONResponse(
        status_code=200,
        content={
            "incident_id": str(saved.incident_id),
            "project_id": saved.project_id,
            "title": saved.title,
            "severity": saved.severity,
            "status": saved.status,
            "acknowledged_by": saved.acknowledged_by,
            "resolved_at": saved.resolved_at.isoformat() if saved.resolved_at else None,
            "created_at": saved.created_at.isoformat(),
        },
    )
