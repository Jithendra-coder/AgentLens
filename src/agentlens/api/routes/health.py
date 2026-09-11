"""Cheap unauthenticated health, readiness, liveness, and startup endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Process liveness probe."""
    return {"status": "ok"}


@router.get("/health/startup")
async def startup(request: Request) -> JSONResponse:
    """Startup probe for container orchestrators during container bootstrap."""
    gateway = getattr(request.app.state, "gateway", None)
    if gateway is None:
        return JSONResponse(status_code=503, content={"status": "initializing"})

    checker = getattr(gateway.repository, "check_ready", None)
    db_ok = bool(checker()) if callable(checker) else True

    if db_ok:
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "service": "agentlens-api", "initialized": True},
        )
    return JSONResponse(
        status_code=503,
        content={"status": "initializing", "service": "agentlens-api", "database": "unavailable"},
    )


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Dependency readiness probe."""
    gateway = request.app.state.gateway
    rate_checker = getattr(gateway.rate_limiter, "check_ready", None)
    if callable(rate_checker):
        rate_checker()
    database_ready = all(
        component is not None
        for component in (
            gateway.config,
            gateway.authenticator,
            gateway.repository,
            gateway.rate_limiter,
        )
    )
    checker = getattr(gateway.repository, "check_ready", None)
    if database_ready and callable(checker):
        database_ready = bool(checker())
    if not gateway.evaluation_enabled:
        rate_health = getattr(gateway.rate_limiter, "health", "local")
        if rate_health == "local":
            return JSONResponse(
                status_code=200 if database_ready else 503,
                content={"status": "ok" if database_ready else "unavailable"},
            )
        return JSONResponse(
            status_code=200 if database_ready else 503,
            content={
                "status": "ok" if database_ready and rate_health == "shared" else "degraded",
                "rate_limit": rate_health,
            },
        )
    queue_checker = getattr(gateway.dispatcher, "check_ready", None)
    queue_ready = bool(queue_checker()) if callable(queue_checker) else False
    if not database_ready:
        status = "unavailable"
        status_code = 503
    elif queue_ready:
        status = "ok"
        status_code = 200
    else:
        # Trace ingestion remains usable while the evaluation wakeup path is down.
        status = "degraded"
        status_code = 200
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "database": "ok" if database_ready else "unavailable",
            "evaluation_queue": "ok" if queue_ready else "unavailable",
            "rate_limit": getattr(gateway.rate_limiter, "health", "local"),
        },
    )
