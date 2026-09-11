# AgentLens Quality Gates

M11 adds a release-decision layer above M10. M10 remains diagnostic: it
compares immutable baseline and candidate replays and reports independent
metric classifications, limits, provenance, and data availability. M11 reads
that completed report and evaluates an immutable, versioned quality-gate
policy. It never changes the report, recalculates a metric, or calls an
evaluator/provider.

```text
Dataset version -> replays -> M10 regression report -> M11 policy
  -> immutable gate decision -> AgentLens CLI -> CI exit code
```

## Policy and rule model

Policies use `agentlens-quality-gate-policy-v1`. Each creation is immutable;
reusing a policy name creates the next version. The policy fingerprint is
stored in every decision. Rules are finite data, not Python, SQL, shell, or
arbitrary expressions.

Supported sources are `metric_classification`, `candidate_limit`,
`regression_count`, `required_metric_availability`, `replay_reproducibility`,
and `execution_failure`.

A rule is `blocking: true` by default. A non-blocking failed rule is an
advisory and cannot fail the gate. Rules do not compensate for one another:
an improved quality metric does not cancel a blocking latency regression.

Missing or incompatible evidence uses an explicit `on_missing` or
`on_incompatible` value: `fail`, `indeterminate`, or `ignore`. The secure
default for a blocking rule is `indeterminate`. M10's `incompatible` result is
never numerically compared by M11.

Hard candidate limits are consumed from M10's `candidate_limit_status`; M11
does not recompute the threshold. Replay rules compare persisted manifest
modes (`exact`, `controlled`, or `best_effort`) against the policy's allowed
modes.

## Decision model

Decisions use `agentlens-quality-gate-decision-v1` and persist the decision
status, every rule result, blocking/advisory/indeterminate counts, dataset and
replay provenance, the M10 report fingerprint, the gate-policy fingerprint,
the comparison-engine version, and the quality-gate-engine version. Completed
decisions are append-only. A changed policy, report, evaluator, or engine
requires a new decision.

Statuses are:

- `passed`: every blocking rule passed or was explicitly ignored.
- `failed`: at least one blocking rule failed.
- `indeterminate`: no blocking rule failed, but required blocking evidence was
  unavailable or incompatible and policy chose indeterminate.
- `error`: reserved for operational execution errors; it is not a candidate
  failure.

## API

The authenticated project-scoped endpoints are:

```text
POST /v1/quality-gate-policies
GET  /v1/quality-gate-policies
GET  /v1/quality-gate-policies/{policy_id}

POST /v1/quality-gate-decisions
GET  /v1/quality-gate-decisions
GET  /v1/quality-gate-decisions/{decision_id}
```

Decision creation accepts `regression_run_id` and `gate_policy_id` and rejects
non-terminal M10 reports. `Idempotency-Key` is optional; within a project,
repeating the same key and request returns the same decision while reusing the
key for a different request returns `409`. Cross-project resources preserve
the existing `404` privacy behavior.

## CLI and CI

The CLI is API-driven and uses the standard library HTTP client. Keep secrets
in environment variables:

```bash
export AGENTLENS_API_URL=https://agentlens.example
export AGENTLENS_API_KEY=replace-with-ci-secret

agentlens gate evaluate \
  --regression-run <m10-regression-run-id> \
  --policy <quality-gate-policy-id>
```

Use `--format json` for automation. Human output is concise and lists failed
or indeterminate rules. Stable exit codes are:

| Exit | Meaning |
| ---: | --- |
| 0 | Gate passed |
| 1 | Gate failed |
| 2 | Gate indeterminate |
| 3 | AgentLens/API/configuration/timeout error |

An AgentLens outage, unauthorized request, invalid identifier, or timeout is
therefore never reported as a candidate failure or a pass. The CLI does not
print API keys, database URLs, Redis URLs, or authorization headers.

The reusable example at
[`examples/ci/github-actions-quality-gate.yml`](../examples/ci/github-actions-quality-gate.yml)
shows a generic replay/report step followed by the CLI. It uses
`secrets.AGENTLENS_API_KEY`; no GitHub App or GitHub API dependency exists.
The same exit-code contract works in GitLab CI, Jenkins, CircleCI, Buildkite,
or a local shell.

## Example: quality versus latency

An M10 report can contain:

```text
agent.task_success:     50% -> 100%, IMPROVED
trace.duration_ms.p95:  800ms -> 1500ms, REGRESSED
```

With both rules blocking, the M11 decision is `failed` with a passed quality
rule and a failed latency rule. Changing only latency to an advisory rule
makes the decision `passed` while retaining the latency warning. This is an
explicit release policy, not a universal model winner or composite score.

## Dashboard

`/quality-gates` lists immutable decisions and policy versions. The detail page
shows status, regression link, dataset/version/checksum, policy and engine
provenance, rule results, semantic provenance where present, and a copyable
CLI command. M10 regression pages remain diagnostic and contain no deploy,
merge, or rollback controls. The browser receives no AgentLens API key; the
existing server-side Next.js BFF allowlist forwards only approved paths.

## Security and limitations

All API reads and evaluations are project-scoped. Policy data is validated
against the trusted finite registry and is never executed. Decision evidence is
bounded to report metadata and rule facts; raw trace payloads are not copied.
Semantic metrics retain evaluator/judge provenance and remain model-assisted,
not mathematically objective.

M11 does not deploy, roll back, merge, comment on pull requests, send
notifications, install provider apps, or provide weighted trade-off policies.
Performance/reliability/security hardening remains M12; production evidence
remains M13.
