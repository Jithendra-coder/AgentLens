"""Unit tests for platform telemetry, MetricsRegistry, and Prometheus exposition."""

from __future__ import annotations

import pytest

from agentlens.telemetry.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_metrics_registry,
)


def test_counter_increments_and_labels() -> None:
    counter = Counter("test_requests_total", "Test counter")
    assert counter.get() == 0.0

    counter.inc()
    assert counter.get() == 1.0

    counter.inc(5.0)
    assert counter.get() == 6.0

    counter.inc(2.0, {"route": "/v1/traces", "status": "200"})
    assert counter.get({"route": "/v1/traces", "status": "200"}) == 2.0
    assert counter.get() == 6.0

    with pytest.raises(ValueError, match="non-negative"):
        counter.inc(-1.0)

    samples = counter.export_samples()
    assert len(samples) == 2


def test_gauge_operations() -> None:
    gauge = Gauge("test_queue_depth", "Test gauge")
    assert gauge.get() == 0.0

    gauge.set(10.0)
    assert gauge.get() == 10.0

    gauge.inc(5.0)
    assert gauge.get() == 15.0

    gauge.dec(3.0)
    assert gauge.get() == 12.0

    gauge.set(42.0, {"queue": "eval"})
    assert gauge.get({"queue": "eval"}) == 42.0
    assert gauge.get() == 12.0


def test_histogram_percentiles() -> None:
    hist = Histogram("test_latency_seconds", "Test histogram")
    summary_empty = hist.get_summary()
    assert summary_empty["count"] == 0
    assert summary_empty["p50"] == 0.0

    # Add samples: 1.0, 2.0, 3.0, ..., 100.0
    for i in range(1, 101):
        hist.observe(float(i))

    summary = hist.get_summary()
    assert summary["count"] == 100
    assert summary["sum"] == 5050.0
    assert 49.0 <= summary["p50"] <= 51.0
    assert 89.0 <= summary["p90"] <= 91.0
    assert 94.0 <= summary["p95"] <= 96.0
    assert 98.0 <= summary["p99"] <= 100.0


def test_metrics_registry_recording_and_prometheus_export() -> None:
    registry = MetricsRegistry()

    # Record API request
    registry.record_http_request("/v1/traces", "POST", 200, 0.045)
    registry.record_http_request("/v1/traces", "POST", 500, 0.120)

    # Record Worker job
    registry.record_worker_job("evaluation", "success", 0.350)
    registry.record_worker_retry("evaluation")

    # Record queue depth
    registry.set_queue_depth("evaluation", 5)

    # Snapshot
    snapshot = registry.get_summary_snapshot()
    assert "api_latency_summary" in snapshot
    assert "worker_latency_summary" in snapshot
    assert snapshot["api_latency_summary"]["count"] == 2
    assert snapshot["worker_latency_summary"]["count"] == 1

    # Prometheus export format
    text = registry.export_prometheus_text()
    assert "# TYPE agentlens_api_requests_total counter" in text
    expected_line_200 = (
        'agentlens_api_requests_total{method="POST",route="/v1/traces",status_code="200"} 1.0'
    )
    expected_line_500 = (
        'agentlens_api_requests_total{method="POST",route="/v1/traces",status_code="500"} 1.0'
    )
    assert expected_line_200 in text
    assert expected_line_500 in text
    assert "# TYPE agentlens_queue_depth gauge" in text
    assert 'agentlens_queue_depth{queue="evaluation"} 5.0' in text


def test_singleton_registry() -> None:
    r1 = get_metrics_registry()
    r2 = get_metrics_registry()
    assert r1 is r2
