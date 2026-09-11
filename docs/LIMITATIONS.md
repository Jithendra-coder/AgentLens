# M9 Limitations

M9 adds a bounded dataset/replay layer to the M2 SDK, M3 gateway, M4 storage,
M5 runtime, M6 deterministic baseline, M7 semantic evaluation, and M8 dashboard.
It is not a complete regression or quality-gate platform.

It does not provide automated retention/deletion, backups, replication,
provider auto-instrumentation, live production provider adapters, cost
calculation, or production security controls. M10 provides bounded
baseline/candidate regression comparison but not statistical significance,
deployment blocking, or a universal score; M11 provides explicit gate
decisions without owning deployment platforms. Capture is explicit;
function arguments,
environment variables, headers, locals, prompts, and outputs are not captured
automatically.

The SDK does not automatically propagate context into manually created OS
threads, does not implement async exporters, and does not provide adaptive or
distributed sampling. Trace-level errors are represented by `Status.ERROR` and
a redacted `error` event because the existing M1 `Trace` contract has no
trace-level `ErrorInfo` field.

M6 result semantics remain intentionally narrow. M8 computes trace p50/p95/p99
only for completed traces in bounded project/time windows; usage reports only fields present in observations and never
infers missing values; reliability excludes `UNSET` spans from terminal error
rates; retrieval requires caller-supplied ground truth and a retrieval span
with an output shaped as `{"documents": [{"id": "..."}]}`.

M7 semantic judgments remain model-dependent and fallible; groundedness is not
a perfect hallucination detector and reproducible configuration is not a
guarantee of identical provider output. The default build has no live provider
adapter and no semantic result cache. Semantic RAG requires explicitly named
retrieval and answer spans with bounded content; citation support is not
implemented beyond structural validity. M9 provides a bounded dataset/replay
workflow using trusted local/sandbox targets, but cannot guarantee identical
external model output, exactly-once side effects, retention enforcement,
dataset branching/merging, distributed target-rate coordination, or a large
annotation workforce. Regression metrics reuse existing evaluator results and
may remain incompatible or insufficient when provenance/data is missing.
M11 does not provide automatic rollout or semantic evaluation cost
calculation. M9/M10/M11 do not add accounts, billing, arbitrary target URLs, or
destructive runtime controls.

M11 adds policy-driven quality-gate decisions and an API-driven CI CLI, but it
does not deploy, roll back, merge, comment on pull requests, send Slack/email
notifications, install GitHub/GitLab/Jenkins integrations, or support weighted
quality trade-offs. Performance, reliability, security hardening, and
production release evidence remain M12/M13 work.
