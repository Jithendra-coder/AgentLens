"""Custom Evaluator authoring SDK for user-defined evaluation logic ."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentlens.evaluation.plugins.models import (
    CustomEvaluationOutput,
    EvaluatorContext,
    SpanContextView,
)


class CustomEvaluator:
    """Base class for authoring object-oriented custom evaluators in AgentLens."""

    def evaluate(
        self,
        context: EvaluatorContext,
        parameters: dict[str, Any],
    ) -> CustomEvaluationOutput:
        """Run custom evaluation logic on the provided EvaluatorContext."""
        raise NotImplementedError("Custom evaluators must implement the evaluate method.")


def custom_evaluator(
    name: str,
    version: str = "1.0.0",
    evaluator_type: str = "deterministic",
) -> Callable[
    [Callable[[EvaluatorContext, dict[str, Any]], CustomEvaluationOutput]],
    Callable[[EvaluatorContext, dict[str, Any]], CustomEvaluationOutput],
]:
    """Decorator to mark a Python function as a valid AgentLens custom evaluator."""

    def decorator(
        fn: Callable[[EvaluatorContext, dict[str, Any]], CustomEvaluationOutput],
    ) -> Callable[[EvaluatorContext, dict[str, Any]], CustomEvaluationOutput]:
        setattr(fn, "_is_agentlens_evaluator", True)  # noqa: B010
        setattr(fn, "_evaluator_name", name)  # noqa: B010
        setattr(fn, "_evaluator_version", version)  # noqa: B010
        setattr(fn, "_evaluator_type", evaluator_type)  # noqa: B010
        return fn

    return decorator


__all__ = [
    "CustomEvaluationOutput",
    "CustomEvaluator",
    "EvaluatorContext",
    "SpanContextView",
    "custom_evaluator",
]
