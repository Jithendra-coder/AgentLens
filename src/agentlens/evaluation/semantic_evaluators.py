"""RAG, tool, and agent evaluators with deterministic-first semantics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import cast
from uuid import UUID

from agentlens.domain import Span, Status, Trace
from agentlens.domain.types import JSONValue, thaw_payload

from .evaluators import _normalized_config
from .judges import (
    JudgeInputBounds,
    JudgeRequest,
    JudgeResponse,
    SemanticJudge,
    build_judge_request,
    invoke_judge,
)
from .prompts import (
    AGENT_CRITERIA_PROMPT_VERSION,
    RAG_CONTEXT_RELEVANCE_PROMPT_VERSION,
    RAG_GROUNDEDNESS_PROMPT_VERSION,
)
from .results import (
    EvaluationFinding,
    EvaluationMode,
    EvaluationResultPayload,
    FindingSeverity,
    JudgeInvocation,
    ResultStatus,
    invalid_input_result,
)

REJECTED_JUDGE_CONFIG_KEYS = frozenset(
    {"api_url", "provider_url", "endpoint", "api_key", "authorization", "password", "secret"}
)


def _invalid(code: str, reason: str) -> EvaluationResultPayload:
    return invalid_input_result(code, "Evaluation input is invalid.", {"reason": reason})


def _span(trace: Trace, config: Mapping[str, JSONValue], key: str) -> Span | None:
    value = config.get(key)
    if not isinstance(value, str):
        return None
    try:
        span_id = UUID(value)
    except ValueError:
        return None
    return next((item for item in trace.spans if item.span_id == span_id), None)


def _answer(span: Span | None) -> str | None:
    if span is None:
        return None
    if isinstance(span.output, str):
        return span.output
    if isinstance(span.output, Mapping):
        for key in ("answer", "text", "content"):
            value = span.output.get(key)
            if isinstance(value, str):
                return value
    return None


def _documents(span: Span | None, *, require_content: bool) -> list[dict[str, JSONValue]] | None:
    if span is None or str(span.span_type) != "retrieval" or not isinstance(span.output, Mapping):
        return None
    raw_documents = span.output.get("documents")
    if not isinstance(raw_documents, (list, tuple)):
        return None
    documents: list[dict[str, JSONValue]] = []
    seen: set[str] = set()
    for raw in raw_documents:
        if not isinstance(raw, Mapping):
            return None
        document_id = raw.get("id")
        if not isinstance(document_id, str) or not document_id or document_id in seen:
            return None
        content = raw.get("content")
        if require_content and not isinstance(content, str):
            return None
        document: dict[str, JSONValue] = {"id": document_id}
        if isinstance(content, str):
            document["content"] = content
        metadata = raw.get("metadata")
        if isinstance(metadata, Mapping):
            document["metadata"] = thaw_payload(metadata)
        documents.append(document)
        seen.add(document_id)
    return documents


def _semantic_config(config: Mapping[str, object], prompt_version: str) -> dict[str, JSONValue]:
    normalized = _normalized_config(config)
    if any(key.lower() in REJECTED_JUDGE_CONFIG_KEYS for key in normalized):
        raise ValueError("judge endpoints and credentials are operator-configured")
    profile = normalized.get("judge_profile", "default-semantic")
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("judge_profile must be a non-empty string")
    normalized["judge_profile"] = profile
    configured_prompt = normalized.get("prompt_version", prompt_version)
    if configured_prompt != prompt_version:
        raise ValueError("prompt_version is evaluator-controlled")
    normalized["prompt_version"] = prompt_version
    return normalized


def _judge_request(
    *,
    evaluation_type: str,
    config: Mapping[str, JSONValue],
    context: Mapping[str, JSONValue],
) -> JudgeRequest:
    bounds = JudgeInputBounds.from_config(config)
    return build_judge_request(
        evaluation_type=evaluation_type,
        judge_profile=cast(str, config["judge_profile"]),
        prompt_version=cast(str, config["prompt_version"]),
        context=context,
        bounds=bounds,
    )


def _criterion_scores(
    response: JudgeResponse,
    ids: list[str],
    labels: set[str],
) -> list[tuple[str, str, float, tuple[str, ...], str | None]]:
    by_id = {item.criterion_id: item for item in response.criterion_results}
    values: list[tuple[str, str, float, tuple[str, ...], str | None]] = []
    for item_id in ids:
        item = by_id.get(item_id)
        if item is None:
            label = response.label
            score = (
                float(response.score)
                if response.score is not None
                else (1.0 if label in labels else 0.0)
            )
            evidence = tuple(response.evidence_document_ids)
            rationale = response.rationale
        else:
            label = item.label
            score = (
                float(item.score) if item.score is not None else (1.0 if label in labels else 0.0)
            )
            evidence = item.evidence_document_ids
            rationale = item.rationale
        values.append((item_id, label, score, evidence, rationale))
    return values


def _truncation_finding(request: JudgeRequest) -> EvaluationFinding | None:
    if not request.truncated:
        return None
    return EvaluationFinding(
        code="judge_input_truncated",
        severity=FindingSeverity.WARNING,
        message="The semantic judge received explicitly bounded evidence.",
        evidence=request.truncation,
    )


class RagContextRelevanceEvaluator:
    evaluation_type = "rag_context_relevance"
    evaluator_name = "agentlens.rag_context_relevance"
    evaluator_version = "1.0.0"
    prompt_version = RAG_CONTEXT_RELEVANCE_PROMPT_VERSION

    def __init__(self, judge: SemanticJudge | None = None) -> None:
        self.judge = judge

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _semantic_config(config, self.prompt_version)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        retrieval = _documents(_span(trace, config, "retrieval_span_id"), require_content=True)
        answer = _answer(_span(trace, config, "answer_span_id"))
        question = config.get("question")
        if (
            retrieval is None
            or not retrieval
            or answer is None
            or not isinstance(question, str)
            or not question.strip()
        ):
            return _invalid(
                "invalid_rag_context_input", "retrieval, answer, and question are required"
            )
        try:
            request = _judge_request(
                evaluation_type=self.evaluation_type,
                config=config,
                context={
                    "question": question,
                    "answer": answer,
                    "documents": cast(JSONValue, retrieval),
                },
            )
            response, invocation = invoke_judge(self.judge, request)
        except ValueError as exc:
            return _invalid("invalid_rag_context_input", str(exc))
        ids = [cast(str, item["id"]) for item in retrieval]
        scored = _criterion_scores(response, ids, {"relevant"})
        irrelevant = [item_id for item_id, label, _, _, _ in scored if label != "relevant"]
        findings = [
            EvaluationFinding(
                code="irrelevant_retrieval",
                severity=FindingSeverity.WARNING,
                message="A retrieved document was judged irrelevant to the task.",
                evidence={"document_id": item_id},
            )
            for item_id in irrelevant
        ]
        truncation_finding = _truncation_finding(request)
        if truncation_finding is not None:
            findings.append(truncation_finding)
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "documents_evaluated": len(scored),
                "relevant_document_count": len(scored) - len(irrelevant),
                "irrelevant_document_count": len(irrelevant),
                "mean_context_relevance": sum(item[2] for item in scored) / len(scored),
            },
            findings=tuple(findings),
            evidence={
                "document_ids": cast(JSONValue, ids),
                "irrelevant_document_ids": cast(JSONValue, irrelevant),
            },
            evaluation_mode=EvaluationMode.MODEL_ASSISTED,
            judge_invocations=(invocation,),
        )


class RagGroundednessEvaluator:
    evaluation_type = "rag_groundedness"
    evaluator_name = "agentlens.rag_groundedness"
    evaluator_version = "1.0.0"
    prompt_version = RAG_GROUNDEDNESS_PROMPT_VERSION

    def __init__(self, judge: SemanticJudge | None = None) -> None:
        self.judge = judge

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _semantic_config(config, self.prompt_version)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        retrieval = _documents(_span(trace, config, "retrieval_span_id"), require_content=True)
        answer = _answer(_span(trace, config, "answer_span_id"))
        claims = config.get("claims")
        if (
            retrieval is None
            or not retrieval
            or answer is None
            or not isinstance(claims, list)
            or not claims
        ):
            return _invalid(
                "invalid_groundedness_input", "retrieval, answer, and claims are required"
            )
        parsed_claims: list[dict[str, JSONValue]] = []
        for claim in claims:
            if not isinstance(claim, Mapping):
                return _invalid("invalid_groundedness_input", "claims must be objects")
            claim_id, text = claim.get("id"), claim.get("text")
            if (
                not isinstance(claim_id, str)
                or not claim_id
                or not isinstance(text, str)
                or not text
            ):
                return _invalid("invalid_groundedness_input", "each claim needs id and text")
            parsed_claims.append({"id": claim_id, "text": text})
        try:
            request = _judge_request(
                evaluation_type=self.evaluation_type,
                config=config,
                context={
                    "answer": answer,
                    "claims": cast(JSONValue, parsed_claims),
                    "documents": cast(JSONValue, retrieval),
                },
            )
            response, invocation = invoke_judge(self.judge, request)
        except ValueError as exc:
            return _invalid("invalid_groundedness_input", str(exc))
        ids = [cast(str, item["id"]) for item in parsed_claims]
        scored = _criterion_scores(response, ids, {"supported"})
        supported = sum(label == "supported" for _, label, _, _, _ in scored)
        partial = sum(label == "partially_supported" for _, label, _, _, _ in scored)
        unsupported = sum(label == "unsupported" for _, label, _, _, _ in scored)
        findings: list[EvaluationFinding] = []
        for claim_id, label, _, evidence, _ in scored:
            if label in {"unsupported", "partially_supported"}:
                findings.append(
                    EvaluationFinding(
                        code=(
                            "unsupported_answer_claim"
                            if label == "unsupported"
                            else "partially_supported_answer_claim"
                        ),
                        severity=(
                            FindingSeverity.ERROR
                            if label == "unsupported"
                            else FindingSeverity.WARNING
                        ),
                        message="An answer claim was not fully supported by retrieved evidence.",
                        evidence={
                            "claim_id": claim_id,
                            "evidence_document_ids": cast(JSONValue, list(evidence)),
                        },
                    )
                )
        truncation_finding = _truncation_finding(request)
        if truncation_finding is not None:
            findings.append(truncation_finding)
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "claims_evaluated": len(scored),
                "supported_claim_count": supported,
                "partially_supported_claim_count": partial,
                "unsupported_claim_count": unsupported,
                "groundedness_score": sum(item[2] for item in scored) / len(scored),
            },
            findings=tuple(findings),
            evidence={"claim_ids": cast(JSONValue, ids)},
            evaluation_mode=EvaluationMode.MODEL_ASSISTED,
            judge_invocations=(invocation,),
        )


def _citation_ids(answer_span: Span | None, config: Mapping[str, JSONValue]) -> list[str] | None:
    configured = config.get("citation_document_ids")
    if configured is not None:
        if not isinstance(configured, list) or any(
            not isinstance(value, str) or not value for value in configured
        ):
            return None
        return [cast(str, value) for value in configured]
    if answer_span is None or not isinstance(answer_span.output, Mapping):
        return []
    citations = answer_span.output.get("citations")
    if not isinstance(citations, (list, tuple)):
        return []
    result: list[str] = []
    for citation in citations:
        if isinstance(citation, str):
            result.append(citation)
        elif isinstance(citation, Mapping) and isinstance(citation.get("id"), str):
            result.append(cast(str, citation["id"]))
        else:
            return None
    return result


class RagCitationIntegrityEvaluator:
    evaluation_type = "rag_citation_integrity"
    evaluator_name = "agentlens.rag_citation_integrity"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _normalized_config(config)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        documents = _documents(_span(trace, config, "retrieval_span_id"), require_content=False)
        citations = _citation_ids(_span(trace, config, "answer_span_id"), config)
        if documents is None or citations is None:
            return _invalid("invalid_citation_input", "retrieval and citations are malformed")
        retrieved = {cast(str, item["id"]) for item in documents}
        counts = Counter(citations)
        invalid = [value for value in citations if value not in retrieved]
        duplicate_count = sum(max(count - 1, 0) for count in counts.values())
        findings: list[EvaluationFinding] = []
        for citation in invalid:
            findings.append(
                EvaluationFinding(
                    code="invalid_citation",
                    severity=FindingSeverity.ERROR,
                    message="The answer cites a document that was not retrieved.",
                    evidence={"document_id": citation},
                )
            )
        for citation, count in counts.items():
            if count > 1:
                findings.append(
                    EvaluationFinding(
                        code="duplicate_citation",
                        severity=FindingSeverity.WARNING,
                        message="The answer cites the same document more than once.",
                        evidence={"document_id": citation, "count": count},
                    )
                )
        if not citations and config.get("require_citations") is True:
            findings.append(
                EvaluationFinding(
                    code="missing_citation",
                    severity=FindingSeverity.WARNING,
                    message="The answer contains no normalized citations.",
                )
            )
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "citations_evaluated": len(citations),
                "valid_citation_count": len(citations) - len(invalid),
                "invalid_citation_count": len(invalid),
                "duplicate_citation_count": duplicate_count,
                "citation_validity_rate": (
                    (len(citations) - len(invalid)) / len(citations) if citations else None
                ),
            },
            findings=tuple(findings),
            evidence={"citation_document_ids": cast(JSONValue, citations)},
        )


def _tool_spans(trace: Trace) -> list[Span]:
    return [span for span in trace.spans if str(span.span_type) == "tool"]


def _string_list(config: Mapping[str, JSONValue], key: str, *, required: bool) -> list[str] | None:
    value = config.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        return None
    return [cast(str, item) for item in value]


def _tool_config(config: Mapping[str, object]) -> dict[str, JSONValue] | None:
    try:
        normalized = _normalized_config(config)
    except Exception:
        return None
    expected = _string_list(normalized, "expected_tools", required=True)
    allowed = _string_list(normalized, "allowed_extra_tools", required=False)
    order_sensitive = normalized.get("order_sensitive", False)
    if expected is None or allowed is None or not isinstance(order_sensitive, bool):
        return None
    normalized["expected_tools"] = cast(JSONValue, expected)
    normalized["allowed_extra_tools"] = cast(JSONValue, allowed)
    normalized["order_sensitive"] = order_sensitive
    return normalized


def _tool_selection_result(
    trace: Trace,
    config: Mapping[str, JSONValue],
    *,
    efficiency: bool = False,
) -> EvaluationResultPayload:
    normalized = _tool_config(config)
    if normalized is None:
        return _invalid("invalid_tool_input", "expected_tools configuration is invalid")
    expected = cast(list[str], normalized["expected_tools"])
    allowed = set(cast(list[str], normalized["allowed_extra_tools"]))
    observed = [span.name for span in _tool_spans(trace)]
    expected_counts = Counter(expected)
    observed_counts = Counter(observed)
    remaining = Counter(observed)
    missing: list[str] = []
    for name in expected:
        if remaining[name] > 0:
            remaining[name] -= 1
        else:
            missing.append(name)
    unexpected = [name for name in observed if name not in expected_counts and name not in allowed]
    duplicates = sum(max(count - 1, 0) for count in observed_counts.values())
    findings: list[EvaluationFinding] = []
    for name in sorted(set(missing)):
        findings.append(
            EvaluationFinding(
                code="missing_expected_tool",
                severity=FindingSeverity.ERROR,
                message="An expected tool was not observed.",
                evidence={"tool": name},
            )
        )
    for name in sorted(set(unexpected)):
        findings.append(
            EvaluationFinding(
                code="unexpected_tool",
                severity=FindingSeverity.WARNING,
                message="An unapproved tool was observed.",
                evidence={"tool": name},
            )
        )
    for name, count in sorted(observed_counts.items()):
        if count > 1:
            findings.append(
                EvaluationFinding(
                    code="duplicate_tool_call",
                    severity=FindingSeverity.WARNING,
                    message="A tool was called more than once.",
                    evidence={"tool": name, "count": count},
                )
            )
    if normalized["order_sensitive"]:
        filtered = [name for name in observed if name in expected_counts]
        if filtered != expected:
            findings.append(
                EvaluationFinding(
                    code="tool_sequence_mismatch",
                    severity=FindingSeverity.ERROR,
                    message="Observed expected tools were out of order.",
                    evidence={"expected_tools": cast(JSONValue, expected)},
                )
            )
    matched = sum(min(observed_counts[name], count) for name, count in expected_counts.items())
    unnecessary = len(unexpected)
    if efficiency:
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "tool_call_count": len(observed),
                "necessary_tool_call_count": len(observed) - unnecessary,
                "unnecessary_tool_call_count": unnecessary,
                "tool_efficiency_rate": (
                    (len(observed) - unnecessary) / len(observed) if observed else None
                ),
            },
            findings=tuple(findings),
            evidence={"observed_tools": cast(JSONValue, observed)},
        )
    return EvaluationResultPayload(
        result_status=ResultStatus.COMPLETED,
        metrics={
            "expected_tool_count": len(expected),
            "matched_expected_tools": matched,
            "missing_expected_tools": cast(JSONValue, sorted(set(missing))),
            "unexpected_tools": cast(JSONValue, sorted(set(unexpected))),
            "duplicate_tool_calls": duplicates,
            "observed_tool_count": len(observed),
        },
        findings=tuple(findings),
        evidence={"observed_tools": cast(JSONValue, observed)},
    )


class ToolSelectionEvaluator:
    evaluation_type = "tool_selection"
    evaluator_name = "agentlens.tool_selection"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _normalized_config(config)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        return _tool_selection_result(trace, config)


class ToolEfficiencyEvaluator:
    evaluation_type = "tool_efficiency"
    evaluator_name = "agentlens.tool_efficiency"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _normalized_config(config)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        return _tool_selection_result(trace, config, efficiency=True)


class ToolArgumentsEvaluator:
    evaluation_type = "tool_arguments"
    evaluator_name = "agentlens.tool_arguments"
    evaluator_version = "1.0.0"

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        return _normalized_config(config)

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        expectations = config.get("expectations")
        if not isinstance(expectations, list) or not expectations:
            return _invalid("invalid_tool_argument_input", "expectations are required")
        spans = _tool_spans(trace)
        matched = 0
        mismatches = 0
        findings: list[EvaluationFinding] = []
        for expectation in expectations:
            if not isinstance(expectation, Mapping):
                return _invalid("invalid_tool_argument_input", "expectations must be objects")
            tool = expectation.get("tool")
            expected_arguments = expectation.get("expected_arguments")
            matching = expectation.get("matching", "subset")
            if (
                not isinstance(tool, str)
                or not isinstance(expected_arguments, Mapping)
                or matching not in {"subset", "exact"}
            ):
                return _invalid(
                    "invalid_tool_argument_input", "tool argument expectation is invalid"
                )
            candidates = [span for span in spans if span.name == tool]
            actual = candidates[0].input if candidates else None
            actual_mapping = actual if isinstance(actual, Mapping) else {}
            fields = [str(field) for field in expected_arguments]
            okay = bool(candidates) and all(
                actual_mapping.get(field) == value for field, value in expected_arguments.items()
            )
            if matching == "exact":
                okay = okay and set(actual_mapping) == set(expected_arguments)
            if okay:
                matched += 1
            else:
                mismatches += 1
                findings.append(
                    EvaluationFinding(
                        code="tool_argument_mismatch",
                        severity=FindingSeverity.ERROR,
                        message="Observed tool arguments did not match the expectation.",
                        evidence={"tool": tool, "fields": cast(JSONValue, fields)},
                    )
                )
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "arguments_evaluated": len(expectations),
                "matched_argument_calls": matched,
                "argument_mismatch_count": mismatches,
            },
            findings=tuple(findings),
            evidence={"tool_names": cast(JSONValue, [span.name for span in spans])},
        )


def _criteria(config: Mapping[str, JSONValue]) -> list[dict[str, JSONValue]] | None:
    raw = config.get("criteria")
    if not isinstance(raw, list) or not raw:
        return None
    result: list[dict[str, JSONValue]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            return None
        criterion_id = item.get("id")
        description = item.get("description")
        mode = item.get("mode", "deterministic")
        if (
            not isinstance(criterion_id, str)
            or not criterion_id
            or criterion_id in seen
            or not isinstance(description, str)
            or not description
            or mode not in {"deterministic", "model_assisted"}
        ):
            return None
        normalized = dict(item)
        normalized["required"] = item.get("required", True)
        if not isinstance(normalized["required"], bool):
            return None
        normalized["mode"] = mode
        result.append(normalized)
        seen.add(criterion_id)
    return result


def _deterministic_criterion(
    trace: Trace,
    criterion: Mapping[str, JSONValue],
    answer_span: Span | None,
) -> tuple[str, float, Mapping[str, JSONValue]] | None:
    criterion_type = criterion.get("type", "output_contains")
    if criterion_type == "expected_tool_called":
        tool = criterion.get("tool")
        if not isinstance(tool, str):
            return None
        passed = any(span.name == tool for span in _tool_spans(trace))
        return ("pass" if passed else "fail", 1.0 if passed else 0.0, {"tool": tool})
    if criterion_type == "error_absent":
        passed = not any(span.status is Status.ERROR for span in trace.spans)
        return ("pass" if passed else "fail", 1.0 if passed else 0.0, {})
    if answer_span is None or not isinstance(answer_span.output, Mapping):
        return None
    output = answer_span.output
    if criterion_type == "required_output_field":
        field = criterion.get("field")
        if not isinstance(field, str):
            return None
        passed = field in output
        return ("pass" if passed else "fail", 1.0 if passed else 0.0, {"field": field})
    if criterion_type == "json_field_equals":
        field, expected = criterion.get("field"), criterion.get("expected")
        if not isinstance(field, str):
            return None
        passed = output.get(field) == expected
        return ("pass" if passed else "fail", 1.0 if passed else 0.0, {"field": field})
    if criterion_type == "output_contains":
        expected = criterion.get("value")
        answer = _answer(answer_span)
        if not isinstance(expected, str) or answer is None:
            return None
        passed = expected in answer
        return ("pass" if passed else "fail", 1.0 if passed else 0.0, {})
    return None


class AgentTaskEvaluator:
    evaluator_version = "1.0.0"

    def __init__(self, evaluation_type: str = "agent_task_success") -> None:
        self.evaluation_type = evaluation_type
        self.evaluator_name = f"agentlens.{evaluation_type}"
        self.prompt_version = AGENT_CRITERIA_PROMPT_VERSION
        self.judge: SemanticJudge | None = None

    def with_judge(self, judge: SemanticJudge | None) -> AgentTaskEvaluator:
        self.judge = judge
        return self

    def normalize_config(self, config: Mapping[str, object]) -> Mapping[str, JSONValue]:
        normalized = _normalized_config(config)
        if any(key.lower() in REJECTED_JUDGE_CONFIG_KEYS for key in normalized):
            raise ValueError("judge endpoints and credentials are operator-configured")
        if "prompt_version" in normalized and normalized["prompt_version"] != self.prompt_version:
            raise ValueError("prompt_version is evaluator-controlled")
        normalized.setdefault("prompt_version", self.prompt_version)
        normalized.setdefault("judge_profile", "default-semantic")
        return normalized

    def evaluate(self, trace: Trace, config: Mapping[str, JSONValue]) -> EvaluationResultPayload:
        task = config.get("task")
        criteria = _criteria(config)
        if not isinstance(task, str) or not task.strip() or criteria is None:
            return _invalid("invalid_agent_task_input", "task and non-empty criteria are required")
        answer_span = _span(trace, config, "answer_span_id")
        deterministic: dict[str, tuple[str, float, Mapping[str, JSONValue]]] = {}
        model_criteria: list[dict[str, JSONValue]] = []
        for criterion in criteria:
            criterion_id = cast(str, criterion["id"])
            if criterion["mode"] == "deterministic":
                outcome = _deterministic_criterion(trace, criterion, answer_span)
                if outcome is None:
                    return _invalid(
                        "invalid_agent_task_input",
                        f"unsupported deterministic criterion: {criterion_id}",
                    )
                deterministic[criterion_id] = outcome
            else:
                model_criteria.append(criterion)
        invocations: tuple[JudgeInvocation, ...] = ()
        semantic: dict[str, tuple[str, float, Mapping[str, JSONValue], str | None]] = {}
        findings: list[EvaluationFinding] = []
        if model_criteria:
            answer = _answer(answer_span)
            if answer is None:
                return _invalid(
                    "invalid_agent_task_input",
                    "model-assisted criteria require answer_span_id",
                )
            try:
                request = _judge_request(
                    evaluation_type=self.evaluation_type,
                    config=config,
                    context={
                        "task": task,
                        "answer": answer,
                        "criteria": cast(JSONValue, model_criteria),
                    },
                )
                response, invocation = invoke_judge(self.judge, request)
            except ValueError as exc:
                return _invalid("invalid_agent_task_input", str(exc))
            ids = [cast(str, item["id"]) for item in model_criteria]
            for criterion_id, label, score, evidence, rationale in _criterion_scores(
                response, ids, {"pass", "supported"}
            ):
                semantic[criterion_id] = (
                    label,
                    score,
                    {"evidence_document_ids": list(evidence)},
                    rationale,
                )
            invocations = (invocation,)
            truncation_finding = _truncation_finding(request)
            if truncation_finding is not None:
                findings.append(truncation_finding)
        criterion_results: list[dict[str, JSONValue]] = []
        required_total = required_passed = optional_total = optional_passed = 0
        modes: set[str] = set()
        for criterion in criteria:
            criterion_id = cast(str, criterion["id"])
            required = cast(bool, criterion["required"])
            if criterion_id in deterministic:
                label, score, criterion_evidence = deterministic[criterion_id]
                rationale = None
                modes.add("deterministic")
            else:
                label, score, criterion_evidence, rationale = semantic[criterion_id]
                modes.add("model_assisted")
            passed = label in {"pass", "supported"}
            if required:
                required_total += 1
                required_passed += passed
            else:
                optional_total += 1
                optional_passed += passed
            result: dict[str, JSONValue] = {
                "criterion_id": criterion_id,
                "status": label,
                "score": score,
                "required": required,
                "evaluation_mode": (
                    "deterministic" if criterion_id in deterministic else "model_assisted"
                ),
                "evidence": dict(criterion_evidence),
            }
            if rationale is not None:
                result["rationale"] = rationale
            criterion_results.append(result)
            if required and not passed:
                findings.append(
                    EvaluationFinding(
                        code="required_agent_criterion_failed",
                        severity=FindingSeverity.ERROR,
                        message="A required agent task criterion failed.",
                        evidence={"criterion_id": criterion_id},
                    )
                )
        mode = (
            EvaluationMode.HYBRID
            if len(modes) > 1
            else EvaluationMode.MODEL_ASSISTED
            if "model_assisted" in modes
            else EvaluationMode.DETERMINISTIC
        )
        return EvaluationResultPayload(
            result_status=ResultStatus.COMPLETED,
            metrics={
                "task_success": required_passed == required_total,
                "aggregation": "all_required_criteria_pass",
                "required_criteria_count": required_total,
                "required_criteria_passed": required_passed,
                "optional_criteria_count": optional_total,
                "optional_criteria_passed": optional_passed,
                "criterion_results": cast(JSONValue, criterion_results),
            },
            findings=tuple(findings),
            evidence={"criterion_ids": cast(JSONValue, [item["id"] for item in criteria])},
            evaluation_mode=mode,
            judge_invocations=invocations,
        )


__all__ = [
    "AgentTaskEvaluator",
    "RagCitationIntegrityEvaluator",
    "RagContextRelevanceEvaluator",
    "RagGroundednessEvaluator",
    "ToolArgumentsEvaluator",
    "ToolEfficiencyEvaluator",
    "ToolSelectionEvaluator",
]
