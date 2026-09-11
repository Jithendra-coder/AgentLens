# ADR-051 — Immutable Auditable Gate Decisions

## Status

Accepted for M11.

## Decision

Completed decisions are append-only PostgreSQL records. Each retains the
dataset and replay provenance, M10 report fingerprint/schema/comparison engine,
gate policy version/fingerprint, rule results, and quality-gate engine version.
Idempotent creation returns the original decision for the same project/key and
request.
