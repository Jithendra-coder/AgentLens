"""Composite quality metrics and evaluation suite domain models ."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class EvaluatorConfigRef:
    """Reference to an individual evaluator included in an EvaluationSuite."""

    evaluator_name: str
    evaluator_version: str = "1.0.0"
    evaluator_type: str = "deterministic"  # deterministic | semantic
    weight: float = 1.0
    threshold: float = 0.8
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.weight <= 0.0:
            raise ValueError("Evaluator weight must be positive (> 0.0)")
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError("Evaluator threshold must be between 0.0 and 1.0")


@dataclass(frozen=True, slots=True)
class EvaluationSuite:
    """A named, weighted collection of deterministic and semantic evaluators."""

    suite_id: UUID = field(default_factory=uuid4)
    project_id: str = ""
    name: str = ""
    description: str | None = None
    passing_threshold: float = 0.8
    evaluators: tuple[EvaluatorConfigRef, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not (0.0 <= self.passing_threshold <= 1.0):
            raise ValueError("Suite passing_threshold must be between 0.0 and 1.0")


@dataclass(frozen=True, slots=True)
class MetricScore:
    """Individual evaluator outcome contributing to a composite quality result."""

    evaluator_name: str
    evaluator_version: str
    evaluator_type: str
    raw_score: float
    weight: float
    weighted_score: float
    threshold: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompositeEvaluationResult:
    """Deterministic composite score and provenance across all suite evaluators."""

    composite_result_id: UUID = field(default_factory=uuid4)
    suite_id: UUID = field(default_factory=uuid4)
    project_id: str = ""
    trace_id: UUID = field(default_factory=uuid4)
    aggregate_score: float = 0.0
    passed: bool = False
    metric_scores: tuple[MetricScore, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
