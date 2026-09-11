"use client";

import { useCallback, useEffect, useState } from "react";
import { dashboardFetch, formatDate, formatNumber } from "../lib/client";
import type { RuntimeSummary } from "../lib/types";
import { Badge, EmptyState, ErrorState, LoadingState } from "./ui";

export default function RuntimeClient() {
  const [runtime, setRuntime] = useState<RuntimeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setRuntime(await dashboardFetch<RuntimeSummary>("runtime/summary")); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load runtime summary."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  if (loading && !runtime) return <LoadingState label="Loading runtime health…" />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!runtime) return <EmptyState label="Runtime summary is unavailable." />;
  const counts = Object.entries(runtime.job_state_counts);
  return <>
    <div className="page-heading"><div><p className="eyebrow">Operational readout</p><h1>Runtime</h1><p className="lede">Read-only visibility into durable evaluation jobs and infrastructure health. No job mutation or destructive control is exposed here.</p></div><button className="button secondary" onClick={() => void load()} disabled={loading}>Refresh</button></div>
    <div className="grid stats"><StatusCard label="Database" value={runtime.database} /><StatusCard label="Redis wakeups" value={runtime.redis} /><StatusCard label="Worker heartbeat" value={runtime.worker} /><StatusCard label="Mode" value={runtime.read_only ? "read-only" : "unknown"} /></div>
    <div className="grid two section"><section className="card"><h2>Evaluation jobs</h2>{counts.length ? <div className="grid stats">{counts.map(([state, count]) => <div className="card" key={state}><div className="stat-label">{state}</div><div className="stat-value">{formatNumber(count)}</div></div>)}</div> : <EmptyState label="No evaluation jobs recorded." />}</section><section className="card"><h2>Recent failures</h2>{runtime.recent_failures.length ? <div className="table-wrap"><table><thead><tr><th>Type</th><th>State</th><th>Failure</th><th>Updated</th></tr></thead><tbody>{runtime.recent_failures.map((failure) => <tr key={failure.job_id}><td>{failure.evaluation_type}<div className="subtle mono">{failure.job_id}</div></td><td><Badge value={failure.state} /></td><td><span className="error">{failure.error_code ?? "unknown"}</span><div className="subtle">{failure.message ?? "No safe message recorded."}</div></td><td>{formatDate(failure.updated_at)}</td></tr>)}</tbody></table></div> : <EmptyState label="No retry or dead-letter failures in the runtime ledger." />}</section></div>
    <section className="card section"><h2>Worker heartbeats</h2>{runtime.workers.length ? <div className="table-wrap"><table><thead><tr><th>Worker</th><th>Type</th><th>State</th><th>Last seen</th></tr></thead><tbody>{runtime.workers.map((worker) => <tr key={worker.worker_id}><td className="mono">{worker.worker_id}</td><td>{worker.worker_type}</td><td><Badge value={`${worker.state}/${worker.health}`} /></td><td>{formatDate(worker.last_seen)}</td></tr>)}</tbody></table></div> : <EmptyState label="No worker heartbeat has been recorded." />}</section>
    <p className="footer-note">Redis unavailable is degraded observability, not a destructive action.</p>
  </>;
}

function StatusCard({ label, value }: { label: string; value: string }) { return <div className="card"><div className="stat-label">{label}</div><div className="stat-value"><Badge value={value} /></div></div>; }
