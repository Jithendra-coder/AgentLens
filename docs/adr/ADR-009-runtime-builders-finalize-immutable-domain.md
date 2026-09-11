# ADR-009 - Runtime Builders Finalize into Immutable Domain Objects

Status: Accepted

## Context

M1 canonical observations are frozen and recursively immutable, while active
instrumentation needs to collect timing, children, events, and explicit user
fields incrementally.

## Decision

M2 uses mutable internal trace and span runtime handles. At context exit, those
handles are validated and converted into immutable M1 `Trace`, `Span`, and
`Event` objects. The SDK never mutates an already finalized domain object.

## Consequences

Capture is convenient during execution and finalized observations remain safe
for later storage and evaluation. Runtime handles have lifecycle rules and
must reject capture after exit.

## Alternatives rejected

Mutating frozen M1 objects during capture was rejected because it would weaken
the canonical observation contract and mutation-safety guarantees.
