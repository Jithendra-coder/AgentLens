"""Send one finished M2 trace through the local M3 HTTP gateway."""

from agentlens import AgentLens, HttpTraceExporter

exporter = HttpTraceExporter(
    base_url="http://127.0.0.1:8000",
    api_key="dev-m3-key-not-real",
    user_agent="agentlens-m3-example/0.1",
)
client = AgentLens(project_id="support-agent", exporter=exporter)

with client.trace("request") as trace:
    with trace.span("work", span_type="custom"):
        pass

print(trace.finished_trace)
