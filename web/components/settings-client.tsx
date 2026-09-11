"use client";

import { useEffect, useState } from "react";
import { dashboardFetch } from "../lib/client";

interface ApiKey {
  key_id: string;
  project_id: string;
  name: string;
  role: string;
  permissions: string[];
  created_at: string;
  is_active: boolean;
  revoked_at: string | null;
}

export default function SettingsClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Dynamic Active Key State
  const [activeKeyToken, setActiveKeyToken] = useState<string>("dev-key-12345");
  const [activeKeyName, setActiveKeyName] = useState<string>("Default Dev Key");
  const [storedTokens, setStoredTokens] = useState<Record<string, string>>({});

  // New Key Form State
  const [keyName, setKeyName] = useState("");
  const [keyRole, setKeyRole] = useState("project_editor");
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<{ token: string; name: string; id: string } | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  // Initialize from LocalStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        const savedToken = localStorage.getItem("agentlens_active_key");
        const savedName = localStorage.getItem("agentlens_active_key_name");
        const savedMap = localStorage.getItem("agentlens_stored_tokens");
        if (savedToken) setActiveKeyToken(savedToken);
        if (savedName) setActiveKeyName(savedName);
        if (savedMap) setStoredTokens(JSON.parse(savedMap));
      } catch {
        // Fallback gracefully
      }
    }
  }, []);

  const fetchKeys = async () => {
    try {
      const data = await dashboardFetch<{ api_keys: ApiKey[] }>(
        `projects/${encodeURIComponent(projectId)}/api-keys`
      );
      setKeys(data.api_keys || []);
    } catch {
      // Retain clean fallback
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchKeys().finally(() => setLoading(false));
  }, [projectId]);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopyFeedback(label);
    setTimeout(() => setCopyFeedback(null), 2500);
  };

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = keyName.trim();
    if (!trimmedName) return;
    try {
      setError(null);
      const data = await dashboardFetch<{ api_key: string; key_id: string }>(
        `projects/${encodeURIComponent(projectId)}/api-keys`,
        {
          method: "POST",
          body: { name: trimmedName, role: keyRole },
        }
      );

      const generatedToken = data.api_key;
      const keyId = data.key_id;

      // Update stored tokens and set as primary active key immediately
      const updatedMap = { ...storedTokens, [keyId]: generatedToken };
      setStoredTokens(updatedMap);
      setActiveKeyToken(generatedToken);
      setActiveKeyName(trimmedName);

      if (typeof window !== "undefined") {
        localStorage.setItem("agentlens_active_key", generatedToken);
        localStorage.setItem("agentlens_active_key_name", trimmedName);
        localStorage.setItem("agentlens_stored_tokens", JSON.stringify(updatedMap));
      }

      setNewlyCreatedKey({ token: generatedToken, name: trimmedName, id: keyId });
      setKeyName("");
      void fetchKeys();
    } catch (err: any) {
      setError(err?.message || "Failed to create API key");
    }
  };

  const handleSetActiveKey = (keyId: string, name: string) => {
    const token = storedTokens[keyId];
    if (token) {
      setActiveKeyToken(token);
      setActiveKeyName(name);
      if (typeof window !== "undefined") {
        localStorage.setItem("agentlens_active_key", token);
        localStorage.setItem("agentlens_active_key_name", name);
      }
      setCopyFeedback(`Active key switched to "${name}"`);
      setTimeout(() => setCopyFeedback(null), 2500);
    } else {
      setActiveKeyName(name);
      if (typeof window !== "undefined") {
        localStorage.setItem("agentlens_active_key_name", name);
      }
      setCopyFeedback(`Selected key "${name}"`);
      setTimeout(() => setCopyFeedback(null), 2500);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!confirm("Are you sure you want to revoke this API key?")) return;
    try {
      await dashboardFetch(
        `projects/${encodeURIComponent(projectId)}/api-keys/${encodeURIComponent(keyId)}`,
        { method: "DELETE" }
      );
      // Clean from stored tokens if revoked
      const updatedMap = { ...storedTokens };
      delete updatedMap[keyId];
      setStoredTokens(updatedMap);
      if (typeof window !== "undefined") {
        localStorage.setItem("agentlens_stored_tokens", JSON.stringify(updatedMap));
      }
      void fetchKeys();
    } catch (err: any) {
      setError(err?.message || "Failed to revoke API key");
    }
  };

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Enterprise Control Plane</p>
          <h1 style={{ color: "#0F172A" }}>Project & API Key Settings</h1>
          <p className="lede" style={{ color: "#475569" }}>
            Zero-credential observability. Authenticate your RAG application, agent pipelines, or CI/CD exporters using project-scoped Bearer API keys.
          </p>
        </div>
      </div>

      {error && (
        <div style={{ padding: "0.75rem 1rem", background: "#FEF2F2", border: "1px solid #FECACA", color: "#B91C1C", borderRadius: "8px", fontSize: "0.85rem" }}>
          {error}
        </div>
      )}

      {copyFeedback && (
        <div style={{ padding: "0.75rem 1rem", background: "#F0FDF4", border: "1px solid #BBF7D0", color: "#166534", borderRadius: "8px", fontSize: "0.85rem", fontWeight: 600 }}>
          ✓ {copyFeedback}
        </div>
      )}

      {/* 1. Active Primary Project API Key Card */}
      <section className="card section" style={{ border: "1px solid #E2E8F0", background: "#FFFFFF", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
              <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", fontWeight: 700 }}>
                Active Project Credentials
              </span>
              <span style={{ fontSize: "0.72rem", background: "#F0FDF4", border: "1px solid #BBF7D0", padding: "0.1rem 0.5rem", borderRadius: "999px", color: "#166534", fontWeight: 600 }}>
                🟢 {activeKeyName}
              </span>
            </div>
            <h2 style={{ fontSize: "1.25rem", margin: "0 0 0.5rem 0", color: "#0F172A" }}>Primary Ingestion Key</h2>
            <p className="subtle" style={{ margin: 0, maxWidth: "650px", color: "#475569" }}>
              Use this key in your Python RAG application or LangChain pipeline to authenticate incoming telemetry traces.
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <span style={{ fontSize: "0.75rem", background: "#F8FAFC", border: "1px solid #E2E8F0", padding: "0.35rem 0.75rem", borderRadius: "6px", color: "#0F172A", fontFamily: "monospace", fontWeight: 600 }}>
              Project: {projectId}
            </span>
          </div>
        </div>

        <div style={{ marginTop: "1rem", padding: "0.85rem 1rem", background: "#F8FAFC", border: "1px solid #CBD5E1", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0, flex: 1 }}>
            <span style={{ color: "#64748B", fontSize: "0.8rem", fontWeight: 700, textTransform: "uppercase" }}>ACTIVE KEY:</span>
            <code style={{ color: "#0F172A", fontSize: "0.95rem", fontWeight: 700, letterSpacing: "0.03em", wordBreak: "break-all" }}>
              {activeKeyToken}
            </code>
          </div>
          <button
            type="button"
            className="button"
            style={{ fontSize: "0.78rem", minHeight: "2rem", padding: "0.25rem 1rem", background: "#0F172A", color: "#FFFFFF" }}
            onClick={() => copyToClipboard(activeKeyToken, `Copied Active Key (${activeKeyToken.slice(0, 12)}...)`)}
          >
            📋 Copy Active Key
          </button>
        </div>

        <div style={{ marginTop: "1.25rem" }}>
          <div style={{ fontSize: "0.72rem", color: "#64748B", fontWeight: 700, textTransform: "uppercase", marginBottom: "0.4rem" }}>
            Live Integration (Uses Your Active Key):
          </div>
          <pre style={{ background: "#F8FAFC", border: "1px solid #CBD5E1", padding: "0.85rem", borderRadius: "8px", fontSize: "0.82rem", color: "#0F172A", overflowX: "auto", margin: 0, lineHeight: "1.5" }}>
{`from agentlens.client import AgentLensClient

client = AgentLensClient(
    api_key="${activeKeyToken}", 
    base_url="http://127.0.0.1:8000"
)
client.log_rag(query="...", context=[...], answer="...", latency_ms=150, tokens=85)`}
          </pre>
        </div>
      </section>

      {/* 2. Scoped API Keys Management */}
      <section className="card section" style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
        <div style={{ marginBottom: "1rem" }}>
          <h2 style={{ color: "#0F172A", margin: "0 0 0.35rem 0" }}>Generate Additional Scoped Keys</h2>
          <p className="subtle" style={{ color: "#475569", margin: 0 }}>
            Create unique, cryptographically secure bearer tokens for external background workers, staging pipelines, or CI test runners.
          </p>
        </div>

        <form onSubmit={handleCreateKey} className="grid two" style={{ gridTemplateColumns: "1fr 1fr auto", gap: "1rem", alignItems: "end", marginBottom: "1.5rem" }}>
          <div>
            <label className="field" style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.75rem", fontWeight: 700, color: "#475569", textTransform: "uppercase" }}>
              Key Name / Purpose
              <input
                type="text"
                placeholder="e.g. Production RAG Service"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                className="control"
                style={{ background: "#FFFFFF", border: "1px solid #CBD5E1", color: "#0F172A" }}
                required
              />
            </label>
          </div>

          <div>
            <label className="field" style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.75rem", fontWeight: 700, color: "#475569", textTransform: "uppercase" }}>
              Permission Role
              <select
                value={keyRole}
                onChange={(e) => setKeyRole(e.target.value)}
                className="control"
                style={{ background: "#FFFFFF", border: "1px solid #CBD5E1", color: "#0F172A" }}
              >
                <option value="project_admin">Project Admin (Full Access)</option>
                <option value="project_editor">Project Editor (Read/Write)</option>
                <option value="service_ingestion">Service Ingestion (Traces Only)</option>
              </select>
            </label>
          </div>

          <div>
            <button type="submit" className="button" style={{ minHeight: "2.35rem", padding: "0 1.25rem", background: "#0F172A", color: "#FFFFFF", fontWeight: 600 }}>
              ⚡ Generate Key
            </button>
          </div>
        </form>

        {/* Newly Created Key Alert Banner */}
        {newlyCreatedKey && (
          <div style={{ marginBottom: "1.5rem", padding: "1rem", background: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
              <div>
                <span style={{ color: "#166534", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "0.25rem" }}>
                  ✓ New API Key Generated for &ldquo;{newlyCreatedKey.name}&rdquo; (Set as Active Primary):
                </span>
                <code style={{ color: "#0F172A", fontSize: "0.95rem", fontWeight: 700, fontFamily: "monospace", letterSpacing: "0.04em", background: "#DCFCE7", padding: "0.2rem 0.5rem", borderRadius: "4px", display: "inline-block" }}>
                  {newlyCreatedKey.token}
                </code>
              </div>
              <button
                type="button"
                className="button"
                style={{ fontSize: "0.75rem", minHeight: "1.9rem", padding: "0.25rem 0.85rem", background: "#166534", color: "#FFFFFF" }}
                onClick={() => copyToClipboard(newlyCreatedKey.token, `Copied New Key for "${newlyCreatedKey.name}"`)}
              >
                📋 Copy Key
              </button>
            </div>
            <p style={{ margin: "0.5rem 0 0 0", fontSize: "0.75rem", color: "#15803D" }}>
              This key has been set as your active primary key and saved to your browser session.
            </p>
          </div>
        )}

        {/* Keys Table */}
        <div className="table-wrap" style={{ border: "1px solid #E2E8F0", borderRadius: "8px", overflow: "hidden" }}>
          <table style={{ width: "100%", textAlign: "left", background: "#FFFFFF" }}>
            <thead style={{ background: "#F8FAFC", borderBottom: "1px solid #E2E8F0" }}>
              <tr>
                <th style={{ padding: "0.6rem 0.85rem", color: "#475569", fontSize: "0.75rem" }}>Key Name</th>
                <th style={{ padding: "0.6rem 0.85rem", color: "#475569", fontSize: "0.75rem" }}>Key ID</th>
                <th style={{ padding: "0.6rem 0.85rem", color: "#475569", fontSize: "0.75rem" }}>Role</th>
                <th style={{ padding: "0.6rem 0.85rem", color: "#475569", fontSize: "0.75rem" }}>Token Status</th>
                <th style={{ padding: "0.6rem 0.85rem", color: "#475569", fontSize: "0.75rem", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody style={{ fontSize: "0.82rem" }}>
              {/* Always show Default Dev Key if present or as reference */}
              <tr style={{ borderBottom: "1px solid #F1F5F9", background: activeKeyToken === "dev-key-12345" ? "#F8FAFC" : "#FFFFFF" }}>
                <td style={{ padding: "0.6rem 0.85rem", fontWeight: 600, color: "#0F172A" }}>
                  Default Dev Key {activeKeyToken === "dev-key-12345" && <span style={{ fontSize: "0.68rem", color: "#166534", background: "#DCFCE7", padding: "0.1rem 0.35rem", borderRadius: "4px", marginLeft: "0.4rem" }}>PRIMARY</span>}
                </td>
                <td style={{ padding: "0.6rem 0.85rem", fontFamily: "monospace", fontSize: "0.75rem", color: "#64748B" }}>key_default_dev</td>
                <td style={{ padding: "0.6rem 0.85rem", textTransform: "capitalize", color: "#334155" }}>Project Admin</td>
                <td style={{ padding: "0.6rem 0.85rem" }}>
                  <span style={{ fontSize: "0.72rem", background: "#DCFCE7", color: "#166534", padding: "0.15rem 0.5rem", borderRadius: "4px", fontWeight: 600 }}>
                    Active
                  </span>
                </td>
                <td style={{ padding: "0.6rem 0.85rem", textAlign: "right" }}>
                  <div style={{ display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                    {activeKeyToken !== "dev-key-12345" && (
                      <button
                        onClick={() => {
                          setActiveKeyToken("dev-key-12345");
                          setActiveKeyName("Default Dev Key");
                          if (typeof window !== "undefined") {
                            localStorage.setItem("agentlens_active_key", "dev-key-12345");
                            localStorage.setItem("agentlens_active_key_name", "Default Dev Key");
                          }
                          setCopyFeedback("Set Default Dev Key as active");
                          setTimeout(() => setCopyFeedback(null), 2500);
                        }}
                        style={{ fontSize: "0.72rem", padding: "0.2rem 0.5rem", background: "#F1F5F9", border: "1px solid #CBD5E1", borderRadius: "4px", cursor: "pointer", color: "#0F172A" }}
                      >
                        Set Active
                      </button>
                    )}
                    <button
                      onClick={() => copyToClipboard("dev-key-12345", "Copied dev-key-12345")}
                      style={{ fontSize: "0.72rem", padding: "0.2rem 0.5rem", background: "#F1F5F9", border: "1px solid #CBD5E1", borderRadius: "4px", cursor: "pointer", color: "#0F172A" }}
                    >
                      Copy
                    </button>
                  </div>
                </td>
              </tr>

              {keys.map((k) => {
                const isCurrentActive = activeKeyName === k.name || (storedTokens[k.key_id] && storedTokens[k.key_id] === activeKeyToken);
                const hasStoredToken = Boolean(storedTokens[k.key_id]);
                return (
                  <tr key={k.key_id} style={{ borderBottom: "1px solid #F1F5F9", background: isCurrentActive ? "#F8FAFC" : "#FFFFFF" }}>
                    <td style={{ padding: "0.6rem 0.85rem", fontWeight: 600, color: "#0F172A" }}>
                      {k.name}
                      {isCurrentActive && (
                        <span style={{ fontSize: "0.68rem", color: "#166534", background: "#DCFCE7", padding: "0.1rem 0.35rem", borderRadius: "4px", marginLeft: "0.4rem" }}>
                          PRIMARY
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "0.6rem 0.85rem", fontFamily: "monospace", fontSize: "0.75rem", color: "#64748B" }}>{k.key_id}</td>
                    <td style={{ padding: "0.6rem 0.85rem", textTransform: "capitalize", color: "#334155" }}>{k.role.replace("_", " ")}</td>
                    <td style={{ padding: "0.6rem 0.85rem" }}>
                      <span style={{ fontSize: "0.72rem", background: k.is_active ? "#DCFCE7" : "#FEE2E2", color: k.is_active ? "#166534" : "#991B1B", padding: "0.15rem 0.5rem", borderRadius: "4px", fontWeight: 600 }}>
                        {k.is_active ? "Active" : "Revoked"}
                      </span>
                    </td>
                    <td style={{ padding: "0.6rem 0.85rem", textAlign: "right" }}>
                      <div style={{ display: "flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                        {k.is_active && !isCurrentActive && (
                          <button
                            onClick={() => handleSetActiveKey(k.key_id, k.name)}
                            style={{ fontSize: "0.72rem", padding: "0.2rem 0.5rem", background: "#F1F5F9", border: "1px solid #CBD5E1", borderRadius: "4px", cursor: "pointer", color: "#0F172A" }}
                          >
                            Set Active
                          </button>
                        )}
                        {hasStoredToken && (
                          <button
                            onClick={() => copyToClipboard(storedTokens[k.key_id], `Copied key for "${k.name}"`)}
                            style={{ fontSize: "0.72rem", padding: "0.2rem 0.5rem", background: "#F1F5F9", border: "1px solid #CBD5E1", borderRadius: "4px", cursor: "pointer", color: "#0F172A" }}
                          >
                            Copy
                          </button>
                        )}
                        {k.is_active && (
                          <button
                            onClick={() => handleRevokeKey(k.key_id)}
                            style={{ fontSize: "0.72rem", padding: "0.2rem 0.5rem", background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "4px", cursor: "pointer", color: "#B91C1C" }}
                          >
                            Revoke
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
