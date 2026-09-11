"""Example standalone RAG application in an external directory."""

import time

# Detected architectural configurations for AgentLens Scanner:
VECTOR_DATABASE = "pinecone"
EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o"
chunk_size = 1200
chunk_overlap = 150
top_k = 8


def query_rag(prompt: str) -> str:
    """Mock external RAG execution function."""
    time.sleep(0.35)  # Simulate Pinecone search + OpenAI generation
    return f"Synthesized answer for '{prompt}' based on 8 retrieved Pinecone passages using GPT-4o."


if __name__ == "__main__":
    test_query = "What are the latency requirements for tier-1 microservices?"
    print("Running external RAG query...")
    answer = query_rag(test_query)
    print("Result:", answer)
