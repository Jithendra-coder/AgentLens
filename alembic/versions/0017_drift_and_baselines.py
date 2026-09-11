"""Migration 0017: Quality baselines and statistical drift detection ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. quality_baselines
    op.create_table(
        "quality_baselines",
        sa.Column("baseline_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("baseline_mean", sa.Float(), nullable=False),
        sa.Column("baseline_std", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("window_size", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_quality_baselines_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_quality_baselines_project", "quality_baselines", ["project_id"])

    # 2. drift_observations
    op.create_table(
        "drift_observations",
        sa.Column("drift_id", uuid_type, primary_key=True),
        sa.Column("baseline_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("observed_mean", sa.Float(), nullable=False),
        sa.Column("z_score", sa.Float(), nullable=False),
        sa.Column("drift_magnitude_pct", sa.Float(), nullable=False),
        sa.Column("drift_type", sa.String(length=64), nullable=False),
        sa.Column("is_alert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["baseline_id"],
            ["quality_baselines.baseline_id"],
            name="fk_drift_observations_baseline_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_drift_observations_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_drift_observations_baseline", "drift_observations", ["baseline_id"])
    op.create_index("ix_drift_observations_project", "drift_observations", ["project_id"])


def downgrade() -> None:
    op.drop_table("drift_observations")
    op.drop_table("quality_baselines")
