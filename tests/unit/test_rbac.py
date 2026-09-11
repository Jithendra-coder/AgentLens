"""Unit tests for Multi-Tenant RBAC models, repository, and key authentication."""

from __future__ import annotations

from agentlens.api.auth import RbacApiKeyAuthenticator
from agentlens.rbac.models import (
    ALL_PERMISSIONS,
    Permission,
    Role,
    get_role_permissions,
)
from agentlens.rbac.repository import InMemoryRbacRepository, hash_api_key


def test_role_permissions_hierarchy() -> None:
    org_admin_perms = get_role_permissions(Role.ORG_ADMIN.value)
    assert org_admin_perms == ALL_PERMISSIONS

    proj_admin_perms = get_role_permissions(Role.PROJECT_ADMIN.value)
    assert Permission.KEYS_MANAGE.value in proj_admin_perms
    assert Permission.MEMBERS_MANAGE.value in proj_admin_perms

    editor_perms = get_role_permissions(Role.PROJECT_EDITOR.value)
    assert Permission.TRACES_WRITE.value in editor_perms
    assert Permission.EVALUATIONS_RUN.value in editor_perms
    assert Permission.KEYS_MANAGE.value not in editor_perms

    viewer_perms = get_role_permissions(Role.PROJECT_VIEWER.value)
    assert Permission.TRACES_READ.value in viewer_perms
    assert Permission.TRACES_WRITE.value not in viewer_perms
    assert Permission.EVALUATIONS_RUN.value not in viewer_perms

    ingestion_perms = get_role_permissions(Role.SERVICE_INGESTION.value)
    assert Permission.TRACES_WRITE.value in ingestion_perms
    assert Permission.EVALUATIONS_RUN.value not in ingestion_perms


def test_hash_api_key_deterministic() -> None:
    token = "al_secret_token_12345"
    h1 = hash_api_key(token)
    h2 = hash_api_key(token)
    assert h1 == h2
    assert len(h1) == 64


def test_in_memory_rbac_repository_tenancy() -> None:
    repo = InMemoryRbacRepository()

    # Organizations
    org = repo.create_organization("Acme Corp", "acme-corp")
    assert org.name == "Acme Corp"
    assert org.slug == "acme-corp"

    fetched_org = repo.get_organization(org.org_id)
    assert fetched_org is not None
    assert fetched_org.name == "Acme Corp"
    assert len(repo.list_organizations()) == 1

    # Projects
    proj = repo.create_project("proj-acme-1", "AI Agent Main", "ai-agent-main", org.org_id)
    assert proj.project_id == "proj-acme-1"
    assert proj.org_id == org.org_id

    fetched_proj = repo.get_project("proj-acme-1")
    assert fetched_proj is not None
    assert len(repo.list_projects(org.org_id)) == 1

    # Members
    member = repo.add_project_member("proj-acme-1", "alice@example.com", Role.PROJECT_ADMIN.value)
    assert member.user_id == "alice@example.com"
    assert len(repo.list_project_members("proj-acme-1")) == 1

    assert repo.remove_project_member("proj-acme-1", "alice@example.com") is True
    assert len(repo.list_project_members("proj-acme-1")) == 0


def test_in_memory_rbac_repository_api_keys_and_authenticator() -> None:
    repo = InMemoryRbacRepository()
    info, token = repo.create_api_key(
        project_id="proj-100",
        name="Ingestion Exporter Key",
        role=Role.SERVICE_INGESTION.value,
    )
    assert token.startswith("al_")
    assert info.role == Role.SERVICE_INGESTION.value
    assert Permission.TRACES_WRITE.value in info.permissions

    # Authenticate via repo
    auth_info = repo.authenticate_key(token)
    assert auth_info is not None
    assert auth_info.key_id == info.key_id
    assert auth_info.project_id == "proj-100"

    # Authenticate via RbacApiKeyAuthenticator
    authenticator = RbacApiKeyAuthenticator(repo)
    ctx = authenticator.authenticate(token)
    assert ctx is not None
    assert ctx.key_id == info.key_id
    assert ctx.project_id == "proj-100"
    assert ctx.role == Role.SERVICE_INGESTION.value
    assert Permission.TRACES_WRITE.value in ctx.permissions

    # Revoke key
    assert repo.revoke_api_key("proj-100", info.key_id) is True
    assert repo.authenticate_key(token) is None
    assert authenticator.authenticate(token) is None
