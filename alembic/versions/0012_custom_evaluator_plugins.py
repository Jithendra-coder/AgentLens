"""Migration 0012: Custom Evaluator Plugins table ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")

    op.create_table(
        "custom_evaluator_plugins",
        sa.Column("plugin_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column(
            "evaluator_type",
            sa.String(length=32),
            nullable=False,
            server_default="deterministic",
        ),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("code_body", sa.Text(), nullable=False),
        sa.Column("schema_parameters", json_type, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_custom_evaluators_project_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "project_id",
            "name",
            "version",
            name="uq_custom_evaluators_project_name_version",
        ),
    )
    op.create_index(
        "ix_custom_evaluators_project",
        "custom_evaluator_plugins",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_custom_evaluators_project", table_name="custom_evaluator_plugins")
    op.drop_table("custom_evaluator_plugins")
