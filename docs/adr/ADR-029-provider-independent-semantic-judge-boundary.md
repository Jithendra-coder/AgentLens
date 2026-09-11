# ADR-029 — Provider-Independent Semantic Judge Boundary

Status: Accepted

## Context

M7 needs semantic interpretation for selected RAG and agent criteria, but the
AgentLens core must remain independent of any model-provider SDK or network
endpoint.

## Decision

Define `SemanticJudge` as a small protocol accepting `JudgeRequest` and
returning strict `JudgeResponse` data. Evaluators depend on this protocol;
operator configuration injects any trusted provider adapter. Tenant job
configuration may select a profile but may not supply an endpoint or
credential.

## Consequences

The core remains provider-independent and deterministic evaluators have no
provider dependency. A live adapter is optional deployment work, and model
availability is isolated to semantic jobs.
