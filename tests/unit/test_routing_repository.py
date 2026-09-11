"""Unit tests for InMemoryRoutingRepository lifecycle and decision storage."""

from __future__ import annotations

from uuid import uuid4

from agentlens.routing.models import RoutingDecision, RoutingRule
from agentlens.routing.repository import InMemoryRoutingRepository


def test_in_memory_routing_repository_lifecycle() -> None:
    repo = InMemoryRoutingRepository()
    rule_id = uuid4()

    rule = RoutingRule(
        rule_id=rule_id,
        project_id="proj-route-repo",
        name="Code Rule",
        task_type="code",
        min_quality_score=0.90,
    )

    # 1. Save and get
    saved = repo.save_rule(rule)
    assert saved.rule_id == rule_id

    fetched = repo.get_rule(rule_id)
    assert fetched is not None
    assert fetched.name == "Code Rule"

    # 2. List
    rules = repo.list_rules("proj-route-repo")
    assert len(rules) == 1

    # 3. Record decision
    dec = RoutingDecision(
        decision_id=uuid4(),
        project_id="proj-route-repo",
        selected_model="gpt-4o",
        selected_provider="openai",
        estimated_cost_usd=0.005,
        reason="Test escalation",
    )
    repo.record_decision(dec)

    decisions = repo.list_decisions("proj-route-repo")
    assert len(decisions) == 1
    assert decisions[0].selected_model == "gpt-4o"

    # 4. Delete
    assert repo.delete_rule(rule_id) is True
    assert repo.get_rule(rule_id) is None
