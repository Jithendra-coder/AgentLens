"""Provider-independent AgentLens package."""

from .sdk import (
    AgentLens,
    AlwaysOffSampler,
    AlwaysOnSampler,
    HttpTraceExporter,
    InMemoryTraceExporter,
    current_span,
    current_trace,
)

__version__ = "0.1.0"

__all__ = (
    "AgentLens",
    "AlwaysOffSampler",
    "AlwaysOnSampler",
    "HttpTraceExporter",
    "InMemoryTraceExporter",
    "__version__",
    "current_span",
    "current_trace",
)
