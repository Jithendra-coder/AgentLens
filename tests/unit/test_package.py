"""Minimal package foundation checks."""

import agentlens


def test_package_import_and_version() -> None:
    assert agentlens.__version__ == "0.1.0"
    assert "AgentLens" in agentlens.__all__
    assert "current_trace" in agentlens.__all__
