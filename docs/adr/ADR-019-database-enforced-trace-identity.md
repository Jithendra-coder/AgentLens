# ADR-019: Database-Enforced Trace Identity

## Status

Accepted for M4.

## Context

Process-local check-then-insert logic cannot safely resolve concurrent retries
or conflicts.

## Decision

The database primary key `(project_id, trace_id)` is the durable idempotency
identity. Inserts use a PostgreSQL uniqueness conflict boundary; committed
content is compared using the unchanged M3 SHA-256 canonical fingerprint.

## Consequences

Concurrent identical submissions produce one row and duplicate semantics.
Concurrent changed submissions produce one authoritative row and a conflict;
the first committed content is never overwritten.
