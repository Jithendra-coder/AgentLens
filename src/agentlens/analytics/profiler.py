"""Deterministic critical-path DAG analysis and trace bottleneck profiler ."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from agentlens.domain import Span, Trace
from agentlens.domain.types import SpanType


def _span_duration_ms(span: Span) -> float:
    if span.ended_at is None or span.started_at is None:
        return 0.0
    diff = (span.ended_at - span.started_at).total_seconds() * 1000.0
    return max(0.0, diff)


def _categorize_span_type(span_type: str) -> str:
    st = span_type.lower()
    if st in (SpanType.LLM.value, SpanType.EMBEDDING.value):
        return "llm"
    if st in (
        SpanType.TOOL.value,
        SpanType.MCP.value,
        SpanType.RETRIEVAL.value,
        SpanType.HTTP.value,
    ):
        return "tool"
    return "agent_overhead"


@dataclass(frozen=True, slots=True)
class SpanProfile:
    span_id: UUID
    name: str
    span_type: str
    category: str
    duration_ms: float
    self_time_ms: float
    is_critical_path: bool
    parent_span_id: UUID | None
    child_span_ids: tuple[UUID, ...]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LatencyBreakdown:
    llm_time_ms: float
    tool_time_ms: float
    network_time_ms: float
    overhead_time_ms: float
    total_duration_ms: float

    @property
    def llm_percentage(self) -> float:
        if self.total_duration_ms <= 0:
            return 0.0
        return self.llm_time_ms / self.total_duration_ms * 100.0

    @property
    def tool_percentage(self) -> float:
        if self.total_duration_ms <= 0:
            return 0.0
        return self.tool_time_ms / self.total_duration_ms * 100.0

    @property
    def overhead_percentage(self) -> float:
        if self.total_duration_ms <= 0:
            return 0.0
        return self.overhead_time_ms / self.total_duration_ms * 100.0


@dataclass(frozen=True, slots=True)
class Hotspot:
    span_id: UUID
    name: str
    hotspot_type: str  # dominant_latency, token_heavy, error_retry
    severity: str  # high, medium, low
    description: str
    impact_percentage: float


@dataclass(frozen=True, slots=True)
class TraceProfile:
    trace_id: UUID
    total_duration_ms: float
    critical_path_span_ids: tuple[UUID, ...]
    critical_path_duration_ms: float
    latency_breakdown: LatencyBreakdown
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    span_profiles: tuple[SpanProfile, ...]
    hotspots: tuple[Hotspot, ...]


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> float:
    """Merge overlapping time intervals and return total duration in milliseconds."""
    if not intervals:
        return 0.0
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = []

    for start, end in sorted_intervals:
        if not merged:
            merged.append((start, end))
            continue
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    total_ms = sum((end - start).total_seconds() * 1000.0 for start, end in merged)
    return max(0.0, total_ms)


def profile_trace(trace: Trace) -> TraceProfile:
    """Perform deterministic DAG critical path analysis and bottleneck diagnosis."""
    trace_uuid = UUID(str(trace.trace_id))
    trace_duration_ms = 0.0
    if trace.ended_at and trace.started_at:
        trace_duration_ms = max(0.0, (trace.ended_at - trace.started_at).total_seconds() * 1000.0)

    # Index spans by UUID
    span_map: dict[UUID, Span] = {}
    children_map: dict[UUID, list[UUID]] = {}
    roots: list[UUID] = []

    for span in trace.spans:
        sid = UUID(str(span.span_id))
        span_map[sid] = span
        children_map[sid] = []

    for span in trace.spans:
        sid = UUID(str(span.span_id))
        pid = UUID(str(span.parent_span_id)) if span.parent_span_id else None
        if pid is not None and pid in span_map:
            children_map[pid].append(sid)
        else:
            roots.append(sid)

    # Compute self-time per span
    self_times: dict[UUID, float] = {}
    for sid, span in span_map.items():
        dur = _span_duration_ms(span)
        child_intervals: list[tuple[datetime, datetime]] = []
        for cid in children_map[sid]:
            cspan = span_map[cid]
            if cspan.started_at and cspan.ended_at:
                child_intervals.append((cspan.started_at, cspan.ended_at))
        children_dur = _merge_intervals(child_intervals)
        self_times[sid] = max(0.0, dur - children_dur)

    # Compute Critical Path via longest DAG path
    memo_path_cost: dict[UUID, float] = {}
    memo_best_child: dict[UUID, UUID | None] = {}

    def get_longest_path(sid: UUID) -> float:
        if sid in memo_path_cost:
            return memo_path_cost[sid]
        self_dur = self_times[sid]
        children = children_map[sid]
        if not children:
            memo_path_cost[sid] = self_dur
            memo_best_child[sid] = None
            return self_dur

        best_child: UUID | None = None
        max_child_cost = 0.0
        for cid in children:
            child_cost = get_longest_path(cid)
            if child_cost > max_child_cost:
                max_child_cost = child_cost
                best_child = cid

        total_cost = self_dur + max_child_cost
        memo_path_cost[sid] = total_cost
        memo_best_child[sid] = best_child
        return total_cost

    best_root: UUID | None = None
    max_root_cost = 0.0
    for r in roots:
        cost = get_longest_path(r)
        if cost > max_root_cost:
            max_root_cost = cost
            best_root = r

    critical_path_ids: list[UUID] = []
    curr = best_root
    while curr is not None:
        critical_path_ids.append(curr)
        curr = memo_best_child.get(curr)

    critical_path_set = set(critical_path_ids)
    crit_duration = max_root_cost if max_root_cost > 0 else trace_duration_ms

    if trace_duration_ms <= 0.0:
        trace_duration_ms = max_root_cost

    # Latency and Token Breakdowns
    llm_time_ms = 0.0
    tool_time_ms = 0.0
    overhead_time_ms = 0.0

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    span_profiles_list: list[SpanProfile] = []
    hotspots_list: list[Hotspot] = []

    for sid, span in span_map.items():
        dur = _span_duration_ms(span)
        self_t = self_times[sid]
        cat = _categorize_span_type(str(span.span_type))

        if cat == "llm":
            llm_time_ms += self_t
        elif cat == "tool":
            tool_time_ms += self_t
        else:
            overhead_time_ms += self_t

        sp_prompt = 0
        sp_comp = 0
        sp_total = 0
        if span.usage:
            sp_prompt = span.usage.input_tokens or 0
            sp_comp = span.usage.output_tokens or 0
            sp_total = span.usage.total_tokens or (sp_prompt + sp_comp)
            prompt_tokens += sp_prompt
            completion_tokens += sp_comp
            total_tokens += sp_total

        # Detect Hotspots
        pct = (dur / trace_duration_ms * 100.0) if trace_duration_ms > 0 else 0.0
        if pct >= 30.0 and dur >= 100.0:
            hotspots_list.append(
                Hotspot(
                    span_id=sid,
                    name=span.name or f"span-{sid}",
                    hotspot_type="dominant_latency",
                    severity="high" if pct >= 50.0 else "medium",
                    description=f"Span accounts for {pct:.1f}% of trace duration.",
                    impact_percentage=round(pct, 2),
                )
            )

        if str(span.status).lower() == "error":
            err_msg = span.error.message if span.error else "execution failure"
            hotspots_list.append(
                Hotspot(
                    span_id=sid,
                    name=span.name or f"span-{sid}",
                    hotspot_type="error_retry",
                    severity="high",
                    description=f"Span failed with error: {err_msg}",
                    impact_percentage=round(pct, 2),
                )
            )

        if sp_total >= 4000:
            hotspots_list.append(
                Hotspot(
                    span_id=sid,
                    name=span.name or f"span-{sid}",
                    hotspot_type="token_heavy",
                    severity="medium",
                    description=f"Span consumed {sp_total:,} tokens.",
                    impact_percentage=round(pct, 2),
                )
            )

        span_profiles_list.append(
            SpanProfile(
                span_id=sid,
                name=span.name or f"span-{sid}",
                span_type=str(span.span_type),
                category=cat,
                duration_ms=round(dur, 2),
                self_time_ms=round(self_t, 2),
                is_critical_path=sid in critical_path_set,
                parent_span_id=UUID(str(span.parent_span_id)) if span.parent_span_id else None,
                child_span_ids=tuple(children_map[sid]),
                prompt_tokens=sp_prompt,
                completion_tokens=sp_comp,
                total_tokens=sp_total,
            )
        )

    accounted_ms = llm_time_ms + tool_time_ms + overhead_time_ms
    if trace_duration_ms > accounted_ms:
        overhead_time_ms += (trace_duration_ms - accounted_ms)

    breakdown = LatencyBreakdown(
        llm_time_ms=round(llm_time_ms, 2),
        tool_time_ms=round(tool_time_ms, 2),
        network_time_ms=0.0,
        overhead_time_ms=round(overhead_time_ms, 2),
        total_duration_ms=round(trace_duration_ms, 2),
    )

    return TraceProfile(
        trace_id=trace_uuid,
        total_duration_ms=round(trace_duration_ms, 2),
        critical_path_span_ids=tuple(critical_path_ids),
        critical_path_duration_ms=round(crit_duration, 2),
        latency_breakdown=breakdown,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        span_profiles=tuple(span_profiles_list),
        hotspots=tuple(hotspots_list),
    )
