"""Migration 0021: Immutable compliance audit trail and retention policies ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. compliance_audit_events
    op.create_table(
        "compliance_audit_events",
        sa.Column("event_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_compliance_audit_events_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_compliance_audit_events_project", "compliance_audit_events", ["project_id"])

    # 2. retention_policies
    op.create_table(
        "retention_policies",
        sa.Column("policy_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("auto_redact_pii", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_retention_policies_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_retention_policies_project", "retention_policies", ["project_id"])


def downgrade() -> None:
    op.drop_table("retention_policies")
    op.drop_table("compliance_audit_events")
