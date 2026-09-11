"""Versioned M10 policy and report value objects."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

from agentlens.domain import JSONValue
from agentlens.domain.types import validate_json_value

REGRESSION_REPORT_SCHEMA_VERSION = "agentlens-regression-report-v1"
REGRESSION_POLICY_SCHEMA_VERSION = "agentlens-regression-policy-v1"
COMPARISON_ENGINE_VERSION = "1.0.0"


class RegressionRunStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    WAITING_FOR_EVALUATIONS = "waiting_for_evaluations"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class MetricClassification(StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    INSUFFICIENT_DATA = "insufficient_data"
    INCOMPATIBLE = "incompatible"
    INFORMATIONAL = "informational"


class CandidateLimitStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    SATISFIED = "satisfied"
    VIOLATED = "violated"


def _finite_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    if number < 0:
        raise ValueError(f"{field_name} must not be negative")
    return number


@dataclass(frozen=True, slots=True)
class MetricRule:
    rule_id: str
    metric_id: str
    direction: MetricDirection | None = None
    absolute_tolerance: float | None = None
    relative_tolerance: float | None = None
    candidate_minimum: float | None = None
    candidate_maximum: float | None = None
    minimum_samples: int = 1
    required: bool = False
    informational: bool = False
    severity: str = "warning"

    def __post_init__(self) -> None:
        if not self.rule_id or len(self.rule_id) > 128:
            raise ValueError("rule_id must be non-empty and bounded")
        if not self.metric_id or len(self.metric_id) > 255:
            raise ValueError("metric_id must be non-empty and bounded")
        direction = self.direction
        if direction is not None and not isinstance(direction, MetricDirection):
            try:
                direction = MetricDirection(str(direction))
            except ValueError:
                raise ValueError("direction is invalid") from None
            object.__setattr__(self, "direction", direction)
        if self.informational and direction is not None:
            raise ValueError("informational rules cannot declare a direction")
        if not self.informational and direction is None:
            raise ValueError("classified rules require a direction")
        for name in (
            "absolute_tolerance",
            "relative_tolerance",
            "candidate_minimum",
            "candidate_maximum",
        ):
            object.__setattr__(self, name, _finite_number(getattr(self, name), name))
        if self.candidate_minimum is not None and self.candidate_maximum is not None:
            if self.candidate_minimum > self.candidate_maximum:
                raise ValueError("candidate_minimum must not exceed candidate_maximum")
        if not isinstance(self.minimum_samples, int) or isinstance(self.minimum_samples, bool):
            raise ValueError("minimum_samples must be an integer")
        if self.minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")
        if self.severity not in {"info", "warning", "critical"}:
            raise ValueError("severity is invalid")

    @classmethod
    def from_dict(cls, value: object) -> MetricRule:
        if not isinstance(value, dict):
            raise ValueError("rule must be an object")
        direction_value = value.get("direction")
        direction = MetricDirection(str(direction_value)) if direction_value is not None else None
        return cls(
            rule_id=str(value.get("rule_id", "")),
            metric_id=str(value.get("metric_id", "")),
            direction=direction,
            absolute_tolerance=value.get("absolute_tolerance"),
            relative_tolerance=value.get("relative_tolerance"),
            candidate_minimum=value.get("candidate_minimum"),
            candidate_maximum=value.get("candidate_maximum"),
            minimum_samples=value.get("minimum_samples", 1),
            required=bool(value.get("required", False)),
            informational=bool(value.get("informational", False)),
            severity=str(value.get("severity", "warning")),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        body: dict[str, JSONValue] = {
            "rule_id": self.rule_id,
            "metric_id": self.metric_id,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "candidate_minimum": self.candidate_minimum,
            "candidate_maximum": self.candidate_maximum,
            "minimum_samples": self.minimum_samples,
            "required": self.required,
            "informational": self.informational,
            "severity": self.severity,
        }
        if self.direction is not None:
            body["direction"] = self.direction.value
        return body


@dataclass(frozen=True, slots=True)
class RegressionPolicy:
    policy_id: UUID = field(default_factory=uuid4)
    project_id: str = ""
    name: str = ""
    description: str = ""
    version: int = 1
    rules: tuple[MetricRule, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = REGRESSION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REGRESSION_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported regression policy schema")
        if not self.project_id or not self.name or len(self.name) > 255:
            raise ValueError("policy project_id and name are required")
        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("policy version must be positive")
        rules = tuple(self.rules)
        if not rules:
            raise ValueError("policy requires at least one rule")
        if any(not isinstance(rule, MetricRule) for rule in rules):
            raise ValueError("policy rules are invalid")
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ValueError("policy rule IDs must be unique")
        validate_json_value(self.description, "policy.description")
        object.__setattr__(self, "rules", rules)
        created = self.created_at
        if created.tzinfo is None or created.utcoffset() is None:
            created = created.replace(tzinfo=UTC)
        object.__setattr__(self, "created_at", created.astimezone(UTC))

    @classmethod
    def from_dict(
        cls,
        value: object,
        *,
        policy_id: UUID | None = None,
        project_id: str = "",
        name: str = "",
        description: str = "",
        version: int = 1,
    ) -> RegressionPolicy:
        if not isinstance(value, dict):
            raise ValueError("policy must be an object")
        if value.get("schema") not in {None, REGRESSION_POLICY_SCHEMA_VERSION}:
            raise ValueError("unsupported regression policy schema")
        raw_rules = value.get("rules")
        if not isinstance(raw_rules, list):
            raise ValueError("policy.rules must be an array")
        return cls(
            policy_id=policy_id or uuid4(),
            project_id=project_id,
            name=name,
            description=description,
            version=version,
            rules=tuple(MetricRule.from_dict(item) for item in raw_rules),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema": self.schema_version,
            "policy_id": str(self.policy_id),
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "rules": cast(JSONValue, [rule.to_dict() for rule in self.rules]),
            "created_at": self.created_at.isoformat(),
        }


def numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


__all__ = [
    "COMPARISON_ENGINE_VERSION",
    "CandidateLimitStatus",
    "MetricClassification",
    "MetricDirection",
    "MetricRule",
    "RegressionPolicy",
    "RegressionRunStatus",
    "REGRESSION_POLICY_SCHEMA_VERSION",
    "REGRESSION_REPORT_SCHEMA_VERSION",
    "numeric",
]
