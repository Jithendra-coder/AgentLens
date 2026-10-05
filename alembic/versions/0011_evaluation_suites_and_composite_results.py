"""Add evaluation_suites, suite_evaluators, and composite_evaluation_results tables ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0011"
down_revision = "0010_enterprise_auth_and_secrets"
branch_labels = None
depends_on = None

uuid_type = UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
json_type = JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # 1. Evaluation Suites
    op.create_table(
        "evaluation_suites",
        sa.Column("suite_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("passing_threshold", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("suite_id"),
    )
    op.create_index("ix_evaluation_suites_project", "evaluation_suites", ["project_id"])

    # 2. Suite Evaluators
    op.create_table(
        "suite_evaluators",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("suite_id", uuid_type, nullable=False),
        sa.Column("evaluator_name", sa.String(128), nullable=False),
        sa.Column("evaluator_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("evaluator_type", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("parameters", json_type, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["evaluation_suites.suite_id"],
            name="fk_suite_evaluators_suite",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_suite_evaluators_suite_id", "suite_evaluators", ["suite_id"])

    # 3. Composite Evaluation Results
    op.create_table(
        "composite_evaluation_results",
        sa.Column("composite_result_id", uuid_type, nullable=False),
        sa.Column("suite_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("trace_id", uuid_type, nullable=False),
        sa.Column("aggregate_score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("metric_scores", json_type, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("composite_result_id"),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["evaluation_suites.suite_id"],
            name="fk_composite_results_suite",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_composite_results_project_suite",
        "composite_evaluation_results",
        ["project_id", "suite_id"],
    )
    op.create_index(
        "ix_composite_results_trace_id",
        "composite_evaluation_results",
        ["trace_id"],
    )


def downgrade() -> None:
    op.drop_table("composite_evaluation_results")
    op.drop_table("suite_evaluators")
    op.drop_table("evaluation_suites")
