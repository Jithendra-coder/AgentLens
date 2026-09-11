"use client";

import { useEffect, useState } from "react";

interface BenchmarkItem {
  benchmark_id: string;
  project_id: string;
  name: string;
  description?: string;
  created_at: string;
}

interface BenchmarkRunItem {
  run_id: string;
  benchmark_id: string;
  model_name: string;
  provider_type: string;
  overall_score: number;
  mean_latency_ms: number;
  mean_cost_usd: number;
  pass_rate: number;
  status: string;
  started_at: string;
}

interface ParetoPointItem {
  model_name: string;
  provider_type: string;
  quality_score: number;
  cost_per_1k: number;
  latency_ms: number;
  is_optimal: boolean;
}

interface ModelQualificationItem {
  qualification_id: string;
  project_id: string;
  model_name: string;
  provider_type: string;
  is_qualified: boolean;
  min_required_score: number;
  latest_run_id?: string;
  updated_at: string;
}

export default function ModelBenchmarkStudioClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [benchmarks, setBenchmarks] = useState<BenchmarkItem[]>([]);
  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState<string | null>(null);
  const [runs, setRuns] = useState<BenchmarkRunItem[]>([]);
  const [paretoPoints, setParetoPoints] = useState<ParetoPointItem[]>([]);
  const [qualifications, setQualifications] = useState<ModelQualificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State - Benchmark
  const [benchName, setBenchName] = useState("");
  const [benchDesc, setBenchDesc] = useState("");
  const [creatingBench, setCreatingBench] = useState(false);

  // Form State - Run
  const [runModel, setRunModel] = useState("gpt-4o");
  const [runProvider, setRunProvider] = useState("openai");
  const [runScore, setRunScore] = useState(0.88);
  const [runLatency, setRunLatency] = useState(950);
  const [runCost, setRunCost] = useState(0.008);
  const [runPassRate, setRunPassRate] = useState(0.92);
  const [recordingRun, setRecordingRun] = useState(false);

  const fetchBenchmarks = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/benchmarks`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const list = data.benchmarks || [];
      setBenchmarks(list);
      if (list.length > 0 && !selectedBenchmarkId) {
        setSelectedBenchmarkId(list[0].benchmark_id);
      }
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load benchmarks");
    } finally {
      setLoading(false);
    }
  };

  const fetchRunsAndPareto = async (benchId?: string) => {
    try {
      if (benchId) {
        const resRuns = await fetch(
          `/api/v1/projects/${encodeURIComponent(projectId)}/benchmarks/${encodeURIComponent(benchId)}/runs`
        );
        if (resRuns.ok) {
          const dataRuns = await resRuns.json();
          setRuns(dataRuns.runs || []);
        }
      }

      const resPareto = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/benchmarks/pareto${benchId ? `?benchmark_id=${encodeURIComponent(benchId)}` : ""}`
      );
      if (resPareto.ok) {
        const dataPareto = await resPareto.json();
        setParetoPoints(dataPareto.points || []);
      }

      const resQual = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/qualifications`);
      if (resQual.ok) {
        const dataQual = await resQual.json();
        setQualifications(dataQual.qualifications || []);
      }
    } catch (err: unknown) {
      console.error(err);
    }
  };

  useEffect(() => {
    void fetchBenchmarks();
  }, [projectId]);

  useEffect(() => {
    if (selectedBenchmarkId) {
      void fetchRunsAndPareto(selectedBenchmarkId);
    }
  }, [selectedBenchmarkId]);

  const handleCreateBenchmark = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!benchName.trim()) return;
    setCreatingBench(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/benchmarks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: benchName.trim(),
          description: benchDesc.trim() || undefined,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setBenchName("");
      setBenchDesc("");
      setSelectedBenchmarkId(data.benchmark_id);
      await fetchBenchmarks();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create benchmark");
    } finally {
      setCreatingBench(false);
    }
  };

  const handleRecordRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedBenchmarkId || !runModel.trim()) return;
    setRecordingRun(true);
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/benchmarks/${encodeURIComponent(selectedBenchmarkId)}/runs`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model_name: runModel.trim(),
            provider_type: runProvider.trim(),
            overall_score: Number(runScore),
            mean_latency_ms: Number(runLatency),
            mean_cost_usd: Number(runCost),
            pass_rate: Number(runPassRate),
            status: "completed",
          }),
        }
      );
      if (!res.ok) throw new Error(`Record run failed: HTTP ${res.status}`);
      const runData = await res.json();

      // Automatically evaluate qualification
      await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/qualifications/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: runData.run_id,
          min_required_score: 0.80,
          max_latency_ms: 2500,
          min_pass_rate: 0.80,
        }),
      });

      await fetchRunsAndPareto(selectedBenchmarkId);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to record run");
    } finally {
      setRecordingRun(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Model Benchmark & Qualification Studio</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Automated standardized model benchmarking, Pareto Frontier optimization (Cost vs Quality), and production qualification.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="benchmark-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="benchmark-project-select"
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

      {/* Qualifications Badges Row */}
      <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
        <h2 className="text-xs font-semibold uppercase text-muted-foreground">Production Qualified Models</h2>
        {qualifications.length === 0 ? (
          <div className="text-xs text-muted-foreground">No models qualified yet. Run a benchmark below to qualify models.</div>
        ) : (
          <div className="flex flex-wrap gap-2.5">
            {qualifications.map((q) => (
              <div
                key={q.qualification_id}
                className={`p-2.5 border rounded-lg text-xs flex items-center space-x-2.5 font-mono ${
                  q.is_qualified ? "bg-green-500/10 border-green-500/30 text-green-700 dark:text-green-300" : "bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-300"
                }`}
              >
                <span className="font-bold">{q.model_name}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold uppercase bg-background text-foreground">
                  {q.is_qualified ? "Qualified" : "Disqualified"}
                </span>
                <span className="text-[11px] text-muted-foreground">(Min Score: {(q.min_required_score * 100).toFixed(0)}%)</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pareto Frontier Table */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">Cost / Quality Pareto Frontier</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Models lying on the Pareto Frontier represent the mathematically non-dominated choices for routing.
            </p>
          </div>
        </div>

        {paretoPoints.length === 0 ? (
          <div className="p-6 border rounded text-center text-xs text-muted-foreground">
            No evaluation runs available to construct the Pareto Frontier.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="pb-2 font-semibold">Model</th>
                  <th className="pb-2 font-semibold">Provider</th>
                  <th className="pb-2 font-semibold text-right">Quality Score</th>
                  <th className="pb-2 font-semibold text-right">Cost / 1k Tokens</th>
                  <th className="pb-2 font-semibold text-right">Latency</th>
                  <th className="pb-2 font-semibold text-right">Pareto Frontier</th>
                </tr>
              </thead>
              <tbody className="divide-y font-mono">
                {paretoPoints.map((p) => (
                  <tr key={`${p.provider_type}:${p.model_name}`} className="hover:bg-muted/40">
                    <td className="py-2.5 font-bold text-foreground">{p.model_name}</td>
                    <td className="py-2.5 uppercase text-muted-foreground">{p.provider_type}</td>
                    <td className="py-2.5 text-right font-semibold">{(p.quality_score * 100).toFixed(1)}%</td>
                    <td className="py-2.5 text-right">${p.cost_per_1k.toFixed(4)}</td>
                    <td className="py-2.5 text-right">{p.latency_ms.toFixed(0)} ms</td>
                    <td className="py-2.5 text-right">
                      {p.is_optimal ? (
                        <span className="px-2 py-0.5 rounded bg-primary/20 text-primary font-bold text-[10px]">
                          PARETO OPTIMAL
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-[10px]">DOMINATED</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Benchmark Suites & Run Logging */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Suites Sidebar */}
        <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
          <h2 className="text-sm font-semibold">Benchmark Suites</h2>
          {loading ? (
            <div className="text-xs text-muted-foreground">Loading suites...</div>
          ) : benchmarks.length === 0 ? (
            <div className="p-4 border rounded text-center text-xs text-muted-foreground">
              No suites created yet.
            </div>
          ) : (
            <div className="space-y-2">
              {benchmarks.map((b) => (
                <div
                  key={b.benchmark_id}
                  onClick={() => setSelectedBenchmarkId(b.benchmark_id)}
                  className={`p-3 border rounded-lg cursor-pointer text-xs transition ${
                    selectedBenchmarkId === b.benchmark_id ? "bg-accent/40 border-primary" : "hover:bg-muted/40"
                  }`}
                >
                  <div className="font-semibold text-foreground">{b.name}</div>
                  {b.description && <div className="text-[11px] text-muted-foreground mt-0.5">{b.description}</div>}
                </div>
              ))}
            </div>
          )}

          {/* New Suite Form */}
          <form onSubmit={handleCreateBenchmark} className="pt-3 border-t space-y-2">
            <h3 className="text-xs font-semibold">New Benchmark Suite</h3>
            <input
              type="text"
              required
              value={benchName}
              onChange={(e) => setBenchName(e.target.value)}
              placeholder="Suite Name (e.g. Reasoning & QA)"
              className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
            />
            <button
              type="submit"
              disabled={creatingBench}
              className="w-full py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {creatingBench ? "Creating..." : "Create Suite"}
            </button>
          </form>
        </div>

        {/* Record Benchmark Run Form */}
        <div className="lg:col-span-2 p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Record Model Evaluation Run</h2>
          <form onSubmit={handleRecordRun} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Model Identifier</label>
                <input
                  type="text"
                  required
                  value={runModel}
                  onChange={(e) => setRunModel(e.target.value)}
                  placeholder="e.g. gpt-4o, claude-3-5-sonnet"
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="run-provider-select" className="text-xs font-semibold">Provider</label>
                <select
                  id="run-provider-select"
                  value={runProvider}
                  onChange={(e) => setRunProvider(e.target.value)}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground"
                >
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">Quality Score (0-1)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  required
                  value={runScore}
                  onChange={(e) => setRunScore(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">Pass Rate (0-1)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  required
                  value={runPassRate}
                  onChange={(e) => setRunPassRate(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">Mean Latency (ms)</label>
                <input
                  type="number"
                  required
                  value={runLatency}
                  onChange={(e) => setRunLatency(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold">Cost per Run ($)</label>
                <input
                  type="number"
                  step="0.001"
                  required
                  value={runCost}
                  onChange={(e) => setRunCost(Number(e.target.value))}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={recordingRun || !selectedBenchmarkId}
                className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {recordingRun ? "Recording & Qualifying..." : "Record Run & Qualify Model"}
              </button>
            </div>
          </form>

          {/* Runs History Table */}
          <div className="pt-4 border-t space-y-2">
            <h3 className="text-xs font-semibold uppercase text-muted-foreground">Recent Benchmark Runs</h3>
            {runs.length === 0 ? (
              <div className="text-xs text-muted-foreground">No runs recorded for this benchmark.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="pb-1.5">Model</th>
                      <th className="pb-1.5 text-right">Score</th>
                      <th className="pb-1.5 text-right">Pass Rate</th>
                      <th className="pb-1.5 text-right">Latency</th>
                      <th className="pb-1.5 text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y font-mono">
                    {runs.slice(0, 5).map((r) => (
                      <tr key={r.run_id}>
                        <td className="py-2 font-semibold text-foreground">{r.model_name}</td>
                        <td className="py-2 text-right">{(r.overall_score * 100).toFixed(1)}%</td>
                        <td className="py-2 text-right">{(r.pass_rate * 100).toFixed(1)}%</td>
                        <td className="py-2 text-right">{r.mean_latency_ms.toFixed(0)} ms</td>
                        <td className="py-2 text-right text-muted-foreground">{new Date(r.started_at).toLocaleTimeString()}</td>
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
