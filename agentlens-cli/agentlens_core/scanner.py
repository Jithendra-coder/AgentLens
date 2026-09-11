"""Universal RAG Codebase Architecture & Static Lighthouse Scanner.

Scans any directory for chunking parameters, vector databases, embedding models,
rerankers, and generation patterns, returning a Lighthouse architecture grade and recommendations.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class CodebaseScanner:
    """Recursively scans any project folder for RAG patterns and configurations."""

    VECTOR_DB_PATTERNS = {
        "pinecone": "Pinecone Vector Database",
        "chromadb": "ChromaDB Embedded Vector Store",
        "qdrant": "Qdrant Vector Database",
        "weaviate": "Weaviate Vector Search Engine",
        "faiss": "FAISS In-Memory Vector Index",
        "pgvector": "PostgreSQL pgvector Extension",
        "milvus": "Milvus Distributed Vector Store",
        "opensearch": "OpenSearch Vector Search",
    }

    EMBEDDING_PATTERNS = {
        "text-embedding-3-small": ("OpenAI text-embedding-3-small (1536 dim)", 0.00002),
        "text-embedding-3-large": ("OpenAI text-embedding-3-large (3072 dim)", 0.00013),
        "text-embedding-ada-002": ("OpenAI text-embedding-ada-002 (Legacy)", 0.00010),
        "all-minilm": ("HuggingFace sentence-transformers/all-MiniLM-L6-v2 (Local 384 dim)", 0.0),
        "bge-": ("BAAI BGE Embedding Model (Open Weights)", 0.0),
        "cohere": ("Cohere Embed v3 (Multilingual)", 0.00010),
        "voyage": ("Voyage AI Embedding Model", 0.00012),
    }

    LLM_PATTERNS = {
        "gpt-4o-mini": ("GPT-4o Mini (Ultra-Fast OpenAI)", 0.0006),
        "gpt-4o": ("GPT-4o (Balanced Latency OpenAI)", 0.0050),
        "gpt-4-turbo": ("GPT-4 Turbo", 0.0100),
        "claude-3-5-sonnet": ("Claude 3.5 Sonnet (Anthropic)", 0.0060),
        "claude-3-haiku": ("Claude 3 Haiku (Fast Anthropic)", 0.0008),
        "gemini-1.5-pro": ("Gemini 1.5 Pro (Google DeepMind 2M)", 0.0035),
        "gemini-1.5-flash": ("Gemini 1.5 Flash (Google DeepMind)", 0.0003),
        "llama-3": ("Meta Llama 3 Open Model", 0.0007),
    }

    def __init__(self, target_dir: str | Path) -> None:
        self.target_dir = Path(target_dir).resolve()

    def scan(self) -> Dict[str, Any]:
        """Perform full static analysis on the target project directory."""
        if not self.target_dir.exists():
            return {
                "error": f"Target directory not found: {self.target_dir}",
                "target_dir": str(self.target_dir),
            }

        files_scanned = 0
        detected_vbs: Dict[str, List[Dict[str, Any]]] = {}
        detected_embeddings: Dict[str, List[Dict[str, Any]]] = {}
        detected_llms: Dict[str, List[Dict[str, Any]]] = {}
        detected_rerankers: List[Dict[str, Any]] = []
        chunk_configs: List[Dict[str, Any]] = []
        top_k_configs: List[Dict[str, Any]] = []
        streaming_enabled = False
        prompt_caching_detected = False

        ignore_dirs = {
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "env",
            "__pycache__",
            ".pytest_cache",
            ".next",
            "dist",
            "build",
        }

        for root, dirs, files in os.walk(str(self.target_dir)):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                if file.endswith((".py", ".ts", ".js", ".json", ".yaml", ".yml", ".env")):
                    files_scanned += 1
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(self.target_dir)
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        lines = content.splitlines()

                        for idx, line in enumerate(lines, 1):
                            line_lower = line.lower()

                            # 1. Vector DB detection
                            for vdb_key, vdb_name in self.VECTOR_DB_PATTERNS.items():
                                if vdb_key in line_lower and not line.strip().startswith("#"):
                                    detected_vbs.setdefault(vdb_name, []).append(
                                        {"file": str(rel_path), "line": idx, "snippet": line.strip()[:100]}
                                    )

                            # 2. Embedding detection
                            for emb_key, (emb_name, cost) in self.EMBEDDING_PATTERNS.items():
                                if emb_key in line_lower and not line.strip().startswith("#"):
                                    detected_embeddings.setdefault(emb_name, []).append(
                                        {"file": str(rel_path), "line": idx, "snippet": line.strip()[:100]}
                                    )

                            # 3. LLM detection
                            for llm_key, (llm_name, cost) in self.LLM_PATTERNS.items():
                                if llm_key in line_lower and not line.strip().startswith("#"):
                                    detected_llms.setdefault(llm_name, []).append(
                                        {"file": str(rel_path), "line": idx, "snippet": line.strip()[:100]}
                                    )

                            # 4. Reranker detection
                            if any(r in line_lower for r in ["rerank", "cross_encoder", "cohere.rerank", "flashrank"]):
                                if not line.strip().startswith("#"):
                                    detected_rerankers.append(
                                        {"file": str(rel_path), "line": idx, "snippet": line.strip()[:100]}
                                    )

                            # 5. Chunk size detection
                            chunk_match = re.search(r"chunk_size\s*[:=]\s*(\d+)", line, re.IGNORECASE)
                            if chunk_match:
                                sz = int(chunk_match.group(1))
                                chunk_configs.append(
                                    {"size": sz, "file": str(rel_path), "line": idx, "snippet": line.strip()[:100]}
                                )

                            # 6. Top-K detection
                            topk_match = re.search(r"(?:top_k|topk|k)\s*[:=]\s*(\d+)", line, re.IGNORECASE)
                            if topk_match and not any(k in line_lower for k in ["api_key", "key"]):
                                k_val = int(topk_match.group(1))
                                if 1 <= k_val <= 100:
                                    top_k_configs.append(
                                        {"k": k_val, "file": str(rel_path), "line": idx, "snippet": line.strip()[:100]}
                                    )

                            # 7. Streaming readiness
                            if re.search(r"stream\s*=\s*true", line_lower) or any(s in line_lower for s in ["streamingresponse", "eventsourceresponse", "text/event-stream"]):
                                streaming_enabled = True

                            # 8. Prompt caching
                            if any(c in line_lower for c in ["prompt_cache", "cache_control", "ephemeral"]):
                                prompt_caching_detected = True

                    except Exception:
                        continue

        # Compute Architecture Lighthouse Grade based on detected parameters
        audit = self._calculate_architecture_score(
            chunk_configs=chunk_configs,
            top_k_configs=top_k_configs,
            has_reranker=bool(detected_rerankers),
            has_vector_db=bool(detected_vbs),
            has_embeddings=bool(detected_embeddings),
            streaming_enabled=streaming_enabled,
            prompt_caching_detected=prompt_caching_detected,
        )

        return {
            "target_dir": str(self.target_dir),
            "files_scanned": files_scanned,
            "architecture_audit": audit,
            "detected_components": {
                "vector_databases": list(detected_vbs.keys()),
                "embedding_models": list(detected_embeddings.keys()),
                "llm_generators": list(detected_llms.keys()),
                "reranker_found": bool(detected_rerankers),
                "streaming_ready": streaming_enabled,
                "prompt_caching": prompt_caching_detected,
            },
            "findings": {
                "chunk_configurations": chunk_configs[:5],
                "top_k_settings": top_k_configs[:5],
                "vector_dbs": {k: v[:2] for k, v in detected_vbs.items()},
                "embeddings": {k: v[:2] for k, v in detected_embeddings.items()},
                "llms": {k: v[:2] for k, v in detected_llms.items()},
            },
        }

    def _calculate_architecture_score(
        self,
        chunk_configs: List[Dict[str, Any]],
        top_k_configs: List[Dict[str, Any]],
        has_reranker: bool,
        has_vector_db: bool,
        has_embeddings: bool,
        streaming_enabled: bool,
        prompt_caching_detected: bool,
    ) -> Dict[str, Any]:
        """Compute architectural grade and opportunities based on static analysis."""
        score = 80
        opportunities = []

        # 1. Chunk size analysis
        chunk_sizes = [c["size"] for c in chunk_configs]
        oversized = [sz for sz in chunk_sizes if sz > 800]
        if oversized:
            score -= 15
            opportunities.append(
                {
                    "title": f"Reduce Oversized Chunking Size ({max(oversized)} tokens detected)",
                    "category": "Vector Density & Cost",
                    "impact": "HIGH",
                    "recommendation": (
                        f"Detected chunk size of {max(oversized)} tokens in project. "
                        "Splitting chunks to 350-500 tokens reduces prompt cost by ~40% and minimizes context contamination."
                    ),
                }
            )
        elif chunk_sizes:
            score += 5

        # 2. Streaming audit (TTFT)
        if not streaming_enabled:
            score -= 10
            opportunities.append(
                {
                    "title": "Enable Token Streaming (SSE / Async Generator)",
                    "category": "Latency & UX",
                    "impact": "HIGH",
                    "recommendation": (
                        "No streaming tokens detected (`stream=True` or `StreamingResponse`). "
                        "Enabling token streaming will improve Time-To-First-Token (TTFT) by 60-75%."
                    ),
                }
            )
        else:
            score += 5

        # 3. Top-K vs Reranker audit
        k_values = [k["k"] for k in top_k_configs]
        max_k = max(k_values) if k_values else 5
        if max_k > 6 and not has_reranker:
            score -= 10
            opportunities.append(
                {
                    "title": f"Add Cross-Encoder Reranker for High Top-K (K={max_k})",
                    "category": "Accuracy & Grounding",
                    "impact": "MEDIUM",
                    "recommendation": (
                        f"Retrieving K={max_k} passages without a reranker causes context stuffing. "
                        "Add a Cohere or FlashRank reranker to compress Top-K to Top-3 before LLM synthesis."
                    ),
                }
            )

        # 4. Prompt caching
        if not prompt_caching_detected:
            opportunities.append(
                {
                    "title": "Enable System Prompt Caching",
                    "category": "Cost Economy",
                    "impact": "MEDIUM",
                    "recommendation": (
                        "Static system prompts and schema definitions can be cached with OpenAI/Claude prompt caching, "
                        "saving ~35% on prompt tokens."
                    ),
                }
            )

        score = max(35, min(98, score))
        if score >= 90:
            grade = "A"
        elif score >= 80:
            grade = "B"
        elif score >= 70:
            grade = "C"
        elif score >= 60:
            grade = "D"
        else:
            grade = "F"

        return {
            "score": score,
            "grade": grade,
            "opportunities": opportunities,
        }
