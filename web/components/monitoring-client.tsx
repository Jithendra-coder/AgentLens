"use client";

import { useEffect, useState } from "react";

interface MonitorItem {
  monitor_id: string;
  project_id: string;
  name: string;
  sampling_rate: number;
  health_status: string;
  health_index: number;
  is_active: boolean;
  created_at: string;
}

interface SnapshotItem {
  snapshot_id: string;
  monitor_id: string;
  health_index: number;
  p95_latency_ms: number;
  mean_quality_score: number;
  error_rate: number;
  total_spans_evaluated: number;
  recorded_at: string;
}

interface HealthSummary {
  project_id: string;
  overall_health_index: number;
  overall_health_status: string;
  monitors_count: number;
  active_monitors: number;
}

export default function ContinuousMonitoringClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [summary, setSummary] = useState<HealthSummary | null>(null);
  const [monitors, setMonitors] = useState<MonitorItem[]>([]);
  const [selectedMonitorId, setSelectedMonitorId] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State - Create Monitor
  const [monName, setMonName] = useState("");
  const [monSamplingRate, setMonSamplingRate] = useState(0.10);
  const [creatingMon, setCreatingMon] = useState(false);

  // Form State - Record Snapshot
  const [snapQuality, setSnapQuality] = useState(0.92);
  const [snapLatency, setSnapLatency] = useState(350);
  const [snapErrorRate, setSnapErrorRate] = useState(0.01);
  const [snapSpans, setSnapSpans] = useState(120);
  const [recordingSnap, setRecordingSnap] = useState(false);

  const fetchHealthAndMonitors = async () => {
    setLoading(true);
    try {
      const resSum = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/monitors/health`);
      if (resSum.ok) {
        const dataSum = await resSum.json();
        setSummary(dataSum);
      }

      const resM = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/monitors`);
      if (!resM.ok) throw new Error(`HTTP ${resM.status}`);
      const dataM = await resM.json();
      const list = dataM.monitors || [];
      setMonitors(list);
      if (list.length > 0 && !selectedMonitorId) {
        setSelectedMonitorId(list[0].monitor_id);
      }
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load monitors");
    } finally {
      setLoading(false);
    }
  };

  const fetchSnapshots = async (monId: string) => {
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/monitors/${encodeURIComponent(monId)}/snapshots`
      );
      if (res.ok) {
        const data = await res.json();
        setSnapshots(data.snapshots || []);
      }
    } catch (err: unknown) {
      console.error(err);
    }
  };

  useEffect(() => {
    void fetchHealthAndMonitors();
  }, [projectId]);

  useEffect(() => {
    if (selectedMonitorId) {
      void fetchSnapshots(selectedMonitorId);
    }
  }, [selectedMonitorId]);

  const handleCreateMonitor = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!monName.trim()) return;
    setCreatingMon(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/monitors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: monName.trim(),
          sampling_rate: Number(monSamplingRate),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMonName("");
      setSelectedMonitorId(data.monitor_id);
      await fetchHealthAndMonitors();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create monitor");
    } finally {
      setCreatingMon(false);
    }
  };

  const handleRecordSnapshot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMonitorId) return;
    setRecordingSnap(true);
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/monitors/${encodeURIComponent(selectedMonitorId)}/snapshots`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mean_quality_score: Number(snapQuality),
            p95_latency_ms: Number(snapLatency),
            error_rate: Number(snapErrorRate),
            total_spans_evaluated: Number(snapSpans),
          }),
        }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchSnapshots(selectedMonitorId);
      await fetchHealthAndMonitors();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to record snapshot");
    } finally {
      setRecordingSnap(false);
    }
  };

  const handleDeleteMonitor = async (id: string) => {
    if (!confirm("Are you sure you want to delete this monitor?")) return;
    try {
      await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/monitors/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      setSelectedMonitorId(null);
      await fetchHealthAndMonitors();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Continuous Production Monitoring & Health</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Real-time background trace stream sampling, quality rollups, and dynamic aggregate health indexing (0-100).
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="monitoring-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="monitoring-project-select"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="text-xs border rounded px-2.5 py-1 bg-background text-foreground"
        >
          <option value="proj-default">proj-default</option>
          <option value="proj-prod">proj-prod</option>
          <option value="proj-staging">proj-staging</option>
        </select>
      </div>

      {error && <div className="p-3 text-xs text-destructive bg-destructive/10 rounded">{error}</div>}

      {/* Aggregate Health Summary Card */}
      {summary && (
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="space-y-1">
            <h2 className="text-sm font-semibold uppercase text-muted-foreground">System Health Index</h2>
            <div className="flex items-baseline space-x-3">
              <span className="text-4xl font-black font-mono tracking-tight text-foreground">
                {summary.overall_health_index.toFixed(1)}
              </span>
              <span className="text-xs text-muted-foreground font-mono">/ 100</span>
              <span
                className={`px-2.5 py-0.5 rounded text-xs font-bold font-mono uppercase ${
                  summary.overall_health_status === "healthy"
                    ? "bg-green-500/20 text-green-700 dark:text-green-300"
                    : summary.overall_health_status === "degraded"
                    ? "bg-yellow-500/20 text-yellow-700 dark:text-yellow-300"
                    : "bg-red-500/20 text-red-700 dark:text-red-300"
                }`}
              >
                {summary.overall_health_status}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Calculated dynamically from live trace quality (50%), latency SLA compliance (25%), and error rate (25%).
            </p>
          </div>

          <div className="flex items-center space-x-6 text-xs font-mono">
            <div>
              <span className="text-muted-foreground text-[10px]">MONITORS:</span>
              <div className="font-bold text-foreground">{summary.monitors_count} Total</div>
            </div>
            <div>
              <span className="text-muted-foreground text-[10px]">ACTIVE SAMPLING:</span>
              <div className="font-bold text-foreground">{summary.active_monitors} Running</div>
            </div>
          </div>
        </div>
      )}

      {/* Monitors List & Snapshot Recording */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Monitors Sidebar */}
        <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
          <h2 className="text-sm font-semibold">Continuous Monitors</h2>
          {loading ? (
            <div className="text-xs text-muted-foreground">Loading monitors...</div>
          ) : monitors.length === 0 ? (
            <div className="p-4 border rounded text-center text-xs text-muted-foreground">
              No monitors configured.
            </div>
          ) : (
            <div className="space-y-2">
              {monitors.map((m) => (
                <div
                  key={m.monitor_id}
                  onClick={() => setSelectedMonitorId(m.monitor_id)}
                  className={`p-3 border rounded-lg cursor-pointer text-xs transition ${
                    selectedMonitorId === m.monitor_id ? "bg-accent/40 border-primary" : "hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">{m.name}</span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-bold uppercase ${
                        m.health_status === "healthy"
                          ? "bg-green-500/20 text-green-700 dark:text-green-300"
                          : m.health_status === "degraded"
                          ? "bg-yellow-500/20 text-yellow-700 dark:text-yellow-300"
                          : "bg-red-500/20 text-red-700 dark:text-red-300"
                      }`}
                    >
                      {m.health_index.toFixed(0)} ({m.health_status})
                    </span>
                  </div>
                  <div className="text-[11px] text-muted-foreground font-mono mt-1">
                    Sampling: {(m.sampling_rate * 100).toFixed(0)}% of live traffic
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* New Monitor Form */}
          <form onSubmit={handleCreateMonitor} className="pt-3 border-t space-y-2">
            <h3 className="text-xs font-semibold">New Monitor</h3>
            <input
              type="text"
              required
              value={monName}
              onChange={(e) => setMonName(e.target.value)}
              placeholder="Monitor Name (e.g. Chatbot Production)"
              className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
            />
            <div className="space-y-0.5">
              <label className="text-[11px] font-semibold text-muted-foreground">
                Sampling Rate: {(monSamplingRate * 100).toFixed(0)}%
              </label>
              <input
                type="range"
                min="0.01"
                max="1.0"
                step="0.01"
                value={monSamplingRate}
                onChange={(e) => setMonSamplingRate(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <button
              type="submit"
              disabled={creatingMon}
              className="w-full py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {creatingMon ? "Creating..." : "Create Monitor"}
            </button>
          </form>
        </div>

        {/* Record Snapshot & Timeline */}
        <div className="lg:col-span-2 p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Record Health Rollup Snapshot</h2>
            {selectedMonitorId && (
              <button
                onClick={() => handleDeleteMonitor(selectedMonitorId)}
                className="text-xs text-destructive hover:underline"
              >
                Delete Monitor
              </button>
            )}
          </div>

          <form onSubmit={handleRecordSnapshot} className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">Mean Quality (0-1)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  required
                  value={snapQuality}
                  onChange={(e) => setSnapQuality(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">P95 Latency (ms)</label>
                <input
                  type="number"
                  required
                  value={snapLatency}
                  onChange={(e) => setSnapLatency(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">Error Rate (0-1)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  required
                  value={snapErrorRate}
                  onChange={(e) => setSnapErrorRate(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">Spans Evaluated</label>
                <input
                  type="number"
                  required
                  value={snapSpans}
                  onChange={(e) => setSnapSpans(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={recordingSnap || !selectedMonitorId}
              className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {recordingSnap ? "Calculating & Recording..." : "Record Health Rollup"}
            </button>
          </form>

          {/* Snapshots Timeline Table */}
          <div className="pt-4 border-t space-y-2">
            <h3 className="text-xs font-semibold uppercase text-muted-foreground">Time-Series Health Snapshots</h3>
            {snapshots.length === 0 ? (
              <div className="text-xs text-muted-foreground">No health snapshots recorded for this monitor.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="pb-1.5">Health Index</th>
                      <th className="pb-1.5 text-right">Mean Quality</th>
                      <th className="pb-1.5 text-right">P95 Latency</th>
                      <th className="pb-1.5 text-right">Error Rate</th>
                      <th className="pb-1.5 text-right">Spans</th>
                      <th className="pb-1.5 text-right">Recorded At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y font-mono">
                    {snapshots.slice(0, 10).map((s) => (
                      <tr key={s.snapshot_id}>
                        <td className="py-2 font-bold text-foreground">{s.health_index.toFixed(1)} / 100</td>
                        <td className="py-2 text-right font-semibold">{(s.mean_quality_score * 100).toFixed(1)}%</td>
                        <td className="py-2 text-right">{s.p95_latency_ms.toFixed(0)} ms</td>
                        <td className="py-2 text-right">{(s.error_rate * 100).toFixed(1)}%</td>
                        <td className="py-2 text-right">{s.total_spans_evaluated}</td>
                        <td className="py-2 text-right text-muted-foreground">{new Date(s.recorded_at).toLocaleTimeString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
