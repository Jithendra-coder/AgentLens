"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { dashboardFetch, formatDate, formatNumber } from "../lib/client";
import type {
  Dataset,
  DatasetCase,
  DatasetVersionDetail,
  DatasetVersionSummary,
  JsonValue,
  ReplayRun,
  ReplayTargetProfile,
} from "../lib/types";
import { Badge, EmptyState, ErrorState, LoadingState } from "./ui";

function useLoad<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await dashboardFetch<T>(path));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => { void load(); }, [load]);
  return { data, error, loading, load };
}

export function DatasetsClient() {
  const { data, error, loading, load } = useLoad<{ items: Dataset[] }>("datasets");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  async function create() {
    setMessage(null);
    try {
      await dashboardFetch("datasets", { method: "POST", body: { name, description } });
      setName(""); setDescription(""); setMessage("Dataset created."); await load();
    } catch (caught) { setMessage(caught instanceof Error ? caught.message : "Unable to create dataset."); }
  }
  return <PageHeading eyebrow="Historical cases" title="Datasets" lede="Project-scoped, immutable replay inputs with explicit provenance.">
    <section className="card section"><h2>Create dataset</h2><div className="form-grid"><label>Name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Support prompts" /></label><label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What this dataset is for" /></label></div><button className="button" onClick={() => void create()} disabled={!name.trim()}>Create</button>{message && <p className="subtle" role="status">{message}</p>}</section>
    {loading && !data ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => void load()} /> : data?.items.length ? <section className="card section"><div className="table-wrap"><table><thead><tr><th>Name</th><th>Latest version</th><th>Cases</th><th>Updated</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.dataset_id}><td><Link className="link" href={`/datasets/${item.dataset_id}`}>{item.name}</Link><div className="subtle">{item.description || "No description"}</div></td><td>{item.latest_version ? <Badge value={item.latest_version.status} /> : "—"}</td><td>{formatNumber(item.latest_version?.case_count ?? 0)}</td><td>{formatDate(item.updated_at)}</td></tr>)}</tbody></table></div></section> : <EmptyState label="No datasets yet." />}
  </PageHeading>;
}

export function DatasetDetailClient({ datasetId }: { datasetId: string }) {
  const { data, error, loading, load } = useLoad<Dataset>(`datasets/${datasetId}`);
  const [message, setMessage] = useState<string | null>(null);
  async function createVersion() {
    try { await dashboardFetch(`datasets/${datasetId}/versions`, { method: "POST", body: { source_metadata: { created_in: "dashboard" } } }); setMessage("Draft version created."); await load(); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Unable to create version."); }
  }
  return <PageHeading eyebrow="Dataset" title={data?.name ?? "Dataset detail"} lede={data?.description ?? "Review versions and their immutable checksums."} action={<button className="button" onClick={() => void createVersion()}>New draft version</button>}>
    {message && <p className="subtle" role="status">{message}</p>}{loading && !data ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => void load()} /> : data?.versions?.length ? <section className="card section"><div className="table-wrap"><table><thead><tr><th>Version</th><th>Status</th><th>Cases</th><th>Checksum</th><th>Created</th></tr></thead><tbody>{data.versions.map((version) => <tr key={version.dataset_version_id}><td><Link className="link" href={`/datasets/${datasetId}/versions/${version.dataset_version_id}`}>v{version.version_number}</Link></td><td><Badge value={version.status} /></td><td>{version.case_count}</td><td className="mono">{version.content_checksum ? version.content_checksum.slice(0, 16) : "draft"}</td><td>{formatDate(version.created_at)}</td></tr>)}</tbody></table></div></section> : <EmptyState label="No versions yet. Create a draft to add cases." />}
  </PageHeading>;
}

export function DatasetVersionClient({ versionId }: { versionId: string }) {
  const { data, error, loading, load } = useLoad<DatasetVersionDetail>(`dataset-versions/${versionId}`);
  const [name, setName] = useState("");
  const [input, setInput] = useState("{}");
  const [groundTruth, setGroundTruth] = useState("");
  const [traceId, setTraceId] = useState("");
  const [spanId, setSpanId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const parse = (value: string): JsonValue => JSON.parse(value) as JsonValue;
  async function addManual() {
    try { await dashboardFetch(`dataset-versions/${versionId}/cases`, { method: "POST", body: { name, input: parse(input), ground_truth: groundTruth.trim() ? parse(groundTruth) : null } }); setName(""); setMessage("Case added."); await load(); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Input must be valid JSON."); }
  }
  async function addTraceCase() {
    try { await dashboardFetch(`dataset-versions/${versionId}/cases/from-trace`, { method: "POST", body: { name, trace_id: traceId, span_id: spanId, input_field: "input" } }); setMessage("Trace-derived case added."); await load(); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Unable to extract case."); }
  }
  async function finalize() {
    if (!window.confirm("Finalize this version? It becomes immutable.")) return;
    try { await dashboardFetch(`dataset-versions/${versionId}/finalize`, { method: "POST", body: {} }); setMessage("Version finalized and immutable."); await load(); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Unable to finalize version."); }
  }
  return <PageHeading eyebrow="Dataset version" title={data ? `Version ${data.version_number}` : "Version detail"} lede={data?.content_checksum ? `Checksum ${data.content_checksum}` : "Draft content can be edited until finalization."} action={data?.status === "draft" ? <button className="button" onClick={() => void finalize()}>Finalize immutable version</button> : <Badge value="finalized" />}>
    {message && <p className="subtle" role="status">{message}</p>}{loading && !data ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => void load()} /> : data ? <>{data.status === "draft" && <div className="grid two section"><section className="card"><h2>Add manual case</h2><label>Name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Case name" /></label><label>Input JSON<textarea value={input} onChange={(event) => setInput(event.target.value)} rows={5} /></label><label>Ground truth JSON<textarea value={groundTruth} onChange={(event) => setGroundTruth(event.target.value)} rows={3} placeholder="Optional" /></label><button className="button" onClick={() => void addManual()} disabled={!name.trim()}>Add case</button></section><section className="card"><h2>Add from trace</h2><p className="subtle">Extraction is explicit: choose the source trace and span.</p><label>Trace ID<input value={traceId} onChange={(event) => setTraceId(event.target.value)} /></label><label>Span ID<input value={spanId} onChange={(event) => setSpanId(event.target.value)} /></label><button className="button secondary" onClick={() => void addTraceCase()} disabled={!name.trim() || !traceId || !spanId}>Extract input case</button></section></div>}<section className="card section"><h2>Ordered cases <span className="subtle">{data.case_count}</span></h2>{data.cases.length ? <div className="table-wrap"><table><thead><tr><th>Position</th><th>Case</th><th>Source</th><th>Tags</th><th>Ground truth</th></tr></thead><tbody>{data.cases.map((item) => <tr key={item.case_id}><td>{item.position}</td><td><strong>{item.name}</strong><div className="subtle mono">{item.case_id}</div></td><td>{String(item.source.kind ?? "manual")}</td><td>{item.tags.join(", ") || "—"}</td><td>{item.ground_truth === null ? "—" : "present"}</td></tr>)}</tbody></table></div> : <EmptyState label="No cases in this draft." />}</section></> : null}
  </PageHeading>;
}

export function ReplaysClient() {
  const runs = useLoad<{ items: ReplayRun[] }>("replay-runs");
  const profiles = useLoad<{ items: ReplayTargetProfile[] }>("replay-target-profiles");
  const datasets = useLoad<{ items: Dataset[] }>("datasets");
  const [versions, setVersions] = useState<DatasetVersionSummary[]>([]);
  const [versionId, setVersionId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [mode, setMode] = useState("best_effort");
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    if (!profiles.data?.items.length) return;
    setProfileId((current) => current || profiles.data?.items[0].profile_id || "");
  }, [profiles.data]);
  useEffect(() => {
    if (!datasets.data) return;
    void Promise.all(datasets.data.items.map((item) => dashboardFetch<Dataset>(`datasets/${item.dataset_id}`))).then((details) => {
      const next = details.flatMap((item) => item.versions ?? []).filter((item) => item.status === "finalized");
      setVersions(next); setVersionId((current) => current || next[0]?.dataset_version_id || "");
    });
  }, [datasets.data]);
  async function create() {
    try { const body = { dataset_version_id: versionId, target_profile_id: profileId, replay_mode: mode, manifest: { reproducibility_status: "partial", unknown_fields: ["external_state"], best_effort_reason: "Dashboard replay does not claim determinism." }, max_concurrency: 4 }; await dashboardFetch("replay-runs", { method: "POST", body }); setMessage("Replay queued."); await runs.load(); }
    catch (caught) { setMessage(caught instanceof Error ? caught.message : "Unable to create replay."); }
  }
  return <PageHeading eyebrow="Dataset execution" title="Replays" lede="Run an immutable dataset version through an operator-configured target.">
    <section className="card section"><h2>Create replay</h2><div className="form-grid"><label>Finalized dataset version<select value={versionId} onChange={(event) => setVersionId(event.target.value)}><option value="">Select a version</option>{versions.map((item) => <option key={item.dataset_version_id} value={item.dataset_version_id}>v{item.version_number} · {item.content_checksum?.slice(0, 12)}</option>)}</select></label><label>Trusted target profile<select value={profileId} onChange={(event) => setProfileId(event.target.value)}>{profiles.data?.items.map((item) => <option key={item.profile_id} value={item.profile_id}>{item.name} · {item.safety_class}</option>)}</select></label><label>Replay mode<select value={mode} onChange={(event) => setMode(event.target.value)}><option value="best_effort">best effort</option><option value="controlled">controlled</option><option value="exact">exact</option></select></label></div><button className="button" onClick={() => void create()} disabled={!versionId || !profileId}>Start replay</button>{message && <p className="subtle" role="status">{message}</p>}</section>
    {runs.loading && !runs.data ? <LoadingState /> : runs.error ? <ErrorState message={runs.error} onRetry={() => void runs.load()} /> : runs.data?.items.length ? <section className="card section"><div className="table-wrap"><table><thead><tr><th>Run</th><th>Dataset/version</th><th>Target</th><th>Mode</th><th>Status</th><th>Progress</th></tr></thead><tbody>{runs.data.items.map((run) => <tr key={run.replay_run_id}><td><Link className="link mono" href={`/replays/${run.replay_run_id}`}>{run.replay_run_id.slice(0, 12)}</Link></td><td className="mono">{run.dataset_version_id.slice(0, 12)}</td><td>{run.target_name}</td><td>{run.replay_mode}</td><td><Badge value={run.status} /></td><td>{run.completed_count}/{run.case_count}</td></tr>)}</tbody></table></div></section> : <EmptyState label="No replay runs yet." />}
  </PageHeading>;
}

export function ReplayDetailClient({ runId }: { runId: string }) {
  const { data, error, loading, load } = useLoad<ReplayRun>(`replay-runs/${runId}`);
  return <PageHeading eyebrow="Replay run" title={data ? data.replay_run_id : "Replay detail"} lede="Execution state and trace links for one immutable replay request.">
    {loading && !data ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => void load()} /> : data ? <><div className="grid stats"><Stat label="Status" value={data.status} note={`${data.completed_count}/${data.case_count} cases complete`} /><Stat label="Mode" value={data.replay_mode} note={`Reproducibility: ${data.reproducibility_status}`} /><Stat label="Target" value={data.target_name} note={`v${data.target_version}`} /><Stat label="Concurrency" value={String(data.max_concurrency)} note="bounded worker setting" /></div><section className="card section"><h2>Manifest</h2><pre className="json">{JSON.stringify(data.manifest, null, 2)}</pre></section><section className="card section"><h2>Case executions</h2>{data.executions?.length ? <div className="table-wrap"><table><thead><tr><th>Position</th><th>Status</th><th>Attempts</th><th>Output</th><th>Trace</th></tr></thead><tbody>{data.executions.map((execution) => <tr key={execution.execution_id}><td>{execution.position}</td><td><Badge value={execution.status} />{execution.safe_error && <div className="subtle">{String(execution.safe_error.message ?? "error")}</div>}</td><td>{execution.attempt_count}</td><td className="mono">{execution.output === null ? "—" : JSON.stringify(execution.output).slice(0, 160)}</td><td>{execution.generated_trace_id ? <Link className="link" href={`/traces/${execution.generated_trace_id}`}>Open trace</Link> : "—"}</td></tr>)}</tbody></table></div> : <EmptyState label="No executions yet." />}</section></> : null}
  </PageHeading>;
}

function PageHeading({ eyebrow, title, lede, action, children }: { eyebrow: string; title: string; lede: string; action?: React.ReactNode; children: React.ReactNode }) {
  return <><div className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="lede">{lede}</p></div>{action && <div className="toolbar">{action}</div>}</div>{children}</>;
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="card"><div className="stat-label">{label}</div><div className="stat-value">{value}</div><p className="stat-note">{note}</p></div>;
}
