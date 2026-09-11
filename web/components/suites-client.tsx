"use client";

import { useEffect, useState } from "react";

interface EvaluatorRef {
  evaluator_name: string;
  evaluator_version: string;
  evaluator_type: string;
  weight: number;
  threshold: number;
  parameters?: Record<string, unknown>;
}

interface EvaluationSuiteData {
  suite_id: string;
  project_id: string;
  name: string;
  description?: string;
  passing_threshold: number;
  evaluators: EvaluatorRef[];
  created_at: string;
  updated_at: string;
}

export default function EvaluationSuitesClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [suites, setSuites] = useState<EvaluationSuiteData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [passingThreshold, setPassingThreshold] = useState(0.8);
  const [evaluators, setEvaluators] = useState<EvaluatorRef[]>([
    {
      evaluator_name: "agentlens.latency",
      evaluator_version: "1.0.0",
      evaluator_type: "deterministic",
      weight: 0.3,
      threshold: 0.8,
    },
    {
      evaluator_name: "agentlens.tool_correctness",
      evaluator_version: "1.0.0",
      evaluator_type: "deterministic",
      weight: 0.4,
      threshold: 0.85,
    },
    {
      evaluator_name: "agentlens.faithfulness",
      evaluator_version: "1.0.0",
      evaluator_type: "semantic",
      weight: 0.3,
      threshold: 0.75,
    },
  ]);
  const [saving, setSaving] = useState(false);

  const fetchSuites = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/evaluation-suites`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSuites(data.suites || []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load evaluation suites");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchSuites();
  }, [projectId]);

  const handleCreateSuite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/evaluation-suites`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || undefined,
          passing_threshold: Number(passingThreshold),
          evaluators,
        }),
      });
      if (!res.ok) throw new Error(`Create failed: HTTP ${res.status}`);
      setName("");
      setDescription("");
      await fetchSuites();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create suite");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSuite = async (suiteId: string) => {
    if (!confirm("Are you sure you want to delete this evaluation suite?")) return;
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/evaluation-suites/${encodeURIComponent(suiteId)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Delete failed: HTTP ${res.status}`);
      await fetchSuites();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete suite");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Composite Evaluation Suites</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Define multi-metric weighted evaluation suites, deterministic hard gates, and composite quality thresholds.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="eval-suites-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="eval-suites-project-select"
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

      {/* Existing Suites List */}
      <div className="space-y-4">
        <h2 className="text-base font-semibold">Configured Evaluation Suites</h2>
        {loading ? (
          <div className="text-xs text-muted-foreground">Loading suites...</div>
        ) : suites.length === 0 ? (
          <div className="p-6 border rounded-lg text-center text-xs text-muted-foreground">
            No evaluation suites created yet for this project. Use the form below to create one.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {suites.map((suite) => (
              <div key={suite.suite_id} className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold text-sm">{suite.name}</h3>
                    {suite.description && <p className="text-xs text-muted-foreground mt-0.5">{suite.description}</p>}
                  </div>
                  <button
                    onClick={() => handleDeleteSuite(suite.suite_id)}
                    className="text-xs text-destructive hover:underline"
                  >
                    Delete
                  </button>
                </div>

                <div className="text-xs space-y-1">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Passing Threshold:</span>
                    <span className="font-semibold text-foreground">{(suite.passing_threshold * 100).toFixed(0)}%</span>
                  </div>
                </div>

                <div className="pt-2 border-t space-y-1.5">
                  <div className="text-[11px] font-semibold text-muted-foreground uppercase">Constituent Metrics ({suite.evaluators.length})</div>
                  <div className="space-y-1 text-xs">
                    {suite.evaluators.map((ev, idx) => (
                      <div key={idx} className="flex items-center justify-between py-0.5">
                        <span className="font-mono text-[11px]">{ev.evaluator_name}</span>
                        <div className="space-x-2 text-[11px] text-muted-foreground">
                          <span className="capitalize">{ev.evaluator_type}</span>
                          <span>Weight: {(ev.weight * 100).toFixed(0)}%</span>
                          <span>Threshold: {(ev.threshold * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create New Suite Form */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4 max-w-2xl">
        <h2 className="text-base font-semibold">Create Evaluation Suite</h2>
        <form onSubmit={handleCreateSuite} className="space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold">Suite Name</label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Production Agent Quality Suite"
              className="w-full text-xs border rounded p-2 bg-background text-foreground"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g., Combines latency limits with tool accuracy and semantic faithfulness"
              className="w-full text-xs border rounded p-2 bg-background text-foreground"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold">Passing Threshold (0.0 to 1.0)</label>
            <input
              type="number"
              step="0.05"
              min="0.0"
              max="1.0"
              required
              value={passingThreshold}
              onChange={(e) => setPassingThreshold(parseFloat(e.target.value))}
              className="w-full text-xs border rounded p-2 bg-background text-foreground"
            />
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? "Creating Suite..." : "Save Evaluation Suite"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
