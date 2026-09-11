"""Heuristic and statistical diagnostic engine ."""

from __future__ import annotations

from agentlens.rca.models import DiagnosticInput, DiagnosticResult


class DiagnosticEngine:
    """Diagnoses trace and telemetry failures to categorize root causes and prescribe fixes."""

    @staticmethod
    def diagnose(diag: DiagnosticInput) -> DiagnosticResult:
        err = (diag.error_message or "").lower()
        prompt = (diag.prompt_text or "").lower()

        # 1. Prompt Injection / Jailbreak
        injection_keywords = (
            "ignore previous instructions",
            "system prompt leak",
            "jailbreak",
            "dan mode",
            "disregard safety guidelines",
        )
        if any(kw in prompt or kw in err for kw in injection_keywords):
            return DiagnosticResult(
                failure_category="prompt_injection",
                root_cause_summary="Prompt injection pattern detected in input payload.",
                confidence_score=0.95,
                recommended_action=(
                    "Enforce strict input sanitization filters and apply pre-flight "
                    "guardrail evaluators."
                ),
            )

        # 2. Context Window Overflow
        if (
            (diag.total_tokens is not None and diag.total_tokens > 8192)
            or "maximum context length" in err
            or "context_length_exceeded" in err
            or "token limit" in err
        ):
            return DiagnosticResult(
                failure_category="context_overflow",
                root_cause_summary=(
                    f"Model context window limit breached "
                    f"({diag.total_tokens or 'overflow'} tokens)."
                ),
                confidence_score=0.92,
                recommended_action=(
                    "Implement chunk summarization, truncate extraneous history, "
                    "or route to long-context frontier models."
                ),
            )

        # 3. Timeout / Latency SLA Breach
        if (
            diag.http_status == 504
            or (diag.latency_ms is not None and diag.latency_ms >= 5000.0)
            or "timed out" in err
            or "timeout" in err
        ):
            return DiagnosticResult(
                failure_category="timeout",
                root_cause_summary=(
                    f"Upstream provider response latency breached SLA threshold "
                    f"({diag.latency_ms or '504'}ms)."
                ),
                confidence_score=0.90,
                recommended_action=(
                    "Configure resilient multi-provider fallback layers and reduce generation "
                    "max_tokens ceiling."
                ),
            )

        # 4. Provider Rate Limits & Server Errors
        if (
            diag.http_status in (429, 500, 502, 503)
            or "rate_limit" in err
            or "overloaded" in err
            or "quota" in err
        ):
            return DiagnosticResult(
                failure_category="provider_error",
                root_cause_summary=(
                    f"Upstream provider service error or rate limit exhaustion "
                    f"(HTTP {diag.http_status or '429'})."
                ),
                confidence_score=0.94,
                recommended_action=(
                    "Activate secondary fallback providers and implement exponential backoff."
                ),
            )

        # 5. Retrieval Failure / Vector Search Void
        if (
            "retriever empty" in err
            or "no chunks returned" in err
            or "vector db" in err
            or "embedding mismatch" in err
        ):
            return DiagnosticResult(
                failure_category="retrieval_failure",
                root_cause_summary="Knowledge retrieval stage yielded empty chunks.",
                confidence_score=0.88,
                recommended_action=(
                    "Tune hybrid BM25 + dense embedding similarity thresholds and check sync."
                ),
            )

        # 6. Evaluation Hallucination / Low Faithfulness
        if diag.eval_score is not None and diag.eval_score < 0.50:
            return DiagnosticResult(
                failure_category="hallucination",
                root_cause_summary=(
                    f"Generated output scored critically low faithfulness/groundedness "
                    f"({diag.eval_score:.2f})."
                ),
                confidence_score=0.85,
                recommended_action=(
                    "Strengthen RAG citation constraints in prompt and inject verification steps."
                ),
            )

        # 7. Fallback Unknown
        summary_msg = diag.error_message or "No explicit error logged."
        return DiagnosticResult(
            failure_category="unknown",
            root_cause_summary=f"Unclassified execution anomaly: {summary_msg}",
            confidence_score=0.50,
            recommended_action="Inspect full span telemetry trace and replay execution in sandbox.",
        )
