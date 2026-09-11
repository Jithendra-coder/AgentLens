"""Minimal local instrumentation runtime built on the M1 domain model."""

from __future__ import annotations

import contextvars
import traceback as traceback_module
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from agentlens.domain import ErrorInfo, Event, Span, Status, Trace, Usage
from agentlens.domain.types import (
    JSONValue,
    freeze_payload,
    normalize_status,
    thaw_payload,
    utc_now,
)
from agentlens.exceptions import InstrumentationError, ValidationError

from .exporter import InMemoryTraceExporter, TraceExporter
from .sampling import AlwaysOnSampler, Sampler

Clock = Callable[[], datetime]
IDFactory = Callable[[], UUID]
Redactor = Callable[..., object]


class _RedactionFailure(Exception):
    """Internal marker preventing fallback to unredacted telemetry."""


_CURRENT_TRACE: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "agentlens_current_trace", default=None
)
_CURRENT_SPAN: contextvars.ContextVar[SpanContext | None] = contextvars.ContextVar(
    "agentlens_current_span", default=None
)


def current_trace() -> TraceContext | None:
    """Return the active trace handle in the current execution context."""

    return _CURRENT_TRACE.get()


def current_span() -> SpanContext | None:
    """Return the active span handle in the current execution context."""

    return _CURRENT_SPAN.get()


def _copy_json(value: object, field: str) -> JSONValue:
    """Validate and copy a caller-owned JSON value."""

    frozen = freeze_payload(value, field)
    return thaw_payload(frozen)


def _copy_attributes(value: object, field: str) -> dict[str, JSONValue]:
    """Validate and copy an object-valued attribute collection."""

    if not isinstance(value, Mapping):
        raise ValidationError(f"{field} must be an object")
    copied = _copy_json(dict(value), field)
    if not isinstance(copied, dict):
        raise ValidationError(f"{field} must be an object")
    return copied


def _call_sampler(sampler: Sampler | Callable[..., bool], project_id: str, name: str) -> bool:
    """Support the public sampler protocol and simple callables."""

    method = getattr(sampler, "should_sample", None)
    if method is not None:
        return bool(method(project_id=project_id, name=name))
    callable_sampler = cast(Callable[..., bool], sampler)
    return bool(callable_sampler(project_id=project_id, name=name))


class AgentLens:
    """Local AgentLens client for explicit sync and async instrumentation."""

    def __init__(
        self,
        *,
        project_id: str,
        exporter: TraceExporter | None = None,
        sampler: Sampler | Callable[..., bool] | None = None,
        redactor: Redactor | None = None,
        attributes: Mapping[str, JSONValue] | None = None,
        clock: Clock = utc_now,
        id_factory: IDFactory = uuid4,
    ) -> None:
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValidationError("project_id must be a non-empty string")
        if not callable(clock):
            raise ValidationError("clock must be callable")
        if not callable(id_factory):
            raise ValidationError("id_factory must be callable")
        if redactor is not None and not callable(redactor):
            raise ValidationError("redactor must be callable")
        self.project_id = project_id
        self._exporter = exporter if exporter is not None else InMemoryTraceExporter()
        self._sampler = sampler if sampler is not None else AlwaysOnSampler()
        self._redactor = redactor
        self._default_attributes = _copy_attributes(attributes or {}, "attributes")
        self._clock = clock
        self._id_factory = id_factory
        self._diagnostics: list[str] = []

    @property
    def exporter(self) -> TraceExporter:
        """Return the configured local exporter."""

        return self._exporter

    @property
    def diagnostics(self) -> tuple[str, ...]:
        """Return non-sensitive SDK diagnostic categories."""

        return tuple(self._diagnostics)

    def trace(
        self,
        name: str,
        *,
        session_id: str | None = None,
        attributes: Mapping[str, JSONValue] | None = None,
    ) -> TraceContext:
        """Create an explicit root trace context."""

        if not isinstance(name, str) or not name.strip():
            raise ValidationError("trace name must be a non-empty string")
        if session_id is not None and not isinstance(session_id, str):
            raise ValidationError("session_id must be a string or None")
        return TraceContext(
            self,
            name=name,
            session_id=session_id,
            attributes=attributes or {},
        )

    def current_trace(self) -> TraceContext | None:
        """Return the current context-local trace, if any."""

        return current_trace()

    def current_span(self) -> SpanContext | None:
        """Return the current context-local span, if any."""

        return current_span()

    def flush(self) -> None:
        """Flush a configured exporter when it exposes a local flush hook."""

        flush = getattr(self._exporter, "flush", None)
        if flush is not None:
            try:
                flush()
            except Exception:
                self._diagnostic("export failure")

    def shutdown(self) -> None:
        """Shut down a configured exporter when it exposes a local hook."""

        shutdown = getattr(self._exporter, "shutdown", None)
        if shutdown is not None:
            try:
                shutdown()
            except Exception:
                self._diagnostic("export failure")

    def _new_id(self) -> UUID:
        value = self._id_factory()
        if not isinstance(value, UUID):
            raise InstrumentationError("id_factory must return UUID objects")
        return value

    def _diagnostic(self, category: str) -> None:
        if category not in self._diagnostics:
            self._diagnostics.append(category)

    def _redact(
        self,
        value: object,
        *,
        field: str,
        context: Mapping[str, str],
    ) -> JSONValue:
        """Copy, optionally redact, and validate one explicit payload."""

        copied = _copy_json(value, field)
        if self._redactor is None:
            return copied
        try:
            redacted = self._redactor(
                copied,
                field=field,
                context=dict(context),
            )
        except Exception as exc:
            raise _RedactionFailure from exc
        try:
            return _copy_json(redacted, f"redacted {field}")
        except ValidationError as exc:
            raise _RedactionFailure from exc

    def _export(self, trace: Trace) -> None:
        try:
            self._exporter.export(trace)
        except Exception:
            self._diagnostic("export failure")


class TraceContext:
    """Mutable runtime trace handle that finalizes into an M1 Trace."""

    def __init__(
        self,
        client: AgentLens,
        *,
        name: str,
        session_id: str | None,
        attributes: Mapping[str, JSONValue],
    ) -> None:
        self.client = client
        self.trace_id = client._new_id()
        self.project_id = client.project_id
        self.name = name
        self.session_id = session_id
        self.started_at = client._clock()
        self.ended_at: datetime | None = None
        self.status = Status.UNSET
        self._sampled = _call_sampler(client._sampler, client.project_id, name)
        self._state = "created"
        self._trace_token: contextvars.Token[TraceContext | None] | None = None
        self._span_token: contextvars.Token[SpanContext | None] | None = None
        self._spans: list[SpanContext] = []
        self._events: list[Event] = []
        self._attributes: dict[str, JSONValue] = {}
        self._capture_failed = False
        self._result: Trace | None = None
        self._set_initial_attributes(attributes)

    @property
    def sampled(self) -> bool:
        """Return the root sampling decision made at construction."""

        return self._sampled

    @property
    def finished_trace(self) -> Trace | None:
        """Return the immutable M1 result after exit, or None if dropped."""

        return self._result

    @property
    def result(self) -> Trace | None:
        """Alias for :attr:`finished_trace`."""

        return self._result

    def __enter__(self) -> TraceContext:
        if self._state != "created":
            raise InstrumentationError("trace context cannot be re-entered")
        self._state = "active"
        self._trace_token = _CURRENT_TRACE.set(self)
        self._span_token = _CURRENT_SPAN.set(None)
        return self

    async def __aenter__(self) -> TraceContext:
        return self.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> Literal[False]:
        if self._state != "active":
            raise InstrumentationError("trace context is not active")
        try:
            if exc is not None:
                self._record_exception(exc, tb)
            self.ended_at = self.client._clock()
            self._finish_open_spans()
            self._state = "finished"
            if self._sampled and not self._capture_failed:
                try:
                    self._result = Trace(
                        trace_id=self.trace_id,
                        project_id=self.project_id,
                        session_id=self.session_id,
                        name=self.name,
                        started_at=self.started_at,
                        ended_at=self.ended_at,
                        status=self.status,
                        spans=[span.finished_span for span in self._spans if span.finished_span],
                        events=self._events,
                        attributes=self._attributes,
                    )
                    self.client._export(self._result)
                except Exception:
                    self.client._diagnostic("finalization failure")
                    self._result = None
        finally:
            self._restore_context()
        return False

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool:
        return self.__exit__(exc_type, exc, tb)

    def span(self, name: str, *, span_type: str = "custom") -> SpanContext:
        """Create a child span context; it must be entered before use."""

        self._require_active()
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("span name must be a non-empty string")
        return SpanContext(self, name=name, span_type=span_type)

    def set_attribute(self, key: str, value: JSONValue) -> None:
        """Record one explicit trace attribute."""

        self._require_active()
        self._set_attribute(self._attributes, key, value, "trace.attributes")

    def set_attributes(self, values: Mapping[str, JSONValue]) -> None:
        """Record explicit trace attributes."""

        self._require_active()
        for key, value in _copy_attributes(values, "trace.attributes").items():
            self._set_attribute(self._attributes, key, value, "trace.attributes")

    def add_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, JSONValue] | None = None,
    ) -> Event | None:
        """Record a trace-level event with explicit attributes."""

        self._require_active()
        return self._add_event(name, span_id=None, attributes=attributes or {})

    def set_status(self, status: Status | str) -> None:
        """Set a manual observed status; exceptions always force error."""

        self._require_active()
        self.status = normalize_status(status)

    def _set_initial_attributes(self, values: Mapping[str, JSONValue]) -> None:
        merged = dict(self.client._default_attributes)
        merged.update(_copy_attributes(values, "trace.attributes"))
        for key, value in merged.items():
            self._set_attribute(self._attributes, key, value, "trace.attributes")

    def _set_attribute(
        self,
        target: dict[str, JSONValue],
        key: str,
        value: object,
        field: str,
    ) -> None:
        if not isinstance(key, str) or not key:
            raise ValidationError("attribute keys must be non-empty strings")
        if self._capture_failed:
            return
        context = {"project_id": self.project_id, "trace_id": str(self.trace_id)}
        try:
            target[key] = self.client._redact(value, field=f"{field}.{key}", context=context)
        except _RedactionFailure:
            self._fail_capture("redaction failure")

    def _add_event(
        self,
        name: str,
        *,
        span_id: UUID | None,
        attributes: Mapping[str, JSONValue],
    ) -> Event | None:
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("event name must be a non-empty string")
        if not self._sampled or self._capture_failed:
            return None
        copied_attributes = _copy_attributes(attributes, "event.attributes")
        redacted: dict[str, JSONValue] = {}
        for key, value in copied_attributes.items():
            self._set_attribute(
                redacted,
                key,
                value,
                "event.attributes",
            )
        if self._capture_failed:
            return None
        event = Event(
            event_id=self.client._new_id(),
            trace_id=self.trace_id,
            span_id=span_id,
            name=name,
            timestamp=self.client._clock(),
            attributes=redacted,
        )
        self._events.append(event)
        return event

    def _require_active(self) -> None:
        if self._state != "active":
            raise InstrumentationError("trace is not active")

    def _fail_capture(self, category: str) -> None:
        if not self._capture_failed:
            self._capture_failed = True
            self.client._diagnostic(category)

    def _record_exception(self, exc: BaseException, tb: Any) -> None:
        self.status = Status.ERROR
        try:
            message = str(exc)
            stack = "".join(traceback_module.format_exception(type(exc), exc, tb))
            context = {"project_id": self.project_id, "trace_id": str(self.trace_id)}
            redacted_message = self.client._redact(
                message,
                field="error.message",
                context=context,
            )
            redacted_stack = self.client._redact(
                stack,
                field="error.traceback",
                context=context,
            )
            if not isinstance(redacted_message, str) or not isinstance(redacted_stack, str):
                raise _RedactionFailure
            if self._sampled:
                self._events.append(
                    Event(
                        event_id=self.client._new_id(),
                        trace_id=self.trace_id,
                        name="error",
                        timestamp=self.client._clock(),
                        attributes={
                            "error_type": type(exc).__name__,
                            "message": redacted_message,
                            "traceback": redacted_stack,
                        },
                    )
                )
        except _RedactionFailure:
            self._fail_capture("redaction failure")

    def _finish_open_spans(self) -> None:
        for span in self._spans:
            if span._state == "active":
                span._finish_partial()

    def _restore_context(self) -> None:
        if self._span_token is not None:
            _CURRENT_SPAN.reset(self._span_token)
            self._span_token = None
        if self._trace_token is not None:
            _CURRENT_TRACE.reset(self._trace_token)
            self._trace_token = None


class SpanContext:
    """Mutable runtime span handle that finalizes into an M1 Span."""

    def __init__(self, trace: TraceContext, *, name: str, span_type: str) -> None:
        if not isinstance(span_type, str) or not span_type.strip():
            raise ValidationError("span_type must be a non-empty string")
        self.trace = trace
        self.client = trace.client
        self.span_id = self.client._new_id()
        self.trace_id = trace.trace_id
        self.parent_span_id: UUID | None = None
        self.name = name
        self.span_type = span_type
        self.started_at: datetime | None = None
        self.ended_at: datetime | None = None
        self.status = Status.UNSET
        self._input: JSONValue | None = None
        self._output: JSONValue | None = None
        self._attributes: dict[str, JSONValue] = {}
        self._usage: Usage | None = None
        self._error: ErrorInfo | None = None
        self._state = "created"
        self._span_token: contextvars.Token[SpanContext | None] | None = None
        self._result: Span | None = None

    @property
    def finished_span(self) -> Span | None:
        """Return the immutable M1 result after span completion."""

        return self._result

    def __enter__(self) -> SpanContext:
        if self._state != "created":
            raise InstrumentationError("span context cannot be re-entered")
        if self.trace._state != "active" or current_trace() is not self.trace:
            raise InstrumentationError("span must be entered inside its active trace")
        parent = current_span()
        self.parent_span_id = parent.span_id if parent is not None else None
        self.started_at = self.client._clock()
        self.trace._spans.append(self)
        self._state = "active"
        self._span_token = _CURRENT_SPAN.set(self)
        return self

    async def __aenter__(self) -> SpanContext:
        return self.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> Literal[False]:
        if self._state != "active":
            raise InstrumentationError("span context is not active")
        try:
            if exc is not None:
                self._record_exception(exc, tb)
            self.ended_at = self.client._clock()
            self._state = "finished"
            if not self.trace._capture_failed and self.trace.sampled:
                try:
                    self._result = self._to_domain()
                except Exception:
                    self.trace._fail_capture("finalization failure")
        finally:
            if self._span_token is not None:
                _CURRENT_SPAN.reset(self._span_token)
                self._span_token = None
        return False

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool:
        return self.__exit__(exc_type, exc, tb)

    def set_attribute(self, key: str, value: JSONValue) -> None:
        """Record one explicit span attribute."""

        self._require_active()
        self.trace._set_attribute(self._attributes, key, value, "span.attributes")

    def set_attributes(self, values: Mapping[str, JSONValue]) -> None:
        """Record explicit span attributes."""

        self._require_active()
        for key, value in _copy_attributes(values, "span.attributes").items():
            self.trace._set_attribute(self._attributes, key, value, "span.attributes")

    def set_input(self, value: JSONValue) -> None:
        """Record an explicit span input payload."""

        self._require_active()
        if self.trace._capture_failed:
            return
        context = {
            "project_id": self.trace.project_id,
            "trace_id": str(self.trace.trace_id),
            "span_id": str(self.span_id),
        }
        try:
            self._input = self.client._redact(value, field="span.input", context=context)
        except _RedactionFailure:
            self.trace._fail_capture("redaction failure")

    def set_output(self, value: JSONValue) -> None:
        """Record an explicit span output payload."""

        self._require_active()
        if self.trace._capture_failed:
            return
        context = {
            "project_id": self.trace.project_id,
            "trace_id": str(self.trace.trace_id),
            "span_id": str(self.span_id),
        }
        try:
            self._output = self.client._redact(value, field="span.output", context=context)
        except _RedactionFailure:
            self.trace._fail_capture("redaction failure")

    def set_usage(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cached_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> None:
        """Record provider-neutral observed token counts."""

        self._require_active()
        self._usage = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
        )

    def add_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, JSONValue] | None = None,
    ) -> Event | None:
        """Record an event associated with this span."""

        self._require_active()
        return self.trace._add_event(name, span_id=self.span_id, attributes=attributes or {})

    def set_status(self, status: Status | str) -> None:
        """Set a manual observed status; exceptions always force error."""

        self._require_active()
        self.status = normalize_status(status)

    def _record_exception(self, exc: BaseException, tb: Any) -> None:
        self.status = Status.ERROR
        try:
            message = str(exc)
            stack = "".join(traceback_module.format_exception(type(exc), exc, tb))
            context = {
                "project_id": self.trace.project_id,
                "trace_id": str(self.trace.trace_id),
                "span_id": str(self.span_id),
            }
            redacted_message = self.client._redact(
                message,
                field="error.message",
                context=context,
            )
            redacted_stack = self.client._redact(
                stack,
                field="error.traceback",
                context=context,
            )
            if not isinstance(redacted_message, str) or not isinstance(redacted_stack, str):
                raise _RedactionFailure
            self._error = ErrorInfo(
                error_type=type(exc).__name__,
                message=redacted_message,
                traceback=redacted_stack,
            )
        except _RedactionFailure:
            self.trace._fail_capture("redaction failure")

    def _finish_partial(self) -> None:
        if self._state != "active":
            return
        self._state = "finished"
        if not self.trace._capture_failed and self.trace.sampled:
            try:
                self._result = self._to_domain()
            except Exception:
                self.trace._fail_capture("finalization failure")
        if self._span_token is not None:
            _CURRENT_SPAN.reset(self._span_token)
            self._span_token = None

    def _to_domain(self) -> Span:
        if self.started_at is None:
            raise InstrumentationError("span was never started")
        return Span(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            span_type=self.span_type,
            name=self.name,
            started_at=self.started_at,
            ended_at=self.ended_at,
            status=self.status,
            input=self._input,
            output=self._output,
            attributes=self._attributes,
            usage=self._usage,
            error=self._error,
        )

    def _require_active(self) -> None:
        if self._state != "active":
            raise InstrumentationError("span is not active")


__all__ = (
    "AgentLens",
    "Redactor",
    "SpanContext",
    "TraceContext",
    "current_span",
    "current_trace",
)
