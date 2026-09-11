"""
Minimal AgentLens Quickstart Example.

Demonstrates logging a complete RAG execution trace in 3 lines of Python.
"""

from agentlens.client import AgentLensClient


def main():
    print("[AgentLens] Initializing Client with project API key...")
    client = AgentLensClient(api_key="dev-key-12345", base_url="http://127.0.0.1:8000")

    # Sample RAG Execution Output
    user_query = "What is the policy for processing customer refunds?"
    retrieved_chunks = [
        "Refunds are processed to the original payment method within 5 to 7 business days.",
        "Items must be returned in original packaging with proof of purchase.",
    ]
    model_answer = (
        "Refunds are credited to your original payment method within 5 to 7 business days "
        "provided the item is returned with proof of purchase."
    )

    print("[AgentLens] Logging live RAG telemetry...")
    trace_id = client.log_rag(
        query=user_query,
        context=retrieved_chunks,
        answer=model_answer,
        latency_ms=138,
        tokens=72,
        model="gpt-4o",
    )

    print(f"[SUCCESS] Trace recorded! Trace ID: {trace_id}")
    print("View live trace in dashboard: http://localhost:3000/traces")


if __name__ == "__main__":
    main()
