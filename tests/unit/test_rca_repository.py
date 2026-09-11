"""Unit tests for InMemoryRCARepository lifecycle."""

from __future__ import annotations

from uuid import uuid4

from agentlens.rca.models import RCAReport
from agentlens.rca.repository import InMemoryRCARepository


def test_in_memory_rca_repository_lifecycle() -> None:
    repo = InMemoryRCARepository()
    rca_id = uuid4()

    report = RCAReport(
        rca_id=rca_id,
        project_id="proj-rca-repo",
        failure_category="context_overflow",
        root_cause_summary="Context window 8k limit reached",
        recommended_action="Truncate conversation history",
        confidence_score=0.92,
    )

    # 1. Save & get report
    saved = repo.save_report(report)
    assert saved.rca_id == rca_id

    fetched = repo.get_report(rca_id)
    assert fetched is not None
    assert fetched.failure_category == "context_overflow"

    # 2. List reports
    reps = repo.list_reports("proj-rca-repo")
    assert len(reps) == 1

    # 3. Record & list clusters
    repo.record_failure_cluster("proj-rca-repo", "Timeout error at 0x49f2b")
    repo.record_failure_cluster("proj-rca-repo", "Timeout error at 0x99999")
    clusters = repo.list_clusters("proj-rca-repo")
    assert len(clusters) == 1
    assert clusters[0].occurrences_count == 2
