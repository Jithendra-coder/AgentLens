"""Lighthouse for RAG — Standalone Offline HTML Report Generator."""

from __future__ import annotations

import os
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
    lighthouse: Dict[str, Any] | None = None,
    output_dir: str = "artifacts/reports",
) -> str:
    """Generate an authentic Google Lighthouse-style standalone offline HTML report."""
    os.makedirs(output_dir, exist_ok=True)
    report_filename = f"raglens_report_{trace_id}.html"
    report_path = os.path.join(output_dir, report_filename)
    latest_path = os.path.join(output_dir, "raglens_latest.html")

    if not lighthouse:
        from agentlens.rag.lighthouse import calculate_lighthouse_audit
        lighthouse = calculate_lighthouse_audit(
            query=query,
            total_latency_ms=total_latency_ms,
            pipeline_spans=pipeline_spans,
            chunks=chunks,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )

    overall_score = lighthouse.get("overall_score", 85)
    overall_grade = lighthouse.get("overall_grade", "B")
    overall_color = lighthouse.get("overall_color", "#10b981")
    pillars = lighthouse.get("pillars", {})

    lat_p = pillars.get("latency", {})
    gro_p = pillars.get("grounding", {})
    cos_p = pillars.get("cost", {})
    vec_p = pillars.get("vector_density", {})

    # Helper for SVG radial gauge
    def svg_gauge(score: int, color: str, size: int = 76, stroke: int = 6) -> str:
        radius = (size - stroke) // 2
        circumference = 2 * 3.14159 * radius
        offset = circumference - (score / 100.0) * circumference
        return f"""
        <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="transform: rotate(-90deg);">
          <circle cx="{size//2}" cy="{size//2}" r="{radius}" fill="transparent" stroke="#e2e8f0" stroke-width="{stroke}" />
          <circle cx="{size//2}" cy="{size//2}" r="{radius}" fill="transparent" stroke="{color}" stroke-width="{stroke}"
                  stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}" stroke-linecap="round" />
        </svg>
        """

    # Build Opportunities HTML
    opps_html = ""
    for opp in lighthouse.get("opportunities", []):
        opps_html += f"""
        <div style="border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; background: #ffffff;">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px;">
            <h4 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0;">{opp.get('title')}</h4>
            <span style="display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 800; background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;">
              {opp.get('savings_label')}
            </span>
          </div>
          <p style="font-size: 13px; color: #475569; margin: 6px 0 10px; line-height: 1.5;">{opp.get('description')}</p>
          <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 4px;">Recommended Implementation:</div>
          <pre style="background: #0f172a; color: #f8fafc; padding: 10px 12px; border-radius: 6px; font-size: 12px; font-family: monospace; overflow-x: auto; margin: 0;">{opp.get('code_snippet')}</pre>
        </div>
        """

    # Build Audits Checklist HTML
    audits_html = ""
    for audit in lighthouse.get("audits", []):
        status_val = audit.get("status", "passed")
        is_pass = status_val == "passed"
        status_color = "#16a34a" if is_pass else "#d97706"
        icon = "[PASS]" if is_pass else "[ALERT]"

        audits_html += f"""
        <tr style="border-bottom: 1px solid #f1f5f9;">
          <td style="padding: 10px 12px; font-weight: 600; font-size: 13px; color: #0f172a;">
            <span style="display: inline-block; font-size: 11px; font-weight: 700; color: {status_color}; margin-right: 6px;">{icon}</span>
            {audit.get('title')}
            <div style="font-size: 11px; font-weight: 400; color: #64748b; margin-top: 2px;">{audit.get('description')}</div>
          </td>
          <td style="padding: 10px 12px; font-size: 13px; font-weight: 600; color: #0f172a;">{audit.get('value')}</td>
          <td style="padding: 10px 12px; font-size: 12px; color: #64748b;">{audit.get('target')}</td>
        </tr>
        """

    # Build Pipeline Waterfall HTML
    spans_html = ""
    for s in pipeline_spans:
        lat = s.get("latency_ms", 0)
        pct = s.get("pct", 0) or round(lat / max(total_latency_ms, 1) * 100, 1)
        name = s.get("name", "")
        comp = s.get("component", "")
        bar_color = "#ef4444" if lat > 1000 else ("#f59e0b" if lat > 450 else "#3b82f6")

        spans_html += f"""
        <div style="margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 600; margin-bottom: 4px;">
            <span>{name} <span style="font-weight: 400; color: #64748b;">({comp})</span></span>
            <span>{lat} ms ({pct}%)</span>
          </div>
          <div style="height: 8px; width: 100%; background: #f1f5f9; border-radius: 4px; overflow: hidden;">
            <div style="height: 100%; width: {min(max(pct, 2), 100)}%; background: {bar_color}; border-radius: 4px;"></div>
          </div>
        </div>
        """

    # Build Chunks HTML
    chunks_html = ""
    for chk in chunks:
        cid = chk.get("chunk_id", "")
        doc = chk.get("doc", "")
        size = chk.get("size_tokens", 0)
        sim = float(chk.get("similarity", 0.0))
        is_high = sim >= 0.70
        is_med = sim >= 0.50 and sim < 0.70
        badge_bg = "#ecfdf5" if is_high else ("#fffbeb" if is_med else "#fef2f2")
        badge_color = "#065f46" if is_high else ("#92400e" if is_med else "#991b1b")
        badge_label = "Strong Grounding" if is_high else ("Moderate" if is_med else "Noise / Cutoff")

        chunks_html += f"""
        <tr style="border-bottom: 1px solid #f1f5f9;">
          <td style="padding: 8px 12px; font-family: monospace; font-size: 12px; color: #64748b;">{cid}</td>
          <td style="padding: 8px 12px; font-weight: 600; font-size: 13px; color: #0f172a;">{doc}</td>
          <td style="padding: 8px 12px; font-size: 13px; color: #64748b;">{size} tokens</td>
          <td style="padding: 8px 12px; font-weight: 700; font-size: 13px; color: #0f172a;">{sim:.2f}</td>
          <td style="padding: 8px 12px;">
            <span style="display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; background: {badge_bg}; color: {badge_color};">
              {badge_label}
            </span>
          </td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lighthouse for RAG — Audit: {api_key}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #f8fafc;
      color: #0f172a;
      line-height: 1.5;
      padding: 24px 16px;
    }}
    .container {{
      max-width: 980px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .gauge-wrapper {{
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 6px;
    }}
    .gauge-circle-container {{
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .gauge-inner-text {{
      position: absolute;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }}
    .gauge-number {{
      font-size: 20px;
      font-weight: 800;
      color: #0f172a;
      line-height: 1;
    }}
    .gauge-grade {{
      font-size: 10px;
      font-weight: 700;
      color: #64748b;
      text-transform: uppercase;
      margin-top: 2px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }}
    th {{
      padding: 8px 12px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748b;
      border-bottom: 1px solid #e2e8f0;
    }}
    .golden-box {{
      background: #0f172a;
      color: #ffffff;
      border-radius: 8px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    a.btn-dashboard {{
      display: inline-block;
      background: #3b82f6;
      color: #ffffff;
      text-decoration: none;
      padding: 9px 16px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 13px;
    }}
    a.btn-dashboard:hover {{
      background: #2563eb;
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px;">
      <div>
        <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b;">
          Google Lighthouse for RAG &bull; Automated AI Performance Audit
        </span>
        <h1 style="font-size: 26px; font-weight: 800; color: #0f172a; letter-spacing: -0.02em; margin-top: 4px;">
          RAG Performance Audit
        </h1>
        <p style="font-size: 13px; color: #64748b; margin-top: 2px;">
          Evaluated via CLI &bull; Domain: <strong>{domain}</strong>
        </p>
      </div>

      <div style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 999px; background: #ecfdf5; border: 1px solid #a7f3d0; color: #065f46; font-size: 12px; font-weight: 700;">
        <span style="width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></span>
        PostgreSQL Persisted Run
      </div>
    </div>

    <!-- Golden Key Box -->
    <div class="golden-box">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
        <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8;">
          Request API Key (Indexed in PostgreSQL)
        </span>
        <span style="font-size: 12px; color: #94a3b8;">Trace ID: <code>{trace_id}</code></span>
      </div>
      <div style="font-family: monospace; font-size: 20px; font-weight: 800; color: #38bdf8;">
        {api_key}
      </div>
      <p style="font-size: 13px; color: #cbd5e1; margin: 0;">
        This exact audit report is stored in PostgreSQL. Paste this key into the RagLens Web Dashboard to explore live graphs.
      </p>
      <div>
        <a href="http://localhost:3000/raglens?key={api_key}" target="_blank" class="btn-dashboard">
          Open Live Report in Web Dashboard &rarr;
        </a>
      </div>
    </div>

    <!-- 4 Lighthouse Score Gauges Card -->
    <div class="card">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; border-bottom: 1px solid #f1f5f9; padding-bottom: 20px;">
        <!-- Overall Gauge -->
        <div style="display: flex; align-items: center; gap: 16px;">
          <div class="gauge-circle-container">
            {svg_gauge(overall_score, overall_color, size=88, stroke=8)}
            <div class="gauge-inner-text">
              <span style="font-size: 24px; font-weight: 800; color: #0f172a; line-height: 1;">{overall_score}</span>
              <span style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase; margin-top: 2px;">{overall_grade}</span>
            </div>
          </div>
          <div>
            <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em;">Overall RAG Grade</div>
            <div style="font-size: 20px; font-weight: 800; color: #0f172a; margin-top: 2px;">Grade {overall_grade} ({overall_score}/100)</div>
            <div style="font-size: 12px; color: #64748b;">Weighted multi-pillar performance index</div>
          </div>
        </div>

        <!-- 4 Pillars -->
        <div style="display: flex; gap: 24px; flex-wrap: wrap;">
          <!-- Latency -->
          <div class="gauge-wrapper">
            <div class="gauge-circle-container">
              {svg_gauge(lat_p.get('score', 80), lat_p.get('color', '#10b981'))}
              <div class="gauge-inner-text">
                <span class="gauge-number">{lat_p.get('score', 80)}</span>
                <span class="gauge-grade">{lat_p.get('grade', 'B')}</span>
              </div>
            </div>
            <span style="font-size: 12px; font-weight: 700; color: #0f172a;">Latency</span>
          </div>

          <!-- Grounding -->
          <div class="gauge-wrapper">
            <div class="gauge-circle-container">
              {svg_gauge(gro_p.get('score', 85), gro_p.get('color', '#10b981'))}
              <div class="gauge-inner-text">
                <span class="gauge-number">{gro_p.get('score', 85)}</span>
                <span class="gauge-grade">{gro_p.get('grade', 'B')}</span>
              </div>
            </div>
            <span style="font-size: 12px; font-weight: 700; color: #0f172a;">Grounding</span>
          </div>

          <!-- Cost -->
          <div class="gauge-wrapper">
            <div class="gauge-circle-container">
              {svg_gauge(cos_p.get('score', 90), cos_p.get('color', '#10b981'))}
              <div class="gauge-inner-text">
                <span class="gauge-number">{cos_p.get('score', 90)}</span>
                <span class="gauge-grade">{cos_p.get('grade', 'A')}</span>
              </div>
            </div>
            <span style="font-size: 12px; font-weight: 700; color: #0f172a;">Cost</span>
          </div>

          <!-- Vector Density -->
          <div class="gauge-wrapper">
            <div class="gauge-circle-container">
              {svg_gauge(vec_p.get('score', 75), vec_p.get('color', '#f59e0b'))}
              <div class="gauge-inner-text">
                <span class="gauge-number">{vec_p.get('score', 75)}</span>
                <span class="gauge-grade">{vec_p.get('grade', 'C')}</span>
              </div>
            </div>
            <span style="font-size: 12px; font-weight: 700; color: #0f172a;">Vector Density</span>
          </div>
        </div>
      </div>

      <!-- Query Bar -->
      <div style="margin-top: 16px;">
        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em; margin-bottom: 4px;">
          Evaluated Question
        </div>
        <div style="font-size: 15px; font-weight: 600; color: #0f172a; padding: 10px 14px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;">
          "{query}"
        </div>
      </div>
    </div>

    <!-- Opportunities Section -->
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <div>
          <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin: 0;">Lighthouse Opportunities (Estimated Savings)</h2>
          <p style="font-size: 13px; color: #64748b; margin-top: 2px;">Concrete engineering optimizations to accelerate latency and cut recurring spend.</p>
        </div>
      </div>
      {opps_html}
    </div>

    <!-- Diagnostic Audits Checklist -->
    <div class="card">
      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin-bottom: 16px;">Diagnostic Audits Checklist</h2>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Audit Item</th>
              <th>Observed Metric</th>
              <th>Target Threshold</th>
            </tr>
          </thead>
          <tbody>
            {audits_html}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pipeline Waterfall -->
    <div class="card">
      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin-bottom: 16px;">Pipeline Span Latency Breakdown</h2>
      {spans_html}
    </div>

    <!-- Chunks Retrieved -->
    <div class="card">
      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin-bottom: 16px;">Retrieved Document Chunks & Grounding</h2>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Chunk ID</th>
              <th>Source Document</th>
              <th>Tokens</th>
              <th>Similarity</th>
              <th>Grounding</th>
            </tr>
          </thead>
          <tbody>
            {chunks_html}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Footer -->
    <div style="text-align: center; font-size: 12px; color: #94a3b8; padding: 12px 0;">
      RagLens Automated AI Performance Audit &bull; PostgreSQL Telemetry Store &bull; Trace ID: {trace_id}
    </div>
  </div>
</body>
</html>
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return report_path
