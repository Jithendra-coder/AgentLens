"""Migration 0013: Cost intelligence, pricing tables, and budget management ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. model_pricing_tables
    op.create_table(
        "model_pricing_tables",
        sa.Column("pricing_id", uuid_type, primary_key=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_pattern", sa.String(length=128), nullable=False),
        sa.Column("input_cost_per_1k", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("output_cost_per_1k", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_model_pricing_provider_pattern",
        "model_pricing_tables",
        ["provider", "model_pattern"],
    )

    # 2. cost_budgets
    op.create_table(
        "cost_budgets",
        sa.Column("budget_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("period", sa.String(length=32), nullable=False, server_default="monthly"),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("alert_threshold_pct", sa.Float(), nullable=False, server_default="80.0"),
        sa.Column("notification_webhook_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_cost_budgets_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_cost_budgets_project", "cost_budgets", ["project_id"])

    # 3. span_costs
    op.create_table(
        "span_costs",
        sa.Column("span_id", uuid_type, primary_key=True),
        sa.Column("trace_id", uuid_type, nullable=False),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default="unknown"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("calculated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_span_costs_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_span_costs_project", "span_costs", ["project_id"])
    op.create_index("ix_span_costs_trace", "span_costs", ["trace_id"])


def downgrade() -> None:
    op.drop_table("span_costs")
    op.drop_table("cost_budgets")
    op.drop_table("model_pricing_tables")
