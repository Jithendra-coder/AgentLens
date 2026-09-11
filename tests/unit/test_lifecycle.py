"""Unit tests for LifecycleCoordinator and graceful shutdown."""

from __future__ import annotations

import time

import pytest

from agentlens.exceptions import LifecycleError
from agentlens.lifecycle import LifecycleCoordinator


def test_lifecycle_startup_hooks_run_in_order() -> None:
    coordinator = LifecycleCoordinator()
    order: list[int] = []

    coordinator.on_startup(lambda: order.append(1))
    coordinator.on_startup(lambda: order.append(2))

    assert not coordinator.is_started
    coordinator.start()
    assert coordinator.is_started
    assert order == [1, 2]

    # Repeated start does not rerun
    coordinator.start()
    assert order == [1, 2]


def test_lifecycle_shutdown_hooks_run_in_lifo_order() -> None:
    coordinator = LifecycleCoordinator()
    order: list[int] = []

    coordinator.on_shutdown(lambda: order.append(1))
    coordinator.on_shutdown(lambda: order.append(2))
    coordinator.on_shutdown(lambda: order.append(3))

    assert not coordinator.is_shutting_down
    coordinator.shutdown()
    assert coordinator.is_shutting_down
    assert order == [3, 2, 1]

    # Repeated shutdown is idempotent
    coordinator.shutdown()
    assert order == [3, 2, 1]


def test_lifecycle_startup_error_raises() -> None:
    coordinator = LifecycleCoordinator()

    def fail_startup() -> None:
        raise ValueError("DB init failed")

    coordinator.on_startup(fail_startup)
    with pytest.raises(LifecycleError, match="Startup hook failed"):
        coordinator.start()


def test_lifecycle_shutdown_timeout_protection() -> None:
    coordinator = LifecycleCoordinator(shutdown_timeout_seconds=0.1)

    def slow_hook() -> None:
        time.sleep(0.3)

    coordinator.on_shutdown(slow_hook)
    with pytest.raises(LifecycleError, match="Shutdown encountered"):
        coordinator.shutdown()
