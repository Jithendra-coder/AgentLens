# ADR-017: PostgreSQL Trace Persistence

## Status

Accepted for M4.

## Context

M3's in-memory sink loses traces and idempotency state on process restart. M4
needs durable, project-scoped storage that still reconstructs the M1 model.

## Decision

Use PostgreSQL as the durable trace store, accessed through synchronous
SQLAlchemy 2.x and psycopg 3. A repository maps canonical traces to relational
trace/span/event rows and reconstructs them through `Trace.from_dict`.

## Consequences

M4 gains transactions, uniqueness, foreign keys, pooling, and restart-safe
storage without making SQLAlchemy part of the domain or SDK. Backups,
replication, and distributed sharding remain deployment/later-milestone work.
