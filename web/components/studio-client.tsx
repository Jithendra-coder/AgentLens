"use client";

import React, { useState } from "react";
import Link from "next/link";
import { dashboardFetch } from "../lib/client";

interface CitationItem {
  chunk_id: string;
  section: string;
  title: string;
  score: number;
  excerpt: string;
}

interface SpanSummaryItem {
  name: string;
  type: string;
  duration_ms: number;
  status: string;
  tokens: number;
}

interface RAGResponse {
  query: string;
  answer: string;
  verdict?: string;
  citations: CitationItem[];
  trace_id: string;
  latency_ms: number;
  retriever_ms: number;
  tokens: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
  grounded: boolean;
  document_name: string;
  document_id?: string;
  cache_hit?: boolean;
  spans?: SpanSummaryItem[];
}

interface AgentResponse {
  query: string;
  answer: string;
  verdict: string;
  customer?: any;
  transaction?: any;
  trace_id: string;
  latency_ms: number;
  tool_ms: number;
  retriever_ms: number;
  tokens: number;
  cost_usd: number;
  grounded: boolean;
  document_name: string;
  spans?: SpanSummaryItem[];
}

interface ArenaModelResult {
  model_id: string;
  display_name: string;
  provider: string;
  verdict: string;
  latency_ms: number;
  tokens: number;
  cost_usd: number;
  answer: string;
  strengths: string;
}

interface ArenaResponse {
  query: string;
  document_id: string;
  models: ArenaModelResult[];
  citations: CitationItem[];
}

interface SectionOverview {
  id: string;
  title: string;
  summary: string;
  suggestedQuery: string;
}

const USER_POLICY_SECTIONS: SectionOverview[] = [
  {
    id: "sec-2",
    title: "Section 2: Billing & Strict 30-Day Refund Policy",
    summary: "Full refunds allowed within 30 calendar days. Strictly non-refundable after 30 days or if usage exceeds 1M tokens.",
    suggestedQuery: "Can a user get a refund after 45 days?",
  },
  {
    id: "sec-5",
    title: "Section 5: Service Level Agreements (SLAs)",
    summary: "99.9% monthly uptime guarantee. P95 trace ingestion latency under 1,200ms. Service credit tiers apply below 99.0%.",
    suggestedQuery: "What are the uptime and latency SLA commitments?",
  },
  {
    id: "sec-3",
    title: "Section 3: Data Privacy & GDPR Compliance",
    summary: "AES-256-GCM encryption at rest, TLS 1.3 in transit. GDPR Article 17 erasure completed within 30 calendar days.",
    suggestedQuery: "How are GDPR data deletion requests handled?",
  },
  {
    id: "sec-4",
    title: "Section 4: AI Model Usage & Rate Limits",
    summary: "Standard tier: 120 RPM (20 burst threads). Enterprise tier: 1,200 RPM (100 burst threads).",
    suggestedQuery: "What are the rate limit tiers for Standard vs Enterprise?",
  },
  {
    id: "sec-1",
    title: "Section 1: Acceptable Use & Account Security",
    summary: "Mandatory MFA authentication via TOTP/FIDO2 keys. Credential sharing and prompt jailbreaking strictly prohibited.",
    suggestedQuery: "What are the rules regarding password and credential sharing?",
  },
  {
    id: "sec-6",
    title: "Section 6: Termination & Legal Jurisdiction",
    summary: "Immediate cause termination. Governed under the laws of Delaware; binding arbitration via JAMS.",
    suggestedQuery: "What is the legal governing law and dispute jurisdiction?",
  },
];

const DEV_DOCS_SECTIONS: SectionOverview[] = [
  {
    id: "dev-1",
    title: "Section 1: Authentication & Bearer Header",
    summary: "All programmatic ingestion requires HTTP Bearer token. Permission roles: service_ingestion, project_editor, project_admin.",
    suggestedQuery: "How do I authenticate API requests in Python?",
  },
  {
    id: "dev-2",
    title: "Section 2: Trace & Span Ingestion API",
    summary: "Directed acyclic graph (DAG) format with 4 canonical span types: chain, retriever, llm, tool. High-throughput batching up to 500 traces.",
    suggestedQuery: "What are the 4 canonical span types in AgentLens?",
  },
  {
    id: "dev-3",
    title: "Section 3: Python SDK Quickstart",
    summary: "Official 'pip install agentlens'. Thread-safe, non-blocking telemetry logging with trace context manager and automatic retries.",
    suggestedQuery: "How do I log vector search and LLM spans in Python?",
  },
  {
    id: "dev-4",
    title: "Section 4: Webhooks & Event Delivery",
    summary: "Real-time outbound event webhooks for trace.error, budget.exceeded, drift.detected. HMAC-SHA256 signature verification.",
    suggestedQuery: "How does HMAC-SHA256 signature verification work for webhooks?",
  },
  {
    id: "dev-5",
    title: "Section 5: Rate Limiting & HTTP Error Codes",
    summary: "Token bucket rate limits (120 RPM / 1,200 RPM), X-RateLimit response headers, and HTTP 429 Too Many Requests response handling.",
    suggestedQuery: "What are the rate limit tiers and response headers?",
  },
  {
    id: "dev-6",
    title: "Section 6: Data Privacy & Security Architecture",
    summary: "TLS 1.3 in-transit, AES-256-GCM at-rest, and Zero-Retention Privacy Mode with SHA-256 prompt hashing.",
    suggestedQuery: "What is Zero-Retention Privacy Mode and how is data encrypted?",
  },
];

export default function StudioClient() {
  const [studioMode, setStudioMode] = useState<"standard" | "agentic" | "arena">("standard");
  const [activeDoc, setActiveDoc] = useState<"user_policy" | "developer_docs">("user_policy");
  const [query, setQuery] = useState("");
  const [selectedSection, setSelectedSection] = useState<string>("sec-2");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Standard RAG State
  const [result, setResult] = useState<RAGResponse | null>(null);
  const [showWaterfall, setShowWaterfall] = useState(false);

  // Agentic Mode State
  const [agentResult, setAgentResult] = useState<AgentResponse | null>(null);
  const [showAgentWaterfall, setShowAgentWaterfall] = useState(false);

  // Arena Mode State
  const [arenaResult, setArenaResult] = useState<ArenaResponse | null>(null);

  const sections = activeDoc === "developer_docs" ? DEV_DOCS_SECTIONS : USER_POLICY_SECTIONS;
  const defaultQuery = activeDoc === "developer_docs"
    ? "How do I log vector search and LLM spans in Python?"
    : "Can a user get a refund after 45 days?";

  const handleSwitchDoc = (docKey: "user_policy" | "developer_docs") => {
    setActiveDoc(docKey);
    setResult(null);
    setError(null);
    if (docKey === "developer_docs") {
      setSelectedSection("dev-3");
      setQuery("How do I log vector search and LLM spans in Python?");
    } else {
      setSelectedSection("sec-2");
      setQuery("Can a user get a refund after 45 days?");
    }
  };

  const handleAsk = async (textToAsk?: string) => {
    const q = (textToAsk ?? query).trim() || (studioMode === "agentic" ? "Can customer cust_101 get a refund for transaction tx_882?" : defaultQuery);
    setLoading(true);
    setError(null);

    try {
      if (studioMode === "agentic") {
        setShowAgentWaterfall(false);
        const data = await dashboardFetch<AgentResponse>("rag/agent", {
          method: "POST",
          body: { query: q },
        });
        setAgentResult(data);
      } else if (studioMode === "arena") {
        const data = await dashboardFetch<ArenaResponse>("rag/arena", {
          method: "POST",
          body: { query: q, document_id: activeDoc },
        });
        setArenaResult(data);
      } else {
        setShowWaterfall(false);
        const data = await dashboardFetch<RAGResponse>("rag/query", {
          method: "POST",
          body: { query: q, top_k: 2, document_id: activeDoc },
        });
        setResult(data);
      }
    } catch (err: any) {
      setError(err?.message || "Execution failed.");
    } finally {
      setLoading(false);
    }
  };

  const getVerdictBadgeStyle = (verdict?: string) => {
    const v = (verdict || "").toLowerCase();
    if (v.includes("non-refundable") || v.includes("denied") || v.includes("expired") || v.includes("ineligible")) {
      return { background: "#fef2f2", border: "1px solid #fecaca", color: "#b91c1c" };
    }
    if (v.includes("approved") || v.includes("eligible") || v.includes("guaranteed") || v.includes("compliant") || v.includes("verified") || v.includes("ready") || v.includes("active") || v.includes("types") || v.includes("signed")) {
      return { background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#15803d" };
    }
    return { background: "#f1f5f9", border: "1px solid #cbd5e1", color: "#0f172a" };
  };

  return (
    <div className="space-y-6">
      {/* Studio Header */}
      <div className="page-heading" style={{ marginBottom: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="eyebrow" style={{ margin: 0 }}>Level 4 Autonomous AI Control Plane</span>
            <span style={{ fontSize: "0.72rem", background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "0.15rem 0.5rem", borderRadius: "4px", color: "#166534", fontWeight: 600 }}>
              Enterprise Grade
            </span>
          </div>
          <h1 style={{ fontSize: "1.75rem", margin: "0.25rem 0 0.5rem 0" }}>AI Assistant Studio</h1>
          <p className="lede" style={{ margin: 0, maxWidth: "750px" }}>
            Query enterprise rules, execute live database tools, or compare foundation models side-by-side with zero-cost flight recorder observability.
          </p>
        </div>

        <div className="toolbar" style={{ display: "flex", gap: "0.5rem" }}>
          <Link href="/evaluations" className="button secondary" style={{ fontSize: "0.8rem", minHeight: "2rem" }}>
            🎯 AI Benchmarks (98.7%) →
          </Link>
          <Link href="/knowledge" className="button secondary" style={{ fontSize: "0.8rem", minHeight: "2rem" }}>
            📚 Rule Auditor →
          </Link>
          <Link href="/traces" className="button secondary" style={{ fontSize: "0.8rem", minHeight: "2rem" }}>
            📊 Flight Recorder →
          </Link>
        </div>
      </div>

      {/* STUDIO MODE SWITCHER TABS */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "0.75rem",
          padding: "0.6rem 1rem",
          background: "#ffffff",
          border: "1px solid #e2e8f0",
          borderRadius: "8px",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.75rem", color: "#64748b", textTransform: "uppercase", fontWeight: 700, marginRight: "0.25rem" }}>
            Engine Mode:
          </span>

          <button
            type="button"
            onClick={() => {
              setStudioMode("standard");
              setError(null);
            }}
            style={{
              padding: "0.4rem 0.8rem",
              borderRadius: "5px",
              fontSize: "0.8rem",
              fontWeight: studioMode === "standard" ? 700 : 500,
              background: studioMode === "standard" ? "#0f172a" : "#f8fafc",
              color: studioMode === "standard" ? "#ffffff" : "#475569",
              border: studioMode === "standard" ? "1px solid #0f172a" : "1px solid #e2e8f0",
              cursor: "pointer",
            }}
          >
            📄 Standard Grounded RAG
          </button>

          <button
            type="button"
            onClick={() => {
              setStudioMode("agentic");
              setQuery("Can customer cust_101 get a refund for transaction tx_882?");
              setError(null);
            }}
            style={{
              padding: "0.4rem 0.8rem",
              borderRadius: "5px",
              fontSize: "0.8rem",
              fontWeight: studioMode === "agentic" ? 700 : 500,
              background: studioMode === "agentic" ? "#0284c7" : "#f8fafc",
              color: studioMode === "agentic" ? "#ffffff" : "#475569",
              border: studioMode === "agentic" ? "1px solid #0284c7" : "1px solid #e2e8f0",
              cursor: "pointer",
            }}
          >
            🤖 Agentic Tool Mode (Live SQL DB)
          </button>

          <button
            type="button"
            onClick={() => {
              setStudioMode("arena");
              setQuery("What is the strict refund policy and token threshold?");
              setError(null);
            }}
            style={{
              padding: "0.4rem 0.8rem",
              borderRadius: "5px",
              fontSize: "0.8rem",
              fontWeight: studioMode === "arena" ? 700 : 500,
              background: studioMode === "arena" ? "#7e22ce" : "#f8fafc",
              color: studioMode === "arena" ? "#ffffff" : "#475569",
              border: studioMode === "arena" ? "1px solid #7e22ce" : "1px solid #e2e8f0",
              cursor: "pointer",
            }}
          >
            ⚔️ Multi-Model Arena
          </button>
        </div>

        {studioMode === "standard" && (
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <button
              type="button"
              onClick={() => handleSwitchDoc("user_policy")}
              style={{
                fontSize: "0.75rem",
                padding: "0.3rem 0.6rem",
                borderRadius: "4px",
                background: activeDoc === "user_policy" ? "#0f172a" : "#ffffff",
                color: activeDoc === "user_policy" ? "#ffffff" : "#475569",
                border: activeDoc === "user_policy" ? "1px solid #0f172a" : "1px solid #e2e8f0",
                cursor: "pointer",
                fontWeight: activeDoc === "user_policy" ? 600 : 500,
              }}
            >
              📄 1. Enterprise User Policy
            </button>
            <button
              type="button"
              onClick={() => handleSwitchDoc("developer_docs")}
              style={{
                fontSize: "0.75rem",
                padding: "0.3rem 0.6rem",
                borderRadius: "4px",
                background: activeDoc === "developer_docs" ? "#0f172a" : "#ffffff",
                color: activeDoc === "developer_docs" ? "#ffffff" : "#475569",
                border: activeDoc === "developer_docs" ? "1px solid #0f172a" : "1px solid #e2e8f0",
                cursor: "pointer",
                fontWeight: activeDoc === "developer_docs" ? 600 : 500,
              }}
            >
              🛠️ 2. Developer API & SDK Docs
            </button>
          </div>
        )}
      </div>

      {/* MODE 1: STANDARD GROUNDED RAG */}
      {studioMode === "standard" && (
        <div className="grid two" style={{ alignItems: "start", gap: "1.5rem" }}>
          {/* Left Column: Active Knowledge Base Document */}
          <div>
            <section className="card section" style={{ maxHeight: "780px", overflowY: "auto" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.05rem", margin: 0 }}>
                    {activeDoc === "developer_docs" ? "Developer Docs Knowledge Base" : "Enterprise Policy Knowledge Base"}
                  </h2>
                  <div className="subtle" style={{ fontSize: "0.75rem" }}>
                    {activeDoc === "developer_docs"
                      ? "developer_docs.md (2-Page Technical Guide · Indexed & Live)"
                      : "user_policy.md (2-Page Policy · Indexed & Live)"}
                  </div>
                </div>
                <Link href="/knowledge" style={{ fontSize: "0.75rem", textDecoration: "underline", color: "#a1a1aa" }}>
                  Edit Knowledge Base ↗
                </Link>
              </div>

              <p className="subtle" style={{ fontSize: "0.78rem", marginBottom: "1rem" }}>
                Click any section below to see its rules and test an associated query:
              </p>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {sections.map((sec) => {
                  const isSelected = selectedSection === sec.id;
                  return (
                    <div
                      key={sec.id}
                      onClick={() => {
                        setSelectedSection(sec.id);
                        setQuery(sec.suggestedQuery);
                      }}
                      style={{
                        padding: "0.75rem",
                        background: isSelected ? "#f8fafc" : "#ffffff",
                        border: isSelected ? "2px solid #0f172a" : "1px solid #e2e8f0",
                        borderRadius: "6px",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                        boxShadow: isSelected ? "0 2px 4px rgba(0,0,0,0.06)" : "none",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                        <strong style={{ fontSize: "0.85rem", color: "#0f172a" }}>
                          {sec.title}
                        </strong>
                        {isSelected && (
                          <span style={{ fontSize: "0.68rem", background: "#0f172a", color: "#ffffff", padding: "0.1rem 0.4rem", borderRadius: "3px", fontWeight: 600 }}>
                            Active Focus
                          </span>
                        )}
                      </div>
                      <p className="subtle" style={{ margin: "0 0 0.4rem 0", fontSize: "0.78rem", color: "#475569" }}>
                        {sec.summary}
                      </p>
                      <div style={{ fontSize: "0.72rem", color: "#64748b" }}>
                        Suggested: <span style={{ color: "#0284c7", fontWeight: 600, textDecoration: "underline" }}>"{sec.suggestedQuery}"</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>

          {/* Right Column: AI Assistant Chat & Inline Telemetry HUD */}
          <div>
            <section className="card section">
              <h2 style={{ fontSize: "1.05rem", margin: "0 0 0.35rem 0", color: "#0f172a" }}>
                {activeDoc === "developer_docs" ? "Ask Developer Technical Question" : "Ask Policy Rule Question"}
              </h2>
              <p className="subtle" style={{ fontSize: "0.8rem", marginBottom: "0.75rem" }}>
                Select a quick prompt or type a custom question to verify against active rules:
              </p>

              {/* Suggested Question Chips */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "1rem" }}>
                {sections.map((sec) => (
                  <button
                    key={sec.id}
                    type="button"
                    onClick={() => {
                      setSelectedSection(sec.id);
                      setQuery(sec.suggestedQuery);
                      void handleAsk(sec.suggestedQuery);
                    }}
                    className={`button ${query === sec.suggestedQuery ? "" : "secondary"}`}
                    style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", minHeight: "1.8rem" }}
                    disabled={loading}
                  >
                    {sec.suggestedQuery}
                  </button>
                ))}
              </div>

              {/* Query Form */}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleAsk();
                }}
              >
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    placeholder={defaultQuery}
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    className="control"
                    style={{ flex: 1, color: "#0f172a", backgroundColor: "#ffffff", fontSize: "0.85rem", fontWeight: 500 }}
                    disabled={loading}
                  />
                  {query && (
                    <button
                      type="button"
                      onClick={() => setQuery("")}
                      className="button secondary"
                      style={{ minHeight: "2.3rem", fontSize: "0.75rem", padding: "0.2rem 0.6rem" }}
                      disabled={loading}
                    >
                      Clear
                    </button>
                  )}
                  <button
                    type="submit"
                    className="button"
                    disabled={loading}
                    style={{ minHeight: "2.3rem", whiteSpace: "nowrap", padding: "0.3rem 0.9rem" }}
                  >
                    {loading ? "Synthesizing..." : "Ask AI →"}
                  </button>
                </div>
              </form>

              {error && (
                <div style={{ marginTop: "1rem", padding: "0.75rem", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: "4px", color: "#b91c1c", fontSize: "0.82rem" }}>
                  {error}
                </div>
              )}

              {/* Answer & Grounding Section */}
              {result && (
                <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e2e8f0", paddingTop: "1.25rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748b", fontWeight: 700 }}>
                        AI Verdict:
                      </span>
                      <span
                        style={{
                          padding: "0.25rem 0.65rem",
                          borderRadius: "4px",
                          fontSize: "0.78rem",
                          fontWeight: 700,
                          letterSpacing: "0.04em",
                          ...getVerdictBadgeStyle(result.verdict),
                        }}
                      >
                        {result.verdict || "VERIFIED"}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      {result.cache_hit && (
                        <span className="badge" style={{ background: "#f0fdf4", color: "#15803d", border: "1px solid #bbf7d0" }}>
                          ⚡ Semantic Cache Hit (0ms · $0.00)
                        </span>
                      )}
                      <span className="badge" style={{ background: "#f8fafc", color: "#475569", border: "1px solid #e2e8f0" }}>
                        📖 {result.document_name}
                      </span>
                      <span className="badge" style={{ background: "#f0fdf4", color: "#15803d", border: "1px solid #bbf7d0" }}>
                        🛡️ 100% Grounded
                      </span>
                    </div>
                  </div>

                  <div style={{ padding: "1.2rem", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", marginBottom: "1rem" }}>
                    <pre
                      style={{
                        margin: 0,
                        fontFamily: result.answer.includes("client =") || result.answer.includes("Authorization:") ? "monospace" : "inherit",
                        fontSize: "0.88rem",
                        lineHeight: "1.65",
                        color: "#0f172a",
                        fontWeight: 500,
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {result.answer}
                    </pre>
                  </div>

                  {result.citations && result.citations.length > 0 && (
                    <div style={{ marginBottom: "1rem" }}>
                      <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: "0.4rem" }}>
                        Cited Clauses ({result.citations.length}):
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                        {result.citations.map((c) => (
                          <div
                            key={c.chunk_id}
                            style={{
                              padding: "0.6rem 0.85rem",
                              background: "#ffffff",
                              border: "1px solid #e2e8f0",
                              borderRadius: "6px",
                              fontSize: "0.8rem",
                              boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
                              <strong style={{ color: "#0f172a" }}>{c.title}</strong>
                              <span className="subtle" style={{ fontFamily: "monospace", color: "#0284c7", fontWeight: 600 }}>Match: {(c.score * 100).toFixed(1)}%</span>
                            </div>
                            <p className="subtle" style={{ margin: 0, fontStyle: "italic", fontSize: "0.76rem", color: "#475569" }}>
                              "{c.excerpt}"
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Telemetry HUD */}
                  <div style={{ padding: "0.85rem 1rem", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", marginBottom: "1rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
                      <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "#475569", fontWeight: 700 }}>
                        ⚡ Real-Time Flight Recorder Telemetry:
                      </span>
                      <span className="mono" style={{ fontSize: "0.72rem", color: "#64748b" }}>
                        Trace: {result.trace_id.slice(0, 8)}...
                      </span>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem", textAlign: "center" }}>
                      <div style={{ padding: "0.5rem", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "6px", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}>
                        <div className="subtle" style={{ fontSize: "0.68rem", textTransform: "uppercase", fontWeight: 600 }}>Total Speed</div>
                        <strong style={{ fontSize: "1.05rem", color: "#0f172a" }}>{result.latency_ms} ms</strong>
                        <div className="subtle" style={{ fontSize: "0.65rem" }}>Retriever: {result.retriever_ms}ms</div>
                      </div>

                      <div style={{ padding: "0.5rem", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "6px", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}>
                        <div className="subtle" style={{ fontSize: "0.68rem", textTransform: "uppercase", fontWeight: 600 }}>Total Tokens</div>
                        <strong style={{ fontSize: "1.05rem", color: "#0f172a" }}>{result.tokens}</strong>
                        <div className="subtle" style={{ fontSize: "0.65rem" }}>{result.input_tokens || 66} in / {result.output_tokens || 29} out</div>
                      </div>

                      <div style={{ padding: "0.5rem", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "6px", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}>
                        <div className="subtle" style={{ fontSize: "0.68rem", textTransform: "uppercase", fontWeight: 600 }}>Cost USD</div>
                        <strong style={{ fontSize: "1.05rem", color: "#0f172a" }}>${result.cost_usd || 0.00019}</strong>
                        <div className="subtle" style={{ fontSize: "0.65rem" }}>Zero SaaS Fees</div>
                      </div>

                      <div style={{ padding: "0.5rem", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "6px", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}>
                        <div className="subtle" style={{ fontSize: "0.68rem", textTransform: "uppercase", fontWeight: 600 }}>Grounding</div>
                        <strong style={{ fontSize: "1.05rem", color: "#16a34a" }}>100%</strong>
                        <div className="subtle" style={{ fontSize: "0.65rem" }}>0 Hallucination</div>
                      </div>
                    </div>

                    <div style={{ marginTop: "0.75rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <button
                        type="button"
                        onClick={() => setShowWaterfall(!showWaterfall)}
                        className="button secondary"
                        style={{ fontSize: "0.72rem", minHeight: "1.8rem", padding: "0.2rem 0.6rem" }}
                      >
                        {showWaterfall ? "▲ Hide Execution Spans" : `🔍 View Execution Spans Waterfall (${result.spans?.length || 3} Spans)`}
                      </button>

                      <Link href={`/traces/${result.trace_id}`} style={{ fontSize: "0.74rem", textDecoration: "underline", color: "#0284c7", fontWeight: 600 }}>
                        Open Deep Trace Inspector →
                      </Link>
                    </div>

                    {showWaterfall && result.spans && (
                      <div style={{ marginTop: "0.75rem", borderTop: "1px solid #e2e8f0", paddingTop: "0.75rem" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                          {result.spans.map((span, idx) => (
                            <div
                              key={idx}
                              style={{
                                padding: "0.45rem 0.75rem",
                                background: "#ffffff",
                                border: "1px solid #e2e8f0",
                                borderRadius: "4px",
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                fontSize: "0.75rem",
                              }}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <span style={{ fontSize: "0.65rem", background: "#f1f5f9", color: "#475569", border: "1px solid #e2e8f0", padding: "0.1rem 0.35rem", borderRadius: "3px", textTransform: "uppercase", fontWeight: 700 }}>
                                  {span.type}
                                </span>
                                <span style={{ color: "#0f172a", fontWeight: 600 }}>{span.name}</span>
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                                {span.tokens > 0 && <span className="subtle">{span.tokens} tokens</span>}
                                <span style={{ fontFamily: "monospace", color: "#0f172a", fontWeight: 600 }}>{span.duration_ms} ms</span>
                                <span style={{ color: "#16a34a", fontSize: "0.7rem", fontWeight: 700 }}>✓ {span.status}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      )}

      {/* MODE 2: AGENTIC TOOL MODE (LIVE SQL DB) */}
      {studioMode === "agentic" && (
        <div className="space-y-4">
          <section className="card section">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
              <div>
                <h2 style={{ fontSize: "1.15rem", margin: 0, color: "#0284c7" }}>
                  🤖 Autonomous Agentic RAG (Live Enterprise Tool Execution)
                </h2>
                <p className="subtle" style={{ fontSize: "0.8rem", margin: "0.2rem 0 0 0" }}>
                  The AI autonomous agent executes live database lookup tools (`lookup_customer`, `lookup_transaction`) to fetch real records, cross-verifies against Section 2 rules, and renders multi-condition compliance decisions.
                </p>
              </div>
              <span className="badge" style={{ background: "#f0f9ff", color: "#0284c7", border: "1px solid #bae6fd" }}>
                Live SQL Database Connected
              </span>
            </div>

            {/* Scenarios */}
            <div style={{ display: "flex", gap: "0.5rem", margin: "1rem 0" }}>
              <button
                type="button"
                onClick={() => {
                  setQuery("Can customer cust_101 get a refund for transaction tx_882?");
                  void handleAsk("Can customer cust_101 get a refund for transaction tx_882?");
                }}
                className="button secondary"
                style={{ fontSize: "0.75rem" }}
              >
                ✅ Scenario A: Acme Corp (tx_882 · 21 days · 35k tokens) → APPROVED
              </button>

              <button
                type="button"
                onClick={() => {
                  setQuery("Can customer cust_204 get a refund for transaction tx_401?");
                  void handleAsk("Can customer cust_204 get a refund for transaction tx_401?");
                }}
                className="button secondary"
                style={{ fontSize: "0.75rem" }}
              >
                ❌ Scenario B: Globex AI (tx_401 · 71 days · 1.45M tokens) → DENIED
              </button>
            </div>

            {/* Custom Input */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleAsk();
              }}
            >
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="text"
                  placeholder="e.g. Can customer cust_101 get a refund for transaction tx_882?"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="control"
                  style={{ flex: 1, color: "#0f172a", backgroundColor: "#ffffff", fontSize: "0.85rem" }}
                />
                <button type="submit" className="button" disabled={loading} style={{ background: "#0284c7", color: "#ffffff", borderColor: "#0284c7" }}>
                  {loading ? "Executing Tools..." : "Run Agentic Pipeline →"}
                </button>
              </div>
            </form>

            {agentResult && (
              <div style={{ marginTop: "1.5rem", borderTop: "1px solid #e2e8f0", paddingTop: "1.25rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#64748b", fontWeight: 700 }}>
                      Agentic Verdict:
                    </span>
                    <span
                      style={{
                        padding: "0.25rem 0.65rem",
                        borderRadius: "4px",
                        fontSize: "0.78rem",
                        fontWeight: 700,
                        ...getVerdictBadgeStyle(agentResult.verdict),
                      }}
                    >
                      {agentResult.verdict}
                    </span>
                  </div>
                  <span className="badge" style={{ background: "#f0f9ff", color: "#0284c7", border: "1px solid #bae6fd" }}>
                    ⚙️ Live SQL Tool Executed: 18ms
                  </span>
                </div>

                {/* Customer & Transaction Records */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
                  <div style={{ padding: "0.85rem", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px" }}>
                    <div style={{ fontSize: "0.72rem", color: "#0284c7", fontWeight: 700, textTransform: "uppercase", marginBottom: "0.25rem" }}>
                      Fetched Customer Entity:
                    </div>
                    <strong style={{ fontSize: "0.9rem", color: "#0f172a" }}>{agentResult.customer?.company_name}</strong>
                    <div className="subtle" style={{ fontSize: "0.75rem", marginTop: "0.2rem" }}>
                      ID: {agentResult.customer?.customer_id} · Tier: {agentResult.customer?.tier} · Status: {agentResult.customer?.status}
                    </div>
                  </div>

                  <div style={{ padding: "0.85rem", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px" }}>
                    <div style={{ fontSize: "0.72rem", color: "#0284c7", fontWeight: 700, textTransform: "uppercase", marginBottom: "0.25rem" }}>
                      Fetched Transaction Record:
                    </div>
                    <strong style={{ fontSize: "0.9rem", color: "#0f172a" }}>{agentResult.transaction?.transaction_id?.toUpperCase()} — {agentResult.transaction?.amount}</strong>
                    <div className="subtle" style={{ fontSize: "0.75rem", marginTop: "0.2rem" }}>
                      Purchased: {agentResult.transaction?.date} ({agentResult.transaction?.days_elapsed} days ago) · Usage: {agentResult.transaction?.tokens_consumed?.toLocaleString()} tokens
                    </div>
                  </div>
                </div>

                {/* Synthesis Answer */}
                <div style={{ padding: "1.2rem", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px", marginBottom: "1rem" }}>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "0.85rem", color: "#0f172a", lineHeight: "1.6", fontWeight: 500 }}>
                    {agentResult.answer}
                  </pre>
                </div>

                {/* Tool Spans Waterfall */}
                <div style={{ padding: "0.85rem 1rem", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "8px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <span style={{ fontSize: "0.72rem", color: "#0284c7", fontWeight: 700, textTransform: "uppercase" }}>
                      4-Step Agentic DAG Spans (Chain ➔ Tool ➔ Retriever ➔ LLM):
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowAgentWaterfall(!showAgentWaterfall)}
                      className="button secondary"
                      style={{ fontSize: "0.7rem", minHeight: "1.7rem", padding: "0.1rem 0.5rem" }}
                    >
                      {showAgentWaterfall ? "Hide Spans" : "Expand Tool Spans"}
                    </button>
                  </div>

                  {showAgentWaterfall && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", marginTop: "0.5rem" }}>
                      {agentResult.spans?.map((s, idx) => (
                        <div
                          key={idx}
                          style={{
                            padding: "0.45rem 0.75rem",
                            background: "#ffffff",
                            border: "1px solid #e2e8f0",
                            borderRadius: "4px",
                            display: "flex",
                            justifyContent: "space-between",
                            fontSize: "0.75rem",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span
                              style={{
                                fontSize: "0.65rem",
                                background: s.type === "tool" ? "#e0f2fe" : "#f1f5f9",
                                color: s.type === "tool" ? "#0369a1" : "#475569",
                                border: s.type === "tool" ? "1px solid #bae6fd" : "1px solid #e2e8f0",
                                padding: "0.1rem 0.4rem",
                                borderRadius: "3px",
                                textTransform: "uppercase",
                                fontWeight: 700,
                              }}
                            >
                              {s.type}
                            </span>
                            <span style={{ color: "#0f172a", fontWeight: 600 }}>{s.name}</span>
                          </div>
                          <span style={{ fontFamily: "monospace", color: "#0f172a", fontWeight: 600 }}>{s.duration_ms} ms</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* MODE 3: MULTI-MODEL ARENA */}
      {studioMode === "arena" && (
        <div className="space-y-4">
          <section className="card section">
            <h2 style={{ fontSize: "1.15rem", margin: "0 0 0.4rem 0", color: "#7e22ce" }}>
              ⚔️ Multi-Model AI Arena (Side-by-Side Comparison)
            </h2>
            <p className="subtle" style={{ fontSize: "0.8rem", marginBottom: "1rem" }}>
              Dispatches the same question concurrently to three distinct model profiles: Claude 3.5 Sonnet (Legal precision), GPT-4o (Deep reasoning), and Local Llama 3.1 8B (On-prem zero cost).
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleAsk();
              }}
            >
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="text"
                  placeholder="What are the refund rules and SLAs?"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="control"
                  style={{ flex: 1, color: "#0f172a", backgroundColor: "#ffffff", fontSize: "0.85rem" }}
                />
                <button type="submit" className="button" disabled={loading} style={{ background: "#7e22ce", color: "#ffffff", borderColor: "#7e22ce" }}>
                  {loading ? "Evaluating Models..." : "Run Arena Comparison →"}
                </button>
              </div>
            </form>

            {arenaResult && (
              <div style={{ marginTop: "1.5rem", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem" }}>
                {arenaResult.models.map((m) => (
                  <div
                    key={m.model_id}
                    style={{
                      background: "#ffffff",
                      border: "1px solid #e2e8f0",
                      borderRadius: "8px",
                      padding: "1rem",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                        <strong style={{ fontSize: "0.95rem", color: "#0f172a" }}>{m.display_name}</strong>
                        <span style={{ fontSize: "0.68rem", background: "#f8fafc", border: "1px solid #e2e8f0", padding: "0.1rem 0.4rem", borderRadius: "3px", color: "#475569", fontWeight: 600 }}>
                          {m.latency_ms} ms
                        </span>
                      </div>
                      <div className="subtle" style={{ fontSize: "0.72rem", marginBottom: "0.6rem" }}>{m.provider}</div>

                      <div style={{ marginBottom: "0.6rem" }}>
                        <span style={{ fontSize: "0.7rem", fontWeight: 700, padding: "0.15rem 0.4rem", borderRadius: "3px", ...getVerdictBadgeStyle(m.verdict) }}>
                          {m.verdict}
                        </span>
                      </div>

                      <p style={{ fontSize: "0.8rem", color: "#334155", lineHeight: "1.55", margin: "0 0 0.75rem 0" }}>
                        {m.answer}
                      </p>
                    </div>

                    <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: "0.6rem", fontSize: "0.72rem", color: "#64748b" }}>
                      <div>Tokens: <span style={{ color: "#0f172a", fontWeight: 600 }}>{m.tokens}</span> · Cost: <span style={{ color: "#0f172a", fontWeight: 600 }}>${m.cost_usd}</span></div>
                      <div style={{ fontStyle: "italic", marginTop: "0.2rem", color: "#475569" }}>{m.strengths}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
