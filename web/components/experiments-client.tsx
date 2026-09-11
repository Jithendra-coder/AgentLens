"use client";

import { useEffect, useState } from "react";

interface VariantMetric {
  variant_id: string;
  name: string;
  is_control: boolean;
  sample_count: number;
  mean_score: number;
  mean_cost_usd: number;
  mean_latency_ms: number;
  score_delta_pct: number;
  cost_delta_pct: number;
  latency_delta_pct: number;
}

interface ExperimentReportData {
  experiment_id: string;
  project_id: string;
  name: string;
  status: string;
  total_evaluations: number;
  variants: VariantMetric[];
}

interface ExperimentListItem {
  experiment_id: string;
  project_id: string;
  name: string;
  description?: string;
  experiment_type: string;
  status: string;
  variants_count: number;
  created_at: string;
}

export default function ExperimentationStudioClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [experiments, setExperiments] = useState<ExperimentListItem[]>([]);
  const [selectedExpId, setSelectedExpId] = useState<string | null>(null);
  const [report, setReport] = useState<ExperimentReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [controlName, setControlName] = useState("Control (GPT-4o)");
  const [controlModel, setControlModel] = useState("gpt-4o");
  const [treatmentName, setTreatmentName] = useState("Treatment (Claude 3.5 Sonnet)");
  const [treatmentModel, setTreatmentModel] = useState("claude-3-5-sonnet-20241022");
  const [creating, setCreating] = useState(false);

  // Split Test State
  const [routingKey, setRoutingKey] = useState("user-session-12345");
  const [splitResult, setSplitResult] = useState<Record<string, unknown> | null>(null);
  const [splitting, setSplitting] = useState(false);

  const fetchExperiments = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/experiments`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const list = data.experiments || [];
      setExperiments(list);
      if (list.length > 0 && !selectedExpId) {
        setSelectedExpId(list[0].experiment_id);
      }
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load experiments");
    } finally {
      setLoading(false);
    }
  };

  const fetchReport = async (expId: string) => {
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(expId)}/report`
      );
      if (!res.ok) throw new Error(`Report HTTP ${res.status}`);
      const data = await res.json();
      setReport(data);
    } catch (err: unknown) {
      console.error(err);
    }
  };

  useEffect(() => {
    void fetchExperiments();
  }, [projectId]);

  useEffect(() => {
    if (selectedExpId) {
      void fetchReport(selectedExpId);
    } else {
      setReport(null);
    }
  }, [selectedExpId]);

  const handleCreateExperiment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/experiments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || undefined,
          experiment_type: "ab_test",
          variants: [
            {
              name: controlName.trim(),
              model_name: controlModel.trim(),
              provider_type: "openai",
              traffic_weight: 0.5,
              is_control: true,
            },
            {
              name: treatmentName.trim(),
              model_name: treatmentModel.trim(),
              provider_type: "anthropic",
              traffic_weight: 0.5,
              is_control: false,
            },
          ],
        }),
      });
      if (!res.ok) throw new Error(`Create failed: HTTP ${res.status}`);
      const data = await res.json();
      setName("");
      setDescription("");
      setSelectedExpId(data.experiment_id);
      await fetchExperiments();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create experiment");
    } finally {
      setCreating(false);
    }
  };

  const handleTestSplit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedExpId || !routingKey.trim()) return;
    setSplitting(true);
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(selectedExpId)}/split`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ routing_key: routingKey.trim() }),
        }
      );
      if (!res.ok) throw new Error(`Split failed: HTTP ${res.status}`);
      const data = await res.json();
      setSplitResult(data);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Traffic split test failed");
    } finally {
      setSplitting(false);
    }
  };

  const handleDeleteExperiment = async (expId: string) => {
    if (!confirm("Are you sure you want to delete this experiment?")) return;
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(expId)}`,
        { method: "DELETE" }
      );
      if (!res.ok) throw new Error(`Delete failed: HTTP ${res.status}`);
      if (selectedExpId === expId) {
        setSelectedExpId(null);
      }
      await fetchExperiments();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete experiment");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Prompt & Model Experimentation Studio</h1>
        <p className="text-sm text-muted-foreground mt-1">
          A/B testing, deterministic traffic routing, and comparative statistical reporting across prompt and model variants.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="exp-studio-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="exp-studio-project-select"
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Experiments List Sidebar */}
        <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
          <h2 className="text-sm font-semibold">Active Experiments</h2>
          {loading ? (
            <div className="text-xs text-muted-foreground">Loading experiments...</div>
          ) : experiments.length === 0 ? (
            <div className="p-4 border rounded text-center text-xs text-muted-foreground">
              No experiments found. Create your first A/B test below.
            </div>
          ) : (
            <div className="space-y-2">
              {experiments.map((exp) => (
                <div
                  key={exp.experiment_id}
                  onClick={() => setSelectedExpId(exp.experiment_id)}
                  className={`p-3 border rounded-lg cursor-pointer text-xs transition ${
                    selectedExpId === exp.experiment_id ? "bg-accent/40 border-primary" : "hover:bg-muted/40"
                  }`}
                >
                  <div className="flex items-center justify-between font-semibold">
                    <span>{exp.name}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteExperiment(exp.experiment_id);
                      }}
                      className="text-destructive hover:underline text-[11px]"
                    >
                      Delete
                    </button>
                  </div>
                  <div className="flex items-center space-x-2 text-[11px] text-muted-foreground mt-1">
                    <span className="uppercase">{exp.experiment_type}</span>
                    <span>•</span>
                    <span>{exp.variants_count} variants</span>
                    <span>•</span>
                    <span className="capitalize">{exp.status}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Experiment Report & Comparative Metrics */}
        <div className="lg:col-span-2 space-y-6">
          {report ? (
            <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-semibold">{report.name}</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Evaluated Runs: <strong className="text-foreground">{report.total_evaluations}</strong>
                  </p>
                </div>
                <span className="text-xs px-2.5 py-1 rounded bg-secondary uppercase font-semibold">
                  {report.status}
                </span>
              </div>

              {/* Comparative Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="pb-2 font-semibold">Variant</th>
                      <th className="pb-2 font-semibold text-right">Samples</th>
                      <th className="pb-2 font-semibold text-right">Avg Quality</th>
                      <th className="pb-2 font-semibold text-right">Δ Quality</th>
                      <th className="pb-2 font-semibold text-right">Avg Cost</th>
                      <th className="pb-2 font-semibold text-right">Δ Cost</th>
                      <th className="pb-2 font-semibold text-right">Avg Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y font-mono">
                    {report.variants.map((v) => (
                      <tr key={v.variant_id} className="hover:bg-muted/40">
                        <td className="py-2.5 font-semibold text-foreground">
                          {v.name} {v.is_control && <span className="text-muted-foreground text-[10px]">(Control)</span>}
                        </td>
                        <td className="py-2.5 text-right">{v.sample_count}</td>
                        <td className="py-2.5 text-right font-bold">{(v.mean_score * 100).toFixed(1)}%</td>
                        <td className={`py-2.5 text-right font-semibold ${v.score_delta_pct > 0 ? "text-green-600" : v.score_delta_pct < 0 ? "text-red-600" : "text-muted-foreground"}`}>
                          {v.is_control ? "—" : `${v.score_delta_pct > 0 ? "+" : ""}${v.score_delta_pct.toFixed(1)}%`}
                        </td>
                        <td className="py-2.5 text-right">${v.mean_cost_usd.toFixed(4)}</td>
                        <td className={`py-2.5 text-right font-semibold ${v.cost_delta_pct < 0 ? "text-green-600" : v.cost_delta_pct > 0 ? "text-amber-600" : "text-muted-foreground"}`}>
                          {v.is_control ? "—" : `${v.cost_delta_pct > 0 ? "+" : ""}${v.cost_delta_pct.toFixed(1)}%`}
                        </td>
                        <td className="py-2.5 text-right">{v.mean_latency_ms.toFixed(0)} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Traffic Split Simulator */}
              <div className="pt-4 border-t space-y-3">
                <h3 className="text-xs font-semibold uppercase text-muted-foreground">Traffic Routing Simulator</h3>
                <form onSubmit={handleTestSplit} className="flex space-x-2">
                  <input
                    type="text"
                    required
                    value={routingKey}
                    onChange={(e) => setRoutingKey(e.target.value)}
                    placeholder="Enter seed / user ID / trace ID"
                    className="flex-1 text-xs border rounded p-2 bg-background text-foreground font-mono"
                  />
                  <button
                    type="submit"
                    disabled={splitting}
                    className="px-3 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    {splitting ? "Routing..." : "Split Traffic"}
                  </button>
                </form>

                {splitResult && (
                  <div className="p-3 border rounded bg-accent/20 text-xs flex items-center justify-between">
                    <div>
                      Routed to: <strong className="text-foreground">{String(splitResult.variant_name)}</strong>
                      <span className="text-muted-foreground text-[11px] ml-2">({String(splitResult.model_name)})</span>
                    </div>
                    {Boolean(splitResult.is_control) && (
                      <span className="text-[10px] bg-secondary px-1.5 py-0.5 rounded font-semibold">CONTROL</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="p-12 border rounded-lg text-center text-xs text-muted-foreground">
              Select an experiment on the left to view its comparative report.
            </div>
          )}
        </div>
      </div>

      {/* Create Experiment Form */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4 max-w-3xl">
        <h2 className="text-base font-semibold">Launch New A/B Experiment</h2>
        <form onSubmit={handleCreateExperiment} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold">Experiment Name</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. GPT-4o vs Claude 3.5 Sonnet RAG"
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold">Description</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Comparing retrieval synthesis quality and cost"
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            {/* Control Variant */}
            <div className="p-4 border rounded bg-accent/10 space-y-2">
              <span className="text-xs font-semibold text-primary">Control Variant (50% Traffic)</span>
              <div className="space-y-1">
                <label className="text-[11px]">Variant Label</label>
                <input
                  type="text"
                  required
                  value={controlName}
                  onChange={(e) => setControlName(e.target.value)}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px]">Model Identifier</label>
                <input
                  type="text"
                  required
                  value={controlModel}
                  onChange={(e) => setControlModel(e.target.value)}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
            </div>

            {/* Treatment Variant */}
            <div className="p-4 border rounded bg-accent/10 space-y-2">
              <span className="text-xs font-semibold text-primary">Treatment Variant (50% Traffic)</span>
              <div className="space-y-1">
                <label className="text-[11px]">Variant Label</label>
                <input
                  type="text"
                  required
                  value={treatmentName}
                  onChange={(e) => setTreatmentName(e.target.value)}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px]">Model Identifier</label>
                <input
                  type="text"
                  required
                  value={treatmentModel}
                  onChange={(e) => setTreatmentModel(e.target.value)}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={creating}
              className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {creating ? "Launching Experiment..." : "Launch Experiment"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
