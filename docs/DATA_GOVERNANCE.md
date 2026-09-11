# Data Governance

## Sensitive by default

Trace payloads may contain user prompts, customer data, internal documents,
model outputs, database-derived content, tool arguments and results, API
responses, or secrets accidentally included by an application. Treat every
payload as potentially sensitive unless policy proves otherwise.

## Future obligations

The architecture must support:

- collection minimization
- redaction hooks and field exclusion
- configurable retention and deletion
- tenant isolation
- secret detection
- payload-size limits
- API-key protection
- auditability
- secure transport
- secure persistence

M0 records these obligations. M2 adds explicit capture-time redaction hooks,
M3 adds a bounded project-scoped HTTP data plane, M4 adds durable PostgreSQL
trace storage, and M5 adds durable job metadata and safe attempt records. M5
stores only job configuration and bounded errors; Redis carries only job IDs.
M4/M5 do not provide retention enforcement, deletion,
credential management, backups, or audit storage.
Redactor failures must not fall back to unredacted payloads, and gateway logs
must not include request bodies or raw authorization headers.

## Evaluation data

Evaluation outputs are derived records. They must reference the observed input
and preserve evaluator provenance without rewriting the source observation.
M6 results store the project/trace/job identity, evaluator name/version,
normalized configuration, configuration fingerprint, trace fingerprint,
metrics, findings, and evidence in an append-only table. Result payloads are
JSON-safe and immutable at the model boundary. Retrieval ground truth is
explicit caller input and may itself be sensitive; it receives the same
project isolation and retention obligations as trace data. M6 does not add
retention, deletion, audit, or field-level encryption controls.

M7 semantic results add only safe judge provenance and structured findings.
Bounded judge evidence is not copied into the result by default; result
evidence references document or claim IDs, and a separate invocation row stores
provider/model/prompt/config fingerprints rather than raw prompts, responses,
credentials, or hidden reasoning. Judge token usage is evaluation overhead and
is never merged into application span usage. Semantic evaluation remains
model-dependent and subject to the same retention, deletion, tenant-isolation,
and sensitivity obligations as the source trace.
