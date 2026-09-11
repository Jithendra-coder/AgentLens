# ADR-012 - Root-Level Sampling

Status: Accepted

## Context

Sampling individual spans within one trace would create incomplete graphs and
make local instrumentation semantics unpredictable.

## Decision

M2 makes one sampling decision when an explicit root trace is created. A
sampled root retains all nested spans/events and exports one canonical trace.
An unsampled root preserves application control flow but exports no canonical
trace.

## Consequences

The trace is either retained as a coherent observation or dropped as a whole.
M2 supports only always-on and always-off policies; adaptive and distributed
sampling are deferred.

## Alternatives rejected

Per-span sampling was rejected because it would violate the canonical graph
integrity expected by downstream consumers.
