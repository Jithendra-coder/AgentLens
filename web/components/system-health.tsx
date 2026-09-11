"use client";

import { useEffect, useState } from "react";

interface SystemOverview {
  timestamp: string;
  service: string;
  infrastructure: {
    database: { status: string };
    redis: { status: string };
  };
  queues: {
    evaluation_depth: number;
    replay_depth: number;
    regression_depth: number;
  };
  telemetry: {
    api_latency: {
      count: number;
      sum: number;
      p50: number;
      p90: number;
      p95: number;
      p99: number;
    };
    worker_latency: {
      count: number;
      sum: number;
      p50: number;
      p90: number;
      p95: number;
      p99: number;
    };
  };
  workers: {
    total_count: number;
    healthy_count: number;
    stale_count: number;
    fleet: Array<{
      worker_id: string;
      worker_type: string;
      started_at: string | null;
      last_seen: string | null;
      state: string;
      health: string;
      heartbeat_age_seconds: number;
    }>;
  };
}

export default function SystemHealthClient() {
  const [data, setData] = useState<SystemOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOverview = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/v1/system/overview");
      if (!res.ok) {
        throw new Error(`Failed to load system health: HTTP ${res.status}`);
      }
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err: any) {
      setError(err?.message || "Failed to load system metrics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(fetchOverview, 10_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Platform System Health & Observability</h1>
          <p className="text-muted-foreground text-sm">
            Internal telemetry, latency distributions, background queue depths, and worker fleet monitoring.
          </p>
        </div>
        <button
          onClick={fetchOverview}
          disabled={loading}
          className="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-md hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-destructive/10 text-destructive text-sm font-medium border border-destructive/20">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Key Metric KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-lg border bg-card text-card-foreground shadow-sm">
              <div className="text-sm font-medium text-muted-foreground">API Latency (p95)</div>
              <div className="text-2xl font-bold mt-1">
                {data.telemetry?.api_latency?.p95 ? `${(data.telemetry.api_latency.p95 * 1000).toFixed(1)}ms` : "0.0ms"}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                p50: {(data.telemetry?.api_latency?.p50 * 1000 || 0).toFixed(1)}ms | p99: {(data.telemetry?.api_latency?.p99 * 1000 || 0).toFixed(1)}ms
              </div>
            </div>

            <div className="p-4 rounded-lg border bg-card text-card-foreground shadow-sm">
              <div className="text-sm font-medium text-muted-foreground">Worker Job Latency (p95)</div>
              <div className="text-2xl font-bold mt-1">
                {data.telemetry?.worker_latency?.p95 ? `${(data.telemetry.worker_latency.p95 * 1000).toFixed(1)}ms` : "0.0ms"}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Processed: {data.telemetry?.worker_latency?.count || 0} jobs
              </div>
            </div>

            <div className="p-4 rounded-lg border bg-card text-card-foreground shadow-sm">
              <div className="text-sm font-medium text-muted-foreground">Pending Task Queues</div>
              <div className="text-2xl font-bold mt-1">
                {(data.queues?.evaluation_depth || 0) + (data.queues?.replay_depth || 0) + (data.queues?.regression_depth || 0)}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Eval: {data.queues?.evaluation_depth || 0} | Replay: {data.queues?.replay_depth || 0} | Reg: {data.queues?.regression_depth || 0}
              </div>
            </div>

            <div className="p-4 rounded-lg border bg-card text-card-foreground shadow-sm">
              <div className="text-sm font-medium text-muted-foreground">Active Worker Fleet</div>
              <div className="text-2xl font-bold mt-1">
                {data.workers?.healthy_count || 0} / {data.workers?.total_count || 0}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                DB: <span className={data.infrastructure?.database?.status === "ok" ? "text-emerald-500 font-semibold" : "text-destructive"}>{data.infrastructure?.database?.status}</span> | Redis: <span className={data.infrastructure?.redis?.status === "ok" ? "text-emerald-500 font-semibold" : "text-amber-500"}>{data.infrastructure?.redis?.status}</span>
              </div>
            </div>
          </div>

          {/* Infrastructure & Queues Section */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-5 rounded-lg border bg-card text-card-foreground shadow-sm space-y-4">
              <h2 className="text-lg font-semibold">Queue Depth & Processing Lag</h2>
              <div className="space-y-3">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Evaluation Queue:</span>
                  <span className="font-mono font-medium">{data.queues?.evaluation_depth || 0} jobs</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Replay Queue:</span>
                  <span className="font-mono font-medium">{data.queues?.replay_depth || 0} executions</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Regression Queue:</span>
                  <span className="font-mono font-medium">{data.queues?.regression_depth || 0} reports</span>
                </div>
              </div>
            </div>

            <div className="p-5 rounded-lg border bg-card text-card-foreground shadow-sm space-y-4">
              <h2 className="text-lg font-semibold">Prometheus Telemetry Scrape</h2>
              <p className="text-xs text-muted-foreground">
                AgentLens exposes raw platform telemetry in standard Prometheus format at <code className="px-1.5 py-0.5 bg-muted rounded font-mono">/metrics</code>.
              </p>
              <div className="pt-2">
                <a
                  href="/metrics"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center text-sm text-primary hover:underline font-medium"
                >
                  Open /metrics endpoint &rarr;
                </a>
              </div>
            </div>
          </div>

          {/* Worker Fleet Table */}
          <div className="p-5 rounded-lg border bg-card text-card-foreground shadow-sm space-y-4">
            <h2 className="text-lg font-semibold">Worker Fleet Status</h2>
            {data.workers?.fleet && data.workers.fleet.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs uppercase bg-muted text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2">Worker ID</th>
                      <th className="px-4 py-2">Type</th>
                      <th className="px-4 py-2">Health</th>
                      <th className="px-4 py-2">Heartbeat Age</th>
                      <th className="px-4 py-2">Last Seen</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {data.workers.fleet.map((w) => (
                      <tr key={w.worker_id} className="hover:bg-muted/50">
                        <td className="px-4 py-2.5 font-mono text-xs">{w.worker_id}</td>
                        <td className="px-4 py-2.5 capitalize">{w.worker_type}</td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`px-2 py-0.5 text-xs rounded-full font-medium ${
                              w.health === "healthy"
                                ? "bg-emerald-500/10 text-emerald-600"
                                : w.health === "stale"
                                ? "bg-amber-500/10 text-amber-600"
                                : "bg-destructive/10 text-destructive"
                            }`}
                          >
                            {w.health}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs">{w.heartbeat_age_seconds}s ago</td>
                        <td className="px-4 py-2.5 text-xs text-muted-foreground">
                          {w.last_seen ? new Date(w.last_seen).toLocaleTimeString() : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground py-4 text-center">
                No active worker heartbeats recorded yet.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
