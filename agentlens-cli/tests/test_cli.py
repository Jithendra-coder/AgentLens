"""Tests for CLI arguments and execution."""

import subprocess
import sys
from pathlib import Path


def test_cli_parser_help():
    cli_path = Path(__file__).parent.parent / "agentlens_core" / "cli.py"
    res = subprocess.run([sys.executable, str(cli_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "agentlens" in res.stdout
    assert "run" in res.stdout
    assert "scan" in res.stdout
    assert "probe" in res.stdout
    assert "history" in res.stdout


def test_cli_scan_command():
    cli_path = Path(__file__).parent.parent / "agentlens_core" / "cli.py"
    example_path = Path(__file__).parent.parent / "examples" / "simple_rag"
    res = subprocess.run([sys.executable, str(cli_path), "scan", str(example_path)], capture_output=True, text=True)
    assert res.returncode == 0
    assert "STATIC LIGHTHOUSE ARCHITECTURE GRADE" in res.stdout
    assert "Pinecone" in res.stdout


def test_cli_run_gpt4o():
    cli_path = Path(__file__).parent.parent / "agentlens_core" / "cli.py"
    res = subprocess.run([sys.executable, str(cli_path), "run", "-m", "gpt-4o", "-q", "Test vector search", "--non-interactive"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "LIGHTHOUSE FOR RAG" in res.stdout
    assert "UNIQUE RUN API KEY" in res.stdout
