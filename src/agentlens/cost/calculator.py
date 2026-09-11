"""Cost calculation engine for spans and traces ."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from agentlens.cost.models import SpanCostRecord
from agentlens.cost.pricing import PricingRegistry
from agentlens.domain import Span, Trace


class CostCalculator:
    """Calculates exact token costs for spans and traces."""

    def __init__(self, pricing_registry: PricingRegistry | None = None) -> None:
        self._pricing = pricing_registry or PricingRegistry()

    def _extract_tokens(self, attributes: Mapping[str, Any]) -> tuple[int, int, str, str]:
        """Extract input tokens, output tokens, model, and provider from span attributes."""
        in_tok = int(
            attributes.get("input_tokens")
            or attributes.get("prompt_tokens")
            or attributes.get("tokens.prompt")
            or attributes.get("tokens.input")
            or 0
        )
        out_tok = int(
            attributes.get("output_tokens")
            or attributes.get("completion_tokens")
            or attributes.get("tokens.completion")
            or attributes.get("tokens.output")
            or 0
        )
        model = str(
            attributes.get("model")
            or attributes.get("llm.model")
            or attributes.get("model_name")
            or "unknown"
        )
        provider = str(
            attributes.get("provider")
            or attributes.get("llm.provider")
            or "unknown"
        )
        return in_tok, out_tok, model, provider

    def calculate_span_cost(self, project_id: str, span: Span) -> SpanCostRecord:
        """Compute cost for a single span."""
        in_tok, out_tok, model, provider = self._extract_tokens(span.attributes)
        pricing = self._pricing.resolve_pricing(provider, model)

        input_cost = (in_tok / 1000.0) * pricing.input_cost_per_1k
        output_cost = (out_tok / 1000.0) * pricing.output_cost_per_1k
        total_cost = round(input_cost + output_cost, 6)

        span_uuid = span.span_id if isinstance(span.span_id, UUID) else UUID(str(span.span_id))
        trace_uuid = span.trace_id if isinstance(span.trace_id, UUID) else UUID(str(span.trace_id))

        return SpanCostRecord(
            span_id=span_uuid,
            trace_id=trace_uuid,
            project_id=project_id,
            provider=provider if provider != "unknown" else pricing.provider,
            model=model if model != "unknown" else pricing.model_pattern,
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_cost_usd=total_cost,
        )

    def calculate_trace_costs(self, trace: Trace) -> list[SpanCostRecord]:
        """Compute costs for all spans in a trace."""
        records: list[SpanCostRecord] = []
        for span in trace.spans:
            rec = self.calculate_span_cost(trace.project_id, span)
            records.append(rec)
        return records
