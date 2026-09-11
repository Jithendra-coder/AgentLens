"use client";

import { useEffect, useState } from "react";

interface CostBreakdownItem {
  dimension_key: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  percentage: number;
}

interface CostSummaryData {
  project_id: string;
  total_cost_usd: number;
  total_tokens: number;
  by_model: CostBreakdownItem[];
}

interface BudgetData {
  budget_id: string;
  project_id: string;
  name: string;
  amount_usd: number;
  period: string;
  alert_threshold_pct: number;
  current_spend_usd: number;
  burn_percentage: number;
  is_breached: boolean;
  alert_triggered: boolean;
  created_at: string;
}

export default function CostIntelligenceClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [summary, setSummary] = useState<CostSummaryData | null>(null);
  const [budgets, setBudgets] = useState<BudgetData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Budget form state
  const [budgetName, setBudgetName] = useState("");
  const [budgetAmount, setBudgetAmount] = useState("100.0");
  const [budgetPeriod, setBudgetPeriod] = useState("monthly");
  const [alertThreshold, setAlertThreshold] = useState("80.0");
  const [savingBudget, setSavingBudget] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [sumRes, budRes] = await Promise.all([
        fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/cost/summary`),
        fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/budgets`),
      ]);
      if (!sumRes.ok) throw new Error(`Cost summary HTTP ${sumRes.status}`);
      if (!budRes.ok) throw new Error(`Budgets HTTP ${budRes.status}`);

      const sumData = await sumRes.json();
      const budData = await budRes.json();
      setSummary(sumData);
      setBudgets(budData.budgets || []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load cost analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
  }, [projectId]);

  const handleCreateBudget = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!budgetName.trim()) return;
    setSavingBudget(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/budgets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: budgetName.trim(),
          amount_usd: parseFloat(budgetAmount),
          period: budgetPeriod,
          alert_threshold_pct: parseFloat(alertThreshold),
        }),
      });
      if (!res.ok) throw new Error(`Create budget failed: HTTP ${res.status}`);
      setBudgetName("");
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create budget");
    } finally {
      setSavingBudget(false);
    }
  };

  const handleDeleteBudget = async (budgetId: string) => {
    if (!confirm("Are you sure you want to delete this budget rule?")) return;
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/budgets/${encodeURIComponent(budgetId)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Delete failed: HTTP ${res.status}`);
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete budget");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Cost Intelligence & Budget Governance</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Multi-dimensional token attribution, model cost breakdown, and proactive threshold breach budget governance.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="cost-intel-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="cost-intel-project-select"
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

      {/* Top Level Spend Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 border rounded-lg bg-card text-card-foreground shadow-sm">
          <div className="text-xs text-muted-foreground font-semibold uppercase">Total Project Spend</div>
          <div className="text-3xl font-bold font-mono mt-2">
            ${summary ? summary.total_cost_usd.toFixed(4) : "0.0000"}
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">Cumulative USD spend across traces</div>
        </div>

        <div className="p-5 border rounded-lg bg-card text-card-foreground shadow-sm">
          <div className="text-xs text-muted-foreground font-semibold uppercase">Total Tokens Tracked</div>
          <div className="text-3xl font-bold font-mono mt-2">
            {summary ? summary.total_tokens.toLocaleString() : "0"}
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">Prompt and completion tokens</div>
        </div>

        <div className="p-5 border rounded-lg bg-card text-card-foreground shadow-sm">
          <div className="text-xs text-muted-foreground font-semibold uppercase">Active Budgets</div>
          <div className="text-3xl font-bold font-mono mt-2">{budgets.length}</div>
          <div className="text-[11px] text-muted-foreground mt-1">
            {budgets.some((b) => b.is_breached) ? (
              <span className="text-destructive font-semibold">⚠ Breached budget active</span>
            ) : (
              <span className="text-green-600 font-semibold">✓ Spend within limits</span>
            )}
          </div>
        </div>
      </div>

      {/* Model Breakdown & Attribution */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
        <h2 className="text-base font-semibold">Model Spend Attribution</h2>
        {loading ? (
          <div className="text-xs text-muted-foreground">Loading cost breakdown...</div>
        ) : !summary || summary.by_model.length === 0 ? (
          <div className="p-6 border rounded text-center text-xs text-muted-foreground">
            No span costs recorded yet for this project.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="pb-2 font-semibold">Model / Provider</th>
                  <th className="pb-2 font-semibold text-right">Input Tokens</th>
                  <th className="pb-2 font-semibold text-right">Output Tokens</th>
                  <th className="pb-2 font-semibold text-right">Total Tokens</th>
                  <th className="pb-2 font-semibold text-right">Total Cost (USD)</th>
                  <th className="pb-2 font-semibold text-right">Share (%)</th>
                </tr>
              </thead>
              <tbody className="divide-y font-mono">
                {summary.by_model.map((item) => (
                  <tr key={item.dimension_key} className="hover:bg-muted/40">
                    <td className="py-2.5 font-semibold text-foreground">{item.dimension_key}</td>
                    <td className="py-2.5 text-right">{item.input_tokens.toLocaleString()}</td>
                    <td className="py-2.5 text-right">{item.output_tokens.toLocaleString()}</td>
                    <td className="py-2.5 text-right">{item.total_tokens.toLocaleString()}</td>
                    <td className="py-2.5 text-right font-bold">${item.cost_usd.toFixed(4)}</td>
                    <td className="py-2.5 text-right">{item.percentage.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Budget Governance & Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Budgets List */}
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Active Project Budgets</h2>
          {budgets.length === 0 ? (
            <div className="p-4 border rounded text-center text-xs text-muted-foreground">
              No budgets configured. Add a budget ceiling to guard against overspending.
            </div>
          ) : (
            <div className="space-y-3">
              {budgets.map((b) => (
                <div key={b.budget_id} className="p-4 border rounded-lg bg-accent/10 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm">{b.name}</span>
                    <button
                      onClick={() => handleDeleteBudget(b.budget_id)}
                      className="text-xs text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>Ceiling: <strong className="text-foreground">${b.amount_usd.toFixed(2)}</strong> / {b.period}</span>
                    <span>Alert at: <strong className="text-foreground">{b.alert_threshold_pct}%</strong></span>
                  </div>

                  {/* Progress Bar */}
                  <div className="space-y-1 pt-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span>Spent: ${b.current_spend_usd.toFixed(4)}</span>
                      <span className={b.is_breached ? "text-red-600 font-bold" : b.alert_triggered ? "text-amber-600 font-bold" : "text-foreground"}>
                        {b.burn_percentage.toFixed(1)}% burned
                      </span>
                    </div>
                    <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${b.is_breached ? "bg-red-600" : b.alert_triggered ? "bg-amber-500" : "bg-primary"}`}
                        style={{ width: `${Math.min(100, b.burn_percentage)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create Budget Form */}
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Create Budget Rule</h2>
          <form onSubmit={handleCreateBudget} className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold">Budget Name</label>
              <input
                type="text"
                required
                value={budgetName}
                onChange={(e) => setBudgetName(e.target.value)}
                placeholder="e.g. Production Monthly Hard Cap"
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Limit (USD)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  value={budgetAmount}
                  onChange={(e) => setBudgetAmount(e.target.value)}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Period</label>
                <select
                  value={budgetPeriod}
                  onChange={(e) => setBudgetPeriod(e.target.value)}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground"
                >
                  <option value="monthly">Monthly</option>
                  <option value="daily">Daily</option>
                </select>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold">Alert Threshold (%)</label>
              <input
                type="number"
                step="1"
                min="1"
                max="100"
                required
                value={alertThreshold}
                onChange={(e) => setAlertThreshold(e.target.value)}
                className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={savingBudget}
                className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {savingBudget ? "Saving Budget..." : "Add Budget Limit"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
