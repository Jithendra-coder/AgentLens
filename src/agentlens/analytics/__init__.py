"""Bounded, project-scoped analytics and performance profiling for the dashboard."""

from .hotspots import (
    ErrorHotspot,
    ProjectHotspotsSummary,
    TokenHotspot,
    ToolHotspot,
    aggregate_project_hotspots,
)
from .profiler import (
    Hotspot,
    LatencyBreakdown,
    SpanProfile,
    TraceProfile,
    profile_trace,
)
from .repository import (
    AnalyticsRepository,
    AnalyticsWindow,
    EvaluationAnalytics,
    OverviewAnalytics,
    PostgresAnalyticsRepository,
    RuntimeSummary,
    TimeseriesPoint,
)

__all__ = [
    "AnalyticsRepository",
    "AnalyticsWindow",
    "ErrorHotspot",
    "EvaluationAnalytics",
    "Hotspot",
    "LatencyBreakdown",
    "OverviewAnalytics",
    "PostgresAnalyticsRepository",
    "ProjectHotspotsSummary",
    "RuntimeSummary",
    "SpanProfile",
    "TimeseriesPoint",
    "TokenHotspot",
    "ToolHotspot",
    "TraceProfile",
    "aggregate_project_hotspots",
    "profile_trace",
]
