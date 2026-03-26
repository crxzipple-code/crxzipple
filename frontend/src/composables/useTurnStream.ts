import { ref, type Ref } from "vue";

import { getConversationMessages, openTurnEvents } from "@/lib/api";
import type {
  ConversationSummary,
  PendingApprovalRequestPayload,
  SessionMessage,
  TurnApprovalRequestedEventPayload,
  TurnApprovalResolvedEventPayload,
  TurnEventEntry,
  TurnEventName,
  TurnMessageEventPayload,
  TurnResponse,
  TurnSnapshotResponse,
  TurnTextDeltaEventPayload,
  TurnToolEventPayload,
} from "@/types";

export function useTurnStream(options: {
  messages: Ref<SessionMessage[]>;
  activeTurn: Ref<TurnResponse | null>;
  pendingApproval: Ref<PendingApprovalRequestPayload | null>;
  activeBulkKey: Ref<string | null>;
  busy: Ref<boolean>;
  activeConversation: Ref<ConversationSummary | null>;
  draftMainKey: Ref<string>;
  hydrateConversationAfterTurn: (bulkKey: string | null) => Promise<void>;
  refreshConversations: () => Promise<void>;
}) {
  const streamState = ref<"idle" | "streaming" | "closed">("idle");
  const turnEvents = ref<TurnEventEntry[]>([]);
  const turnEventSource = ref<EventSource | null>(null);

  function pushEvent(event: TurnEventName, payload: TurnResponse) {
    turnEvents.value.unshift({
      id: `${payload.run.id}:${event}:${Date.now()}`,
      event,
      status: payload.run.status,
      stage: payload.run.stage,
      at: payload.run.updated_at,
      detail: payload.output_text?.slice(0, 120) ?? payload.run.status,
    });
    turnEvents.value = turnEvents.value.slice(0, 10);
  }

  function pushToolEvent(
    event: "tool_started" | "tool_completed",
    payload: TurnToolEventPayload,
  ) {
    turnEvents.value.unshift({
      id: `${payload.run_id}:${event}:${payload.message_id}`,
      event,
      status: payload.status,
      stage: payload.stage,
      at: payload.created_at,
      detail:
        event === "tool_completed" && payload.tool_status
          ? `${payload.tool_name} · ${payload.tool_status}`
          : payload.tool_name,
    });
    turnEvents.value = turnEvents.value.slice(0, 10);
  }

  function messagePreviewText(message: SessionMessage) {
    if (message.content && message.content.trim()) {
      return message.content.trim();
    }
    const payloadText = message.content_payload.text;
    if (typeof payloadText === "string" && payloadText.trim()) {
      return payloadText.trim();
    }
    return "";
  }

  function mergeMessage(message: SessionMessage) {
    let next = [...options.messages.value];
    if (next.some((item) => item.id === message.id)) {
      return;
    }

    if (message.role === "user") {
      const incomingText = messagePreviewText(message);
      const optimisticIndex = next.findIndex(
        (item) =>
          Boolean(item.metadata.optimistic) &&
          item.role === "user" &&
          messagePreviewText(item) === incomingText,
      );
      if (optimisticIndex >= 0) {
        next.splice(optimisticIndex, 1);
      }
    }

    if (
      message.role === "assistant" &&
      message.source_kind === "llm_invocation" &&
      typeof message.source_id === "string" &&
      message.source_id.trim()
    ) {
      const draftIndex = next.findIndex(
        (item) =>
          Boolean(item.metadata.optimistic) &&
          item.role === "assistant" &&
          item.metadata.llm_stream === true &&
          item.metadata.llm_stream_invocation_id === message.source_id,
      );
      if (draftIndex >= 0) {
        next.splice(draftIndex, 1);
      }
    }

    next.push(message);
    next.sort((left, right) => left.sequence_no - right.sequence_no);
    options.messages.value = next;
  }

  function mergeSnapshotMessages(snapshotMessages: SessionMessage[]) {
    if (snapshotMessages.length === 0) {
      return;
    }
    const merged = new Map<string, SessionMessage>();
    for (const message of options.messages.value) {
      if (!message.metadata.optimistic) {
        merged.set(message.id, message);
      }
    }
    for (const message of snapshotMessages) {
      merged.set(message.id, message);
    }
    options.messages.value = [...merged.values()].sort(
      (left, right) => left.sequence_no - right.sequence_no,
    );
  }

  function mergeStreamingAssistant(payload: TurnTextDeltaEventPayload) {
    const next = [...options.messages.value];
    const existingIndex = next.findIndex(
      (item) =>
        Boolean(item.metadata.optimistic) &&
        item.role === "assistant" &&
        item.metadata.llm_stream === true &&
        item.metadata.llm_stream_invocation_id === payload.invocation_id,
    );
    const baseMessage: SessionMessage = {
      id: `local-assistant-${payload.invocation_id}`,
      session_key:
        options.activeConversation.value?.session_key ?? options.draftMainKey.value,
      session_id:
        options.activeConversation.value?.active_session_id ?? "pending-session",
      sequence_no: next.length + 1,
      role: "assistant",
      kind: "message",
      content: payload.text,
      content_payload: { text: payload.text },
      source_kind: "llm_stream",
      source_id: payload.invocation_id,
      visibility: "default",
      metadata: {
        optimistic: true,
        llm_stream: true,
        llm_stream_invocation_id: payload.invocation_id,
      },
      created_at: new Date().toISOString(),
    };

    if (existingIndex >= 0) {
      next[existingIndex] = {
        ...next[existingIndex],
        content: payload.text,
        content_payload: { text: payload.text },
        metadata: {
          ...next[existingIndex].metadata,
          optimistic: true,
          llm_stream: true,
          llm_stream_invocation_id: payload.invocation_id,
        },
      };
    } else {
      next.push(baseMessage);
    }

    next.sort((left, right) => left.sequence_no - right.sequence_no);
    options.messages.value = next;
  }

  function closeTurnStream() {
    turnEventSource.value?.close();
    turnEventSource.value = null;
    if (streamState.value === "streaming") {
      streamState.value = "closed";
    }
  }

  function syncPendingApprovalFromTurn(payload: TurnResponse | TurnSnapshotResponse) {
    const rawRequest = payload.run.metadata.pending_approval_request;
    if (
      payload.run.stage === "waiting_for_confirmation" &&
      rawRequest &&
      typeof rawRequest === "object"
    ) {
      const record = rawRequest as Record<string, unknown>;
      options.pendingApproval.value = {
        request_id: String(record.request_id ?? ""),
        effect_id: String(record.effect_id ?? ""),
        label: String(record.label ?? "Additional access"),
        reason: String(record.reason ?? ""),
        tool_ids: Array.isArray(record.tool_ids)
          ? record.tool_ids.map((item) => String(item))
          : [],
        scope_hint:
          record.scope_hint === null || record.scope_hint === undefined
            ? null
            : String(record.scope_hint),
        created_at: String(record.created_at ?? new Date().toISOString()),
      };
      return;
    }
    options.pendingApproval.value = null;
  }

  function clearTurnEvents() {
    turnEvents.value = [];
  }

  function setStreamState(state: "idle" | "streaming" | "closed") {
    streamState.value = state;
  }

  function watchTurn(runId: string, optionsByRun?: { backgroundMaintenance?: boolean }) {
    closeTurnStream();
    if (!optionsByRun?.backgroundMaintenance) {
      streamState.value = "streaming";
    }
    turnEventSource.value = openTurnEvents(runId, {
      pollIntervalSeconds: 0.35,
      timeoutSeconds: 90,
      onEvent: async (event, payload) => {
        if (optionsByRun?.backgroundMaintenance) {
          const turnPayload =
            event === "snapshot"
              ? ({
                  run: (payload as TurnSnapshotResponse).run,
                  output_text: (payload as TurnSnapshotResponse).output_text,
                } satisfies TurnResponse)
              : (payload as TurnResponse);
          if (
            turnPayload.run.bulk_key &&
            (event === "completed" || event === "failed" || event === "cancelled")
          ) {
            closeTurnStream();
            await options.refreshConversations();
            if (options.activeBulkKey.value === turnPayload.run.bulk_key) {
              options.messages.value = await getConversationMessages(turnPayload.run.bulk_key, {
                includeArchived: true,
              });
            }
          }
          return;
        }
        if (event === "message_appended") {
          mergeMessage((payload as TurnMessageEventPayload).message);
          return;
        }
        if (event === "llm_text_delta") {
          mergeStreamingAssistant(payload as TurnTextDeltaEventPayload);
          return;
        }
        if (event === "tool_started" || event === "tool_completed") {
          pushToolEvent(event, payload as TurnToolEventPayload);
          return;
        }
        if (event === "approval_requested") {
          options.pendingApproval.value = (
            payload as TurnApprovalRequestedEventPayload
          ).request;
          return;
        }
        if (event === "approval_resolved") {
          const resolution = payload as TurnApprovalResolvedEventPayload;
          if (options.pendingApproval.value?.request_id === resolution.request_id) {
            options.pendingApproval.value = null;
          }
          return;
        }

        const turnPayload =
          event === "snapshot"
            ? ({
                run: (payload as TurnSnapshotResponse).run,
                output_text: (payload as TurnSnapshotResponse).output_text,
              } satisfies TurnResponse)
            : (payload as TurnResponse);

        options.activeTurn.value = turnPayload;
        syncPendingApprovalFromTurn(
          event === "snapshot"
            ? (payload as TurnSnapshotResponse)
            : turnPayload,
        );
        if (turnPayload.run.bulk_key) {
          options.activeBulkKey.value = turnPayload.run.bulk_key;
        }
        pushEvent(event, turnPayload);

        if (event === "snapshot") {
          mergeSnapshotMessages((payload as TurnSnapshotResponse).messages);
        }
        if (event === "completed" || event === "failed" || event === "cancelled") {
          options.busy.value = false;
          options.pendingApproval.value = null;
          streamState.value = "closed";
          closeTurnStream();
          await options.hydrateConversationAfterTurn(turnPayload.run.bulk_key);
        }
        if (event === "timeout") {
          options.busy.value = false;
          streamState.value = "closed";
        }
      },
      onError: () => {
        if (!optionsByRun?.backgroundMaintenance) {
          streamState.value = "closed";
        }
      },
    });
  }

  return {
    streamState,
    turnEvents,
    pushEvent,
    closeTurnStream,
    syncPendingApprovalFromTurn,
    clearTurnEvents,
    setStreamState,
    watchTurn,
  };
}
