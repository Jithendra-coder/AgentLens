"""AgentLens Core - Lightweight, standalone CLI and evaluation engine for RAG."""

from __future__ import annotations

__version__ = "0.2.0"

from agentlens_core.lighthouse import calculate_lighthouse_audit
from agentlens_core.sdk import trace_rag, RagLensTracer

__all__ = ["calculate_lighthouse_audit", "trace_rag", "RagLensTracer", "__version__"]
