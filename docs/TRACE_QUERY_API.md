# M4 Trace Query API

M4 adds project-scoped read endpoints backed by the PostgreSQL repository.
Every query requires the same Bearer API key as ingestion. The key's
`project_id` is always applied by the repository; callers cannot query or
enumerate another project.

## `GET /v1/traces/{trace_id}`

Returns the complete canonical `agentlens-trace-v1` JSON document. The
repository reconstructs it through the M1 domain model, so the SDK, ingestion,
storage, and retrieval formats remain the same.

If the trace does not exist in the authenticated project, the endpoint returns
`404 trace_not_found`, including when the ID exists in another project. This
avoids cross-project existence disclosure.

## `GET /v1/traces`

Returns bounded summaries rather than full captured payloads:

```json
{
  "items": [
    {
      "trace_id": "...",
      "name": "request",
      "session_id": "session-1",
      "status": "ok",
      "started_at": "2025-01-01T12:00:00+00:00",
      "ended_at": "2025-01-01T12:00:02+00:00",
      "duration": 2.0,
      "span_count": 2,
      "event_count": 1
    }
  ],
  "next_cursor": "..."
}
```

An empty result is `200` with `items: []` and `next_cursor: null`.

Supported exact filters:

| Parameter | Semantics |
| --- | --- |
| `started_from` | Inclusive UTC-aware ISO-8601 lower bound |
| `started_to` | Inclusive UTC-aware ISO-8601 upper bound |
| `status` | Canonical M1 value: `unset`, `ok`, or `error` |
| `name` | Exact trace name |
| `session_id` | Exact session ID |
| `span_type` | Traces containing at least one matching span |

Pagination uses `limit` and an opaque signed `cursor`. The default limit is
50 and the maximum is 200. Results are ordered newest first by
`started_at DESC, trace_id DESC`; the trace ID is the deterministic tie-breaker.
The cursor is project-bound and does not contain credentials or SQL.

Malformed filters and cursors return `400 invalid_query` or `400
invalid_cursor`. Database failures return `503 query_unavailable` with the
normal request ID error envelope.
