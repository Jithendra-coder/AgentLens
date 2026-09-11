# ADR-030 — Structured Model-Assisted Evaluation Provenance

Status: Accepted

## Context

Model-assisted results are not reproducible from a model name alone and must
remain distinguishable from deterministic evidence.

## Decision

Every successful model-assisted result records a dedicated invocation with
profile, provider, model, adapter version, prompt version, parameters, request
and response fingerprints, timestamps, status, and optional token usage. Raw
judge prompts, raw responses, secrets, and hidden reasoning are not stored.

## Consequences

Result provenance survives model and prompt changes without claiming identical
future output. Judge usage remains separate from observed application usage,
and the invocation plus result are committed atomically with job completion.
