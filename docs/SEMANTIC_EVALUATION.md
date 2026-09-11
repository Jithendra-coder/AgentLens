# M7 Semantic Evaluation

M7 evaluates RAG, tool use, and complete agent tasks downstream of the
canonical observed `Trace`. It produces the same immutable
`agentlens-evaluation-result-v1` shape as M6 and never writes judge activity
back into the observed trace.

## Modes

- `deterministic`: exact evidence only; no judge invocation is present.
- `model_assisted`: a bounded structured request is evaluated by a configured
  `SemanticJudge`; the result contains safe invocation provenance.
- `hybrid`: one evaluation combines deterministic criteria and model-assisted
  criteria. Each agent criterion records its own mechanism.

These modes describe how a result was produced. They do not imply that a
model-assisted result is mathematically deterministic.

## Semantic judge boundary

`agentlens.evaluation.judges.SemanticJudge` is the provider-independent
protocol. It accepts a `JudgeRequest` and returns a strict `JudgeResponse`.
Core evaluators do not import provider SDK objects. The M7 default has no live
provider adapter; an operator may inject an adapter implementing the protocol
when deploying a trusted judge profile. Evaluation requests cannot provide an
endpoint, URL, credential, or provider object.

Requests contain only the selected evaluation context: question, bounded
documents, answer, claims, tool calls, task, or criteria. They include an
immutable system instruction stating that trace content is untrusted evidence,
not instructions. Judges have no tool, web, shell, filesystem, database, MCP,
or agent access. Bounds include maximum documents, per-document characters,
total judge characters, tool calls, and answer characters. Truncation is
recorded in the request metadata and as a result finding.

Responses allow only a label, optional score in `[0, 1]`, document evidence IDs,
criterion results, token usage, and a concise rationale. Unknown fields,
malformed arrays, invalid scores, and long rationale are rejected. Hidden
chain-of-thought is neither requested nor persisted. Raw request and response
content is not persisted.

## Provenance and reproducibility

Each successful model-assisted result stores a separate invocation record with
provider, model, adapter version, judge profile, prompt version, parameters,
request fingerprint, response fingerprint, timestamps, status, and optional
token usage. Prompt versions are evaluator-owned constants in
`evaluation/prompts.py`. The fingerprints provide reproducible configuration
identity; they do not guarantee identical output if external model
infrastructure changes. Application span usage and judge token usage remain
separate.

## RAG evaluators

Semantic RAG jobs must name `retrieval_span_id` and `answer_span_id`; M7 never
guesses among multiple spans. Retrieval output must contain normalized
documents with unique string IDs. Semantic evaluators additionally require
bounded textual `content`.

`rag_context_relevance` asks for a per-document label, normally `relevant` or
`irrelevant`, and reports `documents_evaluated`, relevant/irrelevant counts,
and `mean_context_relevance`. Findings identify document IDs.

`rag_groundedness` accepts explicit bounded answer claims with `id` and `text`.
It keeps support separate from retrieval relevance and recognizes
`supported`, `partially_supported`, and `unsupported`. Findings identify the
claim ID and bounded supporting document IDs; `unsupported_answer_claim` is an
evidence finding, not a claim of perfect hallucination detection.

`rag_citation_integrity` is deterministic. It validates citation IDs against
retrieved IDs, reports unknown and duplicate citations, and can report missing
citations when `require_citations` is enabled. Semantic citation support is
not implemented in M7 and is intentionally separate from citation validity.

## Tool evaluators

`tool_selection` accepts `expected_tools`, optional `allowed_extra_tools`, and
optional `order_sensitive`. It reports expected, matched, missing, unexpected,
duplicate, and observed counts; sequence mismatch is reported only when order
is explicitly enabled. `tool_arguments` supports `subset` and `exact` matching
against observed tool input. `tool_efficiency` reports observed, necessary,
unnecessary, and efficiency-rate metrics using explicit expected tools.

These evaluators inspect observed tool spans only. They never execute tools.
Argument findings identify tool and field names without copying raw argument
values into evidence.

## Agent task evaluators

`agent_task_success` and `agent_criteria` require an explicit `task` and a
non-empty list of unique criteria. Criteria may be `required` (default true) or
optional, and may be deterministic or `model_assisted`.

Supported deterministic criteria are expected tool called, error absent,
required output field, JSON field equality, and output contains. Other criteria
are sent to the judge with the task and criterion descriptions. Results contain
criterion ID, status, score, required flag, evaluation mode, evidence, and
concise rationale where semantic. `task_success` is true exactly when every
required criterion passes; optional failures do not fail the task. This is the
documented `all_required_criteria_pass` aggregation, not a universal score.

## Failure and privacy behavior

Missing spans, empty criteria, malformed normalized structures, unsupported
criterion types, and tenant endpoint configuration produce terminal
`invalid_input` or terminal invalid configuration. Judge timeouts, rate limits,
and availability failures use M5 bounded retry behavior. Authentication and
configuration failures are non-retryable. Malformed structured responses are
terminal `invalid_judge_response`. A semantic-provider outage does not affect
trace ingestion or deterministic evaluation.

Result and invocation reads remain project-scoped and preserve the existing
404 privacy convention. M7 does not implement a semantic cache, live-provider
smoke requirement, dataset/replay workflow, model comparison, dashboard, CI
quality gate, or semantic evaluation cost calculation.
