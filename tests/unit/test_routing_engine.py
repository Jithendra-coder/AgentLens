"""Unit tests for AdaptiveRouter logic and tier selection."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agentlens.cost.pricing import PricingRegistry
from agentlens.routing.engine import AdaptiveRouter
from agentlens.routing.models import RouteRequest, RoutingRule


def test_routing_rule_invariants() -> None:
    with pytest.raises(ValueError, match="RoutingRule name cannot be empty"):
        RoutingRule(project_id="proj-1", name="")

    with pytest.raises(ValueError, match="min_quality_score must be between"):
        RoutingRule(project_id="proj-1", name="Rule", min_quality_score=1.5)


def test_adaptive_router_cost_optimization_vs_escalation() -> None:
    pricing = PricingRegistry()
    router = AdaptiveRouter(pricing)

    rule = RoutingRule(
        rule_id=uuid4(),
        project_id="proj-route",
        name="Default Adaptive",
        task_type="general",
        min_quality_score=0.80,
        tier_priority=("gpt-4o-mini", "claude-3-5-haiku", "gpt-4o", "claude-3-5-sonnet"),
        fallback_model="gpt-4o",
    )

    # 1. Simple query -> should route to cheapest model (gpt-4o-mini)
    simple_req = RouteRequest(
        project_id="proj-route",
        prompt="Hi, what is 2 + 2?",
    )
    r1 = router.route(simple_req, [rule])
    assert r1.selected_model == "gpt-4o-mini"
    assert r1.selected_provider == "openai"
    assert "cost-efficient" in r1.reason

    # 2. Complex reasoning query -> should escalate to frontier model (claude-3-5-sonnet or gpt-4o)
    complex_req = RouteRequest(
        project_id="proj-route",
        prompt="""
        Please prove step by step the convergence of gradient descent for strongly convex functions.
        Derive the exact bounds and explain the chain of thought in detail.
        """ * 5,
    )
    r2 = router.route(complex_req, [rule])
    assert r2.selected_model in ("gpt-4o", "claude-3-5-sonnet")
    assert "Escalated to frontier model" in r2.reason
