# Canonical Domain Model

## M1 status

M1 implements the provider-independent observed execution representation. The
public surface is available from `agentlens.domain`:

```python
from agentlens.domain import ErrorInfo, Event, Span, Trace, Usage
```

The model does not capture executions, transmit them, store them, evaluate
them, or replay them. Those are later boundaries.

## Trace

`Trace` represents one logical execution and contains a schema version, opaque
UUID identity, project/session metadata, name, timezone-aware start and
optional end timestamps, status, spans, events, and JSON-safe attributes.
Traces may be unfinished, contain zero spans, contain events only, and contain
multiple root spans.

## Span

`Span` represents a timed operation with opaque span and trace IDs, an optional
parent, extensible provider-neutral `span_type`, name, start/end timestamps,
status, optional input/output payloads, attributes, `Usage`, and `ErrorInfo`.
Known span type vocabulary includes agent, llm, retrieval, embedding, tool,
mcp, http, workflow, and custom; additional non-empty strings are accepted for
forward compatibility.

## Event

`Event` represents a point-in-time occurrence with event and trace IDs, an
optional span reference, name, timestamp, and attributes. A referenced span
must exist in the containing trace.

## Usage and errors

`Usage` stores optional non-negative input, output, total, cached, and
reasoning token counts without assuming provider-specific arithmetic.
`ErrorInfo` stores observed error type, message, optional code and traceback,
and JSON-safe attributes. Error metadata is not an evaluation finding.

## Invariants and time

IDs normalize to `UUID` objects. All timestamps must be timezone-aware and are
normalized to UTC. End times cannot precede start times, but missing end times
remain valid. Whole-trace validation rejects duplicate IDs, cross-trace
objects, missing parents, self-parenting, cycles, and invalid event references.
Parent/child timestamp containment is intentionally not enforced because
distributed and partial telemetry can violate that simplistic assumption.

## Mutation safety

Domain objects are frozen dataclasses. Payload mappings become read-only
mapping proxies and payload lists become tuples internally. Constructors do not
retain caller-owned nested references, and `to_dict()` returns a fresh ordinary
JSON-compatible copy.

## Serialization

`Trace.to_dict()` / `Trace.from_dict(...)` and `Trace.to_json()` /
`Trace.from_json(...)` provide deterministic JSON-only round trips. The only
supported schema is `agentlens-trace-v1`; unknown schema versions fail
explicitly rather than being treated as v1.
