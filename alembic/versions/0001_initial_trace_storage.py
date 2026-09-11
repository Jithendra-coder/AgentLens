"""Create durable canonical trace storage tables."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0001_initial_trace_storage"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attributes", JSONB, nullable=False),
        sa.Column("span_count", sa.Integer(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "trace_id"),
    )
    op.create_table(
        "spans",
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("span_id", UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("parent_span_id", UUID(as_uuid=True), nullable=True),
        sa.Column("span_type", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("input", JSONB, nullable=True),
        sa.Column("output", JSONB, nullable=True),
        sa.Column("attributes", JSONB, nullable=False),
        sa.Column("usage", JSONB, nullable=True),
        sa.Column("error", JSONB, nullable=True),
        sa.PrimaryKeyConstraint("project_id", "trace_id", "span_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "trace_id"],
            ["traces.project_id", "traces.trace_id"],
            name="fk_spans_trace",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "events",
        sa.Column("project_id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("span_id", UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attributes", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("project_id", "trace_id", "event_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "trace_id"],
            ["traces.project_id", "traces.trace_id"],
            name="fk_events_trace",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "trace_id", "span_id"],
            ["spans.project_id", "spans.trace_id", "spans.span_id"],
            name="fk_events_span",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_traces_project_started", "traces", ["project_id", "started_at"])
    op.create_index("ix_traces_project_status", "traces", ["project_id", "status"])
    op.create_index("ix_traces_project_session", "traces", ["project_id", "session_id"])
    op.create_index("ix_traces_project_name", "traces", ["project_id", "name"])
    op.create_index("ix_spans_trace", "spans", ["project_id", "trace_id"])
    op.create_index("ix_spans_parent", "spans", ["parent_span_id"])
    op.create_index("ix_spans_type", "spans", ["span_type"])


def downgrade() -> None:
    op.drop_index("ix_spans_type", table_name="spans")
    op.drop_index("ix_spans_parent", table_name="spans")
    op.drop_index("ix_spans_trace", table_name="spans")
    op.drop_index("ix_traces_project_name", table_name="traces")
    op.drop_index("ix_traces_project_session", table_name="traces")
    op.drop_index("ix_traces_project_status", table_name="traces")
    op.drop_index("ix_traces_project_started", table_name="traces")
    op.drop_table("events")
    op.drop_table("spans")
    op.drop_table("traces")
