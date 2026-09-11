# AgentLens Python SDK

## M2/M3 status

The M2 SDK instruments explicit local application code and produces immutable
M1 canonical `Trace` objects. M3 adds the optional `HttpTraceExporter`, which
sends one finalized canonical JSON snapshot to `/v1/traces` with a finite
timeout and Bearer authentication. Export failures remain isolated by the M2
runtime and become diagnostics rather than application failures.

```python
from agentlens import AgentLens, InMemoryTraceExporter

exporter = InMemoryTraceExporter()
client = AgentLens(project_id="support-agent", exporter=exporter)

with client.trace("answer-question") as trace:
    with trace.span("retrieve", span_type="retrieval") as span:
        span.set_input({"query": "hello"})
        span.set_output({"documents": []})
        span.add_event("retrieval-complete")

finished = exporter.traces[0]
```

## Context helpers

`agentlens.current_trace()` and `agentlens.current_span()` return the active
runtime handles or `None` outside a context. `contextvars` preserves nested
sync contexts and isolates asyncio tasks. Manually created OS threads are not
automatically propagated.

An explicit nested `client.trace(...)` is a separate root. Exiting it restores
the outer trace and span context.

## Lifecycle

Trace and span handles are created, entered, and finished once. After exit,
`trace.finished_trace` and `span.finished_span` expose immutable M1 results.
Closed handles reject further capture. A normally sampled trace exports once at
root exit; an unsampled trace exports nothing and returns `None`.

Open spans encountered during defensive root finalization remain unfinished
rather than being fabricated as successful.

## Capture and privacy

Capture is explicit. Attributes, input/output, usage, and events are validated
against the M1 JSON-safe boundary and copied before storage. No function
arguments, locals, headers, environment variables, prompts, or outputs are
captured automatically.

The optional redactor receives `(value, field=..., context=...)` before a value
is stored. Redactor failures record an SDK diagnostic and drop the trace; the
original unredacted value is never exported. Trace-level exceptions become a
redacted `error` event with `Status.ERROR`; span-level exceptions populate M1
`ErrorInfo`.

## Sampling and export

Sampling is decided once at root creation. `AlwaysOnSampler` and
`AlwaysOffSampler` are provided; sampled roots retain all nested instrumentation
and unsampled roots export no canonical trace.

`TraceExporter` is a synchronous local protocol. `InMemoryTraceExporter` is
provided for tests and examples. Export failures are isolated by default,
recorded in `client.diagnostics`, and do not change application behavior.
`flush()` and `shutdown()` call optional local exporter hooks; no background
threads, queues, or network calls are created.
