"""Unit tests for Twelve-Factor AgentLensSettings and fail-fast validation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from agentlens.config import (
    AgentLensSettings,
    AuthSettings,
    DatabaseSettings,
    Environment,
    RedisSettings,
    ServerSettings,
    WorkerSettings,
    _mask_secret,
    _mask_url_password,
)
from agentlens.exceptions import ConfigurationError


def test_environment_parsing() -> None:
    assert Environment.from_str("development") == Environment.DEVELOPMENT
    assert Environment.from_str("STAGING") == Environment.STAGING
    assert Environment.from_str("production") == Environment.PRODUCTION
    assert Environment.from_str("test") == Environment.TEST
    assert Environment.from_str(None) == Environment.DEVELOPMENT

    with pytest.raises(ConfigurationError, match="Invalid AGENTLENS_ENVIRONMENT"):
        Environment.from_str("invalid_env")


def test_default_settings_validation_passes() -> None:
    settings = AgentLensSettings()
    settings.validate()
    assert settings.environment == Environment.DEVELOPMENT
    assert settings.server.port == 8000
    assert settings.database.pool_size == 20


def test_database_validation() -> None:
    # Invalid scheme
    with pytest.raises(ConfigurationError, match="AGENTLENS_DATABASE_URL must begin with"):
        DatabaseSettings(url="mysql://user:pass@localhost/db").validate(Environment.DEVELOPMENT)

    # Empty URL
    with pytest.raises(ConfigurationError, match="AGENTLENS_DATABASE_URL is required"):
        DatabaseSettings(url="").validate(Environment.DEVELOPMENT)

    # Invalid pool size
    with pytest.raises(ConfigurationError, match="AGENTLENS_DB_POOL_SIZE must be at least 1"):
        DatabaseSettings(pool_size=0).validate(Environment.DEVELOPMENT)

    # Negative overflow
    with pytest.raises(ConfigurationError, match="AGENTLENS_DB_MAX_OVERFLOW cannot be negative"):
        DatabaseSettings(max_overflow=-1).validate(Environment.DEVELOPMENT)


def test_redis_validation() -> None:
    # Invalid scheme
    with pytest.raises(ConfigurationError, match="AGENTLENS_REDIS_URL must begin with"):
        RedisSettings(url="http://localhost:6379").validate(Environment.DEVELOPMENT)

    # Valid none
    RedisSettings(url=None).validate(Environment.DEVELOPMENT)


def test_auth_validation_in_production() -> None:
    # Default secret key rejected in production
    with pytest.raises(
        ConfigurationError, match="must be set to a secure key in production/staging"
    ):
        AuthSettings(project_api_key="secret-api-key").validate(Environment.PRODUCTION)

    # Short key rejected in production
    with pytest.raises(ConfigurationError, match="must be at least 16 characters"):
        AuthSettings(project_api_key="short_key").validate(Environment.PRODUCTION)

    # Valid key passes
    AuthSettings(project_api_key="valid_production_secret_key_12345").validate(
        Environment.PRODUCTION
    )


def test_server_and_worker_validation() -> None:
    with pytest.raises(ConfigurationError, match="Invalid port"):
        ServerSettings(port=99999).validate(Environment.DEVELOPMENT)

    with pytest.raises(ConfigurationError, match="Invalid AGENTLENS_LOG_LEVEL"):
        ServerSettings(log_level="VERBOSE").validate(Environment.DEVELOPMENT)

    with pytest.raises(ConfigurationError, match="Invalid AGENTLENS_LOG_FORMAT"):
        ServerSettings(log_format="xml").validate(Environment.DEVELOPMENT)

    with pytest.raises(ConfigurationError, match="AGENTLENS_WORKER_CONCURRENCY must be at least 1"):
        WorkerSettings(concurrency=0).validate(Environment.DEVELOPMENT)

    with pytest.raises(
        ConfigurationError, match="AGENTLENS_HEARTBEAT_TTL must be greater than interval"
    ):
        WorkerSettings(heartbeat_interval_seconds=30.0, heartbeat_ttl_seconds=20.0).validate(
            Environment.DEVELOPMENT
        )


def test_secret_masking() -> None:
    assert _mask_secret("short") == "***"
    assert _mask_secret("very_secret_api_key_123") == "ve...23"
    assert _mask_secret(None) == "<none>"

    assert _mask_url_password("postgresql://user:secret123@localhost:5432/db") == "postgresql://user:***@localhost:5432/db"
    assert _mask_url_password("redis://:redispass@localhost:6379/0") == "redis://:***@localhost:6379/0"


def test_load_from_env_success() -> None:
    env_vars = {
        "AGENTLENS_ENVIRONMENT": "staging",
        "AGENTLENS_DATABASE_URL": "postgresql+psycopg://user:pass@127.0.0.1:5432/testdb",
        "AGENTLENS_PROJECT_ID": "test-proj",
        "AGENTLENS_PROJECT_API_KEY": "staging_secret_key_123456",
        "AGENTLENS_API_PORT": "8080",
        "AGENTLENS_LOG_FORMAT": "json",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        settings = AgentLensSettings.load_from_env()
        assert settings.environment == Environment.STAGING
        assert settings.auth.project_id == "test-proj"
        assert settings.server.port == 8080
        safe_dict = settings.to_safe_dict()
        assert "***" in safe_dict["database"]["url"]
        assert "pass" not in safe_dict["database"]["url"]
