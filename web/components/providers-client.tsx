"use client";

import { useState } from "react";

interface TestOutcome {
  status: string;
  latency_ms: number;
  provider: string;
  model: string;
  sample_output: string;
}

interface GenerateOutcome {
  content: string;
  finish_reason: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  latency_ms: number;
  provider: string;
  model: string;
}

export default function ModelProvidersClient() {
  const [projectId, setProjectId] = useState("proj-default");

  // Connectivity Test State
  const [providerType, setProviderType] = useState("openai");
  const [name, setName] = useState("Primary OpenAI");
  const [modelName, setModelName] = useState("gpt-4o");
  const [baseUrl, setBaseUrl] = useState("");
  const [secretName, setSecretName] = useState("openai-api-key");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestOutcome | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  // Playground Generation State
  const [prompt, setPrompt] = useState("Explain deterministic vs semantic evaluation in two sentences.");
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState<GenerateOutcome | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  const handleTestConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/providers/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: {
            name: name.trim(),
            provider_type: providerType,
            model_name: modelName.trim(),
            base_url: baseUrl.trim() || undefined,
            secret_name: secretName.trim(),
            priority: 1,
            enabled: true,
          },
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.message || `Test failed: HTTP ${res.status}`);
      }
      const data = await res.json();
      setTestResult(data);
    } catch (err: unknown) {
      setTestError(err instanceof Error ? err.message : "Provider test failed");
    } finally {
      setTesting(false);
    }
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    setGenerating(true);
    setGenResult(null);
    setGenError(null);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/providers/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{ role: "user", content: prompt.trim() }],
          profiles: [
            {
              name: name.trim(),
              provider_type: providerType,
              model_name: modelName.trim(),
              base_url: baseUrl.trim() || undefined,
              secret_name: secretName.trim(),
              priority: 1,
              enabled: true,
            },
          ],
          temperature: 0.2,
          max_tokens: 512,
          timeout_seconds: 20.0,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.message || `Generation failed: HTTP ${res.status}`);
      }
      const data = await res.json();
      setGenResult(data);
    } catch (err: unknown) {
      setGenError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Model Providers & Fallback Routing</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configure model provider adapters (OpenAI, Anthropic, Gemini, Custom HTTP), test latency, and manage resilient fallback chains.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="model-providers-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="model-providers-project-select"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="text-xs border rounded px-2.5 py-1 bg-background text-foreground"
        >
          <option value="proj-default">proj-default</option>
          <option value="proj-prod">proj-prod</option>
          <option value="proj-staging">proj-staging</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Provider Profile Configuration & Test */}
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Provider Diagnostics & Ping</h2>
          <form onSubmit={handleTestConnection} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Profile Name</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Provider Type</label>
                <select
                  value={providerType}
                  onChange={(e) => {
                    setProviderType(e.target.value);
                    if (e.target.value === "openai") {
                      setModelName("gpt-4o");
                      setSecretName("openai-api-key");
                    } else if (e.target.value === "anthropic") {
                      setModelName("claude-3-5-sonnet-20241022");
                      setSecretName("anthropic-api-key");
                    } else if (e.target.value === "gemini") {
                      setModelName("gemini-1.5-pro");
                      setSecretName("gemini-api-key");
                    }
                  }}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground"
                >
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic Claude</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="custom_http">Custom HTTP (vLLM / Ollama)</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Model Identifier</label>
                <input
                  type="text"
                  required
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Vault Secret Name</label>
                <input
                  type="text"
                  required
                  value={secretName}
                  onChange={(e) => setSecretName(e.target.value)}
                  placeholder="e.g. openai-api-key"
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
            </div>

            {providerType === "custom_http" && (
              <div className="space-y-1">
                <label className="text-xs font-semibold">Base URL</label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="http://localhost:8000/v1"
                  className="w-full text-xs border rounded p-2 bg-background text-foreground font-mono"
                />
              </div>
            )}

            <div className="pt-2">
              <button
                type="submit"
                disabled={testing}
                className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {testing ? "Testing Connectivity..." : "Test Provider Connection"}
              </button>
            </div>
          </form>

          {testError && <div className="p-3 text-xs text-destructive bg-destructive/10 rounded">{testError}</div>}

          {testResult && (
            <div className="p-3 border rounded bg-accent/20 space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-green-600">✓ Connection Successful</span>
                <span className="font-mono">{testResult.latency_ms} ms</span>
              </div>
              <div className="text-muted-foreground text-[11px]">
                Provider: <span className="font-semibold text-foreground">{testResult.provider}</span> | Model: <span className="font-mono text-foreground">{testResult.model}</span>
              </div>
              <div className="p-2 bg-background rounded text-[11px] font-mono mt-1">
                Response: &quot;{testResult.sample_output}&quot;
              </div>
            </div>
          )}
        </div>

        {/* Resilient Generation Gateway */}
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-base font-semibold">Generation Playground</h2>
          <form onSubmit={handleGenerate} className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold">Prompt</label>
              <textarea
                rows={4}
                required
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full text-xs border rounded p-2 bg-background text-foreground leading-relaxed"
              />
            </div>

            <button
              type="submit"
              disabled={generating}
              className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {generating ? "Routing Request..." : "Run Unified Generation"}
            </button>
          </form>

          {genError && <div className="p-3 text-xs text-destructive bg-destructive/10 rounded">{genError}</div>}

          {genResult && (
            <div className="p-4 border rounded bg-accent/20 space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold">Generation Output</span>
                <div className="space-x-3 text-[11px] text-muted-foreground">
                  <span>Tokens: {genResult.usage.total_tokens}</span>
                  <span>Latency: {genResult.latency_ms}ms</span>
                </div>
              </div>
              <div className="p-3 bg-background rounded text-xs leading-relaxed whitespace-pre-wrap">
                {genResult.content}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
