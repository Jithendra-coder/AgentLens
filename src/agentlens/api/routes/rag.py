"""Built-in User Policy RAG API Routes."""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agentlens.rag.engine import UserPolicyRAGEngine

router = APIRouter(prefix="/v1/rag", tags=["rag"])

# Shared engine instance
_ENGINE = UserPolicyRAGEngine()


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="User question to query against policy")
    top_k: int = Field(default=2, ge=1, le=5, description="Number of matching policy clauses to retrieve")
    document_id: str = Field(default="user_policy", description="Knowledge base to query ('user_policy' or 'developer_docs')")


class CitationItem(BaseModel):
    chunk_id: str
    section: str
    title: str
    score: float
    excerpt: str


class SpanSummaryItem(BaseModel):
    name: str
    type: str
    duration_ms: int
    status: str = "ok"
    tokens: int = 0


class RAGQueryResponse(BaseModel):
    query: str
    answer: str
    verdict: str = "POLICY VERIFIED"
    citations: list[CitationItem]
    trace_id: str
    latency_ms: int
    retriever_ms: int
    tokens: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    grounded: bool
    document_name: str
    document_id: str = "user_policy"
    cache_hit: bool = False
    spans: list[SpanSummaryItem] = []


class UpdateDocumentRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=500000, description="Markdown or text content of the policy document")
    document_id: str = Field(default="user_policy", description="Knowledge base to update ('user_policy' or 'developer_docs')")


class UploadDocumentRequest(BaseModel):
    doc_id: str = Field(..., min_length=2, max_length=64, description="Unique slug for document")
    title: str = Field(..., min_length=2, max_length=200, description="Document display title")
    content: str = Field(..., min_length=10, max_length=500000, description="Document text or markdown")
    badge: str = Field(default="Custom Upload", description="Category badge label")
    description: str = Field(default="", description="Brief summary")


class AgentQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="Agent question with customer or transaction ID")


class ArenaQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="Question to evaluate across models")
    document_id: str = Field(default="user_policy", description="Target document")


class WebhookTestRequest(BaseModel):
    webhook_url: str = Field(default="https://api.agentlens.local/webhooks/listener", description="Target webhook URL")
    secret: str = Field(default="whsec_agentlens_live_772", description="HMAC-SHA256 secret key")
    event_type: str = Field(default="trace.error", description="Event type ('trace.error', 'budget.exceeded')")


@router.get("/health")
async def rag_health() -> dict[str, Any]:
    """Ultra-fast, lightweight health check returning gateway status in sub-2ms."""
    return {
        "status": "online",
        "service": "agentlens-control-plane",
        "engine": "Level 4 Autonomous AI Control Plane",
        "documents": len(_ENGINE.docs_store),
        "cached_queries": len(_ENGINE.cache.cache),
        "version": "4.0.0-enterprise",
    }


@router.get("/documents")
async def list_rag_documents() -> list[dict[str, Any]]:
    """List all indexed knowledge base documents with metadata and chunk counts."""
    return _ENGINE.list_documents()


@router.post("/query", response_model=RAGQueryResponse)
async def query_user_policy(body: RAGQueryRequest, request: Request) -> RAGQueryResponse:
    """Execute a query against the selected document with automatic AgentLens tracing."""
    try:
        sink = None
        if hasattr(request.app.state, "gateway") and hasattr(request.app.state.gateway, "sink"):
            sink = request.app.state.gateway.sink
        result = _ENGINE.query(
            query=body.query,
            top_k=body.top_k,
            document_id=body.document_id,
            sink=sink,
        )
        return RAGQueryResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RAG execution failed: {exc}") from exc


@router.post("/agent")
async def query_agentic_tool(body: AgentQueryRequest, request: Request) -> dict[str, Any]:
    """Execute Agentic RAG with live SQL customer & transaction database lookups."""
    try:
        sink = None
        if hasattr(request.app.state, "gateway") and hasattr(request.app.state.gateway, "sink"):
            sink = request.app.state.gateway.sink
        return _ENGINE.query_agent(query=body.query, sink=sink)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agentic RAG execution failed: {exc}") from exc


@router.post("/upload")
async def upload_custom_document(body: UploadDocumentRequest) -> dict[str, Any]:
    """Upload, chunk, and index a new custom knowledge base document."""
    try:
        return _ENGINE.add_custom_document(
            doc_id=body.doc_id,
            title=body.title,
            content=body.content,
            badge=body.badge,
            description=body.description,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document upload failed: {exc}") from exc


@router.post("/audit")
async def audit_policy_document(document_id: Optional[str] = None, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Automated Policy Conflict & Loophole Detector."""
    target_id = document_id or (body.get("document_id") if body else None) or "user_policy"
    try:
        return _ENGINE.audit_policy(document_id=target_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Policy audit failed: {exc}") from exc


@router.post("/benchmark")
async def run_synthetic_benchmark(document_id: Optional[str] = None, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Run Synthetic Benchmark Suite & LLM-as-a-Judge Evaluation."""
    target_id = document_id or (body.get("document_id") if body else None) or "user_policy"
    try:
        return _ENGINE.run_benchmark(document_id=target_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Benchmark evaluation failed: {exc}") from exc


@router.post("/arena")
async def query_model_arena(body: ArenaQueryRequest) -> dict[str, Any]:
    """Compare query responses side-by-side across Claude 3.5 Sonnet, GPT-4o, and Local Llama 3.1 8B."""
    try:
        return _ENGINE.query_arena(query=body.query, document_id=body.document_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Model arena failed: {exc}") from exc


@router.post("/webhooks/test")
async def test_webhook_dispatch(body: WebhookTestRequest) -> dict[str, Any]:
    """Simulate and record outbound signed webhook dispatch with HMAC-SHA256 signature."""
    try:
        return _ENGINE.dispatch_test_webhook(
            webhook_url=body.webhook_url,
            secret=body.secret,
            event_type=body.event_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Webhook test failed: {exc}") from exc


@router.get("/webhooks")
async def get_webhook_deliveries() -> list[dict[str, Any]]:
    """Retrieve history of dispatched webhooks with signatures."""
    return _ENGINE.get_webhook_history()


@router.put("/document")
async def update_policy_document(body: UpdateDocumentRequest) -> dict[str, Any]:
    """Dynamically update the selected knowledge base document and re-index in memory."""
    res = _ENGINE.update_document(body.text, document_id=body.document_id)
    return {
        "status": "success",
        "message": f"Document '{res['document_id']}' updated and re-indexed into {res['chunks_count']} sections.",
        **res,
    }


@router.post("/reset")
async def reset_policy_document(document_id: str = "user_policy") -> dict[str, Any]:
    """Reset the selected knowledge base back to its original template."""
    res = _ENGINE.reset_document(document_id=document_id)
    return {
        "status": "success",
        "message": f"Document '{res['document_id']}' reset to factory defaults.",
        **res,
    }


@router.get("/document")
async def get_policy_document(document_id: str = "user_policy") -> dict[str, Any]:
    """Retrieve full text and structured sections for the specified document."""
    return _ENGINE.get_document(document_id=document_id)
