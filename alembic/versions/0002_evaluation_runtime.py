"""Add the M5 durable evaluation job ledger and attempt history.

Revision ID: 0002_evaluation_runtime
Revises: 0001_initial_trace_storage
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_evaluation_runtime"
down_revision = "0001_initial_trace_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_schema_version", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_type", sa.String(length=255), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("available_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("claimed_by", sa.String(length=255), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.String(length=1024), nullable=True),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id", "trace_id"],
            ["traces.project_id", "traces.trace_id"],
            name="fk_evaluation_jobs_trace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key_hash",
            name="uq_evaluation_jobs_project_idempotency",
        ),
    )
    op.create_index(
        "ix_evaluation_jobs_dispatch",
        "evaluation_jobs",
        ["state", "available_at", "priority", "created_at"],
    )
    op.create_index(
        "ix_evaluation_jobs_project_created",
        "evaluation_jobs",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_evaluation_jobs_project_trace",
        "evaluation_jobs",
        ["project_id", "trace_id"],
    )
    op.create_table(
        "evaluation_job_attempts",
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("safe_error_message", sa.String(length=1024), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["evaluation_jobs.job_id"],
            name="fk_evaluation_job_attempts_job",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_evaluation_attempt_number"),
    )
    op.create_index(
        "ix_evaluation_job_attempts_job",
        "evaluation_job_attempts",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_job_attempts_job", table_name="evaluation_job_attempts")
    op.drop_table("evaluation_job_attempts")
    op.drop_index("ix_evaluation_jobs_project_trace", table_name="evaluation_jobs")
    op.drop_index("ix_evaluation_jobs_project_created", table_name="evaluation_jobs")
    op.drop_index("ix_evaluation_jobs_dispatch", table_name="evaluation_jobs")
    op.drop_table("evaluation_jobs")
