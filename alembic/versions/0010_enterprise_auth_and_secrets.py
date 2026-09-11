"""Add users, user_sessions, and encrypted_secrets tables for Enterprise Auth & Secrets."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0010_enterprise_auth_and_secrets"
down_revision = "0009_organizations_and_rbac"
branch_labels = None
depends_on = None

uuid_type = UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    # 1. Users
    op.create_table(
        "users",
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("auth_provider", sa.String(64), nullable=False, server_default="local"),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 2. User Sessions
    op.create_table(
        "user_sessions",
        sa.Column("session_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("session_id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name="fk_user_sessions_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_refresh_hash", "user_sessions", ["refresh_token_hash"])

    # 3. Encrypted Secrets (AES-256-GCM encrypted provider credentials)
    op.create_table(
        "encrypted_secrets",
        sa.Column("secret_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("org_id", uuid_type, nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("tag", sa.String(64), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("secret_id"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_encrypted_secrets_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.org_id"],
            name="fk_encrypted_secrets_org_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_encrypted_secrets_project_name"),
    )
    op.create_index("ix_encrypted_secrets_project_id", "encrypted_secrets", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_encrypted_secrets_project_id", table_name="encrypted_secrets")
    op.drop_table("encrypted_secrets")

    op.drop_index("ix_user_sessions_refresh_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
