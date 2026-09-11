"""Example LangChain / LlamaIndex style RAG project."""

# Detected architecture parameters
VECTOR_STORE = "chromadb"
EMBEDDINGS = "sentence-transformers/all-minilm-l6-v2"
GENERATOR = "gemini-1.5-flash"
chunk_size = 500
chunk_overlap = 50
top_k = 4
stream = True


def run_pipeline(question: str) -> str:
    """Mock LangChain QA chain execution."""
    return f"LangChain answer retrieved from ChromaDB using Gemini Flash for: {question}"


if __name__ == "__main__":
    print(run_pipeline("Explain multi-region deployment strategies"))
