# ADR-024: Trusted Handler Registry

Status: Accepted for M5.

## Decision

Jobs select a handler by an explicit bounded key. M5 registers only `noop`.
There is no dynamic import, `eval`, `exec`, pickle/deserialization, arbitrary
callable payload, or subprocess execution path.

## Consequences

The runtime is safe to expose as an asynchronous boundary and unknown keys
dead-letter deterministically. Real evaluator implementations require a later
reviewed registry and separate result/provenance contracts.
