"""M10 deterministic policy, delta, and provenance rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentlens.regression.metric_registry import compatible_measurements, get_metric
from agentlens.regression.models import MetricRule, RegressionPolicy
from agentlens.regression.repository import build_comparison_result


def _case(case_id: str, duration: float) -> dict[str, object]:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    ended = started.timestamp() + duration / 1000
    ended_at = datetime.fromtimestamp(ended, UTC).isoformat()
    return {
        "case_id": case_id,
        "position": 0,
        "baseline_execution": {"execution_id": "b", "status": "succeeded"},
        "candidate_execution": {"execution_id": "c", "status": "succeeded"},
        "baseline_trace": {"started_at": started.isoformat(), "ended_at": ended_at, "status": "ok"},
        "candidate_trace": {
            "started_at": started.isoformat(),
            "ended_at": ended_at,
            "status": "ok",
        },
        "baseline_evaluations": [],
        "candidate_evaluations": [],
    }


def test_policy_rejects_duplicate_rules_and_unknown_metric() -> None:
    with pytest.raises(ValueError, match="unique"):
        RegressionPolicy(
            project_id="p",
            name="policy",
            rules=(
                MetricRule("same", "trace.duration_ms.mean", direction="lower_is_better"),
                MetricRule("same", "trace.duration_ms.p95", direction="lower_is_better"),
            ),
        )


def test_comparison_uses_direction_tolerance_and_baseline_zero_relative_null() -> None:
    policy = RegressionPolicy(
        project_id="p",
        name="quality",
        rules=(
            MetricRule(
                "latency",
                "trace.duration_ms.mean",
                direction="lower_is_better",
                relative_tolerance=0.1,
            ),
            MetricRule(
                "quality",
                "replay.execution_success_rate",
                direction="higher_is_better",
            ),
        ),
    )
    cases = [_case("00000000-0000-0000-0000-000000000001", 1000)]
    cases[0]["baseline_execution"] = {"execution_id": "b", "status": "failed"}
    cases[0]["candidate_execution"] = {"execution_id": "c", "status": "succeeded"}
    cases[0]["baseline_trace"] = None
    result = build_comparison_result(
        {"run": {"baseline_manifest": {}, "candidate_manifest": {}}, "cases": cases}, policy
    )
    by_metric = {item["metric_id"]: item for item in result["metrics"]}
    assert by_metric["trace.duration_ms.mean"]["classification"] == "insufficient_data"
    assert by_metric["replay.execution_success_rate"]["classification"] == "improved"
    assert by_metric["replay.execution_success_rate"]["relative_delta"] is None


def test_provenance_excludes_only_retrieval_span_id() -> None:
    definition = get_metric("retrieval.precision_at_5")
    base = [
        {
            "evaluation_type": "retrieval_ranking",
            "evaluator_name": "r",
            "evaluator_version": "1",
            "config": {"top_k": 5, "span_id": "a"},
        }
    ]
    candidate = [
        {
            "evaluation_type": "retrieval_ranking",
            "evaluator_name": "r",
            "evaluator_version": "1",
            "config": {"top_k": 5, "span_id": "b"},
        }
    ]
    assert compatible_measurements(base, candidate, definition) == (True, None)
    candidate[0]["config"] = {"top_k": 10, "span_id": "b"}
    assert compatible_measurements(base, candidate, definition)[0] is False
