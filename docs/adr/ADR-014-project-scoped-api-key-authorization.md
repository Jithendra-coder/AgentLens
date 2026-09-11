# ADR-014: Project-Scoped API-Key Authorization

## Status

Accepted for M3.

## Context

Trace identity and tenant isolation must be enforced at the first network
boundary. A valid credential alone must not allow cross-project ingestion.

## Decision

Each Bearer API key resolves to safe `key_id`, `project_id`, and `enabled`
metadata. The uploaded canonical trace's `project_id` must equal the
authenticated project. Keys are represented in memory by SHA-256 digests and
compared with constant-time digest comparison; raw keys never enter the sink,
logs, URLs, or error bodies.

## Consequences

M3 provides explicit project isolation without introducing user accounts or
enterprise identity. The credential registry is process-local and non-durable.
