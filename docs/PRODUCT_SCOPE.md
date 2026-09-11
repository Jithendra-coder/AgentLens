# Product Scope

## In scope over the product lifetime

AgentLens will provide provider-independent foundations for observing AI
executions, evaluating their quality, replaying preserved cases, and detecting
regressions across baselines and candidates.

## Explicit non-goals

AgentLens is not intended to become:

- an LLM provider
- an AI agent framework
- a vector database
- an MCP framework
- a generic workflow engine
- a chatbot builder
- a prompt-writing application
- a generic model-training platform
- an autonomous coding agent
- a generic APM replacement
- a Kubernetes replacement
- a generic BI or dashboard platform

Integrations may observe or exchange data with adjacent systems, but those
systems remain external responsibilities.

## M0 boundary

M0 implements no trace model, SDK, provider adapter, ingestion endpoint,
database, queue, worker, evaluator, dashboard, replay engine, or regression
engine. Later milestones may add these only under the roadmap and accepted
architecture decisions.

## M1 boundary

M1 adds only the canonical observed domain representation: Trace, Span, Event,
Usage, and ErrorInfo, plus validation and JSON serialization. It does not add
an SDK, provider adapter, ingestion endpoint, database, queue, worker,
evaluator, dashboard, replay engine, or regression engine.

## M2 boundary

M2 adds only the local Python instrumentation SDK: context managers, nested
spans, explicit events and payload capture, context-local propagation,
exception capture, root sampling, redaction hooks, and an in-memory exporter.
It does not add ingestion or persistence.

## M3 boundary

M3 adds the first network boundary: a versioned FastAPI gateway accepting
complete canonical trace snapshots, project-scoped Bearer authentication,
bounded JSON requests, rate limiting, idempotency/conflict handling, and a
storage-independent in-memory sink. M3 does not add durable persistence,
query APIs, provider auto-instrumentation, evaluators, dashboards, replay, or
regression testing. Independent span/event upload endpoints are intentionally
out of scope; the M1 `Trace` remains the ingestion object.

## M4 boundary

M4 adds PostgreSQL persistence, Alembic migrations, restart-safe idempotency,
transactional batch writes, and project-scoped detail/list queries with fixed
filters and cursor pagination. It does not add retention, backups,
replication, evaluation, dashboards, replay, or arbitrary search.

## M5 boundary

M5 adds durable asynchronous evaluation jobs, Redis wakeups, worker claims,
attempt history, bounded retries, lease recovery, dead-lettering, and
project-scoped job APIs. It does not add evaluation metrics, judges,
embeddings, provider adapters, result schemas, datasets, replay, regression,
dashboard, CI, Kafka, or Kubernetes.

## M6 boundary

M6 adds an immutable `agentlens-evaluation-result-v1` schema, append-only
PostgreSQL result persistence, atomic job/result completion, deterministic
latency, usage, reliability, and explicit-ground-truth retrieval-ranking
evaluators, and project-scoped result APIs. It does not add semantic or
model-based judgment, provider calls, cost calculation, cross-trace percentile
aggregation, dashboards, datasets, replay, regression comparison, or CI gates.

## M7 boundary

M7 adds bounded RAG context relevance and groundedness, deterministic citation
integrity, deterministic tool selection/arguments/efficiency, and explicit
criterion-level agent task evaluation. Results distinguish deterministic,
model-assisted, and hybrid modes. Model-assisted work depends only on the
provider-independent `SemanticJudge` protocol; no provider SDK or tenant-owned
URL is required or accepted by the core. M7 does not add dashboards, datasets,
replay, regression comparison, CI gates, model training, autonomous agents,
or a universal composite quality score.

## M10 boundary

M10 adds project-scoped baseline/candidate comparison for terminal replays,
versioned policies and immutable reports, explicit metric deltas and limits,
provenance compatibility, paired case findings, and read-only/API/dashboard
inspection. It does not add CI/CD status checks, pull-request comments,
deployment or merge blocking, notifications, rollout/rollback, arbitrary
metric code, or a universal score. Those delivery decisions remain M11.

## M11 boundary

M11 adds finite versioned quality-gate policies, immutable project-scoped
decisions over completed M10 reports, an API-driven CI CLI with stable exit
codes, a reusable CI example, and read-only dashboard inspection. It does not
deploy, roll back, merge, comment on pull requests, send notifications, install
provider-specific CI apps, or provide weighted quality trade-offs.
