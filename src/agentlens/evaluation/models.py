"""SQLAlchemy Core tables for the versioned job ledger and evaluation results."""

from __future__ import annotations

from sqlalchemy import (
    TIMESTAMP,
    Column,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)

from agentlens.storage.models import json_type, metadata, uuid_type

evaluation_jobs = Table(
    "evaluation_jobs",
    metadata,
    Column("job_id", uuid_type, primary_key=True, nullable=False),
    Column("job_schema_version", String(64), nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("trace_id", uuid_type, nullable=False),
    Column("evaluation_type", String(255), nullable=False),
    Column("config", json_type, nullable=False),
    Column("state", String(32), nullable=False),
    Column("priority", Integer, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    Column("available_at", TIMESTAMP(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("timeout_seconds", Float, nullable=False),
    Column("claimed_by", String(255), nullable=True),
    Column("claim_token", uuid_type, nullable=True),
    Column("lease_expires_at", TIMESTAMP(timezone=True), nullable=True),
    Column("last_error_code", String(128), nullable=True),
    Column("last_error_message", String(1024), nullable=True),
    Column("idempotency_key_hash", String(64), nullable=True),
    Column("request_fingerprint", String(64), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "trace_id"],
        ["traces.project_id", "traces.trace_id"],
        name="fk_evaluation_jobs_trace",
        ondelete="CASCADE",
    ),
    UniqueConstraint(
        "project_id",
        "idempotency_key_hash",
        name="uq_evaluation_jobs_project_idempotency",
    ),
)
Index(
    "ix_evaluation_jobs_dispatch",
    evaluation_jobs.c.state,
    evaluation_jobs.c.available_at,
    evaluation_jobs.c.priority,
    evaluation_jobs.c.created_at,
)
Index(
    "ix_evaluation_jobs_project_created",
    evaluation_jobs.c.project_id,
    evaluation_jobs.c.created_at,
)
Index("ix_evaluation_jobs_project_trace", evaluation_jobs.c.project_id, evaluation_jobs.c.trace_id)

evaluation_job_attempts = Table(
    "evaluation_job_attempts",
    metadata,
    Column("attempt_id", uuid_type, primary_key=True, nullable=False),
    Column("job_id", uuid_type, nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("worker_id", String(255), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
    Column("outcome", String(32), nullable=False),
    Column("error_code", String(128), nullable=True),
    Column("safe_error_message", String(1024), nullable=True),
    Column("duration_seconds", Float, nullable=True),
    ForeignKeyConstraint(
        ["job_id"],
        ["evaluation_jobs.job_id"],
        name="fk_evaluation_job_attempts_job",
        ondelete="CASCADE",
    ),
    UniqueConstraint("job_id", "attempt_number", name="uq_evaluation_attempt_number"),
)
Index("ix_evaluation_job_attempts_job", evaluation_job_attempts.c.job_id)

evaluation_results = Table(
    "evaluation_results",
    metadata,
    Column("result_id", uuid_type, primary_key=True, nullable=False),
    Column("result_schema_version", String(64), nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("trace_id", uuid_type, nullable=False),
    Column("job_id", uuid_type, nullable=False),
    Column("evaluation_type", String(255), nullable=False),
    Column("evaluator_name", String(255), nullable=False),
    Column("evaluator_version", String(64), nullable=False),
    Column("evaluation_mode", String(32), nullable=False),
    Column("result_status", String(32), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("config", json_type, nullable=False),
    Column("config_fingerprint", String(64), nullable=False),
    Column("trace_fingerprint", String(64), nullable=False),
    Column("metrics", json_type, nullable=False),
    Column("findings", json_type, nullable=False),
    Column("evidence", json_type, nullable=False),
    ForeignKeyConstraint(
        ["project_id", "trace_id"],
        ["traces.project_id", "traces.trace_id"],
        name="fk_evaluation_results_trace",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["job_id"],
        ["evaluation_jobs.job_id"],
        name="fk_evaluation_results_job",
        ondelete="CASCADE",
    ),
    UniqueConstraint("job_id", name="uq_evaluation_results_job"),
)
Index(
    "ix_evaluation_results_project_created",
    evaluation_results.c.project_id,
    evaluation_results.c.created_at,
)
Index(
    "ix_evaluation_results_project_trace",
    evaluation_results.c.project_id,
    evaluation_results.c.trace_id,
)

evaluation_judge_invocations = Table(
    "evaluation_judge_invocations",
    metadata,
    Column("invocation_id", uuid_type, primary_key=True, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("result_id", uuid_type, nullable=False),
    Column("job_id", uuid_type, nullable=False),
    Column("judge_profile", String(255), nullable=False),
    Column("provider", String(255), nullable=False),
    Column("model", String(255), nullable=False),
    Column("adapter_version", String(64), nullable=False),
    Column("prompt_version", String(128), nullable=False),
    Column("parameters", json_type, nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("response_fingerprint", String(64), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("ended_at", TIMESTAMP(timezone=True), nullable=False),
    Column("status", String(32), nullable=False),
    Column("token_usage", json_type, nullable=True),
    ForeignKeyConstraint(
        ["result_id"],
        ["evaluation_results.result_id"],
        name="fk_evaluation_judge_invocations_result",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["job_id"],
        ["evaluation_jobs.job_id"],
        name="fk_evaluation_judge_invocations_job",
        ondelete="CASCADE",
    ),
)
Index(
    "ix_evaluation_judge_invocations_project_result",
    evaluation_judge_invocations.c.project_id,
    evaluation_judge_invocations.c.result_id,
)
Index("ix_evaluation_judge_invocations_job", evaluation_judge_invocations.c.job_id)
