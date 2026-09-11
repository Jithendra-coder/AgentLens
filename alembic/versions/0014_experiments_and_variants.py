"""Migration 0014: Prompt and model experimentation, variants, and evaluation metrics ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. experiments
    op.create_table(
        "experiments",
        sa.Column("experiment_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column(
            "experiment_type",
            sa.String(length=32),
            nullable=False,
            server_default="ab_test",
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("concluded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_experiments_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_experiments_project", "experiments", ["project_id"])

    # 2. experiment_variants
    op.create_table(
        "experiment_variants",
        sa.Column("variant_id", uuid_type, primary_key=True),
        sa.Column("experiment_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("provider_type", sa.String(length=32), nullable=False, server_default="openai"),
        sa.Column("traffic_weight", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("is_control", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.experiment_id"],
            name="fk_experiment_variants_experiment_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_experiment_variants_experiment", "experiment_variants", ["experiment_id"])

    # 3. experiment_evaluations
    op.create_table(
        "experiment_evaluations",
        sa.Column("eval_id", uuid_type, primary_key=True),
        sa.Column("experiment_id", uuid_type, nullable=False),
        sa.Column("variant_id", uuid_type, nullable=False),
        sa.Column("trace_id", uuid_type, nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("evaluated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.experiment_id"],
            name="fk_experiment_evaluations_experiment_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["experiment_variants.variant_id"],
            name="fk_experiment_evaluations_variant_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_experiment_evaluations_experiment_variant",
        "experiment_evaluations",
        ["experiment_id", "variant_id"],
    )


def downgrade() -> None:
    op.drop_table("experiment_evaluations")
    op.drop_table("experiment_variants")
    op.drop_table("experiments")
