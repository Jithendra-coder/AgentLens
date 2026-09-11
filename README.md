# AgentLens

**Enterprise Observability, Evaluation, Quality Assurance & Governance Platform for Autonomous AI Agents**

AgentLens provides an end-to-end, provider-independent platform for tracing, evaluating, optimizing, and governing AI applications, RAG systems, tool-using agents, and multi-step autonomous workflows.

---

## Key Features & Capabilities

### 🔍 1. High-Throughput Distributed Telemetry & Tracing
- **Canonical Execution Domain Model**: Provider-independent `Trace`, `Span`, `Event`, `Usage`, and `ErrorInfo` representations.
- **Hybrid Storage Engine**: Dual backend utilizing **PostgreSQL** for relational metadata/RBAC and **DuckDB** for trace analytics.
- **FastAPI Ingress Protocol**: Asynchronous, rate-limited `/v1/traces` ingestion with request correlation IDs and API key authentication.
- **Latency & Bottleneck Profiler**: P50/P95/P99 latency analysis and critical-path DAG visualization.

### 🧪 2. Deterministic Testing, Replays & CI/CD Quality Gates
- **Trace Replay Sandbox**: Reproduce exact production failure trajectories in a sandboxed mock environment.
- **Regression Detection**: Automated regression comparisons across latency, cost, and output accuracy.
- **CI/CD Quality Gates & CLI**: Native `agentlens` CLI to enforce blocking release policies directly in CI/CD deployment pipelines.

### 🏢 3. Enterprise Security, Multi-Tenancy & Secret Vault
- **Multi-Tenant RBAC**: Hierarchical roles (*Org Admin*, *Developer*, *Viewer*) with strict project-level foreign key isolation.
- **AES-256-GCM Secret Vault**: Securely encrypted storage for third-party LLM provider keys with JWT session management.
- **Automated PII Redaction**: Real-time sanitization of emails, international phone numbers, and bearer credentials.

### ⚡ 4. Evaluation Platform & Adaptive Model Routing
- **Composite Quality Metrics**: Configurable weighted scoring combining exact-match, regex, structural schema, and semantic LLM judges.
- **Custom Evaluator Plugin SDK**: Extensible Python SDK to dynamically register, test, and execute custom evaluation plugins.
- **Multi-Model Provider Gateway**: Resilient unified gateway across OpenAI, Anthropic, Gemini, Mistral, and local models with automatic fallback cascades.
- **Adaptive Quality & Cost Router**: Heuristic model selection routing simple queries to lightweight models and complex tasks to frontier models.
- **Cost Intelligence & Budgets**: Multi-dimensional token attribution and spend governance with hard departmental budget caps.
- **Statistical Drift Detection**: Continuous tracking of latency and evaluation distributions using Kolmogorov-Smirnov (KS) and Population Stability Index (PSI) tests.
- **Automated Root-Cause Analysis (RCA)**: Diagnostic classification of trace failures (prompt injections, context window overflows, timeouts, provider errors, and hallucinations) with normalized failure clustering.

### 🛡️ 5. Cryptographic Compliance & Governance
- **SHA-256 Audit Hash Chaining**: Immutable, tamper-evident audit ledger recording all administrative actions.
- **Data Retention Policies**: Automated enforcement of GDPR/HIPAA retention windows.
- **Signed Compliance Bundles**: One-click generation of verifiable compliance export archives.

---

## Architecture Overview

```
Agent Applications (Python SDK / OpenTelemetry)
       │
       ▼
AgentLens Ingress Gateway (FastAPI)
       │
 ┌─────┴───────────────────────────────────────────────────────┐
 │                                                             │
 ▼                                                             ▼
PostgreSQL Metadata Store                             DuckDB Analytical Engine
(Traces, Evals, RBAC, Secrets, Audits)                (Trace Analytics & Profiling)
       │
 ┌─────┴───────────────────────────────────────────────────────┐
 │                                                             │
 ▼                                                             ▼
Asynchronous Workers                                  Next.js 14 Web Console
(Evaluations, Regressions, Replays)                   (14 Dedicated Observability Studios)
```

---

## Quickstart

### 1. Run via Docker Compose
```bash
docker-compose up -d
```

### 2. Start the Backend API
```bash
pip install -e .
alembic upgrade head
python -m agentlens.api
```

### 3. Launch the Web Console
```bash
cd web
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to access the AgentLens Web Console.

---

## Testing & Quality

Run the complete automated test suite:
```bash
pytest
```

Run static type and lint checks:
```bash
mypy src
ruff check .
```

---

## License
Apache 2.0
