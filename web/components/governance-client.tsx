"use client";

import { useEffect, useState } from "react";

interface AuditEventItem {
  event_id: string;
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  payload_hash: string;
  previous_event_hash: string;
  event_hash: string;
  timestamp: string;
}

interface RetentionPolicyItem {
  policy_id: string;
  project_id: string;
  name: string;
  retention_days: number;
  auto_redact_pii: boolean;
  is_active: boolean;
  created_at: string;
}

interface AuditVerificationSummary {
  project_id: string;
  is_valid: boolean;
  total_events: number;
  verification_status: string;
  reason: string;
  compromised_event_id: string | null;
  events: AuditEventItem[];
}

export default function GovernanceComplianceClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [verification, setVerification] = useState<AuditVerificationSummary | null>(null);
  const [policies, setPolicies] = useState<RetentionPolicyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State - Record Audit Action
  const [auditAction, setAuditAction] = useState("secret.rotate");
  const [resourceType, setResourceType] = useState("secret");
  const [resourceId, setResourceId] = useState("sec-prod-openai");
  const [payloadStr, setPayloadStr] = useState('{"rotation_reason":"quarterly_compliance"}');
  const [recordingAudit, setRecordingAudit] = useState(false);

  // Form State - Retention Policy
  const [policyName, setPolicyName] = useState("");
  const [retentionDays, setRetentionDays] = useState(90);
  const [autoRedactPii, setAutoRedactPii] = useState(true);
  const [creatingPolicy, setCreatingPolicy] = useState(false);

  // Export State
  const [exporting, setExporting] = useState(false);
  const [lastExport, setLastExport] = useState<{
    export_id: string;
    root_hash: string;
    digital_signature: string;
    total_audit_events: number;
    exported_at: string;
  } | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const resA = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/governance/audit`);
      if (!resA.ok) throw new Error(`HTTP ${resA.status}`);
      const dataA = await resA.json();
      setVerification(dataA);

      const resP = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/governance/policies`);
      if (!resP.ok) throw new Error(`HTTP ${resP.status}`);
      const dataP = await resP.json();
      setPolicies(dataP.policies || []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load governance data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
  }, [projectId]);

  const handleRecordAuditEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    setRecordingAudit(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/governance/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: auditAction.trim(),
          resource_type: resourceType.trim(),
          resource_id: resourceId.trim(),
          payload: payloadStr.trim(),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to append audit event");
    } finally {
      setRecordingAudit(false);
    }
  };

  const handleCreatePolicy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!policyName.trim()) return;
    setCreatingPolicy(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/governance/policies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: policyName.trim(),
          retention_days: Number(retentionDays),
          auto_redact_pii: autoRedactPii,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setPolicyName("");
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create policy");
    } finally {
      setCreatingPolicy(false);
    }
  };

  const handleDeletePolicy = async (id: string) => {
    if (!confirm("Delete retention policy?")) return;
    try {
      await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/governance/policies/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete policy");
    }
  };

  const handleGenerateExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/governance/export`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setLastExport(data);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Enterprise Governance, Audit Trail & Data Retention</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Cryptographically chained immutable SHA-256 audit logs, automated GDPR/HIPAA retention policies, and verifiable compliance bundles.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="governance-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="governance-project-select"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="text-xs border rounded px-2.5 py-1 bg-background text-foreground"
        >
          <option value="proj-default">proj-default</option>
          <option value="proj-prod">proj-prod</option>
          <option value="proj-staging">proj-staging</option>
        </select>
      </div>

      {error && <div className="p-3 text-xs text-destructive bg-destructive/10 rounded">{error}</div>}

      {/* Cryptographic Hash Chain Verification Card */}
      {verification && (
        <div className="p-6 border rounded-lg bg-card text-card-foreground shadow-sm flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="space-y-1">
            <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Cryptographic Hash Chain Integrity
            </h2>
            <div className="flex items-center space-x-3">
              <span
                className={`px-3 py-1 rounded text-xs font-bold font-mono uppercase tracking-wider ${
                  verification.is_valid
                    ? "bg-green-500/20 text-green-700 dark:text-green-300"
                    : "bg-red-500/20 text-red-700 dark:text-red-300"
                }`}
              >
                {verification.verification_status}
              </span>
              <span className="text-xs text-muted-foreground font-mono">
                ({verification.total_events} Chained Blocks)
              </span>
            </div>
            <p className="text-xs text-muted-foreground font-mono">{verification.reason}</p>
          </div>

          <button
            onClick={handleGenerateExport}
            disabled={exporting}
            className="px-4 py-2.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {exporting ? "Generating Signed Bundle..." : "Generate Compliance Export Bundle"}
          </button>
        </div>
      )}

      {/* Export Feedback Modal / Card */}
      {lastExport && (
        <div className="p-4 border-2 border-primary/40 rounded-lg bg-primary/5 space-y-2 text-xs font-mono">
          <div className="flex items-center justify-between">
            <span className="font-bold text-primary uppercase text-[11px]">Attested Compliance Bundle</span>
            <span className="text-[10px] text-muted-foreground">{new Date(lastExport.exported_at).toLocaleString()}</span>
          </div>
          <div><span className="text-muted-foreground">ROOT HASH:</span> {lastExport.root_hash}</div>
          <div><span className="text-muted-foreground">SIGNATURE:</span> {lastExport.digital_signature}</div>
          <div><span className="text-muted-foreground">TOTAL EVENTS:</span> {lastExport.total_audit_events}</div>
        </div>
      )}

      {/* Two-Column Grid: Policies & Record Action */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Retention Policies Card */}
        <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
          <h2 className="text-sm font-semibold">Data Retention Policies</h2>
          {loading ? (
            <div className="text-xs text-muted-foreground">Loading policies...</div>
          ) : policies.length === 0 ? (
            <div className="p-3 border rounded text-xs text-muted-foreground text-center">
              No retention policies active.
            </div>
          ) : (
            <div className="space-y-2">
              {policies.map((p) => (
                <div key={p.policy_id} className="p-3 border rounded-lg text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">{p.name}</span>
                    <button
                      onClick={() => handleDeletePolicy(p.policy_id)}
                      className="text-[10px] text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                  <div className="text-[11px] font-mono text-muted-foreground">
                    Retention: {p.retention_days} Days | PII Redaction: {p.auto_redact_pii ? "Enabled" : "Disabled"}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* New Policy Form */}
          <form onSubmit={handleCreatePolicy} className="pt-3 border-t space-y-2">
            <h3 className="text-xs font-semibold">New Retention Policy</h3>
            <input
              type="text"
              required
              value={policyName}
              onChange={(e) => setPolicyName(e.target.value)}
              placeholder="Policy Name (e.g. GDPR 90-Day Telemetry)"
              className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
            />
            <div>
              <label className="text-[10px] text-muted-foreground">Retention Period (Days)</label>
              <input
                type="number"
                min="1"
                max="3650"
                value={retentionDays}
                onChange={(e) => setRetentionDays(Number(e.target.value))}
                className="w-full text-xs border rounded p-1 bg-background text-foreground font-mono"
              />
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="pii-check"
                checked={autoRedactPii}
                onChange={(e) => setAutoRedactPii(e.target.checked)}
                className="rounded"
              />
              <label htmlFor="pii-check" className="text-xs text-muted-foreground">
                Automated PII Redaction
              </label>
            </div>
            <button
              type="submit"
              disabled={creatingPolicy}
              className="w-full py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {creatingPolicy ? "Saving..." : "Create Policy"}
            </button>
          </form>
        </div>

        {/* Append Audit Event Form & Live Log */}
        <div className="lg:col-span-2 space-y-6">
          {/* Append Audit Action Form */}
          <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
            <h2 className="text-sm font-semibold">Record Cryptographic Audit Action</h2>
            <form onSubmit={handleRecordAuditEvent} className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] text-muted-foreground">Action</label>
                  <input
                    type="text"
                    required
                    value={auditAction}
                    onChange={(e) => setAuditAction(e.target.value)}
                    placeholder="e.g. user.grant_role"
                    className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground">Resource Type</label>
                  <input
                    type="text"
                    required
                    value={resourceType}
                    onChange={(e) => setResourceType(e.target.value)}
                    placeholder="e.g. role"
                    className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground">Resource ID</label>
                  <input
                    type="text"
                    required
                    value={resourceId}
                    onChange={(e) => setResourceId(e.target.value)}
                    placeholder="e.g. role-org-admin"
                    className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                  />
                </div>
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground">Payload Context (JSON)</label>
                <input
                  type="text"
                  value={payloadStr}
                  onChange={(e) => setPayloadStr(e.target.value)}
                  className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
                />
              </div>
              <button
                type="submit"
                disabled={recordingAudit}
                className="px-4 py-2 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {recordingAudit ? "Chaining Block..." : "Append to SHA-256 Hash Chain"}
              </button>
            </form>
          </div>

          {/* Immutable Audit Trail Table */}
          <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
            <h2 className="text-sm font-semibold">Immutable Audit Trail Logs</h2>
            {verification?.events.length === 0 ? (
              <div className="text-xs text-muted-foreground">No audit events recorded.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="pb-2">Action</th>
                      <th className="pb-2">Actor</th>
                      <th className="pb-2">Resource</th>
                      <th className="pb-2 font-mono">Block Hash</th>
                      <th className="pb-2 text-right">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y font-mono">
                    {verification?.events.map((ev) => (
                      <tr key={ev.event_id}>
                        <td className="py-2.5 font-bold text-foreground">{ev.action}</td>
                        <td className="py-2.5 text-muted-foreground">{ev.actor_id}</td>
                        <td className="py-2.5 text-muted-foreground">{ev.resource_type}:{ev.resource_id}</td>
                        <td className="py-2.5 text-foreground truncate max-w-[120px]">{ev.event_hash}</td>
                        <td className="py-2.5 text-right text-muted-foreground">{new Date(ev.timestamp).toLocaleTimeString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
