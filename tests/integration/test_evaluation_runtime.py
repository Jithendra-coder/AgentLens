"""M5 real PostgreSQL and Redis integration contracts."""

from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.domain import Span, Trace
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.handlers import HandlerRegistry
from agentlens.evaluation.redis import (
    RecoveryDispatcher,
    RedisDispatcher,
    UnavailableDispatcher,
)
from agentlens.evaluation.repository import (
    PostgresEvaluationJobRepository,
    hash_idempotency_key,
    request_fingerprint,
)
from agentlens.evaluation.types import JobState
from agentlens.evaluation.worker import EvaluationWorker
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.models import traces

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL,
    reason="M5 integration tests require real PostgreSQL and Redis",
)


def make_trace(project_id: str) -> Trace:
    trace_id = uuid4()
    started = datetime(2025, 1, 1, 12, tzinfo=UTC)
    return Trace(
        trace_id=trace_id,
        project_id=project_id,
        name="m5-runtime",
        started_at=started,
        spans=(Span(trace_id=trace_id, name="work", started_at=started),),
    )


@pytest.fixture()
def runtime_repositories():
    assert DATABASE_URL is not None and REDIS_URL is not None
    config = DatabaseConfig(DATABASE_URL)
    trace_repository = PostgresTraceRepository(config)
    job_repository = PostgresEvaluationJobRepository(config, engine=trace_repository.engine)
    runtime = EvaluationRuntimeConfig(
        redis_url=REDIS_URL,
        lease_seconds=1.0,
        heartbeat_seconds=0.2,
        default_timeout_seconds=0.2,
        retry_base_seconds=0.02,
        retry_max_seconds=0.02,
        worker_poll_timeout=0,
    )
    dispatcher = RedisDispatcher(runtime)
    dispatcher._client.delete(runtime.queue_name)
    project_id = f"m5-{uuid4()}"
    trace = make_trace(project_id)
    trace_repository.ingest(trace)
    yield config, trace_repository, job_repository, dispatcher, runtime, trace
    with trace_repository.engine.begin() as connection:
        connection.execute(delete(traces).where(traces.c.project_id == project_id))
    dispatcher._client.delete(runtime.queue_name)
    dispatcher.close()
    trace_repository.dispose()


def _authenticator(project_id: str) -> InMemoryApiKeyAuthenticator:
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key="m5-key-a", key_id="m5-key-a", project_id=project_id)
    auth.register(api_key="m5-key-b", key_id="m5-key-b", project_id="other-project")
    return auth


def test_job_api_dispatch_completion_and_project_isolation(runtime_repositories) -> None:
    config, trace_repository, job_repository, dispatcher, runtime, trace = runtime_repositories
    auth = _authenticator(trace.project_id)
    app = create_app(
        database=config,
        authenticator=auth,
        dispatcher=dispatcher,
        runtime_config=runtime,
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            path = f"/v1/traces/{trace.trace_id}/evaluations"
            first = await client.post(
                path,
                headers={"Authorization": "Bearer m5-key-a", "Idempotency-Key": "same-key"},
                json={"evaluation_type": "noop", "config": {}},
            )
            assert first.status_code == 202
            first_body = first.json()
            assert first_body["state"] == "queued"
            second = await client.post(
                path,
                headers={"Authorization": "Bearer m5-key-a", "Idempotency-Key": "same-key"},
                json={"evaluation_type": "noop", "config": {}},
            )
            assert second.status_code == 202
            assert second.json()["job_id"] == first_body["job_id"]
            conflict = await client.post(
                path,
                headers={"Authorization": "Bearer m5-key-a", "Idempotency-Key": "same-key"},
                json={"evaluation_type": "noop", "config": {"changed": True}},
            )
            assert conflict.status_code == 409
            worker = EvaluationWorker(
                repository=job_repository,
                trace_repository=trace_repository,
                dispatcher=dispatcher,
                config=runtime,
            )
            assert worker.run_once() is True
            completed = await client.get(
                f"/v1/evaluation-jobs/{first_body['job_id']}",
                headers={"Authorization": "Bearer m5-key-a"},
            )
            assert completed.status_code == 200
            assert completed.json()["state"] == "succeeded"
            isolated = await client.get(
                f"/v1/evaluation-jobs/{first_body['job_id']}",
                headers={"Authorization": "Bearer m5-key-b"},
            )
            assert isolated.status_code == 404

    asyncio.run(scenario())


def test_trace_ingestion_and_durable_queue_survive_redis_outage(runtime_repositories) -> None:
    config, trace_repository, job_repository, _, runtime, trace = runtime_repositories
    auth = _authenticator(trace.project_id)
    app = create_app(
        database=config,
        authenticator=auth,
        dispatcher=UnavailableDispatcher(),
        runtime_config=runtime,
    )
    queued_job_id: str | None = None

    async def scenario() -> None:
        nonlocal queued_job_id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            ingested = await client.post(
                "/v1/traces",
                headers={"Authorization": "Bearer m5-key-a"},
                json=trace.to_dict(),
            )
            assert ingested.status_code == 202
            queued = await client.post(
                f"/v1/traces/{trace.trace_id}/evaluations",
                headers={"Authorization": "Bearer m5-key-a"},
                json={"evaluation_type": "noop", "config": {}},
            )
            assert queued.status_code == 202
            assert queued.json()["state"] == "queued"
            queued_job_id = cast(str, queued.json()["job_id"])
            ready = await client.get("/health/ready")
            assert ready.status_code == 200
            assert ready.json()["status"] == "degraded"

    asyncio.run(scenario())
    assert queued_job_id is not None
    job = job_repository.get_job(trace.project_id, UUID(queued_job_id))
    assert job is not None and job.state is JobState.QUEUED


def test_retry_dead_letter_concurrent_claim_and_lease_recovery(runtime_repositories) -> None:
    _, trace_repository, job_repository, dispatcher, runtime, trace = runtime_repositories

    class FailingHandler:
        def evaluate(self, trace_value: Trace, config: dict[str, object]) -> None:
            del trace_value, config
            raise RuntimeError("handler detail must not be persisted")

    failing_registry = HandlerRegistry({"failing": FailingHandler()})
    failing = job_repository.create_job(
        project_id=trace.project_id,
        trace_id=trace.trace_id,
        evaluation_type="failing",
        config={},
        priority=0,
        timeout_seconds=0.2,
        max_attempts=3,
    ).job
    dispatcher.dispatch(failing.job_id)
    worker = EvaluationWorker(
        repository=job_repository,
        trace_repository=trace_repository,
        dispatcher=dispatcher,
        registry=failing_registry,
        config=runtime,
    )
    for index in range(3):
        assert worker.run_once() is True
        if index < 2:
            time.sleep(0.03)
            RecoveryDispatcher(job_repository, dispatcher).dispatch_ready(
                now=datetime.now(UTC), limit=10
            )
    dead = job_repository.get_job(trace.project_id, failing.job_id)
    assert dead is not None and dead.state is JobState.DEAD_LETTER
    attempts = job_repository.get_attempts(failing.job_id)
    assert len(attempts) == 3
    assert all(attempt.safe_error_message == "Evaluation handler failed." for attempt in attempts)

    concurrent_job = job_repository.create_job(
        project_id=trace.project_id,
        trace_id=trace.trace_id,
        evaluation_type="noop",
        config={},
        priority=0,
        timeout_seconds=0.2,
        max_attempts=2,
    ).job
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda worker_name: job_repository.claim_next(
                    worker_id=worker_name,
                    now=datetime.now(UTC),
                    lease_seconds=1.0,
                ),
                ("concurrent-a", "concurrent-b"),
            )
        )
    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0].job.job_id == concurrent_job.job_id
    job_repository.complete_success(
        job_id=claimed[0].job.job_id,
        claim_token=claimed[0].claim_token,
        attempt_number=claimed[0].attempt_number,
        now=datetime.now(UTC),
        duration_seconds=0.01,
    )

    lease_job = job_repository.create_job(
        project_id=trace.project_id,
        trace_id=trace.trace_id,
        evaluation_type="noop",
        config={},
        priority=0,
        timeout_seconds=0.2,
        max_attempts=2,
    ).job
    first_claim = job_repository.claim_job(
        job_id=lease_job.job_id,
        worker_id="crashed-worker",
        now=datetime.now(UTC),
        lease_seconds=0.05,
    )
    assert first_claim is not None
    time.sleep(0.08)
    recovered = job_repository.claim_next(
        worker_id="recovery-worker",
        now=datetime.now(UTC),
        lease_seconds=1.0,
    )
    assert recovered is not None and recovered.job.job_id == lease_job.job_id
    assert recovered.attempt_number == 2
    assert any(
        attempt.outcome.value == "lease_expired"
        for attempt in job_repository.get_attempts(lease_job.job_id)
    )
    job_repository.complete_success(
        job_id=recovered.job.job_id,
        claim_token=recovered.claim_token,
        attempt_number=recovered.attempt_number,
        now=datetime.now(UTC),
        duration_seconds=0.01,
    )

    final_attempt_job = job_repository.create_job(
        project_id=trace.project_id,
        trace_id=trace.trace_id,
        evaluation_type="noop",
        config={},
        priority=0,
        timeout_seconds=0.2,
        max_attempts=1,
    ).job
    final_claim = job_repository.claim_job(
        job_id=final_attempt_job.job_id,
        worker_id="final-crashed-worker",
        now=datetime.now(UTC),
        lease_seconds=0.05,
    )
    assert final_claim is not None
    time.sleep(0.08)
    assert (
        job_repository.claim_next(
            worker_id="final-recovery-worker",
            now=datetime.now(UTC),
            lease_seconds=1.0,
        )
        is None
    )
    terminal = job_repository.get_job(trace.project_id, final_attempt_job.job_id)
    assert terminal is not None and terminal.state is JobState.DEAD_LETTER


def test_concurrent_idempotency_creation_returns_one_job(runtime_repositories) -> None:
    _, _, job_repository, _, _, trace = runtime_repositories
    key_hash = hash_idempotency_key("concurrent-key")
    fingerprint = request_fingerprint("noop", {}, 0, 0.2, 3)

    def create() -> UUID:
        return job_repository.create_job(
            project_id=trace.project_id,
            trace_id=trace.trace_id,
            evaluation_type="noop",
            config={},
            priority=0,
            timeout_seconds=0.2,
            max_attempts=3,
            idempotency_key_hash=key_hash,
            request_fingerprint_value=fingerprint,
        ).job.job_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        job_ids = list(pool.map(lambda _: create(), (1, 2)))
    assert job_ids[0] == job_ids[1]
