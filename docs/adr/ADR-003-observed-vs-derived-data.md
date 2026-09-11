# ADR-003 - Observed versus Derived Data

Status: Accepted

## Context

Observed execution history is evidence. Evaluator outputs are interpretations
that may change as evaluators improve.

## Decision

Observed traces and derived evaluation results remain separate records and
boundaries. Evaluator changes must never mutate historical observations.

## Consequences

The same observation can be evaluated repeatedly and compared across evaluator
versions. Storage and query paths must make provenance and source references
explicit.

## Alternatives rejected

Writing scores directly into observed trace payloads was rejected because it
would mix history with mutable interpretation.
