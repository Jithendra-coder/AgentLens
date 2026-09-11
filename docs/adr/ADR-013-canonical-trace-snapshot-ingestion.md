# ADR-013: Canonical Trace Snapshot Ingestion

## Status

Accepted for M3.

## Context

The SDK finalizes an execution into the M1 canonical `Trace`. Independently
uploading spans or events would require stateful assembly, ordering, partial
retry, and persistence semantics before M4.

## Decision

M3 accepts complete `agentlens-trace-v1` trace snapshots through
`POST /v1/traces` and `/v1/traces/batch`. The gateway reconstructs each object
with `Trace.from_dict`; no independent span, event, usage, or error ingestion
endpoints are added.

## Consequences

M1 remains the single canonical validation source of truth. Incremental
streaming and assembly are deferred until a later milestone justifies their
state and durability model.
