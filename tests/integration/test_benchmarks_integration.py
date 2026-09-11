"""Integration tests for Model Benchmarks, Qualification, and Pareto Frontier API."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.benchmarking.repository import InMemoryBenchmarkRepository
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-benchmarks-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-bench-test",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    sink = InMemoryTraceSink()
    bench_repo = InMemoryBenchmarkRepository()

    app = create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=sink,
        rbac_repository=rbac_repo,
        benchmark_repository=bench_repo,
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


def test_benchmarking_and_pareto_workflow() -> None:
    app = make_test_app()

    async def run():
        # 1. Create a benchmark suite
        create_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-bench-test/benchmarks",
            json_body={
                "name": "General Agent Capability Suite",
                "description": "Multi-turn tool use, reasoning, and context retention",
            },
        )
        assert create_res.status_code == 200
        bench_data = create_res.json()
        bench_id = bench_data["benchmark_id"]

        # 2. Record runs for GPT-4o-mini and GPT-4o
        run_mini_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-bench-test/benchmarks/{bench_id}/runs",
            json_body={
                "model_name": "gpt-4o-mini",
                "provider_type": "openai",
                "overall_score": 0.83,
                "mean_latency_ms": 450.0,
                "mean_cost_usd": 0.0004,
                "pass_rate": 0.88,
                "status": "completed",
            },
        )
        assert run_mini_res.status_code == 200
        run_mini_id = run_mini_res.json()["run_id"]

        run_4o_res = await send_request(
            app,
            "POST",
            f"/v1/projects/proj-bench-test/benchmarks/{bench_id}/runs",
            json_body={
                "model_name": "gpt-4o",
                "provider_type": "openai",
                "overall_score": 0.94,
                "mean_latency_ms": 950.0,
                "mean_cost_usd": 0.010,
                "pass_rate": 0.96,
                "status": "completed",
            },
        )
        assert run_4o_res.status_code == 200
        run_4o_id = run_4o_res.json()["run_id"]

        # 3. Evaluate qualifications
        qual_mini_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-bench-test/qualifications/evaluate",
            json_body={
                "run_id": run_mini_id,
                "min_required_score": 0.80,
                "max_latency_ms": 1000.0,
                "min_pass_rate": 0.80,
            },
        )
        assert qual_mini_res.status_code == 200
        assert qual_mini_res.json()["is_qualified"] is True

        qual_4o_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-bench-test/qualifications/evaluate",
            json_body={
                "run_id": run_4o_id,
                "min_required_score": 0.80,
                "max_latency_ms": 1500.0,
                "min_pass_rate": 0.80,
            },
        )
        assert qual_4o_res.status_code == 200
        assert qual_4o_res.json()["is_qualified"] is True

        # 4. Fetch Pareto Frontier
        pareto_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-bench-test/benchmarks/pareto",
        )
        assert pareto_res.status_code == 200
        pareto_data = pareto_res.json()
        assert len(pareto_data["points"]) == 2
        # Both gpt-4o-mini (cheaper) and gpt-4o (higher quality) are Pareto optimal
        assert all(p["is_optimal"] for p in pareto_data["points"])

    asyncio.run(run())
