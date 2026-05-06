const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

export type DataMode = "fixture" | "api";

export const dataMode: DataMode =
  import.meta.env.VITE_DATA_MODE === "fixture" ? "fixture" : "api";

export interface ApiErrorPayload {
  code: string;
  message: string;
  retryable?: boolean;
  trace_id?: string;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly payload: ApiErrorPayload | null;

  constructor(status: number, message: string, payload: ApiErrorPayload | null = null) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.payload = payload;
  }
}

export function buildApiUrl(path: string): string {
  if (!API_BASE) {
    return path;
  }
  if (/^https?:\/\//.test(API_BASE)) {
    return new URL(path, `${API_BASE}/`).toString();
  }
  return `${API_BASE}${path}`;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = buildApiUrl(path);
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (contentType.includes("text/html")) {
    throw new ApiClientError(
      response.status,
      `Expected JSON from ${url}, but received HTML. Check VITE_API_BASE or the Vite proxy route.`,
    );
  }

  if (!response.ok) {
    const payload = await readErrorPayload(response, url, contentType);
    throw new ApiClientError(
      response.status,
      payload?.message ?? `Request failed with status ${response.status}`,
      payload,
    );
  }

  try {
    return (await response.json()) as T;
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new ApiClientError(response.status, `Invalid JSON response from ${url}: ${detail}`);
  }
}

async function readErrorPayload(
  response: Response,
  url: string,
  contentType: string,
): Promise<ApiErrorPayload | null> {
  if (!contentType.includes("json")) {
    const body = await response.text();
    const preview = body.trim().replace(/\s+/g, " ").slice(0, 160);
    return {
      code: "non_json_error_response",
      message: preview
        ? `Expected JSON error payload from ${url}, but received ${
            contentType || "unknown content type"
          }: ${preview}`
        : `Expected JSON error payload from ${url}, but received ${
            contentType || "unknown content type"
          }.`,
    };
  }

  try {
    const value = (await response.json()) as Partial<ApiErrorPayload> & { detail?: unknown };
    const message = errorMessageFromJson(value);
    if (message) {
      return {
        code: typeof value.code === "string" ? value.code : "request_failed",
        message,
        retryable: Boolean(value.retryable),
        trace_id: typeof value.trace_id === "string" ? value.trace_id : undefined,
      };
    }
  } catch {
    return null;
  }
  return null;
}

function errorMessageFromJson(
  value: Partial<ApiErrorPayload> & { detail?: unknown },
): string | null {
  if (typeof value.message === "string") {
    return value.message;
  }
  if (typeof value.detail === "string") {
    return value.detail;
  }
  if (Array.isArray(value.detail)) {
    return "Request validation failed.";
  }
  return null;
}
