"""Statistical drift and quality regression detector ."""

from __future__ import annotations

import math
from collections.abc import Sequence

from agentlens.regression.drift.models import (
    DriftEvaluationResult,
    QualityBaseline,
)


class DriftDetector:
    """Evaluates sample distributions against baselines using Z-scores and delta percentages."""

    @staticmethod
    def evaluate_drift(
        baseline: QualityBaseline,
        observed_values: Sequence[float],
        z_alert_threshold: float = 2.0,
    ) -> DriftEvaluationResult:
        if not observed_values:
            return DriftEvaluationResult(
                baseline_id=baseline.baseline_id,
                baseline_name=baseline.name,
                metric_name=baseline.metric_name,
                observed_mean=baseline.baseline_mean,
                baseline_mean=baseline.baseline_mean,
                z_score=0.0,
                drift_magnitude_pct=0.0,
                drift_type="stable",
                is_alert=False,
                reason="No observed samples provided.",
            )

        n = len(observed_values)
        obs_mean = sum(observed_values) / float(n)
        base_mean = baseline.baseline_mean
        base_std = max(baseline.baseline_std, 1e-4)

        sem = base_std / math.sqrt(n)
        z_score = (obs_mean - base_mean) / sem
        denom_pct = base_mean if abs(base_mean) > 1e-6 else 1e-6
        drift_magnitude_pct = ((obs_mean - base_mean) / denom_pct) * 100.0

        is_alert = False
        drift_type = "stable"
        reason = f"Observed mean ({obs_mean:.4f}) is stable relative to baseline ({base_mean:.4f})."

        if baseline.metric_name == "quality_score":
            if z_score <= -z_alert_threshold or drift_magnitude_pct <= -10.0:
                is_alert = True
                drift_type = "quality_drop"
                reason = (
                    f"Quality regression: mean dropped by {abs(drift_magnitude_pct):.2f}% "
                    f"(Z={z_score:.2f}, base={base_mean:.4f}, obs={obs_mean:.4f})."
                )
        elif baseline.metric_name == "latency_ms":
            if z_score >= z_alert_threshold or drift_magnitude_pct >= 25.0:
                is_alert = True
                drift_type = "latency_spike"
                reason = (
                    f"Latency spike: mean increased by {drift_magnitude_pct:.2f}% "
                    f"(Z={z_score:.2f}, base={base_mean:.1f}ms, obs={obs_mean:.1f}ms)."
                )
        elif baseline.metric_name == "cost_usd":
            if z_score >= z_alert_threshold or drift_magnitude_pct >= 30.0:
                is_alert = True
                drift_type = "cost_inflation"
                reason = (
                    f"Cost inflation: mean increased by {drift_magnitude_pct:.2f}% "
                    f"(Z={z_score:.2f}, base=${base_mean:.4f}, obs=${obs_mean:.4f})."
                )

        return DriftEvaluationResult(
            baseline_id=baseline.baseline_id,
            baseline_name=baseline.name,
            metric_name=baseline.metric_name,
            observed_mean=round(obs_mean, 6),
            baseline_mean=round(base_mean, 6),
            z_score=round(z_score, 4),
            drift_magnitude_pct=round(drift_magnitude_pct, 2),
            drift_type=drift_type,
            is_alert=is_alert,
            reason=reason,
        )
