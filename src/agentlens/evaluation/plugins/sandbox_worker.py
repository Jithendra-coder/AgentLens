"""Container-only worker for evaluating custom evaluator source."""

from __future__ import annotations

import datetime
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class CustomEvaluationOutput:
    def __init__(
        self,
        score: float,
        passed: bool,
        findings: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.score = float(score)
        self.passed = bool(passed)
        self.findings = list(findings or [])
        self.details = dict(details or {})
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("Custom evaluator score must be between 0 and 1")


class CustomEvaluator:
    def evaluate(self, context: Any, parameters: dict[str, Any]) -> Any:
        raise NotImplementedError


def custom_evaluator(*_args: Any, **_kwargs: Any):
    if _args and callable(_args[0]) and len(_args) == 1 and not _kwargs:
        _args[0]._is_agentlens_evaluator = True
        return _args[0]

    def decorate(fn: Any) -> Any:
        fn._is_agentlens_evaluator = True
        return fn

    return decorate


def as_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: as_namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [as_namespace(item) for item in value]
    return value


SAFE_BUILTINS: dict[str, Any] = {
    "__build_class__": __build_class__,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "AttributeError": AttributeError,
}


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "__name__": "<custom_evaluator>",
        "__doc__": None,
        "math": math,
        "json": json,
        "re": re,
        "datetime": datetime,
        "CustomEvaluationOutput": CustomEvaluationOutput,
        "EvaluatorContext": SimpleNamespace,
        "SpanContextView": SimpleNamespace,
        "CustomEvaluator": CustomEvaluator,
        "custom_evaluator": custom_evaluator,
    }
    try:
        exec(compile(payload["code_body"], "<custom_evaluator>", "exec"), scope)
    except SyntaxError as exc:
        return {
            "score": 0.0,
            "passed": False,
            "findings": [f"CompilationError: {exc}"[:2048]],
            "details": {"error_type": "compilation_error", "message": str(exc)},
        }
    try:
        entrypoint = scope.get("evaluate")
        if not callable(entrypoint):
            entrypoint = next(
                (
                    value
                    for value in scope.values()
                    if callable(value) and getattr(value, "_is_agentlens_evaluator", False)
                ),
                None,
            )
        if entrypoint is None:
            evaluator_type = next(
                (
                    value
                    for value in scope.values()
                    if isinstance(value, type)
                    and issubclass(value, CustomEvaluator)
                    and value is not CustomEvaluator
                ),
                None,
            )
            if evaluator_type is not None:
                entrypoint = evaluator_type().evaluate
        if entrypoint is None:
            raise ValueError("No valid evaluator entrypoint found")
        raw = entrypoint(as_namespace(payload["context"]), payload.get("parameters") or {})
        if isinstance(raw, CustomEvaluationOutput):
            result = {
                "score": raw.score,
                "passed": raw.passed,
                "findings": raw.findings,
                "details": raw.details,
            }
        elif isinstance(raw, dict):
            score = float(raw.get("score", 0.0))
            result = {
                "score": min(1.0, max(0.0, score)),
                "passed": bool(raw.get("passed", score >= 0.8)),
                "findings": list(raw.get("findings", [])),
                "details": dict(raw.get("details", {})),
            }
        elif isinstance(raw, (tuple, list)):
            score = float(raw[0]) if raw else 0.0
            result = {
                "score": min(1.0, max(0.0, score)),
                "passed": bool(raw[1]) if len(raw) > 1 else score >= 0.8,
                "findings": list(raw[2]) if len(raw) > 2 else [],
                "details": {},
            }
        else:
            raise TypeError(f"Unsupported evaluator return type: {type(raw).__name__}")
        result["findings"] = [str(item)[:2048] for item in result["findings"][:50]]
        result["details"] = result["details"]
        return result
    except Exception as exc:
        return {
            "score": 0.0,
            "passed": False,
            "findings": [f"RuntimeExecutionError: {exc}"[:2048]],
            "details": {"error_type": "runtime_error", "message": str(exc)},
        }


if __name__ == "__main__":
    request = json.loads(Path("/request.json").read_text(encoding="utf-8"))
    response = evaluate(request)
    output = json.dumps(response, ensure_ascii=False, default=str)
    if len(output.encode("utf-8")) > 64_000:
        response = {
            "score": 0.0,
            "passed": False,
            "findings": ["Evaluator output exceeded the 64 KB limit."],
            "details": {"error_type": "output_too_large"},
        }
        output = json.dumps(response)
    Path("/result.json").write_text(output, encoding="utf-8")
