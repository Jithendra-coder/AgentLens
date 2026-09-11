"use client";

import React, { useState, useEffect } from "react";
import { dashboardFetch, formatDuration, formatNumber } from "../lib/client";

interface PillarData {
  name: string;
  score: number;
  grade: string;
  color: string;
  metric_label: string;
  sub_metric: string;
  summary: string;
}

interface OpportunityItem {
  id: string;
  pillar: string;
  title: string;
  savings_label: string;
  savings_value: string;
  description: string;
  code_snippet: string;
  difficulty: string;
}

interface AuditItem {
  id: string;
  title: string;
  status: "passed" | "warning" | "failed";
  value: string;
  target: string;
  description: string;
}

interface LighthouseAudit {
  overall_score: number;
  overall_grade: string;
  overall_color: string;
  pillars: {
    latency: PillarData;
    grounding: PillarData;
    cost: PillarData;
    vector_density: PillarData;
  };
  opportunities: OpportunityItem[];
  audits: AuditItem[];
  primary_bottleneck: string;
  primary_bottleneck_pct: number;
}

interface PipelineSpan {
  name: string;
  span_type: string;
  latency_ms: number;
  component: string;
  pct?: number;
}

interface ChunkItem {
  chunk_id: string;
  doc: string;
  size_tokens: number;
  similarity: number;
}

interface RagLensReport {
  api_key: string;
  trace_id: string;
  query: string;
  domain?: string;
  model?: string;
  model_name?: string;
  total_latency_ms: number;
  total_tokens: number;
  cost_usd: number;
  status: string;
  storage: string;
  created_at: string;
  summary?: Record<string, any>;
  pipeline_spans: PipelineSpan[];
  diagnosis: Record<string, any>;
  chunks: ChunkItem[];
  lighthouse: LighthouseAudit;
}

interface HistoryReportSummary {
  api_key: string;
  trace_id: string;
  query: string;
  total_latency_ms: number;
  total_tokens: number;
  cost_usd: number;
  created_at: string;
  overall_score?: number;
  overall_grade?: string;
  lighthouse?: LighthouseAudit;
}

export default function RagLensClient() {
  const [loading, setLoading] = useState<boolean>(true);
  const [recentReports, setRecentReports] = useState<HistoryReportSummary[]>([]);

  // Active Report State
  const [lookupKey, setLookupKey] = useState<string>("");
  const [lookupLoading, setLookupLoading] = useState<boolean>(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [loadedReport, setLoadedReport] = useState<RagLensReport | null>(null);

  // Expanded snippets & filters
  const [expandedOppId, setExpandedOppId] = useState<string | null>(null);
  const [auditFilter, setAuditFilter] = useState<"all" | "opportunities" | "passed">("all");
  const [showHistoryDrawer, setShowHistoryDrawer] = useState<boolean>(false);

  // Search & New Run Execution
  const [searchQuery, setSearchQuery] = useState<string>("What is our enterprise refund policy for annual licenses?");
  const [selectedModel, setSelectedModel] = useState<string>("claude-3-5-sonnet");
  const [simulating, setSimulating] = useState<boolean>(false);
  const [justGeneratedKey, setJustGeneratedKey] = useState<string | null>(null);

  // Connect snippet mode
  const [connectMode, setConnectMode] = useState<"sdk" | "agent">("sdk");
  const [copiedKey, setCopiedKey] = useState<boolean>(false);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);

  const loadRecentReports = async () => {
    try {
      setLoading(true);
      const reports = await dashboardFetch<HistoryReportSummary[]>("raglens/reports?limit=10");
      setRecentReports(reports || []);
      return reports;
    } catch (err) {
      console.error("Failed to load past PostgreSQL reports", err);
      return [];
    } finally {
      setLoading(false);
    }
  };

  const handleLoadReportByKey = async (key: string) => {
    const cleanKey = key.trim();
    if (!cleanKey) return;
    try {
      setLookupLoading(true);
      setLookupError(null);
      const rep = await dashboardFetch<RagLensReport>(`raglens/report/${cleanKey}`);
      setLoadedReport(rep);
      setLookupKey(cleanKey);
      if (typeof window !== "undefined") {
        window.history.replaceState({}, "", `/raglens?key=${cleanKey}`);
      }
    } catch (err: any) {
      console.error("Failed to fetch report", err);
      setLookupError(`No report found in PostgreSQL for API key "${cleanKey}".`);
      setLoadedReport(null);
    } finally {
      setLookupLoading(false);
    }
  };

  // Initial mount: load recent reports and URL search param
  useEffect(() => {
    (async () => {
      const reports = await loadRecentReports();
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        const keyFromUrl = params.get("key");
        if (keyFromUrl) {
          handleLoadReportByKey(keyFromUrl);
        } else if (reports && reports.length > 0) {
          // Default to most recent PostgreSQL report
          handleLoadReportByKey(reports[0].api_key);
        }
      }
    })();
  }, []);

  const handleExecuteNewRun = async (queryText?: string, modelToUse?: string) => {
    try {
      setSimulating(true);
      setLookupError(null);
      const queryToRun = queryText || searchQuery;
      const modelParam = modelToUse || selectedModel;
      const res = await dashboardFetch<{
        status: string;
        api_key: string;
        trace_id: string;
        report: RagLensReport;
      }>("raglens/execute", {
        method: "POST",
        body: { query: queryToRun, scenario: "normal", model: modelParam },
      });

      setJustGeneratedKey(res.api_key);
      setLookupKey(res.api_key);
      setLoadedReport(res.report);
      if (typeof window !== "undefined") {
        window.history.replaceState({}, "", `/raglens?key=${res.api_key}`);
      }
      await loadRecentReports();
    } catch (err) {
      console.error("Execution failed", err);
    } finally {
      setSimulating(false);
    }
  };

  const handleCopy = (text: string, type: "key" | "link") => {
    navigator.clipboard.writeText(text);
    if (type === "key") {
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } else {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    }
  };

  // SVG Radial Gauge Renderer
  const renderRadialGauge = (score: number, color: string, size = 80, stroke = 7) => {
    const radius = (size - stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (Math.min(Math.max(score, 0), 100) / 100) * circumference;

    return (
      <div style={{ position: "relative", width: size, height: size, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke="#f1f5f9"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke={color}
            strokeWidth={stroke}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.6s ease-in-out" }}
          />
        </svg>
        <div style={{ position: "absolute", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
          <span style={{ fontSize: size > 80 ? "1.45rem" : "1.15rem", fontWeight: 800, color: "#0f172a", lineHeight: 1 }}>
            {score}
          </span>
        </div>
      </div>
    );
  };

  const currentLighthouse = loadedReport?.lighthouse;

  return (
    <div style={{ maxWidth: "1140px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* ----------------------------------------------------------------- */}
      {/* 1. HEADER TOPBAR & AUDIT TITLE                                    */}
      {/* ----------------------------------------------------------------- */}
      <div style={{ borderBottom: "1px solid #e2e8f0", paddingBottom: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "0.25rem" }}>
              <span style={{ fontSize: "0.72rem", fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "#64748b" }}>
                Lighthouse for RAG &bull; Automated AI Performance Audit
              </span>
              <span style={{ fontSize: "0.68rem", fontWeight: 700, padding: "2px 7px", borderRadius: "999px", backgroundColor: "#ecfdf5", color: "#065f46", border: "1px solid #a7f3d0" }}>
                PostgreSQL Store
              </span>
            </div>
            <h1 style={{ fontSize: "2.1rem", fontWeight: 800, letterSpacing: "-0.03em", color: "#0f172a", margin: "0 0 0.4rem" }}>
              RAG Performance Audit
            </h1>
            <p style={{ margin: 0, fontSize: "0.92rem", color: "#475569", lineHeight: 1.5, maxWidth: "46rem" }}>
              Automated scoring across <strong>Latency</strong>, <strong>Grounding</strong>, <strong>Cost</strong>, and <strong>Vector Density</strong>. Every evaluation is saved in PostgreSQL with a unique API key.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              onClick={() => setShowHistoryDrawer(!showHistoryDrawer)}
              className="button secondary"
              style={{ fontSize: "0.8rem", padding: "0.45rem 0.9rem", display: "flex", alignItems: "center", gap: "6px" }}
            >
              <span>Audit History ({recentReports.length})</span>
              <span style={{ fontSize: "0.7rem", color: "#64748b" }}>▼</span>
            </button>

            {loadedReport && (
              <button
                onClick={() => handleCopy(window.location.href, "link")}
                className="button secondary"
                style={{ fontSize: "0.8rem", padding: "0.45rem 0.9rem" }}
              >
                {copiedLink ? "Link Copied!" : "Share Audit URL"}
              </button>
            )}
          </div>
        </div>

        {/* PostgreSQL History Drawer (Collapsible) */}
        {showHistoryDrawer && (
          <div style={{ marginTop: "1.25rem", padding: "1rem", borderRadius: "8px", border: "1px solid #cbd5e1", backgroundColor: "#f8fafc" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <strong style={{ fontSize: "0.82rem", color: "#0f172a", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                PostgreSQL Audits History (Latest 10 Runs)
              </strong>
              <span style={{ fontSize: "0.75rem", color: "#64748b" }}>Click any run to load full metrics</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "0.6rem" }}>
              {recentReports.map((item) => {
                const isCurrent = loadedReport?.api_key === item.api_key;
                const score = item.overall_score || (item.lighthouse?.overall_score ?? 85);
                const grade = item.overall_grade || (item.lighthouse?.overall_grade ?? "B");
                const scoreColor = score >= 90 ? "#10b981" : score >= 65 ? "#f59e0b" : "#ef4444";

                return (
                  <div
                    key={item.api_key}
                    onClick={() => {
                      handleLoadReportByKey(item.api_key);
                      setShowHistoryDrawer(false);
                    }}
                    style={{
                      padding: "0.75rem",
                      borderRadius: "6px",
                      border: isCurrent ? "2px solid #0f172a" : "1px solid #e2e8f0",
                      backgroundColor: isCurrent ? "#ffffff" : "#ffffff",
                      cursor: "pointer",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <div style={{ overflow: "hidden", paddingRight: "0.5rem" }}>
                      <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#0f172a", whiteSpace: "nowrap", textOverflow: "ellipsis", overflow: "hidden" }}>
                        "{item.query}"
                      </div>
                      <div style={{ fontSize: "0.7rem", color: "#64748b", marginTop: "2px", fontFamily: "monospace" }}>
                        {item.api_key} &bull; {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                      <span style={{ display: "inline-block", padding: "2px 6px", borderRadius: "4px", fontSize: "0.72rem", fontWeight: 800, color: "#ffffff", backgroundColor: scoreColor }}>
                        {score} &bull; {grade}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* 2. API KEY LOOKUP & RUN BAR                                       */}
      {/* ----------------------------------------------------------------- */}
      <div style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem 1.5rem", backgroundColor: "#ffffff" }}>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <div style={{ position: "relative", flex: 1 }}>
            <input
              type="text"
              value={lookupKey}
              onChange={(e) => setLookupKey(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleLoadReportByKey(lookupKey);
              }}
              placeholder="Paste Run API Key (e.g. rl_key_dc28890135aa48e6 or rl_key_demo_001)..."
              style={{
                width: "100%",
                padding: "0.6rem 0.85rem",
                borderRadius: "6px",
                border: "1px solid #cbd5e1",
                fontSize: "0.85rem",
                fontFamily: "monospace",
                color: "#0f172a",
                backgroundColor: "#f8fafc",
                outline: "none",
              }}
            />
          </div>
          <button
            onClick={() => handleLoadReportByKey(lookupKey)}
            disabled={lookupLoading || !lookupKey.trim()}
            className="button"
            style={{ padding: "0.6rem 1.25rem", fontSize: "0.85rem" }}
          >
            {lookupLoading ? "Querying DB..." : "Load Audit"}
          </button>
        </div>

        {/* Demo Key Chips */}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem", marginTop: "0.75rem" }}>
          <span style={{ fontSize: "0.72rem", color: "#64748b", fontWeight: 600 }}>Demo Audits:</span>
          {["rl_key_demo_001", "rl_key_demo_004", "rl_key_dc28890135aa48e6"].map((keyPreset) => (
            <button
              key={keyPreset}
              onClick={() => handleLoadReportByKey(keyPreset)}
              className="button secondary"
              style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem", minHeight: "1.7rem", fontFamily: "monospace" }}
            >
              {keyPreset}
            </button>
          ))}
        </div>

        {lookupError && (
          <div style={{ marginTop: "0.75rem", padding: "0.75rem 1rem", borderRadius: "6px", backgroundColor: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", fontSize: "0.8rem" }}>
            <strong>Lookup Notice:</strong> {lookupError}
          </div>
        )}

        {justGeneratedKey && (
          <div style={{ marginTop: "0.75rem", padding: "0.75rem 1rem", borderRadius: "6px", backgroundColor: "#ecfdf5", border: "1px solid #a7f3d0", color: "#065f46", fontSize: "0.8rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong>New Unique API Key Generated:</strong> <code style={{ fontFamily: "monospace", fontWeight: 700 }}>{justGeneratedKey}</code> (Saved in PostgreSQL)
            </div>
            <button
              onClick={() => handleCopy(justGeneratedKey, "key")}
              className="button secondary"
              style={{ fontSize: "0.7rem", padding: "0.2rem 0.55rem" }}
            >
              {copiedKey ? "Copied!" : "Copy Key"}
            </button>
          </div>
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* 3. LIGHTHOUSE HERO AUDIT SCORE CARD                               */}
      {/* ----------------------------------------------------------------- */}
      {currentLighthouse ? (
        <div style={{ border: "1px solid #e2e8f0", borderRadius: "12px", padding: "1.75rem", backgroundColor: "#ffffff", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1.5rem", borderBottom: "1px solid #f1f5f9", paddingBottom: "1.5rem" }}>
            {/* Overall Score */}
            <div style={{ display: "flex", alignItems: "center", gap: "1.25rem" }}>
              {renderRadialGauge(currentLighthouse.overall_score, currentLighthouse.overall_color, 92, 8)}
              <div>
                <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "#64748b", letterSpacing: "0.06em" }}>
                  Overall RAG Score
                </div>
                <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#0f172a", letterSpacing: "-0.02em", margin: "0.15rem 0" }}>
                  Grade {currentLighthouse.overall_grade} ({currentLighthouse.overall_score}/100)
                </div>
                <div style={{ fontSize: "0.78rem", color: "#64748b" }}>
                  Composite index based on 4 performance pillars
                </div>
              </div>
            </div>

            {/* 4 Pillar Gauges */}
            <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
              {/* Latency */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.3rem", minWidth: "75px" }}>
                {renderRadialGauge(currentLighthouse.pillars.latency.score, currentLighthouse.pillars.latency.color, 68, 6)}
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#0f172a" }}>Latency</span>
                <span style={{ fontSize: "0.68rem", color: "#64748b" }}>{currentLighthouse.pillars.latency.grade}</span>
              </div>

              {/* Grounding */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.3rem", minWidth: "75px" }}>
                {renderRadialGauge(currentLighthouse.pillars.grounding.score, currentLighthouse.pillars.grounding.color, 68, 6)}
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#0f172a" }}>Grounding</span>
                <span style={{ fontSize: "0.68rem", color: "#64748b" }}>{currentLighthouse.pillars.grounding.grade}</span>
              </div>

              {/* Cost */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.3rem", minWidth: "75px" }}>
                {renderRadialGauge(currentLighthouse.pillars.cost.score, currentLighthouse.pillars.cost.color, 68, 6)}
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#0f172a" }}>Cost</span>
                <span style={{ fontSize: "0.68rem", color: "#64748b" }}>{currentLighthouse.pillars.cost.grade}</span>
              </div>

              {/* Vector Density */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.3rem", minWidth: "75px" }}>
                {renderRadialGauge(currentLighthouse.pillars.vector_density.score, currentLighthouse.pillars.vector_density.color, 68, 6)}
                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#0f172a" }}>Vector Density</span>
                <span style={{ fontSize: "0.68rem", color: "#64748b" }}>{currentLighthouse.pillars.vector_density.grade}</span>
              </div>
            </div>
          </div>

          {/* Evaluated Query Excerpt */}
          <div style={{ marginTop: "1.25rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem", flexWrap: "wrap", gap: "4px" }}>
              <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", color: "#64748b", letterSpacing: "0.06em" }}>
                Audited Query & Context
              </div>
              <div style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "0.72rem", fontWeight: 700, padding: "2px 8px", borderRadius: "4px", backgroundColor: "#f1f5f9", color: "#0f172a" }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "#3b82f6" }}></span>
                Model: {loadedReport?.summary?.model_name || loadedReport?.pipeline_spans?.[4]?.component || "Claude 3.5 Sonnet"}
              </div>
            </div>
            <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "#0f172a", padding: "0.75rem 1rem", backgroundColor: "#f8fafc", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              "{loadedReport?.query}"
            </div>
          </div>

          {/* 4 Pillar Quick Summary Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.85rem", marginTop: "1.25rem" }}>
            {/* Latency */}
            <div style={{ padding: "0.85rem", borderRadius: "8px", border: "1px solid #e2e8f0", backgroundColor: "#ffffff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>Latency & Speed</span>
                <span style={{ fontSize: "0.72rem", fontWeight: 800, color: currentLighthouse.pillars.latency.color }}>{currentLighthouse.pillars.latency.grade}</span>
              </div>
              <div style={{ fontSize: "1.25rem", fontWeight: 800, color: "#0f172a", margin: "0.2rem 0 0.1rem" }}>
                {currentLighthouse.pillars.latency.metric_label}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{currentLighthouse.pillars.latency.sub_metric}</div>
            </div>

            {/* Grounding */}
            <div style={{ padding: "0.85rem", borderRadius: "8px", border: "1px solid #e2e8f0", backgroundColor: "#ffffff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>Grounding Quality</span>
                <span style={{ fontSize: "0.72rem", fontWeight: 800, color: currentLighthouse.pillars.grounding.color }}>{currentLighthouse.pillars.grounding.grade}</span>
              </div>
              <div style={{ fontSize: "1.25rem", fontWeight: 800, color: "#0f172a", margin: "0.2rem 0 0.1rem" }}>
                {currentLighthouse.pillars.grounding.metric_label}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{currentLighthouse.pillars.grounding.sub_metric}</div>
            </div>

            {/* Cost */}
            <div style={{ padding: "0.85rem", borderRadius: "8px", border: "1px solid #e2e8f0", backgroundColor: "#ffffff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>Token Economy</span>
                <span style={{ fontSize: "0.72rem", fontWeight: 800, color: currentLighthouse.pillars.cost.color }}>{currentLighthouse.pillars.cost.grade}</span>
              </div>
              <div style={{ fontSize: "1.25rem", fontWeight: 800, color: "#0f172a", margin: "0.2rem 0 0.1rem" }}>
                {currentLighthouse.pillars.cost.metric_label}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{currentLighthouse.pillars.cost.sub_metric}</div>
            </div>

            {/* Vector Density */}
            <div style={{ padding: "0.85rem", borderRadius: "8px", border: "1px solid #e2e8f0", backgroundColor: "#ffffff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>Vector Density</span>
                <span style={{ fontSize: "0.72rem", fontWeight: 800, color: currentLighthouse.pillars.vector_density.color }}>{currentLighthouse.pillars.vector_density.grade}</span>
              </div>
              <div style={{ fontSize: "1.25rem", fontWeight: 800, color: "#0f172a", margin: "0.2rem 0 0.1rem" }}>
                {currentLighthouse.pillars.vector_density.metric_label}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>{currentLighthouse.pillars.vector_density.sub_metric}</div>
            </div>
          </div>
        </div>
      ) : null}

      {/* ----------------------------------------------------------------- */}
      {/* 4. LIGHTHOUSE OPPORTUNITIES (ESTIMATED SAVINGS)                   */}
      {/* ----------------------------------------------------------------- */}
      {currentLighthouse && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 800, color: "#0f172a", margin: 0 }}>
                Lighthouse Opportunities
              </h2>
              <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "2px 7px", borderRadius: "4px", backgroundColor: "#eff6ff", color: "#1d4ed8" }}>
                Estimated Savings
              </span>
            </div>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.82rem", color: "#64748b" }}>
              Actionable engineering optimizations to accelerate TTFT latency and cut recurring token spend.
            </p>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {currentLighthouse.opportunities.map((opp) => {
              const isExpanded = expandedOppId === opp.id;
              return (
                <div
                  key={opp.id}
                  style={{
                    border: "1px solid #e2e8f0",
                    borderRadius: "8px",
                    padding: "1.25rem",
                    backgroundColor: "#ffffff",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
                    <div>
                      <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "#0f172a", margin: 0 }}>
                        {opp.title}
                      </h3>
                      <p style={{ fontSize: "0.82rem", color: "#475569", margin: "0.3rem 0 0", lineHeight: 1.5 }}>
                        {opp.description}
                      </p>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ display: "inline-block", padding: "0.25rem 0.6rem", borderRadius: "4px", fontSize: "0.75rem", fontWeight: 800, backgroundColor: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe" }}>
                        {opp.savings_label}
                      </span>
                      <button
                        onClick={() => setExpandedOppId(isExpanded ? null : opp.id)}
                        className="button secondary"
                        style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", minHeight: "1.7rem" }}
                      >
                        {isExpanded ? "Hide Code Fix" : "View Fix"}
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div style={{ marginTop: "0.85rem", borderTop: "1px solid #f1f5f9", paddingTop: "0.85rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                        <span style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>
                          Implementation Blueprint ({opp.difficulty}):
                        </span>
                        <button
                          onClick={() => handleCopy(opp.code_snippet, "key")}
                          className="button secondary"
                          style={{ fontSize: "0.68rem", padding: "0.15rem 0.45rem", minHeight: "1.5rem" }}
                        >
                          Copy Code
                        </button>
                      </div>
                      <pre
                        style={{
                          backgroundColor: "#0f172a",
                          color: "#f8fafc",
                          padding: "0.85rem",
                          borderRadius: "6px",
                          fontSize: "0.78rem",
                          fontFamily: "monospace",
                          lineHeight: 1.5,
                          overflowX: "auto",
                          margin: 0,
                        }}
                      >
                        {opp.code_snippet}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 5. DIAGNOSTIC AUDITS CHECKLIST (PASSED / WARNING / FAILED)        */}
      {/* ----------------------------------------------------------------- */}
      {currentLighthouse && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
            <div>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 800, color: "#0f172a", margin: 0 }}>
                Diagnostic Audits Checklist
              </h2>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.82rem", color: "#64748b" }}>
                Target thresholds and compliance metrics for production SLAs.
              </p>
            </div>

            <div style={{ display: "flex", gap: "0.35rem" }}>
              <button
                onClick={() => setAuditFilter("all")}
                className="button secondary"
                style={{
                  fontSize: "0.72rem",
                  padding: "0.2rem 0.55rem",
                  minHeight: "1.7rem",
                  backgroundColor: auditFilter === "all" ? "#0f172a" : "#ffffff",
                  color: auditFilter === "all" ? "#ffffff" : "#0f172a",
                }}
              >
                All ({currentLighthouse.audits.length})
              </button>
              <button
                onClick={() => setAuditFilter("opportunities")}
                className="button secondary"
                style={{
                  fontSize: "0.72rem",
                  padding: "0.2rem 0.55rem",
                  minHeight: "1.7rem",
                  backgroundColor: auditFilter === "opportunities" ? "#0f172a" : "#ffffff",
                  color: auditFilter === "opportunities" ? "#ffffff" : "#0f172a",
                }}
              >
                Recommendations ({currentLighthouse.audits.filter((a) => a.status !== "passed").length})
              </button>
              <button
                onClick={() => setAuditFilter("passed")}
                className="button secondary"
                style={{
                  fontSize: "0.72rem",
                  padding: "0.2rem 0.55rem",
                  minHeight: "1.7rem",
                  backgroundColor: auditFilter === "passed" ? "#0f172a" : "#ffffff",
                  color: auditFilter === "passed" ? "#ffffff" : "#0f172a",
                }}
              >
                Passed ({currentLighthouse.audits.filter((a) => a.status === "passed").length})
              </button>
            </div>
          </div>

          <div style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem", backgroundColor: "#ffffff" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #e2e8f0", textAlign: "left" }}>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Audit Item</th>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Observed Value</th>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Target SLA</th>
                  </tr>
                </thead>
                <tbody>
                  {currentLighthouse.audits
                    .filter((audit) => {
                      if (auditFilter === "opportunities") return audit.status !== "passed";
                      if (auditFilter === "passed") return audit.status === "passed";
                      return true;
                    })
                    .map((audit) => {
                      const isPass = audit.status === "passed";
                      const statusColor = isPass ? "#16a34a" : "#d97706";
                      const statusIcon = isPass ? "✓" : "▲";

                      return (
                        <tr key={audit.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                          <td style={{ padding: "0.65rem 0.6rem" }}>
                            <div style={{ display: "flex", alignItems: "flex-start", gap: "6px" }}>
                              <span style={{ fontWeight: 800, color: statusColor }}>{statusIcon}</span>
                              <div>
                                <span style={{ fontWeight: 700, color: "#0f172a" }}>{audit.title}</span>
                                <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "1px" }}>{audit.description}</div>
                              </div>
                            </div>
                          </td>
                          <td style={{ padding: "0.65rem 0.6rem", fontWeight: 700, color: "#0f172a" }}>{audit.value}</td>
                          <td style={{ padding: "0.65rem 0.6rem", color: "#64748b" }}>{audit.target}</td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 6. PIPELINE WATERFALL SPANS                                       */}
      {/* ----------------------------------------------------------------- */}
      {loadedReport && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <div>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 800, color: "#0f172a", margin: 0 }}>
              Pipeline Span Latency Breakdown
            </h2>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.82rem", color: "#64748b" }}>
              Exact milliseconds and proportional latency share across each RAG pipeline span.
            </p>
          </div>

          <div style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.5rem", backgroundColor: "#ffffff" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
              {loadedReport.pipeline_spans.map((span, idx) => {
                const pct = span.pct ?? Math.round((span.latency_ms / loadedReport.total_latency_ms) * 100);
                const barColor = span.latency_ms > 1000 ? "#ef4444" : span.latency_ms > 450 ? "#f59e0b" : "#3b82f6";

                return (
                  <div key={idx} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem", fontWeight: 600 }}>
                      <span style={{ color: "#0f172a" }}>
                        {span.name} <span style={{ fontWeight: 400, color: "#64748b" }}>({span.component})</span>
                      </span>
                      <span style={{ color: "#0f172a" }}>
                        {span.latency_ms} ms <span style={{ color: "#64748b", fontWeight: 400 }}>({pct}%)</span>
                      </span>
                    </div>
                    <div style={{ height: "8px", width: "100%", backgroundColor: "#f1f5f9", borderRadius: "4px", overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${Math.min(Math.max(pct, 2), 100)}%`, backgroundColor: barColor, borderRadius: "4px" }}></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 7. RETRIEVED CHUNKS GROUNDING EXPLORER (POSTGRESQL)               */}
      {/* ----------------------------------------------------------------- */}
      {loadedReport && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <div>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 800, color: "#0f172a", margin: 0 }}>
              Retrieved Document Chunks (Stored in PostgreSQL)
            </h2>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.82rem", color: "#64748b" }}>
              Cosine similarity rankings and citation grounding for this exact execution run.
            </p>
          </div>

          <div style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.25rem", backgroundColor: "#ffffff" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #e2e8f0", textAlign: "left" }}>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Chunk ID</th>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Document Source</th>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Tokens</th>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Cosine Similarity</th>
                    <th style={{ padding: "0.6rem", color: "#64748b", fontWeight: 700 }}>Grounding Status</th>
                  </tr>
                </thead>
                <tbody>
                  {loadedReport.chunks.map((chk, i) => {
                    const sim = chk.similarity;
                    const isHigh = sim >= 0.70;
                    const isMed = sim >= 0.50 && sim < 0.70;
                    const badgeBg = isHigh ? "#ecfdf5" : isMed ? "#fffbeb" : "#fef2f2";
                    const badgeColor = isHigh ? "#065f46" : isMed ? "#92400e" : "#991b1b";
                    const badgeLabel = isHigh ? "Strong Grounding" : isMed ? "Moderate" : "Noise / Prune";

                    return (
                      <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "0.6rem", fontFamily: "monospace", color: "#64748b" }}>{chk.chunk_id}</td>
                        <td style={{ padding: "0.6rem", fontWeight: 600, color: "#0f172a" }}>{chk.doc}</td>
                        <td style={{ padding: "0.6rem", color: "#64748b" }}>{chk.size_tokens} tokens</td>
                        <td style={{ padding: "0.6rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <div style={{ width: "60px", height: "6px", backgroundColor: "#f1f5f9", borderRadius: "3px", overflow: "hidden" }}>
                              <div style={{ width: `${Math.round(sim * 100)}%`, height: "100%", backgroundColor: isHigh ? "#10b981" : isMed ? "#f59e0b" : "#ef4444" }}></div>
                            </div>
                            <span style={{ fontWeight: 700, color: "#0f172a" }}>{sim.toFixed(2)}</span>
                          </div>
                        </td>
                        <td style={{ padding: "0.6rem" }}>
                          <span style={{ display: "inline-block", padding: "2px 8px", borderRadius: "4px", fontSize: "0.72rem", fontWeight: 600, backgroundColor: badgeBg, color: badgeColor }}>
                            {badgeLabel}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* 8. 1-CLICK INTERACTIVE TEST & AUDIT BAR                           */}
      {/* ----------------------------------------------------------------- */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <div>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 800, color: "#0f172a", margin: 0 }}>
            Run New RAG Audit
          </h2>
          <p style={{ margin: "0.2rem 0 0", fontSize: "0.82rem", color: "#64748b" }}>
            Submit any test question. Generates a <strong>fresh unique API key</strong>, computes the Lighthouse audit, and persists to PostgreSQL.
          </p>
        </div>

        <div style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.5rem", backgroundColor: "#ffffff" }}>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.85rem", flexWrap: "wrap" }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Enter question to audit..."
              style={{
                flex: 1,
                minWidth: "260px",
                padding: "0.65rem 0.85rem",
                borderRadius: "6px",
                border: "1px solid #cbd5e1",
                fontSize: "0.88rem",
                color: "#0f172a",
                backgroundColor: "#ffffff",
                outline: "none",
              }}
            />
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={{
                padding: "0.65rem 0.85rem",
                borderRadius: "6px",
                border: "1px solid #cbd5e1",
                fontSize: "0.85rem",
                color: "#0f172a",
                backgroundColor: "#f8fafc",
                fontWeight: 600,
                outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="claude-3-5-sonnet">Claude 3.5 Sonnet (Anthropic)</option>
              <option value="gpt-4o">GPT-4o (OpenAI)</option>
              <option value="gpt-4o-mini">GPT-4o Mini (Ultra-Fast)</option>
              <option value="gemini-1.5-pro">Gemini 1.5 Pro (Google)</option>
              <option value="llama-3.1-70b">Llama 3.1 70B (Groq)</option>
            </select>
            <button
              onClick={() => handleExecuteNewRun()}
              disabled={simulating}
              className="button"
              style={{ padding: "0.65rem 1.35rem", fontSize: "0.85rem" }}
            >
              {simulating ? "Auditing Pipeline..." : "Audit & Store in PostgreSQL"}
            </button>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.72rem", color: "#64748b", fontWeight: 600 }}>Quick Presets:</span>
            {[
              "What is our enterprise refund policy for annual licenses?",
              "How do I configure SSO SAML with Okta in Kubernetes?",
              "Explain the rate limiting algorithm for tiered API keys.",
              "Can I deploy AgentLens in an air-gapped HIPAA environment?",
            ].map((q, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setSearchQuery(q);
                  handleExecuteNewRun(q);
                }}
                className="button secondary"
                style={{ fontSize: "0.72rem", padding: "0.2rem 0.55rem", minHeight: "1.7rem" }}
              >
                {q.length > 35 ? q.substring(0, 35) + "..." : q}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* 9. CONNECT IN 60 SECONDS (SDK & AGENT)                            */}
      {/* ----------------------------------------------------------------- */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <div>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 800, color: "#0f172a", margin: 0 }}>
            Connect Your Application in 60 Seconds
          </h2>
          <p style={{ margin: "0.2rem 0 0", fontSize: "0.82rem", color: "#64748b" }}>
            Production user traffic is never intercepted. Only asynchronous telemetry is transmitted out-of-band.
          </p>
        </div>

        <div style={{ border: "1px solid #e2e8f0", borderRadius: "10px", padding: "1.5rem", backgroundColor: "#ffffff" }}>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
            <button
              onClick={() => setConnectMode("sdk")}
              className="button secondary"
              style={{
                fontSize: "0.8rem",
                backgroundColor: connectMode === "sdk" ? "#0f172a" : "#ffffff",
                color: connectMode === "sdk" ? "#ffffff" : "#0f172a",
                borderColor: connectMode === "sdk" ? "#0f172a" : "#cbd5e1",
              }}
            >
              Option 1: Python SDK (3 lines)
            </button>
            <button
              onClick={() => setConnectMode("agent")}
              className="button secondary"
              style={{
                fontSize: "0.8rem",
                backgroundColor: connectMode === "agent" ? "#0f172a" : "#ffffff",
                color: connectMode === "agent" ? "#ffffff" : "#0f172a",
                borderColor: connectMode === "agent" ? "#0f172a" : "#cbd5e1",
              }}
            >
              Option 2: Interactive Terminal CLI
            </button>
          </div>

          {connectMode === "sdk" && (
            <div>
              <pre
                style={{
                  backgroundColor: "#0f172a",
                  color: "#f8fafc",
                  padding: "1rem",
                  borderRadius: "6px",
                  fontSize: "0.82rem",
                  lineHeight: 1.5,
                  fontFamily: "monospace",
                  overflowX: "auto",
                  margin: 0,
                }}
              >
{`# 1. Install RagLens SDK
pip install raglens

# 2. Add to your application startup
from raglens import RagLens

raglens = RagLens(api_key="rl_live_key", project="support-copilot")
raglens.start()  # Non-blocking background telemetry thread`}
              </pre>
            </div>
          )}

          {connectMode === "agent" && (
            <div>
              <pre
                style={{
                  backgroundColor: "#0f172a",
                  color: "#f8fafc",
                  padding: "1rem",
                  borderRadius: "6px",
                  fontSize: "0.82rem",
                  lineHeight: 1.5,
                  fontFamily: "monospace",
                  overflowX: "auto",
                  margin: 0,
                }}
              >
{`# Run interactive Lighthouse performance audit in terminal:
python -m agentlens.cli run

# Or run non-interactively in automated CI/CD pipeline:
python -m agentlens.cli run --non-interactive`}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
