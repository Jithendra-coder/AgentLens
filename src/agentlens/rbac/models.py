"""Role-Based Access Control (RBAC) models and permission mappings ."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    ORG_ADMIN = "org_admin"
    PROJECT_ADMIN = "project_admin"
    PROJECT_EDITOR = "project_editor"
    PROJECT_VIEWER = "project_viewer"
    SERVICE_INGESTION = "service_ingestion"
    SERVICE_EVALUATOR = "service_evaluator"


class Permission(StrEnum):
    TRACES_WRITE = "traces:write"
    TRACES_READ = "traces:read"
    EVALUATIONS_RUN = "evaluations:run"
    EVALUATIONS_READ = "evaluations:read"
    DATASETS_MANAGE = "datasets:manage"
    REPLAYS_MANAGE = "replays:manage"
    REGRESSIONS_MANAGE = "regressions:manage"
    QUALITY_GATES_MANAGE = "quality_gates:manage"
    MEMBERS_MANAGE = "members:manage"
    KEYS_MANAGE = "keys:manage"
    SYSTEM_ADMIN = "system:admin"


ALL_PERMISSIONS: frozenset[str] = frozenset(p.value for p in Permission)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.ORG_ADMIN.value: ALL_PERMISSIONS,
    Role.PROJECT_ADMIN.value: frozenset(
        {
            Permission.TRACES_WRITE.value,
            Permission.TRACES_READ.value,
            Permission.EVALUATIONS_RUN.value,
            Permission.EVALUATIONS_READ.value,
            Permission.DATASETS_MANAGE.value,
            Permission.REPLAYS_MANAGE.value,
            Permission.REGRESSIONS_MANAGE.value,
            Permission.QUALITY_GATES_MANAGE.value,
            Permission.MEMBERS_MANAGE.value,
            Permission.KEYS_MANAGE.value,
            Permission.SYSTEM_ADMIN.value,
        }
    ),
    Role.PROJECT_EDITOR.value: frozenset(
        {
            Permission.TRACES_WRITE.value,
            Permission.TRACES_READ.value,
            Permission.EVALUATIONS_RUN.value,
            Permission.EVALUATIONS_READ.value,
            Permission.DATASETS_MANAGE.value,
            Permission.REPLAYS_MANAGE.value,
            Permission.REGRESSIONS_MANAGE.value,
            Permission.QUALITY_GATES_MANAGE.value,
        }
    ),
    Role.PROJECT_VIEWER.value: frozenset(
        {
            Permission.TRACES_READ.value,
            Permission.EVALUATIONS_READ.value,
        }
    ),
    Role.SERVICE_INGESTION.value: frozenset(
        {
            Permission.TRACES_WRITE.value,
            Permission.TRACES_READ.value,
        }
    ),
    Role.SERVICE_EVALUATOR.value: frozenset(
        {
            Permission.TRACES_READ.value,
            Permission.EVALUATIONS_RUN.value,
            Permission.EVALUATIONS_READ.value,
        }
    ),
}


def get_role_permissions(role: str) -> frozenset[str]:
    """Return default permissions for a role, defaulting to viewer permissions."""
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS[Role.PROJECT_VIEWER.value])


@dataclass(frozen=True, slots=True)
class Organization:
    org_id: UUID
    name: str
    slug: str
    created_at: datetime
    status: str = "active"


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    name: str
    slug: str
    created_at: datetime
    org_id: UUID | None = None
    status: str = "active"


@dataclass(frozen=True, slots=True)
class ProjectMember:
    member_id: UUID
    project_id: str
    user_id: str
    role: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ApiKeyInfo:
    key_id: str
    project_id: str
    name: str
    role: str
    permissions: frozenset[str]
    created_at: datetime
    org_id: UUID | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
