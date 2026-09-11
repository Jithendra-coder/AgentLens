# ADR-048 — Independent Blocking and Advisory Gate Rules

## Status

Accepted for M11.

## Decision

Each finite gate rule evaluates independently. Blocking failures determine the
release status; advisory failures are retained as warnings and cannot fail the
gate. M11 has no weighted score or compensating trade-off rule.
