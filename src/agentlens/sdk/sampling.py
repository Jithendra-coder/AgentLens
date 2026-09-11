"""Small root-level sampling contracts for the local SDK."""

from __future__ import annotations

from typing import Protocol


class Sampler(Protocol):
    """Decides whether a root trace is retained."""

    def should_sample(self, *, project_id: str, name: str) -> bool:
        """Return the root trace sampling decision."""


class AlwaysOnSampler:
    """Sample every root trace."""

    def should_sample(self, *, project_id: str, name: str) -> bool:
        return True


class AlwaysOffSampler:
    """Sample no root traces."""

    def should_sample(self, *, project_id: str, name: str) -> bool:
        return False


__all__ = ("AlwaysOffSampler", "AlwaysOnSampler", "Sampler")
