"""M3 gateway, sink, auth, limits, and HTTP exporter integration contracts."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from urllib.error import HTTPError
from uuid import uuid4

import httpx
import pytest

from agentlens import AgentLens, HttpTraceExporter
from agentlens.api import (
    GatewayConfig,
    InMemoryApiKeyAuthenticator,
    InMemoryRateLimiter,
    InMemoryTraceSink,
    create_app,
)
from agentlens.domain import Event, Span, Trace
from agentlens.exceptions import HttpExportError

START = datetime(2025, 1, 1, 12, tzinfo=UTC)
API_KEY = "dev-m3-key-not-real"


def make_trace_payload(
    *, project_id: str = "project-a", name: str = "request"
) -> dict[str, object]:
    trace_id = uuid4()
    trace = Trace(
        trace_id=trace_id,
        project_id=project_id,
        name=name,
        started_at=START,
        spans=(Span(trace_id=trace_id, name="work", started_at=START),),
    )
    return trace.to_dict()


def make_gateway(
    *,
    config: GatewayConfig | None = None,
    project_id: str = "project-a",
    api_key: str = API_KEY,
    enabled: bool = True,
    clock=None,
) -> tuple[object, InMemoryTraceSink, InMemoryApiKeyAuthenticator]:
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=api_key,
        key_id="key-a",
        project_id=project_id,
        enabled=enabled,
    )
    sink = InMemoryTraceSink()
    rate_limiter = None
    if clock is not None:
        chosen_config = config or GatewayConfig()
        rate_limiter = InMemoryRateLimiter(
            max_requests=chosen_config.rate_limit,
            window_seconds=chosen_config.rate_window_seconds,
            clock=clock,
        )
    app = create_app(
        config=config,
        authenticator=authenticator,
        sink=sink,
        rate_limiter=rate_limiter,
    )
    return app, sink, authenticator


async def request(
    app: object,
    method: str,
    path: str,
    *,
    api_key: str | None = API_KEY,
    json_body: object | None = None,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request_headers = dict(headers or {})
    if api_key is not None:
        request_headers.setdefault("Authorization", f"Bearer {api_key}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(
            method,
            path,
            headers=request_headers,
            json=json_body,
            content=content,
        )


def test_health_openapi_and_request_ids() -> None:
    app, _, _ = make_gateway()

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        return (
            await request(app, "GET", "/health/live", api_key=None),
            await request(app, "GET", "/health/ready", api_key=None),
            await request(app, "GET", "/openapi.json", api_key=None),
        )

    live, ready, openapi = asyncio.run(run())
    assert live.status_code == 200 and live.json() == {"status": "ok"}
    assert ready.status_code == 200 and ready.json() == {"status": "ok"}
    paths = openapi.json()["paths"]
    assert {"/v1/traces", "/v1/traces/batch", "/health/live", "/health/ready"} <= set(paths)
    assert live.headers["x-request-id"] != ready.headers["x-request-id"]


def test_single_trace_reconstructs_canonical_object_and_is_idempotent() -> None:
    app, sink, _ = make_gateway()
    payload = make_trace_payload()

    async def run() -> tuple[httpx.Response, httpx.Response]:
        return (
            await request(app, "POST", "/v1/traces", json_body=payload),
            await request(app, "POST", "/v1/traces", json_body=payload),
        )

    first, duplicate = asyncio.run(run())
    assert first.status_code == 202
    assert first.json()["duplicate"] is False
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicate"] is True
    assert len(sink.traces) == 1
    assert isinstance(sink.traces[0], Trace)
    assert sink.traces[0] == Trace.from_dict(payload)
    assert first.json()["request_id"] == first.headers["x-request-id"]


def test_conflicting_identity_does_not_overwrite_original() -> None:
    app, sink, _ = make_gateway()
    first = make_trace_payload(name="original")
    changed = dict(first)
    changed["name"] = "changed"

    async def run() -> tuple[httpx.Response, httpx.Response]:
        return (
            await request(app, "POST", "/v1/traces", json_body=first),
            await request(app, "POST", "/v1/traces", json_body=changed),
        )

    accepted, conflict = asyncio.run(run())
    assert accepted.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "trace_conflict"
    assert conflict.json()["error"]["request_id"] == conflict.headers["x-request-id"]
    assert len(sink.traces) == 1 and sink.traces[0].name == "original"


def test_same_trace_id_isolated_between_authorized_projects() -> None:
    app, sink, authenticator = make_gateway()
    other_key = "project-b-key-not-real"
    authenticator.register(api_key=other_key, key_id="key-b", project_id="project-b")
    project_a = make_trace_payload(name="project-a")
    project_b = dict(project_a)
    project_b["project_id"] = "project-b"

    async def run() -> tuple[httpx.Response, httpx.Response]:
        return (
            await request(app, "POST", "/v1/traces", json_body=project_a),
            await request(app, "POST", "/v1/traces", api_key=other_key, json_body=project_b),
        )

    accepted_a, accepted_b = asyncio.run(run())
    assert accepted_a.status_code == 202
    assert accepted_b.status_code == 202
    assert len(sink.traces) == 2


def test_authentication_and_project_isolation() -> None:
    app, sink, _ = make_gateway()
    payload = make_trace_payload()
    other_project = make_trace_payload(project_id="project-b")

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        return (
            await request(app, "POST", "/v1/traces", api_key=None, json_body=payload),
            await request(
                app,
                "POST",
                "/v1/traces",
                api_key=API_KEY,
                json_body=payload,
                headers={"Authorization": "Token malformed"},
            ),
            await request(app, "POST", "/v1/traces", api_key="wrong", json_body=payload),
            await request(app, "POST", "/v1/traces", json_body=other_project),
        )

    missing, malformed, invalid, forbidden = asyncio.run(run())
    assert [response.status_code for response in (missing, malformed, invalid, forbidden)] == [
        401,
        401,
        401,
        403,
    ]
    assert forbidden.json()["error"]["code"] == "project_forbidden"
    responses = (missing, malformed, invalid, forbidden)
    assert API_KEY not in json.dumps([response.json() for response in responses])
    assert sink.traces == ()


def test_unknown_schema_invalid_graph_and_content_type_are_safe_client_errors() -> None:
    app, sink, _ = make_gateway()
    unknown = make_trace_payload()
    unknown["schema_version"] = "agentlens-trace-v999"
    malformed = make_trace_payload()
    malformed["spans"] = [{"bad": "span"}]

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        return (
            await request(app, "POST", "/v1/traces", json_body=unknown),
            await request(app, "POST", "/v1/traces", json_body=malformed),
            await request(
                app,
                "POST",
                "/v1/traces",
                headers={"Content-Type": "text/plain"},
                content=b"{}",
            ),
        )

    unsupported, invalid, media = asyncio.run(run())
    assert unsupported.status_code == 422
    assert unsupported.json()["error"]["code"] == "unsupported_schema"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_trace"
    assert media.status_code == 415
    assert media.json()["error"]["code"] == "unsupported_media_type"
    assert "trace-v999" not in unsupported.text
    assert sink.traces == ()


def test_gateway_accepts_partial_multi_root_and_events_only_canonical_traces() -> None:
    app, sink, _ = make_gateway()
    partial = Trace(
        project_id="project-a",
        name="partial",
        started_at=START,
    ).to_dict()
    multi_root_id = uuid4()
    multi_root = Trace(
        trace_id=multi_root_id,
        project_id="project-a",
        name="multi-root",
        started_at=START,
        spans=(
            Span(trace_id=multi_root_id, name="root-a", started_at=START),
            Span(trace_id=multi_root_id, name="root-b", started_at=START),
        ),
    ).to_dict()
    events_only_id = uuid4()
    events_only = Trace(
        trace_id=events_only_id,
        project_id="project-a",
        name="events-only",
        started_at=START,
        events=(Event(trace_id=events_only_id, name="observed", timestamp=START),),
    ).to_dict()

    async def run() -> httpx.Response:
        return await request(
            app,
            "POST",
            "/v1/traces/batch",
            json_body={"traces": [partial, multi_root, events_only]},
        )

    response = asyncio.run(run())
    assert response.status_code == 202
    assert response.json()["accepted_count"] == 3
    assert len(sink.traces) == 3


def test_batch_is_atomic_and_duplicate_ids_are_rejected() -> None:
    app, sink, _ = make_gateway(config=GatewayConfig(max_batch_size=2))
    valid_a = make_trace_payload(name="a")
    valid_b = make_trace_payload(name="b")
    invalid = dict(valid_b)
    invalid["trace_id"] = "not-a-uuid"

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
        return (
            await request(
                app, "POST", "/v1/traces/batch", json_body={"traces": [valid_a, valid_b]}
            ),
            await request(
                app,
                "POST",
                "/v1/traces/batch",
                json_body={
                    "traces": [make_trace_payload(), make_trace_payload(), make_trace_payload()]
                },
            ),
            await request(
                app,
                "POST",
                "/v1/traces/batch",
                json_body={"traces": [valid_a, invalid]},
            ),
            await request(app, "POST", "/v1/traces/batch", json_body={"traces": []}),
        )

    accepted, over_limit, malformed, empty = asyncio.run(run())
    assert accepted.status_code == 202
    assert accepted.json()["accepted_count"] == 2
    assert len(sink.traces) == 2
    assert over_limit.status_code == 413
    assert over_limit.json()["error"]["code"] == "batch_too_large"
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "invalid_trace"
    assert len(sink.traces) == 2
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "invalid_batch"


def test_batch_duplicate_trace_ids_and_existing_conflict_are_preflighted() -> None:
    app, sink, _ = make_gateway()
    first = make_trace_payload(name="first")
    duplicate = dict(first)
    duplicate["name"] = "different"

    async def run() -> tuple[httpx.Response, httpx.Response]:
        accepted = await request(app, "POST", "/v1/traces", json_body=first)
        batch = await request(
            app,
            "POST",
            "/v1/traces/batch",
            json_body={"traces": [make_trace_payload(name="new"), duplicate]},
        )
        return accepted, batch

    accepted, batch = asyncio.run(run())
    assert accepted.status_code == 202
    assert batch.status_code == 409
    assert batch.json()["error"]["code"] == "trace_conflict"
    assert len(sink.traces) == 1
    assert sink.traces[0].name == "first"


def test_limits_content_type_and_actual_body_size() -> None:
    app, sink, _ = make_gateway(config=GatewayConfig(max_request_bytes=100))
    payload = make_trace_payload()

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        return (
            await request(app, "POST", "/v1/traces", json_body=payload),
            await request(
                app,
                "POST",
                "/v1/traces",
                headers={"Content-Type": "application/json"},
                content=b"{" + b"x" * 200,
            ),
            await request(
                app,
                "POST",
                "/v1/traces",
                headers={"Content-Type": "application/json", "Content-Length": "1"},
                content=b"{" + b"x" * 200,
            ),
        )

    too_large_json, too_large_raw, misleading_length = asyncio.run(run())
    assert too_large_json.status_code == 413
    assert too_large_raw.status_code == 413
    assert misleading_length.status_code == 413
    assert too_large_raw.json()["error"]["code"] == "payload_too_large"
    assert too_large_raw.headers["x-request-id"] == too_large_raw.json()["error"]["request_id"]
    assert sink.traces == ()


def test_rate_limit_is_per_key_and_resets_without_sleeping() -> None:
    now = [0.0]
    config = GatewayConfig(rate_limit=1, rate_window_seconds=10)
    app, sink, authenticator = make_gateway(config=config, clock=lambda: now[0])
    other_key = "other-m3-key-not-real"
    authenticator.register(api_key=other_key, key_id="key-b", project_id="project-a")
    first = make_trace_payload(name="first")
    second = make_trace_payload(name="second")

    async def run() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        return (
            await request(app, "POST", "/v1/traces", json_body=first),
            await request(app, "POST", "/v1/traces", json_body=second),
            await request(app, "POST", "/v1/traces", api_key=other_key, json_body=second),
        )

    accepted, limited, other = asyncio.run(run())
    assert accepted.status_code == 202
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "10"
    assert other.status_code == 202
    now[0] = 11.0
    reset = asyncio.run(
        request(app, "POST", "/v1/traces", json_body=make_trace_payload(name="after-reset"))
    )
    assert reset.status_code == 202
    assert len(sink.traces) == 3


def test_disabled_keys_are_unauthorized() -> None:
    app, _, _ = make_gateway(api_key="disabled-key-not-real", enabled=False)
    response = asyncio.run(
        request(
            app,
            "POST",
            "/v1/traces",
            api_key="disabled-key-not-real",
            json_body=make_trace_payload(),
        )
    )
    assert response.status_code == 401


def test_http_exporter_builds_secure_canonical_request() -> None:
    captured: dict[str, object] = {}

    class Response:
        status = 202

        def read(self) -> bytes:
            return b"{}"

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            del args

    def opener(request_object: object, *, timeout: float) -> Response:
        captured["request"] = request_object
        captured["timeout"] = timeout
        return Response()

    trace = Trace(trace_id=uuid4(), project_id="project-a", name="export", started_at=START)
    exporter = HttpTraceExporter(
        base_url="http://gateway.test/",
        api_key=API_KEY,
        timeout=2.5,
        opener=opener,
    )
    exporter.export(trace)
    request_object = captured["request"]
    assert request_object.full_url == "http://gateway.test/v1/traces"  # type: ignore[attr-defined]
    assert request_object.get_header("Authorization") == f"Bearer {API_KEY}"  # type: ignore[attr-defined]
    assert request_object.get_header("Content-type") == "application/json"  # type: ignore[attr-defined]
    assert json.loads(request_object.data) == trace.to_dict()  # type: ignore[attr-defined]
    assert captured["timeout"] == 2.5
    assert API_KEY not in repr(exporter)


def test_http_exporter_translates_gateway_failures_without_payload_details() -> None:
    class Response:
        def __init__(self, status: int) -> None:
            self.status = status

        def read(self) -> bytes:
            return b"gateway detail must not escape"

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            del args

    trace = Trace(trace_id=uuid4(), project_id="project-a", name="export", started_at=START)
    for status in (401, 403, 409, 429, 500):

        def opener(request_object: object, *, timeout: float, status: int = status) -> Response:
            del request_object, timeout
            return Response(status)

        exporter = HttpTraceExporter(
            base_url="http://gateway.test",
            api_key=API_KEY,
            opener=opener,
        )
        with pytest.raises(HttpExportError) as raised:
            exporter.export(trace)
        assert str(status) in str(raised.value)
        assert "gateway detail" not in str(raised.value)
        assert API_KEY not in str(raised.value)


def test_sdk_http_exporter_reaches_gateway_and_stores_finished_trace() -> None:
    app, sink, _ = make_gateway()

    class Response:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            del args

    def opener(request_object: object, *, timeout: float) -> Response:
        async def send() -> Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://gateway.test",
            ) as client:
                response = await client.request(
                    "POST",
                    request_object.full_url,  # type: ignore[attr-defined]
                    headers=dict(request_object.header_items()),  # type: ignore[attr-defined]
                    content=request_object.data,  # type: ignore[attr-defined]
                    timeout=timeout,
                )
                return Response(response.status_code, response.content)

        return asyncio.run(send())

    exporter = HttpTraceExporter(
        base_url="http://gateway.test",
        api_key=API_KEY,
        opener=opener,
    )
    client = AgentLens(project_id="project-a", exporter=exporter, clock=lambda: START)
    with client.trace("request") as trace:
        with trace.span("work", span_type="custom") as span:
            span.set_input({"query": "hello"})

    assert len(sink.traces) == 1
    assert sink.traces[0] == trace.finished_trace
    assert sink.traces[0].spans[0].input == {"query": "hello"}


def test_http_exporter_failures_are_safe_and_m2_isolates_host_application() -> None:
    def broken_opener(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise OSError("connection refused")

    trace = Trace(trace_id=uuid4(), project_id="project-a", name="export", started_at=START)
    exporter = HttpTraceExporter(
        base_url="http://gateway.test",
        api_key=API_KEY,
        opener=broken_opener,  # type: ignore[arg-type]
    )
    with pytest.raises(HttpExportError) as raised:
        exporter.export(trace)
    assert API_KEY not in str(raised.value)
    assert API_KEY not in repr(exporter)

    client = AgentLens(project_id="project-a", exporter=exporter)
    completed = False
    with client.trace("host-safe"):
        completed = True
    assert completed
    assert "export failure" in client.diagnostics


def test_http_exporter_does_not_leak_http_error_body_or_key() -> None:
    def unauthorized(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise HTTPError("http://gateway.test/v1/traces", 401, API_KEY, {}, None)

    exporter = HttpTraceExporter(
        base_url="http://gateway.test",
        api_key=API_KEY,
        opener=unauthorized,  # type: ignore[arg-type]
    )
    with pytest.raises(HttpExportError) as raised:
        exporter.export(Trace(trace_id=uuid4(), project_id="project-a", name="x", started_at=START))
    assert API_KEY not in str(raised.value)
