"""Unit tests for InMemoryDriftRepository lifecycle."""

from __future__ import annotations

from uuid import uuid4

from agentlens.regression.drift.models import (
    DriftObservation,
    QualityBaseline,
)
from agentlens.regression.drift.repository import InMemoryDriftRepository


def test_in_memory_drift_repository_lifecycle() -> None:
    repo = InMemoryDriftRepository()
    baseline_id = uuid4()

    baseline = QualityBaseline(
        baseline_id=baseline_id,
        project_id="proj-drift-repo",
        name="Production Quality Baseline",
        metric_name="quality_score",
        baseline_mean=0.92,
    )

    # 1. Save & get baseline
    saved = repo.save_baseline(baseline)
    assert saved.baseline_id == baseline_id

    fetched = repo.get_baseline(baseline_id)
    assert fetched is not None
    assert fetched.name == "Production Quality Baseline"

    # 2. List baselines
    b_list = repo.list_baselines("proj-drift-repo")
    assert len(b_list) == 1

    # 3. Record & list observations
    obs = DriftObservation(
        drift_id=uuid4(),
        baseline_id=baseline_id,
        project_id="proj-drift-repo",
        observed_mean=0.75,
        z_score=-3.5,
        drift_magnitude_pct=-18.4,
        drift_type="quality_drop",
        is_alert=True,
    )
    repo.record_observation(obs)
    obs_list = repo.list_observations("proj-drift-repo", baseline_id=baseline_id)
    assert len(obs_list) == 1
    assert obs_list[0].is_alert is True

    # 4. Delete baseline
    assert repo.delete_baseline(baseline_id) is True
    assert repo.get_baseline(baseline_id) is None
    assert len(repo.list_observations("proj-drift-repo")) == 0
