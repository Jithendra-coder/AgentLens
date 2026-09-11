"""Migration 0015: Adaptive quality and cost-aware model routing rules and decision logs ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    # 1. routing_rules
    op.create_table(
        "routing_rules",
        sa.Column("rule_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("min_quality_score", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("max_cost_per_1k", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("max_latency_ms", sa.Float(), nullable=False, server_default="2000.0"),
        sa.Column("fallback_model", sa.String(length=128), nullable=False, server_default="gpt-4o"),
        sa.Column("tier_priority", json_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_routing_rules_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_routing_rules_project", "routing_rules", ["project_id"])

    # 2. routing_decisions
    op.create_table(
        "routing_decisions",
        sa.Column("decision_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", uuid_type, nullable=True),
        sa.Column("rule_id", uuid_type, nullable=True),
        sa.Column("selected_model", sa.String(length=128), nullable=False),
        sa.Column("selected_provider", sa.String(length=64), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("reason", sa.String(length=1024), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_routing_decisions_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["routing_rules.rule_id"],
            name="fk_routing_decisions_rule_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_routing_decisions_project", "routing_decisions", ["project_id"])


def downgrade() -> None:
    op.drop_table("routing_decisions")
    op.drop_table("routing_rules")
