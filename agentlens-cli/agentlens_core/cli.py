"""AgentLens Standalone CLI - Observability, Performance Audit & Universal Scanner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from agentlens_core.db import StorageManager
from agentlens_core.probe import probe_http_endpoint, probe_python_script
from agentlens_core.runner import MODEL_PROFILES, run_pipeline
from agentlens_core.scanner import CodebaseScanner


def cmd_run(args: argparse.Namespace) -> int:
    """Execute RAG pipeline diagnostic with selected model."""
    interactive = not args.non_interactive and (args.query is None and args.scenario == "normal")
    return run_pipeline(
        query=args.query,
        scenario=args.scenario,
        domain=args.domain,
        model=args.model,
        interactive=interactive,
    )


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan any directory on the PC for RAG architecture and best practices."""
    target_path = Path(args.path).resolve()
    print("\n" + "=" * 72)
    print(f"  AGENTLENS CODEBASE SCANNER - RAG ARCHITECTURE AUDIT")
    print("=" * 72)
    print(f"  Target Directory: {target_path}")
    print("-" * 72)

    scanner = CodebaseScanner(target_path)
    result = scanner.scan()

    if "error" in result:
        print(f"\n[ERROR] {result['error']}\n")
        return 1

    print(f"  Files Scanned   : {result['files_scanned']}")
    detected = result["detected_components"]
    vbs = ", ".join(detected["vector_databases"]) if detected["vector_databases"] else "None (In-memory or custom)"
    embs = ", ".join(detected["embedding_models"]) if detected["embedding_models"] else "Custom / Standard"
    llms = ", ".join(detected["llm_generators"]) if detected["llm_generators"] else "Standard API"

    print(f"  Vector Databases: {vbs}")
    print(f"  Embedding Models: {embs}")
    print(f"  LLM Generators  : {llms}")
    print(f"  Reranker Found  : {'Yes' if detected['reranker_found'] else 'No'}")
    print(f"  Streaming Ready : {'Yes (SSE / Generator)' if detected['streaming_ready'] else 'No (Buffering full response)'}")
    print(f"  Prompt Caching  : {'Detected' if detected['prompt_caching'] else 'Not configured'}")

    audit = result["architecture_audit"]
    print("\n" + "=" * 72)
    print(f"  STATIC LIGHTHOUSE ARCHITECTURE GRADE:  {audit['grade']}  ({audit['score']}/100)")
    print("=" * 72)

    if audit["opportunities"]:
        print("  TOP ARCHITECTURE RECOMMENDATIONS:")
        for idx, opp in enumerate(audit["opportunities"], 1):
            print(f"\n  [{idx}] {opp['title']} (Impact: {opp['impact']} | {opp['category']})")
            print(f"      -> {opp['recommendation']}")
    else:
        print("  All architecture best practices (chunk size, streaming, reranking) are satisfied!")

    print("\n" + "=" * 72 + "\n")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Probe an external HTTP endpoint or Python script."""
    print("\n" + "=" * 72)
    print(f"  AGENTLENS APPLICATION PROBE")
    print("=" * 72)

    if args.url:
        print(f"  Probing HTTP Endpoint: {args.url}")
        res = probe_http_endpoint(
            url=args.url,
            method=args.method,
            payload_template=args.body,
            query=args.query,
        )
    elif args.script:
        print(f"  Probing Python Script: {args.script} :: {args.func}")
        res = probe_python_script(
            script_path=args.script,
            func_name=args.func,
            query=args.query,
        )
    else:
        print("\n[ERROR] Either --url or --script must be specified.\n")
        return 1

    if "error" in res:
        print(f"\n[ERROR] {res['error']}\n")
        return 1

    audit = res["audit"]
    print("-" * 72)
    print(f"  Execution Latency : {res['total_latency_ms']} ms")
    print(f"  Token Consumption : {res['total_tokens']} tokens (Est. ${res['cost_usd']})")
    print(f"  Lighthouse Grade  : {audit['overall_grade']} ({audit['overall_score']} / 100)")
    print("-" * 72)
    print(f"  Report Generated  : {res['report_html']}")
    print(f"  Unique API Key    : {res['api_key']}")
    print("=" * 72 + "\n")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """List recent evaluations from PostgreSQL or SQLite."""
    db = StorageManager()
    reports = db.list_reports(limit=args.limit)

    storage_type = "PostgreSQL" if db.use_postgres else "Local SQLite (~/.agentlens/agentlens.db)"
    print("\n" + "=" * 72)
    print(f"  AGENTLENS EVALUATION HISTORY ({storage_type})")
    print("=" * 72)

    if not reports:
        print("  No previous evaluation records found.")
        print("  Run 'agentlens run' to evaluate a pipeline.\n")
        return 0

    print(f"{'API Key':<26} {'Score':<8} {'Latency':<10} {'Cost':<10} {'Query'}")
    print("-" * 72)
    for r in reports:
        summ = r.get("summary", {})
        sc = summ.get("overall_score", "-")
        gr = summ.get("overall_grade", "-")
        q = (r.get("query") or "")[:28]
        lat = f"{round(r.get('total_latency_ms', 0))}ms"
        cost = f"${r.get('cost_usd', 0.0):.4f}"
        print(f"{r['api_key']:<26} {gr} ({sc})   {lat:<10} {cost:<10} {q}")
    print("=" * 72 + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build root CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentlens",
        description="AgentLens - Observability, Performance Audit & Universal Scanner for RAG",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. run command
    p_run = subparsers.add_parser("run", help="Run diagnostic RAG pipeline and Lighthouse audit")
    p_run.add_argument("--query", "-q", help="Test prompt/query")
    p_run.add_argument(
        "--scenario",
        "-s",
        choices=["normal", "slow_rerank", "weak_retrieval"],
        default="normal",
        help="Retrieval latency/grounding profile",
    )
    p_run.add_argument(
        "--domain",
        "-d",
        default="Enterprise Billing & Legal Terms v2.4",
        help="Documentation knowledge domain",
    )
    p_run.add_argument(
        "--model",
        "-m",
        choices=list(MODEL_PROFILES.keys()),
        default="claude-3-5-sonnet",
        help="Target LLM generation model (default: claude-3-5-sonnet)",
    )
    p_run.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without interactive CLI prompts",
    )
    p_run.set_defaults(handler=cmd_run)

    # 2. scan command
    p_scan = subparsers.add_parser("scan", help="Scan any project directory for RAG architecture")
    p_scan.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to external project directory (default: current directory)",
    )
    p_scan.set_defaults(handler=cmd_scan)

    # 3. probe command
    p_probe = subparsers.add_parser("probe", help="Live probe an external HTTP endpoint or Python script")
    p_probe.add_argument("--url", help="HTTP endpoint URL (e.g. http://localhost:8000/query)")
    p_probe.add_argument("--method", default="POST", help="HTTP method (default: POST)")
    p_probe.add_argument("--body", help="JSON payload template (use {{query}} placeholder)")
    p_probe.add_argument("--script", help="Path to external Python script (e.g. ./app.py)")
    p_probe.add_argument("--func", default="query_rag", help="Function name in script (default: query_rag)")
    p_probe.add_argument("--query", "-q", default="Enterprise SLA latency guarantees", help="Test query")
    p_probe.set_defaults(handler=cmd_probe)

    # 4. history command
    p_hist = subparsers.add_parser("history", help="List recent evaluations saved in PostgreSQL/SQLite")
    p_hist.add_argument("--limit", "-n", type=int, default=10, help="Number of records to show")
    p_hist.set_defaults(handler=cmd_history)

    return parser


def main() -> None:
    """CLI Entrypoint."""
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "handler"):
        sys.exit(args.handler(args))
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
