# ADR-028: No Universal Composite Quality Score

Status: Accepted for M6.

## Context

Latency, usage, reliability, and retrieval ranking measure different aspects
of an AI execution. Combining them into one number requires product-specific
weights, denominators, missing-data policy, and decision thresholds.

## Decision

M6 stores named metrics and structured findings only. It does not calculate a
universal composite quality score, total quality percentage, cost-adjusted
score, or cross-trace aggregate. Any future composite must be an explicit
versioned policy with declared inputs, weights, missing-data behavior, and
evidence.

## Consequences

Consumers see the actual measured signals and cannot mistake an unexplained
single number for a general quality claim. Product-specific aggregation can be
added later without changing the immutable M6 result semantics.
