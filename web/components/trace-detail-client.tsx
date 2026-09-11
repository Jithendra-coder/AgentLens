"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { dashboardFetch, formatDate, formatDuration, formatNumber } from "../lib/client";
import type { EvaluationResultItem, TraceDetail } from "../lib/types";
import { Badge, EmptyState, ErrorState, JsonViewer, LoadingState, SpanTree, TraceTime } from "./ui";
import TraceProfiler from "./trace-profiler";

type TraceResultSummary = Pick<EvaluationResultItem, "result_id" | "evaluation_type" | "evaluator_name" | "evaluator_version" | "evaluation_mode" | "result_status" | "created_at">;

export default function TraceDetailClient({ traceId }: { traceId: string }) {
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [results, setResults] = useState<TraceResultSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const nextTrace = await dashboardFetch<TraceDetail>(`traces/${traceId}`);
      let nextResultsItems: TraceResultSummary[] = [];
      try {
        const nextResults = await dashboardFetch<{ items: TraceResultSummary[] }>(`traces/${traceId}/evaluation-results`);
        if (nextResults && Array.isArray(nextResults.items)) {
          nextResultsItems = nextResults.items;
        }
      } catch {
        nextResultsItems = [];
      }
      setTrace(nextTrace);
      setResults(nextResultsItems);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load trace."); }
    finally { setLoading(false); }
  }, [traceId]);
  useEffect(() => { void load(); }, [load]);

  if (loading && !trace) return <LoadingState label="Loading canonical trace…" />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!trace) return <EmptyState label="Trace not found." />;
  const duration = trace.ended_at ? new Date(trace.ended_at).getTime() - new Date(trace.started_at).getTime() : null;
  return <>
    <div className="page-heading"><div><p className="eyebrow">Trace detail</p><h1>{trace.name}</h1><p className="lede mono">{trace.trace_id}</p></div><div className="toolbar"><Badge value={trace.status} /><button className="button secondary" onClick={() => void load()} disabled={loading}>Refresh</button></div></div>
    <section className="card"><dl className="kvs"><dt>Started</dt><dd><TraceTime value={trace.started_at} /></dd><dt>Ended</dt><dd>{trace.ended_at ? <TraceTime value={trace.ended_at} /> : <Badge value="open" />}</dd><dt>Duration</dt><dd>{formatDuration(duration)}</dd><dt>Session</dt><dd>{trace.session_id ?? "—"}</dd><dt>Schema</dt><dd className="mono">{trace.schema_version}</dd><dt>Shape</dt><dd>{trace.spans.length} spans · {trace.events.length} events</dd></dl></section>
    
    {/* Performance Profiler & Bottleneck Analysis  */}
    <section className="card">
      <h2>Performance Profile & Critical Path</h2>
      <TraceProfiler traceId={traceId} />
    </section>

    <div className="detail-grid section"><div className="grid"><section className="card"><div className="split"><h2>Span waterfall</h2><span className="subtle">Parallel spans retain overlap</span></div><SpanTree trace={trace} /></section><SpecializedSpans trace={trace} /><section className="card"><h2>Events</h2>{trace.events.length ? <div className="table-wrap"><table><thead><tr><th>Name</th><th>Timestamp</th><th>Span</th><th>Attributes</th></tr></thead><tbody>{trace.events.map((event) => <tr key={event.event_id}><td>{event.name}</td><td>{formatDate(event.timestamp)}</td><td className="mono">{event.span_id ?? "trace"}</td><td><JsonViewer value={event.attributes} /></td></tr>)}</tbody></table></div> : <EmptyState label="No events recorded." />}</section></div><aside className="grid"><section className="card"><h2>Trace attributes</h2><JsonViewer value={trace.attributes} /></section><section className="card"><h2>Evaluations</h2>{results.length ? <div className="table-wrap"><table><thead><tr><th>Type</th><th>Mode</th><th>Status</th></tr></thead><tbody>{results.map((result) => <tr key={result.result_id}><td><Link className="link" href={`/evaluations/${result.result_id}`}>{result.evaluation_type}</Link><div className="subtle">{result.evaluator_name} · {result.evaluator_version}</div></td><td><Badge value={result.evaluation_mode} /></td><td><Badge value={result.result_status} /></td></tr>)}</tbody></table></div> : <EmptyState label="No evaluations for this trace." />}</section></aside></div>
  </>;
}

function SpecializedSpans({ trace }: { trace: TraceDetail }) {
  const retrieval = trace.spans.filter((span) => span.span_type === "retrieval");
  const tools = trace.spans.filter((span) => span.span_type === "tool");
  const llm = trace.spans.filter((span) => span.span_type === "llm");
  if (!retrieval.length && !tools.length && !llm.length) return null;
  return <section className="card"><h2>Structured span views</h2><div className="grid two">{retrieval.map((span) => <div key={span.span_id}><h3>Retrieval · {span.name}</h3><p className="subtle">Documents and ranked evidence stay data-only.</p><JsonViewer value={span.output} /></div>)}{tools.map((span) => <div key={span.span_id}><h3>Tool · {span.name}</h3><JsonViewer value={{ input: span.input, output: span.output }} /></div>)}{llm.map((span) => <div key={span.span_id}><h3>LLM · {span.name}</h3>{span.usage ? <dl className="kvs"><dt>Input tokens</dt><dd>{formatNumber(span.usage.input_tokens)}</dd><dt>Output tokens</dt><dd>{formatNumber(span.usage.output_tokens)}</dd><dt>Total tokens</dt><dd>{formatNumber(span.usage.total_tokens)}</dd></dl> : <p className="subtle">No usage reported.</p>}<JsonViewer value={span.output} /></div>)}</div></section>;
}
