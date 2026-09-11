"""Lightweight deterministic evaluators; no network or model calls."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import cast
from uuid import UUID

from agentlens.domain import Status, Trace
from agentlens.domain.types import JSONValue, freeze_payload, thaw_payload, validate_json_value

from .results import (
    EvaluationFinding,
    EvaluationResultPayload,
    FindingSeverity,
    ResultStatus,
    invalid_input_result,
)


def _normalized_config(config: Mapping[str, object]) -> dict[str, JSONValue]:
    raw = dict(config)
    validate_json_value(raw, "config")
    frozen = freeze_payload(raw, "config")
    return cast(dict[str, JSONValue], thaw_payload(frozen))


def _empty_config(config: Mapping[str, object]) -> dict[str, JSONValue]:
    normalized = _normalized_config(config)
    return normalized


class LatencyEvaluator:
    evaluation_type = "latency_summary"
    evaluator_name = "agentlens.latency"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _empty_config(config)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        del config
        completed = [span for span in trace.spans if span.ended_at is not None]
        unfinished = [span for span in trace.spans if span.ended_at is None]
        by_type: dict[str, float] = {}
        count_by_type: dict[str, int] = {}
        durations: list[float] = []
        for span in trace.spans:
            span_type = str(span.span_type)
            count_by_type[span_type] = count_by_type.get(span_type, 0) + 1
            if span.ended_at is not None:
                duration = (span.ended_at - span.started_at).total_seconds() * 1000.0
                durations.append(duration)
                by_type[span_type] = by_type.get(span_type, 0.0) + duration
        findings: list[EvaluationFinding] = []
        if trace.ended_at is None:
            findings.append(
                EvaluationFinding(
                    code="trace_incomplete",
                    severity=FindingSeverity.WARNING,
                    message="Trace duration is unavailable because the trace is unfinished.",
                    evidence={"trace_id": str(trace.trace_id)},
                )
            )
        metrics: dict[str, JSONValue] = {
            "trace_duration_ms": (
                (trace.ended_at - trace.started_at).total_seconds() * 1000.0
                if trace.ended_at is not None
                else None
            ),
            "completed_span_count": len(completed),
            "unfinished_span_count": len(unfinished),
            "span_duration_sum_ms": sum(durations),
            "longest_span_duration_ms": max(durations) if durations else None,
            "span_duration_by_type_ms": cast(JSONValue, by_type),
            "span_count_by_type": cast(JSONValue, count_by_type),
        }
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics=metrics,
            findings=tuple(findings),
            evidence={"trace_id": str(trace.trace_id)},
        )


class UsageEvaluator:
    evaluation_type = "usage_summary"
    evaluator_name = "agentlens.usage"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _empty_config(config)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        del config
        usage_spans = [span.usage for span in trace.spans if span.usage is not None]

        def reported(field: str) -> int | None:
            values = [getattr(usage, field) for usage in usage_spans]
            present = [value for value in values if value is not None]
            return sum(cast(list[int], present)) if present else None

        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "spans_with_usage": len(usage_spans),
                "input_tokens_reported": reported("input_tokens"),
                "output_tokens_reported": reported("output_tokens"),
                "total_tokens_reported": reported("total_tokens"),
                "cached_tokens_reported": reported("cached_tokens"),
                "reasoning_tokens_reported": reported("reasoning_tokens"),
            },
            evidence={"trace_id": str(trace.trace_id)},
        )


class ReliabilityEvaluator:
    evaluation_type = "reliability_summary"
    evaluator_name = "agentlens.reliability"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _empty_config(config)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        del config
        ok_count = sum(span.status == Status.OK for span in trace.spans)
        error_count = sum(span.status == Status.ERROR for span in trace.spans)
        unset_count = sum(span.status == Status.UNSET for span in trace.spans)
        terminal_count = ok_count + error_count
        error_types: dict[str, int] = {}
        for span in trace.spans:
            if span.error is not None:
                error_types[span.error.error_type] = error_types.get(span.error.error_type, 0) + 1
        tool_spans = [span for span in trace.spans if str(span.span_type) == "tool"]
        tool_ok = sum(span.status == Status.OK for span in tool_spans)
        tool_error = sum(span.status == Status.ERROR for span in tool_spans)
        tool_terminal = tool_ok + tool_error
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "span_count": len(trace.spans),
                "terminal_span_count": terminal_count,
                "ok_span_count": ok_count,
                "error_span_count": error_count,
                "unset_span_count": unset_count,
                "error_rate": error_count / terminal_count if terminal_count else None,
                "trace_error": trace.status == Status.ERROR,
                "error_type_counts": cast(JSONValue, error_types),
                "tool_span_count": len(tool_spans),
                "tool_terminal_count": tool_terminal,
                "tool_ok_count": tool_ok,
                "tool_error_count": tool_error,
                "tool_success_rate": tool_ok / tool_terminal if tool_terminal else None,
            },
            evidence={"trace_id": str(trace.trace_id)},
        )


def _retrieval_invalid(reason: str, span_id: object = None) -> EvaluationResultPayload:
    evidence: dict[str, JSONValue] = {"reason": reason}
    if isinstance(span_id, str):
        evidence["span_id"] = span_id
    return invalid_input_result(
        "invalid_retrieval_input",
        "Retrieval ranking input is invalid.",
        evidence,
    )


class RetrievalRankingEvaluator:
    evaluation_type = "retrieval_ranking"
    evaluator_name = "agentlens.retrieval_ranking"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        normalized = _normalized_config(config)
        k_values = normalized.get("k_values")
        if isinstance(k_values, list) and all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in k_values
        ):
            normalized["k_values"] = cast(
                JSONValue,
                sorted(set(cast(list[int], k_values))),
            )
        relevant = normalized.get("relevant_document_ids")
        if isinstance(relevant, list) and all(isinstance(value, str) for value in relevant):
            normalized["relevant_document_ids"] = cast(
                JSONValue,
                sorted(set(cast(list[str], relevant))),
            )
        return normalized

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        span_id_value = config.get("span_id")
        relevant_value = config.get("relevant_document_ids")
        k_values_value = config.get("k_values")
        if not isinstance(span_id_value, str):
            return _retrieval_invalid("span_id_missing_or_invalid")
        try:
            span_id = UUID(span_id_value)
        except ValueError:
            return _retrieval_invalid("span_id_invalid", span_id_value)
        if not isinstance(relevant_value, list) or not relevant_value:
            return _retrieval_invalid("relevant_document_ids_empty_or_invalid", span_id_value)
        if any(not isinstance(value, str) or not value for value in relevant_value):
            return _retrieval_invalid("relevant_document_ids_invalid", span_id_value)
        relevant = [cast(str, value) for value in relevant_value]
        if len(set(relevant)) != len(relevant):
            return _retrieval_invalid("relevant_document_ids_duplicate", span_id_value)
        if not isinstance(k_values_value, list) or not k_values_value:
            return _retrieval_invalid("k_values_empty_or_invalid", span_id_value)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 1000
            for value in k_values_value
        ):
            return _retrieval_invalid("k_values_invalid", span_id_value)
        k_values = sorted(set(cast(list[int], k_values_value)))
        if len(k_values) != len(k_values_value):
            return _retrieval_invalid("k_values_duplicate", span_id_value)
        span = next((item for item in trace.spans if item.span_id == span_id), None)
        if span is None:
            return _retrieval_invalid("span_not_found", span_id_value)
        if str(span.span_type) != "retrieval":
            return _retrieval_invalid("span_type_must_be_retrieval", span_id_value)
        documents = span.output.get("documents") if isinstance(span.output, Mapping) else None
        if not isinstance(documents, (list, tuple)):
            return _retrieval_invalid("documents_missing_or_invalid", span_id_value)
        retrieved: list[str] = []
        for document in documents:
            if not isinstance(document, Mapping):
                return _retrieval_invalid("document_invalid", span_id_value)
            document_id = document.get("id")
            if not isinstance(document_id, str) or not document_id:
                return _retrieval_invalid("document_id_invalid", span_id_value)
            if document_id in retrieved:
                return _retrieval_invalid("retrieved_document_ids_duplicate", span_id_value)
            retrieved.append(document_id)
        relevant_set = set(relevant)
        metrics: dict[str, JSONValue] = {}
        for k in k_values:
            top_k = retrieved[:k]
            hits = sum(document_id in relevant_set for document_id in top_k)
            precision = hits / k
            recall = hits / len(relevant_set)
            dcg = sum(
                1.0 / math.log2(rank + 2)
                for rank, document_id in enumerate(top_k)
                if document_id in relevant_set
            )
            ideal_length = min(k, len(relevant_set))
            idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_length))
            metrics[f"precision_at_{k}"] = precision
            metrics[f"recall_at_{k}"] = recall
            metrics[f"hit_rate_at_{k}"] = 1 if hits else 0
            metrics[f"ndcg_at_{k}"] = dcg / idcg if idcg else None
        first_rank = next(
            (
                rank
                for rank, document_id in enumerate(retrieved, start=1)
                if document_id in relevant_set
            ),
            None,
        )
        metrics["mrr"] = 1.0 / first_rank if first_rank is not None else 0.0
        findings: list[EvaluationFinding] = []
        if not any(document_id in relevant_set for document_id in retrieved[: max(k_values)]):
            findings.append(
                EvaluationFinding(
                    code="retrieval_miss",
                    severity=FindingSeverity.WARNING,
                    message="No relevant document was retrieved within the requested cutoff.",
                    evidence={
                        "span_id": span_id_value,
                        "retrieved_document_ids": cast(JSONValue, retrieved[:100]),
                        "relevant_document_ids": cast(JSONValue, relevant[:100]),
                    },
                )
            )
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics=metrics,
            findings=tuple(findings),
            evidence={
                "span_id": span_id_value,
                "retrieved_document_ids": cast(JSONValue, retrieved[:100]),
                "relevant_document_ids": cast(JSONValue, relevant[:100]),
            },
        )


__all__ = [
    "LatencyEvaluator",
    "ReliabilityEvaluator",
    "RetrievalRankingEvaluator",
    "UsageEvaluator",
]
