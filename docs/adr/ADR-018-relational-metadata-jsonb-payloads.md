# ADR-018: Relational Metadata with JSONB Payloads

## Status

Accepted for M4.

## Context

Trace metadata must support useful filters, while arbitrary JSON-safe inputs,
outputs, attributes, usage, and error details must retain canonical fidelity.

## Decision

Persist searchable identity, names, status, timestamps, parent IDs, types,
fingerprints, and counts as relational columns. Persist flexible captured
payloads as PostgreSQL JSONB. Preserve span/event positions for exact ordering.

## Consequences

The schema supports M4 queries without exploding every arbitrary attribute into
columns. Arbitrary attribute search and full-text search are deferred.
