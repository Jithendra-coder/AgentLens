"""Add immutable M6 deterministic evaluation results.

Revision ID: 0003_evaluation_results
Revises: 0002_evaluation_runtime
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_evaluation_results"
down_revision = "0002_evaluation_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_schema_version", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_type", sa.String(length=255), nullable=False),
        sa.Column("evaluator_name", sa.String(length=255), nullable=False),
        sa.Column("evaluator_version", sa.String(length=64), nullable=False),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("trace_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "trace_id"],
            ["traces.project_id", "traces.trace_id"],
            name="fk_evaluation_results_trace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["evaluation_jobs.job_id"],
            name="fk_evaluation_results_job",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("result_id"),
        sa.UniqueConstraint("job_id", name="uq_evaluation_results_job"),
    )
    op.create_index(
        "ix_evaluation_results_project_created",
        "evaluation_results",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_evaluation_results_project_trace",
        "evaluation_results",
        ["project_id", "trace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_project_trace", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_project_created", table_name="evaluation_results")
    op.drop_table("evaluation_results")
