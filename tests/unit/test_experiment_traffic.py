"""Unit tests  TrafficSplitter and experiment domain models."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agentlens.experimentation.models import Experiment, ExperimentVariant
from agentlens.experimentation.splitter import TrafficSplitter


def test_experiment_and_variant_invariants() -> None:
    with pytest.raises(ValueError, match="Experiment name cannot be empty"):
        Experiment(project_id="proj-1", name="")

    with pytest.raises(ValueError, match="traffic_weight must be between"):
        ExperimentVariant(name="VarA", traffic_weight=1.5)


def test_traffic_splitter_deterministic_routing() -> None:
    exp_id = uuid4()
    v1 = ExperimentVariant(
        variant_id=uuid4(),
        experiment_id=exp_id,
        name="Control",
        traffic_weight=0.5,
        is_control=True,
    )
    v2 = ExperimentVariant(
        variant_id=uuid4(),
        experiment_id=exp_id,
        name="Treatment",
        traffic_weight=0.5,
        is_control=False,
    )

    exp = Experiment(
        experiment_id=exp_id,
        project_id="proj-exp",
        name="AB Test 1",
        variants=(v1, v2),
    )

    # Determinism: same key always maps to the same variant
    var_a1 = TrafficSplitter.select_variant(exp, "user-key-100")
    var_a2 = TrafficSplitter.select_variant(exp, "user-key-100")
    assert var_a1.variant_id == var_a2.variant_id

    # Traffic distribution across 1000 keys
    selected_counts: dict[str, int] = {"Control": 0, "Treatment": 0}
    for i in range(1000):
        chosen = TrafficSplitter.select_variant(exp, f"user-session-{i}")
        selected_counts[chosen.name] += 1

    # Should be close to 50/50 split (within 40-60% range)
    assert 400 <= selected_counts["Control"] <= 600
    assert 400 <= selected_counts["Treatment"] <= 600
