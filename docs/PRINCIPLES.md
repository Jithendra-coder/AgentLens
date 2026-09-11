# Engineering Principles

## Provider-independent core

Core and domain code must not depend on OpenAI, Anthropic, Google/Gemini,
LangChain, LlamaIndex, model-provider SDKs, agent-framework SDKs, or MCP vendor
implementations. External data flows through adapters into AgentLens canonical
representations:

```text
Provider/framework data -> adapter -> AgentLens canonical representation
```

The reverse dependency is prohibited.

## Observed data versus derived evaluation

Observed execution history includes prompts, outputs, retrieved documents,
tool activity, timings, and errors. Evaluation results are later
interpretations. Evaluator changes must never mutate historical observations.

## Versioned evaluators

Every evaluation result must preserve evaluator name and version, configuration
version, evaluation time, evaluated input/reference, result, score, and
evidence/reason. Model-based judges must additionally preserve judge provider,
model, prompt version, and parameters when applicable.

## Determinism before probability

Build latency, duration, token, failure, tool, and retrieval-grounded metrics
before embedding-based judgment, learned classifiers, LLM judges, hallucination
estimators, or learned anomaly detection.

## Ingestion is independent of evaluation

Evaluation is downstream work. Evaluation failure must never make valid trace
ingestion fail. M5 persists a queued job before attempting a Redis wakeup, so
Redis/worker failure degrades evaluation dispatch without invalidating trace
storage.

## Explicit replay semantics

Replay must state whether it is exact, controlled, or best-effort. It must not
claim perfect reproducibility when external state prevents it.

## Evidence and safety

Sensitive data is the default assumption for trace payloads. Security,
retention, tenant isolation, redaction, and auditability are architectural
obligations, not optional polish.

## Engineering defaults

Internal timestamps are UTC-oriented, serialization happens at explicit
boundaries, and asynchronous execution is deferred until a concrete reliability
need exists. Avoid uncontrolled global mutable state and speculative
abstractions.
