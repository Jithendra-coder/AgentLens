# ADR-001 - Provider-Independent Core

Status: Accepted

## Context

AgentLens must observe applications using many providers and frameworks. A
canonical core coupled to one vendor would make integrations, portability, and
long-term contracts fragile.

## Decision

Core and domain code remain provider-independent. Provider and framework data
must pass through adapters into AgentLens canonical representations.

## Consequences

Adapters carry integration-specific knowledge. Core contracts are more stable
and testable, but integrations require explicit translation work.

## Alternatives rejected

Using a provider SDK or agent framework as the canonical internal model was
rejected because it reverses the dependency direction and creates lock-in.
