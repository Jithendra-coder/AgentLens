"""Unit tests for PlatformReadinessChecker and GA Certification."""

from __future__ import annotations

from agentlens.readiness.checker import PlatformReadinessChecker


def test_platform_readiness_checker_and_certification() -> None:
    # 1. Run full readiness audit
    report = PlatformReadinessChecker.run_readiness_audit()
    assert report.platform_version == "1.0.0-GA"
    assert report.overall_status == "GA_CERTIFIED"
    assert report.readiness_score == 100.0
    assert report.total_subsystems == 10
    assert report.ready_subsystems == 10
    assert len(report.subsystems) == 10

    # Ensure all pillars are checked
    names = {s.name for s in report.subsystems}
    assert "Database Schema & Migrations" in names
    assert "Multi-Tenant RBAC & Isolation" in names
    assert "Immutable Governance & Audit" in names

    # 2. Generate GA Platform Certification
    cert = PlatformReadinessChecker.generate_certification()
    assert cert.platform_version == "1.0.0-GA"
    assert cert.certification_status == "GA_CERTIFIED"
    assert cert.readiness_score == 100.0
    assert len(cert.digital_seal) == 64
