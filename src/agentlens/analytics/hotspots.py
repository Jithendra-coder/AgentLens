"""Project-level bottleneck and token hotspot aggregation ."""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from agentlens.domain import Trace
from agentlens.domain.types import SpanType

TOOL_SPAN_TYPES = (
    SpanType.TOOL.value,
    SpanType.MCP.value,
    SpanType.RETRIEVAL.value,
    SpanType.HTTP.value,
)


@dataclass(frozen=True, slots=True)
class ToolHotspot:
    tool_name: str
    call_count: int
    avg_duration_ms: float
    p95_duration_ms: float
    max_duration_ms: float
    error_rate: float


@dataclass(frozen=True, slots=True)
class TokenHotspot:
    name: str
    call_count: int
    total_tokens: int
    avg_tokens: float
    avg_prompt_tokens: float
    avg_completion_tokens: float


@dataclass(frozen=True, slots=True)
class ErrorHotspot:
    error_message: str
    occurrences: int
    affected_span_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectHotspotsSummary:
    project_id: str
    analyzed_traces_count: int
    slowest_tools: tuple[ToolHotspot, ...]
    heaviest_token_spans: tuple[TokenHotspot, ...]
    top_errors: tuple[ErrorHotspot, ...]


def aggregate_project_hotspots(
    project_id: str,
    traces: Sequence[Trace],
) -> ProjectHotspotsSummary:
    """Aggregate tool execution latencies, token consumption, and error clusters across traces."""
    tool_durations: dict[str, list[float]] = defaultdict(list)
    tool_errors: dict[str, int] = defaultdict(int)

    # name -> [(prompt, comp, total)]
    token_stats: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    # msg -> [span_type, ...]
    error_counts: dict[str, list[str]] = defaultdict(list)

    for trace in traces:
        for span in trace.spans:
            dur = 0.0
            if span.ended_at and span.started_at:
                dur = max(0.0, (span.ended_at - span.started_at).total_seconds() * 1000.0)

            st = str(span.span_type).lower()
            name = span.name or f"unnamed-{st}"

            # Tool tracking
            if st in TOOL_SPAN_TYPES:
                tool_durations[name].append(dur)
                if str(span.status).lower() == "error":
                    tool_errors[name] += 1

            # Token tracking
            if span.usage and span.usage.total_tokens:
                p = span.usage.input_tokens or 0
                c = span.usage.output_tokens or 0
                t = span.usage.total_tokens or (p + c)
                token_stats[name].append((p, c, t))

            # Error clustering
            if str(span.status).lower() == "error":
                msg = span.error.message if span.error else "Unknown execution failure"
                error_counts[msg].append(st)

    # Process Tool Hotspots
    tool_hotspots_list: list[ToolHotspot] = []
    for t_name, durs in tool_durations.items():
        count = len(durs)
        avg_d = statistics.mean(durs) if durs else 0.0
        max_d = max(durs) if durs else 0.0
        # Calculate p95
        sorted_d = sorted(durs)
        idx_p95 = int(0.95 * len(sorted_d))
        p95_d = sorted_d[min(idx_p95, len(sorted_d) - 1)] if sorted_d else 0.0
        errs = tool_errors.get(t_name, 0)
        err_rate = (errs / count * 100.0) if count > 0 else 0.0

        tool_hotspots_list.append(
            ToolHotspot(
                tool_name=t_name,
                call_count=count,
                avg_duration_ms=round(avg_d, 2),
                p95_duration_ms=round(p95_d, 2),
                max_duration_ms=round(max_d, 2),
                error_rate=round(err_rate, 2),
            )
        )

    # Sort slowest tools by p95 descending
    tool_hotspots_list.sort(key=lambda x: x.p95_duration_ms, reverse=True)

    # Process Token Hotspots
    token_hotspots_list: list[TokenHotspot] = []
    for name, stats in token_stats.items():
        count = len(stats)
        total_p = sum(s[0] for s in stats)
        total_c = sum(s[1] for s in stats)
        total_t = sum(s[2] for s in stats)

        token_hotspots_list.append(
            TokenHotspot(
                name=name,
                call_count=count,
                total_tokens=total_t,
                avg_tokens=round(total_t / count, 1) if count > 0 else 0.0,
                avg_prompt_tokens=round(total_p / count, 1) if count > 0 else 0.0,
                avg_completion_tokens=round(total_c / count, 1) if count > 0 else 0.0,
            )
        )

    # Sort heaviest token consumers by total tokens descending
    token_hotspots_list.sort(key=lambda x: x.total_tokens, reverse=True)

    # Process Error Hotspots
    error_hotspots_list: list[ErrorHotspot] = []
    for msg, types in error_counts.items():
        error_hotspots_list.append(
            ErrorHotspot(
                error_message=msg,
                occurrences=len(types),
                affected_span_types=tuple(sorted(list(set(types)))),
            )
        )

    error_hotspots_list.sort(key=lambda x: x.occurrences, reverse=True)

    return ProjectHotspotsSummary(
        project_id=project_id,
        analyzed_traces_count=len(traces),
        slowest_tools=tuple(tool_hotspots_list[:10]),
        heaviest_token_spans=tuple(token_hotspots_list[:10]),
        top_errors=tuple(error_hotspots_list[:10]),
    )
