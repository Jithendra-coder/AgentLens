"""Provider-neutral M9 dataset and replay value objects."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

from agentlens.domain import JSONValue, Trace
from agentlens.domain.types import validate_json_value


class DatasetVersionStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"


class ReplayMode(StrEnum):
    EXACT = "exact"
    CONTROLLED = "controlled"
    BEST_EFFORT = "best_effort"


class ReplayRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"


class ReproducibilityStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


def _mapping(value: object, field_name: str) -> dict[str, JSONValue]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} must be a JSON object")
    normalized = cast(dict[str, JSONValue], dict(value))
    validate_json_value(normalized, field_name)
    return normalized


def _json(value: object, field_name: str) -> JSONValue:
    validate_json_value(value, field_name)
    return cast(JSONValue, value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DatasetCase:
    case_id: UUID = field(default_factory=uuid4)
    name: str = ""
    input: JSONValue = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
    source: Mapping[str, JSONValue] = field(default_factory=dict)
    ground_truth: JSONValue | None = None
    tags: tuple[str, ...] = ()
    position: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, UUID):
            object.__setattr__(self, "case_id", UUID(str(self.case_id)))
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 255:
            raise ValueError("case name must be a non-empty string of at most 255 characters")
        if not isinstance(self.position, int) or self.position < 0:
            raise ValueError("case position must be a non-negative integer")
        object.__setattr__(self, "input", _json(self.input, "input"))
        object.__setattr__(self, "metadata", _mapping(self.metadata, "metadata"))
        object.__setattr__(self, "source", _mapping(self.source, "source"))
        if self.ground_truth is not None:
            object.__setattr__(self, "ground_truth", _json(self.ground_truth, "ground_truth"))
        if not isinstance(self.tags, (tuple, list)) or any(
            not isinstance(tag, str) or not tag or len(tag) > 100 for tag in self.tags
        ):
            raise ValueError("tags must contain bounded non-empty strings")
        object.__setattr__(self, "tags", tuple(self.tags))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "case_id": str(self.case_id),
            "name": self.name,
            "input": self.input,
            "metadata": dict(self.metadata),
            "source": dict(self.source),
            "ground_truth": self.ground_truth,
            "tags": list(self.tags),
            "position": self.position,
        }


def canonical_case_checksum(cases: tuple[DatasetCase, ...] | list[DatasetCase]) -> str:
    """Hash ordered case identity/content; timestamps are intentionally excluded."""

    ordered = sorted(cases, key=lambda item: item.position)
    if [item.position for item in ordered] != list(range(len(ordered))):
        raise ValueError("case positions must be contiguous and start at zero")
    body = json.dumps(
        [
            {key: value for key, value in item.to_dict().items() if key != "case_id"}
            for item in ordered
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    dataset_version_id: UUID
    dataset_checksum: str
    target_profile_id: str
    target_version: str
    replay_mode: ReplayMode
    reproducibility_status: ReproducibilityStatus
    application: Mapping[str, JSONValue] = field(default_factory=dict)
    prompt: Mapping[str, JSONValue] = field(default_factory=dict)
    model: Mapping[str, JSONValue] = field(default_factory=dict)
    retriever: Mapping[str, JSONValue] = field(default_factory=dict)
    tools: Mapping[str, JSONValue] = field(default_factory=dict)
    environment: Mapping[str, JSONValue] = field(default_factory=dict)
    changed_dimensions: tuple[str, ...] = ()
    unknown_fields: tuple[str, ...] = ()
    best_effort_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_version_id, UUID):
            object.__setattr__(self, "dataset_version_id", UUID(str(self.dataset_version_id)))
        if len(self.dataset_checksum) != 64 or any(
            character not in "0123456789abcdef" for character in self.dataset_checksum.lower()
        ):
            raise ValueError("dataset_checksum must be a SHA-256 hex digest")
        for name in ("application", "prompt", "model", "retriever", "tools", "environment"):
            object.__setattr__(self, name, _mapping(getattr(self, name), name))
        if not isinstance(self.target_profile_id, str) or not self.target_profile_id:
            raise ValueError("target_profile_id is required")
        if not isinstance(self.target_version, str) or not self.target_version:
            raise ValueError("target_version is required")
        if not isinstance(self.changed_dimensions, (tuple, list)) or any(
            not isinstance(item, str) or not item for item in self.changed_dimensions
        ):
            raise ValueError("changed_dimensions must contain strings")
        if not isinstance(self.unknown_fields, (tuple, list)) or any(
            not isinstance(item, str) or not item for item in self.unknown_fields
        ):
            raise ValueError("unknown_fields must contain strings")
        object.__setattr__(self, "changed_dimensions", tuple(self.changed_dimensions))
        object.__setattr__(self, "unknown_fields", tuple(self.unknown_fields))
        object.__setattr__(self, "created_at", _utc(self.created_at))
        self.validate_mode()

    def validate_mode(self) -> None:
        if self.replay_mode is ReplayMode.EXACT and (
            self.reproducibility_status is not ReproducibilityStatus.COMPLETE or self.unknown_fields
        ):
            raise ValueError("exact replay requires complete provenance and no unknown fields")
        if self.replay_mode is ReplayMode.CONTROLLED and not self.changed_dimensions:
            raise ValueError("controlled replay requires changed_dimensions")
        if self.replay_mode is ReplayMode.BEST_EFFORT and not self.best_effort_reason:
            raise ValueError("best_effort replay requires a reason")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "dataset_version_id": str(self.dataset_version_id),
            "dataset_checksum": self.dataset_checksum,
            "target_profile_id": self.target_profile_id,
            "target_version": self.target_version,
            "replay_mode": self.replay_mode.value,
            "reproducibility_status": self.reproducibility_status.value,
            "application": dict(self.application),
            "prompt": dict(self.prompt),
            "model": dict(self.model),
            "retriever": dict(self.retriever),
            "tools": dict(self.tools),
            "environment": dict(self.environment),
            "changed_dimensions": list(self.changed_dimensions),
            "unknown_fields": list(self.unknown_fields),
            "best_effort_reason": self.best_effort_reason,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ReplayTargetResponse:
    output: JSONValue
    trace: Trace | None = None
