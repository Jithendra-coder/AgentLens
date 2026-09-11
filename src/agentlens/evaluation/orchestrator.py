"""Evaluation suite orchestrator and composite score calculator ."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from agentlens.domain import Trace
from agentlens.evaluation.composite import (
    CompositeEvaluationResult,
    EvaluationSuite,
    EvaluatorConfigRef,
    MetricScore,
)
from agentlens.evaluation.evaluators import (
    LatencyEvaluator,
    ReliabilityEvaluator,
    RetrievalRankingEvaluator,
    UsageEvaluator,
)
from agentlens.evaluation.judges import SemanticJudge
from agentlens.evaluation.plugins.models import EvaluatorContext
from agentlens.evaluation.plugins.repository import CustomEvaluatorRepository
from agentlens.evaluation.plugins.sandbox import execute_custom_evaluator


class EvaluationSuiteOrchestrator:
    """Orchestrates multi-metric evaluation pipelines and computes composite scores."""

    def __init__(
        self,
        semantic_judge: SemanticJudge | None = None,
        custom_evaluator_repo: CustomEvaluatorRepository | None = None,
    ) -> None:
        self._semantic_judge = semantic_judge
        self._custom_evaluator_repo = custom_evaluator_repo

    def evaluate_suite(
        self,
        suite: EvaluationSuite,
        trace: Trace,
    ) -> CompositeEvaluationResult:
        """Run all suite evaluators on trace in order, weight results, and compute score."""
        trace_id = trace.trace_id if isinstance(trace.trace_id, UUID) else UUID(str(trace.trace_id))

        if not suite.evaluators:
            return CompositeEvaluationResult(
                composite_result_id=uuid4(),
                suite_id=suite.suite_id,
                project_id=suite.project_id or trace.project_id,
                trace_id=trace_id,
                aggregate_score=1.0,
                passed=True,
                metric_scores=(),
            )

        total_weight = sum(ev.weight for ev in suite.evaluators)
        if total_weight <= 0.0:
            total_weight = float(len(suite.evaluators))

        # Separate deterministic vs semantic
        deterministic_refs: list[EvaluatorConfigRef] = []
        semantic_refs: list[EvaluatorConfigRef] = []
        for ev in suite.evaluators:
            if ev.evaluator_type.lower() == "semantic":
                semantic_refs.append(ev)
            else:
                deterministic_refs.append(ev)

        ordered_evaluators = deterministic_refs + semantic_refs
        metric_scores: list[MetricScore] = []
        aggregate_score = 0.0

        for ev in ordered_evaluators:
            norm_weight = ev.weight / total_weight
            raw_score, details = self._run_evaluator(ev, trace)
            weighted_score = round(raw_score * norm_weight, 4)
            passed = raw_score >= ev.threshold

            aggregate_score += weighted_score

            metric_scores.append(
                MetricScore(
                    evaluator_name=ev.evaluator_name,
                    evaluator_version=ev.evaluator_version,
                    evaluator_type=ev.evaluator_type,
                    raw_score=round(raw_score, 4),
                    weight=round(norm_weight, 4),
                    weighted_score=weighted_score,
                    threshold=ev.threshold,
                    passed=passed,
                    details=details,
                )
            )

        aggregate_score = round(min(1.0, max(0.0, aggregate_score)), 4)
        suite_passed = aggregate_score >= suite.passing_threshold

        return CompositeEvaluationResult(
            composite_result_id=uuid4(),
            suite_id=suite.suite_id,
            project_id=suite.project_id or trace.project_id,
            trace_id=trace_id,
            aggregate_score=aggregate_score,
            passed=suite_passed,
            metric_scores=tuple(metric_scores),
        )

    def _run_evaluator(
        self,
        ev: EvaluatorConfigRef,
        trace: Trace,
    ) -> tuple[float, dict[str, Any]]:
        # 0. Check for custom evaluator plugin in repository
        if self._custom_evaluator_repo is not None:
            plugin = self._custom_evaluator_repo.find_by_name(
                project_id=trace.project_id,
                name=ev.evaluator_name,
                version=ev.evaluator_version,
            )
            if plugin is not None:
                ctx = EvaluatorContext.from_trace(trace)
                res = execute_custom_evaluator(plugin.code_body, ctx, ev.parameters)
                return res.score, {
                    "findings": res.findings,
                    "details": res.details,
                    "is_custom_plugin": True,
                }

        name = ev.evaluator_name.lower()

        # 1. Latency evaluator
        if "latency" in name:
            evaluator = LatencyEvaluator()
            res_l = evaluator.evaluate(trace, ev.parameters)
            penalty = len(res_l.findings) * 0.2
            score = max(0.0, 1.0 - penalty)
            return score, {
                "findings_count": len(res_l.findings),
                "result_status": str(res_l.result_status),
            }

        # 2. Reliability evaluator
        if "reliability" in name or "error" in name:
            evaluator_r = ReliabilityEvaluator()
            res_r = evaluator_r.evaluate(trace, ev.parameters)
            raw_err = res_r.metrics.get("error_rate")
            err_rate = float(raw_err) if isinstance(raw_err, (int, float, str)) else 0.0
            score_r = max(0.0, 1.0 - err_rate)
            return score_r, {
                "findings_count": len(res_r.findings),
                "metrics": dict(res_r.metrics),
            }

        # 3. Usage evaluator
        if "usage" in name or "token" in name:
            evaluator_u = UsageEvaluator()
            res_u = evaluator_u.evaluate(trace, ev.parameters)
            return 1.0, {"metrics": dict(res_u.metrics)}

        # 4. Retrieval evaluator
        if "retrieval" in name:
            evaluator_ret = RetrievalRankingEvaluator()
            res_ret = evaluator_ret.evaluate(trace, ev.parameters)
            penalty_ret = len(res_ret.findings) * 0.25
            return max(0.0, 1.0 - penalty_ret), {"findings_count": len(res_ret.findings)}

        # Default fallback: error absence check
        has_errors = any(str(s.status).lower() == "error" for s in trace.spans)
        default_score = 0.5 if has_errors else 1.0
        return default_score, {"has_errors": has_errors}
