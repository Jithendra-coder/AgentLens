# ADR-025: Immutable Versioned Evaluation Results

Status: Accepted for M6.

## Context

M5 can execute a trusted job but has no durable representation of what an
evaluator produced. A result must remain distinct from the observed trace and
the operational job state, and it must be safe to read across process restarts.

## Decision

M6 defines `agentlens-evaluation-result-v1` as a separate immutable result
contract. Each result stores project/trace/job identity, evaluation type,
evaluator name/version, terminal result status, creation time, normalized
configuration, configuration and trace fingerprints, metrics, findings, and
evidence. PostgreSQL stores results in an append-only table with a unique
`job_id`.

## Consequences

Results are auditable, provider-independent, and reproducible from the stored
trace fingerprint and configuration. The schema intentionally carries derived
data and provenance but does not rewrite observations or expose mutable ORM
objects.
