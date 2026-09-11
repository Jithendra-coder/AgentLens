"""Migration 0018: Continuous production monitoring and health rollups ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. production_monitors
    op.create_table(
        "production_monitors",
        sa.Column("monitor_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sampling_rate", sa.Float(), nullable=False, server_default="0.10"),
        sa.Column("health_status", sa.String(length=32), nullable=False, server_default="healthy"),
        sa.Column("health_index", sa.Float(), nullable=False, server_default="100.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_production_monitors_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_production_monitors_project", "production_monitors", ["project_id"])

    # 2. production_health_snapshots
    op.create_table(
        "production_health_snapshots",
        sa.Column("snapshot_id", uuid_type, primary_key=True),
        sa.Column("monitor_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("health_index", sa.Float(), nullable=False, server_default="100.0"),
        sa.Column("p95_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mean_quality_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("error_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_spans_evaluated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["production_monitors.monitor_id"],
            name="fk_production_health_snapshots_monitor_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_production_health_snapshots_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_production_health_snapshots_monitor", "production_health_snapshots", ["monitor_id"]
    )
    op.create_index(
        "ix_production_health_snapshots_project", "production_health_snapshots", ["project_id"]
    )


def downgrade() -> None:
    op.drop_table("production_health_snapshots")
    op.drop_table("production_monitors")
