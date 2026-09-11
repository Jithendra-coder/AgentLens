from __future__ import annotations

from agentlens.replay.targets import LocalEchoReplayTarget


class FakeReplayTarget(LocalEchoReplayTarget):
    """M9-only deterministic target fixture; production adapters remain registry-owned."""
