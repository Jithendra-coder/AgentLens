"""M8 analytics and runtime contracts against real PostgreSQL and Redis."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.domain import Span, Status, Trace, Usage
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.redis import RedisDispatcher
from agentlens.evaluation.repository import PostgresEvaluationJobRepository
from agentlens.evaluation.result_repository import PostgresEvaluationResultRepository
from agentlens.evaluation.worker import EvaluationWorker
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.models import traces

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL,
    reason="M8 integration tests require real PostgreSQL and Redis",
)


def make_trace(project_id: str, seconds: float | None, status: Status, offset: int) -> Trace:
    trace_id = uuid4()
    started = datetime.now(UTC) - timedelta(minutes=offset)
    ended = started + timedelta(seconds=seconds) if seconds is not None else None
    usage = Usage(input_tokens=2, output_tokens=3, total_tokens=5) if seconds == 1 else None
    return Trace(
        trace_id=trace_id,
        project_id=project_id,
        name="m8-analytics",
        started_at=started,
        ended_at=ended,
        status=status,
        spans=(
            Span(
                trace_id=trace_id,
                span_type="llm",
                name="answer",
                started_at=started,
                ended_at=ended,
                status=status,
                usage=usage,
            ),
        ),
    )


@pytest.fixture()
def m8_runtime():
    assert DATABASE_URL is not None and REDIS_URL is not None
    config = DatabaseConfig(DATABASE_URL)
    trace_repository = PostgresTraceRepository(config)
    job_repository = PostgresEvaluationJobRepository(config, engine=trace_repository.engine)
    result_repository = PostgresEvaluationResultRepository(config, engine=trace_repository.engine)
    runtime = EvaluationRuntimeConfig(
        redis_url=REDIS_URL,
        lease_seconds=2.0,
        heartbeat_seconds=0.2,
        default_timeout_seconds=1.0,
        worker_poll_timeout=0,
    )
    dispatcher = RedisDispatcher(runtime)
    dispatcher._client.delete(runtime.queue_name)
    project_id = f"m8-{uuid4()}"
    values = (
        make_trace(project_id, 1, Status.OK, 2),
        make_trace(project_id, 3, Status.ERROR, 3),
        make_trace(project_id, None, Status.UNSET, 4),
    )
    trace_repository.ingest_many(values)
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key="m8-a", key_id="m8-a", project_id=project_id)
    auth.register(api_key="m8-b", key_id="m8-b", project_id="other-project")
    app = create_app(
        database=config,
        authenticator=auth,
        dispatcher=dispatcher,
        runtime_config=runtime,
    )
    yield (
        config,
        trace_repository,
        job_repository,
        result_repository,
        dispatcher,
        runtime,
        app,
        values,
    )
    with trace_repository.engine.begin() as connection:
        connection.execute(delete(traces).where(traces.c.project_id == project_id))
    dispatcher._client.delete(runtime.queue_name)
    dispatcher.close()
    trace_repository.dispose()


def test_bounded_analytics_and_project_scope(m8_runtime) -> None:
    (
        config,
        trace_repository,
        job_repository,
        result_repository,
        dispatcher,
        runtime,
        app,
        values,
    ) = m8_runtime
    del config, trace_repository
    worker = EvaluationWorker(
        repository=job_repository,
        trace_repository=app.state.gateway.repository,
        dispatcher=dispatcher,
        result_repository=result_repository,
        config=runtime,
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            headers = {"Authorization": "Bearer m8-a"}
            created = await client.post(
                f"/v1/traces/{values[0].trace_id}/evaluations",
                headers=headers,
                json={"evaluation_type": "latency_summary", "config": {}},
            )
            assert created.status_code == 202
            assert worker.run_once() is True
            start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            end = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
            overview = await client.get(
                "/v1/analytics/overview",
                params={"start": start, "end": end},
                headers=headers,
            )
            assert overview.status_code == 200
            body = overview.json()
            assert body["traces"]["count"] == 3
            assert body["traces"]["completed_count"] == 2
            assert body["traces"]["error_count"] == 1
            assert body["latency_ms"]["p50"] == 2000.0
            assert body["latency_ms"]["p95"] == 2900.0
            assert body["reported_tokens"]["total"] == 5
            assert body["evaluations"]["count"] == 1
            timeseries = await client.get("/v1/analytics/timeseries?window=1h", headers=headers)
            assert timeseries.status_code == 200
            evaluations = await client.get("/v1/analytics/evaluations?window=24h", headers=headers)
            assert evaluations.status_code == 200
            assert evaluations.json()["groups"][0]["evaluator_version"]
            results = await client.get("/v1/evaluation-results?window=24h", headers=headers)
            assert results.status_code == 200
            assert len(results.json()["items"]) == 1
            runtime_body = await client.get("/v1/runtime/summary", headers=headers)
            assert runtime_body.status_code == 200
            assert runtime_body.json()["read_only"] is True
            other = await client.get(
                "/v1/analytics/overview?window=24h",
                headers={"Authorization": "Bearer m8-b"},
            )
            assert other.status_code == 200
            assert other.json()["traces"]["count"] == 0
            invalid = await client.get(
                "/v1/analytics/overview?start=not-a-time&end=not-a-time", headers=headers
            )
            assert invalid.status_code == 400

    asyncio.run(scenario())
