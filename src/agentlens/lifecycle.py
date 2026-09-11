"""Production service lifecycle, signal coordination, and graceful shutdown."""

from __future__ import annotations

import asyncio
import inspect
import logging
import signal
import threading
import time
from collections.abc import Callable
from typing import Any

from agentlens.exceptions import LifecycleError

logger = logging.getLogger("agentlens.lifecycle")


class LifecycleCoordinator:
    """Coordinate service startup, signal handling, and graceful shutdown."""

    def __init__(self, shutdown_timeout_seconds: float = 30.0) -> None:
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self._startup_callbacks: list[Callable[[], Any]] = []
        self._shutdown_callbacks: list[Callable[[], Any]] = []
        self._is_shutting_down = False
        self._is_started = False
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()

    @property
    def is_shutting_down(self) -> bool:
        return self._is_shutting_down

    @property
    def is_started(self) -> bool:
        return self._is_started

    def on_startup(self, callback: Callable[[], Any]) -> None:
        """Register a callback to run on startup."""
        self._startup_callbacks.append(callback)

    def on_shutdown(self, callback: Callable[[], Any]) -> None:
        """Register a callback to run on graceful shutdown (LIFO order)."""
        self._shutdown_callbacks.append(callback)

    def start(self) -> None:
        """Execute all startup hooks in registered order."""
        with self._lock:
            if self._is_started:
                return
            logger.info("lifecycle_starting", extra={"hooks_count": len(self._startup_callbacks)})
            for cb in self._startup_callbacks:
                try:
                    res = cb()
                    if inspect.iscoroutine(res):
                        asyncio.run(res)
                except Exception as exc:
                    logger.error("lifecycle_startup_hook_failed", extra={"error": str(exc)})
                    raise LifecycleError(f"Startup hook failed: {exc}") from exc
            self._is_started = True
            logger.info("lifecycle_started")

    def install_signal_handlers(self) -> None:
        """Install SIGINT and SIGTERM handlers to trigger graceful shutdown."""

        def _handler(signum: int, _frame: Any) -> None:
            signame = signal.Signals(signum).name
            logger.info("lifecycle_signal_received", extra={"signal": signame})
            self.shutdown()

        try:
            signal.signal(signal.SIGINT, _handler)
        except (ValueError, AttributeError):
            pass

        try:
            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, AttributeError):
            pass

    def shutdown(self) -> None:
        """Execute all shutdown hooks gracefully in reverse registration order."""
        with self._lock:
            if self._is_shutting_down:
                return
            self._is_shutting_down = True
            self._shutdown_event.set()

        logger.info(
            "lifecycle_shutdown_initiating",
            extra={"hooks_count": len(self._shutdown_callbacks)},
        )
        started_at = time.monotonic()
        errors: list[Exception] = []

        # Execute shutdown callbacks in LIFO order
        for cb in reversed(self._shutdown_callbacks):
            remaining = self.shutdown_timeout_seconds - (time.monotonic() - started_at)
            if remaining <= 0:
                logger.error("lifecycle_shutdown_timeout_exceeded")
                errors.append(LifecycleError("Shutdown timeout exceeded while executing hooks"))
                break

            try:
                res = cb()
                if inspect.iscoroutine(res):
                    asyncio.run(asyncio.wait_for(res, timeout=remaining))
            except Exception as exc:
                logger.error("lifecycle_shutdown_hook_error", extra={"error": str(exc)})
                errors.append(exc)

            if time.monotonic() - started_at > self.shutdown_timeout_seconds:
                logger.error("lifecycle_shutdown_timeout_exceeded")
                errors.append(LifecycleError("Shutdown timeout exceeded while executing hooks"))
                break

        duration = time.monotonic() - started_at
        if errors:
            logger.warning(
                "lifecycle_shutdown_completed_with_errors",
                extra={"duration_seconds": duration, "error_count": len(errors)},
            )
            raise LifecycleError(f"Shutdown encountered {len(errors)} error(s): {errors[0]}")
        else:
            logger.info(
                "lifecycle_shutdown_clean",
                extra={"duration_seconds": duration},
            )

    def wait_for_shutdown(self) -> None:
        """Block until shutdown is signaled."""
        self._shutdown_event.wait()
