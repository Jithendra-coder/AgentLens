# ADR-015: Trace Identity and Idempotent Ingestion

## Status

Accepted for M3.

## Context

HTTP retries are expected, but trace history must not be overwritten by a
changed payload carrying an existing identifier.

## Decision

The M3 ingestion identity is `(project_id, trace_id)`. The sink fingerprints
the deterministic `Trace.to_json()` representation with SHA-256. An identical
retry is a no-op and returns `duplicate: true`; changed canonical content is a
`409 Conflict`, and the stored original is preserved. Repeated IDs inside one
batch are rejected even when payloads are identical.

## Consequences

M3 provides idempotent acceptance within one process lifetime. It does not
claim exactly-once delivery or durable deduplication across restarts.
