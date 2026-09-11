"""Model qualification evaluation gate ."""

from __future__ import annotations

from uuid import uuid4

from agentlens.benchmarking.models import ModelBenchmarkRun, ModelQualification


class QualificationGate:
    """Evaluates whether a benchmarked model meets production readiness standards."""

    @staticmethod
    def evaluate(
        run: ModelBenchmarkRun,
        min_required_score: float = 0.80,
        max_latency_ms: float = 3000.0,
        min_pass_rate: float = 0.80,
    ) -> ModelQualification:
        meets_score = run.overall_score >= min_required_score
        meets_latency = run.mean_latency_ms <= max_latency_ms
        meets_pass_rate = run.pass_rate >= min_pass_rate
        is_completed = run.status == "completed"

        is_qualified = bool(meets_score and meets_latency and meets_pass_rate and is_completed)

        return ModelQualification(
            qualification_id=uuid4(),
            project_id=run.project_id,
            model_name=run.model_name,
            provider_type=run.provider_type,
            is_qualified=is_qualified,
            min_required_score=min_required_score,
            latest_run_id=run.run_id,
        )
