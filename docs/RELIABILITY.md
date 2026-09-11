# M12 Reliability Evidence

The authoritative state remains PostgreSQL. Redis is a wake-up and shared
coordination layer. Ingestion and read queries continue when Redis is down;
readiness reports a degraded state and durable recovery scans remain bounded.
Evaluation, replay, and regression workers retain their existing lease,
claim-token fencing, retry, timeout, duplicate-delivery, and recovery behavior.

Run the bounded evidence harness with the local stack:

```powershell
py -3.11 scripts/reliability_m12.py
```

The result is `artifacts/m12/reliability.json`. It performs live/liveness,
readiness, a bounded 20-operation soak, isolated PostgreSQL-down and
Redis-down checks using unused endpoints, and restored-stack checks. It does
not stop shared PostgreSQL or Redis processes. Existing M5/M9/M10 integration
tests cover durable queue recovery, duplicate wakeups, lease expiry, stale
worker fencing, replay target timeout, and regression recovery. M12 adds
durable operational heartbeats for evaluation, replay, and regression workers;
stopped workers become stale after their last `last_seen` time passes the
30-second dashboard threshold.

Recovery scans are bounded to the existing configured batch sizes. API request
bodies, batches, query pages, analytics windows, replay concurrency, retries,
target timeouts, and dashboard lists remain bounded by their respective
configuration and route contracts. The local soak is deliberately short and
does not imply 24-hour or production durability evidence.
