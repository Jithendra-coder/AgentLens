# AgentLens CLI — Lighthouse for RAG & Universal AI Scanner

> **The automated AI performance, latency, grounding, and cost audit tool for RAG applications. 100% pure Python CLI with zero frontend dependencies.**

---

## ⚡ Quick Installation

Clone or download this folder and install directly with pip:

```bash
# Windows
install.bat

# Linux / macOS
chmod +x install.sh && ./install.sh

# Or directly with pip
pip install -e .
```

Verify the installation from any directory in your terminal:
```bash
agentlens --help
```

---

## 🚀 Core Features

- **Lighthouse for RAG**: Letter grades (A+ to F) across 4 pillars:
  1. *Latency & Speed*: TTFT, component bottlenecks, and reranker overhead.
  2. *Grounding & Accuracy*: Citation coverage, cosine similarity, and hallucination risk.
  3. *Cost & Token Economy*: Blended token pricing across LLM providers.
  4. *Vector Density*: Chunk split size balance and chunk noise ratio.
- **Universal Codebase Scanner (`agentlens scan <dir>`)**: Analyzes *any* RAG project on your machine (LangChain, LlamaIndex, Haystack, custom code) for chunk sizes, vector databases, embedding models, and streaming readiness.
- **Multi-Model Evaluation**: Test and benchmark across GPT-4o, Gemini 1.5 Pro, Claude 3.5 Sonnet, GPT-4o Mini, and Llama 3.1 70B.
- **Zero-Config Persistence**: Automatically persists run traces and API keys into local SQLite (`~/.agentlens/agentlens.db`) or PostgreSQL if available.
- **Standalone Offline HTML Reports**: Generates interactive HTML audit reports with SVG gauges and latency waterfalls.
- **3-Line Drop-in SDK**: Trace external functions in your existing codebases.

---

## 💻 CLI Commands

### 1. Run RAG Evaluation & Lighthouse Audit

```bash
# Interactive guided mode (prompts for query, scenario, domain, and model)
agentlens run

# Run with GPT-4o
agentlens run -m gpt-4o -q "Optimizing vector search indexing algorithms" --non-interactive

# Run with Gemini 1.5 Pro
agentlens run -m gemini-1.5-pro -q "Enterprise multi-tenant security architecture" --non-interactive

# Run with Claude 3.5 Sonnet
agentlens run -m claude-3-5-sonnet -q "HIPAA compliance audit protocols" --non-interactive
```

Supported models:
- `gpt-4o` (OpenAI)
- `gpt-4o-mini` (Ultra-Fast OpenAI)
- `gemini-1.5-pro` (Google DeepMind 2M context)
- `claude-3-5-sonnet` (Anthropic)
- `llama-3.1-70b` (Meta / Groq LPUs)

---

### 2. Scan ANY External RAG Application (`agentlens scan <dir>`)

To audit an existing RAG project in another folder on your computer:

```bash
# Scan a project in another directory
agentlens scan C:\Projects\my-rag-application

# Scan current directory
agentlens scan .
```

**What it detects:**
- Chunk size configurations (`chunk_size=1500` flagged for noise).
- Vector databases (Pinecone, Chroma, Qdrant, Weaviate, FAISS, pgvector).
- Embedding models (OpenAI, HuggingFace all-MiniLM, BGE, Cohere).
- LLM generation models and prompt caching.
- Token streaming readiness (`stream=True` / SSE).

**Output:**
```text
========================================================================
  AGENTLENS CODEBASE SCANNER - RAG ARCHITECTURE AUDIT
========================================================================
  Target Directory: C:\Projects\my-rag-application
------------------------------------------------------------------------
  Files Scanned   : 14
  Vector Databases: Pinecone Vector Database
  Embedding Models: OpenAI text-embedding-3-small (1536 dim)
  LLM Generators  : GPT-4o (OpenAI)
  Reranker Found  : No
  Streaming Ready : Yes (SSE / Generator)
  Prompt Caching  : Not configured

========================================================================
  STATIC LIGHTHOUSE ARCHITECTURE GRADE:  B  (85/100)
========================================================================
  TOP ARCHITECTURE RECOMMENDATIONS:
  [1] Reduce Oversized Chunking Size (1200 tokens detected)
      -> Splitting chunks to 350-500 tokens reduces prompt cost by ~40%.
  [2] Add Cross-Encoder Reranker for High Top-K (K=8)
      -> Retrieving K=8 passages without a reranker causes context stuffing.
========================================================================
```

---

### 3. Live Endpoint / Script Probe (`agentlens probe`)

Test an external live HTTP RAG endpoint or Python script:

```bash
# Probe a running FastAPI / Flask / Node RAG API
agentlens probe --url http://localhost:8000/query --body '{"prompt": "{{query}}"}' -q "User question"

# Probe an external Python script directly
agentlens probe --script C:\Projects\my-rag-app\query.py --func answer_query -q "User question"
```

---

### 4. View Evaluation History & API Keys

```bash
agentlens history --limit 10
```

Lists all recent evaluations, their generated API keys, latency, cost, and overall Lighthouse letter grades.

---

### 5. 3-Line Drop-in Python SDK

In any external Python RAG application in any folder, add:

```python
from agentlens_core import trace_rag

@trace_rag(model="gpt-4o")
def my_rag_pipeline(query: str):
    # Your standard retrieval and LLM logic
    chunks = my_vector_db.search(query)
    answer = my_llm.generate(chunks, query)
    return answer

# Executing this function will automatically:
# 1. Measure latency and token consumption
# 2. Output a Lighthouse score (A+ to F) to the terminal
# 3. Generate a standalone HTML report
# 4. Save the run record under a unique API key
```

---

## 🗄️ Database & Storage

AgentLens automatically chooses the best available storage:
- **PostgreSQL**: Used when `AGENTLENS_DATABASE_URL` is set or PostgreSQL is active on port 5432.
- **Local SQLite**: Zero-configuration embedded database at `~/.agentlens/agentlens.db` initialized automatically if PostgreSQL is not running.
- **Offline HTML Reports**: Generated in `./reports/raglens_report_<trace_id>.html`.

---

## 📄 License

Apache 2.0 / MIT.
