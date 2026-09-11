"""Governance, immutable compliance audit, and data retention API routes ."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.governance.chain import AuditHashChain
from agentlens.governance.models import (
    RetentionPolicy,
)
from agentlens.governance.repository import (
    GovernanceRepository,
    InMemoryGovernanceRepository,
)

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class RecordAuditEventRequest(BaseModel):
    action: str = Field(min_length=1, max_length=128)
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: str = Field(min_length=1, max_length=255)
    payload: str = Field(default="{}", max_length=16384)


class CreateRetentionPolicyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    retention_days: int = Field(default=90, ge=1, le=3650)
    auto_redact_pii: bool = Field(default=True)


def _gov_repo(request: Request) -> GovernanceRepository:
    repo = getattr(request.app.state.gateway, "governance_repository", None)
    if repo is None:
        repo = InMemoryGovernanceRepository()
        request.app.state.gateway.governance_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/governance/audit")
async def record_audit_event(
    project_id: str,
    body: RecordAuditEventRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _gov_repo(request)
    actor_id = getattr(context, "principal", "api_key_user")

    ev = repo.append_audit_event(
        project_id=project_id,
        actor_id=str(actor_id),
        action=body.action,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        payload=body.payload,
    )

    return JSONResponse(
        status_code=200,
        content={
            "event_id": str(ev.event_id),
            "project_id": ev.project_id,
            "actor_id": ev.actor_id,
            "action": ev.action,
            "resource_type": ev.resource_type,
            "resource_id": ev.resource_id,
            "payload_hash": ev.payload_hash,
            "previous_event_hash": ev.previous_event_hash,
            "event_hash": ev.event_hash,
            "timestamp": ev.timestamp.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/governance/audit")
async def get_audit_trail_and_verify(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _gov_repo(request)
    events = repo.list_audit_events(project_id)
    verification = AuditHashChain.verify_chain(project_id, events)

    return JSONResponse(
        status_code=200,
        content={
            "project_id": project_id,
            "is_valid": verification.is_valid,
            "total_events": verification.total_events,
            "verification_status": "VERIFIED" if verification.is_valid else "TAMPERED",
            "reason": verification.reason,
            "compromised_event_id": (
                str(verification.compromised_event_id)
                if verification.compromised_event_id
                else None
            ),
            "events": [
                {
                    "event_id": str(e.event_id),
                    "actor_id": e.actor_id,
                    "action": e.action,
                    "resource_type": e.resource_type,
                    "resource_id": e.resource_id,
                    "payload_hash": e.payload_hash,
                    "previous_event_hash": e.previous_event_hash,
                    "event_hash": e.event_hash,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in reversed(events)
            ],
        },
    )


@router.post("/v1/projects/{project_id}/governance/policies")
async def create_retention_policy(
    project_id: str,
    body: CreateRetentionPolicyRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _gov_repo(request)
    policy = RetentionPolicy(
        policy_id=uuid4(),
        project_id=project_id,
        name=body.name,
        retention_days=body.retention_days,
        auto_redact_pii=body.auto_redact_pii,
        is_active=True,
    )
    saved = repo.save_retention_policy(policy)

    return JSONResponse(
        status_code=200,
        content={
            "policy_id": str(saved.policy_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "retention_days": saved.retention_days,
            "auto_redact_pii": saved.auto_redact_pii,
            "is_active": saved.is_active,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/governance/policies")
async def list_retention_policies(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _gov_repo(request)
    policies = repo.list_retention_policies(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "policies": [
                {
                    "policy_id": str(p.policy_id),
                    "project_id": p.project_id,
                    "name": p.name,
                    "retention_days": p.retention_days,
                    "auto_redact_pii": p.auto_redact_pii,
                    "is_active": p.is_active,
                    "created_at": p.created_at.isoformat(),
                }
                for p in policies
            ]
        },
    )


@router.delete("/v1/projects/{project_id}/governance/policies/{policy_id}")
async def delete_retention_policy(
    project_id: str,
    policy_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _gov_repo(request)
    p = repo.get_retention_policy(policy_id)
    if p is None or p.project_id != project_id:
        raise GatewayError(code="not_found", message="Retention policy not found.", status_code=404)
    deleted = repo.delete_retention_policy(policy_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/governance/export")
async def generate_compliance_export(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _gov_repo(request)
    events = repo.list_audit_events(project_id)
    root_hash = events[-1].event_hash if events else ("0" * 64)

    # Compute digital signature over root hash and export timestamp
    now = datetime.now(UTC)
    sig_material = f"{project_id}|{root_hash}|{now.isoformat()}|AGENTLENS_GOVERNANCE_ROOT"
    signature = hashlib.sha256(sig_material.encode("utf-8")).hexdigest()

    return JSONResponse(
        status_code=200,
        content={
            "export_id": str(uuid4()),
            "project_id": project_id,
            "total_audit_events": len(events),
            "root_hash": root_hash,
            "digital_signature": signature,
            "exported_at": now.isoformat(),
            "status": "ATTESTED",
        },
    )
