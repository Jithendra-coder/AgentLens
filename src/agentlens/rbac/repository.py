"""Repository interfaces and implementations for Tenancy, Projects, Members, and API Keys."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, desc, select, update
from sqlalchemy.engine import Engine

from agentlens.rbac.models import (
    ApiKeyInfo,
    Organization,
    Project,
    ProjectMember,
    Role,
    get_role_permissions,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import api_keys, organizations, project_members, projects


def hash_api_key(key: str) -> str:
    """Hash an API key with SHA-256 for secure constant-time database matching."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class RbacRepository(Protocol):
    def create_organization(self, name: str, slug: str) -> Organization: ...
    def get_organization(self, org_id: UUID) -> Organization | None: ...
    def list_organizations(self) -> Sequence[Organization]: ...
    def create_project(
        self, project_id: str, name: str, slug: str, org_id: UUID | None = None
    ) -> Project: ...
    def get_project(self, project_id: str) -> Project | None: ...
    def list_projects(self, org_id: UUID | None = None) -> Sequence[Project]: ...
    def add_project_member(self, project_id: str, user_id: str, role: str) -> ProjectMember: ...
    def list_project_members(self, project_id: str) -> Sequence[ProjectMember]: ...
    def remove_project_member(self, project_id: str, user_id: str) -> bool: ...
    def create_api_key(
        self,
        project_id: str,
        name: str,
        role: str = Role.PROJECT_EDITOR.value,
        permissions: Sequence[str] | None = None,
        org_id: UUID | None = None,
    ) -> tuple[ApiKeyInfo, str]: ...
    def authenticate_key(self, raw_key: str) -> ApiKeyInfo | None: ...
    def list_api_keys(self, project_id: str) -> Sequence[ApiKeyInfo]: ...
    def revoke_api_key(self, project_id: str, key_id: str) -> bool: ...


class InMemoryRbacRepository:
    """In-memory RBAC repository for zero-dependency tests."""

    def __init__(self) -> None:
        self._orgs: dict[UUID, Organization] = {}
        self._projects: dict[str, Project] = {}
        self._members: dict[UUID, ProjectMember] = {}
        self._keys: dict[str, tuple[ApiKeyInfo, str]] = {}  # key_hash -> (info, raw_key)

    def create_organization(self, name: str, slug: str) -> Organization:
        org = Organization(org_id=uuid4(), name=name, slug=slug, created_at=datetime.now(UTC))
        self._orgs[org.org_id] = org
        return org

    def get_organization(self, org_id: UUID) -> Organization | None:
        return self._orgs.get(org_id)

    def list_organizations(self) -> Sequence[Organization]:
        return list(self._orgs.values())

    def create_project(
        self, project_id: str, name: str, slug: str, org_id: UUID | None = None
    ) -> Project:
        proj = Project(
            project_id=project_id,
            name=name,
            slug=slug,
            org_id=org_id,
            created_at=datetime.now(UTC),
        )
        self._projects[project_id] = proj
        return proj

    def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    def list_projects(self, org_id: UUID | None = None) -> Sequence[Project]:
        if org_id is None:
            return list(self._projects.values())
        return [p for p in self._projects.values() if p.org_id == org_id]

    def add_project_member(self, project_id: str, user_id: str, role: str) -> ProjectMember:
        member = ProjectMember(
            member_id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            role=role,
            created_at=datetime.now(UTC),
        )
        self._members[member.member_id] = member
        return member

    def list_project_members(self, project_id: str) -> Sequence[ProjectMember]:
        return [m for m in self._members.values() if m.project_id == project_id]

    def remove_project_member(self, project_id: str, user_id: str) -> bool:
        to_delete = [
            m.member_id
            for m in self._members.values()
            if m.project_id == project_id and m.user_id == user_id
        ]
        for mid in to_delete:
            del self._members[mid]
        return len(to_delete) > 0

    def create_api_key(
        self,
        project_id: str,
        name: str,
        role: str = Role.PROJECT_EDITOR.value,
        permissions: Sequence[str] | None = None,
        org_id: UUID | None = None,
    ) -> tuple[ApiKeyInfo, str]:
        token = f"al_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(token)
        assigned_perms = frozenset(permissions) if permissions else get_role_permissions(role)
        info = ApiKeyInfo(
            key_id=f"key_{secrets.token_hex(8)}",
            project_id=project_id,
            name=name,
            role=role,
            permissions=assigned_perms,
            org_id=org_id,
            created_at=datetime.now(UTC),
        )
        self._keys[key_hash] = (info, token)
        return info, token

    def authenticate_key(self, raw_key: str) -> ApiKeyInfo | None:
        key_hash = hash_api_key(raw_key)
        item = self._keys.get(key_hash)
        if item is None:
            return None
        info, _ = item
        if not info.is_active:
            return None
        return info

    def list_api_keys(self, project_id: str) -> Sequence[ApiKeyInfo]:
        return [info for info, _ in self._keys.values() if info.project_id == project_id]

    def revoke_api_key(self, project_id: str, key_id: str) -> bool:
        for key_hash, (info, raw) in list(self._keys.items()):
            if info.project_id == project_id and info.key_id == key_id:
                revoked_info = ApiKeyInfo(
                    key_id=info.key_id,
                    project_id=info.project_id,
                    name=info.name,
                    role=info.role,
                    permissions=info.permissions,
                    org_id=info.org_id,
                    created_at=info.created_at,
                    expires_at=info.expires_at,
                    revoked_at=datetime.now(UTC),
                )
                self._keys[key_hash] = (revoked_info, raw)
                return True
        return False


class PostgresRbacRepository:
    """PostgreSQL-backed RBAC and Tenancy Repository."""

    def __init__(self, config: DatabaseConfig, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(
            config.sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
        )

    def create_organization(self, name: str, slug: str) -> Organization:
        org_id = uuid4()
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            conn.execute(
                organizations.insert().values(
                    org_id=org_id,
                    name=name,
                    slug=slug,
                    created_at=now,
                    status="active",
                )
            )
        return Organization(org_id=org_id, name=name, slug=slug, created_at=now)

    def get_organization(self, org_id: UUID) -> Organization | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(organizations).where(organizations.c.org_id == org_id)
            ).mappings().one_or_none()
            if row is None:
                return None
            return Organization(
                org_id=cast(UUID, row["org_id"]),
                name=str(row["name"]),
                slug=str(row["slug"]),
                created_at=cast(datetime, row["created_at"]),
                status=str(row["status"]),
            )

    def list_organizations(self) -> Sequence[Organization]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(organizations).order_by(desc(organizations.c.created_at))
            ).mappings().all()
            return [
                Organization(
                    org_id=cast(UUID, r["org_id"]),
                    name=str(r["name"]),
                    slug=str(r["slug"]),
                    created_at=cast(datetime, r["created_at"]),
                    status=str(r["status"]),
                )
                for r in rows
            ]

    def create_project(
        self, project_id: str, name: str, slug: str, org_id: UUID | None = None
    ) -> Project:
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            conn.execute(
                projects.insert().values(
                    project_id=project_id,
                    org_id=org_id,
                    name=name,
                    slug=slug,
                    created_at=now,
                    status="active",
                )
            )
        return Project(
            project_id=project_id,
            org_id=org_id,
            name=name,
            slug=slug,
            created_at=now,
        )

    def get_project(self, project_id: str) -> Project | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(projects).where(projects.c.project_id == project_id)
            ).mappings().one_or_none()
            if row is None:
                return None
            return Project(
                project_id=str(row["project_id"]),
                org_id=cast(UUID | None, row["org_id"]),
                name=str(row["name"]),
                slug=str(row["slug"]),
                created_at=cast(datetime, row["created_at"]),
                status=str(row["status"]),
            )

    def list_projects(self, org_id: UUID | None = None) -> Sequence[Project]:
        with self.engine.connect() as conn:
            query = select(projects)
            if org_id is not None:
                query = query.where(projects.c.org_id == org_id)
            rows = conn.execute(query.order_by(desc(projects.c.created_at))).mappings().all()
            return [
                Project(
                    project_id=str(r["project_id"]),
                    org_id=cast(UUID | None, r["org_id"]),
                    name=str(r["name"]),
                    slug=str(r["slug"]),
                    created_at=cast(datetime, r["created_at"]),
                    status=str(r["status"]),
                )
                for r in rows
            ]

    def add_project_member(self, project_id: str, user_id: str, role: str) -> ProjectMember:
        member_id = uuid4()
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            conn.execute(
                project_members.insert().values(
                    member_id=member_id,
                    project_id=project_id,
                    user_id=user_id,
                    role=role,
                    created_at=now,
                )
            )
        return ProjectMember(
            member_id=member_id,
            project_id=project_id,
            user_id=user_id,
            role=role,
            created_at=now,
        )

    def list_project_members(self, project_id: str) -> Sequence[ProjectMember]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(project_members).where(project_members.c.project_id == project_id)
            ).mappings().all()
            return [
                ProjectMember(
                    member_id=cast(UUID, r["member_id"]),
                    project_id=str(r["project_id"]),
                    user_id=str(r["user_id"]),
                    role=str(r["role"]),
                    created_at=cast(datetime, r["created_at"]),
                )
                for r in rows
            ]

    def remove_project_member(self, project_id: str, user_id: str) -> bool:
        with self.engine.begin() as conn:
            res = conn.execute(
                project_members.delete().where(
                    and_(
                        project_members.c.project_id == project_id,
                        project_members.c.user_id == user_id,
                    )
                )
            )
            return bool(int(getattr(res, "rowcount", 0) or 0) > 0)

    def create_api_key(
        self,
        project_id: str,
        name: str,
        role: str = Role.PROJECT_EDITOR.value,
        permissions: Sequence[str] | None = None,
        org_id: UUID | None = None,
    ) -> tuple[ApiKeyInfo, str]:
        token = f"al_{secrets.token_urlsafe(32)}"
        key_hash = hash_api_key(token)
        key_id = f"key_{secrets.token_hex(8)}"
        now = datetime.now(UTC)
        assigned_perms = list(permissions) if permissions else list(get_role_permissions(role))

        with self.engine.begin() as conn:
            conn.execute(
                api_keys.insert().values(
                    key_id=key_id,
                    key_hash=key_hash,
                    project_id=project_id,
                    org_id=org_id,
                    name=name,
                    role=role,
                    permissions=assigned_perms,
                    created_at=now,
                )
            )

        info = ApiKeyInfo(
            key_id=key_id,
            project_id=project_id,
            name=name,
            role=role,
            permissions=frozenset(assigned_perms),
            org_id=org_id,
            created_at=now,
        )
        return info, token

    def authenticate_key(self, raw_key: str) -> ApiKeyInfo | None:
        key_hash = hash_api_key(raw_key)
        with self.engine.connect() as conn:
            row = conn.execute(
                select(api_keys).where(
                    and_(
                        api_keys.c.key_hash == key_hash,
                        api_keys.c.revoked_at.is_(None),
                    )
                )
            ).mappings().one_or_none()
            if row is None:
                return None
            raw_perms = row["permissions"]
            if isinstance(raw_perms, (list, set, tuple)):
                perms = frozenset(raw_perms)
            else:
                perms = frozenset()
            return ApiKeyInfo(
                key_id=str(row["key_id"]),
                project_id=str(row["project_id"]),
                name=str(row["name"]),
                role=str(row["role"]),
                permissions=perms,
                org_id=cast(UUID | None, row["org_id"]),
                created_at=cast(datetime, row["created_at"]),
                expires_at=cast(datetime | None, row["expires_at"]),
                revoked_at=cast(datetime | None, row["revoked_at"]),
            )

    def list_api_keys(self, project_id: str) -> Sequence[ApiKeyInfo]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(api_keys)
                .where(api_keys.c.project_id == project_id)
                .order_by(desc(api_keys.c.created_at))
            ).mappings().all()
            output: list[ApiKeyInfo] = []
            for r in rows:
                raw_perms = r["permissions"]
                if isinstance(raw_perms, (list, set, tuple)):
                    perms = frozenset(raw_perms)
                else:
                    perms = frozenset()
                output.append(
                    ApiKeyInfo(
                        key_id=str(r["key_id"]),
                        project_id=str(r["project_id"]),
                        name=str(r["name"]),
                        role=str(r["role"]),
                        permissions=perms,
                        org_id=cast(UUID | None, r["org_id"]),
                        created_at=cast(datetime, r["created_at"]),
                        expires_at=cast(datetime | None, r["expires_at"]),
                        revoked_at=cast(datetime | None, r["revoked_at"]),
                    )
                )
            return output

    def revoke_api_key(self, project_id: str, key_id: str) -> bool:
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            res = conn.execute(
                update(api_keys)
                .where(
                    and_(
                        api_keys.c.project_id == project_id,
                        api_keys.c.key_id == key_id,
                    )
                )
                .values(revoked_at=now)
            )
            return bool(int(getattr(res, "rowcount", 0) or 0) > 0)
