"""M11 API and persistence checks against real PostgreSQL/Redis-backed M10 evidence."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, update

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.quality_gates.repository import PostgresQualityGateRepository
from agentlens.storage import DatabaseConfig, PostgresTraceRepository
from agentlens.storage.models import (
    dataset_cases,
    dataset_versions,
    datasets,
    quality_gate_decisions,
    quality_gate_policies,
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
    not DATABASE_URL or not REDIS_URL, reason="M11 integration requires PostgreSQL and Redis"
)


def test_quality_gate_api_and_policy_scenarios() -> None:
    assert DATABASE_URL and REDIS_URL
    project_id = f"m11-{uuid4()}"
    environment = os.environ.copy()
    environment["AGENTLENS_DATABASE_URL"] = DATABASE_URL
    environment["AGENTLENS_REDIS_URL"] = REDIS_URL
    environment["AGENTLENS_PROJECT_ID"] = project_id
    seeded = subprocess.run(
        [sys.executable, "scripts/seed_m10_browser_fixture.py"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    run_id = UUID(seeded.stdout.strip().splitlines()[-1])
    config = DatabaseConfig(DATABASE_URL)
    trace_repo = PostgresTraceRepository(config)
    gate_repo = PostgresQualityGateRepository(config, engine=trace_repo.engine)
    auth = InMemoryApiKeyAuthenticator()
    auth.register(api_key="m11-a", key_id="m11-a", project_id=project_id)
    auth.register(api_key="m11-b", key_id="m11-b", project_id=f"other-{project_id}")
    app = create_app(database=config, authenticator=auth)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": "Bearer m11-a"}
            policy_body = {
                "name": "production-support-agent",
                "description": "Blocking quality and latency release rules.",
                "rules": [
                    {
                        "name": "no-task-success-regression",
                        "source": "metric_classification",
                        "metric": "replay.execution_success_rate",
                        "block_if": "regressed",
                        "on_missing": "fail",
                        "blocking": True,
                    },
                    {
                        "name": "p95-latency",
                        "source": "metric_classification",
                        "metric": "trace.duration_ms.p95",
                        "block_if": "regressed",
                        "require_candidate_limit_ok": True,
                        "on_missing": "fail",
                        "blocking": True,
                    },
                ],
            }
            created_policy = await client.post(
                "/v1/quality-gate-policies", headers=headers, json=policy_body
            )
            assert created_policy.status_code == 201, created_policy.text
            policy_id = created_policy.json()["gate_policy_id"]
            assert (await client.get("/v1/quality-gate-policies", headers=headers)).json()["items"]
            assert (
                await client.get(f"/v1/quality-gate-policies/{policy_id}", headers=headers)
            ).status_code == 200
            with trace_repo.engine.begin() as connection:
                connection.execute(
                    update(regression_runs)
                    .where(regression_runs.c.regression_run_id == run_id)
                    .values(status="running")
                )
            try:
                nonterminal = await client.post(
                    "/v1/quality-gate-decisions",
                    headers=headers,
                    json={"regression_run_id": str(run_id), "gate_policy_id": policy_id},
                )
                assert nonterminal.status_code == 422
            finally:
                with trace_repo.engine.begin() as connection:
                    connection.execute(
                        update(regression_runs)
                        .where(regression_runs.c.regression_run_id == run_id)
                        .values(status="completed")
                    )
            created = await client.post(
                "/v1/quality-gate-decisions",
                headers={**headers, "Idempotency-Key": "m11-blocking"},
                json={"regression_run_id": str(run_id), "gate_policy_id": policy_id},
            )
            assert created.status_code == 201, created.text
            failed = created.json()
            assert failed["status"] == "failed"
            assert failed["blocking_failure_count"] == 1
            assert failed["rule_results"][0]["status"] == "passed"
            assert failed["rule_results"][1]["status"] == "failed"
            duplicate = await client.post(
                "/v1/quality-gate-decisions",
                headers={**headers, "Idempotency-Key": "m11-blocking"},
                json={"regression_run_id": str(run_id), "gate_policy_id": policy_id},
            )
            assert duplicate.status_code == 201 and duplicate.json()["duplicate"] is True
            assert (
                await client.get(
                    f"/v1/quality-gate-decisions/{failed['decision_id']}", headers=headers
                )
            ).json()["status"] == "failed"
            assert (
                await client.get("/v1/quality-gate-decisions?status=failed", headers=headers)
            ).json()["items"]

            advisory_policy = await client.post(
                "/v1/quality-gate-policies",
                headers=headers,
                json={
                    "name": "advisory-latency",
                    "description": "Latency warning only.",
                    "rules": [
                        {
                            "name": "latency-advisory",
                            "metric": "trace.duration_ms.p95",
                            "block_if": "regressed",
                            "blocking": False,
                        }
                    ],
                },
            )
            advisory_decision = await client.post(
                "/v1/quality-gate-decisions",
                headers=headers,
                json={
                    "regression_run_id": str(run_id),
                    "gate_policy_id": advisory_policy.json()["gate_policy_id"],
                },
            )
            assert advisory_decision.status_code == 201
            assert advisory_decision.json()["status"] == "passed"
            assert advisory_decision.json()["advisory_failure_count"] == 1

            missing_policy = await client.post(
                "/v1/quality-gate-policies",
                headers=headers,
                json={
                    "name": "required-groundedness",
                    "description": "Required evidence.",
                    "required_metrics": ["rag.groundedness"],
                    "required_metrics_on_missing": "indeterminate",
                },
            )
            missing_decision = await client.post(
                "/v1/quality-gate-decisions",
                headers=headers,
                json={
                    "regression_run_id": str(run_id),
                    "gate_policy_id": missing_policy.json()["gate_policy_id"],
                },
            )
            assert missing_decision.json()["status"] == "indeterminate"
            assert (
                await client.get(
                    f"/v1/quality-gate-decisions/{failed['decision_id']}",
                    headers={"Authorization": "Bearer m11-b"},
                )
            ).status_code == 404

    try:
        asyncio.run(scenario())
    finally:
        with trace_repo.engine.begin() as connection:
            connection.execute(
                delete(quality_gate_decisions).where(
                    quality_gate_decisions.c.project_id == project_id
                )
            )
            connection.execute(
                delete(quality_gate_policies).where(
                    quality_gate_policies.c.project_id == project_id
                )
            )
            connection.execute(
                delete(regression_case_comparisons).where(
                    regression_case_comparisons.c.regression_run_id.in_(
                        select_ids(connection, regression_runs, project_id)
                    )
                )
            )
            connection.execute(
                delete(regression_metric_comparisons).where(
                    regression_metric_comparisons.c.regression_run_id.in_(
                        select_ids(connection, regression_runs, project_id)
                    )
                )
            )
            connection.execute(
                delete(regression_runs).where(regression_runs.c.project_id == project_id)
            )
            connection.execute(
                delete(regression_policies).where(regression_policies.c.project_id == project_id)
            )
            connection.execute(
                delete(replay_attempts).where(
                    replay_attempts.c.execution_id.in_(
                        select_ids(connection, replay_case_executions, project_id, "execution_id")
                    )
                )
            )
            connection.execute(
                delete(replay_case_executions).where(
                    replay_case_executions.c.project_id == project_id
                )
            )
            connection.execute(delete(replay_runs).where(replay_runs.c.project_id == project_id))
            connection.execute(
                delete(dataset_cases).where(dataset_cases.c.project_id == project_id)
            )
            connection.execute(
                delete(dataset_versions).where(dataset_versions.c.project_id == project_id)
            )
            connection.execute(delete(datasets).where(datasets.c.project_id == project_id))
            connection.execute(delete(traces).where(traces.c.project_id == project_id))
        gate_repo.dispose()
        trace_repo.dispose()


def select_ids(connection, table, project_id: str, column: str = "regression_run_id"):
    """Small test-only query helper kept local to avoid production abstractions."""

    from sqlalchemy import select

    return select(getattr(table.c, column)).where(table.c.project_id == project_id)
