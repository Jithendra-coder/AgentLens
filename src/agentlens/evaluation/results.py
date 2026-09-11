"""Immutable, provider-independent evaluation result contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

from agentlens.domain.types import JSONValue, freeze_payload, thaw_payload
from agentlens.exceptions import UnsupportedSchemaError, ValidationError

RESULT_SCHEMA_VERSION = "agentlens-evaluation-result-v1"


class ResultStatus(StrEnum):
    COMPLETED = "completed"
    NOT_APPLICABLE = "not_applicable"
    INVALID_INPUT = "invalid_input"


class EvaluationMode(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"
    HYBRID = "hybrid"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def canonical_json_fingerprint(value: object) -> str:
    frozen = freeze_payload(value, "fingerprint")
    payload = thaw_payload(frozen)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("created_at must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class JudgeInvocation:
    """Safe provenance for one structured semantic-judge call."""

    invocation_id: UUID
    judge_profile: str
    provider: str
    model: str
    adapter_version: str
    prompt_version: str
    parameters: Mapping[str, JSONValue]
    request_fingerprint: str
    response_fingerprint: str
    started_at: datetime
    ended_at: datetime
    status: str = "completed"
    token_usage: Mapping[str, JSONValue] | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("judge_profile", self.judge_profile),
            ("provider", self.provider),
            ("model", self.model),
            ("adapter_version", self.adapter_version),
            ("prompt_version", self.prompt_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{name} must be a non-empty string")
        if self.status != "completed":
            raise ValidationError("judge invocation status must be completed")
        for name, value in (
            ("request_fingerprint", self.request_fingerprint),
            ("response_fingerprint", self.response_fingerprint),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise ValidationError(f"{name} must be a SHA-256 fingerprint")
        started = _utc(self.started_at)
        ended = _utc(self.ended_at)
        if ended < started:
            raise ValidationError("judge invocation ended_at must not precede started_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "ended_at", ended)
        frozen_parameters = freeze_payload(self.parameters, "judge_invocation.parameters")
        if not isinstance(frozen_parameters, Mapping):
            raise ValidationError("judge_invocation.parameters must be an object")
        object.__setattr__(self, "parameters", frozen_parameters)
        if self.token_usage is not None:
            frozen_token_usage = freeze_payload(self.token_usage, "judge_invocation.token_usage")
            if not isinstance(frozen_token_usage, Mapping):
                raise ValidationError("judge_invocation.token_usage must be an object")
            object.__setattr__(self, "token_usage", frozen_token_usage)

    def to_dict(self) -> dict[str, JSONValue]:
        body: dict[str, JSONValue] = {
            "invocation_id": str(self.invocation_id),
            "judge_profile": self.judge_profile,
            "provider": self.provider,
            "model": self.model,
            "adapter_version": self.adapter_version,
            "prompt_version": self.prompt_version,
            "parameters": thaw_payload(self.parameters),
            "request_fingerprint": self.request_fingerprint,
            "response_fingerprint": self.response_fingerprint,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "status": self.status,
        }
        if self.token_usage is not None:
            body["token_usage"] = thaw_payload(self.token_usage)
        return body


@dataclass(frozen=True, slots=True)
class EvaluationFinding:
    code: str
    severity: FindingSeverity | str
    message: str
    evidence: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValidationError("finding.code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValidationError("finding.message must be a non-empty string")
        try:
            severity = FindingSeverity(self.severity)
        except ValueError as exc:
            raise ValidationError("finding.severity is invalid") from exc
        object.__setattr__(self, "severity", severity)
        frozen = freeze_payload(self.evidence, "finding.evidence")
        if not isinstance(frozen, Mapping):
            raise ValidationError("finding.evidence must be an object")
        object.__setattr__(self, "evidence", frozen)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "code": self.code,
            "severity": cast(FindingSeverity, self.severity).value,
            "message": self.message,
            "evidence": thaw_payload(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class EvaluationResultPayload:
    result_status: ResultStatus | str
    metrics: Mapping[str, JSONValue] = field(default_factory=dict)
    findings: Sequence[EvaluationFinding] = field(default_factory=tuple)
    evidence: Mapping[str, JSONValue] = field(default_factory=dict)
    evaluation_mode: EvaluationMode | str = EvaluationMode.DETERMINISTIC
    judge_invocations: Sequence[JudgeInvocation] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        try:
            status = ResultStatus(self.result_status)
        except ValueError as exc:
            raise ValidationError("result_status is invalid") from exc
        object.__setattr__(self, "result_status", status)
        try:
            mode = EvaluationMode(self.evaluation_mode)
        except ValueError as exc:
            raise ValidationError("evaluation_mode is invalid") from exc
        object.__setattr__(self, "evaluation_mode", mode)
        for name, value in (("metrics", self.metrics), ("evidence", self.evidence)):
            frozen = freeze_payload(value, f"result.{name}")
            if not isinstance(frozen, Mapping):
                raise ValidationError(f"result.{name} must be an object")
            object.__setattr__(self, name, frozen)
        findings = tuple(self.findings)
        if any(not isinstance(item, EvaluationFinding) for item in findings):
            raise ValidationError("result.findings must contain EvaluationFinding values")
        object.__setattr__(self, "findings", findings)
        invocations = tuple(self.judge_invocations)
        if any(not isinstance(item, JudgeInvocation) for item in invocations):
            raise ValidationError("result.judge_invocations must contain JudgeInvocation values")
        if mode is EvaluationMode.DETERMINISTIC and invocations:
            raise ValidationError("deterministic results cannot contain judge invocations")
        if mode is not EvaluationMode.DETERMINISTIC and not invocations:
            raise ValidationError("semantic results require judge invocations")
        object.__setattr__(self, "judge_invocations", invocations)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "result_status": cast(ResultStatus, self.result_status).value,
            "metrics": thaw_payload(self.metrics),
            "findings": [finding.to_dict() for finding in self.findings],
            "evidence": thaw_payload(self.evidence),
            "evaluation_mode": cast(EvaluationMode, self.evaluation_mode).value,
            "judge_invocations": [invocation.to_dict() for invocation in self.judge_invocations],
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    result_id: UUID
    result_schema_version: str
    project_id: str
    trace_id: UUID
    job_id: UUID
    evaluation_type: str
    evaluator_name: str
    evaluator_version: str
    result_status: ResultStatus
    created_at: datetime
    config: Mapping[str, JSONValue]
    config_fingerprint: str
    trace_fingerprint: str
    metrics: Mapping[str, JSONValue]
    findings: tuple[EvaluationFinding, ...]
    evidence: Mapping[str, JSONValue]
    evaluation_mode: EvaluationMode | str = EvaluationMode.DETERMINISTIC
    judge_invocations: tuple[JudgeInvocation, ...] = ()

    def __post_init__(self) -> None:
        if self.result_schema_version != RESULT_SCHEMA_VERSION:
            raise UnsupportedSchemaError(
                f"unsupported evaluation result schema: {self.result_schema_version}"
            )
        try:
            status = ResultStatus(self.result_status)
        except ValueError as exc:
            raise ValidationError("result_status is invalid") from exc
        object.__setattr__(self, "result_status", status)
        try:
            mode = EvaluationMode(self.evaluation_mode)
        except ValueError as exc:
            raise ValidationError("evaluation_mode is invalid") from exc
        object.__setattr__(self, "evaluation_mode", mode)
        for name, value in (
            ("project_id", self.project_id),
            ("evaluation_type", self.evaluation_type),
            ("evaluator_name", self.evaluator_name),
            ("evaluator_version", self.evaluator_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{name} must be a non-empty string")
        for name, value in (
            ("config_fingerprint", self.config_fingerprint),
            ("trace_fingerprint", self.trace_fingerprint),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise ValidationError(f"{name} must be a SHA-256 fingerprint")
        object.__setattr__(self, "created_at", _utc(self.created_at))
        for field_name, field_value in (
            ("config", self.config),
            ("metrics", self.metrics),
            ("evidence", self.evidence),
        ):
            frozen = freeze_payload(field_value, f"result.{field_name}")
            if not isinstance(frozen, Mapping):
                raise ValidationError(f"result.{field_name} must be an object")
            object.__setattr__(self, field_name, frozen)
        findings = tuple(self.findings)
        if any(not isinstance(item, EvaluationFinding) for item in findings):
            raise ValidationError("findings must contain EvaluationFinding values")
        object.__setattr__(self, "findings", findings)
        invocations = tuple(self.judge_invocations)
        if any(not isinstance(item, JudgeInvocation) for item in invocations):
            raise ValidationError("judge_invocations must contain JudgeInvocation values")
        if mode is EvaluationMode.DETERMINISTIC and invocations:
            raise ValidationError("deterministic results cannot contain judge invocations")
        if mode is not EvaluationMode.DETERMINISTIC and not invocations:
            raise ValidationError("semantic results require judge invocations")
        object.__setattr__(self, "judge_invocations", invocations)

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "result_id": str(self.result_id),
            "result_schema_version": self.result_schema_version,
            "project_id": self.project_id,
            "trace_id": str(self.trace_id),
            "job_id": str(self.job_id),
            "evaluation_type": self.evaluation_type,
            "evaluator_name": self.evaluator_name,
            "evaluator_version": self.evaluator_version,
            "result_status": self.result_status.value,
            "created_at": self.created_at.isoformat(),
            "config": thaw_payload(self.config),
            "config_fingerprint": self.config_fingerprint,
            "trace_fingerprint": self.trace_fingerprint,
            "metrics": thaw_payload(self.metrics),
            "findings": [finding.to_dict() for finding in self.findings],
            "evidence": thaw_payload(self.evidence),
            "evaluation_mode": cast(EvaluationMode, self.evaluation_mode).value,
            "judge_invocations": [invocation.to_dict() for invocation in self.judge_invocations],
        }


def invalid_input_result(
    code: str,
    message: str,
    evidence: Mapping[str, JSONValue] | None = None,
) -> EvaluationResultPayload:
    return EvaluationResultPayload(
        result_status=ResultStatus.INVALID_INPUT,
        findings=(
            EvaluationFinding(
                code=code,
                severity=FindingSeverity.ERROR,
                message=message,
                evidence=evidence or {},
            ),
        ),
    )


__all__ = [
    "EvaluationFinding",
    "EvaluationMode",
    "EvaluationResult",
    "EvaluationResultPayload",
    "FindingSeverity",
    "JudgeInvocation",
    "RESULT_SCHEMA_VERSION",
    "ResultStatus",
    "canonical_json_fingerprint",
    "invalid_input_result",
]
