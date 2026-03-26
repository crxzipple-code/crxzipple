import { buildApiUrl, requestJson } from "@/lib/api/client";
import type {
  TurnApprovalRequestedEventPayload,
  TurnApprovalResolvedEventPayload,
  TurnEventName,
  TurnMessageEventPayload,
  TurnResponse,
  TurnSnapshotResponse,
  TurnTextDeltaEventPayload,
  TurnToolEventPayload,
} from "@/types";

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

export function resolveTurnApproval(
  runId: string,
  requestId: string,
  decision: "allow_once" | "allow_for_session" | "always_for_agent" | "deny",
) {
  return requestJson<TurnResponse>(
    `/turns/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(requestId)}`,
    {
      method: "POST",
      body: JSON.stringify({ decision }),
    },
  );
}

export function requestTurnCompaction(
  runId: string,
  payload?: {
    reason?: string | null;
    preserve?: string | null;
  },
) {
  return requestJson<TurnResponse>(`/turns/${encodeURIComponent(runId)}/compact`, {
    method: "POST",
    body: JSON.stringify({
      reason: payload?.reason ?? null,
      preserve: payload?.preserve ?? null,
    }),
  });
}

export function requestTurnMemoryFlush(
  runId: string,
  payload?: {
    reason?: string | null;
  },
) {
  return requestJson<TurnResponse>(
    `/turns/${encodeURIComponent(runId)}/memory-flush`,
    {
      method: "POST",
      body: JSON.stringify({
        reason: payload?.reason ?? null,
      }),
    },
  );
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
        | TurnApprovalRequestedEventPayload
        | TurnApprovalResolvedEventPayload
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
    "approval_requested",
    "approval_resolved",
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
