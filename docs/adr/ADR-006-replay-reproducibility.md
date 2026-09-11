# ADR-006 - Replay Reproducibility

Status: Accepted

## Context

Replays may preserve inputs while external models, tools, data, or environment
state changes. Calling every replay exact would overstate what the system can
reproduce.

## Decision

Future replay records preserve input, agent version, prompt version, model
configuration, retriever configuration, tool definitions, dataset version,
evaluator versions, and relevant environment metadata. They explicitly label
the replay as:

- **Exact Replay:** conditions are sufficiently preserved to reproduce the
  original configuration.
- **Controlled Replay:** inputs are preserved but a deliberately changed
  candidate configuration is used.
- **Best-Effort Replay:** external dependencies or state prevent exact
  recreation.

## Consequences

Replay reports can explain reproducibility limits and compare like with like.
Capture requirements and environment metadata add operational work.

## Alternatives rejected

Treating every preserved input run as an exact replay was rejected because it
conceals changed dependencies and invalidates comparisons.
