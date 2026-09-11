# ADR-031 — Deterministic Evidence Before Semantic Judgment

Status: Accepted

## Context

Exact facts such as citation existence, expected tool calls, and argument
matches are more reliable and cheaper to establish with program logic.

## Decision

M7 uses deterministic evaluators for structural citation validity, tool ground
truth, and simple agent criteria. Semantic judges are reserved for contextual
relevance, groundedness, and criteria that require interpretation. Hybrid
results expose both mechanisms.

## Consequences

Semantic calls are bounded to the remaining ambiguity, and evaluation results
retain dimension-specific metrics instead of an opaque composite quality score.
