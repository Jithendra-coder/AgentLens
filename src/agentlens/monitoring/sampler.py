"""Deterministic hash-based continuous stream sampler ."""

from __future__ import annotations

import hashlib
from uuid import UUID


class ContinuousSampler:
    """Evaluates whether a trace should be sampled for background evaluation."""

    @staticmethod
    def should_sample(trace_id: UUID | str, sampling_rate: float) -> bool:
        if sampling_rate <= 0.0:
            return False
        if sampling_rate >= 1.0:
            return True

        key_str = str(trace_id).encode("utf-8")
        hash_digest = hashlib.md5(key_str).hexdigest()
        bucket = int(hash_digest[:8], 16) % 10000
        threshold = int(sampling_rate * 10000)

        return bucket < threshold
