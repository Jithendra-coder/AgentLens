"""Unit tests for structured logging, JsonFormatter, and correlation ID propagation."""

from __future__ import annotations

import io
import json
import logging

from agentlens.logging import (
    JsonFormatter,
    configure_logging,
    get_correlation_id,
    get_request_id,
    set_correlation_id,
    set_request_id,
)


def test_contextvars_tracking() -> None:
    assert get_correlation_id() is None
    set_request_id("req-123")
    set_correlation_id("corr-456")

    assert get_request_id() == "req-123"
    assert get_correlation_id() == "corr-456"

    set_request_id(None)
    set_correlation_id(None)

    assert get_correlation_id() is None
    assert get_request_id() is None


def test_json_formatter_outputs_valid_json() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="agentlens.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test event message",
        args=(),
        exc_info=None,
    )
    set_request_id("req-999")
    set_correlation_id("corr-888")
    try:
        record.duration_ms = 12.34
        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "agentlens.test"
        assert data["message"] == "Test event message"
        assert data["request_id"] == "req-999"
        assert data["correlation_id"] == "corr-888"
        assert data["duration_ms"] == 12.34
        assert "timestamp" in data
    finally:
        set_request_id(None)
        set_correlation_id(None)


def test_configure_logging_integration() -> None:
    stream = io.StringIO()
    configure_logging(log_level="DEBUG", json_format=True, stream=stream)

    logger = logging.getLogger("agentlens.app")
    logger.info("Application started successfully")

    content = stream.getvalue().strip()
    data = json.loads(content)
    assert data["message"] == "Application started successfully"
    assert data["level"] == "INFO"
