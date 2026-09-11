import { proxyBackend } from "../../../lib/server-api";

async function forward(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path: pathParts } = await params;
  const path = pathParts.join("/");
  const body = request.method === "GET" || request.method === "DELETE" ? null : await request.arrayBuffer();
  const requestUrl = new URL(request.url);
  const expectedOrigin =
    process.env.AGENTLENS_DASHBOARD_ORIGIN ??
    `${requestUrl.protocol}//${request.headers.get("host") ?? requestUrl.host}`;
  return proxyBackend(
    request.method,
    path,
    requestUrl.search,
    body,
    request.headers.get("origin"),
    expectedOrigin,
  );
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
