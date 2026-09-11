"""Unit tests  Pareto Frontier optimizer and domain models."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agentlens.benchmarking.models import (
    ModelBenchmark,
    ModelBenchmarkRun,
)
from agentlens.benchmarking.pareto import ParetoOptimizer
from agentlens.cost.pricing import PricingRegistry


def test_model_benchmark_invariants() -> None:
    with pytest.raises(ValueError, match="ModelBenchmark name cannot be empty"):
        ModelBenchmark(project_id="proj-1", name="")

    with pytest.raises(ValueError, match="overall_score must be between"):
        ModelBenchmarkRun(
            benchmark_id=uuid4(),
            project_id="proj-1",
            model_name="m1",
            overall_score=1.5,
        )


def test_pareto_optimizer_non_dominated_frontier() -> None:
    pricing = PricingRegistry()
    optimizer = ParetoOptimizer(pricing)
    bench_id = uuid4()

    # 1. Model A: Very cheap, decent quality (gpt-4o-mini: score=0.82, cost=0.000375/1k)
    run_a = ModelBenchmarkRun(
        benchmark_id=bench_id,
        project_id="proj-pareto",
        model_name="gpt-4o-mini",
        provider_type="openai",
        overall_score=0.82,
        mean_latency_ms=400.0,
    )

    # 2. Model B: High quality, higher cost (gpt-4o: score=0.92, cost=0.010/1k)
    run_b = ModelBenchmarkRun(
        benchmark_id=bench_id,
        project_id="proj-pareto",
        model_name="gpt-4o",
        provider_type="openai",
        overall_score=0.92,
        mean_latency_ms=900.0,
    )

    # 3. Model C: Dominated model (lower quality and higher cost than gpt-4o)
    run_c = ModelBenchmarkRun(
        benchmark_id=bench_id,
        project_id="proj-pareto",
        model_name="claude-3-opus-20240229",
        provider_type="anthropic",
        overall_score=0.85,  # lower than gpt-4o (0.92)
        mean_latency_ms=1500.0,
        # cost for opus is 0.045/1k, strictly higher than gpt-4o (0.010)
    )

    report = optimizer.compute_frontier("proj-pareto", bench_id, [run_a, run_b, run_c])
    assert len(report.points) == 3

    point_map = {p.model_name: p for p in report.points}

    # gpt-4o-mini is Pareto optimal (cheapest)
    assert point_map["gpt-4o-mini"].is_optimal is True

    # gpt-4o is Pareto optimal (highest quality)
    assert point_map["gpt-4o"].is_optimal is True

    # claude-3-opus is dominated by gpt-4o (0.85 < 0.92, cost 0.045 > 0.010)
    assert point_map["claude-3-opus-20240229"].is_optimal is False
