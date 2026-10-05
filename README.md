# AgentLens

AgentLens is a provider-independent observability and evaluation platform for AI application traces. Its implemented scope covers trace capture and ingestion, PostgreSQL-backed storage, evaluation and replay workflows, regression reports, quality gates, a CLI, and a Next.js dashboard.

## Current project status

The [roadmap](docs/ROADMAP.md) records completed milestones and remaining work. M12 is documented as **pass with limitations**; M13 covers deployment foundations. M14–M30 are future milestones. AgentLens is not formally certified for production use: the [security hardening notes](docs/SECURITY_HARDENING.md) explicitly exclude a penetration test, formal certification, and production-readiness claim. Review [limitations](docs/LIMITATIONS.md), the [security model](docs/SECURITY_MODEL.md), and [deployment guidance](docs/DEPLOYMENT.md) before using real data or credentials.

## What is implemented

- A Python SDK and canonical trace, span, and event model.
- FastAPI ingestion and query APIs with project-scoped keys and bounded request handling.
- PostgreSQL persistence and optional Redis-backed background work.
- Deterministic metrics and a provider-independent semantic-judge boundary.
- Trusted dataset and replay flows, regression reports, and policy-driven quality gates.
- A dashboard, CLI, container definitions, health probes, and operational configuration.

See the [architecture](docs/ARCHITECTURE.md), [testing strategy](docs/TESTING_STRATEGY.md), and [quality gates](docs/QUALITY_GATES.md) for details and limits. Semantic judgments can be fallible; the default core does not provide a live model-provider adapter.

## Development

Requirements: Python 3.11+, Node.js, and npm. Install the backend development tools and run its checks:

```bash
python -m pip install -e ".[dev]"
pytest
```

Ruff and strict mypy are configured for contributors, but the current source tree still has existing lint and typing findings; they are not claimed as passing release checks.

For dashboard checks:

```bash
cd web
npm ci
npm run typecheck
npm test
npm run lint
```

For the containerized stack, follow [deployment guidance](docs/DEPLOYMENT.md) and configure secrets from `deployment/.env.example`. Do not use sample or placeholder credentials with real data.

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [engineering principles](docs/PRINCIPLES.md). Keep claims tied to reproducible evidence and update the relevant contract or documentation when behavior changes.

## License

Apache 2.0
