"""Real PostgreSQL M4 persistence, query, isolation, and concurrency contracts."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.domain import ErrorInfo, Event, Span, Status, Trace, Usage
from agentlens.storage import DatabaseConfig, PostgresTraceRepository, TraceQuery
from agentlens.storage.contracts import TraceConflictError
from agentlens.storage.models import events, spans, traces

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="M4 integration tests require AGENTLENS_TEST_DATABASE_URL or AGENTLENS_DATABASE_URL",
)

START = datetime(2025, 1, 1, 12, tzinfo=UTC)


def make_trace(
    project_id: str,
    *,
    name: str = "request",
    status: Status = Status.OK,
    session_id: str | None = "session-a",
    started_at: datetime = START,
    span_type: str = "llm",
    trace_id: UUID | None = None,
    complex_payload: bool = True,
) -> Trace:
    actual_trace_id = trace_id or uuid4()
    span_id = uuid4()
    span = Span(
        trace_id=actual_trace_id,
        span_id=span_id,
        name="work",
        span_type=span_type,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=1),
        status=status,
        input={"query": "hello"} if complex_payload else None,
        output={"answer": ["world", 1]} if complex_payload else None,
        attributes={"nested": {"enabled": True}} if complex_payload else {},
        usage=Usage(input_tokens=2, output_tokens=3, total_tokens=5) if complex_payload else None,
        error=ErrorInfo(error_type="ObservedError", message="example")
        if status is Status.ERROR
        else None,
    )
    return Trace(
        trace_id=actual_trace_id,
        project_id=project_id,
        session_id=session_id,
        name=name,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=2),
        status=status,
        spans=(span,) if complex_payload else (),
        events=(
            Event(
                trace_id=actual_trace_id,
                span_id=span_id,
                name="finished",
                timestamp=started_at + timedelta(seconds=1),
                attributes={"count": 1},
            ),
        )
        if complex_payload
        else (),
        attributes={"top": ["a", 2]} if complex_payload else {},
    )


@pytest.fixture()
def repository() -> tuple[PostgresTraceRepository, str]:
    assert DATABASE_URL is not None
    config = DatabaseConfig(url=DATABASE_URL)
    repo = PostgresTraceRepository(config)
    project_id = f"m4-{uuid4()}"
    yield repo, project_id
    with repo.engine.begin() as connection:
        connection.execute(delete(events).where(events.c.project_id == project_id))
        connection.execute(delete(spans).where(spans.c.project_id == project_id))
        connection.execute(delete(traces).where(traces.c.project_id == project_id))
    repo.dispose()


def test_complex_round_trip_and_repository_restart(
    repository: tuple[PostgresTraceRepository, str],
) -> None:
    repo, project_id = repository
    trace = make_trace(project_id)
    assert repo.ingest(trace).duplicate is False
    assert repo.get_trace(project_id, trace.trace_id) == trace
    repo.dispose()

    restarted = PostgresTraceRepository(DatabaseConfig(url=DATABASE_URL or ""))
    try:
        assert restarted.ingest(trace).duplicate is True
        assert restarted.get_trace(project_id, trace.trace_id) == trace
    finally:
        restarted.dispose()


def test_partial_multi_root_and_events_only_round_trip(
    repository: tuple[PostgresTraceRepository, str],
) -> None:
    repo, project_id = repository
    partial = make_trace(project_id, name="partial", complex_payload=False)
    root_id = uuid4()
    multi_root = Trace(
        trace_id=root_id,
        project_id=project_id,
        name="multi-root",
        started_at=START,
        spans=(
            Span(trace_id=root_id, name="root-a", started_at=START),
            Span(trace_id=root_id, name="root-b", started_at=START),
        ),
    )
    event_id = uuid4()
    events_only = Trace(
        trace_id=event_id,
        project_id=project_id,
        name="events-only",
        started_at=START,
        events=(Event(trace_id=event_id, name="observed", timestamp=START),),
    )
    for trace in (partial, multi_root, events_only):
        assert repo.ingest(trace).duplicate is False
        assert repo.get_trace(project_id, trace.trace_id) == trace


def test_batch_conflict_rolls_back_new_rows(
    repository: tuple[PostgresTraceRepository, str],
) -> None:
    repo, project_id = repository
    existing = make_trace(project_id, name="existing")
    new_trace = make_trace(project_id, name="new")
    changed = make_trace(project_id, name="changed", trace_id=existing.trace_id)
    repo.ingest(existing)
    with pytest.raises(TraceConflictError):
        repo.ingest_many((new_trace, changed))
    assert repo.get_trace(project_id, new_trace.trace_id) is None
    assert repo.get_trace(project_id, existing.trace_id) == existing


def test_concurrent_identical_submissions_keep_one_row(
    repository: tuple[PostgresTraceRepository, str],
) -> None:
    _, project_id = repository
    trace = make_trace(project_id)
    config = DatabaseConfig(url=DATABASE_URL or "")
    repositories = [PostgresTraceRepository(config), PostgresTraceRepository(config)]
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda item: item.ingest(trace), repositories))
        assert sorted(result.duplicate for result in results) == [False, True]
        assert repositories[0].get_trace(project_id, trace.trace_id) == trace
    finally:
        for item in repositories:
            item.dispose()


def test_concurrent_conflicts_preserve_one_authoritative_trace(
    repository: tuple[PostgresTraceRepository, str],
) -> None:
    _, project_id = repository
    trace_id = uuid4()
    left = make_trace(project_id, name="left", trace_id=trace_id)
    right = make_trace(project_id, name="right", trace_id=trace_id)
    config = DatabaseConfig(url=DATABASE_URL or "")
    repositories = [PostgresTraceRepository(config), PostgresTraceRepository(config)]

    def submit(pair: tuple[PostgresTraceRepository, Trace]) -> object:
        repo, trace = pair
        try:
            return repo.ingest(trace)
        except TraceConflictError:
            return "conflict"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit, zip(repositories, (left, right), strict=True)))
        assert outcomes.count("conflict") == 1
        stored = repositories[0].get_trace(project_id, trace_id)
        assert stored in (left, right)
    finally:
        for item in repositories:
            item.dispose()


def test_query_filters_and_cursor_pagination(
    repository: tuple[PostgresTraceRepository, str],
) -> None:
    repo, project_id = repository
    traces_to_insert = [
        make_trace(
            project_id,
            name=f"trace-{index}",
            status=Status.OK if index % 2 else Status.ERROR,
            session_id=f"session-{index % 2}",
            span_type="tool" if index == 4 else "llm",
        )
        for index in range(5)
    ]
    for trace in traces_to_insert:
        repo.ingest(trace)

    page = repo.query_traces(project_id, TraceQuery(limit=2))
    ids = [item.trace_id for item in page.items]
    while page.next_cursor is not None:
        page = repo.query_traces(project_id, TraceQuery(limit=2, cursor=page.next_cursor))
        ids.extend(item.trace_id for item in page.items)
    assert len(ids) == 5 and len(set(ids)) == 5
    assert repo.query_traces(project_id, TraceQuery(status="ok", limit=10)).items
    assert len(repo.query_traces(project_id, TraceQuery(name="trace-4", limit=10)).items) == 1
    assert (
        len(repo.query_traces(project_id, TraceQuery(session_id="session-1", limit=10)).items) == 2
    )
    assert len(repo.query_traces(project_id, TraceQuery(span_type="tool", limit=10)).items) == 1
    assert (
        len(
            repo.query_traces(
                project_id,
                TraceQuery(started_from=START, started_to=START, limit=10),
            ).items
        )
        == 5
    )


def test_project_isolation_and_invalid_cursor(
    repository: tuple[PostgresTraceRepository, str],
) -> None:
    repo, project_id = repository
    trace = make_trace(project_id)
    repo.ingest(trace)
    repo.ingest(make_trace(project_id, name="second"))
    assert repo.get_trace("other-project", trace.trace_id) is None
    assert repo.query_traces("other-project", TraceQuery(limit=10)).items == ()
    page = repo.query_traces(project_id, TraceQuery(limit=1))
    assert page.next_cursor is not None
    with pytest.raises(ValueError):
        repo.query_traces(project_id, TraceQuery(limit=1, cursor=page.next_cursor[:-1] + "x"))


def test_database_backed_api_detail_list_and_readiness() -> None:
    assert DATABASE_URL is not None
    project_id = f"m4-api-{uuid4()}"
    key = "m4-api-key-not-real"
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key=key, key_id="m4-api", project_id=project_id)
    app = create_app(
        authenticator=auth,
        database=DatabaseConfig(url=DATABASE_URL),
    )
    trace = make_trace(project_id)

    async def run() -> tuple[
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
    ]:
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return (
                await client.get("/health/live"),
                await client.get("/health/ready"),
                await client.post("/v1/traces", headers=headers, json=trace.to_dict()),
                await client.get(f"/v1/traces/{trace.trace_id}", headers=headers),
                await client.get("/v1/traces?limit=10", headers=headers),
            )

    live, ready, accepted, detail, listing = asyncio.run(run())
    assert live.status_code == 200
    assert ready.status_code == 200
    assert accepted.status_code == 202
    assert detail.status_code == 200
    assert detail.json() == trace.to_dict()
    assert listing.status_code == 200
    assert listing.json()["items"][0]["trace_id"] == str(trace.trace_id)
    repository = app.state.gateway.repository
    page = repository.query_traces(project_id, TraceQuery(limit=10))
    assert len(page.items) == 1
    repository.dispose()


def test_database_down_is_ready_failure_but_live_success() -> None:
    bad = DatabaseConfig(url="postgresql+psycopg://agentlens:agentlens@127.0.0.1:55439/agentlens")
    app = create_app(database=bad)

    async def run() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/health/live"), await client.get("/health/ready")

    live, ready = asyncio.run(run())
    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable"}
    app.state.gateway.repository.dispose()
