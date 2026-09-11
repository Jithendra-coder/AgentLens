"""Subprocess contract tests for the M11 CI CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar


class _GateHandler(BaseHTTPRequestHandler):
    status: ClassVar[str] = "passed"

    def do_POST(self) -> None:  # noqa: N802
        response = {
            "decision_id": "decision-1",
            "regression_run_id": "run-1",
            "gate_policy_id": "policy-1",
            "gate_policy_version": 1,
            "status": self.status,
            "blocking_failure_count": 1 if self.status == "failed" else 0,
            "advisory_failure_count": 0,
            "indeterminate_count": 1 if self.status == "indeterminate" else 0,
            "rule_results": [],
        }
        body = json.dumps(response).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def test_cli_exit_codes_and_output_formats() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GateHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        for status, expected in (("passed", 0), ("failed", 1), ("indeterminate", 2)):
            _GateHandler.status = status
            environment = os.environ.copy()
            environment["AGENTLENS_API_URL"] = base
            environment["AGENTLENS_API_KEY"] = "secret-api-key"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentlens.cli",
                    "gate",
                    "evaluate",
                    "--regression-run",
                    "run-1",
                    "--policy",
                    "policy-1",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            assert result.returncode == expected
            assert json.loads(result.stdout)["status"] == status
            assert "secret-api-key" not in result.stdout + result.stderr
        _GateHandler.status = "passed"
        human = subprocess.run(
            [
                sys.executable,
                "-m",
                "agentlens.cli",
                "gate",
                "evaluate",
                "--regression-run",
                "run-1",
                "--policy",
                "policy-1",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "AGENTLENS_API_URL": base, "AGENTLENS_API_KEY": "secret-api-key"},
            check=False,
        )
        assert human.returncode == 0
        assert "AgentLens Quality Gate: PASSED" in human.stdout
    finally:
        server.shutdown()


def test_cli_configuration_and_network_errors_are_exit_three() -> None:
    missing = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentlens.cli",
            "gate",
            "evaluate",
            "--regression-run",
            "run-1",
            "--policy",
            "policy-1",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"AGENTLENS_API_URL", "AGENTLENS_API_KEY"}
        },
        check=False,
    )
    assert missing.returncode == 3
    assert json.loads(missing.stdout)["status"] == "error"
    network = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentlens.cli",
            "gate",
            "evaluate",
            "--regression-run",
            "run-1",
            "--policy",
            "policy-1",
            "--format",
            "json",
            "--timeout",
            "1",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "AGENTLENS_API_URL": "http://127.0.0.1:1",
            "AGENTLENS_API_KEY": "secret-api-key",
        },
        check=False,
    )
    assert network.returncode == 3
    assert "secret-api-key" not in network.stdout + network.stderr
