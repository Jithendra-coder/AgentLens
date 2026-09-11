"use client";

import { useEffect, useState } from "react";

interface LatencyBreakdown {
  llm_time_ms: number;
  tool_time_ms: number;
  network_time_ms: number;
  overhead_time_ms: number;
  total_duration_ms: number;
  llm_percentage: number;
  tool_percentage: number;
  overhead_percentage: number;
}

interface SpanProfile {
  span_id: string;
  name: string;
  span_type: string;
  category: string;
  duration_ms: number;
  self_time_ms: number;
  is_critical_path: boolean;
  parent_span_id: string | null;
  child_span_ids: string[];
  tokens: number;
}

interface Hotspot {
  span_id: string;
  name: string;
  hotspot_type: string;
  severity: string;
  description: string;
  impact_percentage: number;
}

interface TraceProfileData {
  trace_id: string;
  total_duration_ms: number;
  critical_path_span_ids: string[];
  critical_path_duration_ms: number;
  latency_breakdown: LatencyBreakdown;
  token_breakdown: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  span_profiles: SpanProfile[];
  hotspots: Hotspot[];
}

export default function TraceProfiler({ traceId }: { traceId: string }) {
  const [profile, setProfile] = useState<TraceProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/v1/traces/${encodeURIComponent(traceId)}/profile`)
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`Profile unavailable: HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        setProfile(data);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || "Failed to load trace profile");
      })
      .finally(() => setLoading(false));
  }, [traceId]);

  if (loading) {
    return <div className="p-4 text-xs text-muted-foreground">Analyzing critical path & profiling execution graph...</div>;
  }

  if (error || !profile) {
    return <div className="p-4 text-xs text-destructive bg-destructive/10 rounded-md">Profiling error: {error}</div>;
  }

  const { latency_breakdown, token_breakdown, span_profiles, hotspots } = profile;

  return (
    <div className="space-y-6 pt-2">
      {/* Top Level Latency Breakdown KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3.5 border rounded-lg bg-card text-card-foreground shadow-sm">
          <div className="text-xs text-muted-foreground">Total Trace Duration</div>
          <div className="text-xl font-bold mt-1">{profile.total_duration_ms.toFixed(1)} ms</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            Critical Path: {profile.critical_path_duration_ms.toFixed(1)} ms
          </div>
        </div>

        <div className="p-3.5 border rounded-lg bg-card text-card-foreground shadow-sm">
          <div className="text-xs text-muted-foreground flex justify-between">
            <span>LLM Generation</span>
            <span className="font-semibold text-primary">{latency_breakdown.llm_percentage}%</span>
          </div>
          <div className="text-xl font-bold mt-1">{latency_breakdown.llm_time_ms.toFixed(1)} ms</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            {token_breakdown.total_tokens.toLocaleString()} tokens
          </div>
        </div>

        <div className="p-3.5 border rounded-lg bg-card text-card-foreground shadow-sm">
          <div className="text-xs text-muted-foreground flex justify-between">
            <span>Tool Execution</span>
            <span className="font-semibold text-emerald-600">{latency_breakdown.tool_percentage}%</span>
          </div>
          <div className="text-xl font-bold mt-1">{latency_breakdown.tool_time_ms.toFixed(1)} ms</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">I/O & MCP Tools</div>
        </div>

        <div className="p-3.5 border rounded-lg bg-card text-card-foreground shadow-sm">
          <div className="text-xs text-muted-foreground flex justify-between">
            <span>Framework Overhead</span>
            <span className="font-semibold text-amber-600">{latency_breakdown.overhead_percentage}%</span>
          </div>
          <div className="text-xl font-bold mt-1">{latency_breakdown.overhead_time_ms.toFixed(1)} ms</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">Agent State & Orchestration</div>
        </div>
      </div>

      {/* Visual Composition Stack Bar */}
      <div className="space-y-1.5">
        <div className="text-xs font-semibold text-muted-foreground flex justify-between">
          <span>Latency Composition</span>
          <span>100% of Total Time</span>
        </div>
        <div className="w-full h-3 rounded-full overflow-hidden flex bg-muted">
          <div
            style={{ width: `${latency_breakdown.llm_percentage}%` }}
            className="bg-primary h-full transition-all"
            title={`LLM Generation: ${latency_breakdown.llm_percentage}%`}
          />
          <div
            style={{ width: `${latency_breakdown.tool_percentage}%` }}
            className="bg-emerald-500 h-full transition-all"
            title={`Tool Execution: ${latency_breakdown.tool_percentage}%`}
          />
          <div
            style={{ width: `${latency_breakdown.overhead_percentage}%` }}
            className="bg-amber-500 h-full transition-all"
            title={`Agent Overhead: ${latency_breakdown.overhead_percentage}%`}
          />
        </div>
        <div className="flex space-x-4 text-[11px] text-muted-foreground pt-0.5">
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-primary inline-block" />
            <span>LLM ({latency_breakdown.llm_percentage}%)</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
            <span>Tools ({latency_breakdown.tool_percentage}%)</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
            <span>Overhead ({latency_breakdown.overhead_percentage}%)</span>
          </div>
        </div>
      </div>

      {/* Detected Hotspots Alert Section */}
      {hotspots.length > 0 && (
        <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
          <div className="text-sm font-semibold flex items-center space-x-2">
            <span className="text-amber-500 font-bold">⚠️</span>
            <span>Detected Bottlenecks & Execution Hotspots ({hotspots.length})</span>
          </div>
          <div className="divide-y text-xs">
            {hotspots.map((h, idx) => (
              <div key={idx} className="py-2 flex items-start justify-between space-x-3">
                <div className="space-y-0.5">
                  <div className="font-semibold text-foreground flex items-center space-x-2">
                    <span>{h.name}</span>
                    <span
                      className={`px-1.5 py-0.2 rounded text-[10px] uppercase font-bold ${
                        h.severity === "high"
                          ? "bg-destructive/15 text-destructive"
                          : "bg-amber-500/15 text-amber-600"
                      }`}
                    >
                      {h.severity}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {h.hotspot_type}
                    </span>
                  </div>
                  <p className="text-muted-foreground">{h.description}</p>
                </div>
                <div className="text-right whitespace-nowrap font-medium text-foreground">
                  {h.impact_percentage}% impact
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Critical Path & Spans Table */}
      <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
        <div className="text-sm font-semibold">Critical Path & Span Execution Breakdown</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-muted text-muted-foreground uppercase text-[10px]">
              <tr>
                <th className="px-3 py-2">Span Name</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Category</th>
                <th className="px-3 py-2">Total Duration</th>
                <th className="px-3 py-2">Self Time</th>
                <th className="px-3 py-2">Tokens</th>
                <th className="px-3 py-2 text-right">Path Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {span_profiles.map((sp) => (
                <tr
                  key={sp.span_id}
                  className={`hover:bg-muted/50 ${
                    sp.is_critical_path ? "bg-primary/5 font-medium" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-mono flex items-center space-x-1.5">
                    {sp.is_critical_path && (
                      <span className="w-1.5 h-1.5 rounded-full bg-destructive inline-block" title="On Critical Path" />
                    )}
                    <span>{sp.name}</span>
                  </td>
                  <td className="px-3 py-2 uppercase text-[10px] text-muted-foreground">
                    {sp.span_type}
                  </td>
                  <td className="px-3 py-2 capitalize">{sp.category.replace("_", " ")}</td>
                  <td className="px-3 py-2">{sp.duration_ms.toFixed(1)} ms</td>
                  <td className="px-3 py-2">{sp.self_time_ms.toFixed(1)} ms</td>
                  <td className="px-3 py-2">
                    {sp.tokens > 0 ? sp.tokens.toLocaleString() : "-"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {sp.is_critical_path ? (
                      <span className="px-2 py-0.5 text-[10px] rounded-full font-bold bg-destructive/15 text-destructive">
                        Critical Path
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-[10px]">Parallel Branch</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
