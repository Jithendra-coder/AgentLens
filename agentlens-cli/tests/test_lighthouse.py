"""Tests for the 4-pillar Lighthouse audit scoring engine."""

from agentlens_core.lighthouse import calculate_lighthouse_audit


def test_lighthouse_scoring_grades():
    # Fast, grounded, cost-effective run -> Grade A+
    spans = [
        {"span_type": "embedding", "latency_ms": 75},
        {"span_type": "retrieval", "latency_ms": 90},
        {"span_type": "rerank", "latency_ms": 180},
        {"span_type": "llm", "latency_ms": 400},
    ]
    chunks = [
        {"size_tokens": 400, "similarity": 0.92},
        {"size_tokens": 450, "similarity": 0.88},
    ]

    audit = calculate_lighthouse_audit(
        query="Test query",
        total_latency_ms=745,
        pipeline_spans=spans,
        chunks=chunks,
        total_tokens=2200,
        cost_usd=0.0035,
    )

    assert audit["overall_score"] >= 90
    assert audit["overall_grade"] in ("A", "A+")
    assert audit["pillars"]["latency"]["score"] >= 90
    assert audit["pillars"]["grounding"]["score"] == 100
    assert audit["pillars"]["cost"]["score"] == 100


def test_lighthouse_reranker_bottleneck_penalty():
    # Reranker taking 750ms -> Should penalize latency
    spans = [
        {"span_type": "rerank", "latency_ms": 750},
        {"span_type": "llm", "latency_ms": 600},
    ]
    chunks = [{"size_tokens": 500, "similarity": 0.85}]

    audit = calculate_lighthouse_audit(
        query="Test query",
        total_latency_ms=1600,
        pipeline_spans=spans,
        chunks=chunks,
        total_tokens=3000,
        cost_usd=0.0100,
    )

    assert audit["pillars"]["latency"]["score"] <= 60
    assert any("Rerank" in opp["title"] or "Cross-Encoder" in opp["title"] for opp in audit["opportunities"])
