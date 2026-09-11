"""Sandboxed execution engine for custom evaluator plugins ."""

from __future__ import annotations

import datetime
import json
import math
import re
from typing import Any

from agentlens.evaluation.plugins.models import (
    CustomEvaluationOutput,
    EvaluatorContext,
    SpanContextView,
)
from agentlens.evaluation.plugins.sdk import CustomEvaluator, custom_evaluator

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


def execute_custom_evaluator(
    code_body: str,
    context: EvaluatorContext,
    parameters: dict[str, Any] | None = None,
) -> CustomEvaluationOutput:
    """Execute user-supplied custom evaluator code within a restricted namespace."""
    params = parameters or {}
    local_scope: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "__name__": "<custom_evaluator>",
        "__doc__": None,
        "math": math,
        "json": json,
        "re": re,
        "datetime": datetime,
        "CustomEvaluationOutput": CustomEvaluationOutput,
        "EvaluatorContext": EvaluatorContext,
        "SpanContextView": SpanContextView,
        "CustomEvaluator": CustomEvaluator,
        "custom_evaluator": custom_evaluator,
    }

    try:
        compiled = compile(code_body, "<custom_evaluator>", "exec")
        exec(compiled, local_scope)  # noqa: S102
    except Exception as exc:
        return CustomEvaluationOutput(
            score=0.0,
            passed=False,
            findings=[f"CompilationError: {exc}"],
            details={"error_type": "compilation_error", "message": str(exc)},
        )

    # 1. Search for function named 'evaluate' or decorated with @custom_evaluator
    entrypoint_fn = None
    if "evaluate" in local_scope and callable(local_scope["evaluate"]):
        entrypoint_fn = local_scope["evaluate"]
    else:
        for val in local_scope.values():
            if callable(val) and getattr(val, "_is_agentlens_evaluator", False):
                entrypoint_fn = val
                break

    # 2. Search for subclass of CustomEvaluator
    if entrypoint_fn is None:
        for val in local_scope.values():
            if (
                isinstance(val, type)
                and issubclass(val, CustomEvaluator)
                and val is not CustomEvaluator
            ):
                instance = val()
                entrypoint_fn = instance.evaluate
                break

    if entrypoint_fn is None:
        return CustomEvaluationOutput(
            score=0.0,
            passed=False,
            findings=["No valid evaluator entrypoint ('evaluate' or CustomEvaluator) found."],
            details={"error_type": "missing_entrypoint"},
        )

    try:
        raw_result = entrypoint_fn(context, params)
        if isinstance(raw_result, CustomEvaluationOutput):
            return raw_result
        if isinstance(raw_result, dict):
            score = float(raw_result.get("score", 0.0))
            passed = bool(raw_result.get("passed", score >= 0.8))
            findings = list(raw_result.get("findings", []))
            details = dict(raw_result.get("details", {}))
            return CustomEvaluationOutput(
                score=min(1.0, max(0.0, score)),
                passed=passed,
                findings=findings,
                details=details,
            )
        if isinstance(raw_result, (tuple, list)):
            score = float(raw_result[0]) if len(raw_result) > 0 else 0.0
            passed = bool(raw_result[1]) if len(raw_result) > 1 else (score >= 0.8)
            findings = list(raw_result[2]) if len(raw_result) > 2 else []
            return CustomEvaluationOutput(
                score=min(1.0, max(0.0, score)),
                passed=passed,
                findings=findings,
            )
        ret_type = type(raw_result).__name__
        return CustomEvaluationOutput(
            score=0.0,
            passed=False,
            findings=[f"InvalidReturnType: unsupported type {ret_type}"],
        )
    except Exception as exc:
        return CustomEvaluationOutput(
            score=0.0,
            passed=False,
            findings=[f"RuntimeExecutionError: {exc}"],
            details={"error_type": "runtime_error", "message": str(exc)},
        )
