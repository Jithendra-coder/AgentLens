# AgentLens Charter

## Purpose

AgentLens is a provider-independent observability, evaluation, replay, and
regression-testing platform for AI applications, RAG systems, tool-using
agents, and MCP-enabled workflows.

Its long-term questions are:

1. What happened during an AI execution?
2. Why did it happen?
3. Was the result good?
4. Did a new system version make things better or worse?

## M2 through M7 mandate

M2 implements explicit local Python instrumentation that finalizes runtime
builders into the canonical provider-independent observed execution model. M3
adds a thin network gateway that authenticates, validates, authorizes,
deduplicates, and hands off those snapshots to a process-local sink. It does
not implement durable storage or evaluation. M4 replaces that sink with
transactional PostgreSQL persistence and adds project-scoped trace queries,
without interpreting observations or running evaluation.
M5 adds a PostgreSQL-authoritative asynchronous job ledger, Redis wakeups,
worker leases, bounded retries, dead-lettering, attempt history, and
project-scoped job APIs. M5 executes only the trusted `noop` handler; it does
not calculate metrics or persist evaluation results. M6 adds a versioned,
immutable, append-only evaluation-result contract; deterministic latency,
usage, reliability, and explicit-ground-truth retrieval baselines; and atomic
result/job completion with claim-token fencing. M6 does not add semantic
judgment or model/provider calls. M7 adds bounded RAG, tool, and agent
evaluation through a provider-independent semantic-judge protocol, while
keeping deterministic evidence first, model provenance explicit, and trace
ingestion independent of semantic-provider availability.

## Evidence standard

AgentLens values reproducible engineering evidence over feature count. Claims
about correctness or performance must identify their inputs, configuration,
methodology, and actual verification result.
