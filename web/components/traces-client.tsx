"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { dashboardFetch, formatDate, formatDuration, jsonParams } from "../lib/client";
import type { TraceStatus, TraceSummary } from "../lib/types";
import { Badge, EmptyState, ErrorState, LoadingState } from "./ui";

interface TracePage {
  items: TraceSummary[];
  next_cursor: string | null;
}

export default function TracesClient() {
  const searchParams = useSearchParams();
  const initialName = searchParams?.get("name") || searchParams?.get("query") || "";
  const initialSession = searchParams?.get("session_id") || "";

  const [name, setName] = useState(initialName);
  const [session, setSession] = useState(initialSession);
  const [spanType, setSpanType] = useState("");
  const [status, setStatus] = useState<TraceStatus | "">("");
  const [traceId, setTraceId] = useState("");
  const [page, setPage] = useState<TracePage | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextCursor: string | null = null, filterName?: string) => {
    setLoading(true);
    setError(null);
    try {
      const activeName = filterName !== undefined ? filterName : name;
      const query = jsonParams({
        name: activeName || undefined,
        session_id: session || undefined,
        span_type: spanType || undefined,
        status: status || undefined,
        limit: "50",
        cursor: nextCursor || undefined,
      });
      const result = await dashboardFetch<TracePage>(`traces${query}`);
      setPage(result);
      setCursor(nextCursor);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load traces.");
    } finally {
      setLoading(false);
    }
  }, [name, session, spanType, status]);

  useEffect(() => {
    void load(null, initialName);
  }, [initialName]);

  const exactLookup = () => {
    if (traceId.trim()) window.location.assign(`/traces/${encodeURIComponent(traceId.trim())}`);
  };

  return <>
    <div className="page-heading"><div><p className="eyebrow">Explore observations</p><h1>Traces</h1><p className="lede">Filter project-scoped trace summaries, then open a canonical trace to inspect its span hierarchy and evidence.</p></div><button className="button secondary" onClick={() => void load(cursor)} disabled={loading}>Refresh</button></div>
    <section className="card section"><div className="filters"><label className="field">Name<input className="control" value={name} onChange={(event) => setName(event.target.value)} placeholder="exact name" /></label><label className="field">Session<input className="control" value={session} onChange={(event) => setSession(event.target.value)} placeholder="session id" /></label><label className="field">Span type<input className="control" value={spanType} onChange={(event) => setSpanType(event.target.value)} placeholder="llm, tool…" /></label><label className="field">Status<select className="control" value={status} onChange={(event) => setStatus(event.target.value as TraceStatus | "")}><option value="">Any status</option><option value="ok">ok</option><option value="error">error</option><option value="unset">unset</option></select></label><button className="button" onClick={() => void load(null)}>Apply filters</button></div><div className="filters" style={{ marginTop: ".8rem" }}><label className="field">Exact trace ID<input className="control" value={traceId} onChange={(event) => setTraceId(event.target.value)} placeholder="UUID" /></label><button className="button secondary" onClick={exactLookup}>Open exact trace</button></div></section>
    <section className="card section">{loading && !page ? <LoadingState label="Loading traces…" /> : error ? <ErrorState message={error} onRetry={() => void load(cursor)} /> : page ? page.items.length ? <><div className="table-wrap"><table><thead><tr><th>Trace</th><th>Status</th><th>Started</th><th>Duration</th><th>Shape</th></tr></thead><tbody>{page.items.map((trace) => <tr key={trace.trace_id}><td><Link className="link" href={`/traces/${trace.trace_id}`}>{trace.name}</Link><div className="subtle mono">{trace.trace_id}</div>{trace.session_id && <div className="subtle">session {trace.session_id}</div>}</td><td><Badge value={trace.status} /></td><td>{formatDate(trace.started_at)}</td><td>{formatDuration(trace.duration_ms ?? (typeof (trace as any).duration === "number" ? Math.round((trace as any).duration * 1000) : null))}</td><td className="subtle">{trace.span_count} spans · {trace.event_count} events</td></tr>)}</tbody></table></div><div className="toolbar" style={{ marginTop: "1rem" }}><button className="button secondary" disabled={!cursor || loading} onClick={() => void load(null)}>First page</button><button className="button" disabled={!page.next_cursor || loading} onClick={() => void load(page.next_cursor)}>Next page</button></div></> : <EmptyState label="No traces match these filters." /> : <EmptyState label="Apply filters to load traces." />}</section>
  </>;
}
