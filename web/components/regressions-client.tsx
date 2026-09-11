"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { dashboardFetch, formatDate, formatNumber, formatPercent } from "../lib/client";
import type { RegressionCase, RegressionMetric, RegressionPolicy, RegressionRun, ReplayRun } from "../lib/types";
import { Badge, EmptyState, ErrorState, LoadingState } from "./ui";

function useLoad<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await dashboardFetch<T>(path)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load regression data."); }
    finally { setLoading(false); }
  }, [path]);
  useEffect(() => { void load(); }, [load]);
  return { data, error, loading, load };
}

const defaultRules = JSON.stringify([
  { rule_id: "quality", metric_id: "replay.execution_success_rate", direction: "higher_is_better", absolute_tolerance: 0.02, minimum_samples: 1, required: true, severity: "critical" },
  { rule_id: "latency", metric_id: "trace.duration_ms.p95", direction: "lower_is_better", relative_tolerance: 0.1, candidate_maximum: 1000, minimum_samples: 1, required: true, severity: "warning" },
], null, 2);

export function RegressionsClient() {
  const policies = useLoad<{ items: RegressionPolicy[] }>("regression-policies");
  const runs = useLoad<{ items: RegressionRun[] }>("regression-runs");
  const replays = useLoad<{ items: ReplayRun[] }>("replay-runs");
  const [name, setName] = useState("Default comparison policy");
  const [rules, setRules] = useState(defaultRules);
  const [policyId, setPolicyId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const terminal = useMemo(() => replays.data?.items.filter((item) => ["succeeded", "failed", "partially_failed"].includes(item.status)) ?? [], [replays.data]);
  useEffect(() => { setPolicyId((current) => current || policies.data?.items[0]?.policy_id || ""); }, [policies.data]);
  useEffect(() => { setBaselineId((current) => current || terminal[0]?.replay_run_id || ""); setCandidateId((current) => current || terminal[1]?.replay_run_id || ""); }, [terminal]);
  async function createPolicy() {
    try { await dashboardFetch("regression-policies", { method: "POST", body: { name, description: "Independent quality and performance comparison rules.", rules: JSON.parse(rules) } }); setMessage("Policy version created."); await policies.load(); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Policy JSON is invalid."); }
  }
  async function createRun() {
    try { await dashboardFetch("regression-runs", { method: "POST", body: { baseline_replay_run_id: baselineId, candidate_replay_run_id: candidateId, policy_id: policyId } }); setMessage("Comparison queued."); await runs.load(); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Unable to create comparison."); }
  }
  return <PageHeading eyebrow="Quality engineering" title="Regressions" lede="Compare two terminal replays from the same finalized dataset with explicit, independent metric rules." action={<button className="button secondary" onClick={() => { void policies.load(); void runs.load(); void replays.load(); }}>Refresh</button>}>
    <div className="grid two section">
      <section className="card"><h2>Create policy version</h2><label>Name<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Rules JSON<textarea value={rules} onChange={(event) => setRules(event.target.value)} rows={10} /></label><button className="button" onClick={() => void createPolicy()} disabled={!name.trim()}>Save immutable policy</button></section>
      <section className="card"><h2>Create comparison</h2><label>Policy<select value={policyId} onChange={(event) => setPolicyId(event.target.value)}><option value="">Select policy</option>{policies.data?.items.map((item) => <option key={item.policy_id} value={item.policy_id}>{item.name} · v{item.version}</option>)}</select></label><label>Baseline replay<select value={baselineId} onChange={(event) => setBaselineId(event.target.value)}><option value="">Select baseline</option>{terminal.map((item) => <option key={item.replay_run_id} value={item.replay_run_id}>{item.replay_run_id.slice(0, 12)} · {item.dataset_checksum.slice(0, 10)}</option>)}</select></label><label>Candidate replay<select value={candidateId} onChange={(event) => setCandidateId(event.target.value)}><option value="">Select candidate</option>{terminal.map((item) => <option key={item.replay_run_id} value={item.replay_run_id}>{item.replay_run_id.slice(0, 12)} · {item.dataset_checksum.slice(0, 10)}</option>)}</select></label><button className="button" onClick={() => void createRun()} disabled={!policyId || !baselineId || !candidateId}>Queue comparison</button></section>
    </div>
    {message && <p className="subtle" role="status">{message}</p>}
    {runs.loading && !runs.data ? <LoadingState /> : runs.error ? <ErrorState message={runs.error} onRetry={() => void runs.load()} /> : runs.data?.items.length ? <section className="card section"><h2>Report explorer</h2><div className="table-wrap"><table><thead><tr><th>Report</th><th>Status</th><th>Dataset</th><th>Improved</th><th>Regressed</th><th>Hard limits</th></tr></thead><tbody>{runs.data.items.map((run) => <tr key={run.regression_run_id}><td><Link className="link mono" href={`/regressions/${run.regression_run_id}`}>{run.regression_run_id.slice(0, 12)}…</Link><div className="subtle">policy v{run.policy_version}</div></td><td><Badge value={run.status} /></td><td className="mono">{run.dataset_checksum.slice(0, 16)}…</td><td>{run.improvement_count}</td><td>{run.regression_count}</td><td><Badge value={run.has_regressions ? "violated" : "not_configured"} /></td></tr>)}</tbody></table></div></section> : <EmptyState label="No regression reports yet." />}
  </PageHeading>;
}

export function RegressionDetailClient({ runId }: { runId: string }) {
  const run = useLoad<RegressionRun>(`regression-runs/${runId}`);
  const metrics = useLoad<{ items: RegressionMetric[] }>(`regression-runs/${runId}/metrics`);
  const cases = useLoad<{ items: RegressionCase[] }>(`regression-runs/${runId}/cases?limit=100`);
  if (run.loading && !run.data) return <LoadingState />;
  if (run.error) return <ErrorState message={run.error} onRetry={() => void run.load()} />;
  if (!run.data) return <EmptyState label="Report not found." />;
  const report = run.data;
  return <PageHeading eyebrow="Regression report" title={report.regression_run_id} lede={`${report.report_schema_version} · immutable once completed`} action={<button className="button secondary" onClick={() => { void run.load(); void metrics.load(); void cases.load(); }}>Refresh</button>}>
    <div className="grid stats"><Stat label="Status" value={report.status} note={`Engine ${report.comparison_engine_version}`} /><Stat label="Improved" value={String(report.improvement_count)} note="Independent metric classifications" /><Stat label="Regressed" value={String(report.regression_count)} note="Review before promotion" /><Stat label="Data quality" value={`${report.insufficient_data_count} insufficient`} note={`${report.incompatible_count} incompatible`} /></div>
    <section className="card section"><h2>Comparison provenance</h2><dl className="kvs"><dt>Dataset checksum</dt><dd className="mono">{report.dataset_checksum}</dd><dt>Baseline / candidate</dt><dd className="mono">{report.baseline_replay_run_id} / {report.candidate_replay_run_id}</dd><dt>Changed dimensions</dt><dd>{report.changed_dimensions.length ? report.changed_dimensions.join(", ") : "No manifest changes recorded"}</dd><dt>Policy</dt><dd>{report.policy?.name ?? report.policy_id} · v{report.policy_version}</dd><dt>Finished</dt><dd>{report.finished_at ? formatDate(report.finished_at) : "Pending"}</dd></dl></section>
    <section className="card section"><h2>Independent metric results</h2>{metrics.loading ? <LoadingState /> : metrics.error ? <ErrorState message={metrics.error} onRetry={() => void metrics.load()} /> : metrics.data?.items.length ? <div className="table-wrap"><table><thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th><th>Samples</th><th>Classification</th><th>Candidate limit</th></tr></thead><tbody>{metrics.data.items.map((metric) => <tr key={metric.comparison_id}><td><strong>{metric.metric_id}</strong><div className="subtle">{metric.direction ?? "informational"} · {String(metric.provenance.evaluator_name ?? metric.provenance.source ?? "runtime")}</div><JudgeProvenance value={metric.provenance.judge_provenance} /></td><td>{formatNumber(metric.baseline_value, 3)}</td><td>{formatNumber(metric.candidate_value, 3)}</td><td>{formatNumber(metric.absolute_delta, 3)}<div className="subtle">{formatPercent(metric.relative_delta)}</div></td><td>{metric.baseline_samples}/{metric.candidate_samples}<div className="subtle">paired {metric.paired_samples}</div></td><td><Badge value={metric.classification} /><div className="subtle">{String(metric.details.explanation ?? "")}</div></td><td><Badge value={metric.candidate_limit_status} /></td></tr>)}</tbody></table></div> : <EmptyState label="Metrics are not available until the report completes." />}</section>
    <section className="card section"><h2>Paired case drilldown</h2>{cases.loading ? <LoadingState /> : cases.error ? <ErrorState message={cases.error} onRetry={() => void cases.load()} /> : cases.data?.items.length ? <div className="table-wrap"><table><thead><tr><th>Case</th><th>Status</th><th>Metric outcomes</th><th>Findings</th><th>Traces</th></tr></thead><tbody>{cases.data.items.map((item) => <tr key={item.case_comparison_id}><td>#{item.position}<div className="subtle mono">{item.case_id}</div></td><td><Badge value={item.status} /></td><td>{item.metric_comparisons.map((comparison, index) => <div key={index}><Badge value={String(comparison.classification ?? "unknown")} /> <span className="subtle">{String(comparison.metric_id ?? "metric")}</span></div>)}</td><td>{item.introduced_findings.length ? <div className="error">Introduced: {item.introduced_findings.join(", ")}</div> : "—"}{item.resolved_findings.length ? <div className="subtle">Resolved: {item.resolved_findings.join(", ")}</div> : null}</td><td>{item.baseline_trace_id ? <Link className="link" href={`/traces/${item.baseline_trace_id}`}>Baseline</Link> : "—"} {item.candidate_trace_id ? <Link className="link" href={`/traces/${item.candidate_trace_id}`}>Candidate</Link> : "—"}</td></tr>)}</tbody></table></div> : <EmptyState label="No paired cases are available yet." />}</section>
  </PageHeading>;
}

function PageHeading({ eyebrow, title, lede, action, children }: { eyebrow: string; title: string; lede: string; action?: React.ReactNode; children: React.ReactNode }) {
  return <><div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="lede">{lede}</p></div>{action && <div className="toolbar">{action}</div>}</div>{children}</>;
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="card"><div className="stat-label">{label}</div><div className="stat-value">{value}</div><p className="stat-note">{note}</p></div>;
}

function JudgeProvenance({ value }: { value: unknown }) {
  if (!Array.isArray(value) || !value.length || typeof value[0] !== "object" || value[0] === null || Array.isArray(value[0])) return null;
  const item = value[0] as Record<string, unknown>;
  return <div className="subtle mono">judge {String(item.provider ?? "?")} / {String(item.model ?? "?")} · prompt {String(item.prompt_version ?? "?")}</div>;
}
