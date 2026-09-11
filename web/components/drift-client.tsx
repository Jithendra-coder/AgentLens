"use client";

import { useEffect, useState } from "react";

interface BaselineItem {
  baseline_id: string;
  project_id: string;
  name: string;
  metric_name: string;
  baseline_mean: number;
  baseline_std: number;
  window_size: number;
  status: string;
  created_at: string;
}

interface DriftObservationItem {
  drift_id: string;
  baseline_id: string;
  project_id: string;
  observed_mean: number;
  z_score: number;
  drift_magnitude_pct: number;
  drift_type: string;
  is_alert: boolean;
  observed_at: string;
}

export default function DriftIntelligenceClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [baselines, setBaselines] = useState<BaselineItem[]>([]);
  const [observations, setObservations] = useState<DriftObservationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State - New Baseline
  const [baseName, setBaseName] = useState("");
  const [baseMetric, setBaseMetric] = useState("quality_score");
  const [baseMean, setBaseMean] = useState(0.88);
  const [baseStd, setBaseStd] = useState(0.04);
  const [baseWindow, setBaseWindow] = useState(50);
  const [creatingBaseline, setCreatingBaseline] = useState(false);

  // Form State - Evaluate / Ingest Drift
  const [evalBaselineId, setEvalBaselineId] = useState("");
  const [rawValues, setRawValues] = useState("0.75, 0.72, 0.78, 0.74, 0.76");
  const [evaluatingDrift, setEvaluatingDrift] = useState(false);
  const [evalResult, setEvalResult] = useState<{
    drift_type: string;
    is_alert: boolean;
    z_score: number;
    drift_magnitude_pct: number;
    reason: string;
  } | null>(null);

  const fetchBaselinesAndObservations = async () => {
    setLoading(true);
    try {
      const resB = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/drift/baselines`);
      if (!resB.ok) throw new Error(`HTTP ${resB.status}`);
      const dataB = await resB.json();
      const bList = dataB.baselines || [];
      setBaselines(bList);
      if (bList.length > 0 && !evalBaselineId) {
        setEvalBaselineId(bList[0].baseline_id);
      }

      const resO = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/drift/observations`);
      if (resO.ok) {
        const dataO = await resO.json();
        setObservations(dataO.observations || []);
      }
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to fetch drift data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchBaselinesAndObservations();
  }, [projectId]);

  const handleCreateBaseline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!baseName.trim()) return;
    setCreatingBaseline(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/drift/baselines`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: baseName.trim(),
          metric_name: baseMetric,
          baseline_mean: Number(baseMean),
          baseline_std: Number(baseStd),
          window_size: Number(baseWindow),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setBaseName("");
      await fetchBaselinesAndObservations();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create baseline");
    } finally {
      setCreatingBaseline(false);
    }
  };

  const handleDetectDrift = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!evalBaselineId) return;
    setEvaluatingDrift(true);
    try {
      const parsedValues = rawValues
        .split(",")
        .map((v) => Number(v.trim()))
        .filter((n) => !isNaN(n));

      if (parsedValues.length === 0) {
        alert("Please provide valid comma-separated numerical samples.");
        return;
      }

      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/drift/detect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseline_id: evalBaselineId,
          observed_values: parsedValues,
          z_alert_threshold: 2.0,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEvalResult({
        drift_type: data.drift_type,
        is_alert: data.is_alert,
        z_score: data.z_score,
        drift_magnitude_pct: data.drift_magnitude_pct,
        reason: data.reason,
      });
      await fetchBaselinesAndObservations();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to evaluate drift");
    } finally {
      setEvaluatingDrift(false);
    }
  };

  const handleDeleteBaseline = async (id: string) => {
    if (!confirm("Are you sure you want to delete this baseline?")) return;
    try {
      await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/drift/baselines/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      await fetchBaselinesAndObservations();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Regression & Baseline Drift Intelligence</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Statistical reference baseline tracking, automated Z-score drift detection, and early warning regression alerts.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="drift-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="drift-project-select"
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

      {/* Active Baselines Grid */}
      <div className="space-y-3">
        <h2 className="text-sm font-semibold">Active Metric Baselines</h2>
        {loading ? (
          <div className="text-xs text-muted-foreground">Loading baselines...</div>
        ) : baselines.length === 0 ? (
          <div className="p-6 border rounded-lg text-center text-xs text-muted-foreground bg-card">
            No baselines established for this project. Create a baseline below to enable statistical drift monitoring.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {baselines.map((b) => (
              <div key={b.baseline_id} className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-foreground">{b.name}</span>
                  <button
                    onClick={() => handleDeleteBaseline(b.baseline_id)}
                    className="text-[11px] text-destructive hover:underline"
                  >
                    Delete
                  </button>
                </div>
                <div className="text-[11px] font-mono text-muted-foreground">
                  Metric: <span className="text-foreground font-semibold uppercase">{b.metric_name}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 pt-2 border-t text-xs font-mono">
                  <div>
                    <span className="text-muted-foreground text-[10px]">MEAN (\u03bc):</span>
                    <div className="font-bold text-foreground">
                      {b.metric_name === "cost_usd"
                        ? `$${b.baseline_mean.toFixed(4)}`
                        : b.metric_name === "latency_ms"
                        ? `${b.baseline_mean.toFixed(0)} ms`
                        : `${(b.baseline_mean * 100).toFixed(1)}%`}
                    </div>
                  </div>
                  <div>
                    <span className="text-muted-foreground text-[10px]">STD DEV (\u03c3):</span>
                    <div className="font-bold text-foreground">{b.baseline_std.toFixed(3)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Create Baseline Form */}
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Establish Statistical Baseline</h2>
          <form onSubmit={handleCreateBaseline} className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold">Baseline Name</label>
              <input
                type="text"
                required
                value={baseName}
                onChange={(e) => setBaseName(e.target.value)}
                placeholder="e.g. Production RAG Quality Baseline"
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label htmlFor="base-metric-select" className="text-xs font-semibold">Metric</label>
                <select
                  id="base-metric-select"
                  value={baseMetric}
                  onChange={(e) => setBaseMetric(e.target.value)}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground"
                >
                  <option value="quality_score">Quality Score (0-1)</option>
                  <option value="latency_ms">Latency (ms)</option>
                  <option value="cost_usd">Cost per Trace ($)</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Baseline Mean (\u03bc)</label>
                <input
                  type="number"
                  step="0.001"
                  required
                  value={baseMean}
                  onChange={(e) => setBaseMean(Number(e.target.value))}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Std Dev (\u03c3)</label>
                <input
                  type="number"
                  step="0.001"
                  required
                  value={baseStd}
                  onChange={(e) => setBaseStd(Number(e.target.value))}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Window Size (N)</label>
                <input
                  type="number"
                  required
                  value={baseWindow}
                  onChange={(e) => setBaseWindow(Number(e.target.value))}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={creatingBaseline}
              className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {creatingBaseline ? "Establishing..." : "Establish Baseline"}
            </button>
          </form>
        </div>

        {/* Live Drift Detection Simulator */}
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Live Drift & Regression Ingestion</h2>
          <form onSubmit={handleDetectDrift} className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="eval-baseline-select" className="text-xs font-semibold">Target Baseline</label>
              <select
                id="eval-baseline-select"
                value={evalBaselineId}
                onChange={(e) => setEvalBaselineId(e.target.value)}
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              >
                {baselines.map((b) => (
                  <option key={b.baseline_id} value={b.baseline_id}>
                    {b.name} ({b.metric_name}, \u03bc={b.baseline_mean})
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold">Observed Values (comma-separated)</label>
              <input
                type="text"
                required
                value={rawValues}
                onChange={(e) => setRawValues(e.target.value)}
                placeholder="e.g. 0.75, 0.72, 0.78, 0.74, 0.76"
                className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={evaluatingDrift || !evalBaselineId}
              className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {evaluatingDrift ? "Calculating Z-Score..." : "Evaluate Drift & Z-Score"}
            </button>
          </form>

          {evalResult && (
            <div
              className={`p-3.5 border rounded-lg text-xs font-mono space-y-1.5 ${
                evalResult.is_alert ? "bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-300" : "bg-green-500/10 border-green-500/30 text-green-700 dark:text-green-300"
              }`}
            >
              <div className="flex items-center justify-between font-bold">
                <span className="uppercase">{evalResult.drift_type}</span>
                <span>Z = {evalResult.z_score.toFixed(2)} ({evalResult.drift_magnitude_pct > 0 ? "+" : ""}{evalResult.drift_magnitude_pct.toFixed(1)}%)</span>
              </div>
              <div className="text-[11px] opacity-90">{evalResult.reason}</div>
            </div>
          )}
        </div>
      </div>

      {/* Drift Observations Stream */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
        <h2 className="text-base font-semibold">Recent Drift Observations & Regression Audit Log</h2>
        {observations.length === 0 ? (
          <div className="p-6 border rounded text-center text-xs text-muted-foreground">
            No drift observations recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="pb-2 font-semibold">Status</th>
                  <th className="pb-2 font-semibold">Drift Classification</th>
                  <th className="pb-2 font-semibold text-right">Observed Mean</th>
                  <th className="pb-2 font-semibold text-right">Z-Score</th>
                  <th className="pb-2 font-semibold text-right">Magnitude Delta</th>
                  <th className="pb-2 font-semibold text-right">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y font-mono">
                {observations.map((o) => (
                  <tr key={o.drift_id} className="hover:bg-muted/40">
                    <td className="py-2.5">
                      {o.is_alert ? (
                        <span className="px-2 py-0.5 rounded bg-red-500/20 text-red-600 font-bold text-[10px]">ALERT</span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-green-500/20 text-green-600 font-bold text-[10px]">NORMAL</span>
                      )}
                    </td>
                    <td className="py-2.5 font-bold uppercase text-foreground">{o.drift_type}</td>
                    <td className="py-2.5 text-right">{o.observed_mean.toFixed(4)}</td>
                    <td className="py-2.5 text-right font-semibold">{o.z_score.toFixed(2)}</td>
                    <td className="py-2.5 text-right">{o.drift_magnitude_pct > 0 ? "+" : ""}{o.drift_magnitude_pct.toFixed(1)}%</td>
                    <td className="py-2.5 text-right text-muted-foreground">{new Date(o.observed_at).toLocaleTimeString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
