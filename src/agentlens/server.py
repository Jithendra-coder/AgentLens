"""Production-ready environment-configured FastAPI gateway entry point."""

from __future__ import annotations

import logging

from agentlens.api import GatewayConfig, InMemoryApiKeyAuthenticator, create_app
from agentlens.config import AgentLensSettings
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.lifecycle import LifecycleCoordinator
from agentlens.logging import configure_logging
from agentlens.regression.runtime import RegressionRuntimeConfig
from agentlens.replay.runtime import ReplayRuntimeConfig
from agentlens.storage import DatabaseConfig

# Load settings and configure structured logging
settings = AgentLensSettings.load_from_env()
configure_logging(
    log_level=settings.server.log_level,
    json_format=(settings.server.log_format == "json"),
)

logger = logging.getLogger("agentlens.server")
logger.info("server_initializing", extra={"settings": settings.to_safe_dict()})

lifecycle = LifecycleCoordinator(
    shutdown_timeout_seconds=settings.worker.shutdown_timeout_seconds
)

# Configure API Key Authenticator
authenticator = InMemoryApiKeyAuthenticator()
authenticator.register(
    api_key=settings.auth.project_api_key,
    key_id=settings.auth.api_key_id,
    project_id=settings.auth.project_id,
)

# Configure Gateway and Runtimes
gateway_config = GatewayConfig(
    max_request_bytes=settings.server.max_request_bytes,
    rate_limit=settings.server.rate_limit_per_minute,
    rate_window_seconds=settings.server.rate_window_seconds,
)

redis_url = settings.redis.url
runtime = EvaluationRuntimeConfig(redis_url=redis_url) if redis_url else None
replay_runtime = ReplayRuntimeConfig(redis_url=redis_url) if redis_url else None
regression_runtime = RegressionRuntimeConfig(redis_url=redis_url) if redis_url else None

database_config = DatabaseConfig(settings.database.url)

app = create_app(
    config=gateway_config,
    database=database_config,
    authenticator=authenticator,
    runtime_config=runtime,
    replay_runtime_config=replay_runtime,
    regression_runtime_config=regression_runtime,
)

app.state.lifecycle = lifecycle
app.state.settings = settings
