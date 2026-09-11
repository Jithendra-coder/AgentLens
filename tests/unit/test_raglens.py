"""Unit tests for the RagLens RAG Application & Architecture Analyzer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentlens.api.app import create_app
from agentlens.cli import run_agent, run_check


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_raglens_overview_endpoint(client: TestClient) -> None:
    response = client.get("/v1/raglens/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "requests_total" in data
    assert "avg_latency_ms" in data
    assert "avg_tokens" in data
    assert "retrieval_accuracy_pct" in data


def test_raglens_architecture_endpoint(client: TestClient) -> None:
    response = client.get("/v1/raglens/architecture")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) >= 5
    # Verify core RAG components exist
    labels = [n["label"] for n in data["nodes"]]
    assert "User Query" in labels
    assert "Embedding Model" in labels
    assert "Vector Database" in labels
    assert "LLM Generation" in labels


def test_raglens_chunks_endpoint(client: TestClient) -> None:
    response = client.get("/v1/raglens/chunks")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert data["summary"]["total_chunks_indexed"] > 0
    assert "distribution" in data
    assert "anomalies" in data
    assert len(data["anomalies"]) >= 2


def test_raglens_performance_endpoint(client: TestClient) -> None:
    response = client.get("/v1/raglens/performance")
    assert response.status_code == 200
    data = response.json()
    assert "waterfall" in data
    assert "total_latency_ms" in data
    assert "bottlenecks" in data
    assert "similarity_distribution" in data


def test_raglens_cost_endpoint(client: TestClient) -> None:
    response = client.get("/v1/raglens/cost")
    assert response.status_code == 200
    data = response.json()
    assert "token_anatomy" in data
    assert data["token_anatomy"]["context_ratio_pct"] > 0
    assert "financials" in data
    assert "top_expensive_queries" in data


def test_raglens_traces_and_explain(client: TestClient) -> None:
    # Fetch traces
    traces_res = client.get("/v1/raglens/traces")
    assert traces_res.status_code == 200
    traces = traces_res.json()
    assert len(traces) > 0

    # Explain the first trace
    trace_id = traces[0]["trace_id"]
    explain_res = client.get(f"/v1/raglens/explain/{trace_id}")
    assert explain_res.status_code == 200
    exp = explain_res.json()
    assert exp["trace_id"] == trace_id
    assert "latency_analysis" in exp
    assert "retrieval_quality_analysis" in exp
    assert len(exp["actionable_recommendations"]) > 0


def test_raglens_ingest_telemetry(client: TestClient) -> None:
    payload = {
        "project": "test-rag-app",
        "query": "How do we handle GDPR data retention for customer support tickets?",
        "total_latency_ms": 1720,
        "total_tokens": 3400,
        "cost_usd": 0.015,
        "spans": [
            {"name": "embedding", "span_type": "embedding", "latency_ms": 80},
            {"name": "retrieval", "span_type": "retrieval", "latency_ms": 115},
            {"name": "rerank", "span_type": "rerank", "latency_ms": 280},
            {"name": "llm", "span_type": "llm", "latency_ms": 1245},
        ],
    }
    response = client.post("/v1/raglens/telemetry", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "trace_id" in data


def test_raglens_simulate_trace(client: TestClient) -> None:
    for scenario in ["normal", "slow_rerank", "weak_retrieval"]:
        response = client.post("/v1/raglens/simulate-trace", json={"scenario": scenario})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "trace_id" in data
        assert "trace" in data


def test_raglens_cli_functions() -> None:
    import argparse
    dummy_args = argparse.Namespace()
    assert run_check(dummy_args) == 0
    assert run_agent(dummy_args) == 0


def test_raglens_execute_and_get_report(client: TestClient) -> None:
    # 1. Execute RAG request -> generates unique API key and saves in PostgreSQL
    payload = {
        "query": "How do we configure Okta SAML with multi-region AWS failover?",
        "scenario": "normal",
        "domain": "Security & Architecture v3",
    }
    exec_res = client.post("/v1/raglens/execute", json=payload)
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "ok"
    assert "api_key" in exec_data
    assert exec_data["api_key"].startswith("rl_key_")
    assert "trace_id" in exec_data

    api_key = exec_data["api_key"]

    # 2. Fetch report by unique API key from PostgreSQL
    rep_res = client.get(f"/v1/raglens/report/{api_key}")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data["api_key"] == api_key
    assert rep_data["query"] == payload["query"]
    assert "pipeline_spans" in rep_data
    assert len(rep_data["pipeline_spans"]) == 5
    assert "diagnosis" in rep_data
    assert "chunks" in rep_data
    assert len(rep_data["chunks"]) == 5

    # 3. List reports
    list_res = client.get("/v1/raglens/reports")
    assert list_res.status_code == 200
    reports = list_res.json()
    assert len(reports) > 0
    assert any(r["api_key"] == api_key for r in reports)
    assert "lighthouse" in rep_data
    assert "pillars" in rep_data["lighthouse"]
    assert "latency" in rep_data["lighthouse"]["pillars"]
    assert "grounding" in rep_data["lighthouse"]["pillars"]
    assert "cost" in rep_data["lighthouse"]["pillars"]
    assert "vector_density" in rep_data["lighthouse"]["pillars"]


def test_raglens_lighthouse_engine() -> None:
    from agentlens.rag.lighthouse import calculate_lighthouse_audit, score_to_grade

    # Test score_to_grade
    assert score_to_grade(95) == "A+"
    assert score_to_grade(85) == "B+"
    assert score_to_grade(80) == "B"
    assert score_to_grade(72) == "C"
    assert score_to_grade(61) == "D"
    assert score_to_grade(45) == "F"

    # Test audit calculation with sample spans, chunks, tokens, and cost
    spans = [
        {"name": "Query Embedding", "span_type": "embedding", "duration_ms": 65},
        {"name": "Vector Retrieval", "span_type": "retrieval", "duration_ms": 110},
        {"name": "Reranker Model", "span_type": "rerank", "duration_ms": 180},
        {"name": "Context Builder", "span_type": "context", "duration_ms": 15},
        {"name": "LLM Generation", "span_type": "llm", "duration_ms": 480},
    ]
    chunks = [
        {"chunk_id": "c1", "similarity_score": 0.92, "token_count": 480},
        {"chunk_id": "c2", "similarity_score": 0.88, "token_count": 520},
    ]

    audit = calculate_lighthouse_audit(
        query="What is RAG architecture?",
        total_latency_ms=850.0,
        pipeline_spans=spans,
        chunks=chunks,
        total_tokens=2100,
        cost_usd=0.0035,
        scenario="normal",
    )
    assert 0 <= audit["overall_score"] <= 100
    assert audit["overall_grade"] in ["A+", "A", "B+", "B", "C+", "C", "D", "F"]
    assert len(audit["pillars"]) == 4
    for pillar_key, pillar_val in audit["pillars"].items():
        assert 0 <= pillar_val["score"] <= 100
        assert "grade" in pillar_val
        assert "metric_label" in pillar_val
        assert "color" in pillar_val
    assert "opportunities" in audit
    assert "audits" in audit
    assert len(audit["audits"]) >= 6


def test_raglens_cli_run() -> None:
    import argparse
    from agentlens.cli import run_raglens_run

    args = argparse.Namespace(
        query="Unit test query",
        scenario="normal",
        domain="Test Domain",
        non_interactive=True,
    )
    exit_code = run_raglens_run(args)
    assert exit_code == 0

