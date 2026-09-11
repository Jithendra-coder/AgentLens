"""Non-sensitive runtime errors."""

from __future__ import annotations


class EvaluationRuntimeError(Exception):
    """Base class for expected evaluation-runtime failures."""


class JobNotFoundError(EvaluationRuntimeError):
    pass


class JobIdempotencyConflict(EvaluationRuntimeError):
    pass


class TraceNotFoundError(EvaluationRuntimeError):
    pass


class JobStorageUnavailable(EvaluationRuntimeError):
    pass


class StaleClaimError(EvaluationRuntimeError):
    pass


class RedisUnavailableError(EvaluationRuntimeError):
    pass


class ResultPersistenceUnavailable(EvaluationRuntimeError):
    pass


class JudgeError(EvaluationRuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class JudgeTimeoutError(JudgeError):
    def __init__(self, message: str = "semantic judge timed out") -> None:
        super().__init__("judge_timeout", retryable=True)
        self.message = message


class JudgeRateLimitError(JudgeError):
    def __init__(self, message: str = "semantic judge rate limited") -> None:
        super().__init__("judge_rate_limited", retryable=True)
        self.message = message


class JudgeUnavailableError(JudgeError):
    def __init__(self, message: str = "semantic judge is unavailable") -> None:
        super().__init__("judge_unavailable", retryable=True)
        self.message = message


class JudgeAuthenticationError(JudgeError):
    def __init__(self, message: str = "semantic judge authentication failed") -> None:
        super().__init__("judge_authentication_failure", retryable=False)
        self.message = message


class JudgeConfigurationError(JudgeError):
    def __init__(self, message: str = "semantic judge configuration is invalid") -> None:
        super().__init__("judge_configuration_invalid", retryable=False)
        self.message = message


class MalformedJudgeResponseError(JudgeError):
    def __init__(self, message: str = "semantic judge response is invalid") -> None:
        super().__init__("invalid_judge_response", retryable=False)
        self.message = message


class UnknownHandlerError(EvaluationRuntimeError):
    pass


class EvaluationTimeoutError(EvaluationRuntimeError):
    pass


class HandlerExecutionError(EvaluationRuntimeError):
    def __init__(self, code: str, *, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
