"""M2 SDK lifecycle, capture, context, sampling, and export contracts."""

import asyncio
from datetime import UTC, datetime

import pytest

from agentlens import (
    AgentLens,
    AlwaysOffSampler,
    AlwaysOnSampler,
    InMemoryTraceExporter,
    current_span,
    current_trace,
)
from agentlens.domain import Status
from agentlens.exceptions import InstrumentationError, ValidationError

START = datetime(2025, 1, 1, 12, tzinfo=UTC)


def test_client_and_basic_trace_export() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(
        project_id="support-agent",
        exporter=exporter,
        sampler=AlwaysOnSampler(),
        attributes={"environment": "test", "service": "support"},
        clock=lambda: START,
    )

    with client.trace("answer-question", attributes={"service": "override"}) as trace:
        assert current_trace() is trace
        with trace.span("retrieve", span_type="retrieval") as retrieve:
            assert current_span() is retrieve
            retrieve.set_attribute("documents", 3)
            retrieve.set_input({"query": "hello"})
            retrieve.set_output({"ids": ["a", "b"]})
            retrieve.set_usage(input_tokens=4, output_tokens=0, total_tokens=4)
            retrieve.add_event("cache-hit", attributes={"hit": True})
        assert current_span() is None
        trace.add_event("complete", attributes={"result": "ok"})

    assert current_trace() is None
    assert len(exporter.traces) == 1
    finished = exporter.traces[0]
    assert finished.project_id == "support-agent"
    assert finished.attributes["service"] == "override"  # type: ignore[index]
    assert finished.attributes["environment"] == "test"  # type: ignore[index]
    assert finished.status is Status.UNSET
    assert len(finished.spans) == 1
    assert finished.spans[0].ended_at is not None
    assert len(finished.events) == 2
    assert finished.events[0].span_id == finished.spans[0].span_id
    assert finished.events[1].span_id is None


def test_nested_spans_have_parent_ids_and_siblings_are_roots_of_same_parent() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter)

    with client.trace("nested") as trace:
        with trace.span("agent", span_type="agent"):
            with trace.span("search", span_type="retrieval"):
                pass
            with trace.span("model", span_type="llm"):
                pass
        with trace.span("audit", span_type="custom"):
            pass

    spans = {span.name: span for span in exporter.traces[0].spans}
    assert spans["search"].parent_span_id == spans["agent"].span_id
    assert spans["model"].parent_span_id == spans["agent"].span_id
    assert spans["audit"].parent_span_id is None


def test_nested_explicit_traces_are_independent_and_restore_outer_context() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter)

    with client.trace("outer") as outer:
        with outer.span("outer-span"):
            with client.trace("inner") as inner:
                assert current_trace() is inner
                assert current_span() is None
                with inner.span("inner-span"):
                    pass
            assert current_trace() is outer
            assert current_span() is not None
        assert current_trace() is outer

    assert [trace.name for trace in exporter.traces] == ["inner", "outer"]
    assert exporter.traces[0].spans[0].parent_span_id is None


def test_span_exception_is_captured_and_original_exception_is_reraised() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter)
    original = ValueError("bad input")

    with pytest.raises(ValueError) as raised:
        with client.trace("span-error") as trace:
            with trace.span("database"):
                raise original

    assert raised.value is original
    span = exporter.traces[0].spans[0]
    assert span.status is Status.ERROR
    assert span.error is not None
    assert span.error.error_type == "ValueError"
    assert span.error.message == "bad input"
    assert current_trace() is None
    assert current_span() is None


def test_trace_exception_is_captured_as_redacted_error_event() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter)

    with pytest.raises(RuntimeError, match="boom"):
        with client.trace("trace-error"):
            raise RuntimeError("boom")

    trace = exporter.traces[0]
    assert trace.status is Status.ERROR
    assert len(trace.events) == 1
    assert trace.events[0].name == "error"
    assert trace.events[0].attributes["error_type"] == "RuntimeError"  # type: ignore[index]


def test_async_context_and_concurrent_task_isolation() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter)

    async def worker(name: str) -> tuple[str, str, str | None]:
        async with client.trace(name) as trace:
            trace_id = str(trace.trace_id)
            async with trace.span("work") as span:
                await asyncio.sleep(0)
                assert current_trace() is trace
                assert current_span() is span
                return name, trace_id, str(span.trace_id)

    async def run() -> list[tuple[str, str, str | None]]:
        return await asyncio.gather(worker("one"), worker("two"))

    results = asyncio.run(run())
    assert len({result[1] for result in results}) == 2
    assert all(result[1] == result[2] for result in results)
    assert current_trace() is None
    assert current_span() is None
    assert {trace.name for trace in exporter.traces} == {"one", "two"}
    assert all(trace.spans[0].parent_span_id is None for trace in exporter.traces)


def test_sampling_is_decided_at_root_and_unsampled_exceptions_propagate() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter, sampler=AlwaysOffSampler())
    ran = False

    with client.trace("dropped") as trace:
        ran = True
        with trace.span("ignored"):
            pass
    assert ran
    assert trace.finished_trace is None
    assert exporter.traces == []

    with pytest.raises(KeyError):
        with client.trace("dropped-error"):
            raise KeyError("application")
    assert exporter.traces == []


def test_input_attributes_and_events_are_defensive_copies() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter)
    source = {"nested": {"value": 1}}
    event_source = {"secret": "original"}

    with client.trace("mutation") as trace:
        with trace.span("work") as span:
            span.set_input(source)
            span.set_attributes(source)
            span.add_event("captured", attributes=event_source)
            source["nested"]["value"] = 2
            event_source["secret"] = "changed"

    span = exporter.traces[0].spans[0]
    assert span.input["nested"]["value"] == 1  # type: ignore[index]
    assert span.attributes["nested"]["value"] == 1  # type: ignore[index]
    assert exporter.traces[0].events[0].attributes["secret"] == "original"  # type: ignore[index]


def _redact(value: object, *, field: str, context: dict[str, str]) -> object:
    del field, context
    if isinstance(value, str):
        return value.replace("secret", "[redacted]")
    if isinstance(value, dict):
        return {key: _redact(item, field="nested", context={}) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, field="nested", context={}) for item in value]
    return value


def test_redaction_covers_input_output_attributes_and_events() -> None:
    exporter = InMemoryTraceExporter()
    client = AgentLens(project_id="p", exporter=exporter, redactor=_redact)

    with client.trace("redacted", attributes={"secret": "secret-value"}) as trace:
        trace.add_event("event", attributes={"value": "secret-event"})
        with trace.span("work") as span:
            span.set_input({"value": "secret-input"})
            span.set_output({"value": "secret-output"})
            span.set_attribute("value", "secret-attribute")

    serialized = exporter.traces[0].to_json()
    assert "secret-value" not in serialized
    assert "secret-event" not in serialized
    assert "secret-input" not in serialized
    assert "secret-output" not in serialized
    assert "secret-attribute" not in serialized


def test_redactor_failure_drops_trace_without_breaking_application() -> None:
    exporter = InMemoryTraceExporter()

    def broken_redactor(value: object, *, field: str, context: dict[str, str]) -> object:
        del value, field, context
        raise RuntimeError("redactor unavailable")

    client = AgentLens(project_id="p", exporter=exporter, redactor=broken_redactor)
    with client.trace("safe-drop") as trace:
        with trace.span("work") as span:
            span.set_output({"secret": "must-not-export"})
    assert trace.finished_trace is None
    assert exporter.traces == []
    assert "redaction failure" in client.diagnostics


def test_exporter_failure_isolated_and_does_not_duplicate_or_leak_context() -> None:
    class BrokenExporter:
        def __init__(self) -> None:
            self.calls = 0

        def export(self, trace: object) -> None:
            del trace
            self.calls += 1
            raise RuntimeError("export unavailable")

    exporter = BrokenExporter()
    client = AgentLens(project_id="p", exporter=exporter)  # type: ignore[arg-type]
    with client.trace("export-failure") as trace:
        pass

    assert trace.finished_trace is not None
    assert exporter.calls == 1
    assert "export failure" in client.diagnostics
    assert current_trace() is None


def test_closed_handles_and_invalid_explicit_values_fail_clearly() -> None:
    client = AgentLens(project_id="p")
    with client.trace("lifecycle") as trace:
        span = trace.span("work")
        with span:
            pass
        with pytest.raises(InstrumentationError):
            span.set_output({"late": True})

    with pytest.raises(InstrumentationError):
        trace.__enter__()
    with pytest.raises(InstrumentationError):
        trace.add_event("late")
    with pytest.raises(ValidationError):
        with client.trace("bad") as active_trace:
            with active_trace.span("x") as active_span:
                active_span.set_status("invalid")


def test_invalid_project_and_payload_values_fail_at_explicit_boundary() -> None:
    with pytest.raises(ValidationError):
        AgentLens(project_id=" ")
    client = AgentLens(project_id="p")
    with client.trace("invalid") as trace:
        with trace.span("work") as span:
            with pytest.raises(ValidationError):
                span.set_input({"bad": {1, 2}})  # type: ignore[arg-type]
            with pytest.raises(ValidationError):
                span.set_usage(input_tokens=-1)
