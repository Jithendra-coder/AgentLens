# ADR-016: Storage-Independent Ingestion Sink

## Status

Accepted for M3.

## Context

HTTP routing and canonical validation should not be rewritten when M4 adds
durable persistence.

## Decision

Routes emit validated canonical `Trace` objects through the
`TraceIngestionSink` protocol. M3 supplies a lock-protected in-memory sink
with idempotency and request-level batch preflight. Persistence, transactions,
and query operations are outside the M3 sink contract.

## Consequences

M4 can provide a PostgreSQL-backed implementation behind the same boundary.
The M3 implementation is intentionally process-local and non-durable.
