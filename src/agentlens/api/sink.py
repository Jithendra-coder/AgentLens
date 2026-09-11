"""Storage-independent canonical trace ingestion sink."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Protocol, cast
from uuid import UUID

from agentlens.domain import Trace
from agentlens.storage.contracts import (
    IngestionResult,
    TraceConflictError,
    canonical_fingerprint,
)


class TraceIngestionSink(Protocol):
    """Boundary that receives already validated canonical traces."""

    def ingest(self, trace: Trace) -> IngestionResult:
        """Accept one trace or return an idempotent duplicate."""

    def ingest_many(self, traces: Sequence[Trace]) -> tuple[IngestionResult, ...]:
        """Preflight and accept a batch atomically where practical."""


class InMemoryTraceSink:
    """Thread-safe process-local sink with idempotency and conflict detection."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, UUID], tuple[str, Trace]] = {}
        self._lock = threading.RLock()

    def ingest(self, trace: Trace) -> IngestionResult:
        return self.ingest_many((trace,))[0]

    def ingest_many(self, traces: Sequence[Trace]) -> tuple[IngestionResult, ...]:
        if not traces:
            return ()
        fingerprints = [canonical_fingerprint(trace) for trace in traces]
        with self._lock:
            results: list[IngestionResult] = []
            for trace, fingerprint in zip(traces, fingerprints, strict=True):
                key = (trace.project_id, cast(UUID, trace.trace_id))
                existing = self._records.get(key)
                if existing is not None and existing[0] != fingerprint:
                    raise TraceConflictError("trace identity has conflicting content")
                results.append(
                    IngestionResult(
                        trace_id=cast(UUID, trace.trace_id),
                        duplicate=existing is not None,
                        fingerprint=fingerprint,
                    )
                )
            for trace, fingerprint, result in zip(traces, fingerprints, results, strict=True):
                if not result.duplicate:
                    self._records[(trace.project_id, cast(UUID, trace.trace_id))] = (
                        fingerprint,
                        trace,
                    )
            return tuple(results)

    @property
    def traces(self) -> tuple[Trace, ...]:
        """Return accepted canonical objects in process-local insertion order."""

        with self._lock:
            return tuple(record[1] for record in self._records.values())

    def get(self, project_id: str, trace_id: UUID) -> Trace | None:
        """Return one stored canonical object without exposing internal state."""

        with self._lock:
            record = self._records.get((project_id, trace_id))
            return record[1] if record is not None else None

    def get_trace(self, project_id: str, trace_id: UUID) -> Trace | None:
        """Alias get for TraceQueryRepository compatibility."""
        return self.get(project_id, trace_id)

    def query_traces(self, project_id: str, query: Any) -> Any:
        """Return bounded summaries within a project boundary."""
        from agentlens.storage.repository import TracePage, TraceSummary
        with self._lock:
            summaries: list[TraceSummary] = []
            for (pid, _), (_, trace) in self._records.items():
                if pid != project_id:
                    continue
                duration = None
                if trace.started_at and trace.ended_at:
                    duration = (trace.ended_at - trace.started_at).total_seconds()
                status_str = trace.status.value if hasattr(trace.status, "value") else str(trace.status)
                summaries.append(
                    TraceSummary(
                        trace_id=cast(UUID, trace.trace_id),
                        name=trace.name,
                        session_id=trace.session_id,
                        status=status_str,
                        started_at=trace.started_at,
                        ended_at=trace.ended_at,
                        duration_seconds=duration,
                        span_count=len(trace.spans),
                        event_count=len(trace.events),
                    )
                )
            summaries.sort(key=lambda s: s.started_at, reverse=True)
            limit = getattr(query, "limit", 50)
            return TracePage(items=tuple(summaries[:limit]), next_cursor=None)

    def check_ready(self) -> bool:
        """Keep the development sink compatible with readiness checks."""

        return True

    def dispose(self) -> None:
        """Match the durable repository lifecycle boundary."""



__all__ = (
    "InMemoryTraceSink",
    "IngestionResult",
    "TraceConflictError",
    "canonical_fingerprint",
)
