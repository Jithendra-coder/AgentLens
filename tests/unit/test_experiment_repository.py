"""Unit tests for InMemoryExperimentRepository lifecycle and storage."""

from __future__ import annotations

from uuid import uuid4

from agentlens.experimentation.models import (
    Experiment,
    ExperimentEvaluation,
    ExperimentVariant,
)
from agentlens.experimentation.repository import InMemoryExperimentRepository


def test_in_memory_experiment_repository_lifecycle() -> None:
    repo = InMemoryExperimentRepository()
    exp_id = uuid4()
    v1 = ExperimentVariant(
        variant_id=uuid4(),
        experiment_id=exp_id,
        name="Control",
        is_control=True,
    )
    v2 = ExperimentVariant(
        variant_id=uuid4(),
        experiment_id=exp_id,
        name="Treatment",
        is_control=False,
    )
    exp = Experiment(
        experiment_id=exp_id,
        project_id="proj-exp-repo",
        name="Latency Benchmark Test",
        variants=(v1, v2),
    )

    # 1. Save and get
    saved = repo.save_experiment(exp)
    assert saved.experiment_id == exp_id

    fetched = repo.get_experiment(exp_id)
    assert fetched is not None
    assert fetched.name == "Latency Benchmark Test"
    assert len(fetched.variants) == 2

    # 2. List
    exp_list = repo.list_experiments("proj-exp-repo")
    assert len(exp_list) == 1

    # 3. Record evaluations
    ev = ExperimentEvaluation(
        eval_id=uuid4(),
        experiment_id=exp_id,
        variant_id=v1.variant_id,
        trace_id=uuid4(),
        score=0.95,
        cost_usd=0.002,
        latency_ms=450.0,
    )
    repo.record_evaluation(ev)

    evals = repo.list_evaluations(exp_id)
    assert len(evals) == 1
    assert evals[0].score == 0.95

    # 4. Delete
    assert repo.delete_experiment(exp_id) is True
    assert repo.get_experiment(exp_id) is None
    assert len(repo.list_evaluations(exp_id)) == 0
