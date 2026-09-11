"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { JsonValue, Span, TimeseriesPoint, TraceDetail } from "../lib/types";
import { formatDate, formatDuration, formatNumber } from "../lib/client";

/**
 * AgentLens Logo Icon SVG based on reference lens/goggles outline (Image 3)
 * Transformed into a solid black monochrome vector logo mark.
 */
export function LensLogoIcon({ className = "w-6 h-6" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M3 7C3 5.34315 4.34315 4 6 4H18C19.6569 4 21 5.34315 21 7V13.5C21 15.9853 18.9853 18 16.5 18H15.25C14.5596 18 14 17.4404 14 16.75C14 15.7835 13.2165 15 12.25 15H11.75C10.7835 15 10 15.7835 10 16.75C10 17.4404 9.44036 18 8.75 18H7.5C5.01472 18 3 15.9853 3 13.5V7Z"
        fill="currentColor"
      />
      <circle cx="8" cy="10.5" r="2.2" fill="#FFFFFF" />
      <circle cx="16" cy="10.5" r="2.2" fill="#FFFFFF" />
    </svg>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  const groups = [
    {
      title: "RAG Analyzer",
      items: [
        { label: "RagLens Studio", href: "/raglens" },
      ],
    },
    {
      title: "Core Studio",
      items: [
        { label: "AI Assistant Studio", href: "/" },
        { label: "Knowledge Base & Rules", href: "/knowledge" },
        { label: "AI Quality & Benchmarks", href: "/evaluations" },
      ],
    },
    {
      title: "Observability",
      items: [
        { label: "Live Traces & Spans", href: "/traces" },
        { label: "System Telemetry & KPIs", href: "/analytics" },
        { label: "Alerts & Webhooks", href: "/settings/alerts" },
      ],
    },
    {
      title: "Platform",
      items: [
        { label: "Project & API Keys", href: "/settings" },
        { label: "How It Works Guide", href: "/how-it-works" },
      ],
    },
  ];

  return (
    <aside className="app-sidebar" aria-label="Primary sidebar navigation">
      <div className="sidebar-header">
        <div className="sidebar-brand-mark">
          <LensLogoIcon className="w-5 h-5 text-white" />
        </div>
        <div className="sidebar-brand-text">
          <span className="brand-title">AgentLens</span>
          <span className="brand-subtitle">AI Control Plane</span>
        </div>
      </div>

      <div className="sidebar-nav">
        {groups.map((group) => (
          <div key={group.title} className="sidebar-group">
            <div className="sidebar-group-title">{group.title}</div>
            {group.items.map((item) => {
              const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`sidebar-nav-item ${isActive ? "active" : ""}`}
                >
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="user-profile-tile">
          <div className="user-avatar">AL</div>
          <div className="user-info">
            <span className="user-name">Enterprise Admin</span>
            <span className="user-role">proj-default</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

export function TopHeader() {
  const [searchTerm, setSearchTerm] = React.useState("");
  const [engineStatus, setEngineStatus] = React.useState<{ online: boolean; pingMs: number | null }>({
    online: true,
    pingMs: 12,
  });

  React.useEffect(() => {
    let active = true;
    const checkEngine = async () => {
      const t0 = performance.now();
      try {
        const res = await fetch("/api/rag/health", { cache: "no-store" });
        if (active) {
          const ping = Math.round(performance.now() - t0);
          setEngineStatus({ online: res.ok, pingMs: Math.max(1, ping) });
        }
      } catch {
        if (active) {
          setEngineStatus({ online: false, pingMs: null });
        }
      }
    };
    void checkEngine();
    const timer = setInterval(checkEngine, 6000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const term = searchTerm.trim();
    if (!term) return;
    const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (uuidPattern.test(term)) {
      window.location.href = `/traces/${encodeURIComponent(term)}`;
    } else {
      window.location.href = `/traces?name=${encodeURIComponent(term)}`;
    }
  };

  return (
    <header className="app-topbar">
      <form onSubmit={handleSearch} className="topbar-search" style={{ cursor: "text" }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <input
          type="text"
          placeholder="Search traces, spans, evaluations (press Enter)..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            background: "transparent",
            border: "none",
            outline: "none",
            color: "#000000",
            fontSize: "0.82rem",
            width: "100%",
          }}
        />
        <span className="search-shortcut">↵ Enter</span>
      </form>

      <div className="topbar-actions" style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <div
          className="env-pill"
          style={{
            background: engineStatus.online ? "#f0fdf4" : "#fefce8",
            borderColor: engineStatus.online ? "#bbf7d0" : "#fef08a",
            color: engineStatus.online ? "#166534" : "#854d0e",
            padding: "0.3rem 0.65rem",
            borderRadius: "999px",
            fontSize: "0.74rem",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            border: `1px solid ${engineStatus.online ? "#bbf7d0" : "#fef08a"}`,
            boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
          }}
          title={engineStatus.online ? "Backend AI Engine is connected on port 8000" : "Attempting reconnection to backend engine"}
        >
          <span
            style={{
              width: "7px",
              height: "7px",
              borderRadius: "50%",
              background: engineStatus.online ? "#16a34a" : "#ca8a04",
              display: "inline-block",
            }}
          />
          <span>{engineStatus.online ? `AI Engine Online · ${engineStatus.pingMs}ms` : "Reconnecting Engine..."}</span>
        </div>

        <Link href="/knowledge" className="button secondary" style={{ minHeight: "2rem", fontSize: "0.78rem" }}>
          Knowledge Base
        </Link>
      </div>
    </header>
  );
}

export function LoadingState({ label = "Loading dashboard data…" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-label={label} aria-live="polite">
      <p style={{ margin: 0, fontWeight: 500 }}>{label}</p>
    </div>
  );
}

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="empty" role="status">
      <p style={{ margin: 0 }}>{label}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-box" role="alert">
      <p style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>{message}</p>
      {onRetry && (
        <button className="button secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Badge({ value }: { value: string }) {
  const className = value.replace(/[^a-z0-9_-]/gi, "_");
  return <span className={`badge ${className}`}>{value}</span>;
}

export function JsonViewer({ value }: { value: JsonValue | undefined }) {
  return (
    <pre className="json" aria-label="Structured JSON data">
      {JSON.stringify(value ?? null, null, 2)}
    </pre>
  );
}

export function TimeSeriesChart({ points }: { points: TimeseriesPoint[] }) {
  if (!points.length) return <EmptyState label="No trace buckets in this window." />;
  const max = Math.max(...points.map((point) => point.trace_count), 1);
  return (
    <div className="chart" aria-label="Trace volume by time bucket" role="img">
      {points.map((point) => (
        <div
          className="bar-wrap"
          key={point.bucket_start}
          title={`${formatDate(point.bucket_start)} · ${point.trace_count} traces`}
        >
          <div
            className="bar"
            style={{ height: `${Math.max(4, (point.trace_count / max) * 100)}%` }}
          />
          <span className="bar-label">
            {new Date(point.bucket_start).toLocaleTimeString([], { hour: "numeric" })}
          </span>
        </div>
      ))}
    </div>
  );
}

function spanChildren(spans: Span[], parentId: string | null): Span[] {
  return spans.filter((span) => span.parent_span_id === parentId);
}

function SpanRow({
  span,
  spans,
  depth,
  traceStart,
  traceEnd,
}: {
  span: Span;
  spans: Span[];
  depth: number;
  traceStart: number;
  traceEnd: number;
}) {
  const start = new Date(span.started_at).getTime();
  const end = span.ended_at ? new Date(span.ended_at).getTime() : Math.min(Date.now(), traceEnd);
  const total = Math.max(traceEnd - traceStart, 1);
  const left = Math.max(0, ((start - traceStart) / total) * 100);
  const width = Math.max(2, ((end - start) / total) * 100);
  const children = spanChildren(spans, span.span_id);

  return (
    <>
      <div
        className={`tree-row ${span.ended_at ? "" : "open"}`}
        style={{ marginLeft: `${Math.min(depth, 5) * 0.75}rem` }}
      >
        <div>
          <strong style={{ color: "#000000" }}>{span.name}</strong>
          <div className="subtle mono">
            {span.span_type} · {formatDuration(span.ended_at ? end - start : null)}
          </div>
        </div>
        <div className="waterfall-track" aria-label={`${span.name} waterfall`}>
          <span className="waterfall-bar" style={{ left: `${left}%`, width: `${width}%` }} />
        </div>
        <Badge value={span.ended_at ? span.status : "open"} />
      </div>
      {children.map((child) => (
        <SpanRow
          key={child.span_id}
          span={child}
          spans={spans}
          depth={depth + 1}
          traceStart={traceStart}
          traceEnd={traceEnd}
        />
      ))}
    </>
  );
}

export function SpanTree({ trace }: { trace: TraceDetail }) {
  if (!trace.spans.length) return <EmptyState label="This trace has no spans." />;
  const traceStart = new Date(trace.started_at).getTime();
  const traceEnd = trace.ended_at ? new Date(trace.ended_at).getTime() : Date.now();
  const roots = spanChildren(trace.spans, null);
  return (
    <div className="tree" role="tree" aria-label="Hierarchical span waterfall">
      {roots.map((span) => (
        <SpanRow
          key={span.span_id}
          span={span}
          spans={trace.spans}
          depth={0}
          traceStart={traceStart}
          traceEnd={traceEnd}
        />
      ))}
    </div>
  );
}

export function MetricList({ values }: { values: Record<string, JsonValue> }) {
  return (
    <dl className="kvs">
      {Object.entries(values).map(([key, value]) => (
        <React.Fragment key={key}>
          <dt>{key}</dt>
          <dd className="mono">
            {typeof value === "object" ? JSON.stringify(value) : String(value)}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

export function formatFindingLabel(code: string): string {
  return code.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function TraceTime({ value }: { value: string }) {
  return <time dateTime={value}>{formatDate(value)}</time>;
}

export function CountNote({ count, noun }: { count: number; noun: string }) {
  return (
    <span className="subtle">
      {formatNumber(count)} {noun}
      {count === 1 ? "" : "s"}
    </span>
  );
}
