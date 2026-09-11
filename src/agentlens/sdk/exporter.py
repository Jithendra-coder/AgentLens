"""Local and HTTP exporter boundaries."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agentlens.domain import Trace
from agentlens.exceptions import HttpExportError


class _Response(Protocol):
    status: int

    def read(self) -> bytes: ...

    def __enter__(self) -> _Response: ...

    def __exit__(self, *args: object) -> None: ...


class TraceExporter(Protocol):
    """Synchronous handoff boundary for finalized canonical traces."""

    def export(self, trace: Trace) -> None:
        """Receive one finalized trace."""


class InMemoryTraceExporter:
    """Deterministic local collector for tests and examples."""

    def __init__(self) -> None:
        self.traces: list[Trace] = []

    def export(self, trace: Trace) -> None:
        self.traces.append(trace)

    def flush(self) -> None:
        """Synchronous exporter has nothing to flush."""

    def shutdown(self) -> None:
        """Synchronous exporter has nothing to shut down."""


class HttpTraceExporter:
    """Send canonical trace snapshots to the M3 HTTP ingestion endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 5.0,
        user_agent: str = "agentlens-python/0.1",
        opener: Callable[..., _Response] = urlopen,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
            raise ValueError("timeout must be a finite positive number")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number")
        if not isinstance(user_agent, str) or not user_agent.strip():
            raise ValueError("user_agent must be a non-empty string")
        if not callable(opener):
            raise ValueError("opener must be callable")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = float(timeout)
        self._user_agent = user_agent
        self._opener = opener

    @property
    def timeout(self) -> float:
        """Return the finite request timeout."""

        return self._timeout

    def export(self, trace: Trace) -> None:
        """POST one canonical trace; failures are isolated by AgentLens."""

        request = Request(
            f"{self._base_url}/v1/traces",
            data=trace.to_json().encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": self._user_agent,
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                status = response.status
                response.read()
        except HTTPError as exc:
            raise HttpExportError(f"gateway returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise HttpExportError("gateway request failed") from None
        if not isinstance(status, int) or status < 200 or status >= 300:
            raise HttpExportError(f"gateway returned HTTP {status}")

    def flush(self) -> None:
        """HTTP export is synchronous and has no buffered work."""

    def shutdown(self) -> None:
        """HTTP export owns no persistent connection."""

    def __repr__(self) -> str:
        return f"HttpTraceExporter(base_url={self._base_url!r}, api_key='***')"


__all__ = ("HttpTraceExporter", "InMemoryTraceExporter", "TraceExporter")
