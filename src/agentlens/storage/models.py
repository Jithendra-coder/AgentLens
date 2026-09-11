"""Private SQLAlchemy Core table definitions  persistence."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    Boolean,
    Column,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()
json_type = JSONB().with_variant(JSON(), "sqlite")
uuid_type = UUID(as_uuid=True)

traces = Table(
    "traces",
    metadata,
    Column("project_id", String(255), primary_key=True),
    Column("trace_id", uuid_type, primary_key=True),
    Column("session_id", String(255), nullable=True),
    Column("name", String(1024), nullable=False),
    Column("schema_version", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("ended_at", TIMESTAMP(timezone=True), nullable=True),
    Column("fingerprint", String(64), nullable=False),
    Column("ingested_at", TIMESTAMP(timezone=True), nullable=False),
    Column("attributes", json_type, nullable=False),
    Column("span_count", Integer, nullable=False),
    Column("event_count", Integer, nullable=False),
)

spans = Table(
    "spans",
    metadata,
    Column("project_id", String(255), nullable=False),
    Column("trace_id", uuid_type, nullable=False),
    Column("span_id", uuid_type, nullable=False),
    Column("position", Integer, nullable=False),
    Column("parent_span_id", uuid_type, nullable=True),
    Column("span_type", String(255), nullable=False),
    Column("name", String(1024), nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("ended_at", TIMESTAMP(timezone=True), nullable=True),
    Column("input", json_type, nullable=True),
    Column("output", json_type, nullable=True),
    Column("attributes", json_type, nullable=False),
    Column("usage", json_type, nullable=True),
    Column("error", json_type, nullable=True),
    ForeignKeyConstraint(
        ["project_id", "trace_id"],
        ["traces.project_id", "traces.trace_id"],
        name="fk_spans_trace",
        ondelete="CASCADE",
    ),
)

events = Table(
    "events",
    metadata,
    Column("project_id", String(255), nullable=False),
    Column("trace_id", uuid_type, nullable=False),
    Column("event_id", uuid_type, nullable=False),
    Column("position", Integer, nullable=False),
    Column("span_id", uuid_type, nullable=True),
    Column("name", String(1024), nullable=False),
    Column("timestamp", TIMESTAMP(timezone=True), nullable=False),
    Column("attributes", json_type, nullable=False),
    ForeignKeyConstraint(
        ["project_id", "trace_id"],
        ["traces.project_id", "traces.trace_id"],
        name="fk_events_trace",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "trace_id", "span_id"],
        ["spans.project_id", "spans.trace_id", "spans.span_id"],
        name="fk_events_span",
        ondelete="CASCADE",
    ),
)

Index("ix_traces_project_started", traces.c.project_id, traces.c.started_at)
Index("ix_traces_project_status", traces.c.project_id, traces.c.status)
Index("ix_traces_project_session", traces.c.project_id, traces.c.session_id)
Index("ix_traces_project_name", traces.c.project_id, traces.c.name)
Index("ix_spans_trace", spans.c.project_id, spans.c.trace_id)
Index("ix_spans_parent", spans.c.parent_span_id)
Index("ix_spans_type", spans.c.span_type)

# M9 dataset/replay tables deliberately keep identity, ownership, state, ordering,
# and checksums relational while leaving case/manifest/output shape in JSONB.
datasets = Table(
    "datasets",
    metadata,
    Column("dataset_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", String(2000), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
)

dataset_versions = Table(
    "dataset_versions",
    metadata,
    Column("dataset_version_id", uuid_type, primary_key=True),
    Column("dataset_id", uuid_type, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("version_number", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("source_metadata", json_type, nullable=False),
    Column("case_count", Integer, nullable=False),
    Column("content_checksum", String(64), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("finalized_at", TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["dataset_id"],
        ["datasets.dataset_id"],
        name="fk_dataset_versions_dataset",
        ondelete="CASCADE",
    ),
    UniqueConstraint("dataset_id", "version_number", name="uq_dataset_versions_number"),
)

dataset_cases = Table(
    "dataset_cases",
    metadata,
    Column("case_id", uuid_type, primary_key=True),
    Column("dataset_version_id", uuid_type, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("position", Integer, nullable=False),
    Column("name", String(255), nullable=False),
    Column("input", json_type, nullable=False),
    Column("metadata", json_type, nullable=False),
    Column("source", json_type, nullable=False),
    Column("ground_truth", json_type, nullable=True),
    Column("tags", json_type, nullable=False),
    ForeignKeyConstraint(
        ["dataset_version_id"],
        ["dataset_versions.dataset_version_id"],
        name="fk_dataset_cases_version",
        ondelete="CASCADE",
    ),
    UniqueConstraint("dataset_version_id", "position", name="uq_dataset_cases_position"),
)

replay_runs = Table(
    "replay_runs",
    metadata,
    Column("replay_run_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("dataset_id", uuid_type, nullable=False),
    Column("dataset_version_id", uuid_type, nullable=False),
    Column("dataset_checksum", String(64), nullable=False),
    Column("target_profile_id", String(255), nullable=False),
    Column("target_name", String(255), nullable=False),
    Column("target_type", String(255), nullable=False),
    Column("target_version", String(128), nullable=False),
    Column("replay_mode", String(32), nullable=False),
    Column("reproducibility_status", String(32), nullable=False),
    Column("status", String(32), nullable=False),
    Column("manifest", json_type, nullable=False),
    Column("max_concurrency", Integer, nullable=False),
    Column("timeout_seconds", Float, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("case_count", Integer, nullable=False),
    Column("completed_count", Integer, nullable=False),
    Column("succeeded_count", Integer, nullable=False),
    Column("failed_count", Integer, nullable=False),
    Column("idempotency_key_hash", String(64), nullable=True),
    Column("request_fingerprint", String(64), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=True),
    Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["dataset_id"], ["datasets.dataset_id"], name="fk_replay_runs_dataset", ondelete="RESTRICT"
    ),
    ForeignKeyConstraint(
        ["dataset_version_id"],
        ["dataset_versions.dataset_version_id"],
        name="fk_replay_runs_version",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "project_id", "idempotency_key_hash", name="uq_replay_runs_project_idempotency"
    ),
)

replay_case_executions = Table(
    "replay_case_executions",
    metadata,
    Column("execution_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("replay_run_id", uuid_type, nullable=False),
    Column("case_id", uuid_type, nullable=False),
    Column("position", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("available_at", TIMESTAMP(timezone=True), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=True),
    Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
    Column("attempt_count", Integer, nullable=False),
    Column("claimed_by", String(255), nullable=True),
    Column("claim_token", uuid_type, nullable=True),
    Column("lease_expires_at", TIMESTAMP(timezone=True), nullable=True),
    Column("target_request_fingerprint", String(64), nullable=True),
    Column("target_response_fingerprint", String(64), nullable=True),
    Column("output", json_type, nullable=True),
    Column("safe_error", json_type, nullable=True),
    Column("generated_trace_id", uuid_type, nullable=True),
    ForeignKeyConstraint(
        ["replay_run_id"],
        ["replay_runs.replay_run_id"],
        name="fk_replay_executions_run",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["case_id"],
        ["dataset_cases.case_id"],
        name="fk_replay_executions_case",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["project_id", "generated_trace_id"],
        ["traces.project_id", "traces.trace_id"],
        name="fk_replay_executions_trace",
        ondelete="SET NULL",
    ),
    UniqueConstraint("replay_run_id", "case_id", name="uq_replay_executions_case"),
)

replay_attempts = Table(
    "replay_attempts",
    metadata,
    Column("attempt_id", uuid_type, primary_key=True),
    Column("execution_id", uuid_type, nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
    Column("outcome", String(32), nullable=False),
    Column("error_code", String(128), nullable=True),
    Column("safe_error_message", String(500), nullable=True),
    Column("duration_seconds", Float, nullable=True),
    ForeignKeyConstraint(
        ["execution_id"],
        ["replay_case_executions.execution_id"],
        name="fk_replay_attempts_execution",
        ondelete="CASCADE",
    ),
    UniqueConstraint("execution_id", "attempt_number", name="uq_replay_attempts_number"),
)

Index("ix_datasets_project_updated", datasets.c.project_id, datasets.c.updated_at)
Index("ix_dataset_versions_project", dataset_versions.c.project_id, dataset_versions.c.created_at)
Index("ix_dataset_cases_version", dataset_cases.c.dataset_version_id, dataset_cases.c.position)
Index("ix_replay_runs_project_created", replay_runs.c.project_id, replay_runs.c.created_at)
Index("ix_replay_runs_project_status", replay_runs.c.project_id, replay_runs.c.status)
Index(
    "ix_replay_executions_run_status",
    replay_case_executions.c.replay_run_id,
    replay_case_executions.c.status,
)
Index(
    "ix_replay_executions_available",
    replay_case_executions.c.status,
    replay_case_executions.c.available_at,
)

# M10 keeps policies, report identity, and high-value comparison fields
# relational. Detailed rule/provenance/findings payloads remain JSONB.
regression_policies = Table(
    "regression_policies",
    metadata,
    Column("policy_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", String(2000), nullable=False),
    Column("schema_version", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("rules", json_type, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    UniqueConstraint("project_id", "name", "version", name="uq_regression_policies_version"),
)

regression_runs = Table(
    "regression_runs",
    metadata,
    Column("regression_run_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("report_schema_version", String(64), nullable=False),
    Column("baseline_replay_run_id", uuid_type, nullable=False),
    Column("candidate_replay_run_id", uuid_type, nullable=False),
    Column("dataset_id", uuid_type, nullable=False),
    Column("dataset_version_id", uuid_type, nullable=False),
    Column("dataset_checksum", String(64), nullable=False),
    Column("policy_id", uuid_type, nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("evaluation_plan", json_type, nullable=False),
    Column("baseline_manifest", json_type, nullable=False),
    Column("candidate_manifest", json_type, nullable=False),
    Column("changed_dimensions", json_type, nullable=False),
    Column("status", String(40), nullable=False),
    Column("comparison_engine_version", String(64), nullable=False),
    Column("regression_count", Integer, nullable=False),
    Column("improvement_count", Integer, nullable=False),
    Column("unchanged_count", Integer, nullable=False),
    Column("insufficient_data_count", Integer, nullable=False),
    Column("incompatible_count", Integer, nullable=False),
    Column("has_regressions", Integer, nullable=False),
    Column("available_at", TIMESTAMP(timezone=True), nullable=False),
    Column("claimed_by", String(255), nullable=True),
    Column("claim_token", uuid_type, nullable=True),
    Column("lease_expires_at", TIMESTAMP(timezone=True), nullable=True),
    Column("idempotency_key_hash", String(64), nullable=True),
    Column("request_fingerprint", String(64), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=True),
    Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["baseline_replay_run_id"],
        ["replay_runs.replay_run_id"],
        name="fk_regression_runs_baseline",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["candidate_replay_run_id"],
        ["replay_runs.replay_run_id"],
        name="fk_regression_runs_candidate",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["dataset_id"],
        ["datasets.dataset_id"],
        name="fk_regression_runs_dataset",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["dataset_version_id"],
        ["dataset_versions.dataset_version_id"],
        name="fk_regression_runs_version",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["policy_id"],
        ["regression_policies.policy_id"],
        name="fk_regression_runs_policy",
        ondelete="RESTRICT",
    ),
    UniqueConstraint("project_id", "idempotency_key_hash", name="uq_regression_runs_idempotency"),
)

regression_metric_comparisons = Table(
    "regression_metric_comparisons",
    metadata,
    Column("comparison_id", uuid_type, primary_key=True),
    Column("regression_run_id", uuid_type, nullable=False),
    Column("metric_id", String(255), nullable=False),
    Column("rule_id", String(128), nullable=False),
    Column("baseline_value", Float, nullable=True),
    Column("candidate_value", Float, nullable=True),
    Column("absolute_delta", Float, nullable=True),
    Column("relative_delta", Float, nullable=True),
    Column("direction", String(40), nullable=True),
    Column("baseline_samples", Integer, nullable=False),
    Column("candidate_samples", Integer, nullable=False),
    Column("paired_samples", Integer, nullable=False),
    Column("classification", String(40), nullable=False),
    Column("candidate_limit_status", String(40), nullable=False),
    Column("provenance", json_type, nullable=False),
    Column("details", json_type, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["regression_run_id"],
        ["regression_runs.regression_run_id"],
        name="fk_regression_metrics_run",
        ondelete="CASCADE",
    ),
    UniqueConstraint(
        "regression_run_id", "metric_id", "rule_id", name="uq_regression_metrics_rule"
    ),
)

regression_case_comparisons = Table(
    "regression_case_comparisons",
    metadata,
    Column("case_comparison_id", uuid_type, primary_key=True),
    Column("regression_run_id", uuid_type, nullable=False),
    Column("case_id", uuid_type, nullable=False),
    Column("position", Integer, nullable=False),
    Column("baseline_execution_id", uuid_type, nullable=True),
    Column("candidate_execution_id", uuid_type, nullable=True),
    Column("baseline_trace_id", uuid_type, nullable=True),
    Column("candidate_trace_id", uuid_type, nullable=True),
    Column("status", String(40), nullable=False),
    Column("metric_comparisons", json_type, nullable=False),
    Column("introduced_findings", json_type, nullable=False),
    Column("resolved_findings", json_type, nullable=False),
    Column("details", json_type, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["regression_run_id"],
        ["regression_runs.regression_run_id"],
        name="fk_regression_cases_run",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["case_id"], ["dataset_cases.case_id"], name="fk_regression_cases_case", ondelete="RESTRICT"
    ),
    UniqueConstraint("regression_run_id", "case_id", name="uq_regression_cases_case"),
)

Index(
    "ix_regression_policies_project_created",
    regression_policies.c.project_id,
    regression_policies.c.created_at,
)
Index(
    "ix_regression_runs_project_created", regression_runs.c.project_id, regression_runs.c.created_at
)
Index("ix_regression_runs_project_status", regression_runs.c.project_id, regression_runs.c.status)
Index("ix_regression_runs_dispatch", regression_runs.c.status, regression_runs.c.available_at)
Index("ix_regression_metrics_run", regression_metric_comparisons.c.regression_run_id)
Index(
    "ix_regression_cases_run_position",
    regression_case_comparisons.c.regression_run_id,
    regression_case_comparisons.c.position,
)

# M11 keeps the release policy and immutable decision summary relational while
# retaining the finite policy/rule-result documents as JSONB.
quality_gate_policies = Table(
    "quality_gate_policies",
    metadata,
    Column("gate_policy_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", String(2000), nullable=False),
    Column("schema_version", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("rules", json_type, nullable=False),
    Column("content_fingerprint", String(64), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    UniqueConstraint("project_id", "name", "version", name="uq_quality_gate_policies_version"),
    UniqueConstraint("project_id", "gate_policy_id", name="uq_quality_gate_policies_project_id"),
)

quality_gate_decisions = Table(
    "quality_gate_decisions",
    metadata,
    Column("gate_decision_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("regression_run_id", uuid_type, nullable=False),
    Column("gate_policy_id", uuid_type, nullable=False),
    Column("gate_policy_version", Integer, nullable=False),
    Column("gate_policy_fingerprint", String(64), nullable=False),
    Column("decision_schema_version", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("completed_at", TIMESTAMP(timezone=True), nullable=False),
    Column("blocking_failure_count", Integer, nullable=False),
    Column("advisory_failure_count", Integer, nullable=False),
    Column("indeterminate_count", Integer, nullable=False),
    Column("rule_results", json_type, nullable=False),
    Column("dataset_id", uuid_type, nullable=False),
    Column("dataset_version_id", uuid_type, nullable=False),
    Column("dataset_checksum", String(64), nullable=False),
    Column("baseline_replay_run_id", uuid_type, nullable=False),
    Column("candidate_replay_run_id", uuid_type, nullable=False),
    Column("regression_report_schema", String(64), nullable=False),
    Column("regression_report_fingerprint", String(64), nullable=False),
    Column("comparison_engine_version", String(64), nullable=False),
    Column("quality_gate_engine_version", String(64), nullable=False),
    Column("evaluation_fingerprint", String(64), nullable=False),
    Column("idempotency_key_hash", String(64), nullable=True),
    Column("request_fingerprint", String(64), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "regression_run_id"],
        ["regression_runs.project_id", "regression_runs.regression_run_id"],
        name="fk_quality_gate_decisions_project_run",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["project_id", "gate_policy_id"],
        ["quality_gate_policies.project_id", "quality_gate_policies.gate_policy_id"],
        name="fk_quality_gate_decisions_project_policy",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["dataset_id"],
        ["datasets.dataset_id"],
        name="fk_quality_gate_decisions_dataset",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        ["dataset_version_id"],
        ["dataset_versions.dataset_version_id"],
        name="fk_quality_gate_decisions_dataset_version",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "project_id", "idempotency_key_hash", name="uq_quality_gate_decisions_idempotency"
    ),
)

Index(
    "ix_quality_gate_policies_project_created",
    quality_gate_policies.c.project_id,
    quality_gate_policies.c.created_at,
)
Index(
    "ix_quality_gate_decisions_project_created",
    quality_gate_decisions.c.project_id,
    quality_gate_decisions.c.created_at,
)
Index(
    "ix_quality_gate_decisions_project_status",
    quality_gate_decisions.c.project_id,
    quality_gate_decisions.c.status,
)
Index(
    "ix_quality_gate_decisions_project_policy",
    quality_gate_decisions.c.project_id,
    quality_gate_decisions.c.gate_policy_id,
)
Index(
    "ix_quality_gate_decisions_project_run",
    quality_gate_decisions.c.project_id,
    quality_gate_decisions.c.regression_run_id,
)

worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("worker_id", String(255), primary_key=True),
    Column("worker_type", String(64), nullable=False),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("last_seen", TIMESTAMP(timezone=True), nullable=False),
    Column("state", String(32), nullable=False),
)

Index("ix_worker_heartbeats_last_seen", worker_heartbeats.c.last_seen)

organizations = Table(
    "organizations",
    metadata,
    Column("org_id", uuid_type, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("slug", String(255), nullable=False, unique=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("status", String(32), nullable=False, default="active"),
)
Index("ix_organizations_slug", organizations.c.slug)

projects = Table(
    "projects",
    metadata,
    Column("project_id", String(255), primary_key=True),
    Column("org_id", uuid_type, nullable=True),
    Column("name", String(255), nullable=False),
    Column("slug", String(255), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("status", String(32), nullable=False, default="active"),
    ForeignKeyConstraint(
        ["org_id"],
        ["organizations.org_id"],
        name="fk_projects_org_id",
        ondelete="SET NULL",
    ),
)
Index("ix_projects_org_id", projects.c.org_id)
Index("ix_projects_slug", projects.c.slug)

project_members = Table(
    "project_members",
    metadata,
    Column("member_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("role", String(64), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_project_members_project_id",
        ondelete="CASCADE",
    ),
    UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
)
Index("ix_project_members_project_id", project_members.c.project_id)
Index("ix_project_members_user_id", project_members.c.user_id)

api_keys = Table(
    "api_keys",
    metadata,
    Column("key_id", String(255), primary_key=True),
    Column("key_hash", String(128), nullable=False, unique=True),
    Column("project_id", String(255), nullable=False),
    Column("org_id", uuid_type, nullable=True),
    Column("name", String(255), nullable=False),
    Column("role", String(64), nullable=False),
    Column("permissions", json_type, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
    Column("revoked_at", TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_api_keys_project_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["org_id"],
        ["organizations.org_id"],
        name="fk_api_keys_org_id",
        ondelete="SET NULL",
    ),
)
Index("ix_api_keys_project_id", api_keys.c.project_id)
Index("ix_api_keys_key_hash", api_keys.c.key_hash)

users = Table(
    "users",
    metadata,
    Column("user_id", uuid_type, primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("name", String(255), nullable=False),
    Column("auth_provider", String(64), nullable=False, default="local"),
    Column("external_id", String(255), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("status", String(32), nullable=False, default="active"),
)
Index("ix_users_email", users.c.email)

user_sessions = Table(
    "user_sessions",
    metadata,
    Column("session_id", uuid_type, primary_key=True),
    Column("user_id", uuid_type, nullable=False),
    Column("refresh_token_hash", String(128), nullable=False),
    Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("revoked_at", TIMESTAMP(timezone=True), nullable=True),
    Column("user_agent", String(512), nullable=True),
    ForeignKeyConstraint(
        ["user_id"],
        ["users.user_id"],
        name="fk_user_sessions_user_id",
        ondelete="CASCADE",
    ),
)
Index("ix_user_sessions_user_id", user_sessions.c.user_id)
Index("ix_user_sessions_refresh_hash", user_sessions.c.refresh_token_hash)

encrypted_secrets = Table(
    "encrypted_secrets",
    metadata,
    Column("secret_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("org_id", uuid_type, nullable=True),
    Column("name", String(255), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("ciphertext", Text(), nullable=False),
    Column("nonce", String(64), nullable=False),
    Column("tag", String(64), nullable=False),
    Column("key_version", Integer(), nullable=False, default=1),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_encrypted_secrets_project_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["org_id"],
        ["organizations.org_id"],
        name="fk_encrypted_secrets_org_id",
        ondelete="SET NULL",
    ),
    UniqueConstraint("project_id", "name", name="uq_encrypted_secrets_project_name"),
)
Index("ix_encrypted_secrets_project_id", encrypted_secrets.c.project_id)

# M18 Composite Evaluation Suites
evaluation_suites = Table(
    "evaluation_suites",
    metadata,
    Column("suite_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", String(1024), nullable=True),
    Column("passing_threshold", Float, nullable=False, default=0.8),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
)
Index("ix_evaluation_suites_project", evaluation_suites.c.project_id)

suite_evaluators = Table(
    "suite_evaluators",
    metadata,
    Column("id", uuid_type, primary_key=True),
    Column("suite_id", uuid_type, nullable=False),
    Column("evaluator_name", String(128), nullable=False),
    Column("evaluator_version", String(32), nullable=False, default="1.0.0"),
    Column("evaluator_type", String(32), nullable=False),
    Column("weight", Float, nullable=False, default=1.0),
    Column("threshold", Float, nullable=False, default=0.8),
    Column("parameters", json_type, nullable=True),
    ForeignKeyConstraint(
        ["suite_id"],
        ["evaluation_suites.suite_id"],
        name="fk_suite_evaluators_suite",
        ondelete="CASCADE",
    ),
)
Index("ix_suite_evaluators_suite_id", suite_evaluators.c.suite_id)

composite_evaluation_results = Table(
    "composite_evaluation_results",
    metadata,
    Column("composite_result_id", uuid_type, primary_key=True),
    Column("suite_id", uuid_type, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("trace_id", uuid_type, nullable=False),
    Column("aggregate_score", Float, nullable=False),
    Column("passed", Boolean, nullable=False),
    Column("metric_scores", json_type, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["suite_id"],
        ["evaluation_suites.suite_id"],
        name="fk_composite_results_suite",
        ondelete="CASCADE",
    ),
)
Index(
    "ix_composite_results_project_suite",
    composite_evaluation_results.c.project_id,
    composite_evaluation_results.c.suite_id,
)
Index("ix_composite_results_trace_id", composite_evaluation_results.c.trace_id)

# Custom Evaluator Plugins
custom_evaluator_plugins = Table(
    "custom_evaluator_plugins",
    metadata,
    Column("plugin_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("version", String(32), nullable=False, default="1.0.0"),
    Column("evaluator_type", String(32), nullable=False, default="deterministic"),
    Column("description", String(1024), nullable=True),
    Column("code_body", Text, nullable=False),
    Column("schema_parameters", json_type, nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_custom_evaluators_project_id",
        ondelete="CASCADE",
    ),
    UniqueConstraint(
        "project_id",
        "name",
        "version",
        name="uq_custom_evaluators_project_name_version",
    ),
)
Index("ix_custom_evaluators_project", custom_evaluator_plugins.c.project_id)

model_pricing_tables = Table(
    "model_pricing_tables",
    metadata,
    Column("pricing_id", uuid_type, primary_key=True),
    Column("provider", String(64), nullable=False),
    Column("model_pattern", String(128), nullable=False),
    Column("input_cost_per_1k", Float, nullable=False, default=0.0),
    Column("output_cost_per_1k", Float, nullable=False, default=0.0),
    Column("effective_from", TIMESTAMP(timezone=True), nullable=False),
)
Index(
    "ix_model_pricing_provider_pattern",
    model_pricing_tables.c.provider,
    model_pricing_tables.c.model_pattern,
)

cost_budgets = Table(
    "cost_budgets",
    metadata,
    Column("budget_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("period", String(32), nullable=False, default="monthly"),
    Column("amount_usd", Float, nullable=False),
    Column("alert_threshold_pct", Float, nullable=False, default=80.0),
    Column("notification_webhook_url", String(512), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_cost_budgets_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_cost_budgets_project", cost_budgets.c.project_id)

span_costs = Table(
    "span_costs",
    metadata,
    Column("span_id", uuid_type, primary_key=True),
    Column("trace_id", uuid_type, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("provider", String(64), nullable=False, default="unknown"),
    Column("model", String(128), nullable=False, default="unknown"),
    Column("input_tokens", Integer, nullable=False, default=0),
    Column("output_tokens", Integer, nullable=False, default=0),
    Column("total_cost_usd", Float, nullable=False, default=0.0),
    Column("calculated_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_span_costs_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_span_costs_project", span_costs.c.project_id)
Index("ix_span_costs_trace", span_costs.c.trace_id)

experiments = Table(
    "experiments",
    metadata,
    Column("experiment_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("description", String(1024), nullable=True),
    Column("experiment_type", String(32), nullable=False, default="ab_test"),
    Column("status", String(32), nullable=False, default="running"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    Column("concluded_at", TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_experiments_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_experiments_project", experiments.c.project_id)

experiment_variants = Table(
    "experiment_variants",
    metadata,
    Column("variant_id", uuid_type, primary_key=True),
    Column("experiment_id", uuid_type, nullable=False),
    Column("name", String(128), nullable=False),
    Column("prompt_template", Text, nullable=False, default=""),
    Column("model_name", String(128), nullable=False, default=""),
    Column("provider_type", String(32), nullable=False, default="openai"),
    Column("traffic_weight", Float, nullable=False, default=0.5),
    Column("is_control", Boolean, nullable=False, default=False),
    ForeignKeyConstraint(
        ["experiment_id"],
        ["experiments.experiment_id"],
        name="fk_experiment_variants_experiment_id",
        ondelete="CASCADE",
    ),
)
Index("ix_experiment_variants_experiment", experiment_variants.c.experiment_id)

experiment_evaluations = Table(
    "experiment_evaluations",
    metadata,
    Column("eval_id", uuid_type, primary_key=True),
    Column("experiment_id", uuid_type, nullable=False),
    Column("variant_id", uuid_type, nullable=False),
    Column("trace_id", uuid_type, nullable=False),
    Column("score", Float, nullable=False, default=0.0),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("latency_ms", Float, nullable=False, default=0.0),
    Column("evaluated_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["experiment_id"],
        ["experiments.experiment_id"],
        name="fk_experiment_evaluations_experiment_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["variant_id"],
        ["experiment_variants.variant_id"],
        name="fk_experiment_evaluations_variant_id",
        ondelete="CASCADE",
    ),
)
Index(
    "ix_experiment_evaluations_experiment_variant",
    experiment_evaluations.c.experiment_id,
    experiment_evaluations.c.variant_id,
)

routing_rules = Table(
    "routing_rules",
    metadata,
    Column("rule_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("task_type", String(32), nullable=False, default="general"),
    Column("min_quality_score", Float, nullable=False, default=0.8),
    Column("max_cost_per_1k", Float, nullable=False, default=0.05),
    Column("max_latency_ms", Float, nullable=False, default=2000.0),
    Column("fallback_model", String(128), nullable=False, default="gpt-4o"),
    Column("tier_priority", json_type, nullable=False),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_routing_rules_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_routing_rules_project", routing_rules.c.project_id)

routing_decisions = Table(
    "routing_decisions",
    metadata,
    Column("decision_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("trace_id", uuid_type, nullable=True),
    Column("rule_id", uuid_type, nullable=True),
    Column("selected_model", String(128), nullable=False),
    Column("selected_provider", String(64), nullable=False),
    Column("estimated_cost_usd", Float, nullable=False, default=0.0),
    Column("reason", String(1024), nullable=False),
    Column("decided_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_routing_decisions_project_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["rule_id"],
        ["routing_rules.rule_id"],
        name="fk_routing_decisions_rule_id",
        ondelete="SET NULL",
    ),
)
Index("ix_routing_decisions_project", routing_decisions.c.project_id)

model_benchmarks = Table(
    "model_benchmarks",
    metadata,
    Column("benchmark_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("description", String(1024), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_model_benchmarks_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_model_benchmarks_project", model_benchmarks.c.project_id)

model_benchmark_runs = Table(
    "model_benchmark_runs",
    metadata,
    Column("run_id", uuid_type, primary_key=True),
    Column("benchmark_id", uuid_type, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("model_name", String(128), nullable=False),
    Column("provider_type", String(64), nullable=False, default="openai"),
    Column("overall_score", Float, nullable=False, default=0.0),
    Column("mean_latency_ms", Float, nullable=False, default=0.0),
    Column("mean_cost_usd", Float, nullable=False, default=0.0),
    Column("pass_rate", Float, nullable=False, default=0.0),
    Column("status", String(32), nullable=False, default="completed"),
    Column("started_at", TIMESTAMP(timezone=True), nullable=False),
    Column("completed_at", TIMESTAMP(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["benchmark_id"],
        ["model_benchmarks.benchmark_id"],
        name="fk_model_benchmark_runs_benchmark_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_model_benchmark_runs_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_model_benchmark_runs_benchmark", model_benchmark_runs.c.benchmark_id)

model_qualifications = Table(
    "model_qualifications",
    metadata,
    Column("qualification_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("model_name", String(128), nullable=False),
    Column("provider_type", String(64), nullable=False, default="openai"),
    Column("is_qualified", Boolean, nullable=False, default=False),
    Column("min_required_score", Float, nullable=False, default=0.8),
    Column("latest_run_id", uuid_type, nullable=True),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_model_qualifications_project_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["latest_run_id"],
        ["model_benchmark_runs.run_id"],
        name="fk_model_qualifications_run_id",
        ondelete="SET NULL",
    ),
)
Index("ix_model_qualifications_project", model_qualifications.c.project_id)

quality_baselines = Table(
    "quality_baselines",
    metadata,
    Column("baseline_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("metric_name", String(64), nullable=False),
    Column("baseline_mean", Float, nullable=False),
    Column("baseline_std", Float, nullable=False, default=0.05),
    Column("window_size", Integer, nullable=False, default=50),
    Column("status", String(32), nullable=False, default="active"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_quality_baselines_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_quality_baselines_project", quality_baselines.c.project_id)

drift_observations = Table(
    "drift_observations",
    metadata,
    Column("drift_id", uuid_type, primary_key=True),
    Column("baseline_id", uuid_type, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("observed_mean", Float, nullable=False),
    Column("z_score", Float, nullable=False),
    Column("drift_magnitude_pct", Float, nullable=False),
    Column("drift_type", String(64), nullable=False),
    Column("is_alert", Boolean, nullable=False, default=False),
    Column("observed_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["baseline_id"],
        ["quality_baselines.baseline_id"],
        name="fk_drift_observations_baseline_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_drift_observations_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_drift_observations_baseline", drift_observations.c.baseline_id)
Index("ix_drift_observations_project", drift_observations.c.project_id)

production_monitors = Table(
    "production_monitors",
    metadata,
    Column("monitor_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("sampling_rate", Float, nullable=False, default=0.10),
    Column("health_status", String(32), nullable=False, default="healthy"),
    Column("health_index", Float, nullable=False, default=100.0),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_production_monitors_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_production_monitors_project", production_monitors.c.project_id)

production_health_snapshots = Table(
    "production_health_snapshots",
    metadata,
    Column("snapshot_id", uuid_type, primary_key=True),
    Column("monitor_id", uuid_type, nullable=False),
    Column("project_id", String(255), nullable=False),
    Column("health_index", Float, nullable=False, default=100.0),
    Column("p95_latency_ms", Float, nullable=False, default=0.0),
    Column("mean_quality_score", Float, nullable=False, default=1.0),
    Column("error_rate", Float, nullable=False, default=0.0),
    Column("total_spans_evaluated", Integer, nullable=False, default=0),
    Column("recorded_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["monitor_id"],
        ["production_monitors.monitor_id"],
        name="fk_production_health_snapshots_monitor_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_production_health_snapshots_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_production_health_snapshots_monitor", production_health_snapshots.c.monitor_id)
Index("ix_production_health_snapshots_project", production_health_snapshots.c.project_id)

alert_rules = Table(
    "alert_rules",
    metadata,
    Column("rule_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("trigger_type", String(64), nullable=False),
    Column("channel_type", String(32), nullable=False),
    Column("destination_url", String(1024), nullable=False),
    Column("is_enabled", Boolean, nullable=False, default=True),
    Column("cooldown_seconds", Integer, nullable=False, default=300),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_alert_rules_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_alert_rules_project", alert_rules.c.project_id)

incident_records = Table(
    "incident_records",
    metadata,
    Column("incident_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("rule_id", uuid_type, nullable=True),
    Column("title", String(255), nullable=False),
    Column("severity", String(16), nullable=False, default="P2"),
    Column("status", String(32), nullable=False, default="open"),
    Column("details", String(4096), nullable=False),
    Column("acknowledged_by", String(255), nullable=True),
    Column("resolved_at", TIMESTAMP(timezone=True), nullable=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_incident_records_project_id",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["rule_id"],
        ["alert_rules.rule_id"],
        name="fk_incident_records_rule_id",
        ondelete="SET NULL",
    ),
)
Index("ix_incident_records_project", incident_records.c.project_id)

rca_reports = Table(
    "rca_reports",
    metadata,
    Column("rca_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("trace_id", uuid_type, nullable=True),
    Column("incident_id", uuid_type, nullable=True),
    Column("failure_category", String(64), nullable=False),
    Column("root_cause_summary", String(1024), nullable=False),
    Column("confidence_score", Float, nullable=False, default=1.0),
    Column("recommended_action", String(2048), nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_rca_reports_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_rca_reports_project", rca_reports.c.project_id)

failure_clusters = Table(
    "failure_clusters",
    metadata,
    Column("cluster_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("failure_pattern", String(512), nullable=False),
    Column("occurrences_count", Integer, nullable=False, default=1),
    Column("first_seen", TIMESTAMP(timezone=True), nullable=False),
    Column("last_seen", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_failure_clusters_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_failure_clusters_project", failure_clusters.c.project_id)

compliance_audit_events = Table(
    "compliance_audit_events",
    metadata,
    Column("event_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("actor_id", String(255), nullable=False),
    Column("action", String(128), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("resource_id", String(255), nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("previous_event_hash", String(64), nullable=False),
    Column("event_hash", String(64), nullable=False),
    Column("timestamp", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_compliance_audit_events_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_compliance_audit_events_project", compliance_audit_events.c.project_id)

retention_policies = Table(
    "retention_policies",
    metadata,
    Column("policy_id", uuid_type, primary_key=True),
    Column("project_id", String(255), nullable=False),
    Column("name", String(128), nullable=False),
    Column("retention_days", Integer, nullable=False, default=90),
    Column("auto_redact_pii", Boolean, nullable=False, default=True),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["project_id"],
        ["projects.project_id"],
        name="fk_retention_policies_project_id",
        ondelete="CASCADE",
    ),
)
Index("ix_retention_policies_project", retention_policies.c.project_id)
