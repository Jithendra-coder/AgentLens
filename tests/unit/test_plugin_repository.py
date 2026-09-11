"""Unit tests for CustomEvaluatorRepository operations."""

from __future__ import annotations

from uuid import uuid4

from agentlens.evaluation.plugins.models import CustomEvaluatorPlugin
from agentlens.evaluation.plugins.repository import InMemoryCustomEvaluatorRepository


def test_in_memory_custom_evaluator_repository_lifecycle() -> None:
    repo = InMemoryCustomEvaluatorRepository()

    plugin_id = uuid4()
    plugin = CustomEvaluatorPlugin(
        plugin_id=plugin_id,
        project_id="proj-alpha",
        name="custom.latency_filter",
        version="1.0.0",
        evaluator_type="deterministic",
        description="Filters latency outliers",
        code_body="def evaluate(context, parameters): return CustomEvaluationOutput(1.0, True)",
    )

    saved = repo.save_plugin(plugin)
    assert saved.plugin_id == plugin_id

    fetched = repo.get_plugin(plugin_id)
    assert fetched is not None
    assert fetched.name == "custom.latency_filter"

    found = repo.find_by_name("proj-alpha", "custom.latency_filter", "1.0.0")
    assert found is not None
    assert found.plugin_id == plugin_id

    plugins = repo.list_plugins("proj-alpha")
    assert len(plugins) == 1

    assert repo.delete_plugin(plugin_id) is True
    assert repo.get_plugin(plugin_id) is None
