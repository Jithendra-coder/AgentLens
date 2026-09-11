"""Stable error boundary for AgentLens domain operations."""


class AgentLensError(Exception):
    """Base class for all public AgentLens errors."""


class DomainError(AgentLensError):
    """Base class for invalid or unsupported domain data."""


class ValidationError(DomainError):
    """Raised when domain data violates a canonical invariant."""


class SerializationError(DomainError):
    """Raised when canonical data cannot be encoded or decoded."""


class UnsupportedSchemaError(SerializationError):
    """Raised when a trace schema is not supported by this package."""


class InstrumentationError(AgentLensError):
    """Raised when SDK lifecycle or usage rules are violated."""


class HttpExportError(AgentLensError):
    """Raised by the HTTP exporter without exposing credentials or payloads."""


class ConfigurationError(AgentLensError):
    """Raised when environment or runtime configuration is invalid or missing."""


class LifecycleError(AgentLensError):
    """Raised when service lifecycle or graceful shutdown encounters an error."""


class SecurityError(AgentLensError):
    """Raised when cryptographic verification, token verification, or decryption fails."""


__all__ = (
    "AgentLensError",
    "ConfigurationError",
    "DomainError",
    "HttpExportError",
    "InstrumentationError",
    "LifecycleError",
    "SecurityError",
    "SerializationError",
    "UnsupportedSchemaError",
    "ValidationError",
)
