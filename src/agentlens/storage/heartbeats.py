"""Durable operational heartbeats for the M12 worker dashboard."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import DatabaseConfig


class WorkerHeartbeatRepository:
    def __init__(self, config: DatabaseConfig, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(
            config.sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
            connect_args={
                "connect_timeout": config.connect_timeout,
                "options": f"-c statement_timeout={config.statement_timeout_ms}",
            },
        )

    def upsert(
        self,
        *,
        worker_id: str,
        worker_type: str,
        started_at: datetime,
        last_seen: datetime,
        state: str,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO worker_heartbeats
                        (worker_id, worker_type, started_at, last_seen, state)
                    VALUES (:worker_id, :worker_type, :started_at, :last_seen, :state)
                    ON CONFLICT (worker_id) DO UPDATE SET
                        worker_type = EXCLUDED.worker_type,
                        started_at = EXCLUDED.started_at,
                        last_seen = EXCLUDED.last_seen,
                        state = EXCLUDED.state
                    """
                ),
                {
                    "worker_id": worker_id,
                    "worker_type": worker_type,
                    "started_at": started_at,
                    "last_seen": last_seen,
                    "state": state,
                },
            )

    def touch(self, worker_id: str, last_seen: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE worker_heartbeats
                    SET last_seen = :last_seen, state = 'running'
                    WHERE worker_id = :worker_id
                    """
                ),
                {"worker_id": worker_id, "last_seen": last_seen},
            )

    def stop(self, worker_id: str, last_seen: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE worker_heartbeats
                    SET last_seen = :last_seen, state = 'stopped'
                    WHERE worker_id = :worker_id
                    """
                ),
                {"worker_id": worker_id, "last_seen": last_seen},
            )

    def list(
        self, *, limit: int = 50, stale_after_seconds: float = 30.0
    ) -> tuple[dict[str, Any], ...]:
        bounded_limit = max(1, min(limit, 100))
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT worker_id, worker_type, started_at, last_seen, state,
                           CASE
                             WHEN state = 'running'
                              AND last_seen >= now() - (:stale * interval '1 second')
                             THEN 'healthy' ELSE 'stale'
                           END AS health
                    FROM worker_heartbeats
                    ORDER BY last_seen DESC, worker_id
                    LIMIT :limit
                    """
                ),
                {"limit": bounded_limit, "stale": stale_after_seconds},
            ).mappings()
            return tuple(dict(row) for row in rows)


class WorkerHeartbeat:
    """Best-effort daemon updater; worker work remains authoritative."""

    def __init__(
        self,
        repository: WorkerHeartbeatRepository,
        *,
        worker_id: str,
        worker_type: str,
        interval_seconds: float = 5.0,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.worker_id = worker_id
        self.worker_type = worker_type
        self.interval_seconds = max(1.0, interval_seconds)
        self._now = now
        self._started_at: datetime | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        started = self._now()
        self._started_at = started
        try:
            self.repository.upsert(
                worker_id=self.worker_id,
                worker_type=self.worker_type,
                started_at=started,
                last_seen=started,
                state="running",
            )
        except Exception:
            pass
        self._thread = threading.Thread(
            target=self._run,
            name=f"agentlens-heartbeat-{self.worker_type}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds + 0.5))
        try:
            self.repository.stop(self.worker_id, self._now())
        except Exception:
            return

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.repository.touch(self.worker_id, self._now())
            except Exception:
                if self._started_at is not None:
                    try:
                        self.repository.upsert(
                            worker_id=self.worker_id,
                            worker_type=self.worker_type,
                            started_at=self._started_at,
                            last_seen=self._now(),
                            state="running",
                        )
                    except Exception:
                        continue
