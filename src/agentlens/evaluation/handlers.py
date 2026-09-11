"""Explicit trusted evaluation handler registry.

Registers reviewed deterministic handlers and the provider-independent
semantic boundary. Job payloads contain
a handler key, never import paths, callables, serialized code, or provider
credentials.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from agentlens.domain import Trace
from agentlens.domain.types import JSONValue

from .errors import UnknownHandlerError
from .evaluators import (
    LatencyEvaluator,
    ReliabilityEvaluator,
    RetrievalRankingEvaluator,
    UsageEvaluator,
)
from .judges import SemanticJudge
from .results import EvaluationResultPayload
from .semantic_evaluators import (
    AgentTaskEvaluator,
    RagCitationIntegrityEvaluator,
    RagContextRelevanceEvaluator,
    RagGroundednessEvaluator,
    ToolArgumentsEvaluator,
    ToolEfficiencyEvaluator,
    ToolSelectionEvaluator,
)


class EvaluationHandler(Protocol):
    evaluation_type: str
    evaluator_name: str
    evaluator_version: str

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        """Return the exact normalized configuration used for evaluation."""

    def evaluate(
        self, trace: Trace, config: Mapping[str, JSONValue]
    ) -> EvaluationResultPayload | None:
        """Run one trusted deterministic handler."""


class NoopHandler:
    evaluation_type = "noop"
    evaluator_name = "agentlens.noop"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return cast(Mapping[str, JSONValue], dict(config))

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> None:
        del trace, config


class HandlerRegistry:
    """Small explicit key-to-handler registry; no dynamic loading is supported."""

    def __init__(
        self,
        handlers: Mapping[str, EvaluationHandler] | None = None,
        *,
        semantic_judge: SemanticJudge | None = None,
    ) -> None:
        configured: dict[str, EvaluationHandler]
        if handlers is not None:
            configured = dict(handlers)
        else:
            configured = {
                "noop": NoopHandler(),
                "latency_summary": LatencyEvaluator(),
                "usage_summary": UsageEvaluator(),
                "reliability_summary": ReliabilityEvaluator(),
                "retrieval_ranking": RetrievalRankingEvaluator(),
                "rag_context_relevance": RagContextRelevanceEvaluator(semantic_judge),
                "rag_groundedness": RagGroundednessEvaluator(semantic_judge),
                "rag_citation_integrity": RagCitationIntegrityEvaluator(),
                "tool_selection": ToolSelectionEvaluator(),
                "tool_arguments": ToolArgumentsEvaluator(),
                "tool_efficiency": ToolEfficiencyEvaluator(),
                "agent_task_success": AgentTaskEvaluator().with_judge(semantic_judge),
                "agent_criteria": AgentTaskEvaluator("agent_criteria").with_judge(semantic_judge),
            }
        if not configured or any(not isinstance(key, str) or not key for key in configured):
            raise ValueError("handlers must have non-empty string keys")
        self._handlers = configured

    def get(self, evaluation_type: str) -> EvaluationHandler:
        try:
            return self._handlers[evaluation_type]
        except KeyError:
            raise UnknownHandlerError("unknown_handler") from None

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def public_types(self) -> tuple[str, ...]:
        return tuple(sorted(key for key in self._handlers if key != "noop"))


__all__ = ["EvaluationHandler", "HandlerRegistry", "NoopHandler"]
