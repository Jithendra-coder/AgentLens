# ADR-027: Atomic Result and Job Completion

Status: Accepted for M6.

## Context

A worker can lose its lease between evaluator execution and persistence. A
result written without a successful job, or a job marked successful without a
result, would make the runtime ledger ambiguous and could duplicate work.

## Decision

For result-bearing evaluations, one PostgreSQL transaction locks the job using
the current claim token and attempt number, inserts the unique result, closes
the open attempt as succeeded, marks the job succeeded, and clears the lease.
Every write is fenced by the current claim. A stale worker raises
`StaleClaimError`; the transaction rolls back and cannot affect the recovered
worker's result.

## Consequences

Job/result visibility is consistent and duplicate wakeups are harmless. A
temporary result-storage failure is retryable. The transaction adds a small
database critical section, which is preferable to ambiguous partial state.
