# ADR-010 - Contextvars for Instrumentation Context

Status: Accepted

## Context

Nested synchronous spans and concurrent asyncio tasks need current trace/span
access without unsafe process-global mutable state.

## Decision

M2 stores current trace and span runtime handles in Python `contextvars`.
Context-manager tokens restore prior values on normal and exceptional exit.
Explicit nested root traces are independent contexts and restore their outer
context when finished.

## Consequences

Sync nesting and asyncio task isolation work with standard-library semantics.
Contexts are not automatically propagated into manually created OS threads;
callers must explicitly copy context if they need that behavior later.

## Alternatives rejected

Module-level current-trace variables were rejected because concurrent tasks
would cross-link observations.
