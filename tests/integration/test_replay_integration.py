"""M9 dataset/replay contracts against real PostgreSQL, Redis, and FastAPI."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.domain import Span, Status, Trace
from agentlens.replay.models import ReplayManifest, ReplayMode, ReproducibilityStatus
from agentlens.replay.repository import PostgresReplayRepository
from agentlens.replay.runtime import RedisReplayDispatcher, ReplayRuntimeConfig, ReplayWorker
from agentlens.replay.targets import (
    LOCAL_TARGET_PROFILE_ID,
    ReplayTargetProfile,
    TrustedReplayTargetRegistry,
)
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.models import (
    dataset_cases,
    dataset_versions,
    datasets,
    replay_attempts,
    replay_case_executions,
    replay_runs,
    traces,
)
from tests.support.fake_replay import FakeReplayTarget

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL,
    reason="M9 integration tests require real PostgreSQL and Redis",
)


def _trace(project_id: str) -> Trace:
    trace_id = uuid4()
    now = datetime.now(UTC)
    return Trace(
        trace_id=trace_id,
        project_id=project_id,
        name="m9-source",
        started_at=now,
        ended_at=now,
        status=Status.OK,
        spans=(
            Span(
                trace_id=trace_id,
                span_type="agent",
                name="source",
                started_at=now,
                ended_at=now,
                status=Status.OK,
                input={"from": "trace"},
            ),
        ),
    )


@pytest.fixture()
def m9_runtime():
    assert DATABASE_URL is not None and REDIS_URL is not None
    project_id = f"m9-{uuid4()}"
    config = DatabaseConfig(DATABASE_URL)
    trace_repository = PostgresTraceRepository(config)
    replay_repository = PostgresReplayRepository(config, engine=trace_repository.engine)
    runtime = ReplayRuntimeConfig(
        redis_url=REDIS_URL,
        queue_name=f"agentlens:replay:test:{uuid4()}",
        worker_poll_timeout=0,
        lease_seconds=2.0,
        heartbeat_seconds=0.1,
        default_timeout_seconds=1.0,
        max_concurrency=4,
    )
    dispatcher = RedisReplayDispatcher(runtime)
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key="m9-a", key_id="m9-a", project_id=project_id)
    auth.register(api_key="m9-b", key_id="m9-b", project_id=f"other-{project_id}")
    registry = TrustedReplayTargetRegistry()
    registry.register(
        ReplayTargetProfile(
            profile_id=LOCAL_TARGET_PROFILE_ID,
            name="Fake local target",
            target_type="fake",
            version="1",
            safety_class="sandbox",
        ),
        FakeReplayTarget(),
    )
    app = create_app(
        database=config,
        authenticator=auth,
        replay_runtime_config=runtime,
        replay_target_registry=registry,
    )
    source = _trace(project_id)
    trace_repository.ingest(source)
    yield project_id, config, trace_repository, replay_repository, dispatcher, runtime, app, source
    dispatcher._client.delete(runtime.queue_name)
    with trace_repository.engine.begin() as connection:
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
    dispatcher.close()
    replay_repository.dispose()
    trace_repository.dispose()


def test_dataset_replay_api_and_runtime(m9_runtime) -> None:
    (
        project_id,
        config,
        trace_repository,
        replay_repository,
        dispatcher,
        runtime,
        app,
        source,
    ) = m9_runtime
    del config, trace_repository, replay_repository
    headers = {"Authorization": "Bearer m9-a", "Content-Type": "application/json"}

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            dataset = await client.post(
                "/v1/datasets", headers=headers, json={"name": "m9", "description": "test"}
            )
            assert dataset.status_code == 201
            dataset_id = dataset.json()["dataset_id"]
            version = await client.post(
                f"/v1/datasets/{dataset_id}/versions",
                headers=headers,
                json={"source_metadata": {"source": "test"}},
            )
            assert version.status_code == 201
            version_id = version.json()["dataset_version_id"]
            manual = await client.post(
                f"/v1/dataset-versions/{version_id}/cases",
                headers=headers,
                json={
                    "name": "manual",
                    "input": {"value": 1},
                    "ground_truth": {"value": 1},
                    "tags": ["smoke"],
                },
            )
            assert manual.status_code == 201
            derived = await client.post(
                f"/v1/dataset-versions/{version_id}/cases/from-trace",
                headers=headers,
                json={
                    "trace_id": str(source.trace_id),
                    "span_id": str(source.spans[0].span_id),
                    "input_field": "input",
                    "name": "trace-derived",
                },
            )
            assert derived.status_code == 201
            finalized = await client.post(
                f"/v1/dataset-versions/{version_id}/finalize", headers=headers, json={}
            )
            assert finalized.status_code == 200
            checksum = finalized.json()["content_checksum"]
            assert finalized.json()["cases"][1]["source"]["trace_fingerprint"]
            assert (
                await client.post(
                    f"/v1/dataset-versions/{version_id}/cases",
                    headers=headers,
                    json={"name": "blocked", "input": 1},
                )
            ).status_code == 409
            export = await client.get(f"/v1/dataset-versions/{version_id}/export", headers=headers)
            assert export.status_code == 200 and export.json()["schema"] == "agentlens-dataset-v1"
            export_body = export.json()
            imported_dataset = await client.post(
                "/v1/datasets",
                headers=headers,
                json={"name": "m9-import", "description": "portable"},
            )
            imported_id = imported_dataset.json()["dataset_id"]
            unsupported = {**export_body, "schema": "agentlens-dataset-v0"}
            assert (
                await client.post(
                    f"/v1/datasets/{imported_id}/versions/import",
                    headers=headers,
                    json=unsupported,
                )
            ).status_code == 422
            corrupt = {
                **export_body,
                "version": {**export_body["version"], "content_checksum": "0" * 64},
            }
            assert (
                await client.post(
                    f"/v1/datasets/{imported_id}/versions/import",
                    headers=headers,
                    json=corrupt,
                )
            ).status_code == 422
            duplicate = {
                **export_body,
                "cases": [export_body["cases"][0], export_body["cases"][0]],
            }
            assert (
                await client.post(
                    f"/v1/datasets/{imported_id}/versions/import",
                    headers=headers,
                    json=duplicate,
                )
            ).status_code == 422
            imported = await client.post(
                f"/v1/datasets/{imported_id}/versions/import",
                headers=headers,
                json=export_body,
            )
            assert imported.status_code == 201
            imported_final = await client.post(
                f"/v1/dataset-versions/{imported.json()['dataset_version_id']}/finalize",
                headers=headers,
                json={},
            )
            assert imported_final.status_code == 200
            assert imported_final.json()["content_checksum"] == checksum
            profiles = await client.get("/v1/replay-target-profiles", headers=headers)
            profile_id = profiles.json()["items"][0]["profile_id"]
            replay_body = {
                "dataset_version_id": version_id,
                "target_profile_id": profile_id,
                "replay_mode": "best_effort",
                "manifest": {
                    "reproducibility_status": "partial",
                    "unknown_fields": ["model"],
                    "best_effort_reason": "test",
                },
                "max_concurrency": 2,
            }
            exact = await client.post(
                "/v1/replay-runs",
                headers=headers,
                json={
                    **replay_body,
                    "replay_mode": "exact",
                    "manifest": {
                        "reproducibility_status": "partial",
                        "unknown_fields": ["model"],
                    },
                },
            )
            assert exact.status_code == 422
            created = await client.post(
                "/v1/replay-runs",
                headers={**headers, "Idempotency-Key": "m9-same"},
                json=replay_body,
            )
            assert created.status_code == 202
            run_id = created.json()["replay_run_id"]
            duplicate = await client.post(
                "/v1/replay-runs",
                headers={**headers, "Idempotency-Key": "m9-same"},
                json=replay_body,
            )
            assert duplicate.status_code == 202 and duplicate.json()["replay_run_id"] == run_id
            changed = {**replay_body, "max_concurrency": 3}
            assert (
                await client.post(
                    "/v1/replay-runs",
                    headers={**headers, "Idempotency-Key": "m9-same"},
                    json=changed,
                )
            ).status_code == 409
            other = await client.get(
                f"/v1/datasets/{dataset_id}", headers={"Authorization": "Bearer m9-b"}
            )
            assert other.status_code == 404
            worker = ReplayWorker(
                repository=PostgresReplayRepository(DatabaseConfig(DATABASE_URL)),
                trace_repository=PostgresTraceRepository(DatabaseConfig(DATABASE_URL)),
                dispatcher=dispatcher,
                registry=app.state.gateway.replay_target_registry,
                config=runtime,
            )
            dispatcher._client.delete(runtime.queue_name)
            assert worker.recover_once() == 2
            assert worker.run_batch() == 2
            assert worker.run_once() is False
            run = await client.get(f"/v1/replay-runs/{run_id}", headers=headers)
            assert run.status_code == 200
            body = run.json()
            assert body["status"] == "succeeded"
            assert body["completed_count"] == 2
            assert body["executions"][0]["generated_trace_id"]
            trace_detail = await client.get(
                f"/v1/traces/{body['executions'][0]['generated_trace_id']}", headers=headers
            )
            assert trace_detail.status_code == 200
            assert body["dataset_checksum"] == checksum
            for execution in body["executions"]:
                execution_id = UUID(str(execution["execution_id"]))
                dispatcher.dispatch(execution_id)
                dispatcher.dispatch(execution_id)
            assert worker.run_once() is False
            assert worker.run_once() is False

    asyncio.run(scenario())


def _create_direct_run(
    repository: PostgresReplayRepository,
    dispatcher: RedisReplayDispatcher,
    project_id: str,
    input_value: object,
    *,
    timeout_seconds: float = 1.0,
    max_attempts: int = 1,
) -> tuple[UUID, UUID]:
    dataset = repository.create_dataset(project_id, f"direct-{uuid4()}", "runtime test")
    dataset_id = UUID(str(dataset["dataset_id"]))
    version = repository.create_draft_version(project_id, dataset_id, {"source": "test"})
    version_id = UUID(str(version["dataset_version_id"]))
    repository.add_case(
        project_id,
        version_id,
        name="runtime case",
        input_value=input_value,
        metadata={},
        source={},
        ground_truth=None,
        tags=(),
    )
    finalized = repository.finalize_version(project_id, version_id)
    manifest = ReplayManifest(
        dataset_version_id=version_id,
        dataset_checksum=str(finalized["content_checksum"]),
        target_profile_id=LOCAL_TARGET_PROFILE_ID,
        target_version="1",
        replay_mode=ReplayMode.BEST_EFFORT,
        reproducibility_status=ReproducibilityStatus.PARTIAL,
        unknown_fields=("model",),
        best_effort_reason="runtime test",
    )
    creation = repository.create_replay(
        project_id=project_id,
        version_id=version_id,
        target_profile_id=LOCAL_TARGET_PROFILE_ID,
        target_name="Fake local target",
        target_type="fake",
        target_version="1",
        manifest=manifest,
        max_concurrency=1,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        idempotency_key=None,
        request_fingerprint_value=uuid4().hex,
    )
    execution_id = creation.execution_ids[0]
    dispatcher.dispatch(execution_id)
    return UUID(str(creation.run["replay_run_id"])), execution_id


def test_replay_retry_timeout_and_stale_fencing(m9_runtime) -> None:
    project_id, config, trace_repository, repository, dispatcher, runtime, app, _ = m9_runtime
    del config, app
    registry = TrustedReplayTargetRegistry()
    registry.register(
        ReplayTargetProfile(
            profile_id=LOCAL_TARGET_PROFILE_ID,
            name="Fake local target",
            target_type="fake",
            version="1",
            safety_class="sandbox",
        ),
        FakeReplayTarget(),
    )
    worker = ReplayWorker(
        repository=repository,
        trace_repository=trace_repository,
        dispatcher=dispatcher,
        registry=registry,
        config=runtime,
    )

    retry_run_id, retry_execution_id = _create_direct_run(
        repository,
        dispatcher,
        project_id,
        {"__replay_behavior": {"mode": "error", "temporary": True}},
        max_attempts=2,
    )
    assert worker.run_once() is True
    retry_once = repository.get_execution(project_id, retry_run_id, retry_execution_id)
    assert retry_once["status"] == "retry_wait"
    assert retry_once["attempt_count"] == 1
    dispatcher.dispatch(retry_execution_id)
    assert worker.run_once() is True
    retry_done = repository.get_execution(project_id, retry_run_id, retry_execution_id)
    assert retry_done["status"] == "failed"
    assert len(retry_done["attempts"]) == 2

    timeout_run_id, timeout_execution_id = _create_direct_run(
        repository,
        dispatcher,
        project_id,
        {"__replay_behavior": {"mode": "delay", "seconds": 0.1}},
        timeout_seconds=0.01,
    )
    assert worker.run_once() is True
    timeout_done = repository.get_execution(project_id, timeout_run_id, timeout_execution_id)
    assert timeout_done["status"] == "failed"
    assert timeout_done["safe_error"]["code"] == "timeout"

    fenced_run_id, fenced_execution_id = _create_direct_run(
        repository, dispatcher, project_id, {"value": "fenced"}
    )
    old = repository.claim_execution(
        fenced_execution_id, "old-worker", datetime.now(UTC), lease_seconds=0.05
    )
    assert old is not None
    time.sleep(0.08)
    recovered = repository.claim_execution(
        fenced_execution_id, "new-worker", datetime.now(UTC), lease_seconds=1.0
    )
    assert recovered is not None
    assert not repository.complete_success(
        execution_id=fenced_execution_id,
        claim_token=old.claim_token,
        attempt_number=old.attempt_number,
        output={"stale": True},
        request_fingerprint_value="stale-request",
        response_fingerprint="stale-response",
        generated_trace_id=None,
        now=datetime.now(UTC),
        duration_seconds=0.01,
    )
    assert repository.complete_success(
        execution_id=fenced_execution_id,
        claim_token=recovered.claim_token,
        attempt_number=recovered.attempt_number,
        output={"stale": False},
        request_fingerprint_value="fresh-request",
        response_fingerprint="fresh-response",
        generated_trace_id=None,
        now=datetime.now(UTC),
        duration_seconds=0.01,
    )
    assert repository.get_run(project_id, fenced_run_id)["status"] == "succeeded"


def test_manifest_modes_side_effect_and_timeout(m9_runtime) -> None:
    _, config, trace_repository, repository, dispatcher, runtime, app, _ = m9_runtime
    del config, trace_repository, repository, dispatcher, app

    common = {
        "dataset_version_id": uuid4(),
        "dataset_checksum": "b" * 64,
        "target_profile_id": "target",
        "target_version": "1",
        "reproducibility_status": ReproducibilityStatus.PARTIAL,
    }
    with pytest.raises(ValueError):
        ReplayManifest(replay_mode=ReplayMode.EXACT, **common)
    ReplayManifest(replay_mode=ReplayMode.CONTROLLED, changed_dimensions=("prompt",), **common)
    ReplayManifest(replay_mode=ReplayMode.BEST_EFFORT, best_effort_reason="unknown", **common)
