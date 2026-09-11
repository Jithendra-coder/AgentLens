# ADR-049 — Explicit Missing and Incompatible Evidence Semantics

## Status

Accepted for M11.

## Decision

Every rule declares trusted `fail`, `indeterminate`, or `ignore` behavior for
missing and incompatible M10 evidence. A blocking rule defaults to
`indeterminate`; missing or incompatible evidence never silently passes.
