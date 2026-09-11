"""Production migration runner with PostgreSQL advisory lock protection."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from agentlens.exceptions import ConfigurationError
from agentlens.storage.config import DatabaseConfig
from alembic import command

logger = logging.getLogger("agentlens.migrations")

# Deterministic PostgreSQL 64-bit advisory lock key for AgentLens migrations
MIGRATION_ADVISORY_LOCK_ID = 849204128


def _get_alembic_config(database_url: str) -> Config:
    """Create Alembic Config pointing to project's alembic directory."""
    # Find alembic.ini from project root
    root = Path(__file__).resolve().parent.parent.parent.parent
    ini_path = root / "alembic.ini"
    if not ini_path.exists():
        # Fallback to current working directory
        ini_path = Path("alembic.ini").resolve()

    cfg = Config(str(ini_path) if ini_path.exists() else None)
    cfg.set_main_option("sqlalchemy.url", DatabaseConfig(database_url).sqlalchemy_url)
    script_dir = root / "alembic"
    if script_dir.exists():
        cfg.set_main_option("script_location", str(script_dir))
    return cfg


def run_migrations(
    database_url: str,
    target_revision: str = "head",
    *,
    timeout_seconds: float = 60.0,
    lock_id: int = MIGRATION_ADVISORY_LOCK_ID,
) -> None:
    """Run database migrations with a PostgreSQL advisory lock to prevent race conditions."""
    db_config = DatabaseConfig(database_url)
    engine = create_engine(db_config.sqlalchemy_url, isolation_level="AUTOCOMMIT")

    logger.info("acquiring_migration_lock", extra={"lock_id": lock_id})
    started = time.monotonic()
    acquired = False

    with engine.connect() as conn:
        # Attempt to acquire advisory lock within timeout window
        while time.monotonic() - started < timeout_seconds:
            res = conn.execute(text(f"SELECT pg_try_advisory_lock({lock_id})")).scalar()
            if res:
                acquired = True
                break
            logger.info("migration_lock_busy_waiting")
            time.sleep(1.0)

        if not acquired:
            raise ConfigurationError(
                f"Could not acquire PostgreSQL migration advisory lock ({lock_id}) "
                f"within {timeout_seconds}s. Another migration may be running."
            )

        logger.info("migration_lock_acquired", extra={"lock_id": lock_id})
        try:
            # Set environment variable so alembic env.py uses this specific database URL
            os.environ["AGENTLENS_DATABASE_URL"] = database_url
            cfg = _get_alembic_config(database_url)
            logger.info("applying_migrations", extra={"target": target_revision})
            command.upgrade(cfg, target_revision)
            logger.info("migrations_applied_successfully", extra={"target": target_revision})
        finally:
            conn.execute(text(f"SELECT pg_advisory_unlock({lock_id})"))
            logger.info("migration_lock_released", extra={"lock_id": lock_id})


def downgrade_migrations(
    database_url: str,
    target_revision: str,
    *,
    lock_id: int = MIGRATION_ADVISORY_LOCK_ID,
) -> None:
    """Downgrade database migrations to a specific revision."""
    db_config = DatabaseConfig(database_url)
    engine = create_engine(db_config.sqlalchemy_url, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        res = conn.execute(text(f"SELECT pg_try_advisory_lock({lock_id})")).scalar()
        if not res:
            raise ConfigurationError("Could not acquire advisory lock for migration downgrade.")
        try:
            os.environ["AGENTLENS_DATABASE_URL"] = database_url
            cfg = _get_alembic_config(database_url)
            command.downgrade(cfg, target_revision)
            logger.info("migrations_downgraded", extra={"target": target_revision})
        finally:
            conn.execute(text(f"SELECT pg_advisory_unlock({lock_id})"))
