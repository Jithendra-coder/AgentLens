"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { dashboardFetch } from "../lib/client";

interface SectionChunk {
  id: string;
  title: string;
  section: string;
  summary: string;
  char_count: number;
  keywords: string[];
}

interface DocumentData {
  document_key: string;
  document_name: string;
  document_id: string;
  title: string;
  version: string;
  badge: string;
  description: string;
  full_text: string;
  sections: SectionChunk[];
}

interface TestResult {
  query: string;
  verdict: string;
  answer: string;
  latency_ms: number;
  tokens: number;
  document_name?: string;
}

interface AuditFinding {
  id: string;
  severity: "HIGH" | "MEDIUM" | "INFO";
  category: string;
  title: string;
  sections_involved: string[];
  description: string;
  recommendation: string;
}

interface AuditReport {
  document_id: string;
  document_name: string;
  title: string;
  health_score: number;
  findings_count: number;
  findings: AuditFinding[];
  audited_at: string;
  status: string;
}

export default function KnowledgeClient() {
  const [activeDocKey, setActiveDocKey] = useState<string>("user_policy");
  const [docList, setDocList] = useState<any[]>([]);
  const [doc, setDoc] = useState<DocumentData | null>(null);
  const [editText, setEditText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [testQuery, setTestQuery] = useState("Can a user get a refund after 45 days?");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadSlug, setUploadSlug] = useState("");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadBadge, setUploadBadge] = useState("Enterprise Spec");
  const [uploadContent, setUploadContent] = useState("");
  const [uploading, setUploading] = useState(false);

  // Audit state
  const [auditReport, setAuditReport] = useState<AuditReport | null>(null);
  const [auditing, setAuditing] = useState(false);

  const loadDocuments = async () => {
    try {
      const list = await dashboardFetch<any[]>("rag/documents");
      setDocList(list);
    } catch {
      // fallback
    }
  };

  const loadDoc = async (docKey: string) => {
    setLoading(true);
    setSaveStatus(null);
    setTestResult(null);
    setAuditReport(null);
    try {
      const data = await dashboardFetch<DocumentData>(`rag/document?document_id=${docKey}`);
      setDoc(data);
      setEditText(data.full_text);
      if (docKey === "developer_docs") {
        setTestQuery("How do I authenticate API requests in Python?");
      } else {
        setTestQuery("Can a user get a refund after 45 days?");
      }
    } catch (err: any) {
      setSaveStatus("Failed to load document: " + (err?.message || "network error"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDocuments();
    void loadDoc(activeDocKey);
  }, [activeDocKey]);

  const handleSave = async () => {
    setSaving(true);
    setSaveStatus(null);
    try {
      await dashboardFetch("rag/document", {
        method: "PUT",
        body: { text: editText, document_id: activeDocKey },
      });
      setSaveStatus(`✓ '${doc?.document_name}' updated and re-indexed into knowledge base!`);
      await loadDoc(activeDocKey);
      await loadDocuments();
    } catch (err: any) {
      setSaveStatus("Error saving document: " + (err?.message || "unknown"));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm(`Reset '${doc?.document_name}' back to factory defaults?`)) return;
    setSaving(true);
    try {
      await dashboardFetch(`rag/reset?document_id=${activeDocKey}`, { method: "POST" });
      setSaveStatus(`✓ '${doc?.document_name}' reset to factory defaults.`);
      await loadDoc(activeDocKey);
      await loadDocuments();
    } catch (err: any) {
      setSaveStatus("Error resetting document: " + (err?.message || "unknown"));
    } finally {
      setSaving(false);
    }
  };

  const runTestQuery = async () => {
    setTesting(true);
    try {
      const res = await dashboardFetch<TestResult>("rag/query", {
        method: "POST",
        body: { query: testQuery, top_k: 2, document_id: activeDocKey },
      });
      setTestResult(res);
    } catch (err: any) {
      setSaveStatus("Test query failed: " + (err?.message || "unknown"));
    } finally {
      setTesting(false);
    }
  };

  const runAudit = async () => {
    setAuditing(true);
    try {
      const rep = await dashboardFetch<AuditReport>(`rag/audit?document_id=${activeDocKey}`, {
        method: "POST",
      });
      setAuditReport(rep);
    } catch (err: any) {
      setSaveStatus("Audit failed: " + (err?.message || "unknown"));
    } finally {
      setAuditing(false);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadSlug || !uploadTitle || !uploadContent) {
      alert("Please fill in document slug, title, and content.");
      return;
    }
    setUploading(true);
    try {
      await dashboardFetch("rag/upload", {
        method: "POST",
        body: {
          doc_id: uploadSlug,
          title: uploadTitle,
          badge: uploadBadge,
          content: uploadContent,
        },
      });
      setShowUploadModal(false);
      setSaveStatus(`✓ New document '${uploadTitle}' uploaded and indexed into knowledge base!`);
      await loadDocuments();
      setActiveDocKey(uploadSlug.toLowerCase().replace(/[^\w]/g, "_"));
    } catch (err: any) {
      alert("Upload failed: " + (err?.message || "unknown"));
    } finally {
      setUploading(false);
    }
  };

  const getSeverityBadge = (severity: string) => {
    if (severity === "HIGH") {
      return { background: "#fef2f2", border: "1px solid #fecaca", color: "#b91c1c" };
    }
    if (severity === "MEDIUM") {
      return { background: "#fffbeb", border: "1px solid #fde68a", color: "#b45309" };
    }
    return { background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#15803d" };
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="page-heading">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="eyebrow" style={{ margin: 0 }}>Level 4 Knowledge Architecture</span>
            <span style={{ fontSize: "0.72rem", background: "#f1f5f9", border: "1px solid #e2e8f0", padding: "0.15rem 0.5rem", borderRadius: "4px", color: "#475569", fontWeight: 600 }}>
              Active Chunks: {doc?.sections?.length || 0}
            </span>
          </div>
          <h1 style={{ fontSize: "1.75rem", margin: "0.25rem 0 0.5rem 0" }}>Knowledge Base & Rule Auditor</h1>
          <p className="lede" style={{ margin: 0, maxWidth: "750px" }}>
            Edit rules, upload custom documents, and run automated AI compliance audits to detect policy loopholes and contradictions.
          </p>
        </div>

        <div className="toolbar" style={{ display: "flex", gap: "0.5rem" }}>
          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            className="button secondary"
            style={{ fontSize: "0.8rem", minHeight: "2rem" }}
          >
            ⬆️ Upload Document
          </button>
          <button
            type="button"
            onClick={runAudit}
            className="button"
            style={{ fontSize: "0.8rem", minHeight: "2rem", background: "#7e22ce", color: "#ffffff", borderColor: "#7e22ce" }}
            disabled={auditing}
          >
            {auditing ? "Scanning..." : "🔍 Run Policy Conflict Audit"}
          </button>
          <Link href="/" className="button secondary" style={{ fontSize: "0.8rem", minHeight: "2rem" }}>
            ← AI Studio
          </Link>
        </div>
      </div>

      {/* DOCUMENT TABS */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "0.5rem",
          padding: "0.75rem 1rem",
          background: "#ffffff",
          border: "1px solid #e2e8f0",
          borderRadius: "8px",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}
      >
        <span style={{ fontSize: "0.75rem", color: "#64748b", textTransform: "uppercase", fontWeight: 700, marginRight: "0.25rem" }}>
          Knowledge Base:
        </span>

        {docList.map((d) => {
          const isActive = activeDocKey === d.id;
          return (
            <button
              key={d.id}
              type="button"
              onClick={() => setActiveDocKey(d.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                padding: "0.4rem 0.8rem",
                borderRadius: "5px",
                border: isActive ? "1px solid #0f172a" : "1px solid #e2e8f0",
                background: isActive ? "#0f172a" : "#f8fafc",
                color: isActive ? "#ffffff" : "#475569",
                fontWeight: isActive ? 700 : 500,
                fontSize: "0.8rem",
                cursor: "pointer",
              }}
            >
              <span>{d.title}</span>
              <span style={{ fontSize: "0.65rem", background: isActive ? "#1e293b" : "#e2e8f0", padding: "0.1rem 0.35rem", borderRadius: "3px", color: isActive ? "#ffffff" : "#475569" }}>
                {d.chunks_count} chunks
              </span>
            </button>
          );
        })}
      </div>

      {saveStatus && (
        <div
          style={{
            padding: "0.75rem 1rem",
            background: saveStatus.startsWith("✓") ? "#f0fdf4" : "#fef2f2",
            border: saveStatus.startsWith("✓") ? "1px solid #bbf7d0" : "1px solid #fecaca",
            borderRadius: "6px",
            color: saveStatus.startsWith("✓") ? "#15803d" : "#b91c1c",
            fontSize: "0.85rem",
            fontWeight: 500,
          }}
        >
          {saveStatus}
        </div>
      )}

      {/* POLICY CONFLICT AUDIT FINDINGS PANEL */}
      {auditReport && (
        <section
          style={{
            padding: "1.25rem",
            background: "#faf5ff",
            border: "1px solid #e9d5ff",
            borderRadius: "8px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <strong style={{ fontSize: "1.05rem", color: "#0f172a" }}>
                  Automated Policy Conflict & Loophole Audit: {auditReport.title}
                </strong>
                <span style={{ fontSize: "0.72rem", background: "#f3e8ff", color: "#7e22ce", padding: "0.15rem 0.5rem", borderRadius: "4px", border: "1px solid #d8b4fe", fontWeight: 600 }}>
                  Audited: {new Date(auditReport.audited_at).toLocaleTimeString()}
                </span>
              </div>
              <p className="subtle" style={{ fontSize: "0.8rem", margin: "0.25rem 0 0 0", color: "#475569" }}>
                Scanned {doc?.sections?.length} clauses for cross-clause contradictions, statutory ambiguities, and compliance gaps.
              </p>
            </div>

            <div style={{ textAlign: "right" }}>
              <div className="subtle" style={{ fontSize: "0.68rem", textTransform: "uppercase", fontWeight: 600 }}>Compliance Health</div>
              <strong style={{ fontSize: "1.5rem", color: auditReport.health_score > 90 ? "#16a34a" : "#d97706" }}>
                {auditReport.health_score} / 100
              </strong>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem" }}>
            {auditReport.findings.map((f) => (
              <div
                key={f.id}
                style={{
                  padding: "0.85rem",
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "6px",
                  boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.3rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: "3px", fontWeight: 700, ...getSeverityBadge(f.severity) }}>
                      {f.severity}
                    </span>
                    <strong style={{ fontSize: "0.88rem", color: "#0f172a" }}>{f.title}</strong>
                    <span className="mono" style={{ fontSize: "0.7rem", color: "#64748b" }}>{f.id}</span>
                  </div>
                  <span className="subtle" style={{ fontSize: "0.72rem" }}>{f.category}</span>
                </div>

                <div className="subtle" style={{ fontSize: "0.74rem", marginBottom: "0.4rem" }}>
                  Involved: {f.sections_involved.join(" & ")}
                </div>

                <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.82rem", color: "#334155", lineHeight: "1.5" }}>
                  {f.description}
                </p>

                <div style={{ padding: "0.5rem 0.75rem", background: "#f0fdf4", borderRadius: "4px", fontSize: "0.76rem", border: "1px solid #bbf7d0" }}>
                  <strong style={{ color: "#16a34a" }}>Recommended Legal Patch: </strong>
                  <span style={{ color: "#166534" }}>{f.recommendation}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Editor & Chunks Split */}
      <div className="grid two" style={{ alignItems: "start", gap: "1.5rem" }}>
        {/* Left: Document Text Editor */}
        <div>
          <section className="card section">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
              <div>
                <h2 style={{ fontSize: "1.1rem", margin: 0 }}>{doc?.title || "Document Markdown"}</h2>
                <div className="subtle" style={{ fontSize: "0.74rem" }}>
                  {doc?.document_name} · {doc?.version} · {editText.length} characters
                </div>
              </div>
              <div style={{ display: "flex", gap: "0.4rem" }}>
                <button
                  type="button"
                  onClick={handleReset}
                  className="button secondary"
                  style={{ fontSize: "0.74rem", minHeight: "1.9rem", padding: "0.2rem 0.6rem" }}
                  disabled={saving || loading}
                >
                  Reset Default
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  className="button"
                  style={{ fontSize: "0.74rem", minHeight: "1.9rem", padding: "0.2rem 0.8rem" }}
                  disabled={saving || loading}
                >
                  {saving ? "Saving..." : "Save & Re-Index"}
                </button>
              </div>
            </div>

            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={22}
              style={{
                width: "100%",
                background: "#ffffff",
                border: "1px solid #cbd5e1",
                borderRadius: "6px",
                padding: "0.75rem",
                color: "#0f172a",
                fontFamily: "monospace",
                fontSize: "0.82rem",
                lineHeight: "1.55",
                resize: "vertical",
              }}
              disabled={loading || saving}
            />

            {/* Quick Test Bar directly below editor */}
            <div style={{ marginTop: "1rem", padding: "0.85rem", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "6px" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: "0.4rem" }}>
                ⚡ Test Rule Verification in Real-Time ({doc?.document_name}):
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <input
                  type="text"
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                  className="control"
                  style={{ flex: 1, color: "#0f172a", backgroundColor: "#ffffff", fontSize: "0.82rem" }}
                />
                <button
                  type="button"
                  onClick={runTestQuery}
                  className="button"
                  style={{ minHeight: "2.1rem", fontSize: "0.76rem", whiteSpace: "nowrap" }}
                  disabled={testing}
                >
                  {testing ? "Testing..." : "Test Rule →"}
                </button>
              </div>

              {testResult && (
                <div style={{ marginTop: "0.75rem", padding: "0.85rem", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "6px", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                    <span style={{ fontSize: "0.72rem", color: "#64748b", textTransform: "uppercase", fontWeight: 700 }}>
                      Live Verdict:
                    </span>
                    <span style={{ fontSize: "0.75rem", fontWeight: 700, color: testResult.verdict.includes("NON") ? "#b91c1c" : "#15803d" }}>
                      {testResult.verdict}
                    </span>
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      fontSize: "0.82rem",
                      color: "#0f172a",
                      lineHeight: "1.5",
                      fontFamily: testResult.answer.includes("client =") ? "monospace" : "inherit",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {testResult.answer}
                  </pre>
                </div>
              )}
            </div>
          </section>
        </div>

        {/* Right: Indexed Chunks Inspector */}
        <div>
          <section className="card section" style={{ maxHeight: "780px", overflowY: "auto" }}>
            <h2 style={{ fontSize: "1.1rem", margin: "0 0 0.35rem 0", color: "#0f172a" }}>Indexed Chunks ({doc?.sections?.length || 0})</h2>
            <p className="subtle" style={{ fontSize: "0.78rem", marginBottom: "1rem" }}>
              How AgentLens splits <code>{doc?.document_name}</code> into semantic memory vectors:
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              {doc?.sections?.map((sec) => (
                <div
                  key={sec.id}
                  style={{
                    padding: "0.75rem 0.85rem",
                    background: "#ffffff",
                    border: "1px solid #e2e8f0",
                    borderRadius: "6px",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                    <strong style={{ fontSize: "0.85rem", color: "#0f172a" }}>{sec.title}</strong>
                    <span className="mono" style={{ fontSize: "0.7rem", color: "#64748b" }}>{sec.id}</span>
                  </div>
                  <p className="subtle" style={{ fontSize: "0.76rem", margin: "0 0 0.4rem 0", color: "#475569" }}>
                    {sec.summary}
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                    {sec.keywords?.map((k, i) => (
                      <span
                        key={i}
                        style={{
                          fontSize: "0.65rem",
                          background: "#f1f5f9",
                          border: "1px solid #e2e8f0",
                          padding: "0.1rem 0.35rem",
                          borderRadius: "3px",
                          color: "#475569",
                          fontWeight: 500,
                        }}
                      >
                        {k}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      {/* UPLOAD DOCUMENT MODAL */}
      {showUploadModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(15, 23, 42, 0.45)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              width: "560px",
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: "10px",
              padding: "1.5rem",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ margin: 0, fontSize: "1.1rem", color: "#0f172a" }}>Upload Custom Knowledge Base</h3>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="button secondary"
                style={{ minHeight: "1.8rem", padding: "0.1rem 0.5rem" }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUploadSubmit} className="space-y-3">
              <div>
                <label className="subtle" style={{ fontSize: "0.75rem", display: "block", marginBottom: "0.2rem" }}>
                  Document Slug (e.g. employee_handbook)
                </label>
                <input
                  type="text"
                  value={uploadSlug}
                  onChange={(e) => setUploadSlug(e.target.value)}
                  placeholder="employee_handbook"
                  className="control"
                  style={{ width: "100%", color: "#000000", backgroundColor: "#ffffff" }}
                  required
                />
              </div>

              <div>
                <label className="subtle" style={{ fontSize: "0.75rem", display: "block", marginBottom: "0.2rem" }}>
                  Display Title (e.g. 2026 Employee Handbook)
                </label>
                <input
                  type="text"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder="2026 Employee Handbook"
                  className="control"
                  style={{ width: "100%", color: "#000000", backgroundColor: "#ffffff" }}
                  required
                />
              </div>

              <div>
                <label className="subtle" style={{ fontSize: "0.75rem", display: "block", marginBottom: "0.2rem" }}>
                  Category Badge
                </label>
                <input
                  type="text"
                  value={uploadBadge}
                  onChange={(e) => setUploadBadge(e.target.value)}
                  placeholder="HR & Operations"
                  className="control"
                  style={{ width: "100%", color: "#000000", backgroundColor: "#ffffff" }}
                />
              </div>

              <div>
                <label className="subtle" style={{ fontSize: "0.75rem", display: "block", marginBottom: "0.2rem" }}>
                  Document Markdown Content
                </label>
                <textarea
                  rows={8}
                  value={uploadContent}
                  onChange={(e) => setUploadContent(e.target.value)}
                  placeholder="# Employee Handbook&#10;&#10;## Section 1: PTO and Remote Work Policy&#10;Employees receive 25 days PTO annually..."
                  className="control"
                  style={{ width: "100%", color: "#000000", backgroundColor: "#ffffff", fontFamily: "monospace", fontSize: "0.8rem" }}
                  required
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1rem" }}>
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="button secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="button"
                  disabled={uploading}
                >
                  {uploading ? "Indexing..." : "Upload & Re-Index →"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
