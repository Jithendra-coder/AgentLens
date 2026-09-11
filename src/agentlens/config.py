"""Unified Twelve-Factor production configuration and validation system for AgentLens."""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from agentlens.exceptions import ConfigurationError


class Environment(enum.StrEnum):
    """Runtime deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"

    @classmethod
    def from_str(cls, value: str | None) -> Environment:
        if not value:
            return cls.DEVELOPMENT
        normalized = value.strip().lower()
        for env in cls:
            if env.value == normalized:
                return env
        raise ConfigurationError(
            f"Invalid AGENTLENS_ENVIRONMENT '{value}'. Must be one of: "
            f"{', '.join(e.value for e in cls)}"
        )


def _mask_secret(secret: str | None) -> str:
    if not secret:
        return "<none>"
    if len(secret) <= 6:
        return "***"
    return f"{secret[:2]}...{secret[-2:]}"


def _mask_url_password(url: str | None) -> str:
    if not url:
        return "<none>"
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return parsed._replace(netloc=netloc).geturl()
        return url
    except Exception:
        return "***"


@dataclass(frozen=True)
class DatabaseSettings:
    """PostgreSQL storage configuration."""

    url: str = "postgresql+psycopg://agentlens:agentlens@127.0.0.1:55432/agentlens"
    pool_size: int = 20
    max_overflow: int = 10
    pool_timeout_seconds: float = 30.0

    def validate(self, environment: Environment) -> None:
        if not self.url:
            raise ConfigurationError("AGENTLENS_DATABASE_URL is required")
        if not (self.url.startswith("postgresql://") or self.url.startswith("postgresql+psycopg://")):
            raise ConfigurationError(
                "AGENTLENS_DATABASE_URL must begin with 'postgresql://' or 'postgresql+psycopg://'"
            )
        if self.pool_size < 1:
            raise ConfigurationError("AGENTLENS_DB_POOL_SIZE must be at least 1")
        if self.max_overflow < 0:
            raise ConfigurationError("AGENTLENS_DB_MAX_OVERFLOW cannot be negative")
        if self.pool_timeout_seconds <= 0:
            raise ConfigurationError("AGENTLENS_DB_POOL_TIMEOUT must be greater than 0")


@dataclass(frozen=True)
class RedisSettings:
    """Redis cache and wakeup dispatcher configuration."""

    url: str | None = "redis://127.0.0.1:56379/0"
    socket_timeout_seconds: float = 5.0

    def validate(self, environment: Environment) -> None:
        if self.url is not None:
            if not (self.url.startswith("redis://") or self.url.startswith("rediss://")):
                raise ConfigurationError(
                    "AGENTLENS_REDIS_URL must begin with 'redis://' or 'rediss://'"
                )
        if self.socket_timeout_seconds <= 0:
            raise ConfigurationError("AGENTLENS_REDIS_TIMEOUT must be greater than 0")


@dataclass(frozen=True)
class AuthSettings:
    """API authentication and project identification."""

    project_id: str = "default-project"
    project_api_key: str = "secret-api-key"
    api_key_id: str = "default-key"

    def validate(self, environment: Environment) -> None:
        if not self.project_id or not self.project_id.strip():
            raise ConfigurationError("AGENTLENS_PROJECT_ID cannot be empty")
        if environment in (Environment.PRODUCTION, Environment.STAGING):
            if not self.project_api_key or self.project_api_key == "secret-api-key":
                raise ConfigurationError(
                    "AGENTLENS_PROJECT_API_KEY must be set to a secure key in production/staging"
                )
            if len(self.project_api_key) < 16:
                raise ConfigurationError(
                    "AGENTLENS_PROJECT_API_KEY must be at least 16 characters in production/staging"
                )


@dataclass(frozen=True)
class ServerSettings:
    """FastAPI Gateway server configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = "json"
    max_request_bytes: int = 10 * 1024 * 1024  # 10 MB
    rate_limit_per_minute: int = 1000
    rate_window_seconds: int = 60
    cors_allowed_origins: list[str] = field(default_factory=lambda: ["*"])

    def validate(self, environment: Environment) -> None:
        if not (1 <= self.port <= 65535):
            raise ConfigurationError(f"Invalid port {self.port}. Must be between 1 and 65535")
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError(f"Invalid AGENTLENS_LOG_LEVEL '{self.log_level}'")
        if self.log_format.lower() not in {"json", "text"}:
            raise ConfigurationError(f"Invalid AGENTLENS_LOG_FORMAT '{self.log_format}'")
        if self.max_request_bytes < 1024:
            raise ConfigurationError("AGENTLENS_MAX_REQUEST_BYTES must be at least 1024 bytes")
        if self.rate_limit_per_minute < 1:
            raise ConfigurationError("AGENTLENS_RATE_LIMIT must be at least 1")


@dataclass(frozen=True)
class WorkerSettings:
    """Background worker configuration."""

    concurrency: int = 1
    poll_interval_seconds: float = 1.0
    heartbeat_interval_seconds: float = 15.0
    heartbeat_ttl_seconds: float = 45.0
    lease_duration_seconds: float = 300.0
    shutdown_timeout_seconds: float = 30.0

    def validate(self, environment: Environment) -> None:
        if self.concurrency < 1:
            raise ConfigurationError("AGENTLENS_WORKER_CONCURRENCY must be at least 1")
        if self.poll_interval_seconds <= 0:
            raise ConfigurationError("AGENTLENS_WORKER_POLL_INTERVAL must be positive")
        if self.heartbeat_interval_seconds <= 0:
            raise ConfigurationError("AGENTLENS_HEARTBEAT_INTERVAL must be positive")
        if self.heartbeat_ttl_seconds <= self.heartbeat_interval_seconds:
            raise ConfigurationError("AGENTLENS_HEARTBEAT_TTL must be greater than interval")
        if self.shutdown_timeout_seconds <= 0:
            raise ConfigurationError("AGENTLENS_SHUTDOWN_TIMEOUT must be positive")


@dataclass(frozen=True)
class AgentLensSettings:
    """Master production settings loaded from environment."""

    environment: Environment = Environment.DEVELOPMENT
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)
    auth: AuthSettings = field(default_factory=AuthSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    worker: WorkerSettings = field(default_factory=WorkerSettings)

    def validate(self) -> None:
        """Execute fail-fast validation for all settings."""
        self.database.validate(self.environment)
        self.redis.validate(self.environment)
        self.auth.validate(self.environment)
        self.server.validate(self.environment)
        self.worker.validate(self.environment)

    @classmethod
    def load_from_env(cls) -> AgentLensSettings:
        """Load and validate settings from environment variables."""
        environment = Environment.from_str(os.environ.get("AGENTLENS_ENVIRONMENT"))

        db_url = os.environ.get(
            "AGENTLENS_DATABASE_URL",
            "postgresql+psycopg://agentlens:agentlens@127.0.0.1:55432/agentlens",
        )
        pool_size = int(os.environ.get("AGENTLENS_DB_POOL_SIZE", "20"))
        max_overflow = int(os.environ.get("AGENTLENS_DB_MAX_OVERFLOW", "10"))
        pool_timeout = float(os.environ.get("AGENTLENS_DB_POOL_TIMEOUT", "30.0"))
        database = DatabaseSettings(
            url=db_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout_seconds=pool_timeout,
        )

        redis_url_raw = os.environ.get("AGENTLENS_REDIS_URL")
        redis_url = (
            redis_url_raw
            if redis_url_raw is not None
            else ("redis://127.0.0.1:56379/0" if environment != Environment.TEST else None)
        )
        redis_timeout = float(os.environ.get("AGENTLENS_REDIS_TIMEOUT", "5.0"))
        redis = RedisSettings(url=redis_url, socket_timeout_seconds=redis_timeout)

        auth = AuthSettings(
            project_id=os.environ.get("AGENTLENS_PROJECT_ID", "default-project"),
            project_api_key=os.environ.get("AGENTLENS_PROJECT_API_KEY", "secret-api-key"),
            api_key_id=os.environ.get("AGENTLENS_API_KEY_ID", "default-key"),
        )

        cors_raw = os.environ.get("AGENTLENS_CORS_ORIGINS", "*")
        cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
        server = ServerSettings(
            host=os.environ.get("AGENTLENS_API_HOST", "0.0.0.0"),
            port=int(os.environ.get("AGENTLENS_API_PORT", "8000")),
            log_level=os.environ.get("AGENTLENS_LOG_LEVEL", "INFO"),
            log_format=os.environ.get(
                "AGENTLENS_LOG_FORMAT",
                "json" if environment in (Environment.PRODUCTION, Environment.STAGING) else "text",
            ),
            max_request_bytes=int(os.environ.get("AGENTLENS_MAX_REQUEST_BYTES", "10485760")),
            rate_limit_per_minute=int(os.environ.get("AGENTLENS_RATE_LIMIT", "1000")),
            rate_window_seconds=int(os.environ.get("AGENTLENS_RATE_WINDOW", "60")),
            cors_allowed_origins=cors_origins,
        )

        worker = WorkerSettings(
            concurrency=int(os.environ.get("AGENTLENS_WORKER_CONCURRENCY", "1")),
            poll_interval_seconds=float(os.environ.get("AGENTLENS_WORKER_POLL_INTERVAL", "1.0")),
            heartbeat_interval_seconds=float(
                os.environ.get("AGENTLENS_HEARTBEAT_INTERVAL", "15.0")
            ),
            heartbeat_ttl_seconds=float(os.environ.get("AGENTLENS_HEARTBEAT_TTL", "45.0")),
            lease_duration_seconds=float(os.environ.get("AGENTLENS_LEASE_DURATION", "300.0")),
            shutdown_timeout_seconds=float(os.environ.get("AGENTLENS_SHUTDOWN_TIMEOUT", "30.0")),
        )

        settings = cls(
            environment=environment,
            database=database,
            redis=redis,
            auth=auth,
            server=server,
            worker=worker,
        )
        settings.validate()
        return settings

    def to_safe_dict(self) -> dict[str, Any]:
        """Produce a telemetry/logging safe dictionary with secrets masked."""
        return {
            "environment": self.environment.value,
            "database": {
                "url": _mask_url_password(self.database.url),
                "pool_size": self.database.pool_size,
                "max_overflow": self.database.max_overflow,
                "pool_timeout_seconds": self.database.pool_timeout_seconds,
            },
            "redis": {
                "url": _mask_url_password(self.redis.url),
                "socket_timeout_seconds": self.redis.socket_timeout_seconds,
            },
            "auth": {
                "project_id": self.auth.project_id,
                "project_api_key": _mask_secret(self.auth.project_api_key),
                "api_key_id": self.auth.api_key_id,
            },
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "log_level": self.server.log_level,
                "log_format": self.server.log_format,
                "max_request_bytes": self.server.max_request_bytes,
                "rate_limit_per_minute": self.server.rate_limit_per_minute,
                "rate_window_seconds": self.server.rate_window_seconds,
                "cors_allowed_origins": self.server.cors_allowed_origins,
            },
            "worker": {
                "concurrency": self.worker.concurrency,
                "poll_interval_seconds": self.worker.poll_interval_seconds,
                "heartbeat_interval_seconds": self.worker.heartbeat_interval_seconds,
                "heartbeat_ttl_seconds": self.worker.heartbeat_ttl_seconds,
                "lease_duration_seconds": self.worker.lease_duration_seconds,
                "shutdown_timeout_seconds": self.worker.shutdown_timeout_seconds,
            },
        }
