"""Unit tests for FailureClusterer pattern normalization and grouping."""

from __future__ import annotations

from agentlens.rca.clusterer import FailureClusterer


def test_failure_clusterer_normalization_and_grouping() -> None:
    raw1 = (
        "OpenAI Error 429: Rate limit reached for request "
        "550e8400-e29b-41d4-a716-446655440000 at timestamp 1725000000"
    )
    raw2 = (
        "openai error 429: Rate limit reached for request "
        "12345678-abcd-1234-abcd-1234567890ab at timestamp 1725999999"
    )

    norm1 = FailureClusterer.normalize_pattern(raw1)
    norm2 = FailureClusterer.normalize_pattern(raw2)

    # Both dynamic UUIDs and numbers should be normalized into identical patterns
    assert norm1 == norm2
    assert "<uuid>" in norm1
    assert "<num>" in norm1

    # Clustering aggregation
    clusters: list = []
    c1 = FailureClusterer.cluster_or_update(clusters, "proj-cluster", raw1)
    assert c1.occurrences_count == 1

    c2 = FailureClusterer.cluster_or_update(clusters, "proj-cluster", raw2)
    assert c2.occurrences_count == 2
    assert len(clusters) == 1
