"""M11 API and persistence checks against real PostgreSQL/Redis-backed M10 evidence."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, update

from agentlens.regression.runtime import RegressionRuntimeConfig, RegressionWorker
from agentlens.storage.models import (
    quality_gate_decisions,
    quality_gate_policies,
    regression_runs,
)

DATABASE_URL = os.environ.get("AGENTLENS_TEST_DATABASE_URL") or os.environ.get(
    "AGENTLENS_DATABASE_URL"
)
REDIS_URL = os.environ.get("AGENTLENS_TEST_REDIS_URL") or os.environ.get("AGENTLENS_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL, reason="M11 integration requires PostgreSQL and Redis"
)


def test_quality_gate_api_and_policy_scenarios(m10_runtime) -> None:
    assert DATABASE_URL and REDIS_URL
    (
        project_id,
        trace_repo,
        _,
        regression_repo,
        regression_dispatcher,
        evaluation_dispatcher,
        eval_jobs,
        eval_results,
        app,
        baseline_id,
        candidate_id,
    ) = m10_runtime
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
    run_id = None

    async def scenario() -> None:
        nonlocal run_id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"Authorization": "Bearer m10-a"}
            regression_policy = await client.post(
                "/v1/regression-policies",
                headers=headers,
                json={
                    "name": "quality-gate-fixture",
                    "description": "Seed completed quality and latency comparisons.",
                    "rules": [
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
                    ],
                },
            )
            assert regression_policy.status_code == 201, regression_policy.text
            regression = await client.post(
                "/v1/regression-runs",
                headers={**headers, "Idempotency-Key": f"m11-run-{uuid4()}"},
                json={
                    "baseline_replay_run_id": str(baseline_id),
                    "candidate_replay_run_id": str(candidate_id),
                    "policy_id": regression_policy.json()["policy_id"],
                },
            )
            assert regression.status_code == 202, regression.text
            run_id = regression.json()["regression_run_id"]
            regression_dispatcher._client.delete(regression_dispatcher.config.queue_name)
            assert worker.recover_once() == 1
            assert worker.run_once() is True
            report = await client.get(f"/v1/regression-runs/{run_id}", headers=headers)
            assert report.json()["status"] == "completed", report.text
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
                    headers={"Authorization": "Bearer m10-b"},
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
