"""M11 deterministic policy-to-decision rules."""

from __future__ import annotations

from agentlens.quality_gates.engine import evaluate_gate
from agentlens.quality_gates.models import (
    EvidenceHandling,
    GateRule,
    GateSourceType,
    GateStatus,
    QualityGatePolicy,
)


def report(
    *,
    latency_classification: str = "regressed",
    latency_limit: str = "violated",
    include_quality: bool = True,
    replay_mode: str = "controlled",
) -> dict[str, object]:
    metrics: list[dict[str, object]] = [
        {
            "comparison_id": "latency-comparison",
            "metric_id": "trace.duration_ms.p95",
            "rule_id": "m10-latency",
            "baseline_value": 800.0,
            "candidate_value": 1500.0,
            "absolute_delta": 700.0,
            "relative_delta": 0.875,
            "classification": latency_classification,
            "candidate_limit_status": latency_limit,
            "baseline_samples": 2,
            "candidate_samples": 2,
            "provenance": {"source": "trace_duration"},
        }
    ]
    if include_quality:
        metrics.insert(
            0,
            {
                "comparison_id": "quality-comparison",
                "metric_id": "agent.task_success",
                "rule_id": "m10-quality",
                "baseline_value": 0.5,
                "candidate_value": 1.0,
                "absolute_delta": 0.5,
                "relative_delta": 1.0,
                "classification": "improved",
                "candidate_limit_status": "not_configured",
                "baseline_samples": 2,
                "candidate_samples": 2,
                "provenance": {
                    "source": "agent_task_success",
                    "evaluator_name": "agent-task",
                    "evaluator_version": "1",
                    "judge_provenance": [],
                },
            },
        )
    return {
        "run": {
            "project_id": "project-a",
            "regression_run_id": "regression-a",
            "dataset_id": "dataset-a",
            "dataset_version_id": "version-a",
            "dataset_checksum": "a" * 64,
            "baseline_replay_run_id": "baseline-a",
            "candidate_replay_run_id": "candidate-a",
            "report_schema_version": "agentlens-regression-report-v1",
            "comparison_engine_version": "1.0.0",
            "baseline_manifest": {"replay_mode": "exact"},
            "candidate_manifest": {"replay_mode": replay_mode},
        },
        "metrics": metrics,
        "cases": [{"case_id": "case-a", "status": "compared"}],
    }


def policy(*rules: GateRule) -> QualityGatePolicy:
    return QualityGatePolicy(project_id="project-a", name="release", rules=rules)


def rule(
    name: str,
    metric_id: str,
    *,
    blocking: bool = True,
    on_missing: EvidenceHandling = EvidenceHandling.INDETERMINATE,
    on_incompatible: EvidenceHandling = EvidenceHandling.INDETERMINATE,
) -> GateRule:
    return GateRule(
        gate_rule_id=name,
        name=name,
        source_type=GateSourceType.METRIC_CLASSIFICATION,
        metric_id=metric_id,
        classifications=("regressed",),
        blocking=blocking,
        on_missing=on_missing,
        on_incompatible=on_incompatible,
    )


def test_quality_improvement_does_not_cancel_blocking_latency_regression() -> None:
    decision = evaluate_gate(
        report(),
        policy(
            rule("quality", "agent.task_success"),
            rule("latency", "trace.duration_ms.p95"),
        ),
    )
    assert decision["status"] == GateStatus.FAILED.value
    assert decision["blocking_failure_count"] == 1
    assert [item["status"] for item in decision["rule_results"]] == ["passed", "failed"]


def test_latency_advisory_passes_with_warning() -> None:
    decision = evaluate_gate(
        report(),
        policy(
            rule("quality", "agent.task_success"),
            rule("latency", "trace.duration_ms.p95", blocking=False),
        ),
    )
    assert decision["status"] == GateStatus.PASSED.value
    assert decision["advisory_failure_count"] == 1


def test_missing_evidence_behavior_is_explicit() -> None:
    for behavior, expected in (
        (EvidenceHandling.FAIL, "failed"),
        (EvidenceHandling.INDETERMINATE, "indeterminate"),
        (EvidenceHandling.IGNORE, "not_applicable"),
    ):
        decision = evaluate_gate(
            report(include_quality=False),
            policy(rule("required-quality", "agent.task_success", on_missing=behavior)),
        )
        assert decision["rule_results"][0]["status"] == expected
        assert decision["status"] == (
            "failed"
            if behavior is EvidenceHandling.FAIL
            else "indeterminate"
            if behavior is EvidenceHandling.INDETERMINATE
            else "passed"
        )


def test_incompatible_evidence_can_fail_without_numeric_comparison() -> None:
    decision = evaluate_gate(
        report(latency_classification="incompatible"),
        policy(
            rule(
                "latency",
                "trace.duration_ms.p95",
                on_incompatible=EvidenceHandling.FAIL,
            )
        ),
    )
    assert decision["status"] == GateStatus.FAILED.value
    assert "incompatible" in decision["rule_results"][0]["message"]


def test_incompatible_evidence_precedes_candidate_limit_requirement() -> None:
    decision = evaluate_gate(
        report(latency_classification="incompatible", latency_limit="violated"),
        policy(
            GateRule(
                gate_rule_id="latency",
                name="latency",
                source_type=GateSourceType.METRIC_CLASSIFICATION,
                metric_id="trace.duration_ms.p95",
                classifications=("regressed",),
                require_candidate_limit_ok=True,
                on_incompatible=EvidenceHandling.FAIL,
            )
        ),
    )
    assert decision["status"] == GateStatus.FAILED.value
    assert "incompatible" in decision["rule_results"][0]["message"]
    assert "candidate limit" not in decision["rule_results"][0]["message"]


def test_many_blocking_failures_are_counted_independently() -> None:
    decision = evaluate_gate(
        report(),
        policy(
            rule("latency-a", "trace.duration_ms.p95"),
            rule("latency-b", "trace.duration_ms.p95"),
        ),
    )
    assert decision["status"] == GateStatus.FAILED.value
    assert decision["blocking_failure_count"] == 2


def test_advisory_indeterminate_does_not_fail_gate() -> None:
    decision = evaluate_gate(
        report(include_quality=False),
        policy(
            rule(
                "optional-quality",
                "agent.task_success",
                blocking=False,
                on_missing=EvidenceHandling.INDETERMINATE,
            )
        ),
    )
    assert decision["status"] == GateStatus.PASSED.value
    assert decision["indeterminate_count"] == 1


def test_execution_failure_rule_blocks_failed_replay_cases() -> None:
    broken = report()
    broken["cases"] = [{"case_id": "case-a", "status": "failed"}]
    decision = evaluate_gate(
        broken,
        policy(
            GateRule(
                gate_rule_id="execution",
                name="execution failures",
                source_type=GateSourceType.EXECUTION_FAILURE,
            )
        ),
    )
    assert decision["status"] == GateStatus.FAILED.value


def test_hard_limit_blocks_even_when_metric_improves() -> None:
    decision = evaluate_gate(
        report(latency_classification="improved", latency_limit="violated"),
        policy(
            GateRule(
                gate_rule_id="latency-limit",
                name="latency limit",
                source_type=GateSourceType.CANDIDATE_LIMIT,
                metric_id="trace.duration_ms.p95",
                candidate_limit_status="violated",
            )
        ),
    )
    assert decision["status"] == GateStatus.FAILED.value


def test_replay_mode_requirement_rejects_best_effort() -> None:
    decision = evaluate_gate(
        report(replay_mode="best_effort"),
        policy(
            GateRule(
                gate_rule_id="replay-quality",
                name="controlled replay required",
                source_type=GateSourceType.REPLAY_REPRODUCIBILITY,
                replay_modes={"baseline": ("exact", "controlled"), "candidate": ("controlled",)},
            )
        ),
    )
    assert decision["status"] == GateStatus.FAILED.value
