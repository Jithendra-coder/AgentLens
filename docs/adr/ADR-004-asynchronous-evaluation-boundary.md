# ADR-004 - Asynchronous Evaluation Boundary

Status: Accepted

## Context

Evaluation can be slower, less reliable, or independently scalable than trace
ingestion. A failed evaluator must not discard valid execution evidence.

## Decision

Ingestion and evaluation are separate reliability boundaries. Evaluation is
downstream work and may be queued and retried after ingestion succeeds.

## Consequences

The system needs durable references and explicit retry/failure semantics later.
Users may see observations before evaluation results are available.

## Alternatives rejected

Blocking ingestion on synchronous evaluation was rejected because it couples
data capture to an optional derived process.
