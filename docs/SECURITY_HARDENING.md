# M12 Security Hardening

M12 preserves project-scoped authorization, safe error bodies, bounded JSON,
signed cursors, trusted replay target registration, semantic-judge isolation,
and server-only dashboard credentials from M0–M11.

New controls:

- API instances use a Redis Lua fixed-window limiter when a runtime Redis URL
  is configured. The operation is atomic across instances, keys contain only a
  SHA-256 key-id digest, and a bounded in-memory limiter is used during Redis
  outage. `/health/ready` reports `rate_limit: shared|degraded` for this mode.
- Next.js mutation proxy routes require an exact same-origin `Origin`; missing
  or foreign origins receive a safe 403. The dashboard emits CSP,
  `X-Content-Type-Options`, `Referrer-Policy`, and `X-Frame-Options` headers.
- Dashboard runtime worker status comes from the durable `worker_heartbeats`
  table, not a fabricated process-local value.

Run `py -3.11 scripts/security_scan_m12.py` for the recorded source scan,
dependency inventory, and advisory-tool availability. The final `npm audit`
result is clean; `pip-audit` is unavailable and remains explicitly recorded.
The workspace has no Git metadata, so history scanning is unavailable. An
unavailable tool or a reported advisory is not silently treated as a clean
result. Never place real credentials in
fixtures, logs, artifacts, URLs, or browser code.

M12 does not claim penetration-test completion, formal certification, encrypted
production deployment, retention enforcement, or production readiness.
