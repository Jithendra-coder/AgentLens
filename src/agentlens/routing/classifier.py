"""Task classification and prompt complexity estimation ."""

from __future__ import annotations

import re

from agentlens.routing.models import TaskComplexity

CODE_PATTERNS = [
    r"\bdef\s+\w+",
    r"\bclass\s+\w+",
    r"\bfunction\s+\w+",
    r"\bimport\s+\w+",
    r"```",
    r"\bSELECT\b.*\bFROM\b",
    r"\{\s*\"[\w\-_]+\"\s*:",
]

REASONING_PATTERNS = [
    r"\bstep\s+by\s+step\b",
    r"\bprove\b",
    r"\bderive\b",
    r"\bcalculate\b",
    r"\banalyze\s+the\s+root\s+cause\b",
    r"\bcompare\s+and\s+contrast\b",
    r"\bchain\s+of\s+thought\b",
]

RAG_PATTERNS = [
    r"\bcontext\s*:",
    r"\bpassage\s*:",
    r"\[doc_\d+\]",
    r"\bsource\s*:",
    r"\bbased\s+on\s+the\s+following\s+documents\b",
]

EXTRACTION_PATTERNS = [
    r"\bextract\b",
    r"\bjson\s+schema\b",
    r"\boutput\s+in\s+json\b",
    r"\bparse\s+the\s+entities\b",
]


class TaskClassifier:
    """Classifies prompt task type and estimates reasoning complexity."""

    @staticmethod
    def classify(prompt: str) -> TaskComplexity:
        text_lower = prompt.lower()
        features: list[str] = []

        is_code = any(re.search(pat, prompt, re.IGNORECASE) for pat in CODE_PATTERNS)
        is_rag = any(re.search(pat, text_lower) for pat in RAG_PATTERNS)
        is_extraction = any(re.search(pat, text_lower) for pat in EXTRACTION_PATTERNS)
        is_reasoning = any(re.search(pat, text_lower) for pat in REASONING_PATTERNS)

        complexity = 0.2  # base score
        word_count = len(prompt.split())

        if word_count > 1000:
            complexity += 0.4
            features.append("long_context")
        elif word_count > 300:
            complexity += 0.2
            features.append("medium_context")

        if is_code:
            complexity += 0.3
            features.append("code_generation")
        if is_reasoning:
            complexity += 0.3
            features.append("multi_step_reasoning")
        if is_rag:
            complexity += 0.15
            features.append("rag_grounding")
        if is_extraction:
            complexity += 0.1
            features.append("structured_extraction")

        # Determine dominant task type
        if is_code:
            task_type = "code"
        elif is_reasoning:
            task_type = "reasoning"
        elif is_rag:
            task_type = "rag"
        elif is_extraction:
            task_type = "extraction"
        else:
            task_type = "general"

        bounded_complexity = min(1.0, round(complexity, 2))

        return TaskComplexity(
            task_type=task_type,
            complexity_score=bounded_complexity,
            detected_features=tuple(features),
        )
