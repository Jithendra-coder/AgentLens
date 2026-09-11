"""Contract checks that later milestones remain unimplemented."""

import agentlens


def test_future_product_objects_are_not_implemented() -> None:
    future_names = {
        "SDKClient",
        "Evaluator",
        "Replay",
        "IngestionClient",
        "Dashboard",
    }
    assert future_names.isdisjoint(vars(agentlens))


def test_m2_public_surface_is_exposed() -> None:
    assert hasattr(agentlens, "AgentLens")
    assert hasattr(agentlens, "current_trace")
    assert hasattr(agentlens, "current_span")
