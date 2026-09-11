"""Interactive & Multi-Model RAG Diagnostic Runner."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agentlens_core.db import StorageManager
from agentlens_core.lighthouse import calculate_lighthouse_audit
from agentlens_core.report import generate_raglens_html_report

MODEL_PROFILES = {
    "claude-3-5-sonnet": {
        "name": "Claude 3.5 Sonnet (Anthropic)",
        "provider": "anthropic",
        "lat_range": (1100, 1600),
        "cost_factor": 0.0045,
    },
    "gpt-4o": {
        "name": "GPT-4o (OpenAI)",
        "provider": "openai",
        "lat_range": (550, 850),
        "cost_factor": 0.0035,
    },
    "gpt-4o-mini": {
        "name": "GPT-4o Mini (Ultra-Fast OpenAI)",
        "provider": "openai",
        "lat_range": (280, 450),
        "cost_factor": 0.0006,
    },
    "gemini-1.5-pro": {
        "name": "Gemini 1.5 Pro (Google DeepMind)",
        "provider": "google",
        "lat_range": (700, 1050),
        "cost_factor": 0.0025,
    },
    "llama-3.1-70b": {
        "name": "Llama 3.1 70B (Meta / Groq LPU)",
        "provider": "groq",
        "lat_range": (180, 320),
        "cost_factor": 0.0009,
    },
}


def run_pipeline(
    query: Optional[str] = None,
    scenario: str = "normal",
    domain: str = "Enterprise Billing & Legal Terms v2.4",
    model: str = "claude-3-5-sonnet",
    interactive: bool = False,
) -> int:
    """Execute diagnostic pipeline and print terminal audit."""
    print("\n" + "=" * 72)
    print("  RAGLENS - RAG Application & Architecture Diagnostic Engine")
    print("=" * 72)

    if interactive:
        try:
            print("\n[Step 1/4] User Evaluation Query")
            prompt_in = input("  Enter test prompt/question [or press Enter for default] > ").strip()
            query = prompt_in if prompt_in else (query or "What is our enterprise refund policy for annual licenses?")

            print("\n[Step 2/4] Retrieval & Performance Scenario")
            print("  [1] Normal Latency & High Grounding (Default)")
            print("  [2] Slow Cross-Encoder Reranker Latency Spike")
            print("  [3] Low Retrieval Grounding & Hallucination Risk")
            val = input("  Select scenario [1-3, default 1] > ").strip()
            if val == "2":
                scenario = "slow_rerank"
            elif val == "3":
                scenario = "weak_retrieval"
            else:
                scenario = "normal"

            print("\n[Step 3/4] Enterprise Knowledge Domain")
            print("  [1] Enterprise Billing & Legal Terms v2.4 (Default)")
            print("  [2] Multi-Tenant Architecture & Okta SAML Auth")
            print("  [3] Internal Engineering Runbooks & SRE Protocols")
            val = input("  Select domain [1-3, default 1] > ").strip()
            if val == "2":
                domain = "Multi-Tenant Architecture & Okta SAML Auth"
            elif val == "3":
                domain = "Internal Engineering Runbooks & SRE Protocols"
            else:
                domain = "Enterprise Billing & Legal Terms v2.4"

            print("\n[Step 4/4] LLM Generation Model")
            print("  [1] Claude 3.5 Sonnet (Anthropic - Default)")
            print("  [2] GPT-4o (OpenAI - Balanced Latency/Accuracy)")
            print("  [3] GPT-4o Mini (OpenAI - Ultra Fast & Cost Effective)")
            print("  [4] Gemini 1.5 Pro (Google DeepMind - 2M Context)")
            print("  [5] Llama 3.1 70B (Meta - High Speed Groq LPUs)")
            val = input("  Select model [1-5, default 1] > ").strip()
            if val == "2":
                model = "gpt-4o"
            elif val == "3":
                model = "gpt-4o-mini"
            elif val == "4":
                model = "gemini-1.5-pro"
            elif val == "5":
                model = "llama-3.1-70b"
            else:
                model = "claude-3-5-sonnet"
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 0
    else:
        query = query or "What is our enterprise refund policy for annual licenses?"

    model_info = MODEL_PROFILES.get(model, MODEL_PROFILES["claude-3-5-sonnet"])
    unique_api_key = f"rl_key_{uuid4().hex[:16]}"
    trace_id = f"trace_{uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    print("\n" + "-" * 72)
    print(f"  Executing RAG Pipeline for query: '{query}'")
    print(f"  Profile: {scenario} | Domain: {domain} | Model: {model_info['name']}")
    print("-" * 72)

    is_slow_rerank = scenario == "slow_rerank"
    is_weak_retrieval = scenario == "weak_retrieval"
    has_warning = is_slow_rerank or is_weak_retrieval

    embedding_lat = random.randint(70, 90)
    retrieval_lat = random.randint(95, 130)
    rerank_lat = 710 if is_slow_rerank else random.randint(180, 260)

    if is_slow_rerank:
        llm_lat = round(model_info["lat_range"][0] * 0.85)
    else:
        llm_lat = random.randint(model_info["lat_range"][0], model_info["lat_range"][1])

    total_lat = embedding_lat + retrieval_lat + rerank_lat + 18 + llm_lat
    tokens = random.randint(3400, 4200)
    cost = round((tokens / 1000) * model_info["cost_factor"], 4)
    status = "warning" if has_warning else "success"

    scores = [0.93, 0.87, 0.42, 0.35, 0.29] if is_weak_retrieval else [0.95, 0.89, 0.84, 0.78, 0.72]

    print(f"  [01/05] Embedding Query (text-embedding-3-small)      : [OK] {embedding_lat:4d} ms")
    print(f"  [02/05] Vector ANN Search (Pinecone Serverless Top-5)  : [OK] {retrieval_lat:4d} ms")
    rerank_status = "WARN" if is_slow_rerank else "OK"
    print(f"  [03/05] Cross-Encoder Reranker (Cohere Rerank v3 Top-3): [{rerank_status}] {rerank_lat:4d} ms")
    print("  [04/05] Context & Prompt Assembly                      : [OK]   18 ms")
    print(f"  [05/05] LLM Answer Generation ({model_info['name']}): [OK] {llm_lat:4d} ms")

    pipeline_spans = [
        {"name": "01. Embedding", "span_type": "embedding", "latency_ms": embedding_lat, "component": "text-embedding-3-small", "pct": round(embedding_lat / total_lat * 100, 1)},
        {"name": "02. Vector Search", "span_type": "retrieval", "latency_ms": retrieval_lat, "component": "Pinecone Serverless", "pct": round(retrieval_lat / total_lat * 100, 1)},
        {"name": "03. Reranker", "span_type": "rerank", "latency_ms": rerank_lat, "component": "Cohere Rerank v3", "pct": round(rerank_lat / total_lat * 100, 1)},
        {"name": "04. Context Assembly", "span_type": "prompt", "latency_ms": 18, "component": "In-Memory Template", "pct": round(18 / total_lat * 100, 1)},
        {"name": "05. LLM Generation", "span_type": "llm", "latency_ms": llm_lat, "component": model_info["name"], "pct": round(llm_lat / total_lat * 100, 1)},
    ]

    clean_domain = domain.lower().replace(" ", "_").replace("&", "and")
    chunks = [
        {"chunk_id": f"chk_{uuid4().hex[:6]}", "doc": f"{clean_domain}_p1.pdf", "size_tokens": 460, "similarity": scores[0]},
        {"chunk_id": f"chk_{uuid4().hex[:6]}", "doc": f"{clean_domain}_p2.pdf", "size_tokens": 520, "similarity": scores[1]},
        {"chunk_id": f"chk_{uuid4().hex[:6]}", "doc": "enterprise_sla_terms.pdf", "size_tokens": 980, "similarity": scores[2]},
        {"chunk_id": f"chk_{uuid4().hex[:6]}", "doc": "appendix_definitions.md", "size_tokens": 310, "similarity": scores[3]},
        {"chunk_id": f"chk_{uuid4().hex[:6]}", "doc": "historical_notes.txt", "size_tokens": 120, "similarity": scores[4]},
    ]

    lighthouse_audit = calculate_lighthouse_audit(
        query=query,
        total_latency_ms=total_lat,
        pipeline_spans=pipeline_spans,
        chunks=chunks,
        total_tokens=tokens,
        cost_usd=cost,
        scenario=scenario,
    )

    primary_bottleneck = "Reranker (Cohere)" if is_slow_rerank else f"LLM Generation ({model_info['name']})"
    bottleneck_ms = rerank_lat if is_slow_rerank else llm_lat

    diagnosis = {
        "primary_bottleneck": primary_bottleneck,
        "bottleneck_ms": bottleneck_ms,
        "bottleneck_pct": round(bottleneck_ms / total_lat * 100, 1),
        "diagnosis": (
            f"Reranker latency spike ({rerank_lat}ms accounts for {round(rerank_lat/total_lat*100, 1)}% of total pipeline time)"
            if is_slow_rerank
            else f"LLM token generation took {llm_lat}ms ({round(llm_lat/total_lat*100, 1)}% of execution time)"
        ),
        "retrieval_diagnosis": (
            "3 of 5 retrieved chunks have low similarity (<0.50), causing context contamination."
            if is_weak_retrieval
            else "High citation grounding across retrieved passages (average similarity: 0.83)."
        ),
        "avg_similarity": round(sum(scores) / len(scores), 2),
        "lighthouse": lighthouse_audit,
    }

    db = StorageManager()
    summary = {
        "api_key": unique_api_key,
        "trace_id": trace_id,
        "query": query,
        "domain": domain,
        "model": model,
        "model_name": model_info["name"],
        "total_latency_ms": total_lat,
        "total_tokens": tokens,
        "cost_usd": cost,
        "status": status,
        "storage": "PostgreSQL" if db.use_postgres else "Local SQLite (~/.agentlens/agentlens.db)",
        "created_at": now_iso,
        "overall_score": lighthouse_audit["overall_score"],
        "overall_grade": lighthouse_audit["overall_grade"],
    }

    db.save_report(
        api_key=unique_api_key,
        trace_id=trace_id,
        query=query,
        total_latency_ms=total_lat,
        total_tokens=tokens,
        cost_usd=cost,
        status=status,
        summary=summary,
        pipeline_spans=pipeline_spans,
        diagnosis=diagnosis,
        chunks=chunks,
    )

    html_path = generate_raglens_html_report(
        api_key=unique_api_key,
        trace_id=trace_id,
        query=query,
        domain=domain,
        total_latency_ms=total_lat,
        total_tokens=tokens,
        cost_usd=cost,
        status=status,
        pipeline_spans=pipeline_spans,
        diagnosis=diagnosis,
        chunks=chunks,
        lighthouse=lighthouse_audit,
    )

    # Print Lighthouse Audit
    overall_sc = lighthouse_audit["overall_score"]
    overall_gr = lighthouse_audit["overall_grade"]
    pillars = lighthouse_audit["pillars"]

    print("\n" + "=" * 72)
    print("  LIGHTHOUSE FOR RAG - AUTOMATED AI PERFORMANCE AUDIT")
    print("=" * 72)
    print(f"  Overall Performance Score : {overall_sc:3d} / 100  [GRADE: {overall_gr}]")
    print("-" * 72)
    lat_p = pillars.get("latency", {})
    gro_p = pillars.get("grounding", {})
    cos_p = pillars.get("cost", {})
    vec_p = pillars.get("vector_density", {})
    print(f"  [1] Latency & Speed       : {lat_p.get('score', 0):3d} / 100 (Grade {lat_p.get('grade', 'F')})  | {lat_p.get('metric_label', '')} ({lat_p.get('sub_metric', '')})")
    print(f"  [2] Grounding & Accuracy  : {gro_p.get('score', 0):3d} / 100 (Grade {gro_p.get('grade', 'F')})  | {gro_p.get('metric_label', '')} ({gro_p.get('sub_metric', '')})")
    print(f"  [3] Cost & Token Economy  : {cos_p.get('score', 0):3d} / 100 (Grade {cos_p.get('grade', 'F')})  | {cos_p.get('metric_label', '')} ({cos_p.get('sub_metric', '')})")
    print(f"  [4] Vector Density        : {vec_p.get('score', 0):3d} / 100 (Grade {vec_p.get('grade', 'F')})  | {vec_p.get('metric_label', '')} ({vec_p.get('sub_metric', '')})")
    print("-" * 72)
    print("  TOP LIGHTHOUSE OPPORTUNITIES (ESTIMATED SAVINGS):")
    for opp in lighthouse_audit.get("opportunities", [])[:4]:
        print(f"    * [{opp.get('savings_label')}] {opp.get('title')}")
        print(f"      -> {opp.get('savings_value')}")
    print("=" * 72)

    db_engine_name = "PostgreSQL (table 'raglens_reports')" if db.use_postgres else "Local SQLite (~/.agentlens/agentlens.db)"

    print("\n" + "#" * 72)
    print(f"#  [KEY] UNIQUE RUN API KEY : {unique_api_key}")
    print(f"#  [DB]  DATABASE STORAGE   : {db_engine_name}")
    print(f"#  [RPT] OFFLINE HTML REPORT: {html_path}")
    print("#" * 72)
    print("\nNext steps:")
    print("  - To view report history:  agentlens history")
    print("  - To open the HTML report: open " + html_path + "\n")

    return 0
