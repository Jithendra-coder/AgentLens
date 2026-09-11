"""Immutable quality-gate policy and decision vocabulary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

from agentlens.domain import JSONValue
from agentlens.domain.types import validate_json_value
from agentlens.evaluation.results import canonical_json_fingerprint
from agentlens.regression.models import CandidateLimitStatus, MetricClassification

GATE_POLICY_SCHEMA_VERSION = "agentlens-quality-gate-policy-v1"
GATE_DECISION_SCHEMA_VERSION = "agentlens-quality-gate-decision-v1"
QUALITY_GATE_ENGINE_VERSION = "1.0.0"


class GateStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"
    ERROR = "error"


class GateRuleStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"


class GateSourceType(StrEnum):
    METRIC_CLASSIFICATION = "metric_classification"
    CANDIDATE_LIMIT = "candidate_limit"
    REGRESSION_COUNT = "regression_count"
    REQUIRED_METRIC_AVAILABILITY = "required_metric_availability"
    REPLAY_REPRODUCIBILITY = "replay_reproducibility"
    EXECUTION_FAILURE = "execution_failure"


class EvidenceHandling(StrEnum):
    FAIL = "fail"
    INDETERMINATE = "indeterminate"
    IGNORE = "ignore"


_CLASSIFICATIONS = {item.value for item in MetricClassification}
_LIMIT_STATUSES = {item.value for item in CandidateLimitStatus}
_REPLAY_MODES = {"exact", "controlled", "best_effort"}


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "rule"


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    values = [value] if isinstance(value, str) else value
    if (
        not isinstance(values, (list, tuple))
        or not values
        or any(not isinstance(item, str) or not item.strip() for item in values)
    ):
        raise ValueError(f"{field_name} must contain non-empty strings")
    return tuple(str(item).strip() for item in values)


def _replay_modes(value: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict) or not value:
        raise ValueError("require_replay_modes must be a non-empty object")
    result: dict[str, tuple[str, ...]] = {}
    for participant, modes in value.items():
        if participant not in {"baseline", "candidate"}:
            raise ValueError("replay requirements may target baseline or candidate")
        normalized = _strings(modes, f"require_replay_modes.{participant}")
        if any(mode not in _REPLAY_MODES for mode in normalized):
            raise ValueError("replay mode is invalid")
        result[participant] = normalized
    return result


@dataclass(frozen=True, slots=True)
class GateRule:
    gate_rule_id: str
    name: str
    source_type: GateSourceType
    metric_id: str | None = None
    classifications: tuple[str, ...] = ()
    candidate_limit_status: str | None = None
    metric_ids: tuple[str, ...] = ()
    maximum_regressions: int | None = None
    replay_modes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    require_candidate_limit_ok: bool = False
    blocking: bool = True
    on_missing: EvidenceHandling = EvidenceHandling.INDETERMINATE
    on_incompatible: EvidenceHandling = EvidenceHandling.INDETERMINATE
    description: str = ""

    def __post_init__(self) -> None:
        if not self.gate_rule_id or len(self.gate_rule_id) > 128:
            raise ValueError("gate_rule_id must be non-empty and bounded")
        if not self.name or len(self.name) > 255:
            raise ValueError("rule name must be non-empty and bounded")
        source = self.source_type
        if not isinstance(source, GateSourceType):
            try:
                source = GateSourceType(str(source))
            except ValueError:
                raise ValueError("rule source_type is invalid") from None
            object.__setattr__(self, "source_type", source)
        for field_name in ("on_missing", "on_incompatible"):
            value = getattr(self, field_name)
            if not isinstance(value, EvidenceHandling):
                try:
                    value = EvidenceHandling(str(value))
                except ValueError:
                    raise ValueError(f"{field_name} is invalid") from None
                object.__setattr__(self, field_name, value)
        if not isinstance(self.blocking, bool):
            raise ValueError("blocking must be boolean")
        if not isinstance(self.require_candidate_limit_ok, bool):
            raise ValueError("require_candidate_limit_ok must be boolean")
        if self.metric_id is not None and (
            not isinstance(self.metric_id, str) or not self.metric_id.strip()
        ):
            raise ValueError("metric_id is invalid")
        if any(item not in _CLASSIFICATIONS for item in self.classifications):
            raise ValueError("classification is invalid")
        if (
            self.candidate_limit_status is not None
            and self.candidate_limit_status not in _LIMIT_STATUSES
        ):
            raise ValueError("candidate_limit_status is invalid")
        if self.maximum_regressions is not None and (
            not isinstance(self.maximum_regressions, int)
            or isinstance(self.maximum_regressions, bool)
            or self.maximum_regressions < 0
        ):
            raise ValueError("maximum_regressions must be a non-negative integer")
        modes = _replay_modes(self.replay_modes) if self.replay_modes else {}
        object.__setattr__(self, "replay_modes", modes)
        object.__setattr__(self, "classifications", tuple(self.classifications))
        object.__setattr__(self, "metric_ids", tuple(self.metric_ids))
        validate_json_value(self.description, "rule.description")
        if (
            source
            in {
                GateSourceType.METRIC_CLASSIFICATION,
                GateSourceType.CANDIDATE_LIMIT,
                GateSourceType.REQUIRED_METRIC_AVAILABILITY,
            }
            and not self.metric_id
        ):
            raise ValueError("metric_id is required for this rule source")
        if source is GateSourceType.REGRESSION_COUNT and (
            self.maximum_regressions is None or not self.metric_ids
        ):
            raise ValueError("regression_count requires metric_ids and maximum_regressions")
        if source is GateSourceType.REPLAY_REPRODUCIBILITY and not self.replay_modes:
            raise ValueError("replay_reproducibility requires replay modes")

    @classmethod
    def from_dict(cls, value: object, *, default_id: str | None = None) -> GateRule:
        if not isinstance(value, dict):
            raise ValueError("gate rule must be an object")
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("rule name is required")
        raw_source = value.get("source_type", value.get("source", "metric_classification"))
        try:
            source = GateSourceType(str(raw_source))
        except ValueError:
            raise ValueError("rule source is invalid") from None
        metric_id = value.get("metric_id", value.get("metric"))
        block_if = value.get("classification")
        if block_if is None or block_if == []:
            block_if = value.get("block_if")
        classifications: tuple[str, ...] = ()
        limit_status = value.get("candidate_limit_status")
        if source is GateSourceType.METRIC_CLASSIFICATION:
            classifications = _strings(
                block_if if block_if is not None else "regressed", "block_if"
            )
        elif source is GateSourceType.CANDIDATE_LIMIT:
            limit_status = block_if if block_if is not None else (limit_status or "violated")
            if not isinstance(limit_status, str):
                raise ValueError("candidate limit block_if is invalid")
        metric_ids_value = value.get("metric_ids", value.get("metrics", ()))
        metric_ids: tuple[str, ...] = ()
        if metric_ids_value:
            metric_ids = _strings(metric_ids_value, "metric_ids")
        replay_value = value.get("require_replay_modes", value.get("required_replay_modes", {}))
        replay_modes = _replay_modes(replay_value) if replay_value else {}
        rule_id = value.get("gate_rule_id", value.get("rule_id", default_id or _slug(name)))
        if not isinstance(rule_id, str):
            raise ValueError("gate_rule_id is invalid")
        classifications_value = tuple(item for item in classifications)
        return cls(
            gate_rule_id=rule_id,
            name=name.strip(),
            source_type=source,
            metric_id=str(metric_id).strip() if metric_id is not None else None,
            classifications=classifications_value,
            candidate_limit_status=limit_status,
            metric_ids=metric_ids,
            maximum_regressions=value.get(
                "maximum_regressions", value.get("maximum_blocking_regressions")
            ),
            replay_modes=replay_modes,
            require_candidate_limit_ok=value.get("require_candidate_limit_ok", False),
            blocking=value.get("blocking", True),
            on_missing=value.get("on_missing", EvidenceHandling.INDETERMINATE.value),
            on_incompatible=value.get("on_incompatible", EvidenceHandling.INDETERMINATE.value),
            description=str(value.get("description", "")),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "gate_rule_id": self.gate_rule_id,
            "name": self.name,
            "source_type": self.source_type.value,
            "metric_id": self.metric_id,
            "classification": list(self.classifications),
            "candidate_limit_status": self.candidate_limit_status,
            "metric_ids": list(self.metric_ids),
            "maximum_regressions": self.maximum_regressions,
            "require_replay_modes": {key: list(value) for key, value in self.replay_modes.items()},
            "require_candidate_limit_ok": self.require_candidate_limit_ok,
            "blocking": self.blocking,
            "on_missing": self.on_missing.value,
            "on_incompatible": self.on_incompatible.value,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class QualityGatePolicy:
    gate_policy_id: UUID = field(default_factory=uuid4)
    project_id: str = ""
    name: str = ""
    version: int = 1
    description: str = ""
    rules: tuple[GateRule, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = GATE_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GATE_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported quality gate policy schema")
        if not self.project_id or not self.name or len(self.name) > 255:
            raise ValueError("policy project_id and name are required")
        if not isinstance(self.version, int) or self.version < 1:
            raise ValueError("policy version must be positive")
        rules = tuple(self.rules)
        if not rules or any(not isinstance(rule, GateRule) for rule in rules):
            raise ValueError("policy requires valid rules")
        if len({rule.gate_rule_id for rule in rules}) != len(rules):
            raise ValueError("gate rule IDs must be unique")
        if len({rule.name for rule in rules}) != len(rules):
            raise ValueError("gate rule names must be unique")
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
        gate_policy_id: UUID | None = None,
        project_id: str = "",
        name: str = "",
        description: str = "",
        version: int = 1,
        created_at: datetime | None = None,
    ) -> QualityGatePolicy:
        if not isinstance(value, dict):
            raise ValueError("quality gate policy must be an object")
        schema = value.get("schema", value.get("schema_version"))
        if schema not in {None, GATE_POLICY_SCHEMA_VERSION}:
            raise ValueError("unsupported quality gate policy schema")
        raw_rules = value.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ValueError("policy.rules must be an array")
        rules = [GateRule.from_dict(item) for item in raw_rules]
        required_metrics = value.get("required_metrics", [])
        if required_metrics:
            for metric in _strings(required_metrics, "required_metrics"):
                rules.append(
                    GateRule(
                        gate_rule_id=_slug(f"required-{metric}"),
                        name=f"Required metric: {metric}",
                        source_type=GateSourceType.REQUIRED_METRIC_AVAILABILITY,
                        metric_id=metric,
                        blocking=True,
                        on_missing=value.get(
                            "required_metrics_on_missing", EvidenceHandling.INDETERMINATE.value
                        ),
                        on_incompatible=value.get(
                            "required_metrics_on_incompatible",
                            EvidenceHandling.INDETERMINATE.value,
                        ),
                    )
                )
        return cls(
            gate_policy_id=gate_policy_id or uuid4(),
            project_id=project_id,
            name=name or str(value.get("name", "")),
            description=description or str(value.get("description", "")),
            version=version,
            rules=tuple(rules),
            created_at=created_at or datetime.now(UTC),
        )

    def content_fingerprint(self) -> str:
        return canonical_json_fingerprint(
            {
                "schema": self.schema_version,
                "name": self.name,
                "description": self.description,
                "version": self.version,
                "rules": [rule.to_dict() for rule in self.rules],
            }
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema": self.schema_version,
            "gate_policy_id": str(self.gate_policy_id),
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "rules": cast(JSONValue, [rule.to_dict() for rule in self.rules]),
            "created_at": self.created_at.isoformat(),
            "content_fingerprint": self.content_fingerprint(),
        }


def normalize_policy(raw_rules: object, *, required_metrics: object = None) -> tuple[GateRule, ...]:
    """Validate and normalize API rule data without executing policy code."""

    body: dict[str, object] = {"rules": raw_rules}
    if required_metrics is not None:
        body["required_metrics"] = required_metrics
    policy = QualityGatePolicy.from_dict(
        body, project_id="validation", name="validation", description="validation"
    )
    return policy.rules


__all__ = [
    "EvidenceHandling",
    "GATE_DECISION_SCHEMA_VERSION",
    "GATE_POLICY_SCHEMA_VERSION",
    "GateRule",
    "GateRuleStatus",
    "GateSourceType",
    "GateStatus",
    "QualityGatePolicy",
    "QUALITY_GATE_ENGINE_VERSION",
    "normalize_policy",
]
