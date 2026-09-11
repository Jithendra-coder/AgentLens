"""Unit tests  ExperimentReporter and comparative metrics."""

from __future__ import annotations

from uuid import uuid4

from agentlens.experimentation.models import (
    Experiment,
    ExperimentEvaluation,
    ExperimentVariant,
)
from agentlens.experimentation.reporter import ExperimentReporter


def test_experiment_reporter_comparative_deltas() -> None:
    exp_id = uuid4()
    v_ctrl = ExperimentVariant(
        variant_id=uuid4(),
        experiment_id=exp_id,
        name="Control GPT-4o",
        traffic_weight=0.5,
        is_control=True,
    )
    v_treat = ExperimentVariant(
        variant_id=uuid4(),
        experiment_id=exp_id,
        name="Treatment Claude 3.5",
        traffic_weight=0.5,
        is_control=False,
    )

    exp = Experiment(
        experiment_id=exp_id,
        project_id="proj-rep",
        name="Prompt Optimization",
        variants=(v_ctrl, v_treat),
    )

    # Evaluations for Control: score=0.80, cost=0.010, latency=1000
    e1 = ExperimentEvaluation(
        experiment_id=exp_id,
        variant_id=v_ctrl.variant_id,
        trace_id=uuid4(),
        score=0.80,
        cost_usd=0.010,
        latency_ms=1000.0,
    )
    # Evaluations for Treatment: score=0.90, cost=0.005, latency=800
    e2 = ExperimentEvaluation(
        experiment_id=exp_id,
        variant_id=v_treat.variant_id,
        trace_id=uuid4(),
        score=0.90,
        cost_usd=0.005,
        latency_ms=800.0,
    )

    report = ExperimentReporter.generate_report(exp, [e1, e2])
    assert report.total_evaluations == 2
    assert len(report.variants) == 2

    ctrl_metric = next(v for v in report.variants if v.is_control)
    assert ctrl_metric.sample_count == 1
    assert ctrl_metric.mean_score == 0.80
    assert ctrl_metric.score_delta_pct == 0.0

    treat_metric = next(v for v in report.variants if not v.is_control)
    assert treat_metric.sample_count == 1
    assert treat_metric.mean_score == 0.90
    # Score delta: (0.90 - 0.80) / 0.80 = +12.5%
    assert treat_metric.score_delta_pct == 12.5
    # Cost delta: (0.005 - 0.010) / 0.010 = -50.0%
    assert treat_metric.cost_delta_pct == -50.0
    # Latency delta: (800 - 1000) / 1000 = -20.0%
    assert treat_metric.latency_delta_pct == -20.0
