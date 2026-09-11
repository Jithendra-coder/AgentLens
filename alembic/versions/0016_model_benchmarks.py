"""Migration 0016: Model benchmarking, run metrics, and qualification status ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. model_benchmarks
    op.create_table(
        "model_benchmarks",
        sa.Column("benchmark_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_model_benchmarks_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_model_benchmarks_project", "model_benchmarks", ["project_id"])

    # 2. model_benchmark_runs
    op.create_table(
        "model_benchmark_runs",
        sa.Column("run_id", uuid_type, primary_key=True),
        sa.Column("benchmark_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False, server_default="openai"),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mean_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mean_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pass_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["benchmark_id"],
            ["model_benchmarks.benchmark_id"],
            name="fk_model_benchmark_runs_benchmark_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_model_benchmark_runs_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_model_benchmark_runs_benchmark", "model_benchmark_runs", ["benchmark_id"])

    # 3. model_qualifications
    op.create_table(
        "model_qualifications",
        sa.Column("qualification_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False, server_default="openai"),
        sa.Column("is_qualified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("min_required_score", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("latest_run_id", uuid_type, nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_model_qualifications_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["latest_run_id"],
            ["model_benchmark_runs.run_id"],
            name="fk_model_qualifications_run_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_model_qualifications_project", "model_qualifications", ["project_id"])


def downgrade() -> None:
    op.drop_table("model_qualifications")
    op.drop_table("model_benchmark_runs")
    op.drop_table("model_benchmarks")
