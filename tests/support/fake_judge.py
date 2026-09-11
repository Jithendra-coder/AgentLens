"""Test-only semantic judge; production code has no fake provider."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from agentlens.domain.types import JSONValue
from agentlens.evaluation.judges import JudgeRequest, JudgeResponse


@dataclass
class FakeJudge:
    response: JudgeResponse | object = field(default_factory=lambda: JudgeResponse(label="pass"))
    response_factory: Callable[[JudgeRequest], object] | None = None
    error: BaseException | None = None
    provider: str = "test"
    model: str = "fake-semantic-judge"
    adapter_version: str = "test-adapter-v1"
    parameters: Mapping[str, JSONValue] = field(default_factory=dict)
    calls: list[JudgeRequest] = field(default_factory=list)

    def judge(self, request: JudgeRequest) -> object:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        if self.response_factory is not None:
            return self.response_factory(request)
        return self.response
