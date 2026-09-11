# AgentLens M6 migrations

Set `AGENTLENS_DATABASE_URL` to a PostgreSQL URL and run:

```text
alembic upgrade head
```

The migration files are authoritative for deployed schema management. The
application does not call `metadata.create_all()` during startup.

Migration `0002_evaluation_runtime` appends the PostgreSQL-authoritative
`evaluation_jobs` and `evaluation_job_attempts` tables. The immutable M4
`0001_initial_trace_storage` migration is not modified. Migration
`0003_evaluation_results` appends the immutable M6 `evaluation_results` table;
the earlier migrations are not modified.
