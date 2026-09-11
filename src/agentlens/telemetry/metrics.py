"""Production platform telemetry and Prometheus-compatible metrics registry."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Mapping
from typing import Any


def _format_labels(labels: Mapping[str, str | int] | None) -> str:
    if not labels:
        return ""
    pairs = [f'{k}="{v}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(pairs) + "}"


class Counter:
    """Thread-safe monotonic counter with label support."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._lock = threading.RLock()

    def inc(self, amount: float = 1.0, labels: Mapping[str, str | int] | None = None) -> None:
        if amount < 0:
            raise ValueError("Counter increments must be non-negative")
        key = tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def get(self, labels: Mapping[str, str | int] | None = None) -> float:
        key = tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))
        with self._lock:
            return self._values.get(key, 0.0)

    def export_samples(self) -> list[tuple[str, dict[str, str], float]]:
        with self._lock:
            return [
                (self.name, dict(key), value)
                for key, value in self._values.items()
            ]


class Gauge:
    """Thread-safe gauge tracking instantaneous values."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        self._lock = threading.RLock()

    def set(self, value: float, labels: Mapping[str, str | int] | None = None) -> None:
        key = tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, labels: Mapping[str, str | int] | None = None) -> None:
        key = tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, labels: Mapping[str, str | int] | None = None) -> None:
        self.inc(-amount, labels)

    def get(self, labels: Mapping[str, str | int] | None = None) -> float:
        key = tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))
        with self._lock:
            return self._values.get(key, 0.0)

    def export_samples(self) -> list[tuple[str, dict[str, str], float]]:
        with self._lock:
            return [
                (self.name, dict(key), value)
                for key, value in self._values.items()
            ]


class Histogram:
    """Thread-safe histogram with count, sum, and exact percentiles over a bounded window."""

    def __init__(
        self,
        name: str,
        description: str = "",
        *,
        window_size: int = 1000,
    ) -> None:
        self.name = name
        self.description = description
        self.window_size = window_size
        self._counts: dict[tuple[tuple[str, str], ...], int] = {}
        self._sums: dict[tuple[tuple[str, str], ...], float] = {}
        self._samples: dict[tuple[tuple[str, str], ...], deque[float]] = {}
        self._lock = threading.RLock()

    def observe(self, value: float, labels: Mapping[str, str | int] | None = None) -> None:
        key = tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))
        val = float(value)
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1
            self._sums[key] = self._sums.get(key, 0.0) + val
            if key not in self._samples:
                self._samples[key] = deque(maxlen=self.window_size)
            self._samples[key].append(val)

    def get_summary(self, labels: Mapping[str, str | int] | None = None) -> dict[str, float]:
        with self._lock:
            if labels:
                key = tuple(sorted((k, str(v)) for k, v in labels.items()))
                count = self._counts.get(key, 0)
                total_sum = self._sums.get(key, 0.0)
                sample_list = sorted(self._samples.get(key, []))
            else:
                count = sum(self._counts.values())
                total_sum = sum(self._sums.values())
                all_samples: list[float] = []
                for deq in self._samples.values():
                    all_samples.extend(deq)
                sample_list = sorted(all_samples)

        if not sample_list:
            return {
                "count": count,
                "sum": total_sum,
                "p50": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }

        def _calc_p(pct: float) -> float:
            k = (len(sample_list) - 1) * (pct / 100.0)
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sample_list[int(k)]
            d0 = sample_list[int(f)] * (c - k)
            d1 = sample_list[int(c)] * (k - f)
            return d0 + d1

        return {
            "count": count,
            "sum": round(total_sum, 6),
            "p50": round(_calc_p(50), 6),
            "p90": round(_calc_p(90), 6),
            "p95": round(_calc_p(95), 6),
            "p99": round(_calc_p(99), 6),
        }

    def export_samples(self) -> list[tuple[str, dict[str, str], float]]:
        with self._lock:
            results: list[tuple[str, dict[str, str], float]] = []
            for key, count in self._counts.items():
                lbls = dict(key)
                results.append((f"{self.name}_count", lbls, float(count)))
                results.append((f"{self.name}_sum", lbls, self._sums.get(key, 0.0)))
            return results


class MetricsRegistry:
    """Central metrics collector and Prometheus exporter."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.RLock()
        self._init_standard_metrics()

    def _init_standard_metrics(self) -> None:
        # API Metrics
        self.counter(
            "agentlens_api_requests_total",
            "Total count of HTTP requests processed by AgentLens API",
        )
        self.histogram(
            "agentlens_api_request_duration_seconds",
            "Latency distribution of AgentLens API requests in seconds",
        )
        self.counter(
            "agentlens_api_errors_total",
            "Total count of HTTP error responses returned by AgentLens API",
        )

        # Worker Metrics
        self.counter(
            "agentlens_worker_jobs_total",
            "Total jobs processed by AgentLens background workers",
        )
        self.histogram(
            "agentlens_worker_job_duration_seconds",
            "Execution duration of background worker jobs in seconds",
        )
        self.counter(
            "agentlens_worker_retries_total",
            "Total job retries scheduled by background workers",
        )

        # Infrastructure & Queues
        self.gauge(
            "agentlens_queue_depth",
            "Current depth of background task queues",
        )
        self.gauge(
            "agentlens_redis_latency_seconds",
            "Instantaneous round-trip latency to Redis in seconds",
        )
        self.histogram(
            "agentlens_database_query_duration_seconds",
            "Latency distribution of database operations in seconds",
        )
        self.gauge(
            "agentlens_worker_health_total",
            "Count of worker heartbeats grouped by health state",
        )

    def counter(self, name: str, description: str = "") -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description)
            return self._gauges[name]

    def histogram(self, name: str, description: str = "", *, window_size: int = 1000) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, window_size=window_size)
            return self._histograms[name]

    def record_http_request(
        self, route: str, method: str, status_code: int, duration_seconds: float
    ) -> None:
        status_str = str(status_code)
        labels = {"route": route, "method": method, "status_code": status_str}
        self.counter("agentlens_api_requests_total").inc(1.0, labels)
        self.histogram("agentlens_api_request_duration_seconds").observe(
            duration_seconds, {"route": route, "method": method}
        )
        if status_code >= 400:
            error_type = "client_error" if status_code < 500 else "server_error"
            self.counter("agentlens_api_errors_total").inc(
                1.0, {"route": route, "status_code": status_str, "type": error_type}
            )

    def record_worker_job(
        self, worker_type: str, status: str, duration_seconds: float
    ) -> None:
        labels = {"worker_type": worker_type, "status": status}
        self.counter("agentlens_worker_jobs_total").inc(1.0, labels)
        self.histogram("agentlens_worker_job_duration_seconds").observe(
            duration_seconds, {"worker_type": worker_type}
        )

    def record_worker_retry(self, worker_type: str) -> None:
        self.counter("agentlens_worker_retries_total").inc(1.0, {"worker_type": worker_type})

    def set_queue_depth(self, queue_name: str, depth: int) -> None:
        self.gauge("agentlens_queue_depth").set(float(depth), {"queue": queue_name})

    def set_redis_latency(self, latency_seconds: float) -> None:
        self.gauge("agentlens_redis_latency_seconds").set(latency_seconds)

    def get_summary_snapshot(self) -> dict[str, Any]:
        """Produce an instantaneous JSON-serializable telemetry snapshot."""
        with self._lock:
            api_latency = self.histogram("agentlens_api_request_duration_seconds").get_summary()
            worker_latency = self.histogram("agentlens_worker_job_duration_seconds").get_summary()
            counters_data = {
                name: c.export_samples() for name, c in self._counters.items()
            }
            gauges_data = {
                name: g.export_samples() for name, g in self._gauges.items()
            }

        return {
            "timestamp": time.time(),
            "api_latency_summary": api_latency,
            "worker_latency_summary": worker_latency,
            "counters": counters_data,
            "gauges": gauges_data,
        }

    def export_prometheus_text(self) -> str:
        """Export all registered metrics in Prometheus text exposition format."""
        lines: list[str] = []

        with self._lock:
            for name, counter in sorted(self._counters.items()):
                if counter.description:
                    lines.append(f"# HELP {name} {counter.description}")
                lines.append(f"# TYPE {name} counter")
                for metric_name, labels, val in counter.export_samples():
                    lbl_str = _format_labels(labels)
                    lines.append(f"{metric_name}{lbl_str} {val}")

            for name, gauge in sorted(self._gauges.items()):
                if gauge.description:
                    lines.append(f"# HELP {name} {gauge.description}")
                lines.append(f"# TYPE {name} gauge")
                for metric_name, labels, val in gauge.export_samples():
                    lbl_str = _format_labels(labels)
                    lines.append(f"{metric_name}{lbl_str} {val}")

            for name, hist in sorted(self._histograms.items()):
                if hist.description:
                    lines.append(f"# HELP {name} {hist.description}")
                lines.append(f"# TYPE {name} summary")
                for metric_name, labels, val in hist.export_samples():
                    lbl_str = _format_labels(labels)
                    lines.append(f"{metric_name}{lbl_str} {val}")

        return "\n".join(lines) + "\n"


_GLOBAL_REGISTRY: MetricsRegistry | None = None
_REGISTRY_LOCK = threading.RLock()


def get_metrics_registry() -> MetricsRegistry:
    """Return the global platform MetricsRegistry singleton."""
    global _GLOBAL_REGISTRY
    with _REGISTRY_LOCK:
        if _GLOBAL_REGISTRY is None:
            _GLOBAL_REGISTRY = MetricsRegistry()
        return _GLOBAL_REGISTRY
