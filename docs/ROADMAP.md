# Roadmap

Every milestone is bounded by its exclusions and exits only when its evidence
exists. M0 established the constitution; M1 is the completed domain-model
milestone.

## M0 - Project Constitution & Engineering Foundation

- **Objective:** Establish product boundaries, architectural laws, package
  structure, documentation, and quality gates.
- **Major deliverables:** Constitution docs, ADR-001 through ADR-006, Python
  package foundation, tests, and verification configuration.
- **Key exclusions:** Trace objects, SDKs, APIs, storage, queues, workers,
  evaluators, dashboards, replay, and regression features.
- **Exit criteria:** Required documents exist; package imports; pytest, Ruff,
  mypy, compilation, and dependency checks pass.

## M1 - Canonical Trace Domain Model

- **Objective:** Define and implement provider-independent Trace, Span, and
  Event contracts.
- **Major deliverables:** Typed Trace, Span, Event, Usage, and ErrorInfo domain
  objects; JSON-safe immutable payloads; structural validation; serialization;
  and adversarial contract tests.
- **Key exclusions:** Provider instrumentation, network ingestion, storage,
  and evaluation execution.
- **Exit criteria:** Domain contracts are versioned, deterministic, tested,
  round-trip safely, and documented without provider dependencies.

## M2 - Python Instrumentation SDK

- **Objective:** Capture application execution into the canonical model.
- **Major deliverables:** Local AgentLens client, sync/async trace and span
  context managers, contextvars propagation, explicit capture APIs, exception
  capture, root sampling, redaction, and in-memory export.
- **Key exclusions:** Ingestion service, durable storage, evaluators, and
  dashboards.
- **Exit criteria:** Sampled executions finalize into valid M1 Traces; sync,
  async isolation, exceptions, mutation safety, redaction, sampling, and
  exporter failure contracts pass. No performance target is claimed.

## M3 - Trace Ingestion Gateway (PASS)

- **Objective:** Accept and validate canonical traces reliably over HTTP.
- **Major deliverables:** FastAPI `/v1` single and batch ingestion, health
  endpoints, request IDs, stable errors, hashed project-scoped Bearer keys,
  body and batch limits, process-local rate limiting, idempotency/conflict
  detection, a storage-independent sink, and `HttpTraceExporter`.
- **Key exclusions:** Durable query storage, distributed coordination, and
  evaluation workers.
- **Exit criteria:** Valid canonical traces are accepted, invalid and
  cross-project payloads are rejected, duplicate retries are safe within the
  process lifetime, and ingestion does not depend on evaluation success.

## M4 - PostgreSQL Trace Storage & Query (PASS)

- **Objective:** Persist and query observed execution data durably.
- **Major deliverables:** PostgreSQL schema, Alembic migrations, canonical
  repository mapping, transactional/idempotent writes, project-scoped detail
  and summary queries, filters, signed cursor pagination, and DB readiness.
- **Key exclusions:** Evaluation interpretation, analytics UI, backups,
  retention, and replication.
- **Exit criteria:** Persistence, migration, isolation, concurrency, and query
  contracts pass against real PostgreSQL evidence.

## M5 - Asynchronous Evaluation Runtime (PASS)

- **Objective:** Run trusted, durable asynchronous jobs downstream from
  ingestion.
- **Major deliverables:** PostgreSQL job ledger, Redis wakeup boundary, worker
  lifecycle, retries, failure isolation, lease recovery, and safe attempt
  persistence.
- **Key exclusions:** Specific quality metrics and LLM judges.
- **Exit criteria:** Evaluation failure cannot invalidate a stored observation;
  retry, lease recovery, safe attempt history, Redis outage behavior, and
  project isolation pass against real PostgreSQL and Redis.

## M6 - Deterministic Evaluation Baselines (PASS)

- **Objective:** Deliver reproducible non-probabilistic metrics.
- **Major deliverables:** Versioned immutable result records; atomic result/job
  completion; latency, usage, reliability, and retrieval-ranking metric
  contracts; provenance and result APIs.
- **Key exclusions:** Learned or LLM-based judgment.
- **Exit criteria:** Metrics have definitions, fixtures, provenance, durable
  project isolation, stale-worker protection, and reproducible integration
  evidence against real PostgreSQL and Redis.

## M7 - RAG / Tool / Agent Evaluators

- **Objective:** Evaluate retrieval, tools, and agent behavior.
- **Major deliverables:** provider-independent structured semantic judging with
  bounded evidence and provenance; context relevance, groundedness, and
  citation integrity; deterministic tool selection, arguments, efficiency, and
  explicit criterion-level agent evaluation; hybrid result modes; atomic
  PostgreSQL invocation provenance.
- **Key exclusions:** live provider dependency in core, arbitrary tenant URLs,
  chain-of-thought collection, model training, dashboard, datasets, replay,
  regression comparison, CI gates, and a universal score.
- **Exit criteria:** Each evaluator is versioned, deterministic where
  possible, uses explicit task/ground truth, exposes criterion evidence, and is
  tested against fake-judge and real PostgreSQL/Redis runtime evidence.

## M8 - Observability & Analytics Dashboard

- **Status:** PASS — implemented in the current workspace.
- **Objective:** Make observed and derived data inspectable.
- **Major deliverables:** Dedicated Next.js overview, trace explorer/detail,
  evaluation explorer/detail, PostgreSQL percentile/timeseries analytics, and
  read-only runtime health.
- **Key exclusions:** Generic BI/APM replacement behavior, accounts, billing,
  model integration, replay/datasets, regression comparison, CI gates, and
  destructive runtime controls.
- **Exit criteria:** Views preserve tenant/security boundaries, distinguish
  observations from interpretations, and pass real PostgreSQL/Redis/API/Next
  integration verification.

## M9 - Dataset & Replay Engine

- **Status:** PASS — implemented and verified in the current workspace.
- **Objective:** Preserve historical/manual cases and execute safe replay
  workflows.
- **Major deliverables:** Project-scoped datasets; draft/finalized immutable
  versions; ordered checksumed cases; trace provenance; import/export; trusted
  target profiles; explicit exact/controlled/best-effort manifests; durable
  replay run/execution/attempt ledger; bounded timeout/retry/concurrency;
  Redis recovery and claim fencing; canonical trace links; Datasets and Replays
  dashboard surfaces.
- **Key exclusions:** Run comparison, metric deltas, regression findings,
  quality gates, arbitrary URLs/code, blind production side effects, automatic
  expensive evaluation, large annotation workflows, branching/merging, and
  universal reproducibility claims.
- **Exit criteria:** Real PostgreSQL, Redis, FastAPI, Next.js, and Chromium
  verification passes while M0–M8 behavior remains green.

## M10 - Regression Testing Engine

- **Status:** PASS — implemented and verified in the current workspace.
- **Objective:** Compare candidates against baselines without collapsing
  independent quality/performance dimensions into a score.
- **Major deliverables:** Versioned immutable policies and reports, same-
  dataset/case pairing, explicit metric rules, compatibility-aware provenance,
  durable PostgreSQL/Redis orchestration, case findings, APIs, and dashboard
  explorer/detail views.
- **Key exclusions:** CI/CD gates, deployment decisions, notifications,
  universal composite scores, arbitrary metric code, and provider calls from
  comparison logic.
- **Exit criteria:** Decisions cite datasets, metrics, methodology, provenance,
  and policy-significant evidence.

## M11 - CI/CD Quality Gates

- **Status:** PASS — implemented and verified in the current workspace.
- **Objective:** Enforce evaluation and regression policies in delivery flows.
- **Major deliverables:** Immutable versioned gate policies and decisions,
  explicit blocking/advisory outcomes, machine-readable API/CLI contracts,
  stable exit codes, and a CI example.
- **Key exclusions:** Owning a complete CI/CD platform.
- **Exit criteria:** Gate behavior is documented, reproducible, project-scoped,
  and safe to fail without corrupting observations; M10 reports remain
  diagnostic. Immutable policies/decisions, missing and incompatible evidence
  semantics, candidate limits, replay requirements, API/CLI contracts,
  migration 0007, dashboard surfaces, and CI example are verified.

## M12 - Performance, Reliability & Security

**Status:** PASS WITH LIMITATIONS — bounded local evidence is complete; see
`docs/M12_COMPLETION_REPORT.md`.

- **Objective:** Measure and harden production behavior.
- **Major deliverables:** p50/p95/p99 latency, throughput, error rate, CPU,
  memory, queue lag, storage growth, threat controls, and load evidence.
- **Key exclusions:** Invented targets or unscoped infrastructure claims.
- **Exit criteria:** Results include hardware, workload, configuration, sample
  size, methodology, and reproducible raw evidence.

## M13 - Production Deployment Foundation & Service Lifecycle

- **Status:** PASS — implemented and verified in the current workspace.
- **Objective:** Establish production deployment architecture, containerization, unified configuration, lifecycle management, health probes, structured logging, and advisory-locked migrations.
- **Major deliverables:** Multi-stage Dockerfiles (`Dockerfile.api`, `Dockerfile.worker`, `Dockerfile.web`), `docker-compose.prod.yml`, Twelve-Factor `AgentLensSettings` with fail-fast validation, `LifecycleCoordinator` with graceful shutdown, `/health/live`, `/health/ready`, and `/health/startup` probes, advisory-locked PostgreSQL migration runner (`migration_runner.py`), JSON structured logging with request/correlation ID tracking, and operations/deployment documentation (`DEPLOYMENT.md`, `OPERATIONS.md`, `CONFIGURATION.md`, `M13_TO_M30_MASTER_PLAN.md`).
- **Key exclusions:** Multi-tenant RBAC (M15), enterprise OAuth/OIDC (M16), external telemetry exporters (M14).
- **Exit criteria:** Container definitions, configuration validation, lifecycle shutdown, advisory lock migration safety, health probes, and documentation verified.

## M14 - Production Observability for AgentLens

- **Objective:** Instrument AgentLens with internal telemetry, metrics, and operational dashboards.
- **Major deliverables:** Internal latency distributions, throughput metrics, queue depth, lease age, Prometheus `/metrics` endpoint, operational health dashboard.

## M15 - Multi-Tenant Organization & Access Control

- **Objective:** Introduce hierarchical tenancy (`Organization -> Projects -> Users -> Roles -> API Keys`).
- **Major deliverables:** Organization/user schemas, RBAC (`Owner`, `Admin`, `Developer`, `Viewer`, `Auditor`), API key rotation/revocation, permission middleware.

## M16 - Authentication & Enterprise Security Boundary

- **Objective:** Production-grade identity and perimeter security.
- **Major deliverables:** Secure sessions, password authentication / OIDC abstraction, MFA-ready contracts, token lifecycle, security audit log.

## M17 - Advanced Trace Analytics

- **Objective:** Turn traces into deep analytical intelligence.
- **Major deliverables:** Latency distributions, token trends, error clustering, agent graph analytics, tool failure analysis, trace comparison view.

## M18 - Advanced Extensible Evaluation Platform

- **Objective:** Registry-driven evaluation framework supporting deterministic, semantic, retrieval, tool, agent, and composite evaluators.
- **Major deliverables:** Evaluator registry, versioning, input/output schemas, risk/cost classification, lifecycle states.

## M19 - Custom Evaluator SDK & Isolated Execution

- **Objective:** Enable custom evaluator authoring without modifying core AgentLens code.
- **Major deliverables:** Python SDK `Evaluator` base class, out-of-process sandboxed execution worker with resource limits.

## M20 - Production Model Provider Layer

- **Objective:** Provider-agnostic model judge layer with production resiliency.
- **Major deliverables:** Resilient adapters (OpenAI, Anthropic, Gemini, local), rate limiting, jitter, backoff, circuit breakers, cost measurement.

## M21 - Cost & Usage Intelligence

- **Objective:** Granular financial visibility and attribution for AI workloads.
- **Major deliverables:** Cost tracking per trace/session/model/eval/replay/regression, pricing catalog, cost anomaly detection.

## M22 - Experimentation & Model/Prompt Comparison

- **Objective:** Systematic evaluation of candidate models, prompts, and configurations against baselines.
- **Major deliverables:** Multi-candidate experiment engine, trade-off matrix (quality vs cost vs latency vs reliability).

## M23 - Adaptive Evaluation & Model Routing

- **Objective:** Evidence-based dynamic selection of evaluators and judge tiers.
- **Major deliverables:** Risk-aware routing engine, model escalation triggers, routing audit trail.

## M24 - Evaluation Benchmark & Model Qualification

- **Objective:** Scientific benchmark suite to qualify models before routing eligibility.
- **Major deliverables:** Standardized ground-truth benchmark suite, precision/recall/agreement metrics, qualification gate.

## M25 - Advanced Regression Intelligence

- **Objective:** Detect nuanced multidimensional and cohort-specific regressions.
- **Major deliverables:** Segment, cohort, and temporal regression analysis with root trace deep links.

## M26 - Continuous Production Monitoring & Smart Sampling

- **Objective:** Real-time continuous evaluation of live production traces.
- **Major deliverables:** Configurable sampling policies (percentage, error, high-cost, risk), live evaluation pipeline.

## M27 - Alerting & Incident Intelligence

- **Objective:** Proactive alerting on regressions, anomalies, and quality degradation.
- **Major deliverables:** Alert rule engine, pluggable notification adapters (webhooks, email, Slack), incident evidence grouping.

## M28 - Root-Cause Analysis & Failure Clustering

- **Objective:** Automated pattern detection and diagnosis across failed traces.
- **Major deliverables:** Statistical clustering across failures (prompts, tools, retrievers, exceptions), hypothesis generation with confidence scores.

## M29 - Governance, Audit & Enterprise Controls

- **Objective:** Complete enterprise governance, auditability, and data lifecycle management.
- **Major deliverables:** Immutable audit logs, approval workflows for quality gate policies, PII redaction, retention/purging schedules.

## M30 - Production Platform Hardening & GA Certification

- **Objective:** Final engineering certification, resilience validation, and production readiness.
- **Major deliverables:** Chaos testing, load benchmarks, security review, automated backup/restore verification (RPO < 15m, RTO < 30m), `PRODUCTION_READINESS_REPORT.md`, GA release.
