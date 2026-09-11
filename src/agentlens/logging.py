"""Production structured logging subsystem with correlation ID tracking."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CORRELATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_correlation_id() -> str | None:
    """Return the current correlation ID in the execution context."""
    return _CORRELATION_ID.get()


def set_correlation_id(correlation_id: str | None) -> contextvars.Token[str | None]:
    """Set the correlation ID in the current execution context."""
    return _CORRELATION_ID.set(correlation_id)


def get_request_id() -> str | None:
    """Return the current request ID in the execution context."""
    return _REQUEST_ID.get()


def set_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    """Set the request ID in the current execution context."""
    return _REQUEST_ID.set(request_id)


class JsonFormatter(logging.Formatter):
    """Format log records as structured single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include correlation and request IDs if present in context or record
        corr_id = getattr(record, "correlation_id", None) or get_correlation_id()
        if corr_id:
            data["correlation_id"] = corr_id

        req_id = getattr(record, "request_id", None) or get_request_id()
        if req_id:
            data["request_id"] = req_id

        # Include duration if attached
        duration_ms = getattr(record, "duration_ms", None)
        if duration_ms is not None:
            data["duration_ms"] = duration_ms

        # Include status code or route if present
        for key in ("route", "status_code", "project_id", "worker_id", "job_id", "trace_id"):
            val = getattr(record, key, None)
            if val is not None:
                data[key] = val

        # Include exception info if present
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        # Include extra payload if present
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            for k, v in extra.items():
                if k not in data:
                    data[k] = v

        return json.dumps(data, default=str)


def configure_logging(
    *,
    log_level: str = "INFO",
    json_format: bool = True,
    stream: Any = None,
) -> None:
    """Configure root and application loggers with structured formatting."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setLevel(level)

    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)
    logging.getLogger("agentlens").setLevel(level)
