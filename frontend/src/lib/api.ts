import type {
  AgentProfileSummary,
  ConversationSummary,
  LlmProfileSummary,
  SessionMessage,
  TurnMessageEventPayload,
  TurnEventName,
  TurnResponse,
  TurnSnapshotResponse,
  TurnTextDeltaEventPayload,
  TurnToolEventPayload,
} from "@/types";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

function buildApiUrl(path: string): string {
  if (!API_BASE) {
    return path;
  }
  if (/^https?:\/\//.test(API_BASE)) {
    return new URL(path, `${API_BASE}/`).toString();
  }
  return `${API_BASE}${path}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export function getHealth() {
  return requestJson<{ status: string }>("/health");
}

export function listConversations() {
  return requestJson<ConversationSummary[]>("/conversations");
}

export function listAgents() {
  return requestJson<AgentProfileSummary[]>("/agents");
}

export function listLlms() {
  return requestJson<LlmProfileSummary[]>("/llms");
}

export function getConversation(bulkKey: string) {
  return requestJson<ConversationSummary>(
    `/conversations/${encodeURIComponent(bulkKey)}`,
  );
}

export function getConversationMessages(bulkKey: string) {
  return requestJson<SessionMessage[]>(
    `/conversations/${encodeURIComponent(bulkKey)}/messages`,
  );
}

export function createTurn(payload: Record<string, unknown>) {
  return requestJson<TurnResponse>("/turns", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTurn(runId: string) {
  return requestJson<TurnResponse>(`/turns/${encodeURIComponent(runId)}`);
}

export function cancelTurn(runId: string, reason?: string) {
  return requestJson<TurnResponse>(`/turns/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export function openTurnEvents(
  runId: string,
  options: {
    pollIntervalSeconds?: number;
    timeoutSeconds?: number;
    onEvent: (
      event: TurnEventName,
      payload:
        | TurnResponse
        | TurnSnapshotResponse
        | TurnMessageEventPayload
        | TurnTextDeltaEventPayload
        | TurnToolEventPayload
    ) => void;
    onError?: (error: Event) => void;
  },
) {
  const url = new URL(
    buildApiUrl(`/turns/${encodeURIComponent(runId)}/events`),
    window.location.origin,
  );
  url.searchParams.set(
    "poll_interval_seconds",
    String(options.pollIntervalSeconds ?? 0.5),
  );
  url.searchParams.set("timeout_seconds", String(options.timeoutSeconds ?? 90));

  const source = new EventSource(url.toString());
  const events: TurnEventName[] = [
    "snapshot",
    "updated",
    "message_appended",
    "llm_text_delta",
    "tool_started",
    "tool_completed",
    "completed",
    "failed",
    "cancelled",
    "timeout",
  ];

  for (const eventName of events) {
    source.addEventListener(eventName, (message) => {
      const payload = JSON.parse((message as MessageEvent<string>).data) as TurnResponse;
      options.onEvent(eventName, payload);
    });
  }

  source.onerror = (error) => {
    options.onError?.(error);
  };

  return source;
}
