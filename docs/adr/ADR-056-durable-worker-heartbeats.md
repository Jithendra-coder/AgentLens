# ADR-056: Durable operational worker heartbeats

Evaluation, replay, and regression worker processes upsert one operational
heartbeat row and touch it periodically. The dashboard derives healthy versus
stale from `last_seen`; shutdown marks the row stopped, while a crash naturally
leaves a stale running row for diagnosis. Heartbeat failures do not block the
authoritative work loop.
