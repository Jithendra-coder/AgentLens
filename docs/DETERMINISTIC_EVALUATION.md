# Deterministic Evaluation

M6 evaluates stored M1 traces with trusted local handlers. An evaluator makes
no network calls, uses no randomness, imports no model/provider SDK, and does
not mutate the source trace. The worker stores the normalized configuration and
the canonical trace fingerprint alongside the derived result.

## Result contract

The result schema is `agentlens-evaluation-result-v1`; it is distinct from
`agentlens-trace-v1` and `agentlens-evaluation-job-v1`. A result contains:

- identity: `result_id`, `project_id`, `trace_id`, and `job_id`;
- evaluator provenance: evaluation type, evaluator name, and evaluator
  version;
- status: `completed`, `not_applicable`, or `invalid_input`;
- UTC `created_at`, normalized `config`, `config_fingerprint`, and
  `trace_fingerprint`;
- JSON-safe `metrics`, structured `findings`, and JSON-safe `evidence`.

The Python result model is frozen and recursively immutable. PostgreSQL is the
authoritative append-only store. `job_id` is unique. Result insertion, attempt
success, job success, and lease clearing happen in one transaction guarded by
the current claim token. A stale worker cannot insert a result or complete a
new worker's job.

## Latency summary

`latency_summary` reports:

- `trace_duration_ms`: ended trace duration, or `null` for an unfinished trace;
- `completed_span_count` and `unfinished_span_count`;
- `span_duration_sum_ms` and `longest_span_duration_ms` over ended spans;
- `span_duration_by_type_ms` and `span_count_by_type`.

Span durations are calculated independently and then summed. Overlapping spans
therefore count their full durations; the sum is not wall-clock utilization.
No p95, p99, percentile aggregation, or cost inference is included.

## Usage summary

`usage_summary` reports `spans_with_usage` and independently sums every usage
field present in the trace: input, output, total, cached, and reasoning tokens.
If a field is never reported, its metric is `null`. A reported zero remains
zero. M6 does not estimate missing tokens or calculate price/cost.

## Reliability summary

`reliability_summary` reports counts for `OK`, `ERROR`, and `UNSET` spans,
terminal count, and:

```text
error_rate = error_span_count / (ok_span_count + error_span_count)
```

The denominator excludes `UNSET`. It also reports observed `trace_error`,
`error_type_counts`, tool span/terminal/OK/error counts, and:

```text
tool_success_rate = tool_ok_count / tool_terminal_count
```

An empty terminal denominator yields `null`, not zero. M6 does not invent
error types when the source trace has no `ErrorInfo`.

## Retrieval ranking

`retrieval_ranking` requires explicit JSON configuration:

```json
{
  "span_id": "retrieval-span-uuid",
  "relevant_document_ids": ["doc-a", "doc-b"],
  "k_values": [1, 3, 5]
}
```

The selected span must have type `retrieval` and output shaped as:

```json
{"documents": [{"id": "doc-x"}, {"id": "doc-a"}]}
```

M6 normalizes K values and relevant IDs by sorting and deduplicating them. An
empty relevant set, malformed K, missing span, wrong span type, malformed
documents, or duplicate retrieved IDs produces `invalid_input` with a finding;
it is terminal and is not retried by the worker.

For each normalized K, with `hits` equal to relevant documents in the first K
retrieved positions:

```text
Precision@K = hits / K
Recall@K    = hits / |relevant|
HitRate@K  = 1 if hits > 0 else 0
```

Precision uses K even if the retriever returns fewer than K documents. MRR is
the reciprocal rank of the first relevant retrieved document, or zero when no
relevant document is retrieved. NDCG@K uses binary relevance and the standard
log2 discount against the ideal ranking of the available relevant documents.

## API and failure behavior

Production job creation rejects unsupported evaluation types before creating a
job. `noop` remains available for runtime compatibility and intentionally has
no result. Results are available through:

- `GET /v1/evaluation-results/{result_id}`;
- `GET /v1/traces/{trace_id}/evaluation-results`;
- `GET /v1/evaluation-jobs/{job_id}`, which includes `result_id` when present.

All result reads are project-scoped. Redis is only a wakeup transport;
PostgreSQL remains authoritative. A result-storage failure is retryable, while
an evaluator's explicit `invalid_input` payload is persisted as a successful
terminal evaluation result.

M6 deliberately stops before semantic answer quality, groundedness judgment,
provider/model evaluation, cost, cross-trace percentiles, dashboards,
datasets/replay, regression comparison, and universal composite scores.
