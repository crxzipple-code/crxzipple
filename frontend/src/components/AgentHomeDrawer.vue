<script setup lang="ts">
import { computed, ref, watch } from "vue";

import type { AgentHomeSnapshot, AgentProfileSummary, LlmProfileSummary } from "@/types";

const props = defineProps<{
  open: boolean;
  loading: boolean;
  saving: boolean;
  creating: boolean;
  updatingAgentStatusId: string | null;
  agents: AgentProfileSummary[];
  llms: LlmProfileSummary[];
  selectedAgentId: string | null;
  draftAgentId: string | null;
  conversationAgentId: string | null;
  suggestedHomeBaseDir: string | null;
  snapshot: AgentHomeSnapshot | null;
  selectedFileName: string | null;
  draftContent: string;
  dirtyFileCount: number;
  dirtyFileNames: string[];
  currentFileDirty: boolean;
  errorMessage: string | null;
}>();

const emit = defineEmits<{
  close: [];
  selectAgent: [agentId: string];
  useAgent: [agentId: string];
  enableAgent: [agentId: string];
  disableAgent: [agentId: string];
  createAgent: [payload: {
    id: string;
    name: string;
    description: string;
    defaultLlmId: string;
    homeDir: string | null;
    workdir: string | null;
    systemPrompt: string;
  }];
  selectFile: [fileName: string];
  "update:draftContent": [value: string];
  reload: [];
  save: [];
}>();

const activeFile = computed(
  () => props.snapshot?.files.find((item) => item.name === props.selectedFileName) ?? null,
);

const agentJsonFile = computed(
  () => props.snapshot?.files.find((item) => item.name === "agent.json") ?? null,
);

const selectedAgent = computed(
  () => props.agents.find((item) => item.id === props.selectedAgentId) ?? null,
);

const createMode = ref(false);
const editorMode = ref(false);
const selectedAgentExpanded = ref(false);
const editorView = ref<"basic" | "files">("basic");
const createId = ref("");
const createName = ref("");
const createDescription = ref("");
const createDefaultLlmId = ref("");
const createHomeDir = ref("");
const createWorkdir = ref("");
const createSystemPrompt = ref("You are a concise helpful assistant.");
const basicErrorMessage = ref<string | null>(null);
const basicDraft = ref({
  name: "",
  description: "",
  displayName: "",
  defaultLlmId: "",
  workdir: "",
  systemPrompt: "",
});

const saveLabel = computed(() => {
  if (props.saving) {
    return "Saving...";
  }
  if (props.currentFileDirty) {
    return "Save file";
  }
  return "Saved";
});

const basicEditorReady = computed(
  () => editorView.value === "basic" && props.selectedFileName === "agent.json",
);

const homeFilesSummary = computed(() => {
  const files = props.snapshot?.files.filter((file) => file.exists) ?? [];
  if (!files.length) {
    return "No editable home files yet";
  }
  const names = new Set(files.map((file) => file.name));
  const parts: string[] = [];
  if (names.has("agent.json")) {
    parts.push("config");
  }
  if (names.has("AGENT.md") || names.has("SOUL.md")) {
    parts.push("persona");
  }
  if (names.has("USER.md") || names.has("IDENTITY.md")) {
    parts.push("identity");
  }
  if (names.has("MEMORY.md")) {
    parts.push("memory");
  }
  const detail = parts.length ? ` · ${parts.join(" + ")}` : "";
  return `${files.length} file${files.length === 1 ? "" : "s"}${detail}`;
});

function shortPath(path: string | null) {
  if (!path) {
    return "Not set";
  }
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 4) {
    return path;
  }
  return `.../${parts.slice(-4).join("/")}`;
}

function isProtectedAgent(agentId: string) {
  return agentId === props.draftAgentId || agentId === props.conversationAgentId;
}

function agentStatusHint(agent: AgentProfileSummary) {
  if (agent.id === props.conversationAgentId) {
    return "This agent is bound to the current thread.";
  }
  if (agent.id === props.draftAgentId) {
    return "This agent is selected for new chats.";
  }
  return "Disabled agents stay editable here, but they disappear from the composer.";
}

function slugifyAgentId(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

function suggestHomeDir(agentId: string) {
  const slug = slugifyAgentId(agentId);
  if (!slug || !props.suggestedHomeBaseDir) {
    return "";
  }
  return `${props.suggestedHomeBaseDir}/${slug}`;
}

function openCreateMode() {
  createMode.value = true;
  createId.value = "";
  createName.value = "";
  createDescription.value = "";
  createDefaultLlmId.value =
    props.llms[0]?.id ??
    selectedAgent.value?.llm_routing_policy.default_llm_id ??
    "";
  createHomeDir.value = "";
  createWorkdir.value = selectedAgent.value?.runtime_preferences.workdir ?? "";
  createSystemPrompt.value =
    selectedAgent.value?.name
      ? `You are ${selectedAgent.value.name}, a concise helpful assistant.`
      : "You are a concise helpful assistant.";
}

function closeForms() {
  createMode.value = false;
}

function openEditorMode(fileName?: string) {
  if (fileName) {
    editorView.value = "files";
    emit("selectFile", fileName);
  } else {
    editorView.value = "basic";
    if (agentJsonFile.value) {
      emit("selectFile", "agent.json");
    } else if (!props.selectedFileName && props.snapshot?.files.length) {
      emit("selectFile", props.snapshot.files[0].name);
    }
  }
  editorMode.value = true;
}

function closeEditorMode() {
  editorMode.value = false;
}

function ensureObject(value: unknown) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function syncBasicDraftFromJson(content: string) {
  try {
    const parsed = ensureObject(JSON.parse(content));
    const identity = ensureObject(parsed.identity);
    const llmRoutingPolicy = ensureObject(parsed.llm_routing_policy);
    const runtimePreferences = ensureObject(parsed.runtime_preferences);
    const instructionPolicy = ensureObject(parsed.instruction_policy);
    basicDraft.value = {
      name: typeof parsed.name === "string" ? parsed.name : "",
      description: typeof parsed.description === "string" ? parsed.description : "",
      displayName:
        typeof identity.display_name === "string" ? identity.display_name : "",
      defaultLlmId:
        typeof llmRoutingPolicy.default_llm_id === "string"
          ? llmRoutingPolicy.default_llm_id
          : "",
      workdir:
        typeof runtimePreferences.workdir === "string"
          ? runtimePreferences.workdir
          : "",
      systemPrompt:
        typeof instructionPolicy.system_prompt === "string"
          ? instructionPolicy.system_prompt
          : "You are a concise helpful assistant.",
    };
    basicErrorMessage.value = null;
    return true;
  } catch {
    basicErrorMessage.value =
      "Basic form is unavailable until agent.json parses again. Switch to Files to repair the raw JSON.";
    return false;
  }
}

function openBasicEditor() {
  editorView.value = "basic";
  if (agentJsonFile.value && props.selectedFileName !== "agent.json") {
    emit("selectFile", "agent.json");
  } else if (agentJsonFile.value) {
    syncBasicDraftFromJson(props.draftContent || agentJsonFile.value.content);
  }
}

function writeBasicDraftToJson(nextDraft: typeof basicDraft.value) {
  if (!basicEditorReady.value || !agentJsonFile.value) {
    return;
  }
  try {
    const parsed = ensureObject(JSON.parse(props.draftContent || agentJsonFile.value.content));
    const identity = ensureObject(parsed.identity);
    const llmRoutingPolicy = ensureObject(parsed.llm_routing_policy);
    const runtimePreferences = ensureObject(parsed.runtime_preferences);
    const instructionPolicy = ensureObject(parsed.instruction_policy);

    parsed.name = nextDraft.name.trim() || (typeof parsed.id === "string" ? parsed.id : "");
    parsed.description = nextDraft.description.trim();
    parsed.identity = identity;
    parsed.llm_routing_policy = llmRoutingPolicy;
    parsed.runtime_preferences = runtimePreferences;
    parsed.instruction_policy = instructionPolicy;

    identity.display_name = nextDraft.displayName.trim() || null;
    llmRoutingPolicy.default_llm_id = nextDraft.defaultLlmId.trim();
    runtimePreferences.workdir = nextDraft.workdir.trim() || null;
    instructionPolicy.system_prompt =
      nextDraft.systemPrompt.trim() || "You are a concise helpful assistant.";

    basicDraft.value = nextDraft;
    basicErrorMessage.value = null;
    emit("update:draftContent", `${JSON.stringify(parsed, null, 2)}\n`);
  } catch {
    basicErrorMessage.value =
      "Basic form is unavailable until agent.json parses again. Switch to Files to repair the raw JSON.";
  }
}

function updateBasicField(
  field: keyof typeof basicDraft.value,
  value: string,
) {
  if (!basicEditorReady.value) {
    return;
  }
  writeBasicDraftToJson({
    ...basicDraft.value,
    [field]: value,
  });
}

function submitCreate() {
  const fallbackId = slugifyAgentId(createId.value || createName.value);
  emit("createAgent", {
    id: fallbackId,
    name: createName.value.trim() || fallbackId,
    description: createDescription.value.trim(),
    defaultLlmId: createDefaultLlmId.value,
    homeDir: createHomeDir.value.trim() || suggestHomeDir(fallbackId) || null,
    workdir: createWorkdir.value.trim() || null,
    systemPrompt: createSystemPrompt.value.trim() || "You are a concise helpful assistant.",
  });
}

watch(createName, (value) => {
  if (!createId.value.trim()) {
    createId.value = slugifyAgentId(value);
  }
});

watch(createId, (value) => {
  if (!createHomeDir.value.trim()) {
    createHomeDir.value = suggestHomeDir(value);
  }
});

watch(
  () => props.open,
  (value) => {
    if (!value) {
      closeForms();
      closeEditorMode();
    }
  },
);

watch(
  () => props.selectedAgentId,
  () => {
    selectedAgentExpanded.value = false;
  },
);

watch(
  () =>
    [
      editorMode.value,
      editorView.value,
      props.selectedFileName,
      props.draftContent,
      props.snapshot,
    ] as const,
  () => {
    if (!editorMode.value || editorView.value !== "basic") {
      return;
    }
    if (!agentJsonFile.value) {
      basicErrorMessage.value = "This agent home does not contain an agent.json file.";
      return;
    }
    if (props.selectedFileName !== "agent.json") {
      emit("selectFile", "agent.json");
      return;
    }
    syncBasicDraftFromJson(props.draftContent || agentJsonFile.value.content);
  },
  { immediate: true },
);
</script>

<template>
  <aside class="agent-drawer" :class="{ 'agent-drawer--open': open }">
    <div class="agent-panel shell">
      <div class="agent-panel__header">
        <div>
          <p class="eyebrow">agent directory</p>
          <h3>{{ selectedAgent?.name ?? snapshot?.agent_name ?? selectedAgentId ?? "Agent" }}</h3>
        </div>
        <button
          class="ghost-button"
          type="button"
          title="Close agent directory"
          @click="$emit('close')"
        >
          <span class="button-glyph button-glyph--collapse" aria-hidden="true"></span>
          <span class="sr-only">Collapse</span>
        </button>
      </div>

      <div v-if="errorMessage" class="agent-panel__error">
        <strong>agent home error</strong>
        <p>{{ errorMessage }}</p>
      </div>

      <div class="agent-panel__stack">
        <section class="agent-panel__section">
          <div class="agent-panel__section-head agent-panel__section-head--split">
            <div>
              <p class="eyebrow">directory</p>
              <strong>{{ agents.length }} configured</strong>
            </div>
            <p class="agent-panel__directory-note">
              Pick an agent from the list. The active card expands with home details and editing actions without leaving the directory view.
            </p>
          </div>

          <div class="agent-panel__directory-actions">
            <button
              class="primary-button agent-action-button"
              type="button"
              title="Create new agent"
              @click="openCreateMode"
            >
              <span class="button-glyph button-glyph--new" aria-hidden="true"></span>
              New agent
            </button>
          </div>

          <div class="agent-panel__catalog">
            <article
              v-for="agent in agents"
              :key="agent.id"
              class="agent-card"
              :class="{ 'agent-card--active': agent.id === selectedAgentId }"
              tabindex="0"
              role="button"
              @click="$emit('selectAgent', agent.id)"
              @keydown.enter.prevent="$emit('selectAgent', agent.id)"
              @keydown.space.prevent="$emit('selectAgent', agent.id)"
            >
              <div class="agent-card__topline">
                <div>
                  <strong>{{ agent.name || agent.id }}</strong>
                  <span>{{ agent.id }}</span>
                </div>
                <div class="agent-card__badges">
                  <span
                    v-if="agent.id === selectedAgentId"
                    class="agent-card__badge agent-card__badge--active"
                  >
                    Editing
                  </span>
                  <span
                    v-if="agent.id === selectedAgentId && dirtyFileCount > 0"
                    class="agent-card__badge agent-card__badge--dirty"
                  >
                    {{ dirtyFileCount }} unsaved
                  </span>
                  <span
                    v-if="agent.id === draftAgentId"
                    class="agent-card__badge"
                  >
                    New chats
                  </span>
                  <span
                    v-if="!agent.enabled"
                    class="agent-card__badge agent-card__badge--disabled"
                  >
                    Disabled
                  </span>
                  <span
                    v-if="conversationAgentId && agent.id === conversationAgentId"
                    class="agent-card__badge"
                  >
                    Current thread
                  </span>
                </div>
              </div>

              <p v-if="agent.description" class="agent-card__description">
                {{ agent.description }}
              </p>

              <div class="agent-card__meta">
                <span>LLM · {{ agent.llm_routing_policy.default_llm_id }}</span>
                <span v-if="agent.runtime_preferences.home_dir">
                  Home · {{ shortPath(agent.runtime_preferences.home_dir) }}
                </span>
                <span v-if="agent.runtime_preferences.workdir">
                  Workdir · {{ shortPath(agent.runtime_preferences.workdir) }}
                </span>
              </div>

              <p
                v-if="agent.id === selectedAgentId && dirtyFileCount > 0"
                class="agent-card__dirty-note"
              >
                Unsaved: {{ dirtyFileNames.join(", ") }}
              </p>

              <div
                v-if="agent.id === selectedAgentId"
                class="agent-card__disclosure"
              >
                <div class="agent-card__disclosure-main">
                  <button
                    v-if="snapshot"
                    class="primary-button primary-button--compact agent-action-button"
                    type="button"
                    title="Edit selected agent"
                    @click.stop="openEditorMode()"
                  >
                    <span class="button-glyph button-glyph--edit" aria-hidden="true"></span>
                    Edit agent
                  </button>
                </div>
                <button
                  class="ghost-button ghost-button--compact agent-action-button agent-card__disclosure-toggle"
                  type="button"
                  :title="selectedAgentExpanded ? 'Hide agent details' : 'Show agent details'"
                  @click.stop="selectedAgentExpanded = !selectedAgentExpanded"
                >
                  <span>{{ selectedAgentExpanded ? "Hide details" : "Expand details" }}</span>
                  <span
                    class="agent-card__disclosure-chevron"
                    :class="{ 'agent-card__disclosure-chevron--expanded': selectedAgentExpanded }"
                    aria-hidden="true"
                  >
                    ▾
                  </span>
                </button>
              </div>

              <div
                v-if="agent.id === selectedAgentId && selectedAgentExpanded"
                class="agent-card__expanded"
              >
                <div class="agent-panel__focus-profile">
                  <span
                    v-if="agent.identity.display_name?.trim() && agent.identity.display_name !== agent.name"
                  >
                    {{ agent.identity.display_name }}
                  </span>
                  <code>{{ agent.id }}</code>
                </div>

                <div v-if="loading" class="agent-card__expanded-note">
                  Loading agent home...
                </div>
                <div v-else-if="snapshot" class="agent-panel__focus-grid">
                  <div class="agent-panel__focus-item">
                    <span>Home</span>
                    <strong>{{ snapshot.home_dir }}</strong>
                  </div>
                  <div class="agent-panel__focus-item">
                    <span>Workdir</span>
                    <strong>{{ snapshot.workdir ?? "n/a" }}</strong>
                  </div>
                  <div class="agent-panel__focus-item">
                    <span>Dirty</span>
                    <strong>
                      {{
                        dirtyFileCount > 0
                          ? `${dirtyFileCount} file${dirtyFileCount === 1 ? "" : "s"} changed`
                          : "No unsaved edits"
                      }}
                    </strong>
                  </div>
                  <div class="agent-panel__focus-item">
                    <span>Model</span>
                    <strong>{{ agent.llm_routing_policy.default_llm_id }}</strong>
                  </div>
                  <div class="agent-panel__focus-item">
                    <span>Home contents</span>
                    <strong>{{ homeFilesSummary }}</strong>
                  </div>
                </div>

                <div class="agent-panel__focus-actions">
                  <button
                    v-if="snapshot"
                    class="ghost-button ghost-button--compact agent-action-button"
                    type="button"
                    :disabled="loading"
                    title="Reload agent home"
                    @click.stop="$emit('reload')"
                  >
                    <span class="button-glyph button-glyph--reload" aria-hidden="true"></span>
                    Reload home
                  </button>
                  <button
                    class="ghost-button ghost-button--compact agent-action-button"
                    type="button"
                    :disabled="agent.id === draftAgentId || !agent.enabled"
                    :title="
                      agent.id === draftAgentId
                        ? 'Already set as the new-chat default'
                        : 'Set as new-chat default'
                    "
                    @click.stop="$emit('useAgent', agent.id)"
                  >
                    <span class="button-glyph button-glyph--agent" aria-hidden="true"></span>
                    {{ agent.id === draftAgentId ? "Selected for new chats" : "Use for new chats" }}
                  </button>
                  <button
                    class="ghost-button ghost-button--compact agent-action-button"
                    type="button"
                    :disabled="
                      updatingAgentStatusId === agent.id ||
                      (!agent.enabled && isProtectedAgent(agent.id))
                    "
                    :title="
                      agent.enabled
                        ? 'Disable agent'
                        : 'Enable agent'
                    "
                    @click.stop="
                      agent.enabled
                        ? $emit('disableAgent', agent.id)
                        : $emit('enableAgent', agent.id)
                    "
                  >
                    <span
                      class="button-glyph"
                      :class="agent.enabled ? 'button-glyph--cancel' : 'button-glyph--new'"
                      aria-hidden="true"
                    ></span>
                    {{
                      updatingAgentStatusId === agent.id
                        ? (agent.enabled ? 'Disabling...' : 'Enabling...')
                        : agent.enabled
                          ? 'Disable agent'
                          : 'Enable agent'
                    }}
                  </button>
                </div>
              </div>

              <div
                v-else-if="agent.id !== draftAgentId && agent.enabled"
                class="agent-card__footer"
              >
                <button
                  class="agent-card__link-action"
                  type="button"
                  @click.stop="$emit('useAgent', agent.id)"
                >
                  Set as new-chat default
                </button>
              </div>

              <p v-if="!agent.enabled || isProtectedAgent(agent.id)" class="agent-card__hint">
                {{ agentStatusHint(agent) }}
              </p>
            </article>
          </div>
        </section>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="createMode"
        class="agent-modal-backdrop"
        @click.self="closeForms"
      >
        <section
          class="agent-modal shell"
          role="dialog"
          aria-modal="true"
          aria-label="Create agent"
        >
          <div class="agent-panel__form-head">
            <div>
              <p class="eyebrow">create agent</p>
              <strong>New file-backed agent</strong>
            </div>
          </div>
          <div class="agent-panel__form-grid">
            <label class="agent-panel__field">
              <span>Name</span>
              <input v-model="createName" class="agent-panel__field-input" type="text" />
            </label>
            <label class="agent-panel__field">
              <span>Agent id</span>
              <input v-model="createId" class="agent-panel__field-input" type="text" />
            </label>
            <label class="agent-panel__field">
              <span>Default model</span>
              <select v-model="createDefaultLlmId" class="agent-panel__field-input">
                <option v-for="llm in llms" :key="llm.id" :value="llm.id">
                  {{ llm.id }}
                </option>
              </select>
            </label>
            <label class="agent-panel__field">
              <span>Home dir</span>
              <input v-model="createHomeDir" class="agent-panel__field-input" type="text" />
            </label>
            <label class="agent-panel__field agent-panel__field--wide">
              <span>Workdir</span>
              <input v-model="createWorkdir" class="agent-panel__field-input" type="text" />
            </label>
            <label class="agent-panel__field agent-panel__field--wide">
              <span>Description</span>
              <input v-model="createDescription" class="agent-panel__field-input" type="text" />
            </label>
            <label class="agent-panel__field agent-panel__field--wide">
              <span>System prompt</span>
              <textarea
                v-model="createSystemPrompt"
                class="agent-panel__field-input agent-panel__field-input--textarea"
              ></textarea>
            </label>
          </div>
          <div class="agent-panel__form-actions">
            <button class="ghost-button" type="button" @click="closeForms">
              Cancel
            </button>
            <button
              class="primary-button"
              type="button"
              :disabled="creating || !createName.trim() || !createDefaultLlmId"
              @click="submitCreate"
            >
              {{ creating ? "Creating..." : "Create agent" }}
            </button>
          </div>
        </section>
      </div>

      <div
        v-if="editorMode && snapshot"
        class="agent-modal-backdrop"
        @click.self="closeEditorMode"
      >
        <section
          class="agent-modal agent-modal--wide shell"
          role="dialog"
          aria-modal="true"
          aria-label="Edit agent home"
        >
          <div class="agent-panel__form-head">
            <div>
              <p class="eyebrow">edit agent home</p>
              <strong>{{ snapshot.agent_name }}</strong>
            </div>
            <button
              class="ghost-button agent-toolbar-button agent-toolbar-button--close"
              type="button"
              title="Close agent editor"
              @click="closeEditorMode"
            >
              <span class="button-glyph button-glyph--cancel" aria-hidden="true"></span>
              <span class="sr-only">Close</span>
            </button>
          </div>

          <div class="agent-panel__toolbar">
            <button
              class="ghost-button ghost-button--compact agent-toolbar-button agent-toolbar-button--compact"
              type="button"
              :disabled="loading"
              title="Reload current file"
              @click="$emit('reload')"
            >
              <span class="button-glyph button-glyph--reload" aria-hidden="true"></span>
              Reload
            </button>
            <button
              class="primary-button primary-button--compact agent-toolbar-button agent-toolbar-button--compact"
              type="button"
              :disabled="saving || !currentFileDirty"
              :title="currentFileDirty ? 'Save current file' : 'Current file saved'"
              @click="$emit('save')"
            >
              <span class="button-glyph button-glyph--save" aria-hidden="true"></span>
              {{ saveLabel }}
            </button>
          </div>

          <div class="agent-editor-tabs">
            <button
              class="agent-editor-tab"
              :class="{ 'agent-editor-tab--active': editorView === 'basic' }"
              type="button"
              title="Open Basic tab"
              @click="openBasicEditor"
            >
              <span class="button-glyph button-glyph--basic" aria-hidden="true"></span>
              Basic
            </button>
            <button
              class="agent-editor-tab"
              :class="{ 'agent-editor-tab--active': editorView === 'files' }"
              type="button"
              title="Open Files tab"
              @click="editorView = 'files'"
            >
              <span class="button-glyph button-glyph--files" aria-hidden="true"></span>
              Files
            </button>
          </div>

          <div
            v-if="editorView === 'basic'"
            class="agent-panel__editor"
          >
            <div class="agent-panel__file-meta">
              <div>
                <strong>Basic config</strong>
                <span>{{ snapshot.home_dir }}/agent.json</span>
              </div>
              <p>
                Use the friendly fields for common profile edits. Advanced sections stay available in
                <strong>Files</strong>, where you can still edit the raw <code>agent.json</code>.
              </p>
            </div>
            <div v-if="basicErrorMessage" class="agent-panel__basic-warning">
              <strong>Basic editor unavailable</strong>
              <p>{{ basicErrorMessage }}</p>
            </div>
            <div
              v-else-if="basicEditorReady"
              class="agent-panel__basic"
            >
              <div class="agent-panel__form-grid">
                <label class="agent-panel__field">
                  <span>Name</span>
                  <input
                    :value="basicDraft.name"
                    class="agent-panel__field-input"
                    type="text"
                    @input="
                      updateBasicField(
                        'name',
                        ($event.target as HTMLInputElement).value,
                      )
                    "
                  />
                </label>
                <label class="agent-panel__field">
                  <span>Display name</span>
                  <input
                    :value="basicDraft.displayName"
                    class="agent-panel__field-input"
                    type="text"
                    @input="
                      updateBasicField(
                        'displayName',
                        ($event.target as HTMLInputElement).value,
                      )
                    "
                  />
                </label>
                <label class="agent-panel__field agent-panel__field--wide">
                  <span>Description</span>
                  <input
                    :value="basicDraft.description"
                    class="agent-panel__field-input"
                    type="text"
                    @input="
                      updateBasicField(
                        'description',
                        ($event.target as HTMLInputElement).value,
                      )
                    "
                  />
                </label>
                <label class="agent-panel__field">
                  <span>Default model</span>
                  <select
                    :value="basicDraft.defaultLlmId"
                    class="agent-panel__field-input"
                    @change="
                      updateBasicField(
                        'defaultLlmId',
                        ($event.target as HTMLSelectElement).value,
                      )
                    "
                  >
                    <option v-for="llm in llms" :key="llm.id" :value="llm.id">
                      {{ llm.id }}
                    </option>
                  </select>
                </label>
                <label class="agent-panel__field">
                  <span>Workdir</span>
                  <input
                    :value="basicDraft.workdir"
                    class="agent-panel__field-input"
                    type="text"
                    @input="
                      updateBasicField(
                        'workdir',
                        ($event.target as HTMLInputElement).value,
                      )
                    "
                  />
                </label>
                <label class="agent-panel__field agent-panel__field--wide">
                  <span>Home dir</span>
                  <input
                    :value="snapshot.home_dir"
                    class="agent-panel__field-input agent-panel__field-input--readonly"
                    type="text"
                    readonly
                  />
                </label>
                <label class="agent-panel__field agent-panel__field--wide">
                  <span>System prompt</span>
                  <textarea
                    :value="basicDraft.systemPrompt"
                    class="agent-panel__field-input agent-panel__field-input--textarea"
                    @input="
                      updateBasicField(
                        'systemPrompt',
                        ($event.target as HTMLTextAreaElement).value,
                      )
                    "
                  ></textarea>
                </label>
              </div>
              <p class="agent-panel__basic-note">
                Save writes your current changes back to <code>agent.json</code>.
              </p>
            </div>
          </div>

          <template v-else>
            <div class="agent-panel__tabs">
              <button
                v-for="file in snapshot.files"
                :key="file.name"
                class="agent-panel__tab"
                :class="{
                  'agent-panel__tab--active': file.name === selectedFileName,
                }"
                type="button"
                @click="$emit('selectFile', file.name)"
              >
                <span>{{ file.name }}</span>
                <small>{{ file.language }}</small>
              </button>
            </div>

            <div v-if="activeFile" class="agent-panel__editor">
              <div class="agent-panel__file-meta">
                <div>
                  <strong>{{ activeFile.name }}</strong>
                  <span>{{ activeFile.path }}</span>
                </div>
                <p>
                  {{
                    activeFile.name === "agent.json"
                      ? "Edit structured config here directly when you want full control over the raw JSON."
                      : "Markdown changes save straight to disk and will shape later turns for this agent."
                  }}
                </p>
              </div>
              <textarea
                class="agent-panel__input"
                :value="draftContent"
                spellcheck="false"
                @input="
                  $emit(
                    'update:draftContent',
                    ($event.target as HTMLTextAreaElement).value,
                  )
                "
              ></textarea>
            </div>
          </template>
        </section>
      </div>
    </Teleport>
  </aside>
</template>
