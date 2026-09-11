"""Offline HTML Report Generator for AgentLens CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


def generate_raglens_html_report(
    api_key: str,
    trace_id: str,
    query: str,
    domain: str,
    total_latency_ms: float,
    total_tokens: int,
    cost_usd: float,
    status: str,
    pipeline_spans: List[Dict[str, Any]],
    diagnosis: Dict[str, Any],
    chunks: List[Dict[str, Any]],
    lighthouse: Dict[str, Any],
    output_dir: str = "reports",
) -> str:
    """Generate a clean, self-contained offline HTML audit report."""
    os.makedirs(output_dir, exist_ok=True)
    report_file = os.path.join(output_dir, f"raglens_report_{trace_id}.html")
    latest_file = os.path.join(output_dir, "raglens_latest.html")

    overall_sc = lighthouse.get("overall_score", 85)
    overall_gr = lighthouse.get("overall_grade", "B")
    pillars = lighthouse.get("pillars", {})
    opportunities = lighthouse.get("opportunities", [])

    def grade_color(grade: str) -> str:
        if "A" in grade:
            return "#22c55e"
        if "B" in grade:
            return "#3b82f6"
        if "C" in grade:
            return "#eab308"
        return "#ef4444"

    pillars_html = ""
    for k, p in pillars.items():
        title = k.replace("_", " ").title()
        sc = p.get("score", 0)
        gr = p.get("grade", "N/A")
        clr = grade_color(gr)
        pillars_html += f"""
        <div class="pillar-card">
          <div class="pillar-top">
            <span class="pillar-title">{title}</span>
            <span class="pillar-badge" style="color: {clr}; border-color: {clr}40; background: {clr}15;">{gr} ({sc})</span>
          </div>
          <div class="pillar-metric">{p.get('metric_label', '')}</div>
          <div class="pillar-sub">{p.get('sub_metric', '')}</div>
        </div>
        """

    opps_html = ""
    for o in opportunities:
        opps_html += f"""
        <div class="opp-card">
          <div class="opp-badge">{o.get('savings_label', '')}</div>
          <div class="opp-title">{o.get('title', '')}</div>
          <div class="opp-desc">{o.get('description', '')}</div>
          <div class="opp-impact"><strong>Impact:</strong> {o.get('impact', 'HIGH')} &nbsp;|&nbsp; <strong>Effort:</strong> {o.get('effort', 'LOW')}</div>
        </div>
        """

    spans_html = ""
    for s in pipeline_spans:
        pct = s.get("pct", 10)
        spans_html += f"""
        <div class="span-row">
          <div class="span-name">{s.get('name')} <span style="color:#64748b;font-size:12px">({s.get('component')})</span></div>
          <div class="span-bar-wrapper">
            <div class="span-bar" style="width: {max(6, pct)}%;"></div>
          </div>
          <div class="span-lat">{s.get('latency_ms')} ms ({pct}%)</div>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>RagLens Audit Report - {api_key}</title>
  <style>
    :root {{
      --bg: #0b0f17;
      --card-bg: #121824;
      --border: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); padding: 40px 20px; }}
    .container {{ max-width: 960px; margin: 0 auto; }}
    .header {{ border-bottom: 1px solid var(--border); padding-bottom: 24px; margin-bottom: 32px; }}
    .brand {{ font-size: 13px; font-weight: 700; color: var(--accent); letter-spacing: 1.5px; text-transform: uppercase; }}
    .title {{ font-size: 28px; font-weight: 800; margin-top: 8px; }}
    .meta-bar {{ display: flex; flex-wrap: wrap; gap: 16px; margin-top: 16px; font-size: 13px; color: var(--text-muted); }}
    .meta-item strong {{ color: var(--text); }}
    .score-banner {{
      background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.9));
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 32px;
      display: flex;
      align-items: center;
      gap: 36px;
      margin-bottom: 32px;
    }}
    .circle-score {{
      width: 110px;
      height: 110px;
      border-radius: 50%;
      border: 4px solid {grade_color(overall_gr)};
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: rgba(34, 197, 94, 0.08);
      flex-shrink: 0;
    }}
    .circle-score .grade {{ font-size: 38px; font-weight: 900; color: {grade_color(overall_gr)}; line-height: 1; }}
    .circle-score .score {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}
    .banner-text h2 {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; }}
    .banner-text p {{ color: var(--text-muted); font-size: 14px; line-height: 1.5; }}
    .pillars-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
    .pillar-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
    .pillar-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
    .pillar-title {{ font-size: 14px; font-weight: 600; color: var(--text-muted); }}
    .pillar-badge {{ font-size: 12px; font-weight: 700; padding: 3px 8px; border-radius: 6px; border: 1px solid; }}
    .pillar-metric {{ font-size: 20px; font-weight: 800; margin-bottom: 4px; }}
    .pillar-sub {{ font-size: 12px; color: var(--text-muted); }}
    .section-title {{ font-size: 18px; font-weight: 700; margin-bottom: 16px; }}
    .opps-grid {{ display: grid; gap: 16px; margin-bottom: 32px; }}
    .opp-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
    .opp-badge {{ display: inline-block; font-size: 11px; font-weight: 700; color: #facc15; background: rgba(250, 204, 21, 0.1); border: 1px solid rgba(250, 204, 21, 0.2); padding: 3px 8px; border-radius: 4px; margin-bottom: 8px; }}
    .opp-title {{ font-size: 16px; font-weight: 700; margin-bottom: 6px; }}
    .opp-desc {{ font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 10px; }}
    .opp-impact {{ font-size: 12px; color: #38bdf8; }}
    .spans-list {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 32px; }}
    .span-row {{ display: flex; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
    .span-row:last-child {{ border-bottom: none; }}
    .span-name {{ width: 280px; font-size: 14px; font-weight: 500; }}
    .span-bar-wrapper {{ flex: 1; height: 10px; background: rgba(255,255,255,0.06); border-radius: 5px; margin: 0 16px; overflow: hidden; }}
    .span-bar {{ height: 100%; background: var(--accent); border-radius: 5px; }}
    .span-lat {{ width: 140px; text-align: right; font-size: 13px; font-family: monospace; color: var(--text-muted); }}
    .footer {{ text-align: center; color: var(--text-muted); font-size: 12px; margin-top: 40px; border-top: 1px solid var(--border); padding-top: 20px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">AgentLens &bull; Lighthouse for RAG</div>
      <div class="title">RAG Application Audit Report</div>
      <div class="meta-bar">
        <div class="meta-item">API Key: <strong>{api_key}</strong></div>
        <div class="meta-item">Trace ID: <strong>{trace_id}</strong></div>
        <div class="meta-item">Domain: <strong>{domain}</strong></div>
        <div class="meta-item">Query: <strong>"{query}"</strong></div>
      </div>
    </div>

    <div class="score-banner">
      <div class="circle-score">
        <div class="grade">{overall_gr}</div>
        <div class="score">{overall_sc} / 100</div>
      </div>
      <div class="banner-text">
        <h2>Overall Performance Grade: {overall_gr}</h2>
        <p>This audit evaluated end-to-end latency, vector retrieval grounding, cost economy, and chunk balance. Top opportunities below highlight estimated ROI and latency gains.</p>
      </div>
    </div>

    <div class="section-title">Audit Pillars</div>
    <div class="pillars-grid">
      {pillars_html}
    </div>

    <div class="section-title">Top Actionable Opportunities</div>
    <div class="opps-grid">
      {opps_html}
    </div>

    <div class="section-title">Pipeline Span Latency Breakdown</div>
    <div class="spans-list">
      {spans_html}
    </div>

    <div class="footer">
      Generated automatically by AgentLens Standalone CLI &bull; Provider-Independent AI Observability
    </div>
  </div>
</body>
</html>
"""

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    return report_file
