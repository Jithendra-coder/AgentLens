# ADR-022: Lease-Fenced Worker Ownership

Status: Accepted for M5.

## Decision

Workers claim jobs transactionally with PostgreSQL `FOR UPDATE SKIP LOCKED`, a
finite lease, worker identity, and a random claim token. Lease renewal and all
completion/failure writes require the current token. Expired running jobs can
be claimed again and their open attempt is marked `lease_expired`.

## Consequences

Multiple worker processes can safely compete. A stale worker may finish local
work after a timeout or crash, but it cannot commit a result for a recovered
claim. Timeout remains cooperative because arbitrary Python threads cannot be
hard-killed safely.
