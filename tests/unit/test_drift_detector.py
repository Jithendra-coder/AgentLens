"""Unit tests  DriftDetector and statistical regression evaluation."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agentlens.regression.drift.detector import DriftDetector
from agentlens.regression.drift.models import QualityBaseline


def test_quality_baseline_invariants() -> None:
    with pytest.raises(ValueError, match="QualityBaseline name cannot be empty"):
        QualityBaseline(
            project_id="proj-1",
            name="",
            metric_name="quality_score",
            baseline_mean=0.9,
        )

    with pytest.raises(ValueError, match="baseline_std cannot be negative"):
        QualityBaseline(
            project_id="proj-1",
            name="base",
            metric_name="quality_score",
            baseline_mean=0.9,
            baseline_std=-0.1,
        )


def test_drift_detector_stable_vs_quality_drop() -> None:
    baseline = QualityBaseline(
        baseline_id=uuid4(),
        project_id="proj-drift",
        name="Agent Quality Baseline",
        metric_name="quality_score",
        baseline_mean=0.90,
        baseline_std=0.03,
        window_size=50,
    )

    # 1. Stable observations
    stable_samples = [0.89, 0.91, 0.90, 0.88, 0.92]
    r_stable = DriftDetector.evaluate_drift(baseline, stable_samples)
    assert r_stable.drift_type == "stable"
    assert r_stable.is_alert is False
    assert abs(r_stable.z_score) < 2.0

    # 2. Significant quality regression
    drop_samples = [0.72, 0.74, 0.70, 0.75, 0.73]
    r_drop = DriftDetector.evaluate_drift(baseline, drop_samples)
    assert r_drop.drift_type == "quality_drop"
    assert r_drop.is_alert is True
    assert r_drop.z_score < -2.0
    assert r_drop.drift_magnitude_pct < -10.0


def test_drift_detector_latency_spike_and_cost_inflation() -> None:
    # 1. Latency Baseline
    lat_baseline = QualityBaseline(
        baseline_id=uuid4(),
        project_id="proj-drift",
        name="Latency Baseline",
        metric_name="latency_ms",
        baseline_mean=500.0,
        baseline_std=50.0,
    )
    spike_samples = [950.0, 1000.0, 920.0, 980.0]
    r_lat = DriftDetector.evaluate_drift(lat_baseline, spike_samples)
    assert r_lat.drift_type == "latency_spike"
    assert r_lat.is_alert is True
    assert r_lat.z_score > 2.0

    # 2. Cost Baseline
    cost_baseline = QualityBaseline(
        baseline_id=uuid4(),
        project_id="proj-drift",
        name="Cost Baseline",
        metric_name="cost_usd",
        baseline_mean=0.005,
        baseline_std=0.0005,
    )
    inflation_samples = [0.012, 0.014, 0.013, 0.015]
    r_cost = DriftDetector.evaluate_drift(cost_baseline, inflation_samples)
    assert r_cost.drift_type == "cost_inflation"
    assert r_cost.is_alert is True
    assert r_cost.z_score > 2.0
