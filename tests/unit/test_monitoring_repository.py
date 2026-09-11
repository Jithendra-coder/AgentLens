"""Unit tests for InMemoryMonitoringRepository lifecycle."""

from __future__ import annotations

from uuid import uuid4

from agentlens.monitoring.models import (
    HealthSnapshot,
    ProductionMonitor,
)
from agentlens.monitoring.repository import InMemoryMonitoringRepository


def test_in_memory_monitoring_repository_lifecycle() -> None:
    repo = InMemoryMonitoringRepository()
    mon_id = uuid4()

    monitor = ProductionMonitor(
        monitor_id=mon_id,
        project_id="proj-mon-repo",
        name="Production Ingestion Monitor",
        sampling_rate=0.15,
    )

    # 1. Save & get monitor
    saved = repo.save_monitor(monitor)
    assert saved.monitor_id == mon_id

    fetched = repo.get_monitor(mon_id)
    assert fetched is not None
    assert fetched.name == "Production Ingestion Monitor"

    # 2. List monitors
    m_list = repo.list_monitors("proj-mon-repo")
    assert len(m_list) == 1

    # 3. Update monitor health
    assert repo.update_monitor_health(mon_id, 92.5, "healthy") is True
    assert repo.get_monitor(mon_id) is not None
    assert repo.get_monitor(mon_id).health_index == 92.5  # type: ignore

    # 4. Record & list snapshots
    snap = HealthSnapshot(
        snapshot_id=uuid4(),
        monitor_id=mon_id,
        project_id="proj-mon-repo",
        health_index=92.5,
        p95_latency_ms=300.0,
        mean_quality_score=0.94,
    )
    repo.record_snapshot(snap)
    snaps = repo.list_snapshots("proj-mon-repo", monitor_id=mon_id)
    assert len(snaps) == 1
    assert snaps[0].health_index == 92.5

    # 5. Delete monitor
    assert repo.delete_monitor(mon_id) is True
    assert repo.get_monitor(mon_id) is None
    assert len(repo.list_snapshots("proj-mon-repo")) == 0
