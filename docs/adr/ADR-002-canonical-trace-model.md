# ADR-002 - Canonical Trace Model

Status: Accepted

## Context

Different integrations describe execution differently. Comparisons and future
evaluations require shared semantics.

## Decision

Integrations normalize into a canonical Trace, Span, and Event domain model.
M1 defines and implements those contracts; later milestones consume them.

## Consequences

The model becomes a stable cross-provider contract. Adapters may preserve
provider-specific details at their boundary, while canonical fields need
versioning and compatibility discipline.

## Alternatives rejected

Keeping every provider's object model end-to-end was rejected because it would
make querying and evaluation provider-specific.
