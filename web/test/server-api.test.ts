import { describe, expect, it, vi } from "vitest";
import { proxyBackend } from "../lib/server-api";

describe("dashboard mutation boundary", () => {
  it("rejects missing or foreign origins before forwarding", async () => {
    process.env.AGENTLENS_API_BASE_URL = "http://127.0.0.1:8000";
    process.env.AGENTLENS_PROJECT_API_KEY = "server-only-test-key";
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const response = await proxyBackend("POST", "traces", "", new ArrayBuffer(0), "http://evil", "http://dashboard");
    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockRestore();
  });

  it("forwards an exact same-origin mutation with server credentials", async () => {
    process.env.AGENTLENS_API_BASE_URL = "http://127.0.0.1:8000";
    process.env.AGENTLENS_PROJECT_API_KEY = "server-only-test-key";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 202, headers: { "content-type": "application/json" } }),
    );
    const response = await proxyBackend("POST", "traces", "", new ArrayBuffer(0), "http://dashboard", "http://dashboard");
    expect(response.status).toBe(202);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      headers: expect.objectContaining({ Authorization: "Bearer server-only-test-key" }),
    });
    fetchMock.mockRestore();
  });
});
