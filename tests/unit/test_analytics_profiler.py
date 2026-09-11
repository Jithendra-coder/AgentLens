"""Unit tests for DAG critical-path analysis and trace bottleneck profiler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from agentlens.analytics.profiler import profile_trace
from agentlens.domain import ErrorInfo, Span, Trace, Usage
from agentlens.domain.types import SpanType, Status


def test_sequential_trace_critical_path_and_breakdown() -> None:
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()
    root_id = uuid4()
    llm_id = uuid4()
    tool_id = uuid4()

    # Root span: 0s -> 5s (total 5000ms)
    root = Span(
        span_id=root_id,
        trace_id=trace_id,
        span_type=SpanType.AGENT,
        name="MainAgent",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=5),
        status=Status.OK,
    )
    # LLM child span: 1s -> 3s (total 2000ms)
    llm = Span(
        span_id=llm_id,
        trace_id=trace_id,
        parent_span_id=root_id,
        span_type=SpanType.LLM,
        name="gpt-4o",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=3),
        status=Status.OK,
        usage=Usage(input_tokens=100, output_tokens=50, total_tokens=150),
    )
    # Tool child span: 3s -> 4.5s (total 1500ms)
    tool = Span(
        span_id=tool_id,
        trace_id=trace_id,
        parent_span_id=root_id,
        span_type=SpanType.TOOL,
        name="fetch_weather",
        started_at=t0 + timedelta(seconds=3),
        ended_at=t0 + timedelta(seconds=4, milliseconds=500),
        status=Status.OK,
    )

    trace = Trace(
        trace_id=trace_id,
        project_id="test-proj",
        name="SequentialAgentTrace",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=5),
        status=Status.OK,
        spans=[root, llm, tool],
    )

    profile = profile_trace(trace)
    assert profile.total_duration_ms == 5000.0
    assert profile.total_tokens == 150
    assert profile.prompt_tokens == 100
    assert profile.completion_tokens == 50

    # Latency breakdown
    assert profile.latency_breakdown.llm_time_ms == 2000.0
    assert profile.latency_breakdown.tool_time_ms == 1500.0
    # Overhead = root self time (1500ms)
    assert profile.latency_breakdown.overhead_time_ms == 1500.0

    # Critical path should include root and the longest child
    assert root_id in profile.critical_path_span_ids


def test_parallel_overlapping_spans_self_time() -> None:
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()
    root_id = uuid4()
    tool1_id = uuid4()
    tool2_id = uuid4()

    # Root span: 0s -> 4s (4000ms)
    root = Span(
        span_id=root_id,
        trace_id=trace_id,
        span_type=SpanType.AGENT,
        name="ParallelRunner",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=4),
        status=Status.OK,
    )
    # Tool 1: 1s -> 3s (2000ms)
    tool1 = Span(
        span_id=tool1_id,
        trace_id=trace_id,
        parent_span_id=root_id,
        span_type=SpanType.TOOL,
        name="tool_a",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t0 + timedelta(seconds=3),
        status=Status.OK,
    )
    # Tool 2: 1.5s -> 3.5s (2000ms, overlapping with tool 1)
    tool2 = Span(
        span_id=tool2_id,
        trace_id=trace_id,
        parent_span_id=root_id,
        span_type=SpanType.TOOL,
        name="tool_b",
        started_at=t0 + timedelta(seconds=1, milliseconds=500),
        ended_at=t0 + timedelta(seconds=3, milliseconds=500),
        status=Status.OK,
    )

    trace = Trace(
        trace_id=trace_id,
        project_id="test-proj",
        name="ParallelTrace",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=4),
        status=Status.OK,
        spans=[root, tool1, tool2],
    )

    profile = profile_trace(trace)
    # Merged child interval is 1s -> 3.5s = 2500ms
    # Root self-time should be 4000 - 2500 = 1500ms
    root_profile = next(sp for sp in profile.span_profiles if sp.span_id == root_id)
    assert root_profile.self_time_ms == 1500.0


def test_hotspot_detection_for_dominant_and_error_spans() -> None:
    t0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    trace_id = uuid4()
    slow_span_id = uuid4()
    error_span_id = uuid4()

    # Slow span taking 80% of trace
    slow_span = Span(
        span_id=slow_span_id,
        trace_id=trace_id,
        span_type=SpanType.LLM,
        name="deep_reasoning_step",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=8),
        status=Status.OK,
        usage=Usage(total_tokens=5000),
    )
    # Failed span
    error_span = Span(
        span_id=error_span_id,
        trace_id=trace_id,
        span_type=SpanType.TOOL,
        name="database_lookup",
        started_at=t0 + timedelta(seconds=8),
        ended_at=t0 + timedelta(seconds=10),
        status=Status.ERROR,
        error=ErrorInfo(error_type="PoolError", message="Connection pool exhausted"),
    )

    trace = Trace(
        trace_id=trace_id,
        project_id="test-proj",
        name="HotspotTrace",
        started_at=t0,
        ended_at=t0 + timedelta(seconds=10),
        status=Status.ERROR,
        spans=[slow_span, error_span],
    )

    profile = profile_trace(trace)
    assert len(profile.hotspots) >= 2

    dominant_hotspot = next(h for h in profile.hotspots if h.hotspot_type == "dominant_latency")
    assert dominant_hotspot.span_id == slow_span_id
    assert dominant_hotspot.severity == "high"

    error_hotspot = next(h for h in profile.hotspots if h.hotspot_type == "error_retry")
    assert error_hotspot.span_id == error_span_id
    assert "Connection pool exhausted" in error_hotspot.description
