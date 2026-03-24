<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from "vue";

import ComposerPanel from "@/components/ComposerPanel.vue";
import ConversationSidebar from "@/components/ConversationSidebar.vue";
import MessageTimeline from "@/components/MessageTimeline.vue";
import TurnInspector from "@/components/TurnInspector.vue";
import {
  cancelTurn,
  createTurn,
  getConversation,
  getConversationMessages,
  listAgents,
  listConversations,
  listLlms,
  openTurnEvents,
} from "@/lib/api";
import {
  createDraftRoute,
  routeFromConversation,
  routePayload,
} from "@/lib/conversationRoute";
import type {
  AgentProfileSummary,
  ConversationRoute,
  ConversationSummary,
  LlmProfileSummary,
  SessionMessage,
  TurnMessageEventPayload,
  TurnEventEntry,
  TurnEventName,
  TurnResponse,
  TurnSnapshotResponse,
  TurnTextDeltaEventPayload,
  TurnToolEventPayload,
} from "@/types";

const defaultAgentId = ref("crxzipple");
const agents = ref<AgentProfileSummary[]>([]);
const llms = ref<LlmProfileSummary[]>([]);
const conversations = ref<ConversationSummary[]>([]);
const activeBulkKey = ref<string | null>(null);
const activeConversation = ref<ConversationSummary | null>(null);
const messages = ref<SessionMessage[]>([]);
const loadingConversations = ref(false);
const loadingMessages = ref(false);
const composer = ref("");
const busy = ref(false);
const lastError = ref<string | null>(null);
const activeTurn = ref<TurnResponse | null>(null);
const streamState = ref<"idle" | "streaming" | "closed">("idle");
const turnEvents = ref<TurnEventEntry[]>([]);
const draftRoute = ref<ConversationRoute>(createDraftRoute(defaultAgentId.value));
const turnEventSource = shallowRef<EventSource | null>(null);
const inspectorOpen = ref(true);
const deckOpen = ref(true);
const selectedAgentId = ref<string | null>(defaultAgentId.value);
const selectedLlmId = ref<string | null>(null);

const activeRoute = computed(() =>
  activeConversation.value
    ? {
        ...routeFromConversation(activeConversation.value, defaultAgentId.value),
        agentId:
          selectedAgentId.value ??
          activeConversation.value.runtime_binding.agent_id ??
          defaultAgentId.value,
        llmId:
          selectedLlmId.value ??
          activeConversation.value.runtime_binding.llm_id ??
          undefined,
      }
    : {
        ...draftRoute.value,
        agentId: selectedAgentId.value ?? draftRoute.value.agentId,
        llmId: selectedLlmId.value ?? draftRoute.value.llmId ?? undefined,
      },
);

const activeTitle = computed(() => {
  if (activeConversation.value?.last_message_preview) {
    return activeConversation.value.last_message_preview;
  }
  return "New thread";
});

const canSubmit = computed(
  () => composer.value.trim().length > 0 && !busy.value,
);

const inspectorPayload = computed(() =>
  JSON.stringify(routePayload(activeRoute.value), null, 2),
);

const outputPreview = computed(() => {
  const text = activeTurn.value?.output_text?.trim();
  if (!text) {
    return null;
  }
  if (text.length <= 260) {
    return text;
  }
  return `${text.slice(0, 257)}...`;
});

function buildOptimisticUserMessage(content: string): SessionMessage {
  const now = new Date().toISOString();
  return {
    id: `local-user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    session_key: activeConversation.value?.session_key ?? draftRoute.value.mainKey,
    session_id: activeConversation.value?.active_session_id ?? "pending-session",
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

function pushEvent(event: TurnEventName, payload: TurnResponse) {
  turnEvents.value.unshift({
    id: `${payload.run.id}:${event}:${Date.now()}`,
    event,
    status: payload.run.status,
    stage: payload.run.stage,
    at: new Date().toISOString(),
    detail: null,
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
  let next = [...messages.value];
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
  messages.value = next;
}

function mergeSnapshotMessages(snapshotMessages: SessionMessage[]) {
  if (snapshotMessages.length === 0) {
    return;
  }
  const merged = new Map<string, SessionMessage>();
  for (const message of messages.value) {
    if (!message.metadata.optimistic) {
      merged.set(message.id, message);
    }
  }
  for (const message of snapshotMessages) {
    merged.set(message.id, message);
  }
  messages.value = [...merged.values()].sort(
    (left, right) => left.sequence_no - right.sequence_no,
  );
}

function mergeStreamingAssistant(payload: TurnTextDeltaEventPayload) {
  const next = [...messages.value];
  const existingIndex = next.findIndex(
    (item) =>
      Boolean(item.metadata.optimistic) &&
      item.role === "assistant" &&
      item.metadata.llm_stream === true &&
      item.metadata.llm_stream_invocation_id === payload.invocation_id,
  );
  const baseMessage: SessionMessage = {
    id: `local-assistant-${payload.invocation_id}`,
    session_key: activeConversation.value?.session_key ?? draftRoute.value.mainKey,
    session_id: activeConversation.value?.active_session_id ?? "pending-session",
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
  messages.value = next;
}

function closeTurnStream() {
  turnEventSource.value?.close();
  turnEventSource.value = null;
  if (streamState.value === "streaming") {
    streamState.value = "closed";
  }
}

async function refreshProfiles() {
  const [agentItems, llmItems] = await Promise.all([listAgents(), listLlms()]);
  agents.value = agentItems.filter((item) => item.enabled);
  llms.value = llmItems.filter((item) => item.enabled);

  if (
    selectedAgentId.value === null ||
    !agents.value.some((item) => item.id === selectedAgentId.value)
  ) {
    selectedAgentId.value =
      agents.value.find((item) => item.id === defaultAgentId.value)?.id ??
      agents.value[0]?.id ??
      defaultAgentId.value;
  }
}

async function refreshConversations() {
  loadingConversations.value = true;
  try {
    conversations.value = await listConversations();
    if (
      activeBulkKey.value &&
      !conversations.value.some((item) => item.bulk_key === activeBulkKey.value)
    ) {
      activeBulkKey.value = null;
      activeConversation.value = null;
    }
  } finally {
    loadingConversations.value = false;
  }
}

async function selectConversation(bulkKey: string) {
  loadingMessages.value = true;
  lastError.value = null;
  try {
    const [conversation, history] = await Promise.all([
      getConversation(bulkKey),
      getConversationMessages(bulkKey),
    ]);
    activeBulkKey.value = bulkKey;
    activeConversation.value = conversation;
    messages.value = history;
    draftRoute.value = routeFromConversation(conversation, defaultAgentId.value);
    selectedAgentId.value =
      conversation.runtime_binding.agent_id ??
      selectedAgentId.value ??
      defaultAgentId.value;
    selectedLlmId.value = conversation.runtime_binding.llm_id ?? null;
    closeDeckIfCompact();
  } catch (error) {
    lastError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loadingMessages.value = false;
  }
}

function createFreshConversation() {
  closeTurnStream();
  activeBulkKey.value = null;
  activeConversation.value = null;
  messages.value = [];
  activeTurn.value = null;
  turnEvents.value = [];
  draftRoute.value = createDraftRoute(selectedAgentId.value ?? defaultAgentId.value);
  selectedLlmId.value = null;
  composer.value = "";
  closeDeckIfCompact();
}

function selectAgent(agentId: string) {
  selectedAgentId.value = agentId;
  if (activeConversation.value === null) {
    draftRoute.value = {
      ...draftRoute.value,
      agentId,
    };
  }
}

function selectLlm(llmId: string | null) {
  selectedLlmId.value = llmId;
  if (activeConversation.value === null) {
    draftRoute.value = {
      ...draftRoute.value,
      llmId: llmId ?? undefined,
    };
  }
}

function toggleInspector() {
  inspectorOpen.value = !inspectorOpen.value;
}

function isCompactViewport() {
  return window.matchMedia("(max-width: 860px)").matches;
}

function syncPanelsForViewport() {
  if (isCompactViewport()) {
    deckOpen.value = false;
    inspectorOpen.value = false;
  }
}

function closeDeckIfCompact() {
  if (isCompactViewport()) {
    deckOpen.value = false;
  }
}

function toggleDeck() {
  deckOpen.value = !deckOpen.value;
}

async function hydrateConversationAfterTurn(bulkKey: string | null) {
  await refreshConversations();
  if (bulkKey) {
    await selectConversation(bulkKey);
  }
}

function watchTurn(runId: string) {
  closeTurnStream();
  streamState.value = "streaming";
  turnEventSource.value = openTurnEvents(runId, {
    pollIntervalSeconds: 0.35,
    timeoutSeconds: 90,
    onEvent: async (event, payload) => {
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

      const turnPayload =
        event === "snapshot"
          ? ({
              run: (payload as TurnSnapshotResponse).run,
              output_text: (payload as TurnSnapshotResponse).output_text,
            } satisfies TurnResponse)
          : (payload as TurnResponse);

      activeTurn.value = turnPayload;
      if (turnPayload.run.bulk_key) {
        activeBulkKey.value = turnPayload.run.bulk_key;
      }
      pushEvent(event, turnPayload);

      if (event === "snapshot") {
        mergeSnapshotMessages((payload as TurnSnapshotResponse).messages);
      }
      if (event === "completed" || event === "failed" || event === "cancelled") {
        busy.value = false;
        streamState.value = "closed";
        closeTurnStream();
        await hydrateConversationAfterTurn(turnPayload.run.bulk_key);
      }
      if (event === "timeout") {
        busy.value = false;
        streamState.value = "closed";
      }
    },
    onError: () => {
      streamState.value = "closed";
    },
  });
}

async function submitTurn() {
  if (!canSubmit.value) {
    return;
  }
  lastError.value = null;
  busy.value = true;

  const content = composer.value.trim();
  const route = activeRoute.value;
  const optimisticMessage = buildOptimisticUserMessage(content);
  const previousMessages = [...messages.value];
  messages.value = [...messages.value, optimisticMessage];
  composer.value = "";

  try {
    const payload = await createTurn({
      content,
      source: "web",
      ...routePayload(route),
    });
    activeTurn.value = payload;
    pushEvent("snapshot", payload);
    if (payload.run.bulk_key) {
      activeBulkKey.value = payload.run.bulk_key;
    }
    await refreshConversations();
    watchTurn(payload.run.id);
  } catch (error) {
    messages.value = previousMessages;
    busy.value = false;
    composer.value = content;
    lastError.value = error instanceof Error ? error.message : String(error);
  }
}

async function cancelActiveTurn() {
  if (!activeTurn.value || !busy.value) {
    return;
  }
  try {
    const payload = await cancelTurn(activeTurn.value.run.id, "user_cancelled");
    activeTurn.value = payload;
    pushEvent("cancelled", payload);
    busy.value = false;
    closeTurnStream();
    await hydrateConversationAfterTurn(payload.run.bulk_key);
  } catch (error) {
    lastError.value = error instanceof Error ? error.message : String(error);
  }
}

function formatTime(value: string | null) {
  if (!value) {
    return "pending";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

onMounted(async () => {
  syncPanelsForViewport();
  await refreshProfiles();
  await refreshConversations();
  if (conversations.value[0]) {
    await selectConversation(conversations.value[0].bulk_key);
  } else {
    draftRoute.value = createDraftRoute(selectedAgentId.value ?? defaultAgentId.value);
  }
});

onBeforeUnmount(() => {
  closeTurnStream();
});
</script>

<template>
  <div
    class="app-shell"
    :class="{
      'app-shell--deck-open': deckOpen,
      'app-shell--inspector-open': inspectorOpen,
    }"
  >
    <div class="app-shell__bg"></div>

    <div
      v-if="deckOpen"
      class="app-shell__scrim"
      @click="deckOpen = false"
    ></div>

    <ConversationSidebar
      :open="deckOpen"
      :conversations="conversations"
      :active-bulk-key="activeBulkKey"
      :loading="loadingConversations"
      @select="selectConversation"
      @fresh="createFreshConversation"
      @close="deckOpen = false"
    />

    <main class="workspace">
      <header class="topbar shell">
        <div class="topbar__group">
          <button class="ghost-button" type="button" @click="toggleDeck">
            <span class="button-glyph button-glyph--threads" aria-hidden="true"></span>
            <span class="sr-only">Threads</span>
          </button>
          <div class="topbar__title">
            <p class="eyebrow">crxzipple</p>
            <h1>{{ activeTitle }}</h1>
          </div>
        </div>
        <div class="topbar__actions">
          <button class="ghost-button" type="button" @click="toggleInspector">
            <span class="button-glyph button-glyph--inspect" aria-hidden="true"></span>
            <span class="sr-only">{{ inspectorOpen ? "Hide inspect" : "Inspect" }}</span>
          </button>
        </div>
      </header>

      <div class="workspace__body">
        <MessageTimeline
          :messages="messages"
          :turn-events="turnEvents"
          :active-turn="activeTurn"
          :conversation="activeConversation"
          :loading="loadingMessages"
          :last-error="lastError"
        />
      </div>

      <ComposerPanel
        v-model="composer"
        :busy="busy"
        :disabled="!canSubmit"
        :agents="agents"
        :llms="llms"
        :selected-agent-id="selectedAgentId"
        :selected-llm-id="selectedLlmId"
        @submit="submitTurn"
        @cancel="cancelActiveTurn"
        @select-agent="selectAgent"
        @select-llm="selectLlm"
      />
    </main>

    <TurnInspector
      :open="inspectorOpen"
      :active-turn="activeTurn"
      :turn-events="turnEvents"
      :payload="inspectorPayload"
      :output-preview="outputPreview"
      :last-error="lastError"
      :stream-state="streamState"
      :format-time="formatTime"
      @close="inspectorOpen = false"
    />
  </div>
</template>
