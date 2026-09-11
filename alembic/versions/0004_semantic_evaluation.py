"""Add M7 evaluation modes and semantic judge invocation provenance."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_semantic_evaluation"
down_revision = "0003_evaluation_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_results",
        sa.Column("evaluation_mode", sa.String(length=32), nullable=True),
    )
    op.execute(
        "UPDATE evaluation_results SET evaluation_mode = 'deterministic' "
        "WHERE evaluation_mode IS NULL"
    )
    op.alter_column("evaluation_results", "evaluation_mode", nullable=False)
    op.create_table(
        "evaluation_judge_invocations",
        sa.Column("invocation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("judge_profile", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["evaluation_results.result_id"],
            name="fk_evaluation_judge_invocations_result",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["evaluation_jobs.job_id"],
            name="fk_evaluation_judge_invocations_job",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("invocation_id"),
    )
    op.create_index(
        "ix_evaluation_judge_invocations_project_result",
        "evaluation_judge_invocations",
        ["project_id", "result_id"],
    )
    op.create_index(
        "ix_evaluation_judge_invocations_job",
        "evaluation_judge_invocations",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_judge_invocations_job", table_name="evaluation_judge_invocations")
    op.drop_index(
        "ix_evaluation_judge_invocations_project_result",
        table_name="evaluation_judge_invocations",
    )
    op.drop_table("evaluation_judge_invocations")
    op.drop_column("evaluation_results", "evaluation_mode")
