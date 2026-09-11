"""Construction and round-trip contracts for the canonical domain model."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from agentlens.domain import ErrorInfo, Event, Span, SpanType, Status, Trace, Usage
from agentlens.exceptions import (
    SerializationError,
    UnsupportedSchemaError,
    ValidationError,
)

START = datetime(2025, 1, 1, 12, tzinfo=UTC)


def make_trace(**overrides: object) -> Trace:
    values: dict[str, object] = {
        "trace_id": uuid4(),
        "project_id": "project",
        "name": "request",
        "started_at": START,
    }
    values.update(overrides)
    return Trace(**values)  # type: ignore[arg-type]


def make_span(trace_id: UUID, **overrides: object) -> Span:
    values: dict[str, object] = {
        "trace_id": trace_id,
        "span_type": SpanType.CUSTOM,
        "name": "operation",
        "started_at": START,
    }
    values.update(overrides)
    return Span(**values)  # type: ignore[arg-type]


def test_minimal_partial_trace_and_multiple_roots() -> None:
    trace_id = uuid4()
    trace = make_trace(spans=[make_span(trace_id), make_span(trace_id)], trace_id=trace_id)

    assert trace.ended_at is None
    assert trace.status is Status.UNSET
    assert len(trace.spans) == 2
    assert trace.events == ()


def test_populated_trace_round_trips_through_dict_and_json() -> None:
    trace_id = uuid4()
    root = make_span(
        trace_id,
        span_id=uuid4(),
        span_type=SpanType.AGENT,
        name="agent",
        ended_at=START + timedelta(seconds=2),
        status=Status.OK,
        input={"question": "hello"},
        output={"answer": "world"},
        attributes={"model": {"temperature": 0.2}},
        usage=Usage(input_tokens=4, output_tokens=3, total_tokens=7),
        error=ErrorInfo("Timeout", "observed failure", code="E_TIMEOUT"),
    )
    child = make_span(
        trace_id,
        span_id=uuid4(),
        parent_span_id=root.span_id,
        span_type="llm.future-provider",
        name="model call",
        started_at=START + timedelta(seconds=1),
    )
    event = Event(
        event_id=uuid4(),
        trace_id=trace_id,
        span_id=child.span_id,
        name="retry",
        timestamp=START + timedelta(seconds=1),
        attributes={"attempt": 1},
    )
    trace = make_trace(
        trace_id=trace_id,
        session_id="session-1",
        ended_at=START + timedelta(seconds=3),
        status="ok",
        spans=[root, child],
        events=[event],
        attributes={"nested": [True, None, {"value": 1.5}]},
    )

    as_dict = trace.to_dict()
    assert as_dict["schema_version"] == "agentlens-trace-v1"
    assert as_dict["trace_id"] == str(trace_id)
    assert Trace.from_dict(as_dict) == trace
    assert Trace.from_json(trace.to_json()) == trace
    assert trace.to_json() == Trace.from_dict(as_dict).to_json()


def test_ids_accept_uuid_objects_and_normalize_strings() -> None:
    trace_id = uuid4()
    span_id = uuid4()
    event_id = uuid4()
    span = Span(
        span_id=str(span_id).upper(),
        trace_id=trace_id,
        name="work",
        started_at=START,
    )
    event = Event(
        event_id=str(event_id),
        trace_id=str(trace_id),
        name="started",
        timestamp=START,
    )

    assert span.span_id == span_id
    assert event.event_id == event_id
    assert event.trace_id == trace_id


@pytest.mark.parametrize("bad_id", ["", "not-a-uuid", 42, object()])
def test_malformed_ids_are_rejected(bad_id: object) -> None:
    with pytest.raises(ValidationError):
        Span(span_id=bad_id, trace_id=uuid4(), name="work", started_at=START)  # type: ignore[arg-type]


def test_timestamps_normalize_to_utc_and_naive_values_fail() -> None:
    local = datetime(2025, 1, 1, 13, tzinfo=timezone(timedelta(hours=1)))
    span = Span(trace_id=uuid4(), name="work", started_at=local)
    assert span.started_at == datetime(2025, 1, 1, 12, tzinfo=UTC)
    assert span.started_at.tzinfo is UTC

    with pytest.raises(ValidationError):
        Span(trace_id=uuid4(), name="work", started_at=datetime(2025, 1, 1, 12))


def test_end_before_start_is_rejected_but_missing_end_is_valid() -> None:
    trace_id = uuid4()
    with pytest.raises(ValidationError):
        Span(
            trace_id=trace_id,
            name="work",
            started_at=START,
            ended_at=START - timedelta(seconds=1),
        )
    assert Span(trace_id=trace_id, name="unfinished", started_at=START).ended_at is None


def test_usage_and_error_are_observed_metadata() -> None:
    usage = Usage(input_tokens=1, output_tokens=2, cached_tokens=3, reasoning_tokens=4)
    error = ErrorInfo("ValueError", "bad input", traceback="trace")
    span = Span(trace_id=uuid4(), name="work", started_at=START, usage=usage, error=error)

    assert span.usage == usage
    assert span.error == error
    assert error.stack == "trace"


@pytest.mark.parametrize("bad_count", [-1, True, 1.5, "1"])
def test_negative_or_non_integer_usage_is_rejected(bad_count: object) -> None:
    with pytest.raises(ValidationError):
        Usage(input_tokens=bad_count)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_payload",
    [
        object(),
        {"items": {1, 2}},
        {1: "non-string key"},
        {"value": float("nan")},
        {"value": float("inf")},
    ],
)
def test_payload_boundary_rejects_non_json_values(bad_payload: object) -> None:
    with pytest.raises(ValidationError):
        Span(trace_id=uuid4(), name="work", started_at=START, attributes=bad_payload)  # type: ignore[arg-type]


def test_nested_payloads_and_serialized_output_are_mutation_safe() -> None:
    source = {"model": {"temperature": 0.2}, "messages": [{"role": "user"}]}
    span = Span(trace_id=uuid4(), name="work", started_at=START, attributes=source, input=source)

    source["model"]["temperature"] = 1.0  # type: ignore[index]
    assert span.attributes["model"]["temperature"] == 0.2  # type: ignore[index]
    assert span.input["model"]["temperature"] == 0.2  # type: ignore[index]

    serialized = span.to_dict()
    serialized["attributes"]["model"]["temperature"] = 2.0  # type: ignore[index]
    assert span.attributes["model"]["temperature"] == 0.2  # type: ignore[index]


def test_frozen_nested_values_cannot_mutate_the_domain_object() -> None:
    span = Span(
        trace_id=uuid4(),
        name="work",
        started_at=START,
        attributes={"nested": {"value": 1}},
    )

    with pytest.raises(TypeError):
        span.attributes["nested"]["value"] = 2  # type: ignore[index]


def test_malformed_json_and_missing_fields_use_domain_errors() -> None:
    with pytest.raises(SerializationError):
        Trace.from_json("{")
    with pytest.raises(SerializationError):
        Trace.from_dict({"schema_version": "agentlens-trace-v1"})


def test_unknown_schema_is_not_treated_as_v1() -> None:
    trace = make_trace()
    payload = trace.to_dict()
    payload["schema_version"] = "agentlens-trace-v999"

    with pytest.raises(UnsupportedSchemaError):
        Trace.from_dict(payload)
