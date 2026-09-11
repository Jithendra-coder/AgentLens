"""Pure, deterministic quality gate evaluation over persisted regression report facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from agentlens.domain import JSONValue
from agentlens.evaluation.results import canonical_json_fingerprint

from .models import (
    GATE_DECISION_SCHEMA_VERSION,
    QUALITY_GATE_ENGINE_VERSION,
    EvidenceHandling,
    GateRule,
    GateRuleStatus,
    GateSourceType,
    GateStatus,
    QualityGatePolicy,
)


def report_fingerprint(report: Mapping[str, object]) -> str:
    return canonical_json_fingerprint(
        {
            "run": report["run"],
            "metrics": report.get("metrics", []),
            "cases": report.get("cases", []),
        }
    )


def evaluation_fingerprint(report: Mapping[str, object], policy: QualityGatePolicy) -> str:
    return canonical_json_fingerprint(
        {
            "report_fingerprint": report_fingerprint(report),
            "policy_fingerprint": policy.content_fingerprint(),
            "quality_gate_engine_version": QUALITY_GATE_ENGINE_VERSION,
        }
    )


def _metric(metrics: Sequence[Mapping[str, object]], metric_id: str) -> Mapping[str, object] | None:
    candidates = [item for item in metrics if item.get("metric_id") == metric_id]
    return (
        sorted(candidates, key=lambda item: str(item.get("rule_id", "")))[0] if candidates else None
    )


def _result(
    rule: GateRule,
    status: GateRuleStatus,
    source_reference: Mapping[str, object],
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    message: str,
) -> dict[str, JSONValue]:
    return {
        "rule_id": rule.gate_rule_id,
        "rule_name": rule.name,
        "blocking": rule.blocking,
        "status": status.value,
        "source_reference": cast(JSONValue, dict(source_reference)),
        "expected_condition": cast(JSONValue, dict(expected)),
        "actual_condition": cast(JSONValue, dict(actual)),
        "message": message,
    }


def _evidence_result(
    rule: GateRule,
    *,
    behavior: EvidenceHandling,
    reason: str,
    source_reference: Mapping[str, object],
    expected: Mapping[str, object],
    actual: Mapping[str, object],
) -> dict[str, JSONValue]:
    if behavior is EvidenceHandling.IGNORE:
        status = GateRuleStatus.NOT_APPLICABLE
        message = f"{reason}; policy explicitly ignores this evidence."
    elif behavior is EvidenceHandling.FAIL:
        status = GateRuleStatus.FAILED
        message = f"{reason}; policy maps unavailable evidence to failure."
    else:
        status = GateRuleStatus.INDETERMINATE
        message = f"{reason}; policy maps unavailable evidence to indeterminate."
    return _result(rule, status, source_reference, expected, actual, message)


def _metric_rule(rule: GateRule, metrics: Sequence[Mapping[str, object]]) -> dict[str, JSONValue]:
    assert rule.metric_id is not None
    metric = _metric(metrics, rule.metric_id)
    reference: dict[str, object] = {"source": rule.source_type.value, "metric_id": rule.metric_id}
    expected: dict[str, object] = {"classification": list(rule.classifications)}
    if metric is None:
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=(
                f"Required metric {rule.metric_id} is missing from the immutable regression report"
            ),
            source_reference=reference,
            expected=expected,
            actual={"available": False},
        )
    actual = {
        "available": True,
        "classification": metric.get("classification"),
        "baseline_value": metric.get("baseline_value"),
        "candidate_value": metric.get("candidate_value"),
        "absolute_delta": metric.get("absolute_delta"),
        "relative_delta": metric.get("relative_delta"),
        "candidate_limit_status": metric.get("candidate_limit_status"),
        "baseline_samples": metric.get("baseline_samples"),
        "candidate_samples": metric.get("candidate_samples"),
        "provenance": metric.get("provenance", {}),
    }
    reference["comparison_id"] = metric.get("comparison_id")
    classification: object = metric.get("classification")
    if classification == "incompatible":
        return _evidence_result(
            rule,
            behavior=rule.on_incompatible,
            reason=f"Metric {rule.metric_id} is incompatible under provenance compatibility",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    if classification in {"insufficient_data", None}:
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=f"Metric {rule.metric_id} does not contain sufficient M10 evidence",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    if rule.require_candidate_limit_ok:
        expected["candidate_limit_status"] = "satisfied"
        limit_status = metric.get("candidate_limit_status")
        if limit_status == "not_configured":
            return _evidence_result(
                rule,
                behavior=rule.on_missing,
                reason=f"Candidate limit for {rule.metric_id} is required but not configured",
                source_reference=reference,
                expected=expected,
                actual=actual,
            )
        if limit_status == "violated":
            return _result(
                rule,
                GateRuleStatus.FAILED,
                reference,
                expected,
                actual,
                f"{rule.metric_id} candidate limit is violated; release policy blocks it.",
            )
    if classification in rule.classifications:
        return _result(
            rule,
            GateRuleStatus.FAILED,
            reference,
            expected,
            actual,
            f"{rule.metric_id} classification is {classification}; "
            "release policy blocks this outcome.",
        )
    return _result(
        rule,
        GateRuleStatus.PASSED,
        reference,
        expected,
        actual,
        f"{rule.metric_id} classification is {classification}; no blocking outcome matched.",
    )


def _limit_rule(rule: GateRule, metrics: Sequence[Mapping[str, object]]) -> dict[str, JSONValue]:
    assert rule.metric_id is not None
    metric = _metric(metrics, rule.metric_id)
    reference: dict[str, object] = {"source": rule.source_type.value, "metric_id": rule.metric_id}
    expected = {"candidate_limit_status": rule.candidate_limit_status or "violated"}
    if metric is None:
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=f"Candidate-limit evidence for {rule.metric_id} is missing",
            source_reference=reference,
            expected=expected,
            actual={"available": False},
        )
    actual = {
        "available": True,
        "candidate_limit_status": metric.get("candidate_limit_status"),
        "candidate_value": metric.get("candidate_value"),
        "provenance": metric.get("provenance", {}),
    }
    reference["comparison_id"] = metric.get("comparison_id")
    if metric.get("candidate_limit_status") == "not_configured":
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=f"Candidate limit for {rule.metric_id} is not configured in M10",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    if metric.get("candidate_limit_status") == rule.candidate_limit_status:
        return _result(
            rule,
            GateRuleStatus.FAILED,
            reference,
            expected,
            actual,
            f"{rule.metric_id} candidate limit is "
            f"{metric.get('candidate_limit_status')}; release policy blocks it.",
        )
    return _result(
        rule,
        GateRuleStatus.PASSED,
        reference,
        expected,
        actual,
        f"{rule.metric_id} candidate limit is "
        f"{metric.get('candidate_limit_status')}; limit requirement passed.",
    )


def _required_metric_rule(
    rule: GateRule, metrics: Sequence[Mapping[str, object]]
) -> dict[str, JSONValue]:
    assert rule.metric_id is not None
    metric = _metric(metrics, rule.metric_id)
    reference: dict[str, object] = {"source": rule.source_type.value, "metric_id": rule.metric_id}
    expected = {"required": True}
    if metric is None:
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=f"Required metric {rule.metric_id} is missing from the M10 report",
            source_reference=reference,
            expected=expected,
            actual={"available": False},
        )
    actual = {
        "available": True,
        "classification": metric.get("classification"),
        "provenance": metric.get("provenance", {}),
    }
    reference["comparison_id"] = metric.get("comparison_id")
    if metric.get("classification") == "incompatible":
        return _evidence_result(
            rule,
            behavior=rule.on_incompatible,
            reason=f"Required metric {rule.metric_id} is incompatible under M10",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    if metric.get("classification") == "insufficient_data":
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=f"Required metric {rule.metric_id} has insufficient M10 data",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    return _result(
        rule,
        GateRuleStatus.PASSED,
        reference,
        expected,
        actual,
        f"Required metric {rule.metric_id} is available in the M10 report.",
    )


def _count_rule(rule: GateRule, metrics: Sequence[Mapping[str, object]]) -> dict[str, JSONValue]:
    selected = [item for item in metrics if item.get("metric_id") in rule.metric_ids]
    actual_count = sum(1 for item in selected if item.get("classification") == "regressed")
    reference = {"source": rule.source_type.value, "metric_ids": list(rule.metric_ids)}
    expected = {"maximum_regressions": rule.maximum_regressions}
    actual: dict[str, object] = {
        "selected_metrics": len(selected),
        "regression_count": actual_count,
    }
    if len(selected) != len(rule.metric_ids):
        missing = sorted(set(rule.metric_ids) - {str(item.get("metric_id")) for item in selected})
        actual["missing_metrics"] = missing
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=f"Regression-count rule is missing selected metrics: {', '.join(missing)}",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    if actual_count > cast(int, rule.maximum_regressions):
        return _result(
            rule,
            GateRuleStatus.FAILED,
            reference,
            expected,
            actual,
            f"Selected metrics contain {actual_count} regressions; "
            f"policy allows {rule.maximum_regressions}.",
        )
    return _result(
        rule,
        GateRuleStatus.PASSED,
        reference,
        expected,
        actual,
        f"Selected metrics contain {actual_count} regressions; "
        f"policy allows {rule.maximum_regressions}.",
    )


def _replay_rule(rule: GateRule, run: Mapping[str, object]) -> dict[str, JSONValue]:
    reference = {"source": rule.source_type.value}
    expected = {"replay_modes": {key: list(value) for key, value in rule.replay_modes.items()}}
    actual: dict[str, object] = {}
    missing: list[str] = []
    failures: list[str] = []
    for participant, allowed in rule.replay_modes.items():
        manifest = run.get(f"{participant}_manifest")
        mode = manifest.get("replay_mode") if isinstance(manifest, Mapping) else None
        actual[participant] = mode
        if not isinstance(mode, str):
            missing.append(participant)
        elif mode not in allowed:
            failures.append(f"{participant}={mode} (allowed: {', '.join(allowed)})")
    if missing:
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason=f"Replay reproducibility mode is missing for {', '.join(missing)}",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    if failures:
        return _result(
            rule,
            GateRuleStatus.FAILED,
            reference,
            expected,
            actual,
            f"Replay reproducibility requirement failed: {'; '.join(failures)}.",
        )
    return _result(
        rule,
        GateRuleStatus.PASSED,
        reference,
        expected,
        actual,
        "Required replay reproducibility modes are satisfied.",
    )


def _execution_rule(rule: GateRule, cases: Sequence[Mapping[str, object]]) -> dict[str, JSONValue]:
    reference = {"source": rule.source_type.value}
    expected = {"execution_failures": 0}
    failures = [str(case.get("case_id")) for case in cases if case.get("status") != "compared"]
    actual = {"execution_failure_count": len(failures), "case_ids": failures}
    if not cases:
        return _evidence_result(
            rule,
            behavior=rule.on_missing,
            reason="Execution-failure evidence is missing from the M10 report",
            source_reference=reference,
            expected=expected,
            actual=actual,
        )
    if failures:
        return _result(
            rule,
            GateRuleStatus.FAILED,
            reference,
            expected,
            actual,
            f"M10 contains {len(failures)} replay case execution failure(s).",
        )
    return _result(
        rule,
        GateRuleStatus.PASSED,
        reference,
        expected,
        actual,
        "All paired replay case executions completed.",
    )


def evaluate_gate(
    report: Mapping[str, object],
    policy: QualityGatePolicy,
    *,
    decision_id: UUID | None = None,
    created_at: datetime | None = None,
) -> dict[str, object]:
    """Evaluate immutable M10 facts without recalculating any metric."""

    run = cast(Mapping[str, object], report["run"])
    metrics = cast(Sequence[Mapping[str, object]], report.get("metrics", []))
    cases = cast(Sequence[Mapping[str, object]], report.get("cases", []))
    results: list[dict[str, JSONValue]] = []
    for rule in policy.rules:
        if rule.source_type is GateSourceType.METRIC_CLASSIFICATION:
            result = _metric_rule(rule, metrics)
        elif rule.source_type is GateSourceType.CANDIDATE_LIMIT:
            result = _limit_rule(rule, metrics)
        elif rule.source_type is GateSourceType.REQUIRED_METRIC_AVAILABILITY:
            result = _required_metric_rule(rule, metrics)
        elif rule.source_type is GateSourceType.REGRESSION_COUNT:
            result = _count_rule(rule, metrics)
        elif rule.source_type is GateSourceType.REPLAY_REPRODUCIBILITY:
            result = _replay_rule(rule, run)
        else:
            result = _execution_rule(rule, cases)
        results.append(result)
    blocking_failed = sum(
        1
        for result in results
        if result["blocking"] and result["status"] == GateRuleStatus.FAILED.value
    )
    advisory_failed = sum(
        1
        for result in results
        if not result["blocking"] and result["status"] == GateRuleStatus.FAILED.value
    )
    indeterminate = sum(
        1 for result in results if result["status"] == GateRuleStatus.INDETERMINATE.value
    )
    blocking_indeterminate = any(
        result["blocking"] and result["status"] == GateRuleStatus.INDETERMINATE.value
        for result in results
    )
    if blocking_failed:
        status = GateStatus.FAILED
    elif blocking_indeterminate:
        status = GateStatus.INDETERMINATE
    else:
        status = GateStatus.PASSED
    now = created_at or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    decision_uuid = decision_id or uuid4()
    return {
        "gate_decision_id": str(decision_uuid),
        "project_id": run["project_id"],
        "regression_run_id": run["regression_run_id"],
        "gate_policy_id": str(policy.gate_policy_id),
        "gate_policy_version": policy.version,
        "gate_policy_fingerprint": policy.content_fingerprint(),
        "decision_schema_version": GATE_DECISION_SCHEMA_VERSION,
        "status": status.value,
        "created_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "blocking_failure_count": blocking_failed,
        "advisory_failure_count": advisory_failed,
        "indeterminate_count": indeterminate,
        "rule_results": cast(JSONValue, results),
        "dataset_id": run["dataset_id"],
        "dataset_version_id": run["dataset_version_id"],
        "dataset_checksum": run["dataset_checksum"],
        "baseline_replay_run_id": run["baseline_replay_run_id"],
        "candidate_replay_run_id": run["candidate_replay_run_id"],
        "regression_report_schema": run["report_schema_version"],
        "regression_report_fingerprint": report_fingerprint(report),
        "comparison_engine_version": run["comparison_engine_version"],
        "quality_gate_engine_version": QUALITY_GATE_ENGINE_VERSION,
        "evaluation_fingerprint": evaluation_fingerprint(report, policy),
    }


__all__ = ["evaluate_gate", "evaluation_fingerprint", "report_fingerprint"]
