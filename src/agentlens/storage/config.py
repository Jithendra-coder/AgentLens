"""Validated M4 database configuration."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, repr=False)
class DatabaseConfig:
    """Small synchronous SQLAlchemy configuration without password exposure."""

    url: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    connect_timeout: int = 10
    statement_timeout_ms: int = 5000
    environment: str = "development"
    cursor_secret: str = "agentlens-m4-development-cursor-secret"

    def __post_init__(self) -> None:
        if not isinstance(self.url, str) or not self.url.strip():
            raise ValueError("database URL must be a non-empty string")
        if not self.url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
            raise ValueError("database URL must use PostgreSQL")
        for name in ("pool_size", "max_overflow", "connect_timeout", "statement_timeout_ms"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if (
            not isinstance(self.pool_timeout, (int, float))
            or isinstance(self.pool_timeout, bool)
            or not math.isfinite(self.pool_timeout)
            or self.pool_timeout <= 0
        ):
            raise ValueError("pool_timeout must be a finite positive number")
        if not isinstance(self.environment, str) or not self.environment.strip():
            raise ValueError("environment must be a non-empty string")
        if not isinstance(self.cursor_secret, str) or len(self.cursor_secret) < 16:
            raise ValueError("cursor_secret must be at least 16 characters")

    @property
    def sqlalchemy_url(self) -> str:
        """Return a URL using the installed psycopg 3 SQLAlchemy dialect."""

        if self.url.startswith("postgres://"):
            return "postgresql+psycopg://" + self.url.removeprefix("postgres://")
        if self.url.startswith("postgresql://"):
            return "postgresql+psycopg://" + self.url.removeprefix("postgresql://")
        return self.url

    def __repr__(self) -> str:
        return (
            "DatabaseConfig(url='***', "
            f"pool_size={self.pool_size}, max_overflow={self.max_overflow}, "
            f"environment={self.environment!r})"
        )
