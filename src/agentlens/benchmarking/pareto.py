"""Cost vs Quality Pareto Frontier Optimizer ."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from agentlens.benchmarking.models import (
    ModelBenchmarkRun,
    ParetoFrontierReport,
    ParetoPoint,
)
from agentlens.cost.pricing import PricingRegistry


class ParetoOptimizer:
    """Calculates the non-dominated Pareto Frontier balancing Quality vs Cost."""

    def __init__(self, pricing_registry: PricingRegistry | None = None) -> None:
        self._pricing = pricing_registry or PricingRegistry()

    def compute_frontier(
        self,
        project_id: str,
        benchmark_id: UUID | None,
        runs: Sequence[ModelBenchmarkRun],
    ) -> ParetoFrontierReport:
        if not runs:
            return ParetoFrontierReport(project_id=project_id, benchmark_id=benchmark_id, points=[])

        raw_points: list[ParetoPoint] = []
        for r in runs:
            pricing = self._pricing.resolve_pricing(r.provider_type, r.model_name)
            avg_cost = round((pricing.input_cost_per_1k + pricing.output_cost_per_1k) / 2.0, 6)
            raw_points.append(
                ParetoPoint(
                    model_name=r.model_name,
                    provider_type=r.provider_type,
                    quality_score=round(r.overall_score, 4),
                    cost_per_1k=avg_cost,
                    latency_ms=round(r.mean_latency_ms, 2),
                    is_optimal=False,
                )
            )

        evaluated_points: list[ParetoPoint] = []

        # Determine Pareto optimality: Point A is dominated if there exists B such that
        # Quality(B) >= Quality(A) AND Cost(B) <= Cost(A) with at least one strict inequality.
        for i, a in enumerate(raw_points):
            is_dominated = False
            for j, b in enumerate(raw_points):
                if i == j:
                    continue
                better_or_equal_quality = b.quality_score >= a.quality_score
                cheaper_or_equal_cost = b.cost_per_1k <= a.cost_per_1k
                strictly_better = (
                    (b.quality_score > a.quality_score) or (b.cost_per_1k < a.cost_per_1k)
                )

                if better_or_equal_quality and cheaper_or_equal_cost and strictly_better:
                    is_dominated = True
                    break

            evaluated_points.append(
                ParetoPoint(
                    model_name=a.model_name,
                    provider_type=a.provider_type,
                    quality_score=a.quality_score,
                    cost_per_1k=a.cost_per_1k,
                    latency_ms=a.latency_ms,
                    is_optimal=not is_dominated,
                )
            )

        # Sort points by quality score descending
        evaluated_points.sort(key=lambda p: p.quality_score, reverse=True)

        return ParetoFrontierReport(
            project_id=project_id,
            benchmark_id=benchmark_id,
            points=evaluated_points,
        )
