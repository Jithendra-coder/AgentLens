"""Default model pricing catalog and registry ."""

from __future__ import annotations

import re
from collections.abc import Sequence

from agentlens.cost.models import ModelPricing

DEFAULT_PRICING_TABLE: tuple[ModelPricing, ...] = (
    # OpenAI
    ModelPricing(
        provider="openai",
        model_pattern="^gpt-4o$",
        input_cost_per_1k=0.005,
        output_cost_per_1k=0.015,
    ),
    ModelPricing(
        provider="openai",
        model_pattern="^gpt-4o-mini",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.0006,
    ),
    ModelPricing(
        provider="openai",
        model_pattern="^o1",
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.060,
    ),
    # Anthropic
    ModelPricing(
        provider="anthropic",
        model_pattern="^claude-3-5-sonnet",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
    ),
    ModelPricing(
        provider="anthropic",
        model_pattern="^claude-3-5-haiku|^claude-3-haiku",
        input_cost_per_1k=0.00025,
        output_cost_per_1k=0.00125,
    ),
    ModelPricing(
        provider="anthropic",
        model_pattern="^claude-3-opus",
        input_cost_per_1k=0.015,
        output_cost_per_1k=0.075,
    ),
    # Google Gemini
    ModelPricing(
        provider="gemini",
        model_pattern="^models/gemini-1.5-pro|^gemini-1.5-pro",
        input_cost_per_1k=0.00125,
        output_cost_per_1k=0.005,
    ),
    ModelPricing(
        provider="gemini",
        model_pattern="^models/gemini-1.5-flash|^gemini-1.5-flash",
        input_cost_per_1k=0.000075,
        output_cost_per_1k=0.0003,
    ),
)

FALLBACK_FREE_PRICING = ModelPricing(
    provider="custom_http",
    model_pattern=".*",
    input_cost_per_1k=0.0,
    output_cost_per_1k=0.0,
)


class PricingRegistry:
    """Registry for matching model providers and models to cost rates."""

    def __init__(self, custom_pricings: Sequence[ModelPricing] | None = None) -> None:
        self._pricings: list[ModelPricing] = list(custom_pricings or DEFAULT_PRICING_TABLE)

    def register_pricing(self, pricing: ModelPricing) -> None:
        """Register custom pricing rate with precedence (inserted at start)."""
        self._pricings.insert(0, pricing)

    def resolve_pricing(self, provider: str, model: str) -> ModelPricing:
        """Resolve the matching ModelPricing entry for provider and model name."""
        norm_provider = provider.lower().strip()
        norm_model = model.strip()

        for p in self._pricings:
            if p.provider.lower() == norm_provider or p.provider == "*":
                if re.search(p.model_pattern, norm_model, re.IGNORECASE):
                    return p

        # Check for model pattern match across any provider if provider not specified
        for p in self._pricings:
            if re.search(p.model_pattern, norm_model, re.IGNORECASE):
                return p

        return FALLBACK_FREE_PRICING
