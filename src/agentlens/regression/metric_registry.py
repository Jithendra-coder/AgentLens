"""Trusted M10 metric definitions and measurement compatibility."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean
from typing import cast

from agentlens.evaluation.results import canonical_json_fingerprint

from .models import MetricDirection, numeric


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    direction: MetricDirection
    source: str
    evaluator_type: str | None = None
    metric_key: str | None = None
    aggregation: str = "mean"
    unit: str = "number"


_METRICS: dict[str, MetricDefinition] = {
    "trace.duration_ms.mean": MetricDefinition(
        "trace.duration_ms.mean",
        MetricDirection.LOWER_IS_BETTER,
        "trace_duration",
        aggregation="mean",
        unit="ms",
    ),
    "trace.duration_ms.p50": MetricDefinition(
        "trace.duration_ms.p50",
        MetricDirection.LOWER_IS_BETTER,
        "trace_duration",
        aggregation="p50",
        unit="ms",
    ),
    "trace.duration_ms.p95": MetricDefinition(
        "trace.duration_ms.p95",
        MetricDirection.LOWER_IS_BETTER,
        "trace_duration",
        aggregation="p95",
        unit="ms",
    ),
    "trace.duration_ms.p99": MetricDefinition(
        "trace.duration_ms.p99",
        MetricDirection.LOWER_IS_BETTER,
        "trace_duration",
        aggregation="p99",
        unit="ms",
    ),
    "replay.execution_success_rate": MetricDefinition(
        "replay.execution_success_rate",
        MetricDirection.HIGHER_IS_BETTER,
        "execution_success",
        aggregation="rate",
        unit="rate",
    ),
    "reliability.error_rate": MetricDefinition(
        "reliability.error_rate",
        MetricDirection.LOWER_IS_BETTER,
        "trace_error",
        aggregation="rate",
        unit="rate",
    ),
    "usage.input_tokens_reported.mean": MetricDefinition(
        "usage.input_tokens_reported.mean",
        MetricDirection.LOWER_IS_BETTER,
        "evaluation",
        "usage_summary",
        "input_tokens_reported",
        unit="tokens",
    ),
    "usage.output_tokens_reported.mean": MetricDefinition(
        "usage.output_tokens_reported.mean",
        MetricDirection.LOWER_IS_BETTER,
        "evaluation",
        "usage_summary",
        "output_tokens_reported",
        unit="tokens",
    ),
    "usage.total_tokens_reported.mean": MetricDefinition(
        "usage.total_tokens_reported.mean",
        MetricDirection.LOWER_IS_BETTER,
        "evaluation",
        "usage_summary",
        "total_tokens_reported",
        unit="tokens",
    ),
    "retrieval.precision_at_5": MetricDefinition(
        "retrieval.precision_at_5",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "retrieval_ranking",
        "precision_at_5",
        unit="rate",
    ),
    "retrieval.recall_at_5": MetricDefinition(
        "retrieval.recall_at_5",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "retrieval_ranking",
        "recall_at_5",
        unit="rate",
    ),
    "retrieval.mrr": MetricDefinition(
        "retrieval.mrr",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "retrieval_ranking",
        "mrr",
        unit="rate",
    ),
    "retrieval.ndcg_at_5": MetricDefinition(
        "retrieval.ndcg_at_5",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "retrieval_ranking",
        "ndcg_at_5",
        unit="rate",
    ),
    "rag.groundedness": MetricDefinition(
        "rag.groundedness",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "rag_groundedness",
        "groundedness",
        unit="rate",
    ),
    "rag.mean_context_relevance": MetricDefinition(
        "rag.mean_context_relevance",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "rag_context_relevance",
        "mean_context_relevance",
        unit="rate",
    ),
    "tool.success_rate": MetricDefinition(
        "tool.success_rate",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "reliability_summary",
        "tool_success_rate",
        unit="rate",
    ),
    "agent.task_success": MetricDefinition(
        "agent.task_success",
        MetricDirection.HIGHER_IS_BETTER,
        "evaluation",
        "agent_task_success",
        "task_success",
        unit="rate",
    ),
}


def metric_registry() -> Mapping[str, MetricDefinition]:
    return _METRICS


def get_metric(metric_id: str) -> MetricDefinition:
    try:
        return _METRICS[metric_id]
    except KeyError:
        raise ValueError(f"unknown metric: {metric_id}") from None


def normalize_measurement_config(
    evaluation_type: str, config: Mapping[str, object]
) -> Mapping[str, object]:
    """Apply only evaluator-owned compatibility exclusions."""

    normalized = dict(config)
    if evaluation_type == "retrieval_ranking":
        normalized.pop("span_id", None)
    return normalized


def measurement_spec_fingerprint(
    *,
    evaluation_type: str,
    evaluator_name: str,
    evaluator_version: str,
    config: Mapping[str, object],
    metric_id: str,
) -> str:
    return canonical_json_fingerprint(
        {
            "metric_id": metric_id,
            "evaluation_type": evaluation_type,
            "evaluator_name": evaluator_name,
            "evaluator_version": evaluator_version,
            "config": normalize_measurement_config(evaluation_type, config),
        }
    )


def _judge_signature(rows: Sequence[Mapping[str, object]]) -> tuple[object, ...]:
    signatures: list[object] = []
    for row in rows:
        invocations = row.get("judge_invocations") or []
        for invocation in cast(Sequence[Mapping[str, object]], invocations):
            signatures.append(
                (
                    invocation.get("provider"),
                    invocation.get("model"),
                    invocation.get("adapter_version"),
                    invocation.get("prompt_version"),
                    canonical_json_fingerprint(invocation.get("parameters", {})),
                )
            )
    return tuple(sorted(signatures, key=repr))


def compatible_measurements(
    baseline: Sequence[Mapping[str, object]],
    candidate: Sequence[Mapping[str, object]],
    definition: MetricDefinition,
) -> tuple[bool, str | None]:
    if definition.source != "evaluation":
        return True, None
    if not baseline or not candidate:
        return True, None
    left = baseline[0]
    right = candidate[0]
    for field in ("evaluation_type", "evaluator_name", "evaluator_version"):
        if left.get(field) != right.get(field):
            return False, f"{field} differs"
    left_config = cast(Mapping[str, object], left.get("config", {}))
    right_config = cast(Mapping[str, object], right.get("config", {}))
    if normalize_measurement_config(
        str(left.get("evaluation_type")), left_config
    ) != normalize_measurement_config(str(right.get("evaluation_type")), right_config):
        return False, "measurement configuration differs"
    if _judge_signature(baseline) != _judge_signature(candidate):
        return False, "semantic judge provenance differs"
    return True, None


def extract_case_value(
    definition: MetricDefinition,
    *,
    execution: Mapping[str, object],
    trace: Mapping[str, object] | None,
    evaluations: Sequence[Mapping[str, object]],
) -> tuple[float | None, Mapping[str, object] | None]:
    if definition.source == "execution_success":
        return (1.0 if execution.get("status") == "succeeded" else 0.0), None
    if definition.source == "trace_duration":
        if trace is None or trace.get("ended_at") is None:
            return None, None
        started = trace.get("started_at")
        ended = trace.get("ended_at")
        try:
            from datetime import datetime

            duration = (
                datetime.fromisoformat(str(ended)) - datetime.fromisoformat(str(started))
            ).total_seconds() * 1000.0
            return duration if math.isfinite(duration) else None, None
        except (TypeError, ValueError):
            return None, None
    if definition.source == "trace_error":
        if trace is None:
            return None, None
        return (1.0 if trace.get("status") == "error" else 0.0), None
    if not evaluations or definition.metric_key is None:
        return None, None
    row = evaluations[0]
    metrics = row.get("metrics")
    if not isinstance(metrics, Mapping):
        return None, row
    return numeric(metrics.get(definition.metric_key)), row


def aggregate(values: Sequence[float], method: str) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if method == "mean" or method == "rate":
        return float(mean(values))
    if method == "p50":
        return _percentile(ordered, 0.50)
    if method == "p95":
        return _percentile(ordered, 0.95)
    if method == "p99":
        return _percentile(ordered, 0.99)
    raise ValueError(f"unsupported aggregation: {method}")


def _percentile(values: Sequence[float], quantile: float) -> float:
    if len(values) == 1:
        return float(values[0])
    index = (len(values) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return float(values[lower])
    weight = index - lower
    return float(values[lower] + (values[upper] - values[lower]) * weight)


def finding_keys(rows: Sequence[Mapping[str, object]]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        findings = row.get("findings") or []
        for finding in cast(Sequence[Mapping[str, object]], findings):
            code = finding.get("code")
            evidence = finding.get("evidence", {})
            if isinstance(code, str):
                digest = hashlib.sha256(
                    json.dumps(
                        evidence, sort_keys=True, separators=(",", ":"), default=str
                    ).encode()
                ).hexdigest()[:16]
                keys.add(f"{code}:{digest}")
    return keys


__all__ = [
    "MetricDefinition",
    "aggregate",
    "compatible_measurements",
    "extract_case_value",
    "finding_keys",
    "get_metric",
    "measurement_spec_fingerprint",
    "metric_registry",
    "normalize_measurement_config",
]
