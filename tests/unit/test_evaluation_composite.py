"""Unit tests for composite quality metrics, evaluation suites, and orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from agentlens.domain import Span, Trace
from agentlens.domain.types import SpanType, Status
from agentlens.evaluation.composite import (
    EvaluationSuite,
    EvaluatorConfigRef,
)
from agentlens.evaluation.orchestrator import EvaluationSuiteOrchestrator


def test_suite_and_evaluator_invariants() -> None:
    with pytest.raises(ValueError, match="weight must be positive"):
        EvaluatorConfigRef(evaluator_name="test", weight=-0.5)

    with pytest.raises(ValueError, match="threshold must be between"):
        EvaluatorConfigRef(evaluator_name="test", threshold=1.5)

    with pytest.raises(ValueError, match="passing_threshold must be between"):
        EvaluationSuite(name="test", passing_threshold=2.0)


def test_suite_orchestrator_execution_and_composite_score() -> None:
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()

    s1 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.AGENT,
        name="MainAgent",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
    )
    s2 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.TOOL,
        name="calculator",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
    )
    trace = Trace(
        trace_id=trace_id,
        project_id="proj-suite",
        name="ValidExecution",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
        spans=[s1, s2],
    )

    ev1 = EvaluatorConfigRef(
        evaluator_name="agentlens.latency",
        weight=0.5,
        threshold=0.8,
    )
    ev2 = EvaluatorConfigRef(
        evaluator_name="agentlens.tool_correctness",
        weight=0.5,
        threshold=0.8,
    )

    suite = EvaluationSuite(
        suite_id=uuid4(),
        project_id="proj-suite",
        name="ProductionSuite",
        passing_threshold=0.8,
        evaluators=(ev1, ev2),
    )

    orchestrator = EvaluationSuiteOrchestrator()
    res = orchestrator.evaluate_suite(suite, trace)

    assert res.suite_id == suite.suite_id
    assert res.project_id == "proj-suite"
    assert res.aggregate_score >= 0.8
    assert res.passed is True
    assert len(res.metric_scores) == 2
    assert all(m.passed for m in res.metric_scores)
