"""Health Index calculation and status classification ."""

from __future__ import annotations

from agentlens.monitoring.models import HealthMetrics


class HealthCalculator:
    """Computes composite Health Index (0-100) and operational status."""

    @staticmethod
    def calculate_health_index(metrics: HealthMetrics) -> float:
        # 1. Quality factor (50% weight): score between 0.0 and 1.0
        q_factor = max(0.0, min(1.0, metrics.mean_quality_score))

        # 2. Latency factor (25% weight): degradation above 0ms up to 3000ms SLA cap
        lat_factor = max(0.0, min(1.0, 1.0 - (metrics.p95_latency_ms / 3000.0)))

        # 3. Reliability factor (25% weight): (1 - error_rate)
        err_factor = max(0.0, min(1.0, 1.0 - metrics.error_rate))

        composite = (0.50 * q_factor) + (0.25 * lat_factor) + (0.25 * err_factor)
        index = round(composite * 100.0, 2)
        return max(0.0, min(100.0, index))

    @staticmethod
    def classify_status(health_index: float) -> str:
        if health_index >= 85.0:
            return "healthy"
        if health_index >= 60.0:
            return "degraded"
        return "critical"
