"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { dashboardFetch, formatDate } from "../lib/client";
import type { EvaluationResultDetail } from "../lib/types";
import { Badge, EmptyState, ErrorState, JsonViewer, LoadingState } from "./ui";

export default function EvaluationDetailClient({ resultId }: { resultId: string }) {
  const [result, setResult] = useState<EvaluationResultDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setResult(await dashboardFetch<EvaluationResultDetail>(`evaluation-results/${resultId}`)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load evaluation result."); }
    finally { setLoading(false); }
  }, [resultId]);
  useEffect(() => { void load(); }, [load]);
  if (loading && !result) return <LoadingState label="Loading immutable evaluation result…" />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!result) return <EmptyState label="Evaluation result not found." />;
  return <>
    <div className="page-heading"><div><p className="eyebrow">Evaluation detail</p><h1>{result.evaluation_type}</h1><p className="lede mono">{result.result_id}</p></div><div className="toolbar"><Badge value={result.result_status} /><button className="button secondary" onClick={() => void load()} disabled={loading}>Refresh</button></div></div>
    <section className="card"><dl className="kvs"><dt>Trace</dt><dd><Link className="link mono" href={`/traces/${result.trace_id}`}>{result.trace_id}</Link></dd><dt>Evaluator</dt><dd>{result.evaluator_name} · {result.evaluator_version}</dd><dt>Mode</dt><dd><Badge value={result.evaluation_mode} /></dd><dt>Created</dt><dd>{formatDate(result.created_at)}</dd><dt>Trace fingerprint</dt><dd className="mono">{result.trace_fingerprint}</dd><dt>Config fingerprint</dt><dd className="mono">{result.config_fingerprint}</dd></dl></section>
    <div className="grid two section"><section className="card"><h2>Metrics</h2><JsonViewer value={result.metrics} /></section><section className="card"><h2>Normalized configuration</h2><JsonViewer value={result.config} /></section></div>
    <div className="grid two section"><section className="card"><h2>Findings</h2>{result.findings.length ? <div className="grid">{result.findings.map((finding, index) => <div className="card" key={`${finding.code}-${index}`}><div className="split"><strong>{finding.code}</strong><Badge value={finding.severity} /></div><p>{finding.message}</p><JsonViewer value={finding.evidence} /></div>)}</div> : <EmptyState label="No findings recorded." />}</section><section className="card"><h2>Evidence</h2><JsonViewer value={result.evidence} /></section></div>
    <section className="card section"><h2>Judge provenance</h2>{result.judge_invocations.length ? <div className="table-wrap"><table><thead><tr><th>Profile</th><th>Provider / model</th><th>Prompt</th><th>Status</th><th>Timing</th></tr></thead><tbody>{result.judge_invocations.map((invocation) => <tr key={invocation.invocation_id}><td>{invocation.judge_profile}</td><td className="mono">{invocation.provider} / {invocation.model}<div className="subtle">adapter {invocation.adapter_version}</div></td><td className="mono">{invocation.prompt_version}</td><td><Badge value={invocation.status} /></td><td>{formatDate(invocation.started_at)}<div className="subtle">to {formatDate(invocation.ended_at)}</div></td></tr>)}</tbody></table></div> : <EmptyState label="Deterministic result; no model judge invocation." />}</section>
  </>;
}
