"""Add organizations, projects, project members, and scoped API keys  RBAC."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0009_organizations_and_rbac"
down_revision = "0008_worker_heartbeats"
branch_labels = None
depends_on = None

json_type = JSONB().with_variant(sa.JSON(), "sqlite")
uuid_type = UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    # 1. Organizations
    op.create_table(
        "organizations",
        sa.Column("org_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("org_id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # 2. Projects
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("org_id", uuid_type, nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("project_id"),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.org_id"],
            name="fk_projects_org_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_projects_org_id", "projects", ["org_id"])
    op.create_index("ix_projects_slug", "projects", ["slug"])

    # 3. Project Members
    op.create_table(
        "project_members",
        sa.Column("member_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("member_id"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_project_members_project_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])

    # 4. Scoped API Keys
    op.create_table(
        "api_keys",
        sa.Column("key_id", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("org_id", uuid_type, nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("permissions", json_type, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key_id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_api_keys_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.org_id"],
            name="fk_api_keys_org_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_project_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_index("ix_project_members_project_id", table_name="project_members")
    op.drop_table("project_members")

    op.drop_index("ix_projects_slug", table_name="projects")
    op.drop_index("ix_projects_org_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
