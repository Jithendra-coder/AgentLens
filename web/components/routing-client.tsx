"use client";

import { useEffect, useState } from "react";

interface RoutingRuleItem {
  rule_id: string;
  project_id: string;
  name: string;
  task_type: string;
  min_quality_score: number;
  max_cost_per_1k: number;
  max_latency_ms: number;
  fallback_model: string;
  tier_priority: string[];
  is_active: boolean;
  created_at: string;
}

interface RoutingDecisionItem {
  decision_id: string;
  project_id: string;
  trace_id?: string;
  rule_id?: string;
  selected_model: string;
  selected_provider: string;
  estimated_cost_usd: number;
  reason: string;
  decided_at: string;
}

interface RoutePromptResult {
  selected_model: string;
  selected_provider: string;
  task_type: string;
  complexity_score: number;
  estimated_cost_per_1k: number;
  reason: string;
  rule_id?: string;
}

export default function ModelRoutingConsoleClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [rules, setRules] = useState<RoutingRuleItem[]>([]);
  const [decisions, setDecisions] = useState<RoutingDecisionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State
  const [ruleName, setRuleName] = useState("");
  const [taskType, setTaskType] = useState("general");
  const [minQuality, setMinQuality] = useState(0.85);
  const [fallbackModel, setFallbackModel] = useState("gpt-4o");
  const [creating, setCreating] = useState(false);

  // Simulator State
  const [simPrompt, setSimPrompt] = useState(
    "Write a Python FastAPI service with an asynchronous background worker queue."
  );
  const [routingResult, setRoutingResult] = useState<RoutePromptResult | null>(null);
  const [simulating, setSimulating] = useState(false);

  const fetchRules = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/routing/rules`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRules(data.rules || []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load routing rules");
    } finally {
      setLoading(false);
    }
  };

  const fetchDecisions = async () => {
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/routing/decisions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDecisions(data.decisions || []);
    } catch (err: unknown) {
      console.error(err);
    }
  };

  useEffect(() => {
    void fetchRules();
    void fetchDecisions();
  }, [projectId]);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleName.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/routing/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: ruleName.trim(),
          task_type: taskType,
          min_quality_score: Number(minQuality),
          fallback_model: fallbackModel.trim(),
          tier_priority: ["gpt-4o-mini", "claude-3-5-haiku", "gpt-4o", "claude-3-5-sonnet"],
          is_active: true,
        }),
      });
      if (!res.ok) throw new Error(`Create rule failed: HTTP ${res.status}`);
      setRuleName("");
      await fetchRules();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create rule");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!confirm("Are you sure you want to delete this routing policy?")) return;
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/routing/rules/${encodeURIComponent(ruleId)}`,
        { method: "DELETE" }
      );
      if (!res.ok) throw new Error(`Delete failed: HTTP ${res.status}`);
      await fetchRules();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete rule");
    }
  };

  const handleSimulateRoute = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!simPrompt.trim()) return;
    setSimulating(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/routing/route`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: simPrompt.trim() }),
      });
      if (!res.ok) throw new Error(`Simulation failed: HTTP ${res.status}`);
      const data = await res.json();
      setRoutingResult(data);
      await fetchDecisions();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Routing simulation failed");
    } finally {
      setSimulating(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Adaptive Model Routing Console</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Dynamic, cost-aware model routing balancing prompt complexity, quality targets, and token spend.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="routing-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="routing-project-select"
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

      {/* Simulator Section */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
        <h2 className="text-base font-semibold">Live Routing Decision Simulator</h2>
        <form onSubmit={handleSimulateRoute} className="space-y-3">
          <textarea
            required
            rows={3}
            value={simPrompt}
            onChange={(e) => setSimPrompt(e.target.value)}
            placeholder="Enter test user prompt to evaluate classifier and adaptive routing..."
            className="w-full text-xs border rounded p-2.5 bg-background text-foreground font-mono"
          />
          <button
            type="submit"
            disabled={simulating}
            className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {simulating ? "Evaluating Route..." : "Evaluate Adaptive Route"}
          </button>
        </form>

        {routingResult && (
          <div className="p-4 border rounded-lg bg-accent/20 space-y-2 mt-3">
            <div className="flex items-center justify-between">
              <div className="text-xs font-bold text-foreground">
                Selected: <span className="text-primary font-mono">{routingResult.selected_model}</span> ({routingResult.selected_provider})
              </div>
              <div className="flex items-center space-x-2 text-[11px]">
                <span className="bg-secondary px-2 py-0.5 rounded uppercase font-semibold">
                  {routingResult.task_type}
                </span>
                <span className="text-muted-foreground">
                  Complexity: <strong>{(routingResult.complexity_score * 100).toFixed(0)}%</strong>
                </span>
                <span className="text-muted-foreground">
                  Est. Rate: <strong>${routingResult.estimated_cost_per_1k.toFixed(4)}/1k</strong>
                </span>
              </div>
            </div>
            <p className="text-xs text-muted-foreground italic border-t pt-2 mt-1">
              {routingResult.reason}
            </p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Rules List */}
        <div className="lg:col-span-2 p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Configured Routing Policies</h2>
          {loading ? (
            <div className="text-xs text-muted-foreground">Loading policies...</div>
          ) : rules.length === 0 ? (
            <div className="p-6 border rounded text-center text-xs text-muted-foreground">
              No custom routing rules found. Using platform default tiering.
            </div>
          ) : (
            <div className="space-y-3">
              {rules.map((r) => (
                <div key={r.rule_id} className="p-3.5 border rounded-lg text-xs space-y-1.5 hover:bg-muted/30 transition">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">{r.name}</span>
                    <button
                      onClick={() => void handleDeleteRule(r.rule_id)}
                      className="text-destructive hover:underline text-[11px]"
                    >
                      Delete
                    </button>
                  </div>
                  <div className="flex items-center space-x-3 text-[11px] text-muted-foreground">
                    <span className="uppercase bg-secondary px-1.5 py-0.5 rounded font-semibold">{r.task_type}</span>
                    <span>Min Quality: <strong>{(r.min_quality_score * 100).toFixed(0)}%</strong></span>
                    <span>Fallback: <strong className="font-mono">{r.fallback_model}</strong></span>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    Tiers: <span className="font-mono">{r.tier_priority.join(" → ")}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create Rule Form */}
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">New Policy Rule</h2>
          <form onSubmit={handleCreateRule} className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold">Policy Name</label>
              <input
                type="text"
                required
                value={ruleName}
                onChange={(e) => setRuleName(e.target.value)}
                placeholder="e.g. Code Generation Tiering"
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="task-type-select" className="text-xs font-semibold">Target Task Type</label>
              <select
                id="task-type-select"
                value={taskType}
                onChange={(e) => setTaskType(e.target.value)}
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              >
                <option value="general">general</option>
                <option value="code">code</option>
                <option value="rag">rag</option>
                <option value="extraction">extraction</option>
                <option value="reasoning">reasoning</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold">Min Quality Target ({(minQuality * 100).toFixed(0)}%)</label>
              <input
                type="range"
                min="0.5"
                max="1.0"
                step="0.05"
                value={minQuality}
                onChange={(e) => setMinQuality(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold">Fallback Model</label>
              <input
                type="text"
                required
                value={fallbackModel}
                onChange={(e) => setFallbackModel(e.target.value)}
                className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
              />
            </div>
            <div className="pt-2">
              <button
                type="submit"
                disabled={creating}
                className="w-full py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {creating ? "Saving..." : "Create Policy"}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Decision Audit Log */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
        <h2 className="text-base font-semibold">Recent Routing Decisions Audit</h2>
        {decisions.length === 0 ? (
          <div className="p-6 border rounded text-center text-xs text-muted-foreground">
            No routing decisions recorded yet. Run a prompt through the simulator above.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="pb-2 font-semibold">Model</th>
                  <th className="pb-2 font-semibold">Provider</th>
                  <th className="pb-2 font-semibold">Est. Rate</th>
                  <th className="pb-2 font-semibold">Rationale</th>
                  <th className="pb-2 font-semibold text-right">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {decisions.map((d) => (
                  <tr key={d.decision_id} className="hover:bg-muted/40">
                    <td className="py-2.5 font-semibold font-mono text-foreground">{d.selected_model}</td>
                    <td className="py-2.5 uppercase text-muted-foreground">{d.selected_provider}</td>
                    <td className="py-2.5 font-mono">${d.estimated_cost_usd.toFixed(4)}/1k</td>
                    <td className="py-2.5 text-muted-foreground max-w-md truncate">{d.reason}</td>
                    <td className="py-2.5 text-right font-mono text-muted-foreground">
                      {new Date(d.decided_at).toLocaleTimeString()}
                    </td>
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
