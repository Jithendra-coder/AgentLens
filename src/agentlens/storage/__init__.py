"""M4 durable PostgreSQL storage and trace query boundaries."""

from .config import DatabaseConfig
from .contracts import (
    IngestionResult,
    IngestionUnavailableError,
    StorageUnavailableError,
    TraceConflictError,
    canonical_fingerprint,
)
from .heartbeats import WorkerHeartbeat, WorkerHeartbeatRepository
from .repository import (
    InvalidCursorError,
    PostgresTraceRepository,
    TracePage,
    TraceQuery,
    TraceQueryRepository,
    TraceSummary,
)

__all__ = (
    "DatabaseConfig",
    "IngestionResult",
    "IngestionUnavailableError",
    "InvalidCursorError",
    "PostgresTraceRepository",
    "StorageUnavailableError",
    "TraceConflictError",
    "TracePage",
    "TraceQuery",
    "TraceQueryRepository",
    "TraceSummary",
    "canonical_fingerprint",
    "WorkerHeartbeat",
    "WorkerHeartbeatRepository",
)
