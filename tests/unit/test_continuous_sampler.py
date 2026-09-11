"""Unit tests for ContinuousSampler deterministic sampling."""

from __future__ import annotations

from uuid import uuid4

from agentlens.monitoring.sampler import ContinuousSampler


def test_continuous_sampler_boundary_and_consistency() -> None:
    trace_id = uuid4()

    # Rate 0.0 -> never sample
    assert ContinuousSampler.should_sample(trace_id, 0.0) is False

    # Rate 1.0 -> always sample
    assert ContinuousSampler.should_sample(trace_id, 1.0) is True

    # Determinism: same trace_id with same rate yields same decision
    s1 = ContinuousSampler.should_sample(trace_id, 0.25)
    s2 = ContinuousSampler.should_sample(trace_id, 0.25)
    assert s1 == s2


def test_continuous_sampler_distribution() -> None:
    # Over 1000 random traces at 10% sampling rate, roughly 7-13% should be sampled
    sampled_count = 0
    total = 1000
    rate = 0.10

    for _ in range(total):
        if ContinuousSampler.should_sample(uuid4(), rate):
            sampled_count += 1

    ratio = sampled_count / float(total)
    assert 0.05 <= ratio <= 0.15
