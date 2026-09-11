# ADR-047 — Quality Gates Consume Immutable Regression Reports

## Status

Accepted for M11.

## Decision

M11 evaluates only completed immutable M10 regression reports. It stores a
separate `agentlens-quality-gate-decision-v1` artifact and never recalculates
metrics, reruns evaluators, calls providers, or mutates the M10 report.
