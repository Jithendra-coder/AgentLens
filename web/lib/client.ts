import type { ApiErrorBody } from "./types";

export class DashboardApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;

  constructor(message: string, status: number, requestId: string | null) {
    super(message);
    this.name = "DashboardApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

export async function dashboardFetch<T>(
  path: string,
  options: { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: unknown } = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8_000);
  try {
    const response = await fetch(`/api/${path.replace(/^\//, "")}`, {
      method: options.method ?? "GET",
      headers: { Accept: "application/json" },
      ...(options.body === undefined
        ? {}
        : {
            body: JSON.stringify(options.body),
            headers: { Accept: "application/json", "Content-Type": "application/json" },
          }),
      cache: "no-store",
      signal: controller.signal,
    });
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody | T;
    if (!response.ok) {
      const error = body as ApiErrorBody;
      throw new DashboardApiError(
        error.message ?? "Dashboard request failed.",
        response.status,
        error.request_id ?? response.headers.get("x-request-id"),
      );
    }
    return body as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function formatNumber(value: number | null, digits = 0): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
}

export function formatPercent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

export function formatDuration(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value < 1000 ? `${formatNumber(value, 0)} ms` : `${(value / 1000).toFixed(2)} s`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

export function jsonParams(params: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const result = query.toString();
  return result ? `?${result}` : "";
}
