# Evaluation Governance

Every future evaluation must answer:

1. What was evaluated?
2. Which evaluator ran?
3. Which evaluator version?
4. Which configuration?
5. Against what ground truth, if applicable?
6. When was it evaluated?
7. How was the result produced?

## M6 result and runtime boundary

M5 implements the execution boundary. Its durable job ledger stores a
versioned trusted handler key, JSON-safe configuration, project/trace
reference, operational state, attempts, bounded safe error metadata, and
lease/retry timing. M6 adds the explicit deterministic handlers and stores
their results in the separate `agentlens-evaluation-result-v1` schema.

Every result is immutable at the model boundary and append-only in PostgreSQL.
It contains `result_id`, result schema version, project/trace/job identity,
evaluation type, evaluator name/version, `completed`, `not_applicable`, or
`invalid_input` status, UTC creation time, normalized config, config
fingerprint, trace fingerprint, metrics, findings, and evidence. The unique
job reference means one successful result-bearing job has at most one result.
`invalid_input` is a terminal evaluation result, not a retryable worker error.

Jobs are downstream of trace ingestion. A PostgreSQL row is written before a
Redis wakeup is attempted; Redis carries only `{job_id}` and is not the source
of truth. A Redis outage leaves the job durably queued and does not make trace
ingestion unavailable. See `docs/EVALUATION_RUNTIME.md` for the runtime
contract.

## Required provenance

Results retain evaluator name, evaluator version, normalized configuration,
configuration fingerprint, evaluation timestamp, trace fingerprint, result,
and evidence/reason. M6 does not store provider, model, prompt, embedding, or
judge provenance because it makes no provider/model calls.

## Benchmark evidence

Future benchmark results must record dataset name and version, sample count,
metric definition, random seed where relevant, hardware where relevant,
software version/configuration, and measurement methodology. A bare claim such
as `95% accuracy` is not meaningful without this context.

## Order of work

Deterministic signals come first. M6 implements latency summaries, independently
reported usage fields, reliability/status and tool counts, and explicit-ground-
truth retrieval Precision@K, Recall@K, Hit Rate@K, MRR, and NDCG@K. Probabilistic
and model-based evaluators are later concerns.

## M6 metric rules

- Latency reports trace duration only when the trace has ended; unfinished
  spans are counted separately and excluded from completed-duration sums.
  Overlap is preserved: span durations are summed, not merged into wall time.
  No p95/p99 or cross-trace percentile is claimed.
- Usage fields are summed independently across spans that report each field.
  Missing is `null`; an observed zero remains `0`. M6 does not infer cost or
  pricing.
- Reliability counts `OK`, `ERROR`, and `UNSET` separately. Error rate is
  `ERROR / (OK + ERROR)`; `UNSET` is excluded. Tool success rate uses terminal
  tool spans only. Trace error is the observed trace status.
- Retrieval requires `span_id`, non-empty relevant document IDs, and positive
  `k_values`. The selected span must be type `retrieval` and expose
  `output.documents` as objects with string `id` fields. Precision uses K as
  denominator even when fewer than K documents are returned. Empty ground
  truth and malformed input yield `invalid_input`, not a retry.

Configuration is normalized deterministically: retrieval K values and relevant
IDs are sorted and deduplicated before execution and fingerprinting. The exact
normalized configuration is stored with the result.

## M7 semantic evaluation rules

M7 keeps deterministic evidence first. Citation existence, expected tools,
tool arguments, order-sensitive sequences, and simple agent criteria are
programmatic checks. RAG context relevance and groundedness, and agent
criteria that require interpretation, use the provider-independent
`SemanticJudge` boundary. A result records one of `deterministic`,
`model_assisted`, or `hybrid`; there is no universal quality score.

Every model-assisted result records the selected judge profile, provider,
model, adapter version, prompt version, parameters, request fingerprint,
response fingerprint, timestamps, and optional token usage. The result table
and its dedicated `evaluation_judge_invocations` rows are immutable and are
committed atomically with the attempt and job completion. Complete raw judge
requests, raw responses, secrets, and hidden reasoning are not persisted.

Semantic requests use bounded, minimal structured evidence. Retrieved text,
tool output, questions, and answers are data, not instructions; the fixed
judge boundary explicitly prohibits following trace instructions, tools, URLs,
configuration disclosure, or criteria changes. Tenant jobs may select a
trusted judge profile, but cannot supply provider endpoints or credentials.
Input validation is terminal `invalid_input`; provider timeouts, rate limits,
and availability failures use M5 retry semantics; malformed structured
responses are terminal evaluator failures.

## M10 comparison provenance

Regression reports reuse these immutable result records. Evaluation-backed
measurements are comparable only when evaluation type, evaluator name/version,
normalized configuration, and semantic judge provider/model/adapter, prompt
version, and parameters match. An evaluator-owned trace-local identifier may
be excluded only through an explicit normalization rule. Otherwise the report
marks the metric `incompatible`; it never silently combines methodologies.

Groundedness means support of explicit bounded answer claims by retrieved
document IDs; it is not a perfect hallucination detector. Model-assisted
results are reproducible in configuration and provenance, not guaranteed to
produce identical output across provider infrastructure changes.
