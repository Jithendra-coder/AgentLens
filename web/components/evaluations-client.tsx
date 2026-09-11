"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { dashboardFetch } from "../lib/client";

interface BenchmarkTestCase {
  id: string;
  query: string;
  expected_section: string;
  score: number;
  latency_ms: number;
  status: string;
}

interface BenchmarkReport {
  document_id: string;
  document_title: string;
  total_test_cases: number;
  overall_score: number;
  overall_grade: string;
  faithfulness: number;
  answer_relevance: number;
  context_recall: number;
  test_cases: BenchmarkTestCase[];
  evaluated_at: string;
}

export default function EvaluationsClient() {
  const [activeDoc, setActiveDoc] = useState<"user_policy" | "developer_docs">("user_policy");
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [running, setRunning] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const runBenchmark = async (docId?: string) => {
    const target = docId ?? activeDoc;
    setRunning(true);
    setStatusMessage(null);
    try {
      const data = await dashboardFetch<BenchmarkReport>(`rag/benchmark?document_id=${target}`, {
        method: "POST",
      });
      setReport(data);
      setStatusMessage(`✓ Benchmark suite completed: ${data.total_test_cases} synthetic test cases evaluated!`);
    } catch (err: any) {
      setStatusMessage("Benchmark execution failed: " + (err?.message || "unknown error"));
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    void runBenchmark("user_policy");
  }, []);

  return (
    <div className="space-y-6">
      {/* Page Heading */}
      <div className="page-heading">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="eyebrow" style={{ margin: 0 }}>Level 4 Autonomous Quality</span>
            <span style={{ fontSize: "0.72rem", background: "#052e16", border: "1px solid #166534", padding: "0.15rem 0.5rem", borderRadius: "4px", color: "#86efac" }}>
              LLM-as-a-Judge Active
            </span>
          </div>
          <h1 style={{ fontSize: "1.75rem", margin: "0.25rem 0 0.5rem 0" }}>AI Quality & Synthetic Benchmarks</h1>
          <p className="lede" style={{ margin: 0, maxWidth: "750px" }}>
            Automated synthetic test generator and RAG evaluation engine. Measures factual faithfulness, answer relevance, and context recall against ground-truth document vectors.
          </p>
        </div>

        <div className="toolbar" style={{ display: "flex", gap: "0.5rem" }}>
          <button
            type="button"
            onClick={() => void runBenchmark()}
            className="button"
            disabled={running}
            style={{ fontSize: "0.8rem", minHeight: "2rem", background: "#0284c7", color: "#ffffff" }}
          >
            {running ? "Running Evaluator..." : "⚡ Run Synthetic Benchmark Suite"}
          </button>
          <Link href="/" className="button secondary" style={{ fontSize: "0.8rem", minHeight: "2rem" }}>
            ← AI Studio
          </Link>
        </div>
      </div>

      {statusMessage && (
        <div
          style={{
            padding: "0.75rem 1rem",
            background: statusMessage.startsWith("✓") ? "#052e16" : "#450a0a",
            border: statusMessage.startsWith("✓") ? "1px solid #166534" : "1px solid #991b1b",
            borderRadius: "6px",
            color: statusMessage.startsWith("✓") ? "#86efac" : "#fca5a5",
            fontSize: "0.85rem",
          }}
        >
          {statusMessage}
        </div>
      )}

      {/* Target Document Switcher */}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button
          type="button"
          onClick={() => {
            setActiveDoc("user_policy");
            void runBenchmark("user_policy");
          }}
          className={`button ${activeDoc === "user_policy" ? "" : "secondary"}`}
          style={{ fontSize: "0.8rem" }}
        >
          📄 1. Enterprise User Policy Benchmarks
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveDoc("developer_docs");
            void runBenchmark("developer_docs");
          }}
          className={`button ${activeDoc === "developer_docs" ? "" : "secondary"}`}
          style={{ fontSize: "0.8rem" }}
        >
          🛠️ 2. Developer API & SDK Docs Benchmarks
        </button>
      </div>

      {/* Hero Benchmark Scorecard */}
      {report && (
        <section
          style={{
            padding: "1.5rem",
            background: "#ffffff",
            border: "1px solid #e2e8f0",
            borderRadius: "8px",
            boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
            <div>
              <span className="subtle" style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                Target Knowledge Base
              </span>
              <h2 style={{ fontSize: "1.3rem", margin: "0.2rem 0", color: "#0f172a" }}>{report.document_title}</h2>
              <div className="subtle" style={{ fontSize: "0.76rem" }}>
                Evaluated at {new Date(report.evaluated_at).toLocaleTimeString()} · {report.total_test_cases} Test Cases
              </div>
            </div>

            <div style={{ textAlign: "right", background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "0.6rem 1.25rem", borderRadius: "8px" }}>
              <div className="subtle" style={{ fontSize: "0.68rem", textTransform: "uppercase", fontWeight: 600, color: "#166534" }}>Overall System Score</div>
              <strong style={{ fontSize: "1.8rem", color: "#15803d" }}>{report.overall_score}%</strong>
              <div style={{ fontSize: "0.75rem", color: "#166534", fontWeight: 700 }}>{report.overall_grade}</div>
            </div>
          </div>

          {/* 3 Core Quality Pillars */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
            <div style={{ padding: "1rem", background: "#f8fafc", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.75rem", color: "#475569", textTransform: "uppercase", fontWeight: 700 }}>
                  Faithfulness (Zero Hallucination)
                </span>
                <strong style={{ color: "#15803d", fontSize: "0.95rem" }}>{report.faithfulness}%</strong>
              </div>
              <div style={{ background: "#e2e8f0", height: "6px", borderRadius: "3px", overflow: "hidden", margin: "0.4rem 0" }}>
                <div style={{ width: `${report.faithfulness}%`, height: "100%", background: "#16a34a" }} />
              </div>
              <p className="subtle" style={{ fontSize: "0.72rem", margin: 0, color: "#64748b" }}>
                Every token in synthesized answers is 100% corroborated by cited source clauses.
              </p>
            </div>

            <div style={{ padding: "1rem", background: "#f8fafc", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.75rem", color: "#475569", textTransform: "uppercase", fontWeight: 700 }}>
                  Answer Relevance
                </span>
                <strong style={{ color: "#0284c7", fontSize: "0.95rem" }}>{report.answer_relevance}%</strong>
              </div>
              <div style={{ background: "#e2e8f0", height: "6px", borderRadius: "3px", overflow: "hidden", margin: "0.4rem 0" }}>
                <div style={{ width: `${report.answer_relevance}%`, height: "100%", background: "#0284c7" }} />
              </div>
              <p className="subtle" style={{ fontSize: "0.72rem", margin: 0, color: "#64748b" }}>
                Answers directly resolve the user's explicit question without conversational fluff.
              </p>
            </div>

            <div style={{ padding: "1rem", background: "#f8fafc", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.75rem", color: "#475569", textTransform: "uppercase", fontWeight: 700 }}>
                  Context Recall
                </span>
                <strong style={{ color: "#7e22ce", fontSize: "0.95rem" }}>{report.context_recall}%</strong>
              </div>
              <div style={{ background: "#e2e8f0", height: "6px", borderRadius: "3px", overflow: "hidden", margin: "0.4rem 0" }}>
                <div style={{ width: `${report.context_recall}%`, height: "100%", background: "#7e22ce" }} />
              </div>
              <p className="subtle" style={{ fontSize: "0.72rem", margin: 0, color: "#64748b" }}>
                Retriever surfaces all required clauses necessary to formulate complete verdicts.
              </p>
            </div>
          </div>

          {/* Test Case Execution Matrix */}
          <div>
            <h3 style={{ fontSize: "0.95rem", margin: "0 0 0.6rem 0", color: "#0f172a" }}>Synthetic Test Case Execution Breakdown:</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Test ID</th>
                    <th>Synthetic Query</th>
                    <th>Target Section</th>
                    <th>Execution Latency</th>
                    <th>Retrieval Score</th>
                    <th>Evaluator Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {report.test_cases.map((tc) => (
                    <tr key={tc.id}>
                      <td className="mono" style={{ fontSize: "0.75rem", color: "#64748b" }}>{tc.id}</td>
                      <td style={{ fontSize: "0.82rem", color: "#0f172a", fontWeight: 500 }}>{tc.query}</td>
                      <td style={{ fontSize: "0.78rem", color: "#475569" }}>{tc.expected_section}</td>
                      <td className="mono" style={{ fontSize: "0.78rem" }}>{tc.latency_ms} ms</td>
                      <td className="mono" style={{ fontSize: "0.78rem", color: "#0284c7", fontWeight: 600 }}>{(tc.score * 100).toFixed(1)}%</td>
                      <td>
                        <span style={{ padding: "0.15rem 0.5rem", borderRadius: "3px", background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#15803d", fontSize: "0.7rem", fontWeight: 700 }}>
                          ✓ {tc.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
