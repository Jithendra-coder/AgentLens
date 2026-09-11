"""Adversarial structural validation for canonical traces."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agentlens.domain import Event, Span, Trace
from agentlens.exceptions import ValidationError

START = datetime(2025, 1, 1, tzinfo=UTC)


def span(trace_id, **kwargs):
    values = {"trace_id": trace_id, "name": "span", "started_at": START}
    values.update(kwargs)
    return Span(**values)


def trace(trace_id, **kwargs):
    values = {"trace_id": trace_id, "project_id": "p", "name": "t", "started_at": START}
    values.update(kwargs)
    return Trace(**values)


def test_duplicate_span_ids_are_rejected() -> None:
    trace_id = uuid4()
    duplicate = uuid4()
    with pytest.raises(ValidationError):
        trace(
            trace_id,
            spans=[span(trace_id, span_id=duplicate), span(trace_id, span_id=duplicate)],
        )


def test_duplicate_event_ids_are_rejected() -> None:
    trace_id = uuid4()
    duplicate = uuid4()
    event_a = Event(event_id=duplicate, trace_id=trace_id, name="a", timestamp=START)
    event_b = Event(event_id=duplicate, trace_id=trace_id, name="b", timestamp=START)
    with pytest.raises(ValidationError):
        trace(trace_id, events=[event_a, event_b])


def test_missing_parent_and_self_parent_are_rejected() -> None:
    trace_id = uuid4()
    with pytest.raises(ValidationError):
        trace(trace_id, spans=[span(trace_id, parent_span_id=uuid4())])

    span_id = uuid4()
    with pytest.raises(ValidationError):
        trace(trace_id, spans=[span(trace_id, span_id=span_id, parent_span_id=span_id)])


def test_two_node_and_deep_cycles_are_rejected() -> None:
    trace_id = uuid4()
    first, second = uuid4(), uuid4()
    with pytest.raises(ValidationError):
        trace(
            trace_id,
            spans=[
                span(trace_id, span_id=first, parent_span_id=second),
                span(trace_id, span_id=second, parent_span_id=first),
            ],
        )

    ids = [uuid4() for _ in range(20)]
    spans = [
        span(trace_id, span_id=current, parent_span_id=ids[index + 1])
        for index, current in enumerate(ids[:-1])
    ]
    spans.append(span(trace_id, span_id=ids[-1], parent_span_id=ids[0]))
    with pytest.raises(ValidationError):
        trace(trace_id, spans=spans)


def test_deep_hierarchy_is_valid() -> None:
    trace_id = uuid4()
    ids = [uuid4() for _ in range(30)]
    spans = [
        span(trace_id, span_id=current, parent_span_id=ids[index - 1] if index else None)
        for index, current in enumerate(ids)
    ]

    assert len(trace(trace_id, spans=spans).spans) == 30


def test_cross_trace_objects_and_unknown_event_span_are_rejected() -> None:
    trace_id = uuid4()
    other_trace_id = uuid4()
    with pytest.raises(ValidationError):
        trace(trace_id, spans=[span(other_trace_id)])

    event = Event(trace_id=other_trace_id, name="event", timestamp=START)
    with pytest.raises(ValidationError):
        trace(trace_id, events=[event])

    event = Event(trace_id=trace_id, span_id=uuid4(), name="event", timestamp=START)
    with pytest.raises(ValidationError):
        trace(trace_id, events=[event])


def test_partial_events_only_trace_is_valid() -> None:
    trace_id = uuid4()
    event = Event(trace_id=trace_id, name="heartbeat", timestamp=START)

    observed = trace(trace_id, events=[event])

    assert observed.spans == ()
    assert observed.events == (event,)
