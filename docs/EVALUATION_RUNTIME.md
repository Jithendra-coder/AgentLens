# M7 Evaluation Runtime

M7 extends the M5 asynchronous execution boundary downstream of trace
ingestion. M5 remains responsible for durable jobs, Redis wakeups, claims,
leases, retries, and attempts. M6 adds trusted deterministic evaluators and
immutable result persistence; M7 adds bounded semantic evaluators and safe
judge provenance.

## Durable job contract

PostgreSQL is authoritative. Each job uses schema version
`agentlens-evaluation-job-v1` and contains a UUID, project/trace reference,
trusted `evaluation_type`, JSON-safe `config`, state, priority, timestamps,
available time, bounded attempt count, timeout, claim owner/token, lease, and
safe last-error code. The composite `(project_id, trace_id)` foreign key keeps
job creation project-scoped and prevents an evaluation from pointing at a
different tenant's trace.

The state vocabulary is `queued`, `running`, `retry_wait`, `succeeded`,
`failed`, and `dead_letter`. M5 uses `dead_letter` for non-retryable and
exhausted failures; `failed` remains available for a later explicit terminal
failure policy. State changes are performed by the repository, never by API
payloads. `evaluation_job_attempts` records attempt number, worker identity,
timestamps, outcome, bounded error code/message, and duration. It never stores
trace payloads, secrets, arbitrary exception text, or handler code.

## Dispatch and recovery

Job creation commits the PostgreSQL row before attempting Redis dispatch. Redis
uses the versioned list `agentlens:evaluation:v1` and a minimal JSON payload:

```json
{"job_id":"00000000-0000-0000-0000-000000000000"}
```

Redis is a wakeup mechanism, not a second ledger. Duplicate messages are safe;
the worker re-reads the job and claim-fences stale delivery. A recovery scan
re-publishes queued, retry-ready, and expired-running jobs after an outage.
When Redis is down, trace ingestion still works, and a newly created job
remains durably queued with HTTP 202.

## Worker lifecycle

Run the reference worker with:

```text
AGENTLENS_DATABASE_URL=... AGENTLENS_REDIS_URL=... python -m agentlens.worker
```

Workers have a UUID identity and label, claim with PostgreSQL
`FOR UPDATE SKIP LOCKED`, create an attempt row, and receive a finite lease.
The worker renews the lease while executing and handles SIGINT/SIGTERM
gracefully. If a worker crashes, an expired lease can be claimed by another
worker; the open attempt is marked `lease_expired`. Completion requires the
current claim token, so stale workers cannot mark a recovered job successful.

Timeouts are cooperative at the Python thread boundary. A timed-out handler
is fenced from committing, but Python cannot safely hard-kill an arbitrary
running thread. M5 documents this honestly and keeps the reference no-op
handler bounded.

## Handlers, retry, and idempotency

The registry is explicit and contains `noop`, M6 deterministic handlers, and
M7 reviewed RAG/tool/agent handlers. The runtime does
not import a module from a job, execute a string, deserialize a callable,
invoke a subprocess, or accept provider credentials. Unknown handlers are
terminal dead-letter failures. Invalid evaluator configuration is terminal;
semantic timeouts, rate limits, and provider unavailability use durable
exponential backoff and a bounded default of three attempts; exhausted jobs
become `dead_letter`. Malformed structured judge responses are terminal
evaluator failures. A missing semantic judge does not affect deterministic
handlers or trace ingestion.

`Idempotency-Key` is optional. When provided, PostgreSQL stores only a SHA-256
key hash and request fingerprint per project. Repeating the same request
returns the same job; reusing the key with different content returns 409. If
the header is omitted, every accepted request creates a distinct job.

## HTTP API

- `POST /v1/traces/{trace_id}/evaluations` accepts the M6 types plus
  `rag_context_relevance`, `rag_groundedness`, `rag_citation_integrity`,
  `tool_selection`, `tool_arguments`, `tool_efficiency`, `agent_task_success`,
  and `agent_criteria`, and rejects unsupported production types before
  creating a job.
- `GET /v1/evaluation-jobs/{job_id}` returns safe operational state only.
  It includes `result_id` when a result exists; project mismatch is
  intentionally reported as 404.
- `GET /v1/evaluation-results/{result_id}` returns one project-scoped
  immutable result.
- `GET /v1/traces/{trace_id}/evaluation-results` returns bounded project-scoped
  result summaries.
- `/health/live` remains DB-independent. With M6 enabled,
  `/health/ready` returns `ok` when PostgreSQL and Redis are healthy,
  `degraded` with HTTP 200 when PostgreSQL is healthy but Redis is down, and
  `unavailable` with HTTP 503 when PostgreSQL is down. Trace ingestion remains
  usable in the degraded state.

## M7 result transaction

For result-bearing handlers, one PostgreSQL transaction locks the current job
claim, inserts the immutable `evaluation_results` row and any safe
`evaluation_judge_invocations`, completes the current attempt, marks the job
`succeeded`, and clears the lease/token. The result row has a unique `job_id`.
A stale worker raises `StaleClaimError` and none of those writes commit.
Explicit evaluator `invalid_input` is stored as a terminal result;
result-storage failure is retryable.

## M6 non-goals

M7 does not provide a production provider adapter, embeddings, cost,
cross-trace percentile, dataset, replay, regression, dashboard, CI, Kafka,
Kubernetes, or universal composite-score feature. The exact semantic contracts
and limitations are in `docs/SEMANTIC_EVALUATION.md`; M6 metric definitions
remain in `docs/DETERMINISTIC_EVALUATION.md`.
