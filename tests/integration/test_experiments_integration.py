"""Integration tests  Experimentation Framework and API routes."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.experimentation.repository import InMemoryExperimentRepository
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-experiments-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-experimentation",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    exp_repo = InMemoryExperimentRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        experiment_repository=exp_repo,
    )
    return app


async def send_request(
    app,
    method: str,
    path: str,
    *,
    api_key: str | None = MASTER_KEY,
    json_body: object | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request_headers = dict(headers or {})
    if api_key is not None:
        request_headers.setdefault("Authorization", f"Bearer {api_key}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, headers=request_headers, json=json_body)


def test_experimentation_workflow_and_reporting() -> None:
    app = make_test_app()

    async def run():
        # 1. Create an A/B experiment
        create_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-experimentation/experiments",
            json_body={
                "name": "Prompt Optimization Alpha",
                "description": "Evaluating concise prompt vs verbose prompt",
                "experiment_type": "ab_test",
                "variants": [
                    {
                        "name": "Control (Verbose)",
                        "prompt_template": "You are an assistant. Please answer: {q}",
                        "model_name": "gpt-4o",
                        "provider_type": "openai",
                        "traffic_weight": 0.5,
                        "is_control": True,
                    },
                    {
                        "name": "Treatment (Concise)",
                        "prompt_template": "Answer in <= 10 words: {q}",
                        "model_name": "gpt-4o-mini",
                        "provider_type": "openai",
                        "traffic_weight": 0.5,
                        "is_control": False,
                    },
                ],
            },
        )
        assert create_res.status_code == 200
        exp_data = create_res.json()
        exp_id = exp_data["experiment_id"]
        v_control_id = exp_data["variants"][0]["variant_id"]
        v_treatment_id = exp_data["variants"][1]["variant_id"]

        # 2. Test deterministic traffic split
        split_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-experimentation/experiments/{exp_id}/split",
            json_body={"routing_key": "user_session_42"},
        )
        assert split_res.status_code == 200
        split_data = split_res.json()
        assert split_data["experiment_id"] == exp_id
        assert split_data["selected_variant_id"] in (v_control_id, v_treatment_id)

        # 3. Record evaluations for both variants
        eval_ctrl_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-experimentation/experiments/{exp_id}/evaluations",
            json_body={
                "variant_id": v_control_id,
                "trace_id": str(uuid4()),
                "score": 0.80,
                "cost_usd": 0.010,
                "latency_ms": 1200.0,
            },
        )
        assert eval_ctrl_res.status_code == 200

        eval_treat_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-experimentation/experiments/{exp_id}/evaluations",
            json_body={
                "variant_id": v_treatment_id,
                "trace_id": str(uuid4()),
                "score": 0.92,
                "cost_usd": 0.002,
                "latency_ms": 400.0,
            },
        )
        assert eval_treat_res.status_code == 200

        # 4. Fetch comparative report
        report_res = await send_request(
            app,
            "GET",
            f"/v1/projects/proj-experimentation/experiments/{exp_id}/report",
        )
        assert report_res.status_code == 200
        report_data = report_res.json()
        assert report_data["total_evaluations"] == 2
        assert len(report_data["variants"]) == 2

        treat_metric = next(v for v in report_data["variants"] if not v["is_control"])
        assert treat_metric["mean_score"] == 0.92
        assert treat_metric["score_delta_pct"] == 15.0  # (0.92 - 0.80) / 0.80 = +15%
        assert treat_metric["cost_delta_pct"] == -80.0  # (0.002 - 0.010) / 0.010 = -80%

    asyncio.run(run())
