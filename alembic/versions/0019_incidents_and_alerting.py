"""Migration 0019: Multi-channel alerting rules and incident lifecycle ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. alert_rules
    op.create_table(
        "alert_rules",
        sa.Column("rule_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("trigger_type", sa.String(length=64), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("destination_url", sa.String(length=1024), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_alert_rules_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_alert_rules_project", "alert_rules", ["project_id"])

    # 2. incident_records
    op.create_table(
        "incident_records",
        sa.Column("incident_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("rule_id", uuid_type, nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="P2"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("details", sa.String(length=4096), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_incident_records_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["alert_rules.rule_id"],
            name="fk_incident_records_rule_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_incident_records_project", "incident_records", ["project_id"])


def downgrade() -> None:
    op.drop_table("incident_records")
    op.drop_table("alert_rules")
