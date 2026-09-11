# Regression Testing

M10 compares two terminal replay runs that reference the same finalized dataset
version and checksum. The baseline is the reference run; the candidate is the
run being examined. Cases pair by immutable dataset `case_id`, never by
position or output text.

## Schemas and immutability

Reports use `agentlens-regression-report-v1`, policies use
`agentlens-regression-policy-v1`, and the deterministic comparison engine is
versioned separately. Policies are immutable versioned rows. A changed rule
creates a new policy version. A completed report stores the selected policy
version, both replay manifests, dataset checksum, evaluation plan, metric
provenance, and comparison-engine version; PostgreSQL claim fencing prevents a
second write after completion.

M10 has no hidden default policy and no universal composite score. Every
classified metric has an explicit direction, absolute and/or relative
tolerance, minimum sample count, and optional candidate minimum/maximum. A
candidate limit is displayed independently from baseline movement.

## Metric semantics

The trusted registry currently supports trace duration mean/p50/p95/p99,
replay execution success rate, observed reliability error rate, reported
input/output/total token means, retrieval Precision@5/Recall@5/MRR/NDCG@5,
RAG groundedness and mean context relevance, tool success rate, and agent task
success.

Reports contain baseline, candidate, absolute delta, relative delta, sample
counts, paired sample count, and one of `improved`, `unchanged`, `regressed`,
`insufficient_data`, `incompatible`, or `informational`. Relative delta is
`null` when the baseline is zero. Rate deltas are decimal/percentage-point
semantics in the API; the dashboard renders them as percentages. M10 makes no
statistical significance claim.

## Measurement compatibility

Evaluation-backed metrics require matching evaluation type, evaluator name and
version, normalized configuration, and semantic judge provider/model/adapter,
prompt version, and parameters. Only evaluator-owned trace-local exclusions
are normalized; retrieval `span_id` is the current explicit exclusion. An
incompatible measurement is visible and is not silently compared.

M10 reuses M5-M7 evaluator jobs/results. If a requested evaluation is missing,
the regression worker creates a deterministic idempotent M5 job and waits for
the existing evaluation worker. The comparison engine itself never calls a
provider.

## Runtime and APIs

PostgreSQL is authoritative. Redis only carries UUID wakeups on
`agentlens:regression:v1`; recovery scans re-publish queued, waiting, and
expired work. Claim tokens and leases fence stale workers, and duplicate
notifications are safe.

The project-scoped API provides policy creation/list/detail, run creation/list/
detail, metric results, paginated case results, and case detail under
`/v1/regression-policies` and `/v1/regression-runs`. It does not expose CI,
deployment, pull-request, or merge outcomes; those are M11 concerns.

## Controlled example

A two-case controlled fixture has a baseline success rate of 50% and p95
latency of 800 ms, while the candidate succeeds on both cases but has p95
latency of 1,500 ms. The report therefore shows:

```text
replay.execution_success_rate: improved (+0.5; baseline-zero relative delta is null)
trace.duration_ms.p95:         regressed (+700 ms / +87.5%)
candidate latency limit:        violated (maximum 1,000 ms)
universal winner:               none
```

The paired case table retains candidate/baseline execution status, introduced
and resolved finding keys, and deep-links to both generated traces.
