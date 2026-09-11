"""Failure signature normalization and clustering ."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from agentlens.rca.models import FailureCluster


class FailureClusterer:
    """Groups recurring trace failure signatures into standardized clusters."""

    @staticmethod
    def normalize_pattern(raw_error: str) -> str:
        if not raw_error:
            return "unknown_error"
        # 1. Lowercase & strip leading/trailing whitespace
        s = raw_error.strip().lower()
        # 2. Replace UUIDs / hashes
        s = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", s)
        s = re.sub(r"0x[0-9a-f]+", "<hex>", s)
        # 3. Replace standalone numbers / timestamps
        s = re.sub(r"\b\d+\b", "<num>", s)
        # 4. Collapse whitespace
        s = re.sub(r"\s+", " ", s)
        return s[:255]

    @staticmethod
    def cluster_or_update(
        existing_clusters: list[FailureCluster],
        project_id: str,
        raw_error: str,
        name: str | None = None,
    ) -> FailureCluster:
        pattern = FailureClusterer.normalize_pattern(raw_error)
        now = datetime.now(UTC)

        for idx, cluster in enumerate(existing_clusters):
            if cluster.project_id == project_id and cluster.failure_pattern == pattern:
                updated = FailureCluster(
                    cluster_id=cluster.cluster_id,
                    project_id=cluster.project_id,
                    name=cluster.name,
                    failure_pattern=cluster.failure_pattern,
                    occurrences_count=cluster.occurrences_count + 1,
                    first_seen=cluster.first_seen,
                    last_seen=now,
                )
                existing_clusters[idx] = updated
                return updated

        # Create new cluster
        cluster_name = name or f"Cluster: {pattern[:40]}"
        new_cluster = FailureCluster(
            cluster_id=uuid4(),
            project_id=project_id,
            name=cluster_name,
            failure_pattern=pattern,
            occurrences_count=1,
            first_seen=now,
            last_seen=now,
        )
        existing_clusters.append(new_cluster)
        return new_cluster
