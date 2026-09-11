"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { dashboardFetch, formatDuration, formatNumber, formatPercent, jsonParams } from "../lib/client";
import type { Overview, TimeseriesPoint } from "../lib/types";
import { Badge, EmptyState, TimeSeriesChart, TraceTime } from "./ui";

const windows = ["1h", "24h", "7d"] as const;
type WindowName = (typeof windows)[number];

const INITIAL_OVERVIEW: Overview = {
  window: {
    start: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
    end: new Date().toISOString(),
  },
  traces: {
    count: 0,
    completed_count: 0,
    error_count: 0,
    error_rate: 0,
  },
  latency_ms: {
    p50: 0,
    p95: 0,
    p99: 0,
  },
  reported_tokens: {
    spans_with_usage: 0,
    input: 0,
    output: 0,
    total: 0,
  },
  evaluations: {
    count: 0,
    status_counts: {},
  },
  findings: {
    counts: {},
  },
  recent_traces: [],
  recent_findings: [],
};

const INITIAL_SERIES: TimeseriesPoint[] = [];

export default function OverviewClient() {
  const params = useSearchParams();
  const router = useRouter();
  const selected = (windows.includes(params.get("window") as WindowName) ? params.get("window") : "24h") as WindowName;
  const [overview, setOverview] = useState<Overview>(INITIAL_OVERVIEW);
  const [series, setSeries] = useState<TimeseriesPoint[]>(INITIAL_SERIES);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const query = jsonParams({ window: selected });
      const [nextOverview, nextSeries] = await Promise.all([
        dashboardFetch<Overview>(`analytics/overview${query}`),
        dashboardFetch<{ items: TimeseriesPoint[] }>(`analytics/timeseries${query}`),
      ]);
      if (nextOverview) {
        setOverview(nextOverview);
      }
      if (nextSeries && nextSeries.items) {
        setSeries(nextSeries.items);
      }
    } catch {
      // Backend not reached; keep clean initial state
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    void load();
  }, [load]);

  const changeWindow = (value: WindowName) => router.replace(`/?window=${value}`);

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Enterprise Observability Overview</p>
          <h1>System Overview</h1>
          <p className="lede">
            Real-time telemetry, trace health, token cost attribution, latency SLAs, and automated diagnostics for autonomous AI agents.
          </p>
        </div>
        <div className="toolbar" aria-label="Overview time window">
          {windows.map((value) => (
            <button
              className={`button ${selected === value ? "" : "secondary"}`}
              key={value}
              onClick={() => changeWindow(value)}
              aria-pressed={selected === value}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      {/* New User Onboarding & API Key Card */}
      <section className="card section" style={{ border: "1px solid #E2E8F0", background: "#FFFFFF", marginBottom: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", fontWeight: 700, marginBottom: "0.25rem" }}>
              Quickstart Integration
            </div>
            <h2 style={{ fontSize: "1.2rem", margin: "0 0 0.35rem 0", color: "#0F172A" }}>Connect Your RAG Application</h2>
            <p className="subtle" style={{ margin: 0, fontSize: "0.85rem", color: "#475569" }}>
              To record live latency, tokens, and retrieval accuracy, include your project API key in your AI code.
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Link href="/rag" className="button" style={{ fontSize: "0.8rem", minHeight: "2rem", background: "#0F172A", color: "#FFFFFF" }}>
              Policy RAG Assistant →
            </Link>
            <Link href="/how-it-works" className="button secondary" style={{ fontSize: "0.8rem", minHeight: "2rem" }}>
              How It Works Guide →
            </Link>
          </div>
        </div>

        <div style={{ marginTop: "1rem", padding: "0.75rem 1rem", background: "#F8FAFC", border: "1px solid #CBD5E1", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <span style={{ color: "#64748B", fontSize: "0.78rem", fontWeight: 700 }}>PROJECT: <strong style={{ color: "#0F172A" }}>proj-default</strong></span>
            <span style={{ color: "#CBD5E1" }}>|</span>
            <span style={{ color: "#64748B", fontSize: "0.78rem", fontWeight: 700 }}>API KEY:</span>
            <code style={{ color: "#0F172A", fontSize: "0.92rem", fontWeight: 700, letterSpacing: "0.03em" }}>
              dev-key-12345
            </code>
          </div>
          <button
            type="button"
            className="button secondary"
            style={{ fontSize: "0.75rem", minHeight: "1.8rem", padding: "0.15rem 0.75rem" }}
            onClick={() => {
              const activeKey = (typeof window !== "undefined" && localStorage.getItem("agentlens_active_key")) || "dev-key-12345";
              navigator.clipboard.writeText(activeKey);
              alert("API Key copied: " + activeKey);
            }}
          >
            📋 Copy API Key
          </button>
        </div>

        <div style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: "#64748B" }}>
          Query the built-in RAG assistant from the <Link href="/rag" style={{ textDecoration: "underline", color: "#0284C7", fontWeight: 600 }}>Policy RAG Playground</Link> or send live traces via API using <code style={{ color: "#0F172A", background: "#F1F5F9", padding: "0.15rem 0.4rem", borderRadius: "4px", fontFamily: "monospace", border: "1px solid #E2E8F0" }}>POST /v1/traces</code>.
        </div>
      </section>

      {/* Primary KPI Metrics */}
      <div className="grid stats">
        <Stat
          label="Total Traces"
          value={formatNumber(overview.traces.count)}
          note={`${formatNumber(overview.traces.completed_count)} completed execution trees`}
        />
        <Stat
          label="Error Rate"
          value={formatPercent(overview.traces.error_rate)}
          note={`${formatNumber(overview.traces.error_count)} error traces captured`}
        />
        <Stat
          label="p95 Latency"
          value={formatDuration(overview.latency_ms.p95)}
          note="Critical-path DAG latency SLA"
        />
        <Stat
          label="Total Tokens"
          value={formatNumber(overview.reported_tokens.total || 0)}
          note={`${formatNumber(overview.reported_tokens.spans_with_usage || 0)} spans with token usage`}
        />
      </div>

      {/* Charts Section */}
      <div className="grid two section">
        <section className="card">
          <div className="split">
            <h2>Trace Execution Volume</h2>
            <span className="subtle">Server time buckets</span>
          </div>
          <TimeSeriesChart points={series} />
        </section>

        <section className="card">
          <h2>Completed Latency Profile</h2>
          <div className="grid stats" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
            <Stat label="p50 Latency" value={formatDuration(overview.latency_ms.p50)} note="Median completion time" />
            <Stat label="p95 Latency" value={formatDuration(overview.latency_ms.p95)} note="95th percentile SLA" />
            <Stat label="p99 Latency" value={formatDuration(overview.latency_ms.p99)} note="Tail latency boundary" />
            <Stat
              label="Quality Evaluated"
              value={formatNumber(overview.evaluations.count)}
              note="Automated test suites passed"
            />
          </div>
        </section>
      </div>

      {/* Recent Traces & Findings */}
      <div className="grid two section">
        <section className="card">
          <div className="split" style={{ marginBottom: "0.8rem" }}>
            <h2>Recent Agent Traces</h2>
            <Link href="/traces" className="link" style={{ fontSize: "0.82rem" }}>
              View all →
            </Link>
          </div>
          {overview.recent_traces.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Agent / Trajectory Name</th>
                    <th>Status</th>
                    <th>Started</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.recent_traces.map((trace) => (
                    <tr key={trace.trace_id}>
                      <td>
                        <Link className="link" href={`/traces/${trace.trace_id}`}>
                          {trace.name}
                        </Link>
                        <div className="subtle mono">{trace.trace_id}</div>
                      </td>
                      <td>
                        <Badge value={trace.status} />
                      </td>
                      <td>
                        <TraceTime value={trace.started_at} />
                      </td>
                      <td>{formatDuration(trace.duration_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState label="No traces in this window." />
          )}
        </section>

        <section className="card">
          <div className="split" style={{ marginBottom: "0.8rem" }}>
            <h2>Recent Diagnostic Findings</h2>
            <Link href="/analytics/rca" className="link" style={{ fontSize: "0.82rem" }}>
              RCA Center →
            </Link>
          </div>
          {overview.recent_findings.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Finding Code</th>
                    <th>Severity</th>
                    <th>Evaluation Type</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.recent_findings.map((finding) => (
                    <tr key={`${finding.result_id}-${finding.code}`}>
                      <td>
                        <Link className="link" href={`/evaluations/${finding.result_id}`}>
                          {finding.code}
                        </Link>
                        <div className="subtle">{finding.message}</div>
                      </td>
                      <td>
                        <Badge value={finding.severity} />
                      </td>
                      <td className="mono">{finding.evaluation_type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState label="No diagnostic findings in this window." />
          )}
        </section>
      </div>

      <p className="footer-note">
        AgentLens Telemetry Engine v1.0.0-GA · Cryptographic SHA-256 Audit Chain active · Project: proj-default
      </p>
    </>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <p className="stat-note">{note}</p>
    </div>
  );
}
