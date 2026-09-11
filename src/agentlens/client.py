"""
AgentLens Python Client SDK.

Provides a clean, lightweight interface for transmitting RAG and AI Agent execution
telemetry traces to the AgentLens platform.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any, List, Optional
from uuid import UUID, uuid4

from agentlens.domain import Span, Trace, Usage


class AgentLensClient:
    """Lightweight Python SDK client for AgentLens."""

    def __init__(
        self,
        api_key: str = "dev-key-12345",
        base_url: str = "http://127.0.0.1:8000",
        project_id: str = "proj-default",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id

    def log_rag(
        self,
        query: str,
        context: List[str],
        answer: str,
        latency_ms: int = 150,
        tokens: int = 50,
        retriever_ms: Optional[int] = None,
        model: str = "gpt-4o",
        status: str = "ok",
    ) -> str:
        """
        Log a complete RAG (Retrieval-Augmented Generation) query execution in one call.

        Args:
            query: The user prompt or question.
            context: List of retrieved document strings or chunks.
            answer: The generated response from the LLM.
            latency_ms: Total end-to-end execution time in milliseconds.
            tokens: Total tokens consumed (input + output).
            retriever_ms: Optional latency spent during document retrieval.
            model: Name of the generation model.
            status: 'ok' or 'error'.

        Returns:
            The generated trace_id string.
        """
        trace_id = uuid4()
        root_span_id = uuid4()
        now = datetime.now(UTC)
        start_time = now - timedelta(milliseconds=latency_ms)

        retriever_duration = retriever_ms or max(10, int(latency_ms * 0.35))
        llm_duration = max(10, latency_ms - retriever_duration)

        input_tok = max(1, int(tokens * 0.7))
        output_tok = max(1, tokens - input_tok)
        usage = Usage(input_tokens=input_tok, output_tokens=output_tok)

        spans: List[Span] = []

        # 1. Root Chain Span
        root_span = Span(
            span_id=root_span_id,
            trace_id=trace_id,
            name=f"RAG Pipeline: {query[:32]}...",
            span_type="chain",
            started_at=start_time,
            ended_at=now,
            status=status,
            attributes={
                "query": query,
                "retrieved_count": len(context),
            },
        )
        spans.append(root_span)

        # 2. Retriever Span
        retriever_start = start_time
        retriever_end = start_time + timedelta(milliseconds=retriever_duration)
        retriever_span = Span(
            span_id=uuid4(),
            parent_span_id=root_span_id,
            trace_id=trace_id,
            name="Document Vector Retrieval",
            span_type="retriever",
            started_at=retriever_start,
            ended_at=retriever_end,
            status="ok",
            attributes={
                "top_k": len(context),
                "retrieved_context": context[:3],
            },
        )
        spans.append(retriever_span)

        # 3. LLM Generation Span
        llm_start = retriever_end
        llm_end = now
        llm_span = Span(
            span_id=uuid4(),
            parent_span_id=root_span_id,
            trace_id=trace_id,
            name=f"LLM Generation ({model})",
            span_type="llm",
            started_at=llm_start,
            ended_at=llm_end,
            status=status,
            usage=usage,
            attributes={
                "model": model,
                "prompt": query,
                "completion": answer,
            },
        )
        spans.append(llm_span)

        trace = Trace(
            trace_id=trace_id,
            project_id=self.project_id,
            name=f"RAG: {query[:35]}",
            started_at=start_time,
            ended_at=now,
            status=status,
            spans=tuple(spans),
        )

        self._send(trace.to_dict())
        return str(trace_id)

    def _send(self, payload: dict[str, Any]) -> None:
        url = f"{self.base_url}/v1/traces"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            if resp.status not in (200, 202):
                raise RuntimeError(f"Failed to ingest trace: HTTP {resp.status}")
