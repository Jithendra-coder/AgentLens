"""M7 real PostgreSQL/Redis semantic-evaluation integration contracts."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.domain import Span, Status, Trace
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.handlers import HandlerRegistry
from agentlens.evaluation.judges import JudgeCriterionResult, JudgeResponse
from agentlens.evaluation.models import evaluation_judge_invocations
from agentlens.evaluation.redis import RedisDispatcher
from agentlens.evaluation.repository import PostgresEvaluationJobRepository
from agentlens.evaluation.result_repository import PostgresEvaluationResultRepository
from agentlens.evaluation.worker import EvaluationWorker
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.models import traces
from tests.support.fake_judge import FakeJudge

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL,
    reason="M7 integration tests require real PostgreSQL and Redis",
)


def make_trace(project_id: str) -> Trace:
    trace_id = uuid4()
    started = datetime(2025, 1, 1, 12, tzinfo=UTC)
    retrieval_id = uuid4()
    answer_id = uuid4()
    return Trace(
        trace_id=trace_id,
        project_id=project_id,
        name="m7-integration",
        started_at=started,
        ended_at=started + timedelta(seconds=3),
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
                output={
                    "documents": [
                        {"id": "d1", "content": "The policy starts in January."},
                        {"id": "d2", "content": "An unrelated document."},
                    ]
                },
            ),
            Span(
                trace_id=trace_id,
                span_id=answer_id,
                span_type="llm",
                name="answer",
                started_at=started + timedelta(seconds=1),
                ended_at=started + timedelta(seconds=2),
                status=Status.OK,
                output={"answer": "The policy starts in January.", "citations": ["d1"]},
            ),
            Span(
                trace_id=trace_id,
                span_type="tool",
                name="lookup",
                started_at=started + timedelta(seconds=2),
                ended_at=started + timedelta(seconds=3),
                status=Status.OK,
                input={"q": "policy"},
            ),
        ),
    )


@pytest.fixture()
def m7_runtime():
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
        lease_seconds=2.0,
        heartbeat_seconds=0.2,
        default_timeout_seconds=1.0,
        retry_base_seconds=0.02,
        retry_max_seconds=0.02,
        worker_poll_timeout=0,
    )
    dispatcher = RedisDispatcher(runtime)
    dispatcher._client.delete(runtime.queue_name)
    project_id = f"m7-{uuid4()}"
    trace = make_trace(project_id)
    trace_repository.ingest(trace)
    yield config, trace_repository, job_repository, result_repository, dispatcher, runtime, trace
    with trace_repository.engine.begin() as connection:
        connection.execute(delete(traces).where(traces.c.project_id == project_id))
    dispatcher._client.delete(runtime.queue_name)
    dispatcher.close()
    trace_repository.dispose()


def test_semantic_result_provenance_modes_and_atomic_completion(m7_runtime) -> None:
    config, trace_repository, job_repository, result_repository, dispatcher, runtime, trace = (
        m7_runtime
    )
    judge = FakeJudge(
        response=JudgeResponse(
            label="mixed",
            criterion_results=(
                JudgeCriterionResult("d1", "relevant", 1.0),
                JudgeCriterionResult("d2", "irrelevant", 0.0),
            ),
        )
    )
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key="m7-a", key_id="m7-a", project_id=trace.project_id)
    auth.register(api_key="m7-b", key_id="m7-b", project_id="other-project")
    app = create_app(
        database=config,
        authenticator=auth,
        dispatcher=dispatcher,
        runtime_config=runtime,
        semantic_judge=judge,
    )
    worker = EvaluationWorker(
        repository=job_repository,
        trace_repository=trace_repository,
        dispatcher=dispatcher,
        result_repository=result_repository,
        config=runtime,
        registry=HandlerRegistry(semantic_judge=judge),
    )
    retrieval_id = str(trace.spans[0].span_id)
    answer_id = str(trace.spans[1].span_id)
    requests = (
        (
            "rag_context_relevance",
            {
                "retrieval_span_id": retrieval_id,
                "answer_span_id": answer_id,
                "question": "When does the policy start?",
            },
        ),
        (
            "rag_citation_integrity",
            {"retrieval_span_id": retrieval_id, "answer_span_id": answer_id},
        ),
        ("tool_selection", {"expected_tools": ["lookup"]}),
    )
    job_ids: list[str] = []

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            rejected_endpoint = await client.post(
                f"/v1/traces/{trace.trace_id}/evaluations",
                headers={"Authorization": "Bearer m7-a"},
                json={
                    "evaluation_type": "rag_context_relevance",
                    "config": {"api_url": "http://attacker.invalid/"},
                },
            )
            assert rejected_endpoint.status_code == 422
            for evaluation_type, eval_config in requests:
                response = await client.post(
                    f"/v1/traces/{trace.trace_id}/evaluations",
                    headers={"Authorization": "Bearer m7-a"},
                    json={"evaluation_type": evaluation_type, "config": eval_config},
                )
                assert response.status_code == 202
                job_ids.append(response.json()["job_id"])
            for _ in job_ids:
                assert worker.run_once() is True

            summaries = await client.get(
                f"/v1/traces/{trace.trace_id}/evaluation-results",
                headers={"Authorization": "Bearer m7-a"},
            )
            assert summaries.status_code == 200
            assert len(summaries.json()["items"]) == 3
            semantic_summary = next(
                item
                for item in summaries.json()["items"]
                if item["evaluation_type"] == "rag_context_relevance"
            )
            assert semantic_summary["evaluation_mode"] == "model_assisted"
            detail = await client.get(
                f"/v1/evaluation-results/{semantic_summary['result_id']}",
                headers={"Authorization": "Bearer m7-a"},
            )
            assert detail.status_code == 200
            body = detail.json()
            assert body["evaluation_mode"] == "model_assisted"
            assert body["judge_invocations"][0]["provider"] == "test"
            assert body["judge_invocations"][0]["model"] == "fake-semantic-judge"
            assert "context" not in body["judge_invocations"][0]
            assert body["metrics"]["irrelevant_document_count"] == 1

            hidden = await client.get(
                f"/v1/evaluation-results/{semantic_summary['result_id']}",
                headers={"Authorization": "Bearer m7-b"},
            )
            assert hidden.status_code == 404

    asyncio.run(scenario())
    with trace_repository.engine.begin() as connection:
        rows = (
            connection.execute(
                select(evaluation_judge_invocations).where(
                    evaluation_judge_invocations.c.project_id == trace.project_id
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1
    persisted = result_repository.get_result_for_job(trace.project_id, UUID(job_ids[0]))
    assert persisted is not None
    assert len(persisted.judge_invocations) == 1
