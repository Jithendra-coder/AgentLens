# Architecture

## M8 position

M8 keeps the M1 canonical domain, M4 PostgreSQL trace repository, M5 durable
evaluation ledger, M6 append-only results, and M7 evaluator provenance. A
dedicated `web/` Next.js app calls a same-origin server-side BFF; the BFF calls
the authenticated FastAPI gateway. Dashboard analytics are computed by a
bounded PostgreSQL analytics repository, never by browser page aggregation.
The runtime surface is read-only.

## M7 position

M7 keeps M4's PostgreSQL trace repository, M5's separate PostgreSQL job ledger,
and M6's append-only result table, then adds explicit result modes and a
dedicated judge-provenance table. The M1 canonical domain remains the source of
truth; SQLAlchemy rows are private persistence details. Results and judge
invocations are derived records and never rewrite or extend canonical traces.

## Implemented flow

```text
AI application
      |
Python AgentLens SDK
      |
HttpTraceExporter
      |
FastAPI Ingestion Gateway (/v1)
      |
Auth / canonical validation / project isolation / limits
      |                         |
PostgresTraceRepository   Job API / PostgreSQL job ledger / result API
      |                         |                         |
PostgreSQL traces / spans  Redis wakeups -> worker -> trace reader -> evaluator
                                                            |       |
                                                   deterministic  SemanticJudge
                                                            \       /
                                                     immutable results
      |                         |
Trace Query API (detail + cursor-paginated summaries)
```

The network API version `/v1` remains distinct from the canonical schema
`agentlens-trace-v1`. M4 still accepts complete snapshots only and retrieves
the same canonical trace format.

## Dependency direction

```text
HTTP transport -> API boundary -> repository protocol -> canonical domain
SQLAlchemy/PostgreSQL -> private storage mapping
SDK core -> canonical domain
```

The M1 domain and M2 SDK do not depend on SQLAlchemy. Routes depend on the
storage/query abstraction, never on ORM entities or sessions. The API can
still inject the M3 in-memory sink for local tests, while a `DatabaseConfig`
selects the durable repository.

## M7 limits and later boundaries

M4 does not implement backups, replication, retention jobs, deletion APIs,
arbitrary attribute search, full-text search, or application-level encryption.
The authentication registry remains process-local. Redis carries only wakeups;
PostgreSQL is authoritative. M7's registry contains `noop` plus trusted
deterministic latency, usage, reliability, and retrieval handlers. M7 adds
reviewed RAG, citation, tool, and agent evaluators and an optional
provider-independent SemanticJudge. Core evaluation code does not import a
provider SDK; no tenant-controlled URL is accepted. M7 does not add a live
provider adapter, dashboard, replay, datasets, regression comparison, or CI
gates. Dashboard is M8; replay is M9; regression is M10.

## M9 dataset and replay flow

```text
Historical Traces / Manual Cases
              ↓
          Datasets
              ↓
       Finalized Versions
              ↓
         Replay Run
              ↓
    Trusted Replay Target
              ↓
        Case Executions
              ↓
        Canonical Traces
              ↓
      Existing Evaluators
```

M9 uses a separate PostgreSQL replay ledger rather than evaluation job states.
Redis is recoverable dispatch infrastructure only; leases and claim tokens
fence stale replay workers. Comparison/regression is M10 and CI quality gates
are M11. M9 does not expose arbitrary target URLs, code, or side-effectful
production adapters.

## M10 regression flow

```text
Finalized dataset version
          ↓
Baseline replay ─────┐
                     ├─ same case_id pairs → existing M6/M7 results
Candidate replay ────┘                         ↓
                                  PostgreSQL regression report
                                  ↑ Redis UUID wakeup only
```

The M10 repository enforces terminal runs, same dataset/version/checksum,
project scope, and distinct run IDs before creating a report. A worker claims a
durable run, optionally creates/reuses existing M5 evaluation jobs, and then
persists one immutable metric/case comparison set. No provider call or CI/gate
decision occurs in the comparison engine. See `docs/REGRESSION_TESTING.md`.

## M11 quality-gate flow

```text
Finalized dataset version
          ↓
Baseline replay + candidate replay
          ↓
Immutable M10 regression report
          ↓
Versioned M11 quality-gate policy
          ↓
PostgreSQL quality-gate decision
          ↓
Dashboard / API-driven CLI / external CI
```

M11 consumes completed M10 report facts only. Its synchronous evaluator is
finite and deterministic, makes no model or network calls, and stores a
separate decision artifact. PostgreSQL remains authoritative; CI consumes the
CLI exit code and AgentLens does not deploy, merge, or roll back candidates.
