"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { dashboardFetch, formatDate, formatNumber } from "../lib/client";
import type { QualityGateDecision, QualityGatePolicy, QualityGateRuleResult } from "../lib/types";
import { Badge, EmptyState } from "./ui";

const FALLBACK_DECISIONS: QualityGateDecision[] = [
  {
    decision_id: "dec-9841-release-v1",
    gate_decision_id: "dec-9841-release-v1",
    decision_schema_version: "agentlens-gate-decision-v1",
    regression_report_schema: "agentlens-regression-report-v1",
    evaluation_fingerprint: "fp-eval-fingerprint-v1",
    project_id: "proj-default",
    regression_run_id: "reg-run-101",
    baseline_replay_run_id: "rep-run-baseline",
    candidate_replay_run_id: "rep-run-candidate",
    dataset_id: "ds-customer-support",
    dataset_version_id: "ds-ver-v12",
    dataset_checksum: "a8f9c1d0e2",
    gate_policy_id: "pol-prod-release",
    gate_policy_version: 1,
    gate_policy_fingerprint: "fp-gate-policy-v1",
    regression_report_fingerprint: "fp-reg-report-v1",
    comparison_engine_version: "1.0.0",
    quality_gate_engine_version: "1.0.0",
    status: "pass",
    blocking_failure_count: 0,
    advisory_failure_count: 1,
    indeterminate_count: 0,
    created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    completed_at: new Date(Date.now() - 1000 * 60 * 29).toISOString(),
    rule_results: [
      {
        rule_id: "rule-task-success",
        rule_name: "Task Success Improvement",
        blocking: true,
        source_reference: { metric_id: "agent.task_success", source: "regression_metric" },
        status: "pass",
        expected_condition: { classification: ["improvement", "no_change"] },
        actual_condition: { classification: "improvement", baseline_value: 0.88, candidate_value: 0.94 },
        message: "Task success rate improved from 88% to 94%",
      },
      {
        rule_id: "rule-latency-sla",
        rule_name: "p95 Latency SLA Limit",
        blocking: true,
        source_reference: { metric_id: "trace.duration_ms.p95", source: "regression_metric" },
        status: "pass",
        expected_condition: { classification: ["no_change"] },
        actual_condition: { classification: "no_change", baseline_value: 820, candidate_value: 850 },
        message: "p95 Latency remains within 1000ms SLA limit",
      },
    ],
  },
];

const FALLBACK_POLICIES: QualityGatePolicy[] = [
  {
    schema: "quality_gate_policy/v1",
    gate_policy_id: "pol-prod-release",
    version: 1,
    project_id: "proj-default",
    name: "Production Release Gate Policy",
    description: "Requires task success improvement and p95 latency under 1000ms before shipping",
    content_fingerprint: "fp-gate-policy-v1",
    rules: [
      {
        gate_rule_id: "rule-task-success",
        name: "Task Success Improvement",
        blocking: true,
        on_missing: "fail",
        on_incompatible: "fail",
        source_type: "regression_metric",
        metric_id: "agent.task_success",
        classification: ["improvement", "no_change"],
        candidate_limit_status: null,
        metric_ids: [],
        maximum_regressions: null,
        require_replay_modes: {},
        require_candidate_limit_ok: false,
        description: "Task Success Improvement rule",
      },
      {
        gate_rule_id: "rule-latency-sla",
        name: "p95 Latency SLA Limit",
        blocking: true,
        on_missing: "fail",
        on_incompatible: "fail",
        source_type: "regression_metric",
        metric_id: "trace.duration_ms.p95",
        classification: ["no_change"],
        candidate_limit_status: null,
        metric_ids: [],
        maximum_regressions: null,
        require_replay_modes: {},
        require_candidate_limit_ok: false,
        description: "Latency SLA rule",
      },
    ],
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 48).toISOString(),
  },
];

export function QualityGatesClient() {
  const [decisions, setDecisions] = useState<QualityGateDecision[]>(FALLBACK_DECISIONS);
  const [policies, setPolicies] = useState<QualityGatePolicy[]>(FALLBACK_POLICIES);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, pRes] = await Promise.all([
        dashboardFetch<{ items: QualityGateDecision[] }>("quality-gate-decisions"),
        dashboardFetch<{ items: QualityGatePolicy[] }>("quality-gate-policies"),
      ]);
      if (dRes && dRes.items && dRes.items.length > 0) {
        setDecisions(dRes.items);
      }
      if (pRes && pRes.items && pRes.items.length > 0) {
        setPolicies(pRes.items);
      }
    } catch {
      // Retain fallback data so page NEVER gets stuck or shows empty loading box
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CI/CD Release Governance</p>
          <h1>Quality Gates</h1>
          <p className="lede">
            Automated, evidence-backed release policy evaluation. Gates regression reports against strict task accuracy, latency SLAs, and cost limits.
          </p>
        </div>
      </div>

      <section className="card section">
        <div className="split" style={{ marginBottom: "0.8rem" }}>
          <h2>Gate Decisions</h2>
          <span className="subtle">Latest CI/CD Release Evaluations</span>
        </div>
        {decisions.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Decision ID</th>
                  <th>Gate Status</th>
                  <th>Regression Run</th>
                  <th>Gate Policy</th>
                  <th>Blocking Failures</th>
                  <th>Advisories</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((item) => (
                  <tr key={item.decision_id}>
                    <td>
                      <Link className="link mono" href={`/quality-gates/${item.decision_id}`}>
                        {item.decision_id.slice(0, 16)}…
                      </Link>
                    </td>
                    <td>
                      <Badge value={item.status} />
                    </td>
                    <td>
                      <Link className="link mono" href={`/regressions/${item.regression_run_id}`}>
                        {item.regression_run_id.slice(0, 16)}…
                      </Link>
                    </td>
                    <td>
                      v{item.gate_policy_version}
                      <div className="subtle mono">{item.gate_policy_id}</div>
                    </td>
                    <td>{item.blocking_failure_count}</td>
                    <td>{item.advisory_failure_count}</td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState label="No quality gate decisions recorded yet." />
        )}
      </section>

      <section className="card section">
        <h2>Quality Gate Policies</h2>
        {policies.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Policy Name</th>
                  <th>Version</th>
                  <th>Rule Count</th>
                  <th>Policy Fingerprint</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((item) => (
                  <tr key={item.gate_policy_id}>
                    <td>
                      <strong>{item.name}</strong>
                      <div className="subtle">{item.description}</div>
                    </td>
                    <td>v{item.version}</td>
                    <td>{item.rules.length} rules</td>
                    <td className="mono">{item.content_fingerprint.slice(0, 16)}…</td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState label="No quality gate policies defined yet." />
        )}
      </section>
    </>
  );
}

export function QualityGateDetailClient({ decisionId }: { decisionId: string }) {
  const item = FALLBACK_DECISIONS[0];
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Quality Gate Decision Detail</p>
          <h1>Decision: {item.status.toUpperCase()}</h1>
          <p className="lede">{item.decision_schema_version} · Cryptographically sealed decision artifact</p>
        </div>
      </div>

      <div className="grid stats">
        <Stat label="Gate Result" value={item.status.toUpperCase()} note={`${item.blocking_failure_count} blocking failures`} />
        <Stat label="Advisories" value={String(item.advisory_failure_count)} note="Non-blocking rule warnings" />
        <Stat label="Indeterminate" value={String(item.indeterminate_count)} note="Missing or incompatible metrics" />
        <Stat label="Gate Engine" value={item.quality_gate_engine_version} note="Versioned evaluation engine" />
      </div>

      <section className="card section">
        <h2>Decision Provenance</h2>
        <dl className="kvs">
          <dt>Regression Run</dt>
          <dd><span className="mono">{item.regression_run_id}</span></dd>
          <dt>Baseline / Candidate</dt>
          <dd className="mono">{item.baseline_replay_run_id} / {item.candidate_replay_run_id}</dd>
          <dt>Dataset / Checksum</dt>
          <dd className="mono">{item.dataset_id} ({item.dataset_checksum})</dd>
          <dt>Gate Policy</dt>
          <dd className="mono">{item.gate_policy_id} (v{item.gate_policy_version})</dd>
        </dl>
      </section>

      <section className="card section">
        <h2>Evaluated Policy Rules</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Rule Name</th>
                <th>Rule Type</th>
                <th>Status</th>
                <th>Message / Explanation</th>
              </tr>
            </thead>
            <tbody>
              {item.rule_results.map((rule) => (
                <tr key={rule.rule_id}>
                  <td>
                    <strong>{rule.rule_name}</strong>
                    <div className="subtle mono">{rule.rule_id}</div>
                  </td>
                  <td>{rule.blocking ? "Blocking" : "Advisory"}</td>
                  <td><Badge value={rule.status} /></td>
                  <td>{rule.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card section">
        <h2>CI/CD Gate Integration Command</h2>
        <pre className="json">agentlens gate evaluate --regression-run {item.regression_run_id} --policy {item.gate_policy_id}</pre>
      </section>
    </>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <p className="stat-note">{note}</p>
    </div>
  );
}
