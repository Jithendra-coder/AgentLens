# AgentLens Configuration Reference

AgentLens follows the **Twelve-Factor App** configuration methodology. All settings are configured via environment variables and validated at startup using `agentlens.config.AgentLensSettings`.

---

## Configuration Variables Reference

### Environment & Mode

| Variable | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `AGENTLENS_ENVIRONMENT` | Deployment environment (`development`, `staging`, `production`, `test`). | String | `development` |

---

### PostgreSQL Database

| Variable | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `AGENTLENS_DATABASE_URL` | PostgreSQL connection URL with psycopg driver. | String | `postgresql+psycopg://agentlens:agentlens@127.0.0.1:55432/agentlens` |
| `AGENTLENS_DB_POOL_SIZE` | SQLAlchemy connection pool size. | Integer | `20` |
| `AGENTLENS_DB_MAX_OVERFLOW` | Maximum pool overflow connections. | Integer | `10` |
| `AGENTLENS_DB_POOL_TIMEOUT` | Connection pool checkout timeout in seconds. | Float | `30.0` |

---

### Redis Cache & Queue

| Variable | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `AGENTLENS_REDIS_URL` | Redis connection URL for worker dispatch & rate limiting. | String | `redis://127.0.0.1:56379/0` |
| `AGENTLENS_REDIS_TIMEOUT` | Redis socket timeout in seconds. | Float | `5.0` |

---

### Authentication & Project Isolation

| Variable | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `AGENTLENS_PROJECT_ID` | Project identifier for multi-tenant data isolation. | String | `default-project` |
| `AGENTLENS_PROJECT_API_KEY` | Bearer API token for authentication. Min 16 chars in prod. | String | `secret-api-key` |
| `AGENTLENS_API_KEY_ID` | Key identifier metadata. | String | `default-key` |

---

### API Gateway Server

| Variable | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `AGENTLENS_API_HOST` | Host interface to bind. | String | `0.0.0.0` |
| `AGENTLENS_API_PORT` | HTTP port to listen on. | Integer | `8000` |
| `AGENTLENS_LOG_LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | String | `INFO` |
| `AGENTLENS_LOG_FORMAT` | Logging output format (`json` or `text`). | String | `json` in prod |
| `AGENTLENS_MAX_REQUEST_BYTES` | Maximum allowed request body size in bytes. | Integer | `10485760` (10 MB) |
| `AGENTLENS_RATE_LIMIT` | Ingestion rate limit (requests per window). | Integer | `1000` |
| `AGENTLENS_RATE_WINDOW` | Rate limit window duration in seconds. | Integer | `60` |
| `AGENTLENS_CORS_ORIGINS` | Comma-separated allowed CORS origins. | String | `*` |

---

### Worker Configuration

| Variable | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `AGENTLENS_WORKER_CONCURRENCY` | Number of concurrent execution tasks per worker. | Integer | `1` |
| `AGENTLENS_WORKER_POLL_INTERVAL`| Polling interval when idle in seconds. | Float | `1.0` |
| `AGENTLENS_HEARTBEAT_INTERVAL` | Heartbeat refresh interval in seconds. | Float | `15.0` |
| `AGENTLENS_HEARTBEAT_TTL` | Heartbeat expiration threshold in seconds. | Float | `45.0` |
| `AGENTLENS_LEASE_DURATION` | Task lease acquisition duration in seconds. | Float | `300.0` |
| `AGENTLENS_SHUTDOWN_TIMEOUT` | Maximum graceful shutdown duration in seconds. | Float | `30.0` |

---

## Configuration Validation CLI

You can validate your environment settings before starting services:

```bash
agentlens config check
```

Example Output:
```json
{
  "status": "valid",
  "configuration": {
    "environment": "production",
    "database": {
      "url": "postgresql+psycopg://agentlens:***@postgres:5432/agentlens",
      "pool_size": 20,
      "max_overflow": 10,
      "pool_timeout_seconds": 30.0
    },
    "redis": {
      "url": "redis://redis:6379/0",
      "socket_timeout_seconds": 5.0
    },
    "auth": {
      "project_id": "prod-project",
      "project_api_key": "pr...45",
      "api_key_id": "prod-key"
    },
    "server": {
      "host": "0.0.0.0",
      "port": 8000,
      "log_level": "INFO",
      "log_format": "json"
    }
  }
}
```
