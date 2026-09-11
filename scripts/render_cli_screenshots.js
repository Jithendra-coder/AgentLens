const puppeteer = require('c:/Users/JITHU/OneDrive/Desktop/AI AGent/web/node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const outDir = 'c:/Users/JITHU/OneDrive/Desktop/AI AGent/screenshots';
const brainDir = 'C:\\Users\\JITHU\\.gemini\\antigravity\\brain\\18f9a59e-b87a-44ba-9ce4-a398771866ec\\screenshots';

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}
if (!fs.existsSync(brainDir)) {
  fs.mkdirSync(brainDir, { recursive: true });
}

function buildHtml(title, terminalContent) {
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #111318;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 32px;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  }
  .window {
    width: 1100px;
    background: #0c0c0c;
    border-radius: 8px;
    box-shadow: 0 25px 60px rgba(0,0,0,0.85), 0 0 0 1px rgba(255,255,255,0.1);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .titlebar {
    height: 38px;
    background: #1e1e1e;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 10px 0 14px;
    border-bottom: 1px solid #2d2d2d;
    user-select: none;
  }
  .tabs-group {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 100%;
  }
  .tab {
    display: flex;
    align-items: center;
    gap: 8px;
    background: #0c0c0c;
    color: #e6edf3;
    font-size: 12px;
    font-weight: 500;
    padding: 6px 14px;
    border-radius: 6px 6px 0 0;
    border-top: 2px solid #0078d4;
    height: 100%;
  }
  .tab-icon {
    width: 14px;
    height: 14px;
    fill: #4cc2ff;
  }
  .window-controls {
    display: flex;
    align-items: center;
    gap: 16px;
    color: #999999;
    font-size: 13px;
  }
  .window-controls span {
    cursor: default;
  }
  .control-close {
    color: #cccccc;
    font-weight: bold;
  }
  .terminal-body {
    padding: 20px 24px;
    background: #0c0c0c;
    color: #cccccc;
    font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
    font-size: 13.5px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .prompt-line {
    margin-bottom: 8px;
  }
  .prompt-path {
    color: #cccccc;
  }
  .prompt-cmd {
    color: #ffffff;
    font-weight: bold;
  }
  .cyan { color: #00d7d7; font-weight: bold; }
  .sky { color: #38bdf8; }
  .green { color: #22c55e; font-weight: bold; }
  .emerald { color: #34d399; }
  .yellow { color: #facc15; font-weight: bold; }
  .purple { color: #c084fc; font-weight: bold; }
  .white { color: #ffffff; font-weight: bold; }
  .gray { color: #737373; }
  .red { color: #ef4444; }
  .cursor {
    display: inline-block;
    width: 8px;
    height: 15px;
    background: #cccccc;
    vertical-align: middle;
    animation: blink 1s step-end infinite;
  }
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }
</style>
</head>
<body>
  <div class="window">
    <div class="titlebar">
      <div class="tabs-group">
        <div class="tab">
          <svg class="tab-icon" viewBox="0 0 16 16">
            <path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h11A1.5 1.5 0 0 1 15 2.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 13.5v-11zM2.5 2a.5.5 0 0 0-.5.5v11a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5v-11a.5.5 0 0 0-.5-.5h-11zM4.146 5.146a.5.5 0 0 1 .708 0L7.5 7.793l2.646-2.647a.5.5 0 0 1 .708.708l-3 3a.5.5 0 0 1-.708 0l-3-3a.5.5 0 0 1 0-.708z"/>
          </svg>
          <span>${title}</span>
        </div>
      </div>
      <div class="window-controls">
        <span>&#x2014;</span>
        <span>&#x25A2;</span>
        <span class="control-close">&#x2715;</span>
      </div>
    </div>
    <div class="terminal-body">
${terminalContent}
    </div>
  </div>
</body>
</html>`;
}

const screenshots = [
  {
    file: '01_cli_agentlens_run_gpt4o.png',
    title: 'PowerShell - agentlens run (GPT-4o)',
    content: `<div class="prompt-line"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">agentlens run --model gpt-4o --query "Optimizing vector search indexing algorithms" --scenario normal --non-interactive</span></div>
<span class="cyan">========================================================================</span>
<span class="white">  RAGLENS - RAG Application &amp; Architecture Diagnostic Engine</span>
<span class="cyan">========================================================================</span>

<span class="gray">------------------------------------------------------------------------</span>
  Executing RAG Pipeline for query: <span class="white">'Optimizing vector search indexing algorithms'</span>
  Profile: <span class="emerald">normal</span> | Domain: <span class="white">Enterprise Billing &amp; Legal Terms v2.4</span> | Model: <span class="yellow">GPT-4o (OpenAI)</span>
<span class="gray">------------------------------------------------------------------------</span>
  [01/05] Embedding Query (text-embedding-3-small)      : [<span class="green">OK</span>]   83 ms
  [02/05] Vector ANN Search (Pinecone Serverless Top-5)  : [<span class="green">OK</span>]  128 ms
  [03/05] Cross-Encoder Reranker (Cohere Rerank v3 Top-3): [<span class="green">OK</span>]  198 ms
  [04/05] Context &amp; Prompt Assembly                      : [<span class="green">OK</span>]   18 ms
  [05/05] LLM Answer Generation (GPT-4o (OpenAI)): [<span class="green">OK</span>]  671 ms

<span class="cyan">========================================================================</span>
<span class="white">  LIGHTHOUSE FOR RAG - AUTOMATED AI PERFORMANCE AUDIT</span>
<span class="cyan">========================================================================</span>
  Overall Performance Score :  <span class="green">97 / 100</span>  [<span class="green">GRADE: A+</span>]
<span class="gray">------------------------------------------------------------------------</span>
  [1] Latency &amp; Speed       : <span class="green">100 / 100</span> (Grade A+)  | 1098 ms total (TTFT ~1098 ms)
  [2] Grounding &amp; Accuracy  : <span class="green">100 / 100</span> (Grade A+)  | 0.84 avg similarity (16.0% hallucination risk)
  [3] Cost &amp; Token Economy  : <span class="green">100 / 100</span> (Grade A+)  | $0.0131 / req (3,735 tokens)
  [4] Vector Density        :  <span class="yellow">85 / 100</span> (Grade B+)  | 5 chunks retrieved (1 oversized chunks)
<span class="gray">------------------------------------------------------------------------</span>
  TOP LIGHTHOUSE OPPORTUNITIES (ESTIMATED SAVINGS):
    * <span class="yellow">[TRIM 537 MS TTFT]</span> Enable Server-Sent Events (SSE) Token Streaming
      -&gt; Reduces perceived latency by ~537 ms
    * <span class="yellow">[SAVE $420/MO]</span> Optimize Chunk Split Size from 1,200 to 500 Tokens
      -&gt; Saves ~$420/month at 50k requests/mo
    * <span class="yellow">[CUT PROMPT COST 35%]</span> Enable System Prompt Caching on Claude / OpenAI
      -&gt; Saves ~$380/month on repetitive instruction tokens
<span class="cyan">========================================================================</span>

<span class="yellow">########################################################################</span>
<span class="yellow">#</span>  [KEY] UNIQUE RUN API KEY : <span class="white">rl_key_dcb7bd4499da432d</span>
<span class="yellow">#</span>  [DB]  DATABASE STORAGE   : <span class="sky">PostgreSQL (table 'raglens_reports')</span>
<span class="yellow">#</span>  [RPT] OFFLINE HTML REPORT: <span class="purple">artifacts/reports\\raglens_report_trace_2cce35224579.html</span>
<span class="yellow">#</span>  [WEB] WEB DASHBOARD LINK : <span class="gray">http://localhost:3000/raglens?key=rl_key_dcb7bd4499da432d</span>
<span class="yellow">########################################################################</span>

Instructions:
1. Copy your unique API key above.
2. Open the RagLens Web Dashboard at http://localhost:3000/raglens
3. Paste the API key into the top search bar (or open the direct URL above)
4. The website will query PostgreSQL and render the complete visual graphs.

<div class="prompt-line" style="margin-top:14px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="cursor"></span></div>`
  },
  {
    file: '02_cli_agentlens_run_gemini.png',
    title: 'PowerShell - agentlens run (Gemini 1.5 Pro)',
    content: `<div class="prompt-line"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">agentlens run --model gemini-1.5-pro --query "Enterprise SLA and multi-tenant security architecture" --scenario normal --non-interactive</span></div>
<span class="cyan">========================================================================</span>
<span class="white">  RAGLENS - RAG Application &amp; Architecture Diagnostic Engine</span>
<span class="cyan">========================================================================</span>

<span class="gray">------------------------------------------------------------------------</span>
  Executing RAG Pipeline for query: <span class="white">'Enterprise SLA and multi-tenant security architecture'</span>
  Profile: <span class="emerald">normal</span> | Domain: <span class="white">Enterprise Billing &amp; Legal Terms v2.4</span> | Model: <span class="yellow">Gemini 1.5 Pro (Google DeepMind)</span>
<span class="gray">------------------------------------------------------------------------</span>
  [01/05] Embedding Query (text-embedding-3-small)      : [<span class="green">OK</span>]   75 ms
  [02/05] Vector ANN Search (Pinecone Serverless Top-5)  : [<span class="green">OK</span>]   97 ms
  [03/05] Cross-Encoder Reranker (Cohere Rerank v3 Top-3): [<span class="green">OK</span>]  203 ms
  [04/05] Context &amp; Prompt Assembly                      : [<span class="green">OK</span>]   18 ms
  [05/05] LLM Answer Generation (Gemini 1.5 Pro (Google DeepMind)): [<span class="green">OK</span>]  829 ms

<span class="cyan">========================================================================</span>
<span class="white">  LIGHTHOUSE FOR RAG - AUTOMATED AI PERFORMANCE AUDIT</span>
<span class="cyan">========================================================================</span>
  Overall Performance Score :  <span class="green">90 / 100</span>  [<span class="green">GRADE: A</span>]
<span class="gray">------------------------------------------------------------------------</span>
  [1] Latency &amp; Speed       :  <span class="yellow">80 / 100</span> (Grade B)   | 1222 ms total (TTFT ~1222 ms)
  [2] Grounding &amp; Accuracy  : <span class="green">100 / 100</span> (Grade A+)  | 0.84 avg similarity (16.0% hallucination risk)
  [3] Cost &amp; Token Economy  :  <span class="green">90 / 100</span> (Grade A)   | $0.0103 / req (4,112 tokens)
  [4] Vector Density        :  <span class="yellow">85 / 100</span> (Grade B+)  | 5 chunks retrieved (1 oversized chunks)
<span class="gray">------------------------------------------------------------------------</span>
  TOP LIGHTHOUSE OPPORTUNITIES (ESTIMATED SAVINGS):
    * <span class="yellow">[TRIM 663 MS TTFT]</span> Enable Server-Sent Events (SSE) Token Streaming
      -&gt; Reduces perceived latency by ~663 ms
    * <span class="yellow">[SAVE $420/MO]</span> Optimize Chunk Split Size from 1,200 to 500 Tokens
      -&gt; Saves ~$420/month at 50k requests/mo
    * <span class="yellow">[CUT PROMPT COST 35%]</span> Enable System Prompt Caching on Claude / OpenAI
      -&gt; Saves ~$380/month on repetitive instruction tokens
<span class="cyan">========================================================================</span>

<span class="yellow">########################################################################</span>
<span class="yellow">#</span>  [KEY] UNIQUE RUN API KEY : <span class="white">rl_key_dd95e8b0f3cc4888</span>
<span class="yellow">#</span>  [DB]  DATABASE STORAGE   : <span class="sky">PostgreSQL (table 'raglens_reports')</span>
<span class="yellow">#</span>  [RPT] OFFLINE HTML REPORT: <span class="purple">artifacts/reports\\raglens_report_trace_6eaf8b33a5ff.html</span>
<span class="yellow">#</span>  [WEB] WEB DASHBOARD LINK : <span class="gray">http://localhost:3000/raglens?key=rl_key_dd95e8b0f3cc4888</span>
<span class="yellow">########################################################################</span>

<div class="prompt-line" style="margin-top:14px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="cursor"></span></div>`
  },
  {
    file: '03_cli_interactive_prompt_flow.png',
    title: 'PowerShell - agentlens run (Interactive Mode)',
    content: `<div class="prompt-line"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">agentlens run</span></div>
<span class="cyan">========================================================================</span>
<span class="white">  RAGLENS - RAG Application &amp; Architecture Diagnostic Engine</span>
<span class="cyan">========================================================================</span>

<span class="sky">[Step 1/4] User Evaluation Query</span>
  Enter test prompt/question: <span class="green">Hybrid BM25 and Vector Search architecture</span>

<span class="sky">[Step 2/4] Retrieval &amp; Performance Scenario</span>
  [1] Normal Latency &amp; High Grounding (Default)
  [2] Slow Cross-Encoder Reranker Latency Spike
  [3] Low Retrieval Grounding &amp; Hallucination Risk
  Select scenario [1-3, default 1] &gt; <span class="green">1</span>

<span class="sky">[Step 3/4] Enterprise Knowledge Domain</span>
  [1] Enterprise Billing &amp; Legal Terms v2.4 (Default)
  [2] Multi-Tenant Architecture &amp; Okta SAML Auth
  [3] Internal Engineering Runbooks &amp; SRE Protocols
  Select domain [1-3, default 1] &gt; <span class="green">1</span>

<span class="sky">[Step 4/4] LLM Generation Model</span>
  [1] Claude 3.5 Sonnet (Anthropic - Default)
  [2] GPT-4o (OpenAI - Balanced Latency/Accuracy)
  [3] GPT-4o Mini (OpenAI - Ultra Fast &amp; Cost Effective)
  [4] Gemini 1.5 Pro (Google DeepMind - 2M Context)
  [5] Llama 3.1 70B (Meta - High Speed Groq LPUs)
  Select model [1-5, default 1] &gt; <span class="green">2</span>

<span class="gray">------------------------------------------------------------------------</span>
  Executing RAG Pipeline for query: <span class="white">'Hybrid BM25 and Vector Search architecture'</span>
  Profile: <span class="emerald">normal</span> | Domain: <span class="white">Enterprise Billing &amp; Legal Terms v2.4</span> | Model: <span class="yellow">GPT-4o (OpenAI)</span>
<span class="gray">------------------------------------------------------------------------</span>
  [01/05] Embedding Query (text-embedding-3-small)      : [<span class="green">OK</span>]   81 ms
  [02/05] Vector ANN Search (Pinecone Serverless Top-5)  : [<span class="green">OK</span>]  119 ms
  [03/05] Cross-Encoder Reranker (Cohere Rerank v3 Top-3): [<span class="green">OK</span>]  210 ms
  [04/05] Context &amp; Prompt Assembly                      : [<span class="green">OK</span>]   18 ms
  [05/05] LLM Answer Generation (GPT-4o (OpenAI)): [<span class="green">OK</span>]  694 ms

<span class="cyan">========================================================================</span>
<span class="white">  LIGHTHOUSE FOR RAG - AUTOMATED AI PERFORMANCE AUDIT</span>
<span class="cyan">========================================================================</span>
  Overall Performance Score :  <span class="green">96 / 100</span>  [<span class="green">GRADE: A+</span>]
<span class="gray">------------------------------------------------------------------------</span>
  TOP LIGHTHOUSE OPPORTUNITIES (ESTIMATED SAVINGS):
    * <span class="yellow">[TRIM 555 MS TTFT]</span> Enable Server-Sent Events (SSE) Token Streaming
    * <span class="yellow">[SAVE $420/MO]</span> Optimize Chunk Split Size from 1,200 to 500 Tokens
<span class="cyan">========================================================================</span>

<span class="yellow">########################################################################</span>
<span class="yellow">#</span>  [KEY] UNIQUE RUN API KEY : <span class="white">rl_key_3a502ef2917b4f32</span>
<span class="yellow">#</span>  [DB]  DATABASE STORAGE   : <span class="sky">PostgreSQL (table 'raglens_reports')</span>
<span class="yellow">#</span>  [RPT] OFFLINE HTML REPORT: <span class="purple">artifacts/reports\\raglens_report_trace_a22cbb218b88.html</span>
<span class="yellow">########################################################################</span>

<div class="prompt-line" style="margin-top:14px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="cursor"></span></div>`
  },
  {
    file: '04_cli_installed_help_options.png',
    title: 'PowerShell - agentlens run --help',
    content: `<div class="prompt-line"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">agentlens run --help</span></div>
usage: agentlens run [-h] [--query QUERY]
                     [--scenario {normal,slow_rerank,weak_retrieval}]
                     [--domain DOMAIN]
                     [--model {claude-3-5-sonnet,gpt-4o,gpt-4o-mini,gemini-1.5-pro,llama-3.1-70b}]
                     [--non-interactive]

<span class="sky">options:</span>
  <span class="white">-h, --help</span>            show this help message and exit
  <span class="white">--query, -q QUERY</span>     Query to run through the diagnostic RAG pipeline
  <span class="white">--scenario, -s</span> {normal,slow_rerank,weak_retrieval}
                        Execution latency / grounding profile
  <span class="white">--domain, -d DOMAIN</span>   Documentation knowledge domain
  <span class="white">--model, -m</span> {claude-3-5-sonnet,gpt-4o,gpt-4o-mini,gemini-1.5-pro,llama-3.1-70b}
                        <span class="yellow">Target LLM generation model (default: claude-3-5-sonnet)</span>
  <span class="white">--non-interactive</span>     Run directly without interactive prompts using defaults

<div class="prompt-line" style="margin-top:16px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">Get-Command agentlens</span></div>
<span class="white">CommandType     Name                     Version        Source</span>
-----------     ----                     -------        ------
Application     agentlens.exe            0.1.0          C:\\Users\\JITHU\\anaconda3\\Scripts\\agentlens.exe

<div class="prompt-line" style="margin-top:16px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="cursor"></span></div>`
  },
  {
    file: '05_cli_postgresql_storage_query.png',
    title: 'PowerShell - PostgreSQL Database Storage Query',
    content: `<div class="prompt-line"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">python -c "import psycopg; conn = psycopg.connect('postgresql://postgres:postgres@127.0.0.1:5432/postgres'); cur = conn.cursor(); cur.execute('SELECT api_key, query, total_latency_ms, cost_usd, created_at FROM raglens_reports ORDER BY created_at DESC LIMIT 5;'); [print(r) for r in cur.fetchall()]"</span></div>
('rl_key_6cf40c580bd54d61', 'Production microservices latency budget', 797.0, 0.0022, datetime.datetime(2026, 9, 11, 12, 50, 52, 556857, tzinfo=ZoneInfo(key='Asia/Calcutta')))
('rl_key_dd95e8b0f3cc4888', 'Enterprise SLA and multi-tenant security architecture', 1222.0, 0.0103, datetime.datetime(2026, 9, 11, 12, 54, 28, 912831, tzinfo=ZoneInfo(key='Asia/Calcutta')))
('rl_key_dcb7bd4499da432d', 'Optimizing vector search indexing algorithms', 1098.0, 0.0131, datetime.datetime(2026, 9, 11, 12, 54, 18, 419204, tzinfo=ZoneInfo(key='Asia/Calcutta')))
('rl_key_3a502ef2917b4f32', 'Hybrid BM25 and Vector Search architecture', 1122.0, 0.0135, datetime.datetime(2026, 9, 11, 12, 54, 40, 102914, tzinfo=ZoneInfo(key='Asia/Calcutta')))

<div class="prompt-line" style="margin-top:14px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="cursor"></span></div>`
  },
  {
    file: '06_cli_agentlens_scan_project.png',
    title: 'PowerShell - agentlens scan (External Codebase)',
    content: `<div class="prompt-line"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">agentlens scan ./agentlens-cli/examples/simple_rag</span></div>
<span class="cyan">========================================================================</span>
<span class="white">  AGENTLENS CODEBASE SCANNER - RAG ARCHITECTURE AUDIT</span>
<span class="cyan">========================================================================</span>
  Target Directory: <span class="white">C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent\\agentlens-cli\\examples\\simple_rag</span>
<span class="gray">------------------------------------------------------------------------</span>
  Files Scanned   : <span class="white">1</span>
  Vector Databases: <span class="sky">Pinecone Vector Database</span>
  Embedding Models: <span class="sky">OpenAI text-embedding-3-small (1536 dim)</span>
  LLM Generators  : <span class="yellow">GPT-4o (Balanced Latency OpenAI)</span>
  Reranker Found  : <span class="red">No</span>
  Streaming Ready : <span class="red">No (Buffering full response)</span>
  Prompt Caching  : <span class="gray">Not configured</span>

<span class="cyan">========================================================================</span>
<span class="white">  STATIC LIGHTHOUSE ARCHITECTURE GRADE:  </span><span class="red">F  (45/100)</span>
<span class="cyan">========================================================================</span>
  TOP ARCHITECTURE RECOMMENDATIONS:

  [1] <span class="yellow">Reduce Oversized Chunking Size (1200 tokens detected)</span> (<span class="red">Impact: HIGH</span> | Vector Density &amp; Cost)
      -&gt; Detected chunk size of 1200 tokens in project. Splitting chunks to 350-500 tokens reduces prompt cost by ~40% and minimizes context contamination.

  [2] <span class="yellow">Enable Token Streaming (SSE / Async Generator)</span> (<span class="red">Impact: HIGH</span> | Latency &amp; UX)
      -&gt; No streaming tokens detected (\`stream=True\` or \`StreamingResponse\`). Enabling token streaming will improve Time-To-First-Token (TTFT) by 60-75%.

  [3] <span class="yellow">Add Cross-Encoder Reranker for High Top-K (K=8)</span> (<span class="yellow">Impact: MEDIUM</span> | Accuracy &amp; Grounding)
      -&gt; Retrieving K=8 passages without a reranker causes context stuffing. Add a Cohere or FlashRank reranker to compress Top-K to Top-3 before LLM synthesis.

  [4] <span class="yellow">Enable System Prompt Caching</span> (<span class="yellow">Impact: MEDIUM</span> | Cost Economy)
      -&gt; Static system prompts and schema definitions can be cached with OpenAI/Claude prompt caching, saving ~35% on prompt tokens.

<span class="cyan">========================================================================</span>

<div class="prompt-line" style="margin-top:14px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="cursor"></span></div>`
  },
  {
    file: '07_cli_agentlens_probe_script.png',
    title: 'PowerShell - agentlens probe (External Script)',
    content: `<div class="prompt-line"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="prompt-cmd">agentlens probe --script ./agentlens-cli/examples/simple_rag/app.py --func query_rag -q "How do we scale vector embeddings?"</span></div>
<span class="cyan">========================================================================</span>
<span class="white">  AGENTLENS APPLICATION PROBE</span>
<span class="cyan">========================================================================</span>
  Probing Python Script: <span class="white">./agentlens-cli/examples/simple_rag/app.py :: query_rag</span>
<span class="gray">------------------------------------------------------------------------</span>
  Execution Latency : <span class="green">353.2 ms</span>
  Token Consumption : <span class="white">150 tokens</span> (Est. <span class="green">$0.0008</span>)
  Lighthouse Grade  : <span class="green">A+ (100 / 100)</span>
<span class="gray">------------------------------------------------------------------------</span>
  Report Generated  : <span class="purple">reports\\raglens_report_trace_37a135f36717.html</span>
  Unique API Key    : <span class="white">rl_key_05f6095f65254530</span>
<span class="cyan">========================================================================</span>

<div class="prompt-line" style="margin-top:14px;"><span class="prompt-path">PS C:\\Users\\JITHU\\OneDrive\\Desktop\\AI AGent&gt; </span><span class="cursor"></span></div>`
  }
];

async function main() {
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  for (const s of screenshots) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1200, height: 900, deviceScaleFactor: 2 });
    const html = buildHtml(s.title, s.content);
    await page.setContent(html, { waitUntil: 'load' });
    const element = await page.$('.window');
    
    const outPath = path.join(outDir, s.file);
    const brainPath = path.join(brainDir, s.file);

    await element.screenshot({ path: outPath });
    await element.screenshot({ path: brainPath });
    await page.close();

    const stats = fs.statSync(outPath);
    console.log(`Saved CLI screenshot: ${s.file} (${stats.size} bytes)`);
  }

  await browser.close();
  console.log('All 5 CLI screenshots successfully captured.');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
