# AgentLens Deployment Guide

This guide details how to deploy AgentLens in production environments using containerization and Docker Compose.

---

## Architecture Overview

```text
                               ┌────────────────────────┐
                               │   Next.js Dashboard    │
                               │        (:3000)         │
                               └───────────┬────────────┘
                                           │
                                           ▼
                               ┌────────────────────────┐
                               │  FastAPI Gateway API   │
                               │        (:8000)         │
                               └─────┬────────────┬─────┘
                                     │            │
             ┌───────────────────────┘            └───────────────────────┐
             ▼                                                            ▼
┌─────────────────────────┐                                  ┌─────────────────────────┐
│       PostgreSQL        │                                  │          Redis          │
│        (:5432)          │                                  │         (:6379)         │
└───────┬─────────────────┘                                  └───────┬─────────────────┘
        │                                                            │
        ├─────────────────────────────┬──────────────────────────────┤
        ▼                             ▼                              ▼
┌─────────────────┐           ┌─────────────────┐            ┌─────────────────┐
│Evaluation Worker│           │  Replay Worker  │            │Regression Worker│
└─────────────────┘           └─────────────────┘            └─────────────────┘
```

---

## Prerequisites

- Docker Engine 24.0+ and Docker Compose v2+
- PostgreSQL 16+ (or managed RDS/Cloud SQL)
- Redis 7+ (or managed ElastiCache/MemoryStore)

---

## Quickstart Production Deployment

### 1. Configure Environment

Copy the example configuration and set production secrets:

```bash
cp deployment/.env.example deployment/.env
```

Edit `deployment/.env`:
- Set a strong `POSTGRES_PASSWORD`
- Set a secure `AGENTLENS_PROJECT_API_KEY` (minimum 16 characters)
- Configure `AGENTLENS_DATABASE_URL` and `AGENTLENS_REDIS_URL`

### 2. Run Database Migrations

AgentLens includes an advisory-locked migration runner that applies Alembic migrations safely:

```bash
docker compose -f deployment/docker-compose.prod.yml run --rm migration
```

### 3. Launch Services

Start all platform services in the background:

```bash
docker compose -f deployment/docker-compose.prod.yml up -d
```

### 4. Verify Service Health

Check container health status:

```bash
docker compose -f deployment/docker-compose.prod.yml ps
```

Verify API health probes:
```bash
# Process Liveness
curl -f http://localhost:8000/health/live

# Dependency Readiness (DB + Redis)
curl -f http://localhost:8000/health/ready

# Orchestrator Startup Probe
curl -f http://localhost:8000/health/startup
```

Access the dashboard at `http://localhost:3000`.

---

## Production Operations

### Scaling Workers

To scale evaluation workers horizontally:

```bash
docker compose -f deployment/docker-compose.prod.yml up -d --scale worker=4
```

### Graceful Upgrades

1. Apply database migrations:
   ```bash
   docker compose -f deployment/docker-compose.prod.yml run --rm migration
   ```
2. Recreate API and worker containers with zero downtime:
   ```bash
   docker compose -f deployment/docker-compose.prod.yml up -d --no-deps api worker replay-worker regression-worker
   ```
