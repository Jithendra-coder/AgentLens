"""Data lifecycle retention policies and PII redaction ."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta


class RetentionEnforcer:
    """Evaluates retention expiry and enforces PII data sanitization."""

    @staticmethod
    def is_expired(created_at: datetime, retention_days: int, now: datetime | None = None) -> bool:
        current_time = now or datetime.now(UTC)
        cutoff = current_time - timedelta(days=retention_days)
        return created_at < cutoff

    @staticmethod
    def redact_pii(text: str) -> str:
        if not text:
            return ""

        # 1. Emails
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        s = re.sub(email_pattern, "[REDACTED_EMAIL]", text)

        # 2. Phone numbers (international and US formats)
        phone_pattern = r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
        s = re.sub(phone_pattern, "[REDACTED_PHONE]", s)

        # 3. API Keys / Secrets (sk-..., Bearer ...)
        key_pattern = r"\b(?:sk-[a-zA-Z0-9_-]{20,}|Bearer\s+[a-zA-Z0-9_.-]{20,})\b"
        s = re.sub(key_pattern, "[REDACTED_SECRET]", s)

        return s
