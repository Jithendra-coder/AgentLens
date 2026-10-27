"""Unit tests for Custom Evaluator SDK and sandboxed runtime."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from agentlens.domain import Span, Trace
from agentlens.domain.types import SpanType, Status
from agentlens.evaluation.plugins import sandbox, sandbox_worker
from agentlens.evaluation.plugins.models import (
    EvaluatorContext,
)
from agentlens.evaluation.plugins.sandbox import execute_custom_evaluator


def make_test_trace() -> Trace:
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()
    s1 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.AGENT,
        name="Router",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=1),
        status=Status.OK,
    )
    s2 = Span(
        span_id=uuid4(),
        trace_id=trace_id,
        span_type=SpanType.TOOL,
        name="database_query",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
        attributes={"db_table": "users", "rows": 10},
    )
    return Trace(
        trace_id=trace_id,
        project_id="proj-plugin",
        name="PluginTestTrace",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=2),
        status=Status.OK,
        spans=[s1, s2],
    )


def test_evaluator_context_extraction() -> None:
    trace = make_test_trace()
    ctx = EvaluatorContext.from_trace(trace)
    assert ctx.trace_id == str(trace.trace_id)
    assert ctx.project_id == "proj-plugin"
    assert len(ctx.spans) == 2
    assert ctx.spans[1].name == "database_query"
    assert ctx.spans[1].attributes.get("db_table") == "users"


@pytest.mark.skipif(
    not sandbox._docker_available(), reason="Docker is required for isolated evaluator tests"
)
def test_function_custom_evaluator_execution() -> None:
    code = """
def evaluate(context, parameters):
    min_spans = int(parameters.get("min_spans", 1))
    passed = len(context.spans) >= min_spans
    score = 1.0 if passed else 0.0
    return CustomEvaluationOutput(
        score=score,
        passed=passed,
        findings=[f"Found {len(context.spans)} spans (required >= {min_spans})"],
    )
"""
    trace = make_test_trace()
    ctx = EvaluatorContext.from_trace(trace)

    res = execute_custom_evaluator(code, ctx, parameters={"min_spans": 2})
    assert res.score == 1.0
    assert res.passed is True
    assert len(res.findings) == 1

    res_fail = execute_custom_evaluator(code, ctx, parameters={"min_spans": 5})
    assert res_fail.score == 0.0
    assert res_fail.passed is False


@pytest.mark.skipif(
    not sandbox._docker_available(), reason="Docker is required for isolated evaluator tests"
)
def test_class_custom_evaluator_execution() -> None:
    code = """
class ToolSpanChecker(CustomEvaluator):
    def evaluate(self, context, parameters):
        tools = [s for s in context.spans if s.span_type == "tool"]
        return CustomEvaluationOutput(
            score=1.0 if tools else 0.0,
            passed=bool(tools),
            details={"tool_count": len(tools)},
        )
"""
    trace = make_test_trace()
    ctx = EvaluatorContext.from_trace(trace)

    res = execute_custom_evaluator(code, ctx)
    assert res.score == 1.0
    assert res.passed is True
    assert res.details.get("tool_count") == 1


@pytest.mark.skipif(
    not sandbox._docker_available(), reason="Docker is required for isolated evaluator tests"
)
def test_sandbox_runtime_error_isolation() -> None:
    code = """
def evaluate(context, parameters):
    raise ValueError("Intentional evaluator failure")
"""
    trace = make_test_trace()
    ctx = EvaluatorContext.from_trace(trace)

    res = execute_custom_evaluator(code, ctx)
    assert res.score == 0.0
    assert res.passed is False
    assert any("RuntimeExecutionError" in f for f in res.findings)


@pytest.mark.skipif(
    not sandbox._docker_available(), reason="Docker is required for isolated evaluator tests"
)
def test_sandbox_syntax_error_isolation() -> None:
    code = "def syntax_error( context )"
    trace = make_test_trace()
    ctx = EvaluatorContext.from_trace(trace)

    res = execute_custom_evaluator(code, ctx)
    assert res.score == 0.0
    assert res.passed is False
    assert any("CompilationError" in f for f in res.findings)


def test_evaluator_fails_closed_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox, "_docker_available", lambda: False)
    result = execute_custom_evaluator(
        "def evaluate(context, parameters): return 1",
        EvaluatorContext(
            trace_id="trace",
            project_id="project",
            name="trace",
            status="ok",
            started_at="2026-01-01T00:00:00+00:00",
            ended_at=None,
        ),
    )
    assert result.passed is False
    assert result.details["error_type"] == "sandbox_unavailable"


def test_container_worker_accepts_supported_evaluator_result() -> None:
    result = sandbox_worker.evaluate(
        {
            "code_body": (
                "def evaluate(context, parameters):\n"
                "    return {'score': 1, 'passed': True,\n"
                "            'findings': [context.name]}\n"
            ),
            "context": {"name": "worker-smoke", "spans": []},
            "parameters": {},
        }
    )
    assert result == {
        "score": 1.0,
        "passed": True,
        "findings": ["worker-smoke"],
        "details": {},
    }
