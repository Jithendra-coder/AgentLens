# ADR-023: Bounded Retry and Dead-Letter States

Status: Accepted for M5.

## Decision

Retryable handler errors and timeouts use durable `available_at` backoff and a
bounded `max_attempts` default of three. Non-retryable errors and exhausted
attempts become terminal `dead_letter` jobs. Errors are represented by safe,
bounded codes and messages only.

## Consequences

Workers do not spin on immediate failures, restarts preserve retry timing, and
operators can distinguish terminal failures from retryable delay without
exposing exception payloads or secrets.
