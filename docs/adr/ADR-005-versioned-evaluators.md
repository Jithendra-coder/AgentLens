# ADR-005 - Versioned Evaluators

Status: Accepted

## Context

Scores without evaluator provenance cannot be reproduced or compared safely.
Evaluation logic and configuration will evolve.

## Decision

Evaluator implementations, configurations, and results require provenance:
name, version, configuration version, timestamp, evaluated input/reference,
result, score, and evidence/reason. Model judges also record provider, model,
prompt version, and parameters when applicable.

## Consequences

Results are auditable and re-runnable. Result schemas are slightly larger, and
version changes must be explicit.

## Alternatives rejected

A bare score such as `{"quality": 0.91}` was rejected because it cannot answer
what produced the result.
