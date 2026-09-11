"""Deterministic traffic splitting for experimentation ."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from agentlens.experimentation.models import Experiment, ExperimentVariant


class TrafficSplitter:
    """Deterministic hash-based traffic routing across experiment variants."""

    @staticmethod
    def select_variant(
        experiment: Experiment,
        routing_key: str,
    ) -> ExperimentVariant:
        """Select variant deterministically using MD5 hash bucket of experiment ID + routing key."""
        variants: Sequence[ExperimentVariant] = experiment.variants
        if not variants:
            raise ValueError(f"Experiment '{experiment.name}' has no configured variants.")

        if len(variants) == 1:
            return variants[0]

        total_weight = sum(v.traffic_weight for v in variants)
        if total_weight <= 0.0:
            return variants[0]

        # Normalized cumulative weights
        norm_weights = [v.traffic_weight / total_weight for v in variants]

        # Deterministic 0.0 -> 1.0 bucket
        hash_input = f"{experiment.experiment_id}:{routing_key}".encode()
        bucket = (int(hashlib.md5(hash_input).hexdigest(), 16) % 10000) / 10000.0

        cum = 0.0
        for i, weight in enumerate(norm_weights):
            cum += weight
            if bucket <= cum or i == len(variants) - 1:
                return variants[i]

        return variants[0]
