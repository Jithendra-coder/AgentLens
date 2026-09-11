from uuid import uuid4

import pytest

from agentlens.replay.models import (
    DatasetCase,
    ReplayManifest,
    ReplayMode,
    ReproducibilityStatus,
    canonical_case_checksum,
)


def test_checksum_includes_ordered_content_and_ground_truth() -> None:
    first = DatasetCase(case_id=uuid4(), name="one", input={"value": 1}, position=0)
    second = DatasetCase(case_id=uuid4(), name="two", input={"value": 2}, position=1)
    assert canonical_case_checksum([first, second]) == canonical_case_checksum([first, second])
    assert canonical_case_checksum([first, second]) != canonical_case_checksum(
        [
            DatasetCase(
                case_id=first.case_id,
                name="one",
                input={"value": 1},
                ground_truth={"x": 1},
                position=0,
            ),
            second,
        ]
    )
    # Positions are authoritative; list iteration order is not.
    assert canonical_case_checksum([first, second]) == canonical_case_checksum([second, first])


def test_manifest_modes_are_explicit() -> None:
    common = {
        "dataset_version_id": uuid4(),
        "dataset_checksum": "a" * 64,
        "target_profile_id": "trusted",
        "target_version": "1",
        "reproducibility_status": ReproducibilityStatus.COMPLETE,
    }
    ReplayManifest(replay_mode=ReplayMode.EXACT, **common)
    ReplayManifest(
        replay_mode=ReplayMode.CONTROLLED,
        changed_dimensions=("model",),
        **common,
    )
    ReplayManifest(
        replay_mode=ReplayMode.BEST_EFFORT,
        best_effort_reason="provider state is unavailable",
        **common,
    )
    with pytest.raises(ValueError):
        ReplayManifest(
            replay_mode=ReplayMode.EXACT,
            unknown_fields=("model",),
            **common,
        )
    with pytest.raises(ValueError):
        ReplayManifest(replay_mode=ReplayMode.CONTROLLED, **common)
    with pytest.raises(ValueError):
        ReplayManifest(replay_mode=ReplayMode.BEST_EFFORT, **common)
