"""M10 controlled quality-vs-latency comparison against real services."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.domain import Span, Status, Trace
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.models import evaluation_jobs
from agentlens.evaluation.redis import RedisDispatcher
from agentlens.evaluation.repository import PostgresEvaluationJobRepository
from agentlens.evaluation.result_repository import PostgresEvaluationResultRepository
from agentlens.regression.repository import PostgresRegressionRepository
from agentlens.regression.runtime import (
    RedisRegressionDispatcher,
    RegressionRuntimeConfig,
    RegressionWorker,
)
from agentlens.replay.models import ReplayManifest, ReplayMode, ReproducibilityStatus
from agentlens.replay.repository import PostgresReplayRepository
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.models import (
    dataset_cases,
    dataset_versions,
    datasets,
    regression_case_comparisons,
    regression_metric_comparisons,
    regression_policies,
    regression_runs,
    replay_attempts,
    replay_case_executions,
    replay_runs,
    traces,
)

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL, reason="M10 integration requires PostgreSQL and Redis"
)


def _trace(project_id: str, milliseconds: int) -> Trace:
    trace_id = uuid4()
    started = datetime.now(UTC)
    return Trace(
        trace_id=trace_id,
        project_id=project_id,
        name="m10-fixture",
        started_at=started,
        ended_at=started + timedelta(milliseconds=milliseconds),
        status=Status.OK,
        spans=(
            Span(
                trace_id=trace_id,
                span_type="agent",
                name="answer",
                started_at=started,
                ended_at=started + timedelta(milliseconds=milliseconds),
                status=Status.OK,
            ),
        ),
    )


@pytest.fixture()
def m10_runtime():
    assert DATABASE_URL and REDIS_URL
    project_id = f"m10-{uuid4()}"
    config = DatabaseConfig(DATABASE_URL)
    trace_repo = PostgresTraceRepository(config)
    replay_repo = PostgresReplayRepository(config, engine=trace_repo.engine)
    regression_repo = PostgresRegressionRepository(config, engine=trace_repo.engine)
    eval_jobs = PostgresEvaluationJobRepository(config, engine=trace_repo.engine)
    eval_results = PostgresEvaluationResultRepository(config, engine=trace_repo.engine)
    regression_config = RegressionRuntimeConfig(
        redis_url=REDIS_URL,
        queue_name=f"agentlens:regression:test:{uuid4()}",
        worker_poll_timeout=0,
        lease_seconds=2,
        heartbeat_seconds=0.1,
    )
    evaluation_config = EvaluationRuntimeConfig(
        redis_url=REDIS_URL,
        queue_name=f"agentlens:evaluation:m10:{uuid4()}",
        worker_poll_timeout=0,
        lease_seconds=2,
        heartbeat_seconds=0.1,
        default_timeout_seconds=1,
    )
    regression_dispatcher = RedisRegressionDispatcher(regression_config)
    evaluation_dispatcher = RedisDispatcher(evaluation_config)
    dataset = replay_repo.create_dataset(
        project_id, f"m10-{uuid4()}", "controlled regression fixture"
    )
    dataset_id = UUID(str(dataset["dataset_id"]))
    version = replay_repo.create_draft_version(project_id, dataset_id, {"fixture": "m10"})
    version_id = UUID(str(version["dataset_version_id"]))
    replay_repo.add_case(
        project_id,
        version_id,
        name="quality",
        input_value={"case": 1},
        metadata={},
        source={},
        ground_truth=True,
        tags=(),
    )
    replay_repo.add_case(
        project_id,
        version_id,
        name="latency",
        input_value={"case": 2},
        metadata={},
        source={},
        ground_truth=True,
        tags=(),
    )
    finalized = replay_repo.finalize_version(project_id, version_id)
    checksum = str(finalized["content_checksum"])

    def make_replay(name: str, target_version: str) -> tuple[UUID, tuple[UUID, ...]]:
        manifest = ReplayManifest(
            dataset_version_id=version_id,
            dataset_checksum=checksum,
            target_profile_id="fixture",
            target_version=target_version,
            replay_mode=ReplayMode.CONTROLLED,
            reproducibility_status=ReproducibilityStatus.COMPLETE,
            changed_dimensions=(name,),
        )
        creation = replay_repo.create_replay(
            project_id=project_id,
            version_id=version_id,
            target_profile_id="fixture",
            target_name=name,
            target_type="fixture",
            target_version=target_version,
            manifest=manifest,
            max_concurrency=2,
            timeout_seconds=1,
            max_attempts=1,
            idempotency_key=None,
            request_fingerprint_value=uuid4().hex,
        )
        return UUID(str(creation.run["replay_run_id"])), creation.execution_ids

    baseline_id, baseline_execs = make_replay("baseline", "1")
    candidate_id, candidate_execs = make_replay("candidate", "2")
    traces_to_ingest = [_trace(project_id, 800), _trace(project_id, 1500), _trace(project_id, 1500)]
    trace_repo.ingest_many(traces_to_ingest)
    for index, execution_id in enumerate(baseline_execs):
        claimed = replay_repo.claim_execution(execution_id, "m10-fixture", datetime.now(UTC), 2)
        assert claimed
        if index == 1:
            replay_repo.record_failure(
                execution_id=execution_id,
                claim_token=claimed.claim_token,
                attempt_number=claimed.attempt_number,
                error_code="fixture_failure",
                safe_message="fixture",
                retryable=False,
                max_attempts=1,
                now=datetime.now(UTC),
                duration_seconds=0.01,
            )
        else:
            replay_repo.complete_success(
                execution_id=execution_id,
                claim_token=claimed.claim_token,
                attempt_number=claimed.attempt_number,
                output={"ok": True},
                request_fingerprint_value="b",
                response_fingerprint="b",
                generated_trace_id=traces_to_ingest[0].trace_id,
                now=datetime.now(UTC),
                duration_seconds=0.8,
            )
    for index, execution_id in enumerate(candidate_execs):
        claimed = replay_repo.claim_execution(execution_id, "m10-fixture", datetime.now(UTC), 2)
        assert claimed
        replay_repo.complete_success(
            execution_id=execution_id,
            claim_token=claimed.claim_token,
            attempt_number=claimed.attempt_number,
            output={"ok": True},
            request_fingerprint_value="c",
            response_fingerprint="c",
            generated_trace_id=traces_to_ingest[index + 1].trace_id,
            now=datetime.now(UTC),
            duration_seconds=1.5,
        )
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key="m10-a", key_id="m10-a", project_id=project_id)
    auth.register(api_key="m10-b", key_id="m10-b", project_id=f"other-{project_id}")
    app = create_app(
        database=config, authenticator=auth, regression_runtime_config=regression_config
    )
    yield (
        project_id,
        trace_repo,
        replay_repo,
        regression_repo,
        regression_dispatcher,
        evaluation_dispatcher,
        eval_jobs,
        eval_results,
        app,
        baseline_id,
        candidate_id,
    )
    regression_dispatcher._client.delete(regression_config.queue_name)
    evaluation_dispatcher._client.delete(evaluation_config.queue_name)
    with trace_repo.engine.begin() as connection:
        connection.execute(
            delete(regression_case_comparisons).where(
                regression_case_comparisons.c.regression_run_id.in_(
                    select(regression_runs.c.regression_run_id).where(
                        regression_runs.c.project_id == project_id
                    )
                )
            )
        )
        connection.execute(
            delete(regression_metric_comparisons).where(
                regression_metric_comparisons.c.regression_run_id.in_(
                    select(regression_runs.c.regression_run_id).where(
                        regression_runs.c.project_id == project_id
                    )
                )
            )
        )
        connection.execute(
            delete(regression_runs).where(regression_runs.c.project_id == project_id)
        )
        connection.execute(
            delete(regression_policies).where(regression_policies.c.project_id == project_id)
        )
        execution_ids = select(replay_case_executions.c.execution_id).where(
            replay_case_executions.c.project_id == project_id
        )
        connection.execute(
            delete(replay_attempts).where(replay_attempts.c.execution_id.in_(execution_ids))
        )
        connection.execute(
            delete(replay_case_executions).where(replay_case_executions.c.project_id == project_id)
        )
        connection.execute(delete(replay_runs).where(replay_runs.c.project_id == project_id))
        connection.execute(delete(dataset_cases).where(dataset_cases.c.project_id == project_id))
        connection.execute(
            delete(dataset_versions).where(dataset_versions.c.project_id == project_id)
        )
        connection.execute(delete(datasets).where(datasets.c.project_id == project_id))
        connection.execute(delete(traces).where(traces.c.project_id == project_id))
    regression_dispatcher.close()
    evaluation_dispatcher.close()
    regression_repo.dispose()
    replay_repo.dispose()
    trace_repo.dispose()


def test_controlled_quality_improvement_and_latency_regression(m10_runtime) -> None:
    (
        project_id,
        trace_repo,
        replay_repo,
        regression_repo,
        regression_dispatcher,
        evaluation_dispatcher,
        eval_jobs,
        eval_results,
        app,
        baseline_id,
        candidate_id,
    ) = m10_runtime
    del trace_repo, replay_repo
    rules = [
        {
            "rule_id": "quality",
            "metric_id": "replay.execution_success_rate",
            "direction": "higher_is_better",
            "absolute_tolerance": 0.02,
            "minimum_samples": 1,
            "required": True,
            "severity": "critical",
        },
        {
            "rule_id": "latency",
            "metric_id": "trace.duration_ms.p95",
            "direction": "lower_is_better",
            "relative_tolerance": 0.1,
            "candidate_maximum": 1000,
            "minimum_samples": 1,
            "required": True,
            "severity": "warning",
        },
    ]
    worker = RegressionWorker(
        repository=regression_repo,
        evaluation_job_repository=eval_jobs,
        evaluation_result_repository=eval_results,
        evaluation_dispatcher=evaluation_dispatcher,
        dispatcher=regression_dispatcher,
        config=RegressionRuntimeConfig(
            redis_url=REDIS_URL,
            queue_name=regression_dispatcher.config.queue_name,
            worker_poll_timeout=0,
            lease_seconds=2,
            heartbeat_seconds=0.1,
        ),
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": "Bearer m10-a"}
            policy = await client.post(
                "/v1/regression-policies",
                headers=headers,
                json={"name": "fixture", "description": "fixture", "rules": rules},
            )
            assert policy.status_code == 201
            created = await client.post(
                "/v1/regression-runs",
                headers={**headers, "Idempotency-Key": "m10-run"},
                json={
                    "baseline_replay_run_id": str(baseline_id),
                    "candidate_replay_run_id": str(candidate_id),
                    "policy_id": policy.json()["policy_id"],
                },
            )
            assert created.status_code == 202, created.text
            run_id = created.json()["regression_run_id"]
            duplicate = await client.post(
                "/v1/regression-runs",
                headers={**headers, "Idempotency-Key": "m10-run"},
                json={
                    "baseline_replay_run_id": str(baseline_id),
                    "candidate_replay_run_id": str(candidate_id),
                    "policy_id": policy.json()["policy_id"],
                },
            )
            assert duplicate.status_code == 202 and duplicate.json()["duplicate"] is True
            regression_dispatcher._client.delete(regression_dispatcher.config.queue_name)
            assert worker.recover_once() == 1
            assert worker.run_once() is True
            report = await client.get(f"/v1/regression-runs/{run_id}", headers=headers)
            metrics = await client.get(f"/v1/regression-runs/{run_id}/metrics", headers=headers)
            cases = await client.get(
                f"/v1/regression-runs/{run_id}/cases?limit=100", headers=headers
            )
            assert report.json()["status"] == "completed", report.text
            by_metric = {item["metric_id"]: item for item in metrics.json()["items"]}
            assert by_metric["replay.execution_success_rate"]["classification"] == "improved"
            assert by_metric["trace.duration_ms.p95"]["classification"] == "regressed"
            assert by_metric["trace.duration_ms.p95"]["candidate_limit_status"] == "violated"
            assert len(cases.json()["items"]) == 2
            assert cases.json()["items"][0]["candidate_trace_id"]
            regression_dispatcher.dispatch(UUID(run_id))
            regression_dispatcher.dispatch(UUID(run_id))
            assert worker.run_once() is False
            assert worker.run_once() is False
            fenced = await client.post(
                "/v1/regression-runs",
                headers=headers,
                json={
                    "baseline_replay_run_id": str(baseline_id),
                    "candidate_replay_run_id": str(candidate_id),
                    "policy_id": policy.json()["policy_id"],
                },
            )
            fenced_id = UUID(fenced.json()["regression_run_id"])
            old_claim = regression_repo.claim_run(
                project_id, fenced_id, "old-m10-worker", datetime.now(UTC), 0.05
            )
            assert old_claim is not None
            time.sleep(0.08)
            new_claim = regression_repo.claim_run(
                project_id, fenced_id, "new-m10-worker", datetime.now(UTC), 1
            )
            assert new_claim is not None
            assert (
                regression_repo.persist_comparison(project_id, fenced_id, old_claim.claim_token, {})
                is False
            )
            assert (
                regression_repo.fail_run(project_id, fenced_id, new_claim.claim_token, "fence test")
                is True
            )
            assert (
                await client.get(
                    f"/v1/regression-runs/{run_id}", headers={"Authorization": "Bearer m10-b"}
                )
            ).status_code == 404

    asyncio.run(scenario())


def test_missing_evaluation_is_orchestrated_through_existing_jobs(m10_runtime) -> None:
    (
        project_id,
        trace_repo,
        replay_repo,
        regression_repo,
        regression_dispatcher,
        evaluation_dispatcher,
        eval_jobs,
        eval_results,
        app,
        baseline_id,
        candidate_id,
    ) = m10_runtime
    del trace_repo, replay_repo
    worker = RegressionWorker(
        repository=regression_repo,
        evaluation_job_repository=eval_jobs,
        evaluation_result_repository=eval_results,
        evaluation_dispatcher=evaluation_dispatcher,
        dispatcher=regression_dispatcher,
        config=RegressionRuntimeConfig(
            redis_url=REDIS_URL,
            queue_name=regression_dispatcher.config.queue_name,
            worker_poll_timeout=0,
            lease_seconds=2,
            heartbeat_seconds=0.1,
        ),
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": "Bearer m10-a"}
            policy = await client.post(
                "/v1/regression-policies",
                headers=headers,
                json={
                    "name": "evaluation-plan",
                    "rules": [
                        {
                            "rule_id": "latency",
                            "metric_id": "trace.duration_ms.mean",
                            "direction": "lower_is_better",
                        }
                    ],
                },
            )
            created = await client.post(
                "/v1/regression-runs",
                headers=headers,
                json={
                    "baseline_replay_run_id": str(baseline_id),
                    "candidate_replay_run_id": str(candidate_id),
                    "policy_id": policy.json()["policy_id"],
                    "evaluation_plan": [{"evaluation_type": "latency_summary", "config": {}}],
                },
            )
            assert created.status_code == 202, created.text
            assert worker.run_once() is True
            report = await client.get(
                f"/v1/regression-runs/{created.json()['regression_run_id']}", headers=headers
            )
            assert report.json()["status"] == "waiting_for_evaluations"
            with regression_repo.engine.connect() as connection:
                count = connection.execute(
                    select(evaluation_jobs.c.job_id).where(
                        evaluation_jobs.c.project_id == project_id
                    )
                ).all()
            assert len(count) == 3

    asyncio.run(scenario())
