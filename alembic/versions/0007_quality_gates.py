"""Add M11 immutable quality-gate policies and decisions."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_quality_gates"
down_revision = "0006_regression_engine"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
STAMP = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_regression_policies_project_policy",
        "regression_policies",
        ["project_id", "policy_id"],
    )
    op.create_unique_constraint(
        "uq_regression_runs_project_run",
        "regression_runs",
        ["project_id", "regression_run_id"],
    )
    op.create_table(
        "quality_gate_policies",
        sa.Column("gate_policy_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("rules", JSONB, nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.PrimaryKeyConstraint("gate_policy_id"),
        sa.UniqueConstraint(
            "project_id", "name", "version", name="uq_quality_gate_policies_version"
        ),
        sa.UniqueConstraint(
            "project_id", "gate_policy_id", name="uq_quality_gate_policies_project_id"
        ),
    )
    op.create_table(
        "quality_gate_decisions",
        sa.Column("gate_decision_id", UUID, nullable=False),
        sa.Column("project_id", sa.String(255), nullable=False),
        sa.Column("regression_run_id", UUID, nullable=False),
        sa.Column("gate_policy_id", UUID, nullable=False),
        sa.Column("gate_policy_version", sa.Integer, nullable=False),
        sa.Column("gate_policy_fingerprint", sa.String(64), nullable=False),
        sa.Column("decision_schema_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", STAMP, nullable=False),
        sa.Column("completed_at", STAMP, nullable=False),
        sa.Column("blocking_failure_count", sa.Integer, nullable=False),
        sa.Column("advisory_failure_count", sa.Integer, nullable=False),
        sa.Column("indeterminate_count", sa.Integer, nullable=False),
        sa.Column("rule_results", JSONB, nullable=False),
        sa.Column("dataset_id", UUID, nullable=False),
        sa.Column("dataset_version_id", UUID, nullable=False),
        sa.Column("dataset_checksum", sa.String(64), nullable=False),
        sa.Column("baseline_replay_run_id", UUID, nullable=False),
        sa.Column("candidate_replay_run_id", UUID, nullable=False),
        sa.Column("regression_report_schema", sa.String(64), nullable=False),
        sa.Column("regression_report_fingerprint", sa.String(64), nullable=False),
        sa.Column("comparison_engine_version", sa.String(64), nullable=False),
        sa.Column("quality_gate_engine_version", sa.String(64), nullable=False),
        sa.Column("evaluation_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id", "regression_run_id"],
            ["regression_runs.project_id", "regression_runs.regression_run_id"],
            name="fk_quality_gate_decisions_project_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "gate_policy_id"],
            ["quality_gate_policies.project_id", "quality_gate_policies.gate_policy_id"],
            name="fk_quality_gate_decisions_project_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
            name="fk_quality_gate_decisions_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.dataset_version_id"],
            name="fk_quality_gate_decisions_dataset_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("gate_decision_id"),
        sa.UniqueConstraint(
            "project_id", "idempotency_key_hash", name="uq_quality_gate_decisions_idempotency"
        ),
    )
    op.create_index(
        "ix_quality_gate_policies_project_created",
        "quality_gate_policies",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_quality_gate_decisions_project_created",
        "quality_gate_decisions",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_quality_gate_decisions_project_status",
        "quality_gate_decisions",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_quality_gate_decisions_project_policy",
        "quality_gate_decisions",
        ["project_id", "gate_policy_id"],
    )
    op.create_index(
        "ix_quality_gate_decisions_project_run",
        "quality_gate_decisions",
        ["project_id", "regression_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_quality_gate_decisions_project_run", table_name="quality_gate_decisions")
    op.drop_index("ix_quality_gate_decisions_project_policy", table_name="quality_gate_decisions")
    op.drop_index("ix_quality_gate_decisions_project_status", table_name="quality_gate_decisions")
    op.drop_index("ix_quality_gate_decisions_project_created", table_name="quality_gate_decisions")
    op.drop_index("ix_quality_gate_policies_project_created", table_name="quality_gate_policies")
    op.drop_table("quality_gate_decisions")
    op.drop_table("quality_gate_policies")
    op.drop_constraint("uq_regression_runs_project_run", "regression_runs", type_="unique")
    op.drop_constraint(
        "uq_regression_policies_project_policy", "regression_policies", type_="unique"
    )
