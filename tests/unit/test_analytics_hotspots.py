"""Unit tests for project-level tool latency, token consumption, and error hotspot aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from agentlens.analytics.hotspots import aggregate_project_hotspots
from agentlens.domain import ErrorInfo, Span, Trace, Usage
from agentlens.domain.types import SpanType, Status


def test_aggregate_project_hotspots() -> None:
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)

    # Trace 1
    t1_id = uuid4()
    t1_s1 = Span(
        span_id=uuid4(),
        trace_id=t1_id,
        span_type=SpanType.TOOL,
        name="web_search",
        started_at=t0,
        ended_at=t0 + timedelta(milliseconds=500),
        status=Status.OK,
    )
    t1_s2 = Span(
        span_id=uuid4(),
        trace_id=t1_id,
        span_type=SpanType.LLM,
        name="gpt-4o",
        started_at=t0 + timedelta(milliseconds=500),
        ended_at=t0 + timedelta(milliseconds=1500),
        status=Status.OK,
        usage=Usage(input_tokens=200, output_tokens=100, total_tokens=300),
    )
    trace1 = Trace(trace_id=t1_id, project_id="proj-x", spans=[t1_s1, t1_s2])

    # Trace 2
    t2_id = uuid4()
    t2_s1 = Span(
        span_id=uuid4(),
        trace_id=t2_id,
        span_type=SpanType.TOOL,
        name="web_search",
        started_at=t0,
        ended_at=t0 + timedelta(milliseconds=1500),
        status=Status.ERROR,
        error=ErrorInfo(error_type="TimeoutError", message="HTTP 504 Gateway Timeout"),
    )
    trace2 = Trace(trace_id=t2_id, project_id="proj-x", spans=[t2_s1])

    summary = aggregate_project_hotspots("proj-x", [trace1, trace2])
    assert summary.project_id == "proj-x"
    assert summary.analyzed_traces_count == 2

    # Check slowest tools
    assert len(summary.slowest_tools) == 1
    tool = summary.slowest_tools[0]
    assert tool.tool_name == "web_search"
    assert tool.call_count == 2
    assert tool.avg_duration_ms == 1000.0
    assert tool.max_duration_ms == 1500.0
    assert tool.error_rate == 50.0

    # Check heaviest token spans
    assert len(summary.heaviest_token_spans) == 1
    token_span = summary.heaviest_token_spans[0]
    assert token_span.name == "gpt-4o"
    assert token_span.total_tokens == 300

    # Check error hotspots
    assert len(summary.top_errors) == 1
    err = summary.top_errors[0]
    assert err.error_message == "HTTP 504 Gateway Timeout"
    assert err.occurrences == 1
    assert "tool" in err.affected_span_types
