"""FastAPI application factory for the AgentLens gateway and runtimes."""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agentlens.alerting.repository import (
    AlertingRepository,
    InMemoryAlertingRepository,
    PostgresAlertingRepository,
)
from agentlens.analytics.repository import (
    AnalyticsRepository,
    InMemoryAnalyticsRepository,
    PostgresAnalyticsRepository,
)
from agentlens.benchmarking.repository import (
    BenchmarkRepository,
    InMemoryBenchmarkRepository,
    PostgresBenchmarkRepository,
)
from agentlens.cost.repository import (
    CostRepository,
    InMemoryCostRepository,
    PostgresCostRepository,
)
from agentlens.evaluation import (
    EvaluationSuiteRepository,
    InMemoryEvaluationSuiteRepository,
    PostgresEvaluationSuiteRepository,
)
from agentlens.evaluation.config import EvaluationRuntimeConfig
from agentlens.evaluation.handlers import HandlerRegistry
from agentlens.evaluation.judges import SemanticJudge
from agentlens.evaluation.plugins import (
    CustomEvaluatorRepository,
    InMemoryCustomEvaluatorRepository,
    PostgresCustomEvaluatorRepository,
)
from agentlens.evaluation.redis import (
    EvaluationDispatcher,
    RedisDispatcher,
    UnavailableDispatcher,
)
from agentlens.evaluation.repository import (
    EvaluationJobRepository,
    PostgresEvaluationJobRepository,
)
from agentlens.evaluation.result_repository import (
    EvaluationResultRepository,
    PostgresEvaluationResultRepository,
)
from agentlens.experimentation.repository import (
    ExperimentRepository,
    InMemoryExperimentRepository,
    PostgresExperimentRepository,
)
from agentlens.governance.repository import (
    GovernanceRepository,
    InMemoryGovernanceRepository,
    PostgresGovernanceRepository,
)
from agentlens.monitoring.repository import (
    InMemoryMonitoringRepository,
    MonitoringRepository,
    PostgresMonitoringRepository,
)
from agentlens.quality_gates.repository import PostgresQualityGateRepository
from agentlens.rbac import InMemoryRbacRepository, PostgresRbacRepository, RbacRepository
from agentlens.rca.repository import (
    InMemoryRCARepository,
    PostgresRCARepository,
    RCARepository,
)
from agentlens.regression.drift.repository import (
    DriftRepository,
    InMemoryDriftRepository,
    PostgresDriftRepository,
)
from agentlens.regression.repository import PostgresRegressionRepository
from agentlens.regression.runtime import (
    RedisRegressionDispatcher,
    RegressionDispatcher,
    RegressionRuntimeConfig,
    UnavailableRegressionDispatcher,
)
from agentlens.replay.repository import PostgresReplayRepository
from agentlens.replay.runtime import (
    RedisReplayDispatcher,
    ReplayDispatcher,
    ReplayRuntimeConfig,
    UnavailableReplayDispatcher,
)
from agentlens.replay.targets import (
    LOCAL_TARGET_PROFILE_ID,
    LocalEchoReplayTarget,
    ReplayTargetProfile,
    TrustedReplayTargetRegistry,
)
from agentlens.routing.repository import (
    InMemoryRoutingRepository,
    PostgresRoutingRepository,
    RoutingRepository,
)
from agentlens.security import (
    InMemorySecretStore,
    InMemoryUserRepository,
    PostgresSecretStore,
    PostgresUserRepository,
    SecretStore,
    UserRepository,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.repository import PostgresTraceRepository, TraceQueryRepository

from .auth import ApiKeyAuthenticator, InMemoryApiKeyAuthenticator, RbacApiKeyAuthenticator
from .config import GatewayConfig
from .errors import GatewayError, error_response_body
from .middleware import RequestMiddleware
from .rate_limit import InMemoryRateLimiter, RedisRateLimiter
from .routes.alerting import router as alerting_router
from .routes.analytics import router as analytics_router
from .routes.auth import router as auth_router
from .routes.benchmarking import router as benchmarking_router
from .routes.cost import router as cost_router
from .routes.custom_evaluators import router as custom_evaluators_router
from .routes.datasets import router as datasets_router
from .routes.drift import router as drift_router
from .routes.evaluation_suites import router as evaluation_suites_router
from .routes.evaluations import router as evaluations_router
from .routes.experiments import router as experiments_router
from .routes.governance import router as governance_router
from .routes.health import router as health_router
from .routes.monitoring import router as monitoring_router
from .routes.providers import router as providers_router
from .routes.quality_gates import router as quality_gates_router
from .routes.query import router as query_router
from .routes.rag import router as rag_router
from .routes.raglens import raglens_router
from .routes.rca import router as rca_router
from .routes.readiness import router as readiness_router
from .routes.regressions import router as regressions_router
from .routes.replays import router as replays_router
from .routes.routing import router as routing_router
from .routes.secrets import router as secrets_router
from .routes.system import router as system_router
from .routes.tenancy import router as tenancy_router
from .routes.traces import router as traces_router
from .sink import InMemoryTraceSink, TraceIngestionSink


class _GatewayComponents:
    def __init__(
        self,
        config: Any,
        authenticator: Any,
        sink: Any,
        repository: Any,
        rate_limiter: Any,
        job_repository: Any,
        result_repository: Any,
        analytics_repository: Any,
        dispatcher: Any,
        handler_registry: HandlerRegistry,
        runtime_config: EvaluationRuntimeConfig | None,
        evaluation_enabled: bool,
        replay_repository: Any,
        replay_dispatcher: ReplayDispatcher,
        replay_target_registry: TrustedReplayTargetRegistry,
        replay_runtime_config: ReplayRuntimeConfig | None,
        regression_repository: Any,
        regression_dispatcher: RegressionDispatcher,
        regression_runtime_config: RegressionRuntimeConfig | None,
        quality_gate_repository: Any,
        rbac_repository: Any = None,
        secret_store: Any = None,
        user_repository: Any = None,
        suite_repository: Any = None,
        custom_evaluator_repository: Any = None,
        cost_repository: Any = None,
        experiment_repository: Any = None,
        routing_repository: Any = None,
        benchmark_repository: Any = None,
        drift_repository: Any = None,
        monitoring_repository: Any = None,
        alerting_repository: Any = None,
        rca_repository: Any = None,
        governance_repository: Any = None,
    ) -> None:
        self.config = config
        self.authenticator = authenticator
        self.sink = sink
        self.repository = repository
        self.rate_limiter = rate_limiter
        self.job_repository = job_repository
        self.result_repository = result_repository
        self.analytics_repository = analytics_repository
        self.dispatcher = dispatcher
        self.handler_registry = handler_registry
        self.runtime_config = runtime_config
        self.evaluation_enabled = evaluation_enabled
        self.replay_repository = replay_repository
        self.replay_dispatcher = replay_dispatcher
        self.replay_target_registry = replay_target_registry
        self.replay_runtime_config = replay_runtime_config
        self.regression_repository = regression_repository
        self.regression_dispatcher = regression_dispatcher
        self.regression_runtime_config = regression_runtime_config
        self.quality_gate_repository = quality_gate_repository
        self.rbac_repository = rbac_repository
        self.secret_store = secret_store
        self.user_repository = user_repository
        self.suite_repository = suite_repository
        self.custom_evaluator_repository = custom_evaluator_repository
        self.cost_repository = cost_repository
        self.experiment_repository = experiment_repository
        self.routing_repository = routing_repository
        self.benchmark_repository = benchmark_repository
        self.drift_repository = drift_repository
        self.monitoring_repository = monitoring_repository
        self.alerting_repository = alerting_repository
        self.rca_repository = rca_repository
        self.governance_repository = governance_repository


def create_app(
    *,
    config: GatewayConfig | None = None,
    authenticator: ApiKeyAuthenticator | None = None,
    sink: TraceIngestionSink | None = None,
    rate_limiter: Any | None = None,
    repository: TraceQueryRepository | None = None,
    database: DatabaseConfig | None = None,
    job_repository: EvaluationJobRepository | None = None,
    result_repository: EvaluationResultRepository | None = None,
    analytics_repository: AnalyticsRepository | None = None,
    dispatcher: EvaluationDispatcher | None = None,
    handler_registry: HandlerRegistry | None = None,
    semantic_judge: SemanticJudge | None = None,
    runtime_config: EvaluationRuntimeConfig | None = None,
    replay_repository: Any | None = None,
    replay_dispatcher: ReplayDispatcher | None = None,
    replay_target_registry: TrustedReplayTargetRegistry | None = None,
    replay_runtime_config: ReplayRuntimeConfig | None = None,
    regression_repository: Any | None = None,
    regression_dispatcher: RegressionDispatcher | None = None,
    regression_runtime_config: RegressionRuntimeConfig | None = None,
    quality_gate_repository: Any | None = None,
    rbac_repository: RbacRepository | None = None,
    secret_store: SecretStore | None = None,
    user_repository: UserRepository | None = None,
    suite_repository: EvaluationSuiteRepository | None = None,
    custom_evaluator_repository: CustomEvaluatorRepository | None = None,
    cost_repository: CostRepository | None = None,
    experiment_repository: ExperimentRepository | None = None,
    routing_repository: RoutingRepository | None = None,
    benchmark_repository: BenchmarkRepository | None = None,
    drift_repository: DriftRepository | None = None,
    monitoring_repository: MonitoringRepository | None = None,
    alerting_repository: AlertingRepository | None = None,
    rca_repository: RCARepository | None = None,
    governance_repository: GovernanceRepository | None = None,
) -> FastAPI:
    """Create an injectable AgentLens gateway application without global state."""

    if repository is not None and (sink is not None or database is not None):
        raise ValueError("provide repository, sink, or database, not multiple")
    if sink is not None and database is not None:
        raise ValueError("provide sink or database, not both")

    gateway_config = config if config is not None else GatewayConfig()
    gateway_repository: Any
    if repository is not None:
        gateway_repository = repository
    elif database is not None:
        gateway_repository = PostgresTraceRepository(database)
    else:
        gateway_repository = sink if sink is not None else InMemoryTraceSink()
    gateway_sink = gateway_repository

    master_secret = os.environ.get(
        "AGENTLENS_MASTER_KEY",
        os.environ.get("AGENTLENS_SECRET_KEY", "dev-insecure-master-key-32-chars-long"),
    )
    gateway_rbac_repository: RbacRepository = (
        rbac_repository
        or (
            PostgresRbacRepository(database, engine=getattr(gateway_repository, "engine", None))
            if database is not None and hasattr(gateway_repository, "engine")
            else InMemoryRbacRepository()
        )
    )
    gateway_secret_store: SecretStore = (
        secret_store
        or (
            PostgresSecretStore(
                database,
                master_secret=master_secret,
                engine=getattr(gateway_repository, "engine", None),
            )
            if database is not None and hasattr(gateway_repository, "engine")
            else InMemorySecretStore(master_secret=master_secret)
        )
    )
    gateway_user_repository: UserRepository = (
        user_repository
        or (
            PostgresUserRepository(
                database,
                engine=getattr(gateway_repository, "engine", None),
            )
            if database is not None and hasattr(gateway_repository, "engine")
            else InMemoryUserRepository()
        )
    )
    if authenticator is not None:
        raw_authenticator = authenticator
    else:
        raw_authenticator = InMemoryApiKeyAuthenticator()
        raw_authenticator.register(
            api_key="dev-key-12345",
            key_id="key-default",
            project_id="proj-default",
        )
    gateway_authenticator = (
        raw_authenticator
        if isinstance(raw_authenticator, RbacApiKeyAuthenticator)
        else RbacApiKeyAuthenticator(gateway_rbac_repository, fallback=raw_authenticator)
    )
    evaluation_enabled = (
        runtime_config is not None or job_repository is not None or dispatcher is not None
    )
    gateway_job_repository: Any = job_repository
    if gateway_job_repository is None and database is not None:
        gateway_job_repository = PostgresEvaluationJobRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    gateway_result_repository: Any = result_repository
    if gateway_result_repository is None and database is not None:
        gateway_result_repository = PostgresEvaluationResultRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    gateway_analytics_repository: Any = analytics_repository
    if gateway_analytics_repository is None and database is not None:
        gateway_analytics_repository = PostgresAnalyticsRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    elif gateway_analytics_repository is None:
        gateway_analytics_repository = InMemoryAnalyticsRepository(sink=gateway_sink)
    gateway_replay_repository: Any = replay_repository
    if gateway_replay_repository is None and database is not None:
        gateway_replay_repository = PostgresReplayRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    gateway_regression_repository: Any = regression_repository
    if gateway_regression_repository is None and database is not None:
        gateway_regression_repository = PostgresRegressionRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    gateway_quality_gate_repository: Any = quality_gate_repository
    if gateway_quality_gate_repository is None and database is not None:
        gateway_quality_gate_repository = PostgresQualityGateRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    gateway_suite_repository: Any = suite_repository
    if (
        gateway_suite_repository is None
        and database is not None
        and hasattr(gateway_repository, "engine")
    ):
        gateway_suite_repository = PostgresEvaluationSuiteRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    elif gateway_suite_repository is None:
        gateway_suite_repository = InMemoryEvaluationSuiteRepository()
    gateway_custom_evaluator_repository: Any = custom_evaluator_repository
    if (
        gateway_custom_evaluator_repository is None
        and database is not None
        and hasattr(gateway_repository, "engine")
    ):
        gateway_custom_evaluator_repository = PostgresCustomEvaluatorRepository(
            database,
            engine=getattr(gateway_repository, "engine", None),
        )
    elif gateway_custom_evaluator_repository is None:
        gateway_custom_evaluator_repository = InMemoryCustomEvaluatorRepository()
    gateway_cost_repository: Any = cost_repository
    if gateway_cost_repository is None and database is not None:
        gateway_cost_repository = PostgresCostRepository(database)
    elif gateway_cost_repository is None:
        gateway_cost_repository = InMemoryCostRepository()
    gateway_experiment_repository: Any = experiment_repository
    if gateway_experiment_repository is None and database is not None:
        gateway_experiment_repository = PostgresExperimentRepository(database)
    elif gateway_experiment_repository is None:
        gateway_experiment_repository = InMemoryExperimentRepository()
    gateway_routing_repository: Any = routing_repository
    if gateway_routing_repository is None and database is not None:
        gateway_routing_repository = PostgresRoutingRepository(database)
    elif gateway_routing_repository is None:
        gateway_routing_repository = InMemoryRoutingRepository()
    gateway_benchmark_repository: Any = benchmark_repository
    if gateway_benchmark_repository is None and database is not None:
        gateway_benchmark_repository = PostgresBenchmarkRepository(database)
    elif gateway_benchmark_repository is None:
        gateway_benchmark_repository = InMemoryBenchmarkRepository()
    gateway_drift_repository: Any = drift_repository
    if gateway_drift_repository is None and database is not None:
        gateway_drift_repository = PostgresDriftRepository(database)
    elif gateway_drift_repository is None:
        gateway_drift_repository = InMemoryDriftRepository()
    gateway_monitoring_repository: Any = monitoring_repository
    if gateway_monitoring_repository is None and database is not None:
        gateway_monitoring_repository = PostgresMonitoringRepository(database)
    elif gateway_monitoring_repository is None:
        gateway_monitoring_repository = InMemoryMonitoringRepository()
    gateway_alerting_repository: Any = alerting_repository
    if gateway_alerting_repository is None and database is not None:
        gateway_alerting_repository = PostgresAlertingRepository(database)
    elif gateway_alerting_repository is None:
        gateway_alerting_repository = InMemoryAlertingRepository()
    gateway_rca_repository: Any = rca_repository
    if gateway_rca_repository is None and database is not None:
        gateway_rca_repository = PostgresRCARepository(database)
    elif gateway_rca_repository is None:
        gateway_rca_repository = InMemoryRCARepository()
    gateway_governance_repository: Any = governance_repository
    if gateway_governance_repository is None and database is not None:
        gateway_governance_repository = PostgresGovernanceRepository(database)
    elif gateway_governance_repository is None:
        gateway_governance_repository = InMemoryGovernanceRepository()
    gateway_dispatcher: Any = dispatcher
    if gateway_dispatcher is None:
        gateway_dispatcher = (
            RedisDispatcher(runtime_config)
            if runtime_config is not None
            else UnavailableDispatcher()
        )
    gateway_registry = (
        handler_registry
        if handler_registry is not None
        else HandlerRegistry(semantic_judge=semantic_judge)
    )
    gateway_replay_registry = replay_target_registry or TrustedReplayTargetRegistry()
    if replay_target_registry is None:
        gateway_replay_registry.register(
            ReplayTargetProfile(
                profile_id=LOCAL_TARGET_PROFILE_ID,
                name="Local Echo (test only)",
                target_type="local_echo",
                version="1",
                safety_class="sandbox",
            ),
            LocalEchoReplayTarget(),
        )
    gateway_replay_dispatcher: ReplayDispatcher
    if replay_dispatcher is None:
        gateway_replay_dispatcher = (
            RedisReplayDispatcher(replay_runtime_config)
            if replay_runtime_config is not None
            else UnavailableReplayDispatcher()
        )
    else:
        gateway_replay_dispatcher = replay_dispatcher
    gateway_regression_dispatcher: RegressionDispatcher
    if regression_dispatcher is None:
        gateway_regression_dispatcher = (
            RedisRegressionDispatcher(regression_runtime_config)
            if regression_runtime_config is not None
            else UnavailableRegressionDispatcher()
        )
    else:
        gateway_regression_dispatcher = regression_dispatcher
    redis_url = next(
        (
            runtime.redis_url
            for runtime in (runtime_config, replay_runtime_config, regression_runtime_config)
            if runtime is not None
        ),
        None,
    )
    gateway_rate_limiter = rate_limiter
    if gateway_rate_limiter is None and redis_url is not None:
        gateway_rate_limiter = RedisRateLimiter(
            redis_url=redis_url,
            max_requests=gateway_config.rate_limit,
            window_seconds=gateway_config.rate_window_seconds,
        )
    if gateway_rate_limiter is None:
        gateway_rate_limiter = InMemoryRateLimiter(
            max_requests=gateway_config.rate_limit,
            window_seconds=gateway_config.rate_window_seconds,
        )
    app = FastAPI(
        title="AgentLens Ingestion Gateway",
        version="1",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.gateway = _GatewayComponents(
        gateway_config,
        gateway_authenticator,
        gateway_sink,
        gateway_repository,
        gateway_rate_limiter,
        gateway_job_repository,
        gateway_result_repository,
        gateway_analytics_repository,
        gateway_dispatcher,
        gateway_registry,
        runtime_config,
        evaluation_enabled,
        gateway_replay_repository,
        gateway_replay_dispatcher,
        gateway_replay_registry,
        replay_runtime_config,
        gateway_regression_repository,
        gateway_regression_dispatcher,
        regression_runtime_config,
        gateway_quality_gate_repository,
        gateway_rbac_repository,
        gateway_secret_store,
        gateway_user_repository,
        gateway_suite_repository,
        gateway_custom_evaluator_repository,
        gateway_cost_repository,
        gateway_experiment_repository,
        gateway_routing_repository,
        gateway_benchmark_repository,
        gateway_drift_repository,
        gateway_monitoring_repository,
        gateway_alerting_repository,
        gateway_rca_repository,
        gateway_governance_repository,
    )
    app.add_middleware(RequestMiddleware, max_request_bytes=gateway_config.max_request_bytes)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(traces_router)
    app.include_router(rag_router)
    app.include_router(query_router)
    app.include_router(evaluations_router)
    app.include_router(evaluation_suites_router)
    app.include_router(custom_evaluators_router)
    app.include_router(analytics_router)
    app.include_router(datasets_router)
    app.include_router(replays_router)
    app.include_router(regressions_router)
    app.include_router(quality_gates_router)
    app.include_router(system_router)
    app.include_router(tenancy_router)
    app.include_router(secrets_router)
    app.include_router(providers_router)
    app.include_router(cost_router)
    app.include_router(experiments_router)
    app.include_router(routing_router)
    app.include_router(benchmarking_router)
    app.include_router(drift_router)
    app.include_router(monitoring_router)
    app.include_router(alerting_router)
    app.include_router(rca_router)
    app.include_router(governance_router)
    app.include_router(readiness_router)
    app.include_router(raglens_router)

    def _req_id(req: Request) -> str:
        try:
            return str(getattr(req.state, "request_id", None) or uuid4())
        except Exception:
            return str(uuid4())

    @app.exception_handler(GatewayError)
    async def handle_gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response_body(exc, _req_id(request)),
            headers=dict(exc.headers),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del exc
        error = GatewayError(
            code="invalid_request",
            message="Request is invalid.",
            status_code=400,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=error_response_body(error, _req_id(request)),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        error = GatewayError(
            code="method_not_allowed" if exc.status_code == 405 else "invalid_request",
            message="Method is not allowed." if exc.status_code == 405 else "Request is invalid.",
            status_code=exc.status_code,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=error_response_body(error, _req_id(request)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        del exc
        error = GatewayError(
            code="internal_error",
            message="Internal gateway error.",
            status_code=500,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=error_response_body(error, _req_id(request)),
        )

    return app
