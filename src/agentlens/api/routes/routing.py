"""Routing API endpoints ."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.routing.engine import AdaptiveRouter
from agentlens.routing.models import RouteRequest, RoutingDecision, RoutingRule
from agentlens.routing.repository import (
    InMemoryRoutingRepository,
    RoutingRepository,
)

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class CreateRoutingRuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    task_type: str = Field(default="general", pattern="^(general|code|rag|extraction|reasoning)$")
    min_quality_score: float = Field(default=0.8, ge=0.0, le=1.0)
    max_cost_per_1k: float = Field(default=0.05, ge=0.0)
    max_latency_ms: float = Field(default=2000.0, ge=0.0)
    fallback_model: str = Field(default="gpt-4o")
    tier_priority: list[str] = Field(
        default_factory=lambda: ["gpt-4o-mini", "claude-3-5-haiku", "gpt-4o", "claude-3-5-sonnet"]
    )
    is_active: bool = Field(default=True)


class RoutePromptRequest(BaseModel):
    prompt: str = Field(min_length=1)
    trace_id: UUID | None = Field(default=None)
    max_latency_ms: float | None = Field(default=None)
    min_quality_score: float | None = Field(default=None)


def _routing_repo(request: Request) -> RoutingRepository:
    repo = getattr(request.app.state.gateway, "routing_repository", None)
    if repo is None:
        repo = InMemoryRoutingRepository()
        request.app.state.gateway.routing_repository = repo
    return repo


@router.post("/v1/projects/{project_id}/routing/rules")
async def create_routing_rule(
    project_id: str,
    body: CreateRoutingRuleRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _routing_repo(request)
    rule = RoutingRule(
        rule_id=uuid4(),
        project_id=project_id,
        name=body.name,
        task_type=body.task_type,
        min_quality_score=body.min_quality_score,
        max_cost_per_1k=body.max_cost_per_1k,
        max_latency_ms=body.max_latency_ms,
        fallback_model=body.fallback_model,
        tier_priority=tuple(body.tier_priority),
        is_active=body.is_active,
    )
    saved = repo.save_rule(rule)

    return JSONResponse(
        status_code=200,
        content={
            "rule_id": str(saved.rule_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "task_type": saved.task_type,
            "min_quality_score": saved.min_quality_score,
            "max_cost_per_1k": saved.max_cost_per_1k,
            "max_latency_ms": saved.max_latency_ms,
            "fallback_model": saved.fallback_model,
            "tier_priority": list(saved.tier_priority),
            "is_active": saved.is_active,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/routing/rules")
async def list_routing_rules(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _routing_repo(request)
    rules = repo.list_rules(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "rules": [
                {
                    "rule_id": str(r.rule_id),
                    "project_id": r.project_id,
                    "name": r.name,
                    "task_type": r.task_type,
                    "min_quality_score": r.min_quality_score,
                    "max_cost_per_1k": r.max_cost_per_1k,
                    "max_latency_ms": r.max_latency_ms,
                    "fallback_model": r.fallback_model,
                    "tier_priority": list(r.tier_priority),
                    "is_active": r.is_active,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rules
            ]
        },
    )


@router.delete("/v1/projects/{project_id}/routing/rules/{rule_id}")
async def delete_routing_rule(
    project_id: str,
    rule_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _routing_repo(request)
    rule = repo.get_rule(rule_id)
    if rule is None or rule.project_id != project_id:
        raise GatewayError(code="not_found", message="Routing rule not found.", status_code=404)
    deleted = repo.delete_rule(rule_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/v1/projects/{project_id}/routing/route")
async def route_prompt(
    project_id: str,
    body: RoutePromptRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _routing_repo(request)
    rules = repo.list_rules(project_id)

    router_engine = AdaptiveRouter()
    route_req = RouteRequest(
        project_id=project_id,
        prompt=body.prompt,
        trace_id=body.trace_id,
        max_latency_ms=body.max_latency_ms,
        min_quality_score=body.min_quality_score,
    )
    result = router_engine.route(route_req, rules)

    # Record decision audit
    decision = RoutingDecision(
        decision_id=uuid4(),
        project_id=project_id,
        trace_id=body.trace_id,
        rule_id=result.rule_id,
        selected_model=result.selected_model,
        selected_provider=result.selected_provider,
        estimated_cost_usd=result.estimated_cost_per_1k,
        reason=result.reason,
    )
    repo.record_decision(decision)

    return JSONResponse(
        status_code=200,
        content={
            "selected_model": result.selected_model,
            "selected_provider": result.selected_provider,
            "task_type": result.task_type,
            "complexity_score": result.complexity_score,
            "estimated_cost_per_1k": result.estimated_cost_per_1k,
            "reason": result.reason,
            "rule_id": str(result.rule_id) if result.rule_id else None,
        },
    )


@router.get("/v1/projects/{project_id}/routing/decisions")
async def list_routing_decisions(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _routing_repo(request)
    decisions = repo.list_decisions(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "decisions": [
                {
                    "decision_id": str(d.decision_id),
                    "project_id": d.project_id,
                    "trace_id": str(d.trace_id) if d.trace_id else None,
                    "rule_id": str(d.rule_id) if d.rule_id else None,
                    "selected_model": d.selected_model,
                    "selected_provider": d.selected_provider,
                    "estimated_cost_usd": d.estimated_cost_usd,
                    "reason": d.reason,
                    "decided_at": d.decided_at.isoformat(),
                }
                for d in decisions
            ]
        },
    )
