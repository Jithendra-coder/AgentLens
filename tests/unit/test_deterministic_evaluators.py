"""Hand-calculated M6 deterministic evaluator contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import log2
from uuid import uuid4

import pytest

from agentlens.domain import Span, Status, Trace, Usage
from agentlens.evaluation.evaluators import (
    LatencyEvaluator,
    ReliabilityEvaluator,
    RetrievalRankingEvaluator,
    UsageEvaluator,
)
from agentlens.evaluation.results import (
    RESULT_SCHEMA_VERSION,
    EvaluationFinding,
    EvaluationResult,
    ResultStatus,
    canonical_json_fingerprint,
)

START = datetime(2025, 1, 1, 12, tzinfo=UTC)


def make_trace(*, ended: bool = True) -> Trace:
    trace_id = uuid4()
    retrieval_id = uuid4()
    tool_id = uuid4()
    return Trace(
        trace_id=trace_id,
        project_id="unit-project",
        name="evaluation-fixture",
        started_at=START,
        ended_at=START + timedelta(seconds=2) if ended else None,
        status=Status.OK,
        spans=(
            Span(
                trace_id=trace_id,
                span_id=retrieval_id,
                span_type="retrieval",
                name="retrieve",
                started_at=START,
                ended_at=START + timedelta(seconds=1),
                status=Status.OK,
                output={
                    "documents": [
                        {"id": "d3"},
                        {"id": "d1"},
                        {"id": "d8"},
                        {"id": "d2"},
                    ]
                },
                usage=Usage(input_tokens=0, output_tokens=5, total_tokens=99),
            ),
            Span(
                trace_id=trace_id,
                span_id=tool_id,
                span_type="tool",
                name="tool",
                started_at=START + timedelta(milliseconds=500),
                ended_at=START + timedelta(seconds=2),
                status=Status.ERROR,
                usage=Usage(output_tokens=0, cached_tokens=2, reasoning_tokens=3),
            ),
            Span(
                trace_id=trace_id,
                span_type="custom",
                name="unfinished",
                started_at=START,
                status=Status.UNSET,
            ),
        ),
    )


def test_latency_is_wall_clock_and_counts_unfinished_spans() -> None:
    result = LatencyEvaluator().evaluate(make_trace(), {})
    assert result.result_status is ResultStatus.COMPLETED
    assert result.metrics["trace_duration_ms"] == 2000.0
    assert result.metrics["completed_span_count"] == 2
    assert result.metrics["unfinished_span_count"] == 1
    assert result.metrics["span_duration_sum_ms"] == 2500.0
    assert result.metrics["longest_span_duration_ms"] == 1500.0

    incomplete = LatencyEvaluator().evaluate(make_trace(ended=False), {})
    assert incomplete.metrics["trace_duration_ms"] is None
    assert incomplete.findings[0].code == "trace_incomplete"


def test_usage_distinguishes_missing_from_reported_zero() -> None:
    result = UsageEvaluator().evaluate(make_trace(), {})
    assert result.metrics["spans_with_usage"] == 2
    assert result.metrics["input_tokens_reported"] == 0
    assert result.metrics["output_tokens_reported"] == 5
    assert result.metrics["total_tokens_reported"] == 99
    assert result.metrics["cached_tokens_reported"] == 2
    assert result.metrics["reasoning_tokens_reported"] == 3

    no_usage = UsageEvaluator().evaluate(
        Trace(project_id="unit-project", name="empty", started_at=START), {}
    )
    assert no_usage.metrics["spans_with_usage"] == 0
    assert no_usage.metrics["input_tokens_reported"] is None


def test_reliability_excludes_unset_from_error_denominator() -> None:
    result = ReliabilityEvaluator().evaluate(make_trace(), {})
    assert result.metrics["span_count"] == 3
    assert result.metrics["terminal_span_count"] == 2
    assert result.metrics["error_span_count"] == 1
    assert result.metrics["unset_span_count"] == 1
    assert result.metrics["error_rate"] == 0.5
    assert result.metrics["tool_success_rate"] == 0.0


def test_retrieval_metrics_match_hand_calculated_values() -> None:
    trace = make_trace()
    span_id = str(trace.spans[0].span_id)
    evaluator = RetrievalRankingEvaluator()
    config = evaluator.normalize_config(
        {
            "span_id": span_id,
            "relevant_document_ids": ["d1", "d2"],
            "k_values": [1, 3, 5],
        }
    )
    result = evaluator.evaluate(trace, config)
    assert result.result_status is ResultStatus.COMPLETED
    assert result.metrics["precision_at_1"] == 0.0
    assert result.metrics["recall_at_3"] == 0.5
    assert result.metrics["hit_rate_at_3"] == 1
    assert result.metrics["mrr"] == 0.5
    expected_ndcg = (1 / log2(3)) / (1 + 1 / log2(3))
    assert result.metrics["ndcg_at_3"] == expected_ndcg


def test_retrieval_invalid_input_is_terminal_result_not_exception() -> None:
    trace = make_trace()
    result = RetrievalRankingEvaluator().evaluate(
        trace,
        {
            "span_id": str(trace.spans[0].span_id),
            "relevant_document_ids": [],
            "k_values": [5],
        },
    )
    assert result.result_status is ResultStatus.INVALID_INPUT
    assert result.findings[0].code == "invalid_retrieval_input"


def test_result_model_is_versioned_and_recursively_immutable() -> None:
    config = {"nested": {"ids": ["d1"]}}
    result = EvaluationResult(
        result_id=uuid4(),
        result_schema_version=RESULT_SCHEMA_VERSION,
        project_id="unit-project",
        trace_id=uuid4(),
        job_id=uuid4(),
        evaluation_type="latency_summary",
        evaluator_name="agentlens.latency",
        evaluator_version="1.0.0",
        result_status="completed",
        created_at=START,
        config=config,
        config_fingerprint=canonical_json_fingerprint(config),
        trace_fingerprint="a" * 64,
        metrics={"nested": {"value": 1}},
        findings=[
            EvaluationFinding(
                code="example",
                severity="info",
                message="Example finding",
            )
        ],
        evidence={},
    )
    config["nested"]["ids"].append("d2")
    assert result.result_status is ResultStatus.COMPLETED
    assert isinstance(result.findings, tuple)
    assert result.to_dict()["config"] == {"nested": {"ids": ["d1"]}}
    with pytest.raises(TypeError):
        result.config["new"] = True  # type: ignore[index]
