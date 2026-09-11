# Contributing to AgentLens

Keep changes inside the active milestone. Read
[docs/00_READ_FIRST.md](docs/00_READ_FIRST.md) before editing architecture or
domain behavior.

## Development loop

1. Update the relevant contract or ADR before changing a project-wide rule.
2. Implement the smallest deterministic change that satisfies the contract.
3. Add or update a focused test.
4. Run the local verification commands.
5. Record deviations and evidence; do not invent benchmark results.

## Current milestone boundary

M2 must not add providers, databases, queues, API servers, dashboards,
evaluators, replay engines, or network transport. The SDK remains explicit,
local, provider-independent, and built on the M1 domain.
