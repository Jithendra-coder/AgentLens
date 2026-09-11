"""Unit tests for RetentionEnforcer expiry calculation and PII redaction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentlens.governance.retention import RetentionEnforcer


def test_retention_enforcer_expiry_and_pii_redaction() -> None:
    now = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)

    # 1. Expiry Check (90 days policy)
    recent_ts = now - timedelta(days=30)
    expired_ts = now - timedelta(days=100)

    assert RetentionEnforcer.is_expired(recent_ts, 90, now=now) is False
    assert RetentionEnforcer.is_expired(expired_ts, 90, now=now) is True

    # 2. PII Redaction
    sample_text = (
        "User contact is john.doe@company.org or support@agentlens.io with phone (555) 123-4567. "
        "Bearer token sk-proj-1234567890abcdefghijklmnop."
    )
    redacted = RetentionEnforcer.redact_pii(sample_text)

    assert "john.doe@company.org" not in redacted
    assert "support@agentlens.io" not in redacted
    assert "[REDACTED_EMAIL]" in redacted

    assert "(555) 123-4567" not in redacted
    assert "[REDACTED_PHONE]" in redacted

    assert "sk-proj-1234567890abcdefghijklmnop" not in redacted
    assert "[REDACTED_SECRET]" in redacted
