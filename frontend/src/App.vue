<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from "vue";

import ComposerPanel from "@/components/ComposerPanel.vue";
import ConversationSidebar from "@/components/ConversationSidebar.vue";
import MessageTimeline from "@/components/MessageTimeline.vue";
import { useAgentDirectory } from "@/composables/useAgentDirectory";
import { useAgentHomeEditor } from "@/composables/useAgentHomeEditor";
import { useConversationSession } from "@/composables/useConversationSession";
import { useMemoryPanel } from "@/composables/useMemoryPanel";
import { usePersistentUiState } from "@/composables/usePersistentUiState";
import { useRunPresentation } from "@/composables/useRunPresentation";
import { useTheme } from "@/composables/useTheme";
import { useTurnStream } from "@/composables/useTurnStream";

const TurnInspector = defineAsyncComponent(
  () => import("@/components/TurnInspector.vue"),
);
const MemoryDrawer = defineAsyncComponent(
  () => import("@/components/MemoryDrawer.vue"),
);
const AgentHomeDrawer = defineAsyncComponent(
  () => import("@/components/AgentHomeDrawer.vue"),
);

const defaultAgentId = ref("crxzipple");
const composer = ref("");
const { theme, toggleTitle, toggleTheme } = useTheme();
const {
  deckOpen,
  preferredRightPanel,
  activeRightPanel,
  setActiveRightPanel,
  agentPanelAgentId,
} = usePersistentUiState();
const selectedAgentId = ref<string | null>(defaultAgentId.value);
const selectedLlmId = ref<string | null>(null);

const {
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
  selectConversation,
  createFreshConversation,
  submitTurn,
  cancelActiveTurn,
  requestCompaction,
  requestMemoryFlush,
  resolveActiveApproval,
} = useConversationSession({
  defaultAgentId,
  selectedAgentId,
  selectedLlmId,
  refreshMemoryPanel: (agentId) => refreshMemoryPanel(agentId),
  refreshAgentHomeIfSafe,
  closeDeckIfCompact,
});

const inspectorOpen = computed(() => activeRightPanel.value === "inspect");
const memoryOpen = computed(() => activeRightPanel.value === "memory");
const agentHomeOpen = computed(() => activeRightPanel.value === "agent");

const currentMemoryAgentId = computed(
  () => activeRoute.value.agentId ?? selectedAgentId.value ?? defaultAgentId.value,
);
const {
  pendingMemoryCandidates,
  approvedMemoryEntries,
  memoryQuery,
  loadingMemory,
  currentThreadMemoryCandidates,
  otherMemoryCandidates,
  refreshMemoryPanel,
  approveMemoryCandidateById,
  rejectMemoryCandidateById,
} = useMemoryPanel({
  activeAgentId: currentMemoryAgentId,
  activeConversation,
  lastError,
});

const preferredAgentHomeId = computed(
  () => activeRoute.value.agentId ?? selectedAgentId.value ?? defaultAgentId.value,
);
const currentAgentHomeId = computed(
  () => agentPanelAgentId.value ?? preferredAgentHomeId.value,
);

const {
  loading: loadingAgentHome,
  saving: savingAgentHome,
  errorMessage: agentHomeError,
  snapshot: agentHomeSnapshot,
  selectedFileName: selectedAgentHomeFile,
  draftContent: activeAgentHomeDraftContent,
  dirtyFileNames: dirtyAgentHomeFileNames,
  currentFileDirty: currentAgentHomeFileDirty,
  hasDirtyChanges: hasDirtyAgentHomeChanges,
  refresh: refreshAgentHome,
  selectFile: selectAgentHomeFile,
  updateDraft: updateAgentHomeDraft,
  saveCurrentFile: saveAgentHomeFile,
} = useAgentHomeEditor({
  currentAgentId: currentAgentHomeId,
  initialFileName: "AGENT.md",
});

const {
  agents,
  llms,
  creatingAgent,
  updatingAgentStatusId,
  errorMessage: agentDirectoryError,
  enabledAgents,
  suggestedAgentHomeBaseDir,
  refreshProfiles,
  selectAgent,
  selectAgentHomeAgent,
  useAgentForNewChats,
  createAgentFromPanel,
  updateAgentEnabledState,
  selectLlm,
} = useAgentDirectory({
  defaultAgentId,
  selectedAgentId,
  selectedLlmId,
  draftRoute,
  activeConversation,
  agentPanelAgentId,
  currentAgentHomeId,
  agentHomeOpen,
  hasDirtyAgentHomeChanges,
  refreshMemoryPanel,
  refreshAgentHome,
  confirmDiscardAgentHomeChanges,
});

const {
  streamState,
  turnEvents,
  pushEvent,
  closeTurnStream,
  syncPendingApprovalFromTurn,
  clearTurnEvents,
  setStreamState,
  watchTurn,
} = useTurnStream({
  messages,
  activeTurn,
  pendingApproval,
  activeBulkKey,
  busy,
  activeConversation,
  draftMainKey: computed(() => draftRoute.value.mainKey),
  hydrateConversationAfterTurn,
  refreshConversations,
});

bindStream({
  pushEvent,
  closeTurnStream,
  syncPendingApprovalFromTurn,
  clearTurnEvents,
  setStreamState,
  watchTurn,
});

const {
  activeTitle,
  activeCompactionRequest,
  activeContextBudget,
  activeContextMeter,
  topbarStatusNote,
  activeRunFeedback,
  compactionRunning,
  memoryFlushRunning,
  canCompact,
  canMemoryFlush,
  canSubmit,
  inspectorPayload,
  outputPreview,
} = useRunPresentation({
  activeConversation,
  activeTurn,
  pendingApproval,
  turnEvents,
  streamState,
  busy,
  loadingMessages,
  currentRunId,
  activeRoute,
  composer,
});

const agentPanelError = computed(
  () => agentHomeError.value ?? agentDirectoryError.value,
);

async function refreshAgentHomeIfSafe(agentId?: string | null) {
  if (agentHomeOpen.value && !hasDirtyAgentHomeChanges.value) {
    await refreshAgentHome(agentId);
  }
}

async function startFreshConversation() {
  composer.value = "";
  await createFreshConversation();
}

function confirmDiscardAgentHomeChanges(reason: string) {
  if (!hasDirtyAgentHomeChanges.value) {
    return true;
  }
  const files = dirtyAgentHomeFileNames.value.join(", ");
  return window.confirm(
    `You have unsaved agent home changes in ${files}. ${reason}`,
  );
}

function toggleInspector() {
  if (activeRightPanel.value === "inspect") {
    setActiveRightPanel(null);
    return;
  }
  setActiveRightPanel("inspect");
}

function toggleMemory() {
  if (activeRightPanel.value === "memory") {
    setActiveRightPanel(null);
    return;
  }
  setActiveRightPanel("memory");
}

async function toggleAgentHome() {
  const nextPanel = activeRightPanel.value === "agent" ? null : "agent";
  if (nextPanel === null) {
    setActiveRightPanel(null);
  } else {
    setActiveRightPanel(nextPanel);
  }
  if (nextPanel === "agent") {
    if (!agentPanelAgentId.value) {
      agentPanelAgentId.value = preferredAgentHomeId.value;
    }
    if (!hasDirtyAgentHomeChanges.value) {
      await refreshAgentHome();
    }
  }
}

function isCompactViewport() {
  return window.matchMedia("(max-width: 860px)").matches;
}

async function reloadAgentHomeWithGuard() {
  if (
    !confirmDiscardAgentHomeChanges(
      "Reloading the home will discard unsaved edits.",
    )
  ) {
    return;
  }
  await refreshAgentHome();
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasDirtyAgentHomeChanges.value) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
}

function syncPanelsForViewport() {
  if (isCompactViewport()) {
    deckOpen.value = false;
    setActiveRightPanel(null, { persist: false });
    return;
  }
  if (activeRightPanel.value === null && preferredRightPanel.value !== null) {
    setActiveRightPanel(preferredRightPanel.value, { persist: false });
  }
}

function closeDeckIfCompact() {
  if (isCompactViewport()) {
    deckOpen.value = false;
  }
}

function closeRightPanel() {
  setActiveRightPanel(null);
}

function toggleDeck() {
  deckOpen.value = !deckOpen.value;
}

async function submitComposerTurn() {
  const submitted = await submitTurn(composer.value);
  if (submitted) {
    composer.value = "";
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
  window.addEventListener("beforeunload", handleBeforeUnload);
  window.addEventListener("resize", syncPanelsForViewport);
  syncPanelsForViewport();
  await refreshProfiles();
  await refreshConversations();
  if (conversations.value[0]) {
    await selectConversation(conversations.value[0].bulk_key);
  } else {
    await createFreshConversation();
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload);
  window.removeEventListener("resize", syncPanelsForViewport);
  closeTurnStream();
});
</script>

<template>
  <div
    class="app-shell"
    :class="{
      'app-shell--deck-open': deckOpen,
      'app-shell--inspector-open': inspectorOpen || memoryOpen || agentHomeOpen,
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
      @fresh="startFreshConversation"
      @close="deckOpen = false"
    />

    <main class="workspace">
      <header class="topbar shell">
        <div class="topbar__group">
          <button
            class="ghost-button"
            type="button"
            :title="deckOpen ? 'Close thread list' : 'Open thread list'"
            @click="toggleDeck"
          >
            <span class="button-glyph button-glyph--threads" aria-hidden="true"></span>
            <span class="sr-only">Threads</span>
          </button>
          <div class="topbar__title">
            <p class="eyebrow">crxzipple</p>
            <h1>{{ activeTitle }}</h1>
            <div v-if="topbarStatusNote" class="topbar__meta-row">
              <p v-if="topbarStatusNote" class="topbar__meta-note">
                {{ topbarStatusNote }}
              </p>
            </div>
          </div>
        </div>
        <div class="topbar__actions">
          <button
            class="ghost-button"
            type="button"
            :title="toggleTitle"
            @click="toggleTheme"
          >
            <span
              class="button-glyph"
              :class="theme === 'dark' ? 'button-glyph--theme-dark' : 'button-glyph--theme-light'"
              aria-hidden="true"
            ></span>
            <span class="sr-only">{{ toggleTitle }}</span>
          </button>
          <button
            class="ghost-button"
            type="button"
            :title="agentHomeOpen ? 'Close agent directory' : 'Open agent directory'"
            @click="toggleAgentHome"
          >
            <span class="button-glyph button-glyph--agent" aria-hidden="true"></span>
            <span class="sr-only">{{ agentHomeOpen ? "Hide agents" : "Agents" }}</span>
          </button>
          <button
            class="ghost-button"
            type="button"
            :title="memoryOpen ? 'Close memory panel' : 'Open memory panel'"
            @click="toggleMemory"
          >
            <span class="button-glyph button-glyph--memory" aria-hidden="true"></span>
            <span class="sr-only">{{ memoryOpen ? "Hide memory" : "Memory" }}</span>
          </button>
          <button
            class="ghost-button"
            type="button"
            :title="inspectorOpen ? 'Close inspector' : 'Open inspector'"
            @click="toggleInspector"
          >
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
          :compaction-request="activeCompactionRequest"
          :conversation="activeConversation"
          :loading="loadingMessages"
          :last-error="lastError"
          :run-feedback="activeRunFeedback"
        />
      </div>

      <ComposerPanel
        v-model="composer"
        :busy="busy"
        :disabled="!canSubmit"
        :can-compact="canCompact"
        :can-memory-flush="canMemoryFlush"
        :compaction-running="compactionRunning"
        :memory-flush-running="memoryFlushRunning"
        :agents="enabledAgents"
        :llms="llms"
        :selected-agent-id="selectedAgentId"
        :selected-llm-id="selectedLlmId"
        :pending-approval="pendingApproval"
        :pending-memory-candidate-count="pendingMemoryCandidates.length"
        :context-meter="activeContextMeter"
        :run-feedback="activeRunFeedback"
        @submit="submitComposerTurn"
        @cancel="cancelActiveTurn"
        @compact="requestCompaction"
        @memory-flush="requestMemoryFlush"
        @resolve-approval="resolveActiveApproval"
        @select-agent="selectAgent"
        @select-llm="selectLlm"
      />
    </main>

    <TurnInspector
      :open="inspectorOpen"
      :active-turn="activeTurn"
      :compaction-request="activeCompactionRequest"
      :turn-events="turnEvents"
      :payload="inspectorPayload"
      :output-preview="outputPreview"
      :last-error="lastError"
      :stream-state="streamState"
      :context-budget="activeContextBudget"
      :format-time="formatTime"
      @close="closeRightPanel"
    />

    <MemoryDrawer
      :open="memoryOpen"
      :loading="loadingMemory"
      :current-thread-memory-candidates="currentThreadMemoryCandidates"
      :other-memory-candidates="otherMemoryCandidates"
      :entries="approvedMemoryEntries"
      :query="memoryQuery"
      :format-time="formatTime"
      @approve-memory-candidate="approveMemoryCandidateById"
      @reject-memory-candidate="rejectMemoryCandidateById"
      @update:query="memoryQuery = $event"
      @refresh="refreshMemoryPanel"
      @close="closeRightPanel"
    />

    <AgentHomeDrawer
      :open="agentHomeOpen"
      :loading="loadingAgentHome"
      :saving="savingAgentHome"
      :creating="creatingAgent"
      :updating-agent-status-id="updatingAgentStatusId"
      :agents="agents"
      :llms="llms"
      :selected-agent-id="currentAgentHomeId"
      :draft-agent-id="selectedAgentId"
      :conversation-agent-id="activeConversation?.runtime_binding.agent_id ?? null"
      :suggested-home-base-dir="suggestedAgentHomeBaseDir"
      :snapshot="agentHomeSnapshot"
      :selected-file-name="selectedAgentHomeFile"
      :draft-content="activeAgentHomeDraftContent"
      :dirty-file-count="dirtyAgentHomeFileNames.length"
      :dirty-file-names="dirtyAgentHomeFileNames"
      :current-file-dirty="currentAgentHomeFileDirty"
      :error-message="agentPanelError"
      @close="closeRightPanel"
      @select-agent="selectAgentHomeAgent"
      @use-agent="useAgentForNewChats"
      @enable-agent="updateAgentEnabledState($event, true)"
      @disable-agent="updateAgentEnabledState($event, false)"
      @create-agent="createAgentFromPanel"
      @select-file="selectAgentHomeFile"
      @update:draft-content="updateAgentHomeDraft"
      @reload="reloadAgentHomeWithGuard()"
      @save="saveAgentHomeFile"
    />
  </div>
</template>
