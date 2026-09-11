"""Migration 0020: Automated root-cause analysis and failure clustering ."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.CHAR(36)

    # 1. rca_reports
    op.create_table(
        "rca_reports",
        sa.Column("rca_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", uuid_type, nullable=True),
        sa.Column("incident_id", uuid_type, nullable=True),
        sa.Column("failure_category", sa.String(length=64), nullable=False),
        sa.Column("root_cause_summary", sa.String(length=1024), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("recommended_action", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_rca_reports_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_rca_reports_project", "rca_reports", ["project_id"])

    # 2. failure_clusters
    op.create_table(
        "failure_clusters",
        sa.Column("cluster_id", uuid_type, primary_key=True),
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("failure_pattern", sa.String(length=512), nullable=False),
        sa.Column("occurrences_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_failure_clusters_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_failure_clusters_project", "failure_clusters", ["project_id"])


def downgrade() -> None:
    op.drop_table("failure_clusters")
    op.drop_table("rca_reports")
