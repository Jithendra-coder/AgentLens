# Security Model

## Security posture

AgentLens will handle data that may include secrets and customer information.
Security requirements therefore apply to collection, transport, processing,
storage, access, retention, and deletion.

## Required controls

Future milestones must address:

- least-privilege authentication and authorization
- tenant isolation
- encrypted transport and protected persistence
- API-key and secret protection
- configurable redaction and field exclusion
- payload and request limits
- retention and deletion policy enforcement
- audit logging
- safe handling of evaluator inputs and outputs

## M3 controls and limits

M3 adds Bearer API-key authentication. The in-memory registry stores SHA-256
digests of high-entropy keys and uses constant-time digest comparison; raw keys
are not placed in URLs, logs, error bodies, or safe auth context. Each key maps
to one project, and a trace whose `project_id` differs is rejected.

M3 also enforces a configurable actual-body limit, JSON content type, batch
size, process-local per-key rate limits, request IDs, and safe structured
request logging. M5 makes trace content, job metadata, attempts, and
idempotency fingerprints durable in PostgreSQL, while credentials remain
process-local. Redis carries only job IDs and is not authoritative. M5 does not implement retention,
backups, replication, field encryption, enterprise identity, or a claim of
production security. Redactor failures still drop affected traces rather than
falling back to unredacted data.

## M7 semantic-judge controls

Trace content is untrusted evidence. The semantic boundary passes only the
minimal selected question, bounded documents, answer, claims, tool calls, or
criteria, with explicit truncation metadata. Its fixed instruction says not to
follow retrieved text, call tools, access URLs, reveal configuration, or alter
criteria. The protocol has no MCP, web, filesystem, shell, database, or agent
tool access. No chain-of-thought or raw judge prompt/response is stored.

Provider adapters, when deployed, are operator-configured behind the
provider-independent `SemanticJudge` protocol. Normal evaluation requests can
choose a trusted profile but cannot provide `api_url`, provider endpoints, or
credentials, preventing tenant-controlled SSRF. The M7 default has no live
provider adapter; deterministic evaluators continue to work without one and
trace ingestion remains independent of judge availability.

Judge provenance is safe metadata: provider/model/adapter and prompt versions,
parameters, fingerprints, timestamps, and optional token usage. Tool-argument
findings identify field names and mismatch status without copying raw values.
Project-scoped result and invocation queries preserve 404 privacy semantics.

## M8 dashboard controls

The dashboard project key is server-side only. The browser calls same-origin
Next.js BFF routes, whose allowlist forwards a fixed set of GET endpoints with
the environment-configured Bearer credential. The browser cannot choose
`project_id`; FastAPI resolves it from the key on every request. Dashboard
errors preserve safe bounded messages and request IDs without returning the
credential.

Analytics predicates are project-scoped and time-bounded. Trace content is
rendered as structured data with no raw HTML, `eval`, or dangerous HTML sinks.
Runtime is read-only, and missing worker heartbeat is explicit rather than
fabricated. Reported token usage remains nullable, and judge token usage is
not merged into application usage.

## M9 dataset and replay controls

Datasets, versions, cases, replay runs, outputs, target metadata, and generated
traces are project-scoped. Cross-project lookups use the established 404
privacy behavior. Finalized dataset versions are immutable and replay manifests
persist the exact version/checksum used.

Replay target selection is a trusted operator registry lookup. Tenant requests
cannot provide URLs, module paths, scripts, commands, imports, `eval`, or
`exec`; M9 has no HTTP target adapter. Target secrets and database/Redis
credentials remain server-side. Read-only and sandbox profiles are allowed;
side-effectful profiles are rejected by default. Outputs are JSON-safe, safe
errors are bounded, and full values are not logged by default.

PostgreSQL owns replay state. Redis loss is recoverable through durable scans,
and lease claim tokens prevent stale workers from overwriting recovered
executions. Target execution is at-least-once after crashes, so M9 does not
claim exactly-once side effects. Retention/deletion enforcement for datasets,
outputs, and replay traces remains deferred.
