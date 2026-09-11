"""Unit tests for EvaluationSuiteRepository operations and composite result storage."""

from __future__ import annotations

from uuid import uuid4

from agentlens.evaluation.composite import (
    CompositeEvaluationResult,
    EvaluationSuite,
    EvaluatorConfigRef,
    MetricScore,
)
from agentlens.evaluation.suite_repository import InMemoryEvaluationSuiteRepository


def test_in_memory_suite_repository_lifecycle() -> None:
    repo = InMemoryEvaluationSuiteRepository()

    suite_id = uuid4()
    suite = EvaluationSuite(
        suite_id=suite_id,
        project_id="proj-alpha",
        name="Security & Latency Suite",
        passing_threshold=0.85,
        evaluators=(
            EvaluatorConfigRef(
                evaluator_name="agentlens.latency",
                weight=0.4,
                threshold=0.8,
            ),
            EvaluatorConfigRef(
                evaluator_name="agentlens.tool_correctness",
                weight=0.6,
                threshold=0.9,
            ),
        ),
    )

    saved = repo.create_suite(suite)
    assert saved.suite_id == suite_id

    fetched = repo.get_suite(suite_id)
    assert fetched is not None
    assert fetched.name == "Security & Latency Suite"
    assert len(fetched.evaluators) == 2

    suites = repo.list_suites("proj-alpha")
    assert len(suites) == 1

    # Store result
    res_id = uuid4()
    result = CompositeEvaluationResult(
        composite_result_id=res_id,
        suite_id=suite_id,
        project_id="proj-alpha",
        trace_id=uuid4(),
        aggregate_score=0.92,
        passed=True,
        metric_scores=(
            MetricScore(
                evaluator_name="agentlens.latency",
                evaluator_version="1.0.0",
                evaluator_type="deterministic",
                raw_score=0.95,
                weight=0.4,
                weighted_score=0.38,
                threshold=0.8,
                passed=True,
            ),
        ),
    )
    repo.store_result(result)

    results = repo.list_results("proj-alpha", suite_id=suite_id)
    assert len(results) == 1
    assert results[0].aggregate_score == 0.92

    # Delete suite
    assert repo.delete_suite(suite_id) is True
    assert repo.get_suite(suite_id) is None
