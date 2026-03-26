import { computed, ref, type Ref } from "vue";

import {
  cancelTurn,
  createTurn,
  getConversation,
  getConversationMessages,
  getTurn,
  listConversations,
  requestTurnCompaction,
  requestTurnMemoryFlush,
  resolveTurnApproval,
} from "@/lib/api";
import {
  createDraftRoute,
  routeFromConversation,
  routePayload,
} from "@/lib/conversationRoute";
import type {
  ConversationRoute,
  ConversationSummary,
  PendingApprovalRequestPayload,
  SessionMessage,
  TurnEventName,
  TurnResponse,
  TurnSnapshotResponse,
} from "@/types";

type StreamState = "idle" | "streaming" | "closed";

export type ConversationSessionStreamBridge = {
  pushEvent: (event: TurnEventName, payload: TurnResponse) => void;
  closeTurnStream: () => void;
  syncPendingApprovalFromTurn: (
    payload: TurnResponse | TurnSnapshotResponse,
  ) => void;
  clearTurnEvents: () => void;
  setStreamState: (state: StreamState) => void;
  watchTurn: (
    runId: string,
    options?: { backgroundMaintenance?: boolean },
  ) => void;
};

export function useConversationSession(options: {
  defaultAgentId: Ref<string>;
  selectedAgentId: Ref<string | null>;
  selectedLlmId: Ref<string | null>;
  refreshMemoryPanel: (agentId?: string | null) => Promise<void>;
  refreshAgentHomeIfSafe: (agentId?: string | null) => Promise<void>;
  closeDeckIfCompact: () => void;
}) {
  const conversations = ref<ConversationSummary[]>([]);
  const activeBulkKey = ref<string | null>(null);
  const activeConversation = ref<ConversationSummary | null>(null);
  const messages = ref<SessionMessage[]>([]);
  const loadingConversations = ref(false);
  const loadingMessages = ref(false);
  const busy = ref(false);
  const lastError = ref<string | null>(null);
  const activeTurn = ref<TurnResponse | null>(null);
  const pendingApproval = ref<PendingApprovalRequestPayload | null>(null);
  const draftRoute = ref<ConversationRoute>(
    createDraftRoute(options.selectedAgentId.value ?? options.defaultAgentId.value),
  );

  const activeRoute = computed(() =>
    activeConversation.value
      ? {
          ...routeFromConversation(
            activeConversation.value,
            options.defaultAgentId.value,
          ),
          agentId:
            options.selectedAgentId.value ??
            activeConversation.value.runtime_binding.agent_id ??
            options.defaultAgentId.value,
          llmId:
            options.selectedLlmId.value ??
            activeConversation.value.runtime_binding.llm_id ??
            undefined,
        }
      : {
          ...draftRoute.value,
          agentId:
            options.selectedAgentId.value ?? draftRoute.value.agentId,
          llmId:
            options.selectedLlmId.value ?? draftRoute.value.llmId ?? undefined,
        },
  );

  const currentRunId = computed(
    () =>
      activeConversation.value?.display_run_id ??
      activeConversation.value?.latest_run_id ??
      activeTurn.value?.run.id ??
      null,
  );

  let streamBridge: ConversationSessionStreamBridge | null = null;

  function bindStream(bridge: ConversationSessionStreamBridge) {
    streamBridge = bridge;
  }

  function requireStream() {
    if (!streamBridge) {
      throw new Error("Conversation session stream bridge is not bound.");
    }
    return streamBridge;
  }

  function isTerminalRunStatus(status: string | null | undefined) {
    return status === "completed" ||
      status === "failed" ||
      status === "cancelled" ||
      status === "timed_out";
  }

  function buildOptimisticUserMessage(content: string): SessionMessage {
    const now = new Date().toISOString();
    return {
      id: `local-user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      session_key:
        activeConversation.value?.session_key ?? draftRoute.value.mainKey,
      session_id:
        activeConversation.value?.active_session_id ?? "pending-session",
      sequence_no: messages.value.length + 1,
      role: "user",
      kind: "message",
      content,
      content_payload: { text: content },
      source_kind: "web",
      source_id: "local-pending",
      visibility: "default",
      metadata: {
        optimistic: true,
      },
      created_at: now,
    };
  }

  async function refreshConversations() {
    loadingConversations.value = true;
    try {
      conversations.value = await listConversations();
      if (activeBulkKey.value) {
        const refreshedActive = conversations.value.find(
          (item) => item.bulk_key === activeBulkKey.value,
        );
        if (refreshedActive) {
          activeConversation.value = refreshedActive;
        }
      }
      if (
        activeBulkKey.value &&
        !conversations.value.some(
          (item) => item.bulk_key === activeBulkKey.value,
        )
      ) {
        activeBulkKey.value = null;
        activeConversation.value = null;
      }
    } finally {
      loadingConversations.value = false;
    }
  }

  async function hydrateConversationAfterTurn(bulkKey: string | null) {
    await refreshConversations();
    if (bulkKey) {
      await selectConversation(bulkKey);
    } else {
      await options.refreshMemoryPanel(
        activeRoute.value.agentId ?? options.selectedAgentId.value,
      );
    }
  }

  async function syncActiveTurnForConversation(
    conversation: ConversationSummary,
  ) {
    const displayRunId =
      conversation.display_run_id?.trim() ||
      conversation.latest_run_id?.trim();
    const stream = requireStream();
    if (!displayRunId) {
      activeTurn.value = null;
      pendingApproval.value = null;
      stream.setStreamState("idle");
      return;
    }

    const turn = await getTurn(displayRunId);
    activeTurn.value = turn;
    stream.syncPendingApprovalFromTurn(turn);

    const latestRunId = conversation.latest_run_id?.trim();
    const shouldWatchBackgroundMaintenance =
      latestRunId &&
      latestRunId !== displayRunId &&
      conversation.latest_run_status !== null &&
      !isTerminalRunStatus(conversation.latest_run_status);

    if (shouldWatchBackgroundMaintenance) {
      stream.watchTurn(latestRunId, { backgroundMaintenance: true });
      return;
    }

    if (isTerminalRunStatus(turn.run.status)) {
      stream.setStreamState("idle");
      return;
    }
    stream.watchTurn(displayRunId);
  }

  async function selectConversation(bulkKey: string) {
    const stream = requireStream();
    stream.closeTurnStream();
    stream.clearTurnEvents();
    loadingMessages.value = true;
    lastError.value = null;
    try {
      const [conversation, history] = await Promise.all([
        getConversation(bulkKey),
        getConversationMessages(bulkKey, {
          includeArchived: true,
        }),
      ]);
      activeBulkKey.value = bulkKey;
      activeConversation.value = conversation;
      messages.value = history;
      pendingApproval.value = null;
      draftRoute.value = routeFromConversation(
        conversation,
        options.defaultAgentId.value,
      );
      options.selectedAgentId.value =
        conversation.runtime_binding.agent_id ??
        options.selectedAgentId.value ??
        options.defaultAgentId.value;
      options.selectedLlmId.value =
        conversation.runtime_binding.llm_id ?? null;
      await options.refreshMemoryPanel(
        conversation.runtime_binding.agent_id ??
          options.selectedAgentId.value ??
          options.defaultAgentId.value,
      );
      await options.refreshAgentHomeIfSafe();
      await syncActiveTurnForConversation(conversation);
      options.closeDeckIfCompact();
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error);
    } finally {
      loadingMessages.value = false;
    }
  }

  async function createFreshConversation() {
    const stream = requireStream();
    stream.closeTurnStream();
    activeBulkKey.value = null;
    activeConversation.value = null;
    messages.value = [];
    activeTurn.value = null;
    pendingApproval.value = null;
    stream.clearTurnEvents();
    draftRoute.value = createDraftRoute(
      options.selectedAgentId.value ?? options.defaultAgentId.value,
    );
    options.selectedLlmId.value = null;
    await options.refreshMemoryPanel(
      options.selectedAgentId.value ?? options.defaultAgentId.value,
    );
    await options.refreshAgentHomeIfSafe();
    options.closeDeckIfCompact();
  }

  async function submitTurn(content: string) {
    if (!content.trim() || busy.value) {
      return false;
    }
    const stream = requireStream();
    lastError.value = null;
    busy.value = true;

    const trimmedContent = content.trim();
    const route = activeRoute.value;
    const optimisticMessage = buildOptimisticUserMessage(trimmedContent);
    const previousMessages = [...messages.value];
    messages.value = [...messages.value, optimisticMessage];

    try {
      const payload = await createTurn({
        content: trimmedContent,
        source: "web",
        ...routePayload(route),
      });
      activeTurn.value = payload;
      stream.pushEvent("snapshot", payload);
      stream.syncPendingApprovalFromTurn(payload);
      if (payload.run.bulk_key) {
        activeBulkKey.value = payload.run.bulk_key;
      }
      await refreshConversations();
      stream.watchTurn(payload.run.id);
      return true;
    } catch (error) {
      messages.value = previousMessages;
      busy.value = false;
      lastError.value = error instanceof Error ? error.message : String(error);
      return false;
    }
  }

  async function cancelActiveTurn() {
    if (!activeTurn.value || !busy.value) {
      return;
    }
    const stream = requireStream();
    try {
      const payload = await cancelTurn(
        activeTurn.value.run.id,
        "user_cancelled",
      );
      activeTurn.value = payload;
      stream.pushEvent("cancelled", payload);
      busy.value = false;
      stream.closeTurnStream();
      await hydrateConversationAfterTurn(payload.run.bulk_key);
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error);
    }
  }

  async function requestCompaction() {
    if (!activeConversation.value || !currentRunId.value || busy.value || loadingMessages.value) {
      return;
    }
    const stream = requireStream();
    lastError.value = null;
    busy.value = true;
    pendingApproval.value = null;
    try {
      const payload = await requestTurnCompaction(currentRunId.value, {
        reason: "manual_compaction_from_ui",
      });
      activeTurn.value = payload;
      stream.pushEvent("snapshot", payload);
      stream.syncPendingApprovalFromTurn(payload);
      if (payload.run.bulk_key) {
        activeBulkKey.value = payload.run.bulk_key;
      }
      await refreshConversations();
      stream.watchTurn(payload.run.id);
    } catch (error) {
      busy.value = false;
      lastError.value = error instanceof Error ? error.message : String(error);
    }
  }

  async function requestMemoryFlush() {
    if (!activeConversation.value || !currentRunId.value || busy.value || loadingMessages.value) {
      return;
    }
    const stream = requireStream();
    lastError.value = null;
    busy.value = true;
    pendingApproval.value = null;
    try {
      const payload = await requestTurnMemoryFlush(currentRunId.value, {
        reason: "manual_memory_flush_from_ui",
      });
      activeTurn.value = payload;
      stream.pushEvent("snapshot", payload);
      stream.syncPendingApprovalFromTurn(payload);
      if (payload.run.bulk_key) {
        activeBulkKey.value = payload.run.bulk_key;
      }
      await refreshConversations();
      stream.watchTurn(payload.run.id);
    } catch (error) {
      busy.value = false;
      lastError.value = error instanceof Error ? error.message : String(error);
    }
  }

  async function resolveActiveApproval(
    decision: "allow_once" | "allow_for_session" | "always_for_agent" | "deny",
  ) {
    if (!activeTurn.value || !pendingApproval.value) {
      return;
    }
    const stream = requireStream();
    lastError.value = null;
    try {
      const payload = await resolveTurnApproval(
        activeTurn.value.run.id,
        pendingApproval.value.request_id,
        decision,
      );
      activeTurn.value = payload;
      stream.syncPendingApprovalFromTurn(payload);
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : String(error);
    }
  }

  return {
    conversations,
    activeBulkKey,
    activeConversation,
    messages,
    loadingConversations,
    loadingMessages,
    busy,
    lastError,
    activeTurn,
    pendingApproval,
    draftRoute,
    activeRoute,
    currentRunId,
    bindStream,
    refreshConversations,
    hydrateConversationAfterTurn,
    syncActiveTurnForConversation,
    selectConversation,
    createFreshConversation,
    submitTurn,
    cancelActiveTurn,
    requestCompaction,
    requestMemoryFlush,
    resolveActiveApproval,
  };
}
