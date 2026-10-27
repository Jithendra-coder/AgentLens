"""Run custom evaluators in a resource-limited, network-isolated container."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentlens.evaluation.plugins.models import CustomEvaluationOutput, EvaluatorContext

_IMAGE = "python:3.11-slim"
_OUTPUT_LIMIT = 64_000


def _failure(kind: str, message: str) -> CustomEvaluationOutput:
    return CustomEvaluationOutput(
        score=0.0,
        passed=False,
        findings=[message],
        details={"error_type": kind},
    )


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def _ensure_image() -> bool:
    try:
        inspect = subprocess.run(
            ["docker", "image", "inspect", _IMAGE], capture_output=True, timeout=10, check=False
        )
        if inspect.returncode == 0:
            return True
        return (
            subprocess.run(
                ["docker", "pull", _IMAGE], capture_output=True, timeout=120, check=False
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def execute_custom_evaluator(
    code_body: str,
    context: EvaluatorContext,
    parameters: dict[str, Any] | None = None,
) -> CustomEvaluationOutput:
    """Execute untrusted evaluator code without falling back to host execution."""
    if not _docker_available():
        return _failure(
            "sandbox_unavailable",
            "Custom evaluator execution requires an available Docker daemon.",
        )
    try:
        image_ready = _ensure_image()
    except (OSError, subprocess.TimeoutExpired):
        image_ready = False
    if not image_ready:
        return _failure(
            "sandbox_image_unavailable",
            "The isolated evaluator runtime could not be prepared.",
        )

    payload = json.dumps(
        {"code_body": code_body, "context": asdict(context), "parameters": parameters or {}},
        ensure_ascii=False,
        default=str,
    )
    worker = Path(__file__).with_name("sandbox_worker.py").read_text(encoding="utf-8")
    container_name = f"agentlens-evaluator-{uuid4().hex}"

    try:
        with tempfile.TemporaryDirectory(prefix="agentlens-evaluator-") as temporary_dir:
            request_file = Path(temporary_dir) / "request.json"
            result_file = Path(temporary_dir) / "result.json"
            request_file.write_text(payload, encoding="utf-8")
            result_file.touch()
            os.chmod(temporary_dir, 0o755)
            os.chmod(request_file, 0o644)
            os.chmod(result_file, 0o666)

            created = subprocess.run(
                [
                    "docker",
                    "create",
                    "--name",
                    container_name,
                    "--network=none",
                    "--memory=128m",
                    "--cpus=0.5",
                    "--pids-limit=32",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges:true",
                    "--user=65534:65534",
                    "--log-driver=none",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
                    "--mount",
                    f"type=bind,source={request_file},target=/request.json,readonly",
                    "--mount",
                    f"type=bind,source={result_file},target=/result.json",
                    _IMAGE,
                    "python",
                    "-I",
                    "-c",
                    worker,
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if created.returncode != 0:
                return _failure("sandbox_start_failed", "The isolated evaluator could not start.")

            container_id = created.stdout.strip()
            started = subprocess.run(
                ["docker", "start", container_id], capture_output=True, timeout=10, check=False
            )
            if started.returncode != 0:
                return _failure("sandbox_start_failed", "The isolated evaluator could not start.")

            try:
                waited = subprocess.run(
                    ["docker", "wait", container_id],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["docker", "kill", container_id], capture_output=True, timeout=5, check=False
                )
                return _failure("sandbox_timeout", "Custom evaluator exceeded the 5 second limit.")
            if waited.returncode != 0 or waited.stdout.strip() != "0":
                return _failure("sandbox_execution_failed", "The isolated evaluator failed.")

            if not result_file.is_file() or result_file.stat().st_size == 0:
                return _failure(
                    "sandbox_result_missing", "The isolated evaluator returned no result."
                )
            if result_file.stat().st_size > _OUTPUT_LIMIT:
                return _failure(
                    "sandbox_result_too_large", "Evaluator output exceeded the 64 KB limit."
                )

            result = json.loads(result_file.read_text(encoding="utf-8"))
            return CustomEvaluationOutput(
                score=float(result["score"]),
                passed=bool(result["passed"]),
                findings=[str(item)[:2048] for item in result.get("findings", [])[:50]],
                details=result.get("details", {})
                if isinstance(result.get("details", {}), dict)
                else {},
            )
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return _failure("sandbox_error", "The isolated evaluator could not be completed.")
    finally:
        try:
            subprocess.run(
                ["docker", "rm", "--force", container_name],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
