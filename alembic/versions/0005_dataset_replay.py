"""Add M9 durable datasets and replay execution ledger."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_dataset_replay"
down_revision = "0004_semantic_evaluation"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
STAMP = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("updated_at", STAMP, nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("dataset_version_id", UUID, nullable=False),
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_metadata", JSONB, nullable=False),
        sa.Column("case_count", sa.Integer, nullable=False),
        sa.Column("content_checksum", sa.String(64), nullable=True),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("finalized_at", STAMP, nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
            name="fk_dataset_versions_dataset",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("dataset_version_id"),
        sa.UniqueConstraint("dataset_id", "version_number", name="uq_dataset_versions_number"),
    )
    op.create_table(
        "dataset_cases",
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("dataset_version_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("input", JSONB, nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("source", JSONB, nullable=False),
        sa.Column("ground_truth", JSONB, nullable=True),
        sa.Column("tags", JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.dataset_version_id"],
            name="fk_dataset_cases_version", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("case_id"),
        sa.UniqueConstraint("dataset_version_id", "position", name="uq_dataset_cases_position"),
    )
    op.create_table(
        "replay_runs",
        sa.Column("replay_run_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("dataset_version_id", UUID, nullable=False),
        sa.Column("dataset_checksum", sa.String(64), nullable=False),
        sa.Column("target_profile_id", sa.String(255), nullable=False),
        sa.Column("target_name", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(255), nullable=False),
        sa.Column("target_version", sa.String(128), nullable=False),
        sa.Column("replay_mode", sa.String(32), nullable=False),
        sa.Column("reproducibility_status", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("max_concurrency", sa.Integer, nullable=False),
        sa.Column("timeout_seconds", sa.Float, nullable=False),
        sa.Column("max_attempts", sa.Integer, nullable=False),
        sa.Column("case_count", sa.Integer, nullable=False),
        sa.Column("completed_count", sa.Integer, nullable=False),
        sa.Column("succeeded_count", sa.Integer, nullable=False),
        sa.Column("failed_count", sa.Integer, nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("started_at", STAMP, nullable=True),
        sa.Column("finished_at", STAMP, nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
            name="fk_replay_runs_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.dataset_version_id"],
            name="fk_replay_runs_version", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("replay_run_id"),
        sa.UniqueConstraint(
            "project_id", "idempotency_key_hash", name="uq_replay_runs_project_idempotency"
        ),
    )
    op.create_table(
        "replay_case_executions",
        sa.Column("execution_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("replay_run_id", UUID, nullable=False),
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("available_at", STAMP, nullable=False),
        sa.Column("started_at", STAMP, nullable=True),
        sa.Column("finished_at", STAMP, nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("claim_token", UUID, nullable=True),
        sa.Column("lease_expires_at", STAMP, nullable=True),
        sa.Column("target_request_fingerprint", sa.String(64), nullable=True),
        sa.Column("target_response_fingerprint", sa.String(64), nullable=True),
        sa.Column("output", JSONB, nullable=True),
        sa.Column("safe_error", JSONB, nullable=True),
        sa.Column("generated_trace_id", UUID, nullable=True),
        sa.ForeignKeyConstraint(
            ["replay_run_id"],
            ["replay_runs.replay_run_id"],
            name="fk_replay_executions_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["dataset_cases.case_id"],
            name="fk_replay_executions_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "generated_trace_id"], ["traces.project_id", "traces.trace_id"],
            name="fk_replay_executions_trace", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("execution_id"),
        sa.UniqueConstraint("replay_run_id", "case_id", name="uq_replay_executions_case"),
    )
    op.create_table(
        "replay_attempts",
        sa.Column("attempt_id", UUID, nullable=False),
        sa.Column("execution_id", UUID, nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("started_at", STAMP, nullable=False),
        sa.Column("finished_at", STAMP, nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("safe_error_message", sa.String(500), nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["replay_case_executions.execution_id"],
            name="fk_replay_attempts_execution", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint("execution_id", "attempt_number", name="uq_replay_attempts_number"),
    )
    op.create_index("ix_datasets_project_updated", "datasets", ["project_id", "updated_at"])
    op.create_index("ix_dataset_versions_project", "dataset_versions", ["project_id", "created_at"])
    op.create_index("ix_dataset_cases_version", "dataset_cases", ["dataset_version_id", "position"])
    op.create_index("ix_replay_runs_project_created", "replay_runs", ["project_id", "created_at"])
    op.create_index("ix_replay_runs_project_status", "replay_runs", ["project_id", "status"])
    op.create_index(
        "ix_replay_executions_run_status", "replay_case_executions", ["replay_run_id", "status"]
    )
    op.create_index(
        "ix_replay_executions_available", "replay_case_executions", ["status", "available_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_replay_executions_available", table_name="replay_case_executions")
    op.drop_index("ix_replay_executions_run_status", table_name="replay_case_executions")
    op.drop_index("ix_replay_runs_project_status", table_name="replay_runs")
    op.drop_index("ix_replay_runs_project_created", table_name="replay_runs")
    op.drop_index("ix_dataset_cases_version", table_name="dataset_cases")
    op.drop_index("ix_dataset_versions_project", table_name="dataset_versions")
    op.drop_index("ix_datasets_project_updated", table_name="datasets")
    op.drop_table("replay_attempts")
    op.drop_table("replay_case_executions")
    op.drop_table("replay_runs")
    op.drop_table("dataset_cases")
    op.drop_table("dataset_versions")
    op.drop_table("datasets")
