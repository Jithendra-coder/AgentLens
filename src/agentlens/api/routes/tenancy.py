"""Tenancy and RBAC management routes: Organizations, Projects, Members, and API Keys."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_permission
from agentlens.api.errors import GatewayError
from agentlens.rbac.models import Permission, Role
from agentlens.rbac.repository import RbacRepository

router = APIRouter()
MEMBERS_MANAGE_DEP = Depends(require_permission(Permission.MEMBERS_MANAGE.value))
KEYS_MANAGE_DEP = Depends(require_permission(Permission.KEYS_MANAGE.value))
SYSTEM_ADMIN_DEP = Depends(require_permission(Permission.SYSTEM_ADMIN.value))


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)


class CreateProjectRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)


class AddMemberRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    role: str = Field(default=Role.PROJECT_VIEWER.value)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(default=Role.PROJECT_EDITOR.value)
    permissions: list[str] | None = None


def _get_rbac_repo(request: Request) -> RbacRepository:
    repo = getattr(request.app.state.gateway, "rbac_repository", None)
    if repo is None:
        raise GatewayError(
            code="tenancy_unavailable",
            message="Tenancy repository is not configured.",
            status_code=503,
        )
    return cast(RbacRepository, repo)


# Organizations
@router.post("/v1/organizations")
async def create_organization(
    payload: CreateOrgRequest,
    request: Request,
    auth: AuthContext = SYSTEM_ADMIN_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    org = repo.create_organization(payload.name, payload.slug)
    return {
        "org_id": str(org.org_id),
        "name": org.name,
        "slug": org.slug,
        "created_at": org.created_at.isoformat(),
        "status": org.status,
    }


@router.get("/v1/organizations")
async def list_organizations(
    request: Request,
    auth: AuthContext = SYSTEM_ADMIN_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    orgs = repo.list_organizations()
    return {
        "organizations": [
            {
                "org_id": str(o.org_id),
                "name": o.name,
                "slug": o.slug,
                "created_at": o.created_at.isoformat(),
                "status": o.status,
            }
            for o in orgs
        ]
    }


@router.get("/v1/organizations/{org_id}")
async def get_organization(
    org_id: UUID,
    request: Request,
    auth: AuthContext = SYSTEM_ADMIN_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    org = repo.get_organization(org_id)
    if org is None:
        raise GatewayError(code="not_found", message="Organization not found.", status_code=404)
    return {
        "org_id": str(org.org_id),
        "name": org.name,
        "slug": org.slug,
        "created_at": org.created_at.isoformat(),
        "status": org.status,
    }


# Projects
@router.post("/v1/organizations/{org_id}/projects")
async def create_project_in_org(
    org_id: UUID,
    payload: CreateProjectRequest,
    request: Request,
    auth: AuthContext = SYSTEM_ADMIN_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    proj = repo.create_project(
        project_id=payload.project_id,
        name=payload.name,
        slug=payload.slug,
        org_id=org_id,
    )
    return {
        "project_id": proj.project_id,
        "org_id": str(proj.org_id) if proj.org_id else None,
        "name": proj.name,
        "slug": proj.slug,
        "created_at": proj.created_at.isoformat(),
        "status": proj.status,
    }


@router.get("/v1/organizations/{org_id}/projects")
async def list_projects_in_org(
    org_id: UUID,
    request: Request,
    auth: AuthContext = SYSTEM_ADMIN_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    projects = repo.list_projects(org_id=org_id)
    return {
        "projects": [
            {
                "project_id": p.project_id,
                "org_id": str(p.org_id) if p.org_id else None,
                "name": p.name,
                "slug": p.slug,
                "created_at": p.created_at.isoformat(),
                "status": p.status,
            }
            for p in projects
        ]
    }


@router.get("/v1/projects")
async def list_projects(
    request: Request,
    auth: AuthContext = SYSTEM_ADMIN_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    projects = repo.list_projects()
    return {
        "projects": [
            {
                "project_id": p.project_id,
                "org_id": str(p.org_id) if p.org_id else None,
                "name": p.name,
                "slug": p.slug,
                "created_at": p.created_at.isoformat(),
                "status": p.status,
            }
            for p in projects
        ]
    }


# Project Members
@router.post("/v1/projects/{project_id}/members")
async def add_project_member(
    project_id: str,
    payload: AddMemberRequest,
    request: Request,
    auth: AuthContext = MEMBERS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    member = repo.add_project_member(
        project_id=project_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    return {
        "member_id": str(member.member_id),
        "project_id": member.project_id,
        "user_id": member.user_id,
        "role": member.role,
        "created_at": member.created_at.isoformat(),
    }


@router.get("/v1/projects/{project_id}/members")
async def list_project_members(
    project_id: str,
    request: Request,
    auth: AuthContext = MEMBERS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    members = repo.list_project_members(project_id)
    return {
        "members": [
            {
                "member_id": str(m.member_id),
                "project_id": m.project_id,
                "user_id": m.user_id,
                "role": m.role,
                "created_at": m.created_at.isoformat(),
            }
            for m in members
        ]
    }


@router.delete("/v1/projects/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: str,
    user_id: str,
    request: Request,
    auth: AuthContext = MEMBERS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    success = repo.remove_project_member(project_id, user_id)
    if not success:
        raise GatewayError(code="not_found", message="Member not found.", status_code=404)
    return {"deleted": True, "project_id": project_id, "user_id": user_id}


# API Keys
@router.post("/v1/projects/{project_id}/api-keys")
async def create_api_key(
    project_id: str,
    payload: CreateApiKeyRequest,
    request: Request,
    auth: AuthContext = KEYS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    info, raw_key = repo.create_api_key(
        project_id=project_id,
        name=payload.name,
        role=payload.role,
        permissions=payload.permissions,
    )
    return {
        "key_id": info.key_id,
        "project_id": info.project_id,
        "name": info.name,
        "role": info.role,
        "permissions": sorted(list(info.permissions)),
        "created_at": info.created_at.isoformat(),
        "api_key": raw_key,  # Returned only once upon creation
    }


@router.get("/v1/projects/{project_id}/api-keys")
async def list_api_keys(
    project_id: str,
    request: Request,
    auth: AuthContext = KEYS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    keys = repo.list_api_keys(project_id)
    return {
        "api_keys": [
            {
                "key_id": k.key_id,
                "project_id": k.project_id,
                "name": k.name,
                "role": k.role,
                "permissions": sorted(list(k.permissions)),
                "created_at": k.created_at.isoformat(),
                "is_active": k.is_active,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            }
            for k in keys
        ]
    }


@router.delete("/v1/projects/{project_id}/api-keys/{key_id}")
async def revoke_api_key(
    project_id: str,
    key_id: str,
    request: Request,
    auth: AuthContext = KEYS_MANAGE_DEP,
) -> dict[str, Any]:
    del auth
    repo = _get_rbac_repo(request)
    success = repo.revoke_api_key(project_id, key_id)
    if not success:
        raise GatewayError(code="not_found", message="API key not found.", status_code=404)
    return {"revoked": True, "project_id": project_id, "key_id": key_id}
