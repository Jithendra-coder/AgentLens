# M12 Performance Evidence

M12 performance claims are measured, workload-specific observations rather
than service-level objectives. Run the reproducible harness from the repository
root after starting the local PostgreSQL, Redis, FastAPI, and worker stack:

```powershell
$env:AGENTLENS_DATABASE_URL="postgresql+psycopg://agentlens:agentlens@127.0.0.1:55432/agentlens"
$env:AGENTLENS_REDIS_URL="redis://127.0.0.1:56379/0"
$env:AGENTLENS_BENCHMARK_API_KEY=$env:AGENTLENS_PROJECT_API_KEY
py -3.11 scripts/benchmark_m12.py
```

The harness writes `artifacts/m12/benchmark.json` with schema
`agentlens-benchmark-result-v1`. It records OS, CPU, logical CPU count, memory
availability, Python/Node, PostgreSQL/Redis versions, configuration URLs with
credentials removed, the unavailable Git-history status, warmup and measured
counts, concurrency, operation names, successes, failures, duration, raw
latency samples, and p50/p95/p99. Percentiles use linear interpolation over
successful samples only. A failed request is never converted into a latency
sample, and missing measurements are explicitly labelled `not_measured`.

The current harness measures SDK no-instrumentation, AlwaysOff, AlwaysOn with
`InMemoryTraceExporter`, live single/batch ingestion, trace list/detail,
analytics, and runtime-summary calls. Queue drain, worker throughput, storage
growth, and multi-worker scaling require a separately provisioned workload and
are not represented by invented numbers; the report records that limitation.

The benchmark intentionally uses bounded local workloads. It is not a
capacity guarantee, production SLO, or certification.
