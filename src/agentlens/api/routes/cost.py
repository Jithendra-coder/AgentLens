"""Cost intelligence and budget API routes ."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentlens.api.auth import AuthContext
from agentlens.api.dependencies import require_auth
from agentlens.api.errors import GatewayError
from agentlens.cost.budget import BudgetEvaluator
from agentlens.cost.models import CostBudget
from agentlens.cost.repository import CostRepository, InMemoryCostRepository

router = APIRouter()
AUTH_DEP = Depends(require_auth)


class CreateBudgetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    amount_usd: float = Field(gt=0.0)
    period: str = Field(default="monthly", pattern="^(daily|monthly)$")
    alert_threshold_pct: float = Field(default=80.0, gt=0.0, le=100.0)
    notification_webhook_url: str | None = Field(default=None, max_length=512)


def _cost_repo(request: Request) -> CostRepository:
    repo = getattr(request.app.state.gateway, "cost_repository", None)
    if repo is None:
        repo = InMemoryCostRepository()
        request.app.state.gateway.cost_repository = repo
    return repo


@router.get("/v1/projects/{project_id}/cost/summary")
async def get_project_cost_summary(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _cost_repo(request)
    summary = repo.get_cost_summary(project_id)

    return JSONResponse(
        status_code=200,
        content={
            "project_id": summary.project_id,
            "total_cost_usd": summary.total_cost_usd,
            "total_tokens": summary.total_tokens,
            "by_model": [
                {
                    "dimension_key": item.dimension_key,
                    "cost_usd": item.cost_usd,
                    "input_tokens": item.input_tokens,
                    "output_tokens": item.output_tokens,
                    "total_tokens": item.total_tokens,
                    "percentage": item.percentage,
                }
                for item in summary.by_model
            ],
        },
    )


@router.post("/v1/projects/{project_id}/budgets")
async def create_project_budget(
    project_id: str,
    body: CreateBudgetRequest,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _cost_repo(request)
    budget = CostBudget(
        budget_id=uuid4(),
        project_id=project_id,
        name=body.name,
        amount_usd=body.amount_usd,
        period=body.period,
        alert_threshold_pct=body.alert_threshold_pct,
        notification_webhook_url=body.notification_webhook_url,
    )
    saved = repo.save_budget(budget)

    return JSONResponse(
        status_code=200,
        content={
            "budget_id": str(saved.budget_id),
            "project_id": saved.project_id,
            "name": saved.name,
            "amount_usd": saved.amount_usd,
            "period": saved.period,
            "alert_threshold_pct": saved.alert_threshold_pct,
            "notification_webhook_url": saved.notification_webhook_url,
            "created_at": saved.created_at.isoformat(),
        },
    )


@router.get("/v1/projects/{project_id}/budgets")
async def list_project_budgets(
    project_id: str,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _cost_repo(request)
    budgets = repo.list_budgets(project_id)
    summary = repo.get_cost_summary(project_id)

    evaluator = BudgetEvaluator()
    items = []
    for b in budgets:
        status = evaluator.evaluate(b, summary.total_cost_usd)
        items.append({
            "budget_id": str(b.budget_id),
            "project_id": b.project_id,
            "name": b.name,
            "amount_usd": b.amount_usd,
            "period": b.period,
            "alert_threshold_pct": b.alert_threshold_pct,
            "current_spend_usd": status.current_spend_usd,
            "burn_percentage": status.burn_percentage,
            "is_breached": status.is_breached,
            "alert_triggered": status.alert_triggered,
            "created_at": b.created_at.isoformat(),
        })

    return JSONResponse(status_code=200, content={"budgets": items})


@router.delete("/v1/projects/{project_id}/budgets/{budget_id}")
async def delete_project_budget(
    project_id: str,
    budget_id: UUID,
    request: Request,
    context: AuthContext = AUTH_DEP,
) -> JSONResponse:
    repo = _cost_repo(request)
    budget = repo.get_budget(budget_id)
    if budget is None or budget.project_id != project_id:
        raise GatewayError(code="not_found", message="Budget not found.", status_code=404)
    deleted = repo.delete_budget(budget_id)
    return JSONResponse(status_code=200, content={"deleted": deleted})
