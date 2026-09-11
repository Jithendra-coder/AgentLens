"""Dependency-light contracts shared by M3 and M4 ingestion boundaries."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from agentlens.domain import Trace


class TraceConflictError(Exception):
    """Raised when one project/trace identity receives changed content."""


class IngestionUnavailableError(Exception):
    """Raised when a sink cannot accept telemetry."""


class StorageUnavailableError(Exception):
    """Raised when the durable storage boundary cannot serve a request."""


@dataclass(frozen=True, slots=True)
class IngestionResult:
    trace_id: UUID
    duplicate: bool
    fingerprint: str


def canonical_fingerprint(trace: Trace) -> str:
    """Hash deterministic M1 JSON, independent of transport or database rows."""

    return hashlib.sha256(trace.to_json().encode("utf-8")).hexdigest()
