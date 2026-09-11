"""Stable value types for the asynchronous evaluation runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

JOB_SCHEMA_VERSION = "agentlens-evaluation-job-v1"


class JobState(StrEnum):
    """Persisted job states and their operational meaning."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class AttemptOutcome(StrEnum):
    """Safe, bounded outcomes recorded for one execution attempt."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRY_WAIT = "retry_wait"
    DEAD_LETTER = "dead_letter"
    LEASE_EXPIRED = "lease_expired"


@dataclass(frozen=True, slots=True)
class EvaluationJob:
    job_id: UUID
    job_schema_version: str
    project_id: str
    trace_id: UUID
    evaluation_type: str
    config: Mapping[str, object]
    state: JobState
    priority: int
    created_at: datetime
    updated_at: datetime
    available_at: datetime
    attempt_count: int
    max_attempts: int
    timeout_seconds: float
    claimed_by: str | None
    claim_token: UUID | None
    lease_expires_at: datetime | None
    last_error_code: str | None


@dataclass(frozen=True, slots=True)
class EvaluationAttempt:
    attempt_id: UUID
    job_id: UUID
    attempt_number: int
    worker_id: str
    started_at: datetime
    finished_at: datetime | None
    outcome: AttemptOutcome
    error_code: str | None
    safe_error_message: str | None
    duration_seconds: float | None


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job: EvaluationJob
    attempt_number: int
    claim_token: UUID


@dataclass(frozen=True, slots=True)
class JobCreation:
    job: EvaluationJob
    duplicate: bool


@dataclass(frozen=True, slots=True)
class JobFailure:
    state: JobState
    retry_at: datetime | None
