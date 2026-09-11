"""Statistical reporting and comparative metrics for experimentation ."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from agentlens.experimentation.models import (
    Experiment,
    ExperimentEvaluation,
    ExperimentReport,
    VariantComparativeMetric,
)


class ExperimentReporter:
    """Computes comparative metrics, quality deltas, and cost trade-offs for experiments."""

    @staticmethod
    def generate_report(
        experiment: Experiment,
        evaluations: Sequence[ExperimentEvaluation],
    ) -> ExperimentReport:
        evals_by_variant: dict[UUID, list[ExperimentEvaluation]] = {}
        for ev in evaluations:
            evals_by_variant.setdefault(ev.variant_id, []).append(ev)

        # Identify control variant
        control_variant = next((v for v in experiment.variants if v.is_control), None)
        control_evals = (
            evals_by_variant.get(control_variant.variant_id, []) if control_variant else []
        )
        ctrl_n = len(control_evals)
        ctrl_mean_score = (sum(e.score for e in control_evals) / ctrl_n) if ctrl_n > 0 else 0.0
        ctrl_mean_cost = (sum(e.cost_usd for e in control_evals) / ctrl_n) if ctrl_n > 0 else 0.0
        ctrl_mean_lat = (sum(e.latency_ms for e in control_evals) / ctrl_n) if ctrl_n > 0 else 0.0

        variant_metrics: list[VariantComparativeMetric] = []

        for v in experiment.variants:
            v_evals = evals_by_variant.get(v.variant_id, [])
            n = len(v_evals)
            mean_score = (sum(e.score for e in v_evals) / n) if n > 0 else 0.0
            mean_cost = (sum(e.cost_usd for e in v_evals) / n) if n > 0 else 0.0
            mean_lat = (sum(e.latency_ms for e in v_evals) / n) if n > 0 else 0.0

            if v.is_control or v == control_variant or ctrl_n == 0:
                score_delta = 0.0
                cost_delta = 0.0
                lat_delta = 0.0
            else:
                score_delta = (
                    round(((mean_score - ctrl_mean_score) / ctrl_mean_score) * 100.0, 2)
                    if ctrl_mean_score > 0
                    else 0.0
                )
                cost_delta = (
                    round(((mean_cost - ctrl_mean_cost) / ctrl_mean_cost) * 100.0, 2)
                    if ctrl_mean_cost > 0
                    else 0.0
                )
                lat_delta = (
                    round(((mean_lat - ctrl_mean_lat) / ctrl_mean_lat) * 100.0, 2)
                    if ctrl_mean_lat > 0
                    else 0.0
                )

            variant_metrics.append(
                VariantComparativeMetric(
                    variant_id=v.variant_id,
                    name=v.name,
                    is_control=v.is_control,
                    sample_count=n,
                    mean_score=round(mean_score, 4),
                    mean_cost_usd=round(mean_cost, 6),
                    mean_latency_ms=round(mean_lat, 2),
                    score_delta_pct=score_delta,
                    cost_delta_pct=cost_delta,
                    latency_delta_pct=lat_delta,
                )
            )

        return ExperimentReport(
            experiment_id=experiment.experiment_id,
            project_id=experiment.project_id,
            name=experiment.name,
            status=experiment.status,
            total_evaluations=len(evaluations),
            variants=variant_metrics,
        )
