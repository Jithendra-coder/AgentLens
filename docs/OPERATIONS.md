# AgentLens Operations & Runbook

This document details day-to-day operational tasks, maintenance, monitoring, health checks, troubleshooting, and lifecycle management for AgentLens.

---

## Service Lifecycle & Process Management

AgentLens services implement structured lifecycle coordination:

### Signal Handling & Graceful Shutdown
When receiving `SIGINT` (Ctrl+C) or `SIGTERM` (from container stop / orchestrator kill signals):
1. **API Gateway**: Stops accepting new requests, drains active HTTP connections, and closes database/Redis pools cleanly.
2. **Workers**: Stops claiming new jobs, clears active leases safely, stops heartbeats, and releases database resources.
3. **Timeout Protection**: If graceful shutdown exceeds `AGENTLENS_SHUTDOWN_TIMEOUT` (default: 30s), the process logs a timeout error and cleanly terminates.

---

## Health Checks & Monitoring

AgentLens exposes three distinct health probe endpoints:

| Endpoint | Type | Purpose | Expected Status |
| :--- | :--- | :--- | :--- |
| `/health/live` | Liveness | Verifies process is alive and responsive. | `200 OK` (`{"status": "ok"}`) |
| `/health/ready` | Readiness | Verifies DB and Redis connectivity. | `200 OK` (`{"status": "ok"}`) / `503 Unavailable` |
| `/health/startup` | Startup | Verifies initial initialization & schema availability. | `200 OK` (`{"status": "ok"}`) / `503 Initializing` |

### Log Inspection & Structured Logging

Logs are formatted in single-line JSON format in production. Every log record includes:
- `timestamp`: UTC ISO8601 timestamp.
- `level`: `INFO`, `WARNING`, `ERROR`.
- `logger`: Logger name (e.g. `agentlens.gateway`, `agentlens.worker`).
- `message`: Human-readable message identifier.
- `request_id`: Unique UUID for HTTP requests.
- `correlation_id`: End-to-end trace correlation ID.
- `duration_ms`: Duration of operations in milliseconds.

To inspect structured logs:
```bash
docker compose -f deployment/docker-compose.prod.yml logs -f api
docker compose -f deployment/docker-compose.prod.yml logs -f worker
```

---

## Troubleshooting Guide

### 1. Database Connection Errors
- **Symptom**: `/health/ready` returns `503 Unavailable` with `database: unavailable`.
- **Resolution**: Verify `AGENTLENS_DATABASE_URL` matches PostgreSQL container credentials and host port. Test connectivity:
  ```bash
  docker compose -f deployment/docker-compose.prod.yml exec postgres pg_isready -U agentlens
  ```

### 2. Redis Degraded Mode
- **Symptom**: `/health/ready` returns `200 OK` with `status: degraded` and `evaluation_queue: unavailable`.
- **Explanation**: AgentLens preserves trace ingestion even if Redis wakeups are temporarily unreachable.
- **Resolution**: Check Redis container logs:
  ```bash
  docker compose -f deployment/docker-compose.prod.yml logs redis
  ```

### 3. Stale Worker Heartbeats
- **Symptom**: Runtime dashboard shows worker state as `offline` or `stale`.
- **Resolution**: Check worker container status. The heartbeat repository marks workers stale after `AGENTLENS_HEARTBEAT_TTL` (default 45s).
