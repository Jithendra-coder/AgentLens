# ADR-007 - Immutable Canonical Observations

Status: Accepted

## Context

Observed execution data is historical evidence. Caller-owned nested mappings
and lists must not remain live references that can silently rewrite an observed
trace after construction.

## Decision

M1 uses frozen dataclasses with recursively immutable payload containers:
mapping proxies for objects and tuples for arrays. Constructors validate and
copy payloads. Serialization returns fresh ordinary JSON-compatible structures.

## Consequences

Domain objects cannot be accidentally mutated through ordinary references, and
round trips are reproducible. Callers must use a new object rather than mutate
an existing observation. Serialization is the explicit mutable boundary.

## Alternatives rejected

Shallow copies were rejected because nested dictionaries and lists would still
leak mutation. Python pickle was rejected because it is executable and not a
stable JSON contract.
