"""Unit tests  TaskClassifier and complexity estimation."""

from __future__ import annotations

from agentlens.routing.classifier import TaskClassifier


def test_task_classifier_code() -> None:
    code_prompt = """
    def fibonacci(n: int) -> int:
        if n <= 1:
            return n
        return fibonacci(n-1) + fibonacci(n-2)
    """
    res = TaskClassifier.classify(code_prompt)
    assert res.task_type == "code"
    assert "code_generation" in res.detected_features
    assert res.complexity_score >= 0.5


def test_task_classifier_rag() -> None:
    rag_prompt = """
    Context: The user account was created in 2024.
    Passage: Subscription tier is Enterprise.
    Based on the following documents, what is the tier?
    """
    res = TaskClassifier.classify(rag_prompt)
    assert res.task_type == "rag"
    assert "rag_grounding" in res.detected_features


def test_task_classifier_reasoning() -> None:
    reasoning_prompt = """
    Please solve this step by step and prove why the statement holds:
    If x > 0 and y > 0, prove that (x+y)/2 >= sqrt(xy).
    """
    res = TaskClassifier.classify(reasoning_prompt)
    assert res.task_type == "reasoning"
    assert "multi_step_reasoning" in res.detected_features
    assert res.complexity_score >= 0.5


def test_task_classifier_general_simple() -> None:
    simple_prompt = "Hello, what is the capital of France?"
    res = TaskClassifier.classify(simple_prompt)
    assert res.task_type == "general"
    assert res.complexity_score <= 0.4
