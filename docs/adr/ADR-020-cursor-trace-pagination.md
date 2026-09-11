# ADR-020: Cursor-Based Trace Pagination

## Status

Accepted for M4.

## Context

Trace enumeration must be bounded and stable when multiple traces share the
same timestamp. Offset pagination would be less robust under insertion.

## Decision

List queries use opaque HMAC-signed cursors with the fixed ordering
`started_at DESC, trace_id DESC`. Cursors are project-bound, validated, and
contain only the last ordering key.

## Consequences

Sequential traversal does not duplicate or skip rows in a stable dataset and
does not expose SQL or secrets. Arbitrary sorting and full-text search are not
part of M4.
