# M7 PostgreSQL Storage

## Database architecture

M4 uses synchronous SQLAlchemy 2.x with the psycopg 3 driver. A
`PostgresTraceRepository` owns one pooled engine and creates short-lived
sessions per operation. Routes depend on the repository protocol, not on
SQLAlchemy rows or sessions.

The database URL is supplied through `DatabaseConfig`; application code does
not read environment variables throughout persistence code. Passwords are
never included in configuration representations, API responses, or normal
logs.

## Tables

- `traces` stores project-scoped identity, searchable metadata, schema/status,
  timestamps, canonical fingerprint, top-level attributes, and denormalized
  span/event counts.
- `spans` stores ordered canonical span fields, parent relationships, input,
  output, attributes, and JSON usage/error objects.
- `events` stores ordered trace/span event fields and attributes.
- `evaluation_jobs` stores versioned job metadata, state, retry timing, and
  lease ownership; `evaluation_job_attempts` stores bounded attempt history.
- `evaluation_results` stores immutable M7 result records, provenance,
  normalized configuration, fingerprints, metrics, findings, and evidence.
  `job_id` is unique, so one successful result-bearing job can produce at most
  one result.
- `evaluation_judge_invocations` stores safe model-assisted provenance linked
  to the result and job. It does not store raw requests, raw responses, or
  hidden reasoning.

The composite identity `(project_id, trace_id)` is the trace primary key and is
protected by database uniqueness. Child rows use composite foreign keys with
cascade deletion, so administrative trace deletion cannot orphan spans or
events. Evaluation results also reference the trace and job and are removed by
the same database cascade if their source trace is administratively deleted.
M4 exposes no delete endpoint.

## Canonical mapping

The repository maps a validated M1 `Trace` into relational searchable fields
and child rows. It stores span/event positions so reconstruction preserves
canonical ordering. Reads rebuild one JSON-compatible document and call
`Trace.from_dict`; SQLAlchemy objects never escape the storage boundary.

## JSONB strategy

Flexible JSON-safe payloads remain JSONB: trace/span attributes, span input and
output, and usage/error objects. Trace IDs, project/session identity, names,
status, timestamps, fingerprints, parent IDs, span types, and counts remain
relational for filtering and integrity.

## Transactions and idempotency

Single and batch writes use one database transaction. Batch parent rows are
inserted with PostgreSQL `ON CONFLICT DO NOTHING` and `RETURNING`; existing
rows are locked and compared with the M3 SHA-256 fingerprint. A matching
fingerprint is a durable duplicate/no-op. A changed fingerprint raises a
conflict, and the transaction rolls back all new rows in that batch.

The unique identity constraint protects concurrent submissions. M4 therefore
preserves M3 semantics across process restarts and concurrent repository
instances.

## Indexes and queries

Indexes support project/time, project/status, project/session, project/name,
trace child lookup, span parent lookup, and span-type filtering. List queries
use one bounded summary query with denormalized counts; they do not issue
per-trace count queries.

## Migrations and durability boundary

Alembic migrations are authoritative. Startup never calls
`metadata.create_all()`. Use `alembic upgrade head`; the initial migration has
a safe downgrade that drops child tables before parent tables.

PostgreSQL persistence survives application restarts, but M7 does not
implement backups, replication, point-in-time recovery, retention/deletion
jobs, or application-level field encryption. Results are append-only through
the repository contract; updates/deletes are not exposed by the API. TLS and
storage encryption are deployment responsibilities. The API-key registry
remains the M3 process-local registry. Migration `0003_evaluation_results`
appends the result table without modifying migrations `0001` or `0002`;
`0004_semantic_evaluation` adds result modes and judge provenance without
modifying prior migrations.
