# Testing Strategy

## Hierarchy

```text
tests/
|-- unit/
|-- contract/
|-- integration/
|-- adversarial/
`-- regression/
```

Performance tests may live under `benchmarks/` or a dedicated performance
suite when justified.

## Test classes

- **Unit tests** verify pure deterministic behavior.
- **Contract tests** verify schemas, serialization, public APIs, and
  compatibility contracts.
- **Integration tests** verify database, queue, worker, HTTP, and API
  boundaries when those systems exist.
- **Adversarial tests** cover malformed input, hostile structure, tenant
  leakage attempts, pathological traces, oversized payloads, and related
  failure cases.
- **Regression tests** permanently preserve previously fixed bugs.

## M2 through M6 verification

M2 retains all M1 checks and adds synchronous and asynchronous SDK lifecycle,
nested parent relationships, contextvars isolation, exception fidelity,
sampling, redaction, exporter failure isolation, lifecycle misuse, and
mutation-safety checks. M3 adds ASGI integration coverage for canonical
single/batch ingestion, auth/project isolation, body and batch limits, stable
errors, request IDs, health, deterministic rate limiting, idempotency/conflicts,
security leakage checks, OpenAPI, and SDK HTTP exporter delivery. The
repository runs pytest in CI. Ruff and strict mypy are configured, but the
current source tree still has existing lint and typing findings; those checks
are not represented as passing release gates. M4 adds real PostgreSQL migration, canonical
round-trip, transaction rollback, restart idempotency, concurrent conflict,
project isolation, filters, cursor pagination, query API, and readiness tests.
M5 adds real PostgreSQL migration downgrade/re-upgrade, real Redis dispatch,
durable job creation, idempotency, worker completion, concurrent claims,
bounded retry/dead-letter behavior, lease expiry recovery, Redis outage
isolation, project-scoped job reads, safe error storage, and degraded
readiness. M6 adds unit fixtures for metric definitions and malformed retrieval
inputs, immutable result-model validation, PostgreSQL migration and round-trip
coverage, atomic result/job completion, stale-worker rejection, result API
project isolation, result linkage, duplicate wakeup handling, and the full M5
regression suite. M3 tests do not sleep or claim distributed durability; M5/M6
timing tests use bounded short leases only against real dependencies.

## M7 verification

M7 unit tests use a test-only deterministic fake judge to inspect bounded
structured requests and return predefined strict responses. They cover
injection text, unknown response fields, malformed arrays, timeouts, rate
limits, unavailable judges, per-document relevance, supported/partial/
unsupported claims, citations, expected/missing/unexpected/duplicate tools,
exact arguments, order, agent required/optional criteria, and hybrid mode.
The M7 integration suite uses real PostgreSQL and Redis to verify API type
registration, worker execution, atomic result plus invocation persistence,
project isolation, and deterministic evaluators without semantic-provider
infrastructure. No paid provider or live credential is required.
