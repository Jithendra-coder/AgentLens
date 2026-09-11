# ADR-053: Redis-backed shared rate limiting with local fallback

When a runtime Redis URL is configured, API instances use one atomic Lua
fixed-window counter keyed by a SHA-256 key-id digest. Redis is coordination,
not authorization; on outage requests use a bounded process-local fallback and
readiness reports degraded rate-limit coordination.
