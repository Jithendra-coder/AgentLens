"""Tests for the universal codebase scanner."""

from pathlib import Path
import pytest

from agentlens_core.scanner import CodebaseScanner


def test_scanner_detects_simple_rag():
    example_dir = Path(__file__).parent.parent / "examples" / "simple_rag"
    scanner = CodebaseScanner(example_dir)
    res = scanner.scan()

    assert "error" not in res
    assert res["files_scanned"] >= 1
    detected = res["detected_components"]

    # Verify detected components
    assert "Pinecone Vector Database" in detected["vector_databases"]
    assert any("OpenAI" in emb for emb in detected["embedding_models"])
    assert any("GPT-4o" in llm for llm in detected["llm_generators"])

    # Verify architecture audit flagged oversized chunk
    audit = res["architecture_audit"]
    assert audit["score"] <= 85
    assert any("Oversized" in opp["title"] for opp in audit["opportunities"])


def test_scanner_detects_langchain_rag():
    example_dir = Path(__file__).parent.parent / "examples" / "langchain_rag"
    scanner = CodebaseScanner(example_dir)
    res = scanner.scan()

    assert "error" not in res
    detected = res["detected_components"]

    assert "ChromaDB Embedded Vector Store" in detected["vector_databases"]
    assert detected["streaming_ready"] is True
    audit = res["architecture_audit"]
    assert audit["score"] >= 80
