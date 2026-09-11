# AgentLens M8 Dashboard

## Scope

M8 adds a dedicated `web/` Next.js dashboard for one already-authenticated
AgentLens project. It is observational only: there are no accounts, billing,
model integrations, replay/dataset controls, regression comparison, universal
quality score, or destructive runtime actions.

## Run locally

Start PostgreSQL and Redis, then expose the gateway:

```text
AGENTLENS_DATABASE_URL=postgresql+psycopg://...
AGENTLENS_PROJECT_ID=project-a
AGENTLENS_PROJECT_API_KEY=<server-only-key>
AGENTLENS_REDIS_URL=redis://...
python -m uvicorn agentlens.server:app --app-dir src --port 8000
```

Start the dashboard with the same project boundary:

```text
cd web
AGENTLENS_API_BASE_URL=http://127.0.0.1:8000
AGENTLENS_PROJECT_API_KEY=<server-only-key>
npm install
npm run dev
```

`AGENTLENS_PROJECT_API_KEY` is read only by the Next.js server-side BFF. The
browser calls same-origin `/api/*` routes and never receives the project key or
a trusted `project_id` selector.

## Surfaces

- `/` — bounded 1h/24h/7d overview, volume/error rate, PostgreSQL p50/p95/p99 completed latency, reported tokens, evaluation counts, and recent traces/findings.
- `/traces` — exact project-scoped trace filters and cursor pagination.
- `/traces/{traceId}` — canonical trace detail, hierarchy/waterfall, open spans, safe JSON, retrieval/tool/LLM views, events, and result links.
- `/evaluations` — bounded result explorer plus provenance-safe groups.
- `/evaluations/{resultId}` — immutable result, metrics, findings/evidence, and semantic judge provenance.
- `/runtime` — queued/running/retry/dead-letter job state, safe failures, DB/Redis status, and explicit unavailable worker heartbeat.

## API boundary

The backend owns authentication and project isolation. Analytics routes accept
only bounded time windows and allowlisted filters. Percentiles, time buckets,
evaluation grouping, finding counts, and runtime state counts are computed in
PostgreSQL through `agentlens.analytics.repository`; the browser does not
aggregate pages. Semantic groups retain evaluator name/version, mode, config
fingerprint, judge profile, provider/model, and prompt version.

Reported usage is nullable. Missing values are not converted to zero, and
judge token usage is not merged into application span usage. No cost is shown.

## Verification

From `web/`:

```text
npm test
npm run lint
npm run typecheck
npm run build
npm run e2e
```

Playwright uses the local Next server. M8 integration verification also runs
the dashboard through the server-side BFF with real PostgreSQL, Redis, gateway,
trace, evaluation, and runtime data.
