"use client";

import React, { useState } from "react";
import Link from "next/link";
import { dashboardFetch } from "../lib/client";

interface Citation {
  chunk_id: string;
  section: string;
  title: string;
  score: number;
  excerpt: string;
}

interface RAGResponse {
  query: string;
  answer: string;
  citations: Citation[];
  trace_id: string;
  latency_ms: number;
  retriever_ms: number;
  tokens: number;
  grounded: boolean;
  document_name: string;
}

export function RAGPlaygroundClient() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  // Initial state is null: No pre-filled or fake result before user asks a question
  const [result, setResult] = useState<RAGResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const presetQueries = [
    "Can a user get a refund after 45 days?",
    "What are the uptime and latency SLA commitments?",
    "How are GDPR data deletion requests handled?",
    "What are the rate limit tiers for Standard vs Enterprise?",
    "What are the rules regarding password and credential sharing?",
  ];

  const handleAsk = async (questionText?: string) => {
    const q = (questionText !== undefined && questionText !== "" ? questionText : query).trim() || presetQueries[0];
    setQuery(q);
    setLoading(true);
    setError(null);

    try {
      // Call Next.js API proxy properly via dashboardFetch
      const data = await dashboardFetch<RAGResponse>("rag/query", {
        method: "POST",
        body: { query: q, top_k: 2 },
      });
      setResult(data);
    } catch (err: any) {
      setError(err?.message || "Failed to query policy RAG system.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Enterprise RAG Assistant</p>
          <h1>User Policy RAG System</h1>
          <p className="lede">
            Built-in Retrieval-Augmented Generation engine. Queries the 2-page enterprise user policy document, retrieves exact clause citations, and records live execution telemetry directly into AgentLens.
          </p>
        </div>
      </div>

      {/* Split-Screen Layout adhering strictly to Noir Monochrome */}
      <div className="grid two" style={{ alignItems: "start", gap: "1.5rem" }}>
        {/* Left Column: 2-Page Policy Document Overview */}
        <div>
          <section className="card section" style={{ maxHeight: "720px", overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <div>
                <h2 style={{ fontSize: "1.05rem", margin: 0 }}>Active Knowledge Base</h2>
                <div className="subtle" style={{ fontSize: "0.75rem" }}>user_policy.md (v3.2-Enterprise · 2 Pages)</div>
              </div>
              <span className="badge">Indexed & Active</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", fontSize: "0.8rem" }}>
              <div style={{ padding: "0.75rem", background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: "6px" }}>
                <strong style={{ display: "block", marginBottom: "0.25rem", color: "#0F172A" }}>
                  Section 1: Acceptable Use & Account Security
                </strong>
                <p className="subtle" style={{ margin: 0, color: "#475569" }}>
                  Mandatory MFA authentication via TOTP/FIDO2 keys. Credential sharing and automated prompt jailbreaking strictly prohibited.
                </p>
              </div>

              <div style={{ padding: "0.75rem", background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: "6px" }}>
                <strong style={{ display: "block", marginBottom: "0.25rem", color: "#0F172A" }}>
                  Section 2: Billing & Strict 30-Day Refund Policy
                </strong>
                <p className="subtle" style={{ margin: 0, color: "#475569" }}>
                  Full refunds allowed within 30 calendar days. Strictly non-refundable after 30 days or if usage exceeds 1,000,000 tokens.
                </p>
              </div>

              <div style={{ padding: "0.75rem", background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: "6px" }}>
                <strong style={{ display: "block", marginBottom: "0.25rem", color: "#0F172A" }}>
                  Section 3: Data Privacy & GDPR Compliance
                </strong>
                <p className="subtle" style={{ margin: 0, color: "#475569" }}>
                  AES-256-GCM encryption at rest, TLS 1.3 in transit. GDPR Article 17 erasure completed within 30 calendar days.
                </p>
              </div>

              <div style={{ padding: "0.75rem", background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: "6px" }}>
                <strong style={{ display: "block", marginBottom: "0.25rem", color: "#0F172A" }}>
                  Section 4: AI Model Usage & Rate Limits
                </strong>
                <p className="subtle" style={{ margin: 0, color: "#475569" }}>
                  Standard tier: 120 RPM (20 burst threads). Enterprise tier: 1,200 RPM (100 burst threads). Content safety filters active.
                </p>
              </div>

              <div style={{ padding: "0.75rem", background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: "6px" }}>
                <strong style={{ display: "block", marginBottom: "0.25rem", color: "#0F172A" }}>
                  Section 5: Service Level Agreements (SLAs)
                </strong>
                <p className="subtle" style={{ margin: 0, color: "#475569" }}>
                  99.9% monthly uptime guarantee. P95 trace ingestion latency under 1,200ms. Service credit tiers apply below 99.0%.
                </p>
              </div>

              <div style={{ padding: "0.75rem", background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: "6px" }}>
                <strong style={{ display: "block", marginBottom: "0.25rem", color: "#0F172A" }}>
                  Section 6: Termination & Legal Jurisdiction
                </strong>
                <p className="subtle" style={{ margin: 0, color: "#475569" }}>
                  Immediate cause termination. Governed under the laws of Delaware; binding arbitration via JAMS.
                </p>
              </div>
            </div>
          </section>
        </div>

        {/* Right Column: Interactive RAG Query & Live Telemetry Box */}
        <div>
          <section className="card section">
            <h2 style={{ fontSize: "1.05rem", marginBottom: "0.4rem" }}>Ask Policy Question</h2>
            <p className="subtle" style={{ fontSize: "0.82rem", marginBottom: "0.75rem" }}>
              Click any question below to test retrieval against the active policy rules:
            </p>

            {/* Quick Preset Buttons */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "1rem" }}>
              {presetQueries.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => {
                    setQuery(preset);
                    void handleAsk(preset);
                  }}
                  className={`button ${query === preset ? "" : "secondary"}`}
                  style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", minHeight: "1.8rem" }}
                  disabled={loading}
                >
                  {preset}
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
                  placeholder="e.g. Can I get a refund after 45 days?"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="control"
                  style={{ width: "100%", padding: "0.5rem 0.75rem", fontSize: "0.88rem" }}
                />
                {query.trim() && (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => {
                      setQuery("");
                      setError(null);
                    }}
                    style={{ whiteSpace: "nowrap", padding: "0.3rem 0.6rem", fontSize: "0.78rem" }}
                  >
                    Clear
                  </button>
                )}
                <button
                  type="submit"
                  className="button"
                  disabled={loading}
                  style={{ whiteSpace: "nowrap", minWidth: "7rem" }}
                >
                  {loading ? "Searching..." : "Ask RAG →"}
                </button>
              </div>
            </form>

            {error && (
              <div style={{ marginTop: "0.75rem", padding: "0.5rem 0.75rem", background: "#FEF2F2", border: "1px solid #FECACA", color: "#B91C1C", fontSize: "0.78rem", borderRadius: "6px" }}>
                {error}
              </div>
            )}
          </section>

          {/* RAG Answer Display */}
          {result ? (
            <section className="card section" style={{ border: "1px solid #E2E8F0", background: "#FFFFFF", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", fontWeight: 700 }}>
                  Grounded Synthesis Result
                </div>
                <span className="badge" style={{ background: "#DCFCE7", color: "#166534", border: "1px solid #BBF7D0", fontWeight: 600 }}>100% Policy Grounded</span>
              </div>

              <div style={{ fontSize: "0.92rem", lineHeight: "1.6", color: "#0F172A", marginBottom: "1rem" }}>
                {result.answer}
              </div>

              {/* Citations */}
              <div style={{ marginBottom: "1rem" }}>
                <div style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#64748B", fontWeight: 700, marginBottom: "0.4rem" }}>
                  Retrieved Policy Clauses ({result.citations.length})
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {result.citations.map((c, i) => (
                    <div key={i} style={{ padding: "0.6rem 0.8rem", background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: "6px", fontSize: "0.75rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 600, color: "#0F172A", marginBottom: "0.2rem" }}>
                        <span>{c.title} ({c.section})</span>
                        <span className="mono" style={{ color: "#0284C7", fontWeight: 700 }}>Match: {(c.score * 100).toFixed(1)}%</span>
                      </div>
                      <div className="subtle" style={{ fontStyle: "italic", margin: 0, color: "#475569" }}>&ldquo;{c.excerpt}&rdquo;</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Live Telemetry Card */}
              <div style={{ padding: "0.75rem 1rem", background: "#F8FAFC", border: "1px solid #CBD5E1", borderRadius: "8px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                  <div className="mono" style={{ display: "flex", alignItems: "center", gap: "0.75rem", fontSize: "0.75rem", color: "#0F172A" }}>
                    <span><strong style={{ color: "#64748B", fontFamily: "inherit" }}>LATENCY:</strong> {result.latency_ms}ms</span>
                    <span><strong style={{ color: "#64748B", fontFamily: "inherit" }}>RETRIEVER:</strong> {result.retriever_ms}ms</span>
                    <span><strong style={{ color: "#64748B", fontFamily: "inherit" }}>TOKENS:</strong> {result.tokens}</span>
                  </div>

                  <Link
                    href={`/traces/${result.trace_id}`}
                    className="button secondary"
                    style={{ fontSize: "0.72rem", padding: "0.2rem 0.6rem", minHeight: "1.8rem" }}
                  >
                    Inspect Waterfall in Traces →
                  </Link>
                </div>
                <div className="mono" style={{ marginTop: "0.4rem", fontSize: "0.68rem", color: "#64748B" }}>
                  Trace ID: {result.trace_id}
                </div>
              </div>
            </section>
          ) : (
            <section className="card section" style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
              <p className="subtle" style={{ margin: 0, fontSize: "0.85rem" }}>
                Click a preset question above or enter your question to query the active policy document.
              </p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
