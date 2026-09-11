"""Small local M2 SDK example; run from the repository root."""

from agentlens import AgentLens, InMemoryTraceExporter

exporter = InMemoryTraceExporter()
client = AgentLens(project_id="support-agent", exporter=exporter)

with client.trace("answer-question") as trace:
    with trace.span("retrieve", span_type="retrieval") as retrieve:
        retrieve.set_input({"query": "How do I reset my password?"})
        retrieve.set_output({"documents": ["password-reset-guide"]})
        retrieve.add_event("retrieval-complete", attributes={"count": 1})

    with trace.span("generate", span_type="llm") as generate:
        generate.set_input({"question": "How do I reset my password?"})
        generate.set_output({"answer": "Use the password reset link."})
        generate.set_usage(input_tokens=20, output_tokens=8, total_tokens=28)

finished = exporter.traces[0]
print(finished.to_json())
