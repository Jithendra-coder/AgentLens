"""Operational telemetry, Prometheus metrics exposition, and system overview routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.telemetry import get_metrics_registry

router = APIRouter()
AUTH_DEPENDENCY = Depends(require_auth)


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics() -> str:
    """Expose platform metrics in standard Prometheus text exposition format."""
    return get_metrics_registry().export_prometheus_text()


@router.get("/v1/system/metrics")
async def system_metrics_snapshot(
    auth: AuthContext = AUTH_DEPENDENCY,
) -> dict[str, Any]:
    """Authenticated endpoint returning instantaneous JSON telemetry snapshot."""
    del auth
    registry = get_metrics_registry()
    return registry.get_summary_snapshot()


@router.get("/v1/system/overview")
async def system_overview(
    request: Request,
    auth: AuthContext = AUTH_DEPENDENCY,
) -> dict[str, Any]:
    """Authenticated comprehensive operational health & diagnostic overview."""
    del auth
    gateway = request.app.state.gateway
    registry = get_metrics_registry()
    now_dt = datetime.now(UTC)

    # 1. DB & Redis Status
    checker = getattr(gateway.repository, "check_ready", None)
    db_ok = bool(checker()) if callable(checker) else True

    queue_checker = getattr(gateway.dispatcher, "check_ready", None)
    redis_ok = bool(queue_checker()) if callable(queue_checker) else False

    # 2. Worker Fleet Status
    heartbeat_repo = None
    if hasattr(gateway, "repository") and hasattr(gateway.repository, "engine"):
        from agentlens.storage.heartbeats import WorkerHeartbeatRepository

        engine = getattr(gateway.repository, "engine", None)
        if engine is not None:
            heartbeat_repo = WorkerHeartbeatRepository(gateway.config, engine=engine)

    workers_list: list[dict[str, Any]] = []
    if heartbeat_repo is not None:
        try:
            raw_workers = heartbeat_repo.list(limit=50, stale_after_seconds=45.0)
            for w in raw_workers:
                last_seen_dt = w.get("last_seen")
                age_s = (now_dt - last_seen_dt).total_seconds() if last_seen_dt else 0.0
                workers_list.append(
                    {
                        "worker_id": w.get("worker_id"),
                        "worker_type": w.get("worker_type"),
                        "started_at": (
                            w["started_at"].isoformat() if w.get("started_at") else None
                        ),
                        "last_seen": last_seen_dt.isoformat() if last_seen_dt else None,
                        "state": w.get("state"),
                        "health": w.get("health", "unknown"),
                        "heartbeat_age_seconds": round(max(0.0, age_s), 1),
                    }
                )
        except Exception:
            pass

    # 3. Queue Depths
    eval_pending = 0
    replay_pending = 0
    regression_pending = 0

    if hasattr(gateway, "job_repository") and gateway.job_repository is not None:
        count_fn = getattr(gateway.job_repository, "count_pending_jobs", None)
        if callable(count_fn):
            try:
                eval_pending = count_fn()
            except Exception:
                pass

    if hasattr(gateway, "replay_repository") and gateway.replay_repository is not None:
        count_fn = getattr(gateway.replay_repository, "count_pending_executions", None)
        if callable(count_fn):
            try:
                replay_pending = count_fn()
            except Exception:
                pass

    # Update gauge values
    registry.set_queue_depth("evaluation", eval_pending)
    registry.set_queue_depth("replay", replay_pending)
    registry.set_queue_depth("regression", regression_pending)

    # 4. Telemetry Snapshot
    telemetry = registry.get_summary_snapshot()

    return {
        "timestamp": now_dt.isoformat(),
        "service": "agentlens-platform",
        "infrastructure": {
            "database": {"status": "ok" if db_ok else "unavailable"},
            "redis": {
                "status": (
                    "ok" if redis_ok else ("unavailable" if gateway.runtime_config else "disabled")
                )
            },
        },
        "queues": {
            "evaluation_depth": eval_pending,
            "replay_depth": replay_pending,
            "regression_depth": regression_pending,
        },
        "telemetry": {
            "api_latency": telemetry["api_latency_summary"],
            "worker_latency": telemetry["worker_latency_summary"],
        },
        "workers": {
            "total_count": len(workers_list),
            "healthy_count": sum(1 for w in workers_list if w.get("health") == "healthy"),
            "stale_count": sum(1 for w in workers_list if w.get("health") == "stale"),
            "fleet": workers_list,
        },
    }
