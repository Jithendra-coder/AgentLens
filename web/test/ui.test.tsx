import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorState, JsonViewer, LoadingState, SpanTree } from "../components/ui";
import type { TraceDetail } from "../lib/types";

const trace: TraceDetail = {
  trace_id: "00000000-0000-0000-0000-000000000001",
  project_id: "project-a",
  name: "parallel-agent",
  session_id: null,
  status: "ok",
  started_at: "2026-08-14T00:00:00Z",
  ended_at: "2026-08-14T00:00:04Z",
  schema_version: "agentlens-trace-v1",
  attributes: { safe: "data" },
  events: [],
  spans: [
    { span_id: "00000000-0000-0000-0000-000000000010", trace_id: "00000000-0000-0000-0000-000000000001", parent_span_id: null, span_type: "agent", name: "root", started_at: "2026-08-14T00:00:00Z", ended_at: "2026-08-14T00:00:04Z", status: "ok", input: null, output: null, attributes: {}, usage: null, error: null },
    { span_id: "00000000-0000-0000-0000-000000000011", trace_id: "00000000-0000-0000-0000-000000000001", parent_span_id: "00000000-0000-0000-0000-000000000010", span_type: "tool", name: "lookup", started_at: "2026-08-14T00:00:01Z", ended_at: null, status: "ok", input: { query: "safe" }, output: null, attributes: {}, usage: null, error: null },
  ],
};

describe("dashboard states and trace visualization", () => {
  it("renders loading and error states with accessible roles", () => {
    render(<><LoadingState label="Loading traces" /><ErrorState message="Backend unavailable" /></>);
    expect(screen.getByRole("status", { name: "Loading traces" })).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Backend unavailable");
  });

  it("renders a hierarchical waterfall and marks unfinished spans", () => {
    render(<SpanTree trace={trace} />);
    expect(screen.getByRole("tree", { name: "Hierarchical span waterfall" })).toBeInTheDocument();
    expect(screen.getByText("root")).toBeInTheDocument();
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.getByLabelText("lookup waterfall")).toBeInTheDocument();
  });

  it("renders structured content as escaped JSON data", () => {
    render(<JsonViewer value={{ text: "<script>not markup</script>" }} />);
    expect(document.querySelector("pre")).toHaveTextContent("<script>not markup</script>");
    expect(document.querySelector("script")).toBeNull();
  });
});
