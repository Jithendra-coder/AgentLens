# ADR-021: PostgreSQL Job Ledger with Redis Wakeups

Status: Accepted for M5.

## Decision

Persist evaluation jobs and attempts in PostgreSQL before attempting to publish
a minimal `{job_id}` wakeup to the versioned Redis list
`agentlens:evaluation:v1`. Recovery scans PostgreSQL and re-publishes
dispatchable jobs. Duplicate delivery is expected and safe.

## Rationale

The database can preserve a queued job across Redis outages. Treating Redis as
authoritative or requiring an unsafe database/queue dual write could lose jobs
or block trace ingestion.

## Consequences

Redis outage makes evaluation dispatch degraded, not trace storage unavailable.
The worker must re-read and claim from PostgreSQL, and operators need a
recovery scan after Redis returns.
