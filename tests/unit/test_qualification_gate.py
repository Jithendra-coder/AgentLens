"""Unit tests  QualificationGate and evaluation criteria."""

from __future__ import annotations

from uuid import uuid4

from agentlens.benchmarking.models import ModelBenchmarkRun
from agentlens.benchmarking.qualifier import QualificationGate


def test_qualification_gate_pass_and_fail() -> None:
    bench_id = uuid4()

    # 1. High performing run -> passes qualification
    good_run = ModelBenchmarkRun(
        benchmark_id=bench_id,
        project_id="proj-qual",
        model_name="gpt-4o",
        provider_type="openai",
        overall_score=0.91,
        mean_latency_ms=800.0,
        pass_rate=0.95,
        status="completed",
    )
    q1 = QualificationGate.evaluate(good_run, min_required_score=0.80, max_latency_ms=2000.0)
    assert q1.is_qualified is True
    assert q1.model_name == "gpt-4o"

    # 2. Run with low quality score -> fails qualification
    low_score_run = ModelBenchmarkRun(
        benchmark_id=bench_id,
        project_id="proj-qual",
        model_name="small-model",
        provider_type="openai",
        overall_score=0.72,
        mean_latency_ms=300.0,
        pass_rate=0.75,
        status="completed",
    )
    q2 = QualificationGate.evaluate(low_score_run, min_required_score=0.80)
    assert q2.is_qualified is False

    # 3. Run with excessive latency -> fails qualification
    slow_run = ModelBenchmarkRun(
        benchmark_id=bench_id,
        project_id="proj-qual",
        model_name="slow-model",
        provider_type="openai",
        overall_score=0.95,
        mean_latency_ms=4500.0,
        pass_rate=0.98,
        status="completed",
    )
    q3 = QualificationGate.evaluate(slow_run, max_latency_ms=2500.0)
    assert q3.is_qualified is False
