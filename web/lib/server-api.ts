import { randomUUID } from "node:crypto";

const allowedPaths = [
  /^analytics\/(overview|timeseries|evaluations|hotspots)$/,
  /^runtime\/summary$/,
  /^traces$/,
  /^traces\/[0-9a-f-]{36}$/i,
  /^traces\/[0-9a-f-]{36}\/profile$/i,
  /^traces\/[0-9a-f-]{36}\/evaluation-results$/i,
  /^evaluation-results$/,
  /^evaluation-results\/[0-9a-f-]{36}$/i,
  /^datasets$/,
  /^datasets\/[0-9a-f-]{36}$/i,
  /^datasets\/[0-9a-f-]{36}\/versions$/i,
  /^datasets\/[0-9a-f-]{36}\/versions\/import$/i,
  /^dataset-versions\/[0-9a-f-]{36}$/i,
  /^dataset-versions\/[0-9a-f-]{36}\/export$/i,
  /^dataset-versions\/[0-9a-f-]{36}\/cases$/i,
  /^dataset-versions\/[0-9a-f-]{36}\/cases\/from-trace$/i,
  /^dataset-versions\/[0-9a-f-]{36}\/cases\/[0-9a-f-]{36}$/i,
  /^dataset-versions\/[0-9a-f-]{36}\/finalize$/i,
  /^replay-target-profiles$/,
  /^replay-runs$/,
  /^replay-runs\/[0-9a-f-]{36}$/i,
  /^replay-runs\/[0-9a-f-]{36}\/cases$/i,
  /^replay-runs\/[0-9a-f-]{36}\/cases\/[0-9a-f-]{36}$/i,
  /^regression-policies$/,
  /^regression-policies\/[0-9a-f-]{36}$/i,
  /^regression-runs$/,
  /^regression-runs\/[0-9a-f-]{36}$/i,
  /^regression-runs\/[0-9a-f-]{36}\/metrics$/i,
  /^regression-runs\/[0-9a-f-]{36}\/cases$/i,
  /^regression-runs\/[0-9a-f-]{36}\/cases\/[0-9a-f-]{36}$/i,
  /^quality-gate-policies$/,
  /^quality-gate-policies\/[0-9a-f-]{36}$/i,
  /^quality-gate-decisions$/,
  /^quality-gate-decisions\/[0-9a-f-]{36}$/i,
  /^system\/(metrics|overview)$/,
  /^organizations$/,
  /^organizations\/[0-9a-f-]{36}$/i,
  /^organizations\/[0-9a-f-]{36}\/projects$/i,
  /^projects$/,
  /^projects\/[a-zA-Z0-9_.-]+\/api-keys$/,
  /^projects\/[a-zA-Z0-9_.-]+\/api-keys\/[a-zA-Z0-9_.-]+$/,
  /^projects\/[a-zA-Z0-9_.-]+\/members$/,
  /^projects\/[a-zA-Z0-9_.-]+\/members\/[a-zA-Z0-9_@.-]+$/,
  /^auth\/(login|refresh|logout|me)$/,
  /^projects\/[a-zA-Z0-9_.-]+\/secrets$/,
  /^projects\/[a-zA-Z0-9_.-]+\/secrets\/[a-zA-Z0-9_.-]+$/,
  /^projects\/[a-zA-Z0-9_.-]+\/evaluation-suites$/,
  /^projects\/[a-zA-Z0-9_.-]+\/evaluation-suites\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/evaluation-suites\/[0-9a-f-]{36}\/run$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/evaluation-suites\/[0-9a-f-]{36}\/results$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/custom-evaluators$/,
  /^projects\/[a-zA-Z0-9_.-]+\/custom-evaluators\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/custom-evaluators\/[0-9a-f-]{36}\/test$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/providers\/test$/,
  /^projects\/[a-zA-Z0-9_.-]+\/providers\/generate$/,
  /^projects\/[a-zA-Z0-9_.-]+\/cost\/summary$/,
  /^projects\/[a-zA-Z0-9_.-]+\/budgets$/,
  /^projects\/[a-zA-Z0-9_.-]+\/budgets\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/experiments$/,
  /^projects\/[a-zA-Z0-9_.-]+\/experiments\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/experiments\/[0-9a-f-]{36}\/split$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/experiments\/[0-9a-f-]{36}\/evaluations$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/experiments\/[0-9a-f-]{36}\/report$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/routing\/rules$/,
  /^projects\/[a-zA-Z0-9_.-]+\/routing\/rules\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/routing\/route$/,
  /^projects\/[a-zA-Z0-9_.-]+\/routing\/decisions$/,
  /^projects\/[a-zA-Z0-9_.-]+\/benchmarks$/,
  /^projects\/[a-zA-Z0-9_.-]+\/benchmarks\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/benchmarks\/[0-9a-f-]{36}\/runs$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/benchmarks\/pareto$/,
  /^projects\/[a-zA-Z0-9_.-]+\/qualifications$/,
  /^projects\/[a-zA-Z0-9_.-]+\/qualifications\/evaluate$/,
  /^projects\/[a-zA-Z0-9_.-]+\/drift\/baselines$/,
  /^projects\/[a-zA-Z0-9_.-]+\/drift\/baselines\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/drift\/detect$/,
  /^projects\/[a-zA-Z0-9_.-]+\/drift\/observations$/,
  /^projects\/[a-zA-Z0-9_.-]+\/monitors$/,
  /^projects\/[a-zA-Z0-9_.-]+\/monitors\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/monitors\/[0-9a-f-]{36}\/snapshots$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/monitors\/health$/,
  /^projects\/[a-zA-Z0-9_.-]+\/alerts\/rules$/,
  /^projects\/[a-zA-Z0-9_.-]+\/alerts\/rules\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/alerts\/incidents$/,
  /^projects\/[a-zA-Z0-9_.-]+\/alerts\/incidents\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/rca\/diagnose$/,
  /^projects\/[a-zA-Z0-9_.-]+\/rca\/reports$/,
  /^projects\/[a-zA-Z0-9_.-]+\/rca\/reports\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/rca\/clusters$/,
  /^projects\/[a-zA-Z0-9_.-]+\/governance\/audit$/,
  /^projects\/[a-zA-Z0-9_.-]+\/governance\/policies$/,
  /^projects\/[a-zA-Z0-9_.-]+\/governance\/policies\/[0-9a-f-]{36}$/i,
  /^projects\/[a-zA-Z0-9_.-]+\/governance\/export$/,
  /^system\/readiness$/,
  /^system\/certify$/,
  /^rag\/(health|query|document|documents|reset|agent|arena|audit|benchmark|upload|webhooks(\/test)?)$/,
  /^raglens\/(overview|architecture|chunks|performance|cost|traces|telemetry|simulate-trace|execute|reports|report\/[a-zA-Z0-9_.-]+|explain\/[a-zA-Z0-9_.-]+)$/,
];

export async function proxyBackend(
  method: string,
  path: string,
  search: string,
  requestBody: ArrayBuffer | null = null,
  origin: string | null = null,
  expectedOrigin: string | null = null,
): Promise<Response> {
  const cleanPath = path.replace(/^v1\//, "");
  if (!allowedPaths.some((pattern) => pattern.test(cleanPath))) {
    return Response.json({ code: "not_found", message: "Dashboard endpoint was not found." }, { status: 404 });
  }
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method.toUpperCase()) && origin && expectedOrigin) {
    const normOrigin = origin.replace("127.0.0.1", "localhost");
    const normExpected = expectedOrigin.replace("127.0.0.1", "localhost");
    if (normOrigin !== normExpected) {
      return Response.json(
        { code: "csrf_rejected", message: "Request origin is not allowed." },
        { status: 403 },
      );
    }
  }
  const baseUrl = process.env.AGENTLENS_API_BASE_URL || "http://127.0.0.1:8000";
  const projectKey = process.env.AGENTLENS_PROJECT_API_KEY || "dev-key-12345";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8_000);
  const requestId = randomUUID();
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/${cleanPath}${search}`, {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${projectKey}`,
        "X-Request-ID": requestId,
        ...(requestBody ? { "Content-Type": "application/json" } : {}),
      },
      body: requestBody,
      cache: "no-store",
      signal: controller.signal,
    });
    const responseBody = await response.arrayBuffer();
    const headers = new Headers({
      "Content-Type": response.headers.get("content-type") ?? "application/json",
      "X-Request-ID": response.headers.get("x-request-id") ?? requestId,
      "Cache-Control": "no-store",
    });
    return new Response(responseBody, { status: response.status, headers });
  } catch {
    return Response.json(
      { code: "backend_unavailable", message: "Dashboard backend is temporarily unavailable.", request_id: requestId },
      { status: 503, headers: { "X-Request-ID": requestId } },
    );
  } finally {
    clearTimeout(timeout);
  }
}
