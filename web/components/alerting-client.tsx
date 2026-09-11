"use client";

import { useEffect, useState } from "react";

interface AlertRuleItem {
  rule_id: string;
  project_id: string;
  name: string;
  trigger_type: string;
  channel_type: string;
  destination_url: string;
  cooldown_seconds: number;
  is_enabled: boolean;
  created_at: string;
}

interface IncidentItem {
  incident_id: string;
  project_id: string;
  title: string;
  details: string;
  severity: string;
  status: string;
  acknowledged_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

interface WebhookDelivery {
  delivery_id: string;
  event_type: string;
  webhook_url: string;
  status_code: number;
  status: string;
  signature_header: string;
  timestamp: string;
  latency_ms: number;
  payload: Record<string, any>;
}

export default function MultiChannelAlertingClient() {
  const [projectId, setProjectId] = useState("proj-default");
  const [rules, setRules] = useState<AlertRuleItem[]>([]);
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State - Create Rule
  const [ruleName, setRuleName] = useState("");
  const [triggerType, setTriggerType] = useState("drift_alert");
  const [channelType, setChannelType] = useState("slack");
  const [destinationUrl, setDestinationUrl] = useState("https://hooks.slack.com/services/T00/B00/X00");
  const [cooldownSec, setCooldownSec] = useState(300);
  const [creatingRule, setCreatingRule] = useState(false);

  // Form State - Trigger Incident
  const [incTitle, setIncTitle] = useState("");
  const [incDetails, setIncDetails] = useState("");
  const [incTrigger, setIncTrigger] = useState("drift_alert");
  const [incSeverity, setIncSeverity] = useState("P2");
  const [triggeringInc, setTriggeringInc] = useState(false);
  const [lastDispatches, setLastDispatches] = useState<Array<{ channel_type: string; dispatched: boolean; reason: string }>>([]);

  // Webhook State (Level 3 Autonomous Dispatcher)
  const [webhookUrl, setWebhookUrl] = useState("https://api.acme-corp.internal/v1/webhooks/policy-alerts");
  const [webhookSecret, setWebhookSecret] = useState("whsec_live_99a8b7c6d5e4f3");
  const [webhookEventType, setWebhookEventType] = useState("policy.violation");
  const [webhookDeliveries, setWebhookDeliveries] = useState<WebhookDelivery[]>([]);
  const [dispatchingWebhook, setDispatchingWebhook] = useState(false);
  const [lastDispatchedDelivery, setLastDispatchedDelivery] = useState<WebhookDelivery | null>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const resR = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/alerts/rules`);
      if (!resR.ok) throw new Error(`HTTP ${resR.status}`);
      const dataR = await resR.json();
      setRules(dataR.rules || []);

      const resI = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/alerts/incidents`);
      if (!resI.ok) throw new Error(`HTTP ${resI.status}`);
      const dataI = await resI.json();
      setIncidents(dataI.incidents || []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load alerting data");
    } finally {
      setLoading(false);
    }
  };

  const fetchWebhooks = async () => {
    try {
      const res = await fetch("/api/rag/webhooks");
      if (res.ok) {
        const data = await res.json();
        setWebhookDeliveries(data || []);
      }
    } catch {
      // ignore
    }
  };

  const handleSendTestWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    setDispatchingWebhook(true);
    try {
      const res = await fetch("/api/rag/webhooks/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          webhook_url: webhookUrl,
          secret: webhookSecret,
          event_type: webhookEventType,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const delivery = await res.json();
      setLastDispatchedDelivery(delivery);
      setWebhookDeliveries((prev) => [delivery, ...prev]);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to dispatch test webhook");
    } finally {
      setDispatchingWebhook(false);
    }
  };

  useEffect(() => {
    void fetchData();
    void fetchWebhooks();
  }, [projectId]);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleName.trim() || !destinationUrl.trim()) return;
    setCreatingRule(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/alerts/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: ruleName.trim(),
          trigger_type: triggerType,
          channel_type: channelType,
          destination_url: destinationUrl.trim(),
          cooldown_seconds: Number(cooldownSec),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRuleName("");
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create rule");
    } finally {
      setCreatingRule(false);
    }
  };

  const handleDeleteRule = async (id: string) => {
    if (!confirm("Are you sure you want to delete this rule?")) return;
    try {
      await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/alerts/rules/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete rule");
    }
  };

  const handleTriggerIncident = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!incTitle.trim()) return;
    setTriggeringInc(true);
    try {
      const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/alerts/incidents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: incTitle.trim(),
          details: incDetails.trim() || "Anomaly detected in production telemetry stream.",
          trigger_type: incTrigger,
          severity: incSeverity,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setLastDispatches(data.dispatches || []);
      setIncTitle("");
      setIncDetails("");
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to trigger incident");
    } finally {
      setTriggeringInc(false);
    }
  };

  const handleUpdateIncidentStatus = async (id: string, newStatus: string) => {
    try {
      const res = await fetch(
        `/api/v1/projects/${encodeURIComponent(projectId)}/alerts/incidents/${encodeURIComponent(id)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: newStatus,
            user: "oncall-engineer@agentlens.io",
          }),
        }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update status");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Multi-Channel Alerting & Incident Intelligence</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Configurable notification dispatchers (Slack, PagerDuty, Webhook, Email), storm cooldown protection, and incident lifecycle management.
        </p>
      </div>

      <div className="flex items-center space-x-3">
        <label htmlFor="alerting-project-select" className="text-xs font-semibold text-muted-foreground">Project:</label>
        <select
          id="alerting-project-select"
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

      {/* Level 3: Outbound HMAC-SHA256 Signed Webhook Station */}
      <div className="p-5 border rounded-xl bg-card text-card-foreground shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b pb-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold tracking-tight">Outbound Signed Webhook Station</h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-primary/10 text-primary border border-primary/20">
                HMAC-SHA256 Cryptographic Auth
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Autonomous, signed webhook delivery pipeline for agentic alerts, refund decisions, and compliance events with signature verification.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-muted-foreground">Logged Deliveries: {webhookDeliveries.length}</span>
            <button
              onClick={() => void fetchWebhooks()}
              className="px-2.5 py-1 text-xs border rounded hover:bg-muted font-mono"
            >
              ↻ Refresh Log
            </button>
          </div>
        </div>

        {/* Dispatch Form */}
        <form onSubmit={handleSendTestWebhook} className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          <div className="md:col-span-2 space-y-1">
            <label className="text-[11px] font-semibold text-muted-foreground">Target Endpoint URL</label>
            <input
              type="url"
              required
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://api.domain.com/v1/webhooks"
              className="w-full border rounded p-2 bg-background font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[11px] font-semibold text-muted-foreground">Signing Secret (HMAC-SHA256)</label>
            <input
              type="text"
              required
              value={webhookSecret}
              onChange={(e) => setWebhookSecret(e.target.value)}
              placeholder="whsec_..."
              className="w-full border rounded p-2 bg-background font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[11px] font-semibold text-muted-foreground">Event Type</label>
            <div className="flex gap-2">
              <select
                value={webhookEventType}
                onChange={(e) => setWebhookEventType(e.target.value)}
                className="w-full border rounded p-2 bg-background text-xs"
              >
                <option value="policy.violation">policy.violation</option>
                <option value="refund.approved">refund.approved</option>
                <option value="refund.denied">refund.denied</option>
                <option value="audit.conflict_detected">audit.conflict_detected</option>
                <option value="trace.error">trace.error</option>
                <option value="budget.exceeded">budget.exceeded</option>
              </select>
              <button
                type="submit"
                disabled={dispatchingWebhook}
                className="px-4 py-2 rounded bg-foreground text-background font-semibold hover:opacity-90 disabled:opacity-50 whitespace-nowrap text-xs shadow-sm"
              >
                {dispatchingWebhook ? "Signing..." : "⚡ Send Ping"}
              </button>
            </div>
          </div>
        </form>

        {/* Last Dispatched Feedback */}
        {lastDispatchedDelivery && (
          <div className="p-3.5 border rounded-lg bg-emerald-500/5 dark:bg-emerald-950/20 border-emerald-500/30 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="font-semibold text-foreground">Delivery Succeeded (HTTP {lastDispatchedDelivery.status_code} OK)</span>
                <span className="text-[10px] font-mono text-muted-foreground">· Latency: {lastDispatchedDelivery.latency_ms}ms</span>
              </div>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                VERIFIED HMAC-SHA256 SIGNATURE
              </span>
            </div>
            <div className="font-mono text-[11px] text-muted-foreground break-all bg-background/80 p-2 rounded border">
              <span className="font-bold text-foreground">X-AgentLens-Signature:</span> {lastDispatchedDelivery.signature_header}
            </div>
            <div className="font-mono text-[10px] text-muted-foreground bg-background/60 p-2 rounded border overflow-x-auto max-h-32">
              <pre>{JSON.stringify(lastDispatchedDelivery.payload, null, 2)}</pre>
            </div>
          </div>
        )}

        {/* Deliveries History Table */}
        <div className="space-y-2 pt-1">
          <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Recent Signed Deliveries Log ({webhookDeliveries.length})
          </div>
          {webhookDeliveries.length === 0 ? (
            <div className="p-3 border rounded text-xs text-muted-foreground text-center font-mono">
              No webhook deliveries recorded yet. Click &quot;⚡ Send Ping&quot; above to dispatch a cryptographically signed payload.
            </div>
          ) : (
            <div className="overflow-x-auto border rounded-lg">
              <table className="w-full text-xs text-left">
                <thead className="bg-muted/40 text-muted-foreground border-b text-[11px]">
                  <tr>
                    <th className="py-2 px-3">Status</th>
                    <th className="py-2 px-3">Event Type</th>
                    <th className="py-2 px-3">Destination</th>
                    <th className="py-2 px-3">HMAC-SHA256 Signature</th>
                    <th className="py-2 px-3">Latency</th>
                    <th className="py-2 px-3 text-right">Delivered At</th>
                  </tr>
                </thead>
                <tbody className="divide-y font-mono text-[11px]">
                  {webhookDeliveries.slice(0, 5).map((del) => (
                    <tr key={del.delivery_id} className="hover:bg-muted/20">
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                          {del.status_code} OK
                        </span>
                      </td>
                      <td className="py-2 px-3 font-medium text-foreground">
                        {del.event_type}
                      </td>
                      <td className="py-2 px-3 text-muted-foreground truncate max-w-[200px]" title={del.webhook_url}>
                        {del.webhook_url}
                      </td>
                      <td className="py-2 px-3 text-muted-foreground truncate max-w-[180px]" title={del.signature_header}>
                        {del.signature_header}
                      </td>
                      <td className="py-2 px-3 text-muted-foreground">
                        {del.latency_ms} ms
                      </td>
                      <td className="py-2 px-3 text-right text-muted-foreground">
                        {new Date(del.timestamp).toLocaleTimeString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Grid: Rules & Trigger Simulation */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Rules Card */}
        <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
          <h2 className="text-sm font-semibold">Notification Routing Rules</h2>
          {loading ? (
            <div className="text-xs text-muted-foreground">Loading rules...</div>
          ) : rules.length === 0 ? (
            <div className="p-3 border rounded text-xs text-muted-foreground text-center">
              No alert routing rules configured.
            </div>
          ) : (
            <div className="space-y-2">
              {rules.map((r) => (
                <div key={r.rule_id} className="p-3 border rounded-lg text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">{r.name}</span>
                    <button
                      onClick={() => handleDeleteRule(r.rule_id)}
                      className="text-[10px] text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                  <div className="flex items-center space-x-2 text-[11px] font-mono">
                    <span className="px-1.5 py-0.5 rounded bg-muted uppercase">{r.channel_type}</span>
                    <span className="text-muted-foreground">Trigger: {r.trigger_type}</span>
                  </div>
                  <div className="text-[10px] text-muted-foreground truncate font-mono">
                    {r.destination_url}
                  </div>
                  <div className="text-[10px] text-muted-foreground font-mono">
                    Cooldown: {r.cooldown_seconds}s
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* New Rule Form */}
          <form onSubmit={handleCreateRule} className="pt-3 border-t space-y-2">
            <h3 className="text-xs font-semibold">Create Routing Rule</h3>
            <input
              type="text"
              required
              value={ruleName}
              onChange={(e) => setRuleName(e.target.value)}
              placeholder="Rule Name (e.g. Prod P1 Alerts)"
              className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
            />
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-muted-foreground">Trigger</label>
                <select
                  value={triggerType}
                  onChange={(e) => setTriggerType(e.target.value)}
                  className="w-full text-xs border rounded p-1 bg-background text-foreground"
                >
                  <option value="drift_alert">Drift Alert</option>
                  <option value="health_critical">Health Critical</option>
                  <option value="budget_exhausted">Budget Exhausted</option>
                  <option value="quality_gate_fail">Quality Gate Fail</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground">Channel</label>
                <select
                  value={channelType}
                  onChange={(e) => setChannelType(e.target.value)}
                  className="w-full text-xs border rounded p-1 bg-background text-foreground"
                >
                  <option value="slack">Slack</option>
                  <option value="pagerduty">PagerDuty</option>
                  <option value="webhook">Webhook</option>
                  <option value="email">Email</option>
                </select>
              </div>
            </div>
            <input
              type="text"
              required
              value={destinationUrl}
              onChange={(e) => setDestinationUrl(e.target.value)}
              placeholder="Destination URL (Webhook / Endpoint)"
              className="w-full text-xs border rounded p-1.5 bg-background text-foreground font-mono"
            />
            <div>
              <label className="text-[10px] text-muted-foreground">Cooldown (seconds)</label>
              <input
                type="number"
                min="0"
                max="86400"
                value={cooldownSec}
                onChange={(e) => setCooldownSec(Number(e.target.value))}
                className="w-full text-xs border rounded p-1 bg-background text-foreground font-mono"
              />
            </div>
            <button
              type="submit"
              disabled={creatingRule}
              className="w-full py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {creatingRule ? "Saving..." : "Add Rule"}
            </button>
          </form>
        </div>

        {/* Incident Trigger & Lifecycle Management */}
        <div className="lg:col-span-2 space-y-6">
          {/* Incident Trigger Simulator */}
          <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
            <h2 className="text-sm font-semibold">Simulate / Trigger Incident</h2>
            <form onSubmit={handleTriggerIncident} className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-2 space-y-1">
                  <label className="text-[11px] font-semibold">Incident Title</label>
                  <input
                    type="text"
                    required
                    value={incTitle}
                    onChange={(e) => setIncTitle(e.target.value)}
                    placeholder="e.g. Critical Latency Spike on Reasoning Pipeline"
                    className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold">Severity</label>
                  <select
                    value={incSeverity}
                    onChange={(e) => setIncSeverity(e.target.value)}
                    className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
                  >
                    <option value="P1">P1 - Critical</option>
                    <option value="P2">P2 - Major</option>
                    <option value="P3">P3 - Minor</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-2 space-y-1">
                  <label className="text-[11px] font-semibold">Details</label>
                  <input
                    type="text"
                    value={incDetails}
                    onChange={(e) => setIncDetails(e.target.value)}
                    placeholder="Describe failure symptoms and context..."
                    className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold">Trigger Event Type</label>
                  <select
                    value={incTrigger}
                    onChange={(e) => setIncTrigger(e.target.value)}
                    className="w-full text-xs border rounded p-1.5 bg-background text-foreground"
                  >
                    <option value="drift_alert">Drift Alert</option>
                    <option value="health_critical">Health Critical</option>
                    <option value="budget_exhausted">Budget Exhausted</option>
                    <option value="quality_gate_fail">Quality Gate Fail</option>
                  </select>
                </div>
              </div>
              <button
                type="submit"
                disabled={triggeringInc}
                className="px-4 py-2 text-xs font-semibold rounded bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
              >
                {triggeringInc ? "Dispatching..." : "Trigger Incident & Dispatch Alerts"}
              </button>
            </form>

            {/* Last Dispatch Feedback */}
            {lastDispatches.length > 0 && (
              <div className="p-3 border rounded bg-accent/20 space-y-1 text-xs">
                <span className="font-semibold text-muted-foreground text-[10px] uppercase">Alert Dispatch Results:</span>
                {lastDispatches.map((d, idx) => (
                  <div key={idx} className="font-mono text-[11px]">
                    <span className={d.dispatched ? "text-green-600 font-bold" : "text-yellow-600 font-bold"}>
                      [{d.channel_type.toUpperCase()}]
                    </span>{" "}
                    {d.reason}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Incidents Triage Table */}
          <div className="p-4 border rounded-lg bg-card text-card-foreground shadow-sm space-y-3">
            <h2 className="text-sm font-semibold">Incident Triage & State Board</h2>
            {incidents.length === 0 ? (
              <div className="text-xs text-muted-foreground">No recorded incidents.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b text-muted-foreground">
                      <th className="pb-2">Severity</th>
                      <th className="pb-2">Title</th>
                      <th className="pb-2">Status</th>
                      <th className="pb-2">Acknowledged By</th>
                      <th className="pb-2">Created</th>
                      <th className="pb-2 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {incidents.map((inc) => (
                      <tr key={inc.incident_id}>
                        <td className="py-2.5">
                          <span
                            className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                              inc.severity === "P1"
                                ? "bg-red-500/20 text-red-700 dark:text-red-300"
                                : inc.severity === "P2"
                                ? "bg-yellow-500/20 text-yellow-700 dark:text-yellow-300"
                                : "bg-blue-500/20 text-blue-700 dark:text-blue-300"
                            }`}
                          >
                            {inc.severity}
                          </span>
                        </td>
                        <td className="py-2.5 font-medium">
                          <div>{inc.title}</div>
                          <div className="text-[11px] text-muted-foreground truncate max-w-xs">{inc.details}</div>
                        </td>
                        <td className="py-2.5">
                          <span
                            className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] uppercase ${
                              inc.status === "resolved"
                                ? "bg-green-500/20 text-green-700 dark:text-green-300"
                                : inc.status === "acknowledged"
                                ? "bg-blue-500/20 text-blue-700 dark:text-blue-300"
                                : "bg-red-500/20 text-red-700 dark:text-red-300"
                            }`}
                          >
                            {inc.status}
                          </span>
                        </td>
                        <td className="py-2.5 font-mono text-[11px] text-muted-foreground">
                          {inc.acknowledged_by || "—"}
                        </td>
                        <td className="py-2.5 font-mono text-[11px] text-muted-foreground">
                          {new Date(inc.created_at).toLocaleTimeString()}
                        </td>
                        <td className="py-2.5 text-right space-x-2 font-mono">
                          {inc.status === "open" && (
                            <button
                              onClick={() => handleUpdateIncidentStatus(inc.incident_id, "acknowledged")}
                              className="px-2 py-1 bg-secondary text-secondary-foreground rounded text-[10px] font-semibold hover:bg-secondary/80"
                            >
                              Acknowledge
                            </button>
                          )}
                          {inc.status !== "resolved" && (
                            <button
                              onClick={() => handleUpdateIncidentStatus(inc.incident_id, "resolved")}
                              className="px-2 py-1 bg-green-600 text-white rounded text-[10px] font-semibold hover:bg-green-700"
                            >
                              Resolve
                            </button>
                          )}
                        </td>
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
