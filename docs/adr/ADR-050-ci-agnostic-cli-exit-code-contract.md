# ADR-050 — CI-Agnostic CLI Exit-Code Contract

## Status

Accepted for M11.

## Decision

The API-driven AgentLens CLI is the CI boundary. It returns 0 for passed, 1
for failed, 2 for indeterminate, and 3 for operational/configuration errors.
Provider-specific CI SDKs and integrations are not part of the gate engine.
