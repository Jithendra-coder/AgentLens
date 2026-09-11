"""M6 real PostgreSQL/Redis evaluation-result integration contracts."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.domain import Span, Status, Trace, Usage
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.errors import StaleClaimError
from agentlens.evaluation.evaluators import LatencyEvaluator
from agentlens.evaluation.redis import RedisDispatcher
from agentlens.evaluation.repository import PostgresEvaluationJobRepository
from agentlens.evaluation.result_repository import PostgresEvaluationResultRepository
from agentlens.evaluation.results import ResultStatus
from agentlens.evaluation.worker import EvaluationWorker
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.contracts import canonical_fingerprint
from agentlens.storage.models import traces

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL,
    reason="M6 integration tests require real PostgreSQL and Redis",
)


def make_trace(project_id: str) -> Trace:
    trace_id = uuid4()
    started = datetime(2025, 1, 1, 12, tzinfo=UTC)
    retrieval_id = uuid4()
    return Trace(
        trace_id=trace_id,
        project_id=project_id,
        name="m6-evaluation",
        started_at=started,
        ended_at=started + timedelta(seconds=2),
        status=Status.OK,
        spans=(
            Span(
                trace_id=trace_id,
                span_id=retrieval_id,
                span_type="retrieval",
                name="retrieve",
                started_at=started,
                ended_at=started + timedelta(seconds=1),
                status=Status.OK,
                output={"documents": [{"id": "d3"}, {"id": "d1"}, {"id": "d2"}]},
                usage=Usage(input_tokens=4, output_tokens=5, total_tokens=9),
            ),
            Span(
                trace_id=trace_id,
                span_type="tool",
                name="tool",
                started_at=started + timedelta(milliseconds=500),
                ended_at=started + timedelta(seconds=2),
                status=Status.ERROR,
                usage=Usage(output_tokens=0, cached_tokens=2),
            ),
        ),
    )


@pytest.fixture()
def m6_runtime():
    assert DATABASE_URL is not None and REDIS_URL is not None
    config = DatabaseConfig(DATABASE_URL)
    trace_repository = PostgresTraceRepository(config)
    job_repository = PostgresEvaluationJobRepository(config, engine=trace_repository.engine)
    result_repository = PostgresEvaluationResultRepository(
        config,
        engine=trace_repository.engine,
    )
    runtime = EvaluationRuntimeConfig(
        redis_url=REDIS_URL,
        lease_seconds=1.0,
        heartbeat_seconds=0.2,
        default_timeout_seconds=0.5,
        retry_base_seconds=0.02,
        retry_max_seconds=0.02,
        worker_poll_timeout=0,
    )
    dispatcher = RedisDispatcher(runtime)
    dispatcher._client.delete(runtime.queue_name)
    project_id = f"m6-{uuid4()}"
    trace = make_trace(project_id)
    trace_repository.ingest(trace)
    yield config, trace_repository, job_repository, result_repository, dispatcher, runtime, trace
    with trace_repository.engine.begin() as connection:
        connection.execute(delete(traces).where(traces.c.project_id == project_id))
    dispatcher._client.delete(runtime.queue_name)
    dispatcher.close()
    trace_repository.dispose()


def _auth(project_id: str) -> InMemoryApiKeyAuthenticator:
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(api_key="m6-a", key_id="m6-a", project_id=project_id)
    authenticator.register(api_key="m6-b", key_id="m6-b", project_id="other-project")
    return authenticator


def test_end_to_end_results_api_and_project_isolation(m6_runtime) -> None:
    config, trace_repository, job_repository, result_repository, dispatcher, runtime, trace = (
        m6_runtime
    )
    auth = _auth(trace.project_id)
    app = create_app(
        database=config,
        authenticator=auth,
        dispatcher=dispatcher,
        runtime_config=runtime,
    )
    retrieval_config = {
        "span_id": str(trace.spans[0].span_id),
        "relevant_document_ids": ["d1", "d2"],
        "k_values": [1, 3],
    }
    requests = (
        ("latency_summary", {}),
        ("usage_summary", {}),
        ("reliability_summary", {}),
        ("retrieval_ranking", retrieval_config),
    )
    job_ids: list[str] = []

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            for evaluation_type, eval_config in requests:
                response = await client.post(
                    f"/v1/traces/{trace.trace_id}/evaluations",
                    headers={"Authorization": "Bearer m6-a"},
                    json={"evaluation_type": evaluation_type, "config": eval_config},
                )
                assert response.status_code == 202
                job_ids.append(response.json()["job_id"])
            unsupported = await client.post(
                f"/v1/traces/{trace.trace_id}/evaluations",
                headers={"Authorization": "Bearer m6-a"},
                json={"evaluation_type": "not_supported", "config": {}},
            )
            assert unsupported.status_code == 422

            worker = EvaluationWorker(
                repository=job_repository,
                trace_repository=trace_repository,
                dispatcher=dispatcher,
                result_repository=result_repository,
                config=runtime,
            )
            for _ in job_ids:
                assert worker.run_once() is True

            summaries = await client.get(
                f"/v1/traces/{trace.trace_id}/evaluation-results",
                headers={"Authorization": "Bearer m6-a"},
            )
            assert summaries.status_code == 200
            assert len(summaries.json()["items"]) == 4
            retrieval = next(
                item
                for item in summaries.json()["items"]
                if item["evaluation_type"] == "retrieval_ranking"
            )
            detail = await client.get(
                f"/v1/evaluation-results/{retrieval['result_id']}",
                headers={"Authorization": "Bearer m6-a"},
            )
            assert detail.status_code == 200
            body = detail.json()
            assert body["result_schema_version"] == "agentlens-evaluation-result-v1"
            assert body["trace_fingerprint"] == canonical_fingerprint(trace)
            assert body["metrics"]["recall_at_3"] == 1.0
            assert body["config"]["k_values"] == [1, 3]

            job = await client.get(
                f"/v1/evaluation-jobs/{job_ids[0]}",
                headers={"Authorization": "Bearer m6-a"},
            )
            assert job.status_code == 200
            assert job.json()["state"] == "succeeded"
            assert job.json()["result_id"]

            hidden_detail = await client.get(
                f"/v1/evaluation-results/{retrieval['result_id']}",
                headers={"Authorization": "Bearer m6-b"},
            )
            hidden_list = await client.get(
                f"/v1/traces/{trace.trace_id}/evaluation-results",
                headers={"Authorization": "Bearer m6-b"},
            )
            assert hidden_detail.status_code == 404
            assert hidden_list.status_code == 404

    asyncio.run(scenario())
    duplicate_job_id = UUID(job_ids[0])
    dispatcher.dispatch(duplicate_job_id)
    dispatcher.dispatch(duplicate_job_id)
    worker = EvaluationWorker(
        repository=job_repository,
        trace_repository=trace_repository,
        dispatcher=dispatcher,
        result_repository=result_repository,
        config=runtime,
    )
    assert worker.run_once() is False
    assert worker.run_once() is False
    assert len(result_repository.list_results(trace.project_id, trace.trace_id, 20)) == 4


def test_atomic_result_completion_rejects_stale_worker(m6_runtime) -> None:
    _, trace_repository, job_repository, result_repository, _, runtime, trace = m6_runtime
    job = job_repository.create_job(
        project_id=trace.project_id,
        trace_id=trace.trace_id,
        evaluation_type="latency_summary",
        config={},
        priority=0,
        timeout_seconds=0.5,
        max_attempts=2,
    ).job
    old_claim = job_repository.claim_job(
        job_id=job.job_id,
        worker_id="old-worker",
        now=datetime.now(UTC),
        lease_seconds=0.05,
    )
    assert old_claim is not None
    time.sleep(0.08)
    new_claim = job_repository.claim_job(
        job_id=job.job_id,
        worker_id="new-worker",
        now=datetime.now(UTC),
        lease_seconds=1.0,
    )
    assert new_claim is not None
    payload = LatencyEvaluator().evaluate(trace, {})
    with pytest.raises(StaleClaimError):
        result_repository.complete_success_with_result(
            job_id=job.job_id,
            claim_token=old_claim.claim_token,
            attempt_number=old_claim.attempt_number,
            evaluator_name="agentlens.latency",
            evaluator_version="1.0.0",
            normalized_config={},
            trace_fingerprint=canonical_fingerprint(trace),
            payload=payload,
            now=datetime.now(UTC),
            duration_seconds=0.01,
        )
    result = result_repository.complete_success_with_result(
        job_id=job.job_id,
        claim_token=new_claim.claim_token,
        attempt_number=new_claim.attempt_number,
        evaluator_name="agentlens.latency",
        evaluator_version="1.0.0",
        normalized_config={},
        trace_fingerprint=canonical_fingerprint(trace),
        payload=payload,
        now=datetime.now(UTC),
        duration_seconds=0.01,
    )
    assert result.result_status is ResultStatus.COMPLETED
    assert result_repository.get_result_for_job(trace.project_id, job.job_id) is not None
