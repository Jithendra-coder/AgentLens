"""Unit tests  HealthCalculator and status classification."""

from __future__ import annotations

from agentlens.monitoring.calculator import HealthCalculator
from agentlens.monitoring.models import HealthMetrics


def test_health_calculator_healthy_degraded_critical() -> None:
    # 1. Healthy system (high quality, low latency, 0 errors)
    healthy_metrics = HealthMetrics(
        mean_quality_score=0.95,
        p95_latency_ms=250.0,
        error_rate=0.005,
        total_spans_evaluated=500,
    )
    h_idx = HealthCalculator.calculate_health_index(healthy_metrics)
    assert h_idx >= 85.0
    assert HealthCalculator.classify_status(h_idx) == "healthy"

    # 2. Degraded system (moderate quality, latency near SLA cap, minor errors)
    degraded_metrics = HealthMetrics(
        mean_quality_score=0.72,
        p95_latency_ms=1800.0,
        error_rate=0.08,
        total_spans_evaluated=200,
    )
    d_idx = HealthCalculator.calculate_health_index(degraded_metrics)
    assert 60.0 <= d_idx < 85.0
    assert HealthCalculator.classify_status(d_idx) == "degraded"

    # 3. Critical system (poor quality, SLA breached, high errors)
    critical_metrics = HealthMetrics(
        mean_quality_score=0.40,
        p95_latency_ms=3500.0,
        error_rate=0.35,
        total_spans_evaluated=100,
    )
    c_idx = HealthCalculator.calculate_health_index(critical_metrics)
    assert c_idx < 60.0
    assert HealthCalculator.classify_status(c_idx) == "critical"
