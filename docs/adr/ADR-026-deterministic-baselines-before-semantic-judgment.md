# ADR-026: Deterministic Baselines Before Semantic Judgment

Status: Accepted for M6.

## Context

AgentLens needs useful evaluation evidence before introducing model judges,
provider adapters, prompts, embeddings, or probabilistic behavior. Early
metrics must be reproducible and explainable from one canonical trace.

## Decision

M6 implements only local deterministic latency, usage, reliability, and
explicit-ground-truth retrieval-ranking evaluators. They use no network,
randomness, or ML dependency. Configuration normalization is deterministic and
the normalized value is stored with the result. Malformed evaluator input is
an explicit `invalid_input` result rather than a retryable infrastructure
failure.

## Consequences

Metric definitions can be unit-tested and reproduced exactly. Semantic answer
quality, groundedness, model/provider comparison, and probabilistic findings
remain later milestone work with separate contracts.
