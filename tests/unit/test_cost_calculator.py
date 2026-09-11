"""Unit tests  PricingRegistry and CostCalculator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from agentlens.cost.calculator import CostCalculator
from agentlens.cost.models import ModelPricing
from agentlens.cost.pricing import PricingRegistry
from agentlens.domain import Span, Trace
from agentlens.domain.types import SpanType, Status


def test_pricing_registry_resolution() -> None:
    registry = PricingRegistry()

    p_gpt4o = registry.resolve_pricing("openai", "gpt-4o")
    assert p_gpt4o.provider == "openai"
    assert p_gpt4o.input_cost_per_1k == 0.005
    assert p_gpt4o.output_cost_per_1k == 0.015

    p_claude = registry.resolve_pricing("anthropic", "claude-3-5-sonnet-20241022")
    assert p_claude.provider == "anthropic"
    assert p_claude.input_cost_per_1k == 0.003

    p_gemini = registry.resolve_pricing("gemini", "gemini-1.5-pro")
    assert p_gemini.provider == "gemini"
    assert p_gemini.input_cost_per_1k == 0.00125

    p_unknown = registry.resolve_pricing("self_hosted", "custom-llama")
    assert p_unknown.input_cost_per_1k == 0.0


def test_custom_pricing_registration_precedence() -> None:
    registry = PricingRegistry()
    custom_p = ModelPricing(
        provider="custom_provider",
        model_pattern="^custom-model$",
        input_cost_per_1k=0.010,
        output_cost_per_1k=0.020,
    )
    registry.register_pricing(custom_p)

    resolved = registry.resolve_pricing("custom_provider", "custom-model")
    assert resolved.input_cost_per_1k == 0.010
    assert resolved.output_cost_per_1k == 0.020


def test_cost_calculator_span_and_trace() -> None:
    calculator = CostCalculator()
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()

    span1 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.LLM,
        name="LLMGeneration",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=1),
        status=Status.OK,
        attributes={
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        },
    )

    span2 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.TOOL,
        name="ToolExec",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
    )

    trace = Trace(
        trace_id=trace_id,
        project_id="proj-cost",
        name="CostTrace",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
        spans=[span1, span2],
    )

    records = calculator.calculate_trace_costs(trace)
    assert len(records) == 2

    r1 = records[0]
    # input: (1000/1000)*0.005 = 0.005, output: (500/1000)*0.015 = 0.0075 -> total 0.0125
    assert r1.input_tokens == 1000
    assert r1.output_tokens == 500
    assert r1.total_cost_usd == 0.0125
    assert r1.provider == "openai"
    assert r1.model == "gpt-4o"

    r2 = records[1]
    assert r2.input_tokens == 0
    assert r2.output_tokens == 0
    assert r2.total_cost_usd == 0.0
