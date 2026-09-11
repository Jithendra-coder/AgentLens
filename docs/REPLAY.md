# AgentLens Replay

M9 replays one finalized dataset version through an operator-registered trusted
target. A replay run persists the dataset version and checksum, target profile
and version, execution mode, immutable manifest, reproducibility assessment,
bounded timeout/concurrency, and case progress. Each case has one durable
logical execution record and separate attempt history.

## Modes

- `exact` requires complete provenance and no unknown fields; requests without
  that evidence are rejected.
- `controlled` requires explicit `changed_dimensions`; M9 records differences
  but does not compare outcomes.
- `best_effort` requires a reason explaining why exact reproduction is not
  possible.

The engine never silently changes a requested mode and never claims identical
external model output without provenance.

## Trusted targets and safety

Tenants select only a profile ID from the operator-populated registry. Profile
metadata includes target type, version, configuration reference, and safety
class. Secrets remain operator-side. Arbitrary URLs, Python module paths,
scripts, shell commands, imports, `eval`, and `exec` are not accepted. HTTP
targets are not implemented in M9, so SSRF is avoided by construction.

`read_only` and `sandbox` targets are allowed. `side_effectful` targets are
rejected by default at replay creation and execution. The built-in local echo
target exists only for tests and local browser verification; it is not a
production AI adapter.

## Runtime and recovery

PostgreSQL is authoritative for runs, executions, attempts, progress, and
outputs. Redis carries wake-up notifications only. Recovery scans re-dispatch
durable queued, retry-ready, or expired-lease executions. Claim tokens and
leases fence stale workers. Timeout and bounded retry are owned by the replay
runtime. Duplicate Redis delivery cannot create another logical case row.

Execution is at-least-once at the target boundary: a worker crash can repeat a
remote call, so side-effectful production targets must not be replayed blindly.
Outputs are JSON-safe and bounded by the existing request/data-governance
boundaries; complete input/output values are not written to logs.

## Traces and evaluations

Compatible targets return a canonical AgentLens Trace with replay correlation
attributes. The execution stores a durable generated trace ID, and normal M8
Trace Detail can inspect it. Targets without traces may leave that link null.
Automatic evaluation-on-replay is intentionally not implemented. M10 may
orchestrate missing evaluations through the existing M5 job ledger, but it
does not introduce a second evaluator or provider call in comparison logic.

Retention policy enforcement for the increased dataset/replay sensitivity is
still deferred.
