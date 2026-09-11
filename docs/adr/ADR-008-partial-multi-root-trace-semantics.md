# ADR-008 - Partial and Multi-Root Trace Semantics

Status: Accepted

## Context

Telemetry can be interrupted, distributed, sampled, or received without a
single visible root. Requiring complete timing or exactly one root would reject
valid observations.

## Decision

AgentLens permits unfinished traces, unfinished spans, zero-span traces,
events-only traces, and multiple root spans. It rejects structural errors such
as duplicate IDs, missing parents, self-parenting, cycles, cross-trace objects,
and invalid event span references.

Parent/child timestamp containment is not required because partial and
distributed telemetry can make that relationship unavailable or misleading.

## Consequences

The model preserves more real-world observations and makes incompleteness
explicit through absent end times. Consumers must distinguish partial data from
structurally invalid data.

## Alternatives rejected

Requiring one root and complete nested timing was rejected because it would
discard valid distributed or interrupted executions.
