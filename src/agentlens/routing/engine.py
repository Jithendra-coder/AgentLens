"""Adaptive quality and cost-aware model routing engine ."""

from __future__ import annotations

from collections.abc import Sequence

from agentlens.cost.pricing import PricingRegistry
from agentlens.routing.classifier import TaskClassifier
from agentlens.routing.models import RouteRequest, RouteResult, RoutingRule


class AdaptiveRouter:
    """Selects the optimal LLM provider and model balancing quality, latency, and cost."""

    def __init__(self, pricing_registry: PricingRegistry | None = None) -> None:
        self._pricing = pricing_registry or PricingRegistry()

    def route(
        self,
        request: RouteRequest,
        rules: Sequence[RoutingRule],
    ) -> RouteResult:
        """Evaluate prompt against active routing rules and return model recommendation."""
        complexity = TaskClassifier.classify(request.prompt)

        # 1. Find matching rule by task_type, fallback to "general" rule or default
        matched_rule = next(
            (r for r in rules if r.is_active and r.task_type == complexity.task_type),
            None,
        )
        if matched_rule is None:
            matched_rule = next(
                (r for r in rules if r.is_active and r.task_type == "general"),
                None,
            )

        tier_candidates = (
            matched_rule.tier_priority
            if matched_rule
            else ("gpt-4o-mini", "claude-3-5-haiku", "gpt-4o", "claude-3-5-sonnet")
        )
        fallback_model = matched_rule.fallback_model if matched_rule else "gpt-4o"

        # 2. Decision Logic
        # If task is complex (score >= 0.5) or strict min quality requested (> 0.85), use top tier
        if complexity.complexity_score >= 0.5 or (request.min_quality_score or 0.0) > 0.85:
            # Pick strongest model from candidates
            selected_model = next(
                (
                    m
                    for m in reversed(tier_candidates)
                    if "mini" not in m and "haiku" not in m and "flash" not in m
                ),
                fallback_model,
            )
            reason = (
                f"Escalated to frontier model '{selected_model}' due to high complexity "
                f"({complexity.complexity_score:.2f}) for task type '{complexity.task_type}'."
            )
        else:
            # Pick cheapest model in tier
            selected_model = tier_candidates[0] if tier_candidates else fallback_model
            reason = (
                f"Routed to cost-efficient model '{selected_model}' for task type "
                f"'{complexity.task_type}' with moderate complexity "
                f"({complexity.complexity_score:.2f})."
            )

        # 3. Resolve provider and pricing
        provider = self._resolve_provider(selected_model)
        pricing = self._pricing.resolve_pricing(provider, selected_model)
        avg_cost_per_1k = round((pricing.input_cost_per_1k + pricing.output_cost_per_1k) / 2.0, 6)

        return RouteResult(
            selected_model=selected_model,
            selected_provider=provider,
            task_type=complexity.task_type,
            complexity_score=complexity.complexity_score,
            estimated_cost_per_1k=avg_cost_per_1k,
            reason=reason,
            rule_id=matched_rule.rule_id if matched_rule else None,
        )

    def _resolve_provider(self, model_name: str) -> str:
        name_lower = model_name.lower()
        if "gpt" in name_lower or "o1" in name_lower or "o3" in name_lower:
            return "openai"
        if "claude" in name_lower:
            return "anthropic"
        if "gemini" in name_lower:
            return "gemini"
        return "openai"
