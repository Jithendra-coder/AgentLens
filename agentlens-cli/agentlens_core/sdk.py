"""3-Line Drop-in SDK for any external Python RAG application."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from agentlens_core.db import StorageManager
from agentlens_core.lighthouse import calculate_lighthouse_audit
from agentlens_core.report import generate_raglens_html_report


class RagLensTracer:
    """Context manager for tracing external RAG pipelines."""

    def __init__(self, query: str, model: str = "gpt-4o", domain: str = "Custom RAG Application") -> None:
        self.query = query
        self.model = model
        self.domain = domain
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.chunks: List[Dict[str, Any]] = []
        self.pipeline_spans: List[Dict[str, Any]] = []
        self.tokens: int = 2500
        self.cost: float = 0.0050
        self.trace_id = f"trace_{uuid4().hex[:12]}"
        self.api_key = f"rl_key_{uuid4().hex[:16]}"
        self.db = StorageManager()

    def __enter__(self) -> "RagLensTracer":
        self.start_time = time.perf_counter()
        return self

    def log_retrieval(self, chunks: List[Any], scores: Optional[List[float]] = None) -> None:
        """Record retrieved document chunks and similarity scores."""
        scores = scores or [0.85] * len(chunks)
        self.chunks = []
        for idx, c in enumerate(chunks):
            txt = str(c)
            self.chunks.append(
                {
                    "chunk_id": f"chk_{uuid4().hex[:6]}",
                    "doc": f"doc_{idx+1}.txt",
                    "size_tokens": max(50, len(txt.split())),
                    "similarity": scores[idx] if idx < len(scores) else 0.75,
                }
            )

    def log_generation(self, model: Optional[str] = None, prompt_tokens: int = 1500, completion_tokens: int = 250) -> None:
        """Record model generation parameters."""
        if model:
            self.model = model
        self.tokens = prompt_tokens + completion_tokens
        # Pricing estimation
        cost_per_k = 0.0050 if "gpt-4o" in self.model else 0.0030
        self.cost = round((self.tokens / 1000) * cost_per_k, 4)

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.end_time = time.perf_counter()
        total_lat_ms = (self.end_time - self.start_time) * 1000.0

        if not self.chunks:
            self.chunks = [
                {"chunk_id": "chk_default", "doc": "knowledge_doc.pdf", "size_tokens": 450, "similarity": 0.84}
            ]

        self.pipeline_spans = [
            {"name": "01. Retrieval", "span_type": "retrieval", "latency_ms": round(total_lat_ms * 0.35, 1), "component": "Vector Store", "pct": 35.0},
            {"name": "02. LLM Synthesis", "span_type": "llm", "latency_ms": round(total_lat_ms * 0.65, 1), "component": self.model, "pct": 65.0},
        ]

        # Calculate Lighthouse Audit
        audit = calculate_lighthouse_audit(
            query=self.query,
            total_latency_ms=total_lat_ms,
            pipeline_spans=self.pipeline_spans,
            chunks=self.chunks,
            total_tokens=self.tokens,
            cost_usd=self.cost,
        )

        # Save to DB
        summary = {
            "api_key": self.api_key,
            "trace_id": self.trace_id,
            "query": self.query,
            "domain": self.domain,
            "model": self.model,
            "total_latency_ms": round(total_lat_ms, 1),
            "total_tokens": self.tokens,
            "cost_usd": self.cost,
            "overall_score": audit["overall_score"],
            "overall_grade": audit["overall_grade"],
        }
        self.db.save_report(
            api_key=self.api_key,
            trace_id=self.trace_id,
            query=self.query,
            total_latency_ms=total_lat_ms,
            total_tokens=self.tokens,
            cost_usd=self.cost,
            status="success",
            summary=summary,
            pipeline_spans=self.pipeline_spans,
            diagnosis={"primary_bottleneck": f"LLM Generation ({self.model})"},
            chunks=self.chunks,
        )

        # Generate HTML report
        html_path = generate_raglens_html_report(
            api_key=self.api_key,
            trace_id=self.trace_id,
            query=self.query,
            domain=self.domain,
            total_latency_ms=total_lat_ms,
            total_tokens=self.tokens,
            cost_usd=self.cost,
            status="success",
            pipeline_spans=self.pipeline_spans,
            diagnosis={"primary_bottleneck": f"LLM Generation ({self.model})"},
            chunks=self.chunks,
            lighthouse=audit,
        )

        # Terminal feedback
        print(f"\n[AgentLens] Lighthouse Audit: Grade {audit['overall_grade']} ({audit['overall_score']}/100)")
        print(f"[AgentLens] API Key: {self.api_key} | Report: {html_path}\n")


def trace_rag(model: str = "gpt-4o", domain: str = "Custom RAG") -> Callable[..., Any]:
    """Decorator to automatically audit any RAG function."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            query_str = args[0] if args and isinstance(args[0], str) else kwargs.get("query", "Evaluation Query")
            with RagLensTracer(query=str(query_str), model=model, domain=domain) as tracer:
                result = fn(*args, **kwargs)
                if isinstance(result, (list, tuple)):
                    tracer.log_retrieval(result)
                return result

        return wrapper

    return decorator
