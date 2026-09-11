"use client";

import { useEffect, useState } from "react";

interface CustomEvaluatorPluginData {
  plugin_id: string;
  project_id: string;
  name: string;
  version: string;
  evaluator_type: string;
  description?: string;
  code_body: string;
  schema_parameters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface TestOutcome {
  score: number;
  passed: boolean;
  findings: string[];
  details: Record<string, unknown>;
}

const DEFAULT_CODE_TEMPLATE = `def evaluate(context, parameters):
    """Custom Evaluator checking tool invocation hygiene and latency."""
    findings = []
    tool_spans = [s for s in context.spans if s.span_type == "tool"]
    
    if not tool_spans:
        findings.append("No tools executed in this trace.")
        return CustomEvaluationOutput(score=1.0, passed=True, findings=findings)
        
    error_spans = [s for s in tool_spans if s.status == "error"]
    if error_spans:
        findings.append(f"Detected {len(error_spans)} failed tool execution(s).")
        return CustomEvaluationOutput(score=0.2, passed=False, findings=findings)
        
    return CustomEvaluationOutput(score=1.0, passed=True, findings=["All tool spans completed successfully."])
`;

export default function CustomEvaluatorStudioClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [plugins, setPlugins] = useState<CustomEvaluatorPluginData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [evaluatorType, setEvaluatorType] = useState("deterministic");
  const [description, setDescription] = useState("");
  const [codeBody, setCodeBody] = useState(DEFAULT_CODE_TEMPLATE);
  const [saving, setSaving] = useState(false);

  // Test states
  const [testPluginId, setTestPluginId] = useState<string | null>(null);
  const [testTraceId, setTestTraceId] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestOutcome | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const fetchPlugins = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/custom-evaluators`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setPlugins(data.custom_evaluators || []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load custom evaluators");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchPlugins();
  }, [projectId]);

  const handleRegisterPlugin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !codeBody.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/custom-evaluators`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          version: version.trim(),
          evaluator_type: evaluatorType,
          description: description.trim() || undefined,
          code_body: codeBody,
          schema_parameters: {},
        }),
      });
      if (!res.ok) throw new Error(`Registration failed: HTTP ${res.status}`);
      setName("");
      setDescription("");
      await fetchPlugins();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to register plugin");
    } finally {
      setSaving(false);
    }
  };

  const handleDeletePlugin = async (pluginId: string) => {
    if (!confirm("Are you sure you want to delete this custom evaluator plugin?")) return;
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/custom-evaluators/${encodeURIComponent(pluginId)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Delete failed: HTTP ${res.status}`);
      if (testPluginId === pluginId) {
        setTestPluginId(null);
        setTestResult(null);
      }
      await fetchPlugins();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete plugin");
    }
  };

  const handleTestPlugin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testPluginId || !testTraceId.trim()) return;
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/custom-evaluators/${encodeURIComponent(testPluginId)}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trace_id: testTraceId.trim(),
          parameters: {},
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.message || `Test failed: HTTP ${res.status}`);
      }
      const data = await res.json();
      setTestResult(data);
    } catch (err: unknown) {
      setTestError(err instanceof Error ? err.message : "Test execution failed");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Custom Evaluator Studio</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Author, test, and register custom Python evaluator plugins with sandboxed isolation and composite suite integration.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="custom-eval-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="custom-eval-project-select"
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

      {/* Existing Plugins List */}
      <div className="space-y-4">
        <h2 className="text-base font-semibold">Registered Custom Evaluators</h2>
        {loading ? (
          <div className="text-xs text-muted-foreground">Loading custom plugins...</div>
        ) : plugins.length === 0 ? (
          <div className="p-6 border rounded-lg text-center text-xs text-muted-foreground">
            No custom evaluator plugins registered yet for this project.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {plugins.map((plugin) => (
              <div key={plugin.plugin_id} className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold text-sm font-mono">{plugin.name}</h3>
                    <div className="flex items-center space-x-2 text-[11px] text-muted-foreground mt-0.5">
                      <span className="bg-secondary px-1.5 py-0.5 rounded">v{plugin.version}</span>
                      <span className="capitalize">{plugin.evaluator_type}</span>
                    </div>
                  </div>
                  <div className="space-x-2">
                    <button
                      onClick={() => {
                        setTestPluginId(plugin.plugin_id);
                        setTestResult(null);
                        setTestError(null);
                      }}
                      className="text-xs text-primary hover:underline"
                    >
                      Test
                    </button>
                    <button
                      onClick={() => handleDeletePlugin(plugin.plugin_id)}
                      className="text-xs text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {plugin.description && <p className="text-xs text-muted-foreground">{plugin.description}</p>}

                <div className="text-[11px] font-mono bg-muted/40 p-2 rounded max-h-24 overflow-y-auto">
                  <pre className="whitespace-pre-wrap">{plugin.code_body}</pre>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Test Runner Panel */}
      {testPluginId && (
        <div className="p-6 border rounded-lg bg-accent/20 space-y-4 max-w-2xl">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Test Custom Evaluator</h2>
            <button onClick={() => setTestPluginId(null)} className="text-xs text-muted-foreground hover:underline">
              Close Test Panel
            </button>
          </div>

          <form onSubmit={handleTestPlugin} className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold">Target Trace ID (UUID)</label>
              <input
                type="text"
                required
                value={testTraceId}
                onChange={(e) => setTestTraceId(e.target.value)}
                placeholder="e.g. 7c9e6679-7425-40de-944b-e07fc1f90ae7"
                className="w-full text-xs font-mono border rounded p-2 bg-background text-foreground"
              />
            </div>
            <button
              type="submit"
              disabled={testing}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {testing ? "Running Sandbox..." : "Run Test Evaluation"}
            </button>
          </form>

          {testError && <div className="p-3 text-xs text-destructive bg-destructive/10 rounded">{testError}</div>}

          {testResult && (
            <div className="p-3 border rounded bg-card space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold">Test Result:</span>
                <span className={`font-semibold ${testResult.passed ? "text-green-600" : "text-red-600"}`}>
                  {testResult.passed ? "PASSED" : "FAILED"} (Score: {(testResult.score * 100).toFixed(1)}%)
                </span>
              </div>
              {testResult.findings.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold text-muted-foreground uppercase">Findings</div>
                  <ul className="list-disc list-inside space-y-0.5">
                    {testResult.findings.map((f, i) => (
                      <li key={i} className="text-xs text-muted-foreground">{f}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Author New Evaluator Form */}
      <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4 max-w-3xl">
        <h2 className="text-base font-semibold">Register Custom Evaluator Plugin</h2>
        <form onSubmit={handleRegisterPlugin} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold">Plugin Name</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. custom.tool_hygiene"
                className="w-full text-xs font-mono border rounded p-2 bg-background text-foreground"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold">Version</label>
              <input
                type="text"
                required
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="1.0.0"
                className="w-full text-xs font-mono border rounded p-2 bg-background text-foreground"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold">Type</label>
              <select
                value={evaluatorType}
                onChange={(e) => setEvaluatorType(e.target.value)}
                className="w-full text-xs border rounded p-2 bg-background text-foreground"
              >
                <option value="deterministic">Deterministic</option>
                <option value="semantic">Semantic</option>
              </select>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g., Validates that tools are invoked without consecutive failure states"
              className="w-full text-xs border rounded p-2 bg-background text-foreground"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold">Python Evaluator Code (`evaluate(context, parameters)`)</label>
            <textarea
              required
              rows={12}
              value={codeBody}
              onChange={(e) => setCodeBody(e.target.value)}
              className="w-full text-xs font-mono border rounded p-3 bg-background text-foreground leading-relaxed"
            />
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving ? "Registering Plugin..." : "Register Evaluator Plugin"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
