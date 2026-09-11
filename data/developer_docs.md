# AgentLens Developer API & SDK Integration Guide
**Document ID:** DOC-DEV-2026-001  
**Version:** 2.4-Technical  
**Target Audience:** AI Engineers, Backend Developers, and DevOps Integrators  

---

## Section 1: Authentication & Project API Keys

All programmatic communication with the AgentLens ingestion gateway requires HTTP Bearer token authentication. API keys are provisioned per project and scoped to specific security roles.

### 1.1 Authorization Header Format
Every inbound HTTP request must supply the authorization token in the standard header:
```http
Authorization: Bearer al_live_9f83ac21087e59b201
Content-Type: application/json
X-Request-ID: 7a91b2c3-4d5e-6f7a-8b9c-0d1e2f3a4b5c
```

### 1.2 Permission Roles & Scope Boundaries
* **`service_ingestion`**: Restricted write-only permission. Permitted to ingest traces (`POST /v1/traces`) and report telemetry metrics. Cannot read analytics or modify project settings.
* **`project_editor`**: Read/write permission. Permitted to query traces, create evaluation suites, and test custom evaluators.
* **`project_admin`**: Full administrative permission. Permitted to provision API keys, configure cloud credentials, and manage team members.

---

## Section 2: Trace & Span Ingestion API

The ingestion gateway receives structured OpenTelemetry-compatible execution graphs. A trace is a directed acyclic graph (DAG) composed of hierarchical spans.

### 2.1 Single Trace Ingestion (`POST /v1/traces`)
Emits a completed execution tree. The root span represents the overarching agent chain, while child spans represent retrieval, tool execution, or model inference.

### 2.2 Canonical Span Types
* **`chain`**: Represents an end-to-end agent workflow or sequential pipeline.
* **`retriever`**: Represents semantic vector search, BM25 keyword matching, or hybrid retrieval. Must include document match scores.
* **`llm`**: Represents foundation model inference (e.g. GPT-4, Claude, Gemini). Must report token usage (`input_tokens`, `output_tokens`).
* **`tool`**: Represents third-party API calls, SQL queries, or sandbox code execution.

### 2.3 High-Throughput Batch Ingestion (`POST /v1/traces/batch`)
For high-volume production clusters, clients should buffer spans and transmit up to 500 traces in a single compressed batch request to minimize connection overhead.

---

## Section 3: Python SDK Integration & Quickstart

The official `agentlens` Python package provides thread-safe, non-blocking telemetry instrumentation with automatic retries and in-memory buffering.

### 3.1 Installation
Install the client package from PyPI:
```bash
pip install agentlens
```

### 3.2 Basic Client Initialization & RAG Logging
```python
from agentlens.client import AgentLensClient

# Initialize client with project credentials
client = AgentLensClient(
    api_key="dev-key-12345",
    base_url="http://127.0.0.1:8000"
)

# Record an execution trace with vector search and generation spans
with client.trace(name="Customer Support RAG") as t:
    # 1. Log retrieval span
    t.log_retrieval(
        name="Knowledge Base Search",
        documents=["Policy Section 2.2"],
        latency_ms=12
    )
    
    # 2. Log model generation span
    t.log_llm(
        name="Claude 3.5 Sonnet",
        prompt="Can I get a refund after 45 days?",
        completion="Refunds are limited to 30 days.",
        input_tokens=65,
        output_tokens=28,
        latency_ms=45
    )
```

---

## Section 4: Webhooks & Event Delivery

AgentLens can dispatch real-time outbound webhooks to third-party endpoints (e.g. Slack, PagerDuty, Datadog) when critical pipeline anomalies occur.

### 4.1 Supported Event Types
* **`trace.error`**: Triggered when an agent execution fails or raises an uncaught exception.
* **`budget.exceeded`**: Triggered when a project reaches 90% or 100% of its monthly token spend budget.
* **`drift.detected`**: Triggered when statistical embedding drift exceeds configured cosine distance thresholds.

### 4.2 HMAC-SHA256 Signature Verification
To prevent replay attacks and verify authenticity, every webhook request contains the `X-AgentLens-Signature` header:
```python
import hmac, hashlib

def verify_signature(payload_bytes, secret, signature_header):
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)
```

### 4.3 Retry & Exponential Backoff Schedule
If the receiving webhook endpoint returns an HTTP 5xx code or times out, AgentLens retries delivery up to 5 times with exponential backoff: 1s, 2s, 4s, 8s, and 16s.

---

## Section 5: Rate Limiting & HTTP Error Codes

To protect service availability, the gateway enforces token bucket rate limiting on every incoming API key.

### 5.1 Concurrency & RPM Tiers
* **Standard Tier**: 120 requests per minute (RPM) with a maximum burst concurrency of 20 simultaneous threads.
* **Enterprise Tier**: 1,200 requests per minute (RPM) with up to 100 simultaneous threads.

### 5.2 Response Headers
Every response includes standard rate limit headers:
* `X-RateLimit-Limit`: Maximum requests permitted per window.
* `X-RateLimit-Remaining`: Number of remaining requests in current window.
* `X-RateLimit-Reset`: Unix timestamp when the quota refreshes.

### 5.3 Error Code Dictionary
* **`400 Bad Request`**: Malformed JSON schema or missing required span fields.
* **`401 Unauthorized`**: Missing or invalid Bearer API key.
* **`403 Forbidden`**: API key role does not possess permissions for this endpoint.
* **`429 Too Many Requests`**: Rate limit exceeded; client should respect `Retry-After`.
* **`503 Service Unavailable`**: Database or ingestion pipeline temporarily degraded.

---

## Section 6: Data Privacy & Security Architecture

AgentLens is architected for zero-retention compliance and enterprise isolation.

### 6.1 Cryptographic Standards
* **In-Transit**: Enforced TLS 1.3 with modern cipher suites (ChaCha20-Poly1305 or AES-256-GCM).
* **At-Rest**: Database tables, trace metadata, and vector embeddings are encrypted using AES-256-GCM with customer-managed KMS keys.

### 6.2 Zero-Retention Privacy Mode
Enterprise customers can enable `privacy_mode: true` in their project configuration. When active:
* Prompt and completion text are redacted via cryptographic SHA-256 one-way hashing before persistence.
* Token counts, duration, and metadata tags are retained for analytics without exposing raw PII or proprietary prompt text.
