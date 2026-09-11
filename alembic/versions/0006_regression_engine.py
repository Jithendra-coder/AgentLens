"""Add M10 versioned regression policies and comparison reports."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_regression_engine"
down_revision = "0005_dataset_replay"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
STAMP = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "regression_policies",
        sa.Column("policy_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("rules", JSONB, nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.PrimaryKeyConstraint("policy_id"),
        sa.UniqueConstraint("project_id", "name", "version", name="uq_regression_policies_version"),
    )
    op.create_table(
        "regression_runs",
        sa.Column("regression_run_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("report_schema_version", sa.String(64), nullable=False),
        sa.Column("baseline_replay_run_id", UUID, nullable=False),
        sa.Column("candidate_replay_run_id", UUID, nullable=False),
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("dataset_version_id", UUID, nullable=False),
        sa.Column("dataset_checksum", sa.String(64), nullable=False),
        sa.Column("policy_id", UUID, nullable=False),
        sa.Column("policy_version", sa.Integer, nullable=False),
        sa.Column("evaluation_plan", JSONB, nullable=False),
        sa.Column("baseline_manifest", JSONB, nullable=False),
        sa.Column("candidate_manifest", JSONB, nullable=False),
        sa.Column("changed_dimensions", JSONB, nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("comparison_engine_version", sa.String(64), nullable=False),
        sa.Column("regression_count", sa.Integer, nullable=False),
        sa.Column("improvement_count", sa.Integer, nullable=False),
        sa.Column("unchanged_count", sa.Integer, nullable=False),
        sa.Column("insufficient_data_count", sa.Integer, nullable=False),
        sa.Column("incompatible_count", sa.Integer, nullable=False),
        sa.Column("has_regressions", sa.Integer, nullable=False),
        sa.Column("available_at", STAMP, nullable=False),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("claim_token", UUID, nullable=True),
        sa.Column("lease_expires_at", STAMP, nullable=True),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("started_at", STAMP, nullable=True),
        sa.Column("finished_at", STAMP, nullable=True),
        sa.ForeignKeyConstraint(
            ["baseline_replay_run_id"],
            ["replay_runs.replay_run_id"],
            name="fk_regression_runs_baseline",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_replay_run_id"],
            ["replay_runs.replay_run_id"],
            name="fk_regression_runs_candidate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
            name="fk_regression_runs_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.dataset_version_id"],
            name="fk_regression_runs_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["regression_policies.policy_id"],
            name="fk_regression_runs_policy",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("regression_run_id"),
        sa.UniqueConstraint(
            "project_id", "idempotency_key_hash", name="uq_regression_runs_idempotency"
        ),
    )
    op.create_table(
        "regression_metric_comparisons",
        sa.Column("comparison_id", UUID, nullable=False),
        sa.Column("regression_run_id", UUID, nullable=False),
        sa.Column("metric_id", sa.String(255), nullable=False),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("baseline_value", sa.Float, nullable=True),
        sa.Column("candidate_value", sa.Float, nullable=True),
        sa.Column("absolute_delta", sa.Float, nullable=True),
        sa.Column("relative_delta", sa.Float, nullable=True),
        sa.Column("direction", sa.String(40), nullable=True),
        sa.Column("baseline_samples", sa.Integer, nullable=False),
        sa.Column("candidate_samples", sa.Integer, nullable=False),
        sa.Column("paired_samples", sa.Integer, nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("candidate_limit_status", sa.String(40), nullable=False),
        sa.Column("provenance", JSONB, nullable=False),
        sa.Column("details", JSONB, nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.ForeignKeyConstraint(
            ["regression_run_id"],
            ["regression_runs.regression_run_id"],
            name="fk_regression_metrics_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("comparison_id"),
        sa.UniqueConstraint(
            "regression_run_id", "metric_id", "rule_id", name="uq_regression_metrics_rule"
        ),
    )
    op.create_table(
        "regression_case_comparisons",
        sa.Column("case_comparison_id", UUID, nullable=False),
        sa.Column("regression_run_id", UUID, nullable=False),
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("baseline_execution_id", UUID, nullable=True),
        sa.Column("candidate_execution_id", UUID, nullable=True),
        sa.Column("baseline_trace_id", UUID, nullable=True),
        sa.Column("candidate_trace_id", UUID, nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metric_comparisons", JSONB, nullable=False),
        sa.Column("introduced_findings", JSONB, nullable=False),
        sa.Column("resolved_findings", JSONB, nullable=False),
        sa.Column("details", JSONB, nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.ForeignKeyConstraint(
            ["regression_run_id"],
            ["regression_runs.regression_run_id"],
            name="fk_regression_cases_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["dataset_cases.case_id"],
            name="fk_regression_cases_case",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("case_comparison_id"),
        sa.UniqueConstraint("regression_run_id", "case_id", name="uq_regression_cases_case"),
    )
    op.create_index(
        "ix_regression_policies_project_created",
        "regression_policies",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_regression_runs_project_created", "regression_runs", ["project_id", "created_at"]
    )
    op.create_index(
        "ix_regression_runs_project_status", "regression_runs", ["project_id", "status"]
    )
    op.create_index("ix_regression_runs_dispatch", "regression_runs", ["status", "available_at"])
    op.create_index(
        "ix_regression_metrics_run", "regression_metric_comparisons", ["regression_run_id"]
    )
    op.create_index(
        "ix_regression_cases_run_position",
        "regression_case_comparisons",
        ["regression_run_id", "position"],
    )


def downgrade() -> None:
    op.drop_index("ix_regression_cases_run_position", table_name="regression_case_comparisons")
    op.drop_index("ix_regression_metrics_run", table_name="regression_metric_comparisons")
    op.drop_index("ix_regression_runs_dispatch", table_name="regression_runs")
    op.drop_index("ix_regression_runs_project_status", table_name="regression_runs")
    op.drop_index("ix_regression_runs_project_created", table_name="regression_runs")
    op.drop_index("ix_regression_policies_project_created", table_name="regression_policies")
    op.drop_table("regression_case_comparisons")
    op.drop_table("regression_metric_comparisons")
    op.drop_table("regression_runs")
    op.drop_table("regression_policies")
