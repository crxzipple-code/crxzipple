<script setup lang="ts">
import { ArrowRight, Copy, GitBranch, MessageCircle, Plus, Power, RefreshCcw, Save, Trash2 } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import DataTable from "@/shared/ui/DataTable.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  listSettingsResources,
} from "../api";
import {
  deleteChannelProfile,
  getChannelProfile,
  listChannelProfiles,
  setChannelProfileEnabled,
  upsertChannelProfile,
  type ChannelProfileApiPayload,
  type ChannelProfileWritePayload,
} from "../ownerApis/channelProfiles";

type JsonRecord = Record<string, unknown>;
type TableRow = Record<string, string | number | null>;

interface SettingsResourceSummaryPayload {
  id?: string;
  resource_id?: string;
  title?: string;
  display_name?: string;
  status?: string;
  enabled?: boolean;
  source?: string | null;
  version?: string | number | null;
  updated_at?: string | null;
  metadata?: JsonRecord;
  payload?: JsonRecord;
  effective_config?: JsonRecord;
  resolution?: {
    value?: unknown;
    source?: { kind?: string; name?: string };
    sources?: Array<{ kind?: string; name?: string; version_id?: string | null }>;
    override_trace?: unknown[];
  };
}

interface SettingsResourceDetailPayload extends SettingsResourceSummaryPayload {
  title?: string;
  payload?: JsonRecord;
  versions?: JsonRecord[];
  validation?: { status?: string; checks?: { rows?: JsonRecord[] } };
  audit?: { recent_changes?: { rows?: JsonRecord[]; total?: number } };
}

interface SettingsResourcePagePayload {
  title?: string;
  description?: string;
  status?: string;
  resources?: SettingsResourceSummaryPayload[];
  list?: { total?: number };
  detail?: SettingsResourceDetailPayload | null;
}

const settingsPage = ref<SettingsResourcePagePayload | null>(null);
const selectedDetail = ref<SettingsResourceDetailPayload | null>(null);
const selectedResourceId = ref<string | null>(null);
const isLoading = ref(false);
const detailLoading = ref(false);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const ownerActionError = ref<string | null>(null);
const ownerActionMessage = ref<string | null>(null);
const ownerActionLoading = ref(false);
const editMode = ref<"create" | "update">("update");
const editorText = ref("");

const resources = computed(() => settingsPage.value?.resources ?? []);
const selectedResource = computed(() =>
  resources.value.find((resource) => settingsResourceId(resource) === selectedResourceId.value)
  ?? resources.value[0]
  ?? null,
);
const activeDetail = computed(() => selectedDetail.value ?? selectedResource.value);
const selectedConfig = computed(() => activeDetail.value ? resourceConfig(activeDetail.value) : {});
const channelRows = computed<TableRow[]>(() =>
  resources.value.map((resource) => {
    const config = resourceConfig(resource);
    return {
      Name: textValue(resource.display_name, settingsResourceId(resource)),
      "Channel ID": settingsResourceId(resource),
      Type: textValue(config.channel_kind, textValue(config.channel_type, "-")),
      Status: resource.enabled === false ? "disabled" : textValue(resource.status, "ready"),
      Source: textValue(resource.source, resource.resolution?.source?.name ?? "settings_application"),
      Version: textValue(resource.version, "-"),
      "Updated At": formatTime(resource.updated_at),
    };
  }),
);
const effectiveRows = computed<TableRow[]>(() =>
  Object.entries(selectedConfig.value).slice(0, 14).map(([key, value]) => ({
    Key: key,
    Value: formatValue(value),
  })),
);
const resolutionRows = computed<TableRow[]>(() =>
  (activeDetail.value?.resolution?.sources ?? []).map((source, index) => ({
    Layer: index === 0 ? "primary" : "source",
    Source: textValue(source.name, textValue(source.kind, "settings")),
    Version: textValue(source.version_id, "-"),
  })),
);
const totalResources = computed(() => settingsPage.value?.list?.total ?? resources.value.length);
const selectedChannelType = computed(() => selectedResourceId.value ?? textValue(activeDetail.value?.resource_id));
const canWriteOwnerProfile = computed(() => !ownerActionLoading.value && editorText.value.trim().length > 0);
const ownerFormTitle = computed(() => editMode.value === "create" ? "Create Channel Profile" : "Update Channel Profile");

onMounted(() => {
  void loadChannelProfiles();
});

async function loadChannelProfiles(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [profiles, overlay] = await Promise.all([
      listChannelProfiles(),
      loadSettingsOverlay(),
    ]);
    const payload = buildChannelProfilePage(profiles, overlay);
    settingsPage.value = payload;
    const first = profiles[0] ?? null;
    selectedResourceId.value = first ? first.channel_type : null;
    selectedDetail.value = first ? channelProfileToDetail(first) : null;
    if (selectedDetail.value) {
      resetEditorFromDetail(selectedDetail.value);
    } else {
      beginCreateProfile();
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    settingsPage.value = null;
    selectedDetail.value = null;
  } finally {
    isLoading.value = false;
  }
}

async function selectResource(resource: SettingsResourceSummaryPayload): Promise<void> {
  const resourceId = settingsResourceId(resource);
  selectedResourceId.value = resourceId;
  detailLoading.value = true;
  detailError.value = null;
  try {
    selectedDetail.value = channelProfileToDetail(await getChannelProfile(resourceId));
    editMode.value = "update";
    resetEditorFromDetail(selectedDetail.value);
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

function selectChannelRow(row: unknown): void {
  const channelId = textValue(tableCellValue(row, "Channel ID"), "");
  const resource = resources.value.find((item) => settingsResourceId(item) === channelId);
  if (resource) void selectResource(resource);
}

async function handleOwnerActionCompleted(resourceId = selectedResourceId.value): Promise<void> {
  if (!resourceId) {
    await loadChannelProfiles();
    return;
  }
  await loadChannelProfiles();
  selectedResourceId.value = resourceId;
  try {
    selectedDetail.value = channelProfileToDetail(await getChannelProfile(resourceId));
    resetEditorFromDetail(selectedDetail.value);
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  }
}

function beginCreateProfile(): void {
  editMode.value = "create";
  selectedResourceId.value = null;
  selectedDetail.value = null;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  editorText.value = JSON.stringify(
    {
      channel_type: "webhook",
      enabled: true,
      capabilities: {},
      accounts: [],
      metadata: {},
    },
    null,
    2,
  );
}

function resetEditorFromDetail(detail: SettingsResourceSummaryPayload): void {
  editMode.value = "update";
  editorText.value = JSON.stringify(channelWritePayloadFromConfig(resourceConfig(detail)), null, 2);
}

async function submitOwnerProfile(): Promise<void> {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  if (!canWriteOwnerProfile.value) return;
  ownerActionLoading.value = true;
  try {
    const payload = parseEditorPayload();
    const channelType = textValue(payload.channel_type, selectedChannelType.value).trim().toLowerCase();
    if (!channelType) {
      throw new Error("channel_type is required by the Channels API.");
    }
    const saved = await upsertChannelProfile(channelType, payload);
    ownerActionMessage.value = `${saved.channel_type} saved through /channels/profiles.`;
    editMode.value = "update";
    await handleOwnerActionCompleted(saved.channel_type);
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function toggleOwnerEnabled(enabled: boolean): Promise<void> {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  const channelType = selectedChannelType.value;
  if (!channelType) return;
  ownerActionLoading.value = true;
  try {
    const profile = await setChannelProfileEnabled(channelType, enabled);
    ownerActionMessage.value = `${profile.channel_type} ${enabled ? "enabled" : "disabled"} through Channels API.`;
    await handleOwnerActionCompleted(profile.channel_type);
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function removeOwnerProfile(): Promise<void> {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  const channelType = selectedChannelType.value;
  if (!channelType) return;
  if (!window.confirm(`Delete channel profile '${channelType}' through /channels/profiles?`)) return;
  ownerActionLoading.value = true;
  try {
    await deleteChannelProfile(channelType);
    ownerActionMessage.value = `${channelType} deleted through Channels API.`;
    await loadChannelProfiles();
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

function parseEditorPayload(): ChannelProfileWritePayload {
  let value: unknown;
  try {
    value = JSON.parse(editorText.value);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`Invalid JSON: ${detail}`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Channel profile payload must be a JSON object.");
  }
  return channelWritePayloadFromConfig(value as JsonRecord);
}

function channelWritePayloadFromConfig(config: JsonRecord): ChannelProfileWritePayload {
  return {
    channel_type: optionalText(config.channel_type ?? config.channel_kind),
    enabled: typeof config.enabled === "boolean" ? config.enabled : true,
    capabilities: objectValue(config.capabilities) ?? {},
    accounts: arrayOfRecords(config.accounts),
    metadata: objectValue(config.metadata) ?? {},
  };
}

async function loadSettingsOverlay(): Promise<SettingsResourcePagePayload | null> {
  try {
    return await listSettingsResources("channel-profiles", { limit: 1, offset: 0 }) as SettingsResourcePagePayload;
  } catch {
    return null;
  }
}

function buildChannelProfilePage(
  profiles: ChannelProfileApiPayload[],
  overlay: SettingsResourcePagePayload | null,
): SettingsResourcePagePayload {
  return {
    title: overlay?.title ?? "Channel Profiles",
    description: overlay?.description ?? "Channel profiles from Channels module with Settings governance overlay.",
    status: overlay?.status ?? (profiles.length ? "ready" : "empty"),
    resources: profiles.map(channelProfileToResource),
    list: { total: profiles.length },
    detail: profiles[0] ? channelProfileToDetail(profiles[0]) : null,
  };
}

function channelProfileToResource(profile: ChannelProfileApiPayload): SettingsResourceSummaryPayload {
  const effectiveConfig = channelProfileConfig(profile);
  return {
    id: profile.channel_type,
    resource_id: profile.channel_type,
    display_name: profile.channel_type,
    status: profile.enabled ? "ready" : "disabled",
    enabled: profile.enabled,
    source: "channels_module_api",
    version: null,
    updated_at: null,
    metadata: {
      owner: "channels",
      account_count: profile.accounts.length,
    },
    payload: effectiveConfig,
    effective_config: effectiveConfig,
    resolution: ownerResolution("Channels module API", effectiveConfig),
  };
}

function channelProfileToDetail(profile: ChannelProfileApiPayload): SettingsResourceDetailPayload {
  return {
    ...channelProfileToResource(profile),
    title: profile.channel_type,
    validation: {
      status: "owner-api",
      checks: {
        rows: [
          { Check: "truth source", Result: "Channels module API" },
          { Check: "settings role", Result: "governance overlay only" },
        ],
      },
    },
    audit: { recent_changes: { rows: [], total: 0 } },
    versions: [],
  };
}

function channelProfileConfig(profile: ChannelProfileApiPayload): JsonRecord {
  return {
    channel_type: profile.channel_type,
    channel_kind: profile.channel_type,
    enabled: profile.enabled,
    capabilities: profile.capabilities,
    accounts: profile.accounts,
    account_count: profile.accounts.length,
    metadata: profile.metadata,
  };
}

function ownerResolution(name: string, value: JsonRecord): SettingsResourceSummaryPayload["resolution"] {
  return {
    value,
    source: { kind: "owner_module", name },
    sources: [{ kind: "owner_module", name, version_id: null }],
    override_trace: [],
  };
}

function resourceConfig(resource: SettingsResourceSummaryPayload): JsonRecord {
  return objectValue(resource.effective_config)
    ?? objectValue(resource.payload)
    ?? objectValue(resource.resolution?.value)
    ?? {};
}

function settingsResourceId(resource: SettingsResourceSummaryPayload): string {
  return textValue(resource.resource_id, textValue(resource.id, "unknown"));
}

function objectValue(value: unknown): JsonRecord | null {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as JsonRecord;
  return null;
}

function arrayOfRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value)
    ? value.map(objectValue).filter((item): item is JsonRecord => item !== null)
    : [];
}

function optionalText(value: unknown): string | null {
  const text = textValue(value, "");
  return text || null;
}

function tableCellValue(row: unknown, key: string): unknown {
  if (!row || typeof row !== "object") return null;
  if ("cells" in row && row.cells && typeof row.cells === "object") {
    return (row.cells as Record<string, unknown>)[key];
  }
  return (row as Record<string, unknown>)[key];
}

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatTime(value: unknown): string {
  const raw = textValue(value, "");
  if (!raw) return "-";
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
}
</script>

<template>
  <main class="settings-module channel-settings scroll-area">
    <header class="channel-page-header">
      <div>
        <p>Settings / <strong>Channel Profiles</strong></p>
        <h1>{{ textValue(activeDetail?.display_name, textValue(activeDetail?.title, "Channel Profiles")) }} <span><i class="channel-status-dot" />{{ textValue(activeDetail?.status, settingsPage?.status ?? "unknown") }}</span></h1>
        <div class="channel-id">ID: <code>{{ selectedResourceId ?? "-" }}</code><Copy :size="13" /></div>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="beginCreateProfile">
          <Plus :size="14" /> New
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadChannelProfiles">
          <RefreshCcw :size="14" /> Refresh
        </UiButton>
      </div>
    </header>

    <section v-if="loadError" class="settings-panel">
      <p class="settings-tone-danger">{{ loadError }}</p>
    </section>

    <section class="channel-layout">
      <aside class="settings-panel channel-picker">
        <label><MessageCircle :size="14" /><input disabled placeholder="Search loaded profiles..." /></label>
        <select disabled><option>Channels owner profiles</option></select>
        <div class="channel-list">
          <button
            v-for="resource in resources"
            :key="settingsResourceId(resource)"
            :class="{ active: settingsResourceId(resource) === selectedResourceId }"
            type="button"
            @click="selectResource(resource)"
          >
            <span><MessageCircle :size="18" /></span>
            <strong>{{ textValue(resource.display_name, settingsResourceId(resource)) }}<small>{{ settingsResourceId(resource) }}</small></strong>
            <em>{{ resource.enabled === false ? "disabled" : textValue(resource.status, "ready") }}</em>
          </button>
        </div>
        <p class="channel-owner-note">Create and update channel profiles through the Channels module API. Settings only shows governance policy.</p>
      </aside>

      <div class="channel-workspace">
        <section class="settings-panel">
          <div class="settings-panel-heading">
            <h2>Channel Profiles</h2>
            <span>{{ isLoading ? "Loading" : `${channelRows.length} / ${totalResources}` }}</span>
          </div>
          <DataTable
            :columns="['Name', 'Channel ID', 'Type', 'Status', 'Source', 'Version', 'Updated At']"
            :rows="channelRows"
            section-id="channel-profiles"
            clickable-rows
            @row-click="selectChannelRow"
          />
        </section>

        <section v-if="!isLoading && !resources.length && editMode !== 'create'" class="settings-panel settings-empty-state">
          <MessageCircle :size="24" />
          <h2>No channel profiles</h2>
          <p><code>/channels/profiles</code> returned no profiles. Profile truth and write workflows remain in Channels; Settings only shows governance policy.</p>
        </section>

        <section v-else class="channel-top-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Effective Configuration</h2></div>
            <DataTable :columns="['Key', 'Value']" :rows="effectiveRows" section-id="channel-effective-config" />
            <p v-if="detailLoading">Loading selected channel detail...</p>
            <p v-if="detailError" class="settings-tone-danger">{{ detailError }}</p>
          </article>

          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>Resolution Trace</h2></div>
            <DataTable :columns="['Layer', 'Source', 'Version']" :rows="resolutionRows" section-id="channel-resolution-trace" />
          </article>

          <aside class="channel-side-stack">
            <article class="settings-panel">
              <div class="settings-panel-heading"><h2>Summary</h2></div>
              <dl class="settings-kv">
                <div><dt>Status</dt><dd>{{ textValue(activeDetail?.status, "unknown") }}</dd></div>
                <div><dt>Enabled</dt><dd>{{ activeDetail?.enabled === false ? "false" : "true" }}</dd></div>
                <div><dt>Source</dt><dd>{{ textValue(activeDetail?.source, activeDetail?.resolution?.source?.name ?? "-") }}</dd></div>
                <div><dt>Version</dt><dd>{{ textValue(activeDetail?.version, "-") }}</dd></div>
                <div><dt>Overrides</dt><dd>{{ activeDetail?.resolution?.override_trace?.length ?? 0 }}</dd></div>
                <div><dt>Versions</dt><dd>{{ selectedDetail?.versions?.length ?? 0 }}</dd></div>
              </dl>
            </article>
            <article class="settings-panel channel-owner-editor">
              <div class="settings-panel-heading">
                <h2>{{ ownerFormTitle }}</h2>
                <span>Channels owner API</span>
              </div>
              <textarea v-model="editorText" spellcheck="false" />
              <div class="settings-header-actions compact-actions">
                <UiButton size="sm" variant="primary" :disabled="!canWriteOwnerProfile" @click="submitOwnerProfile">
                  <Save :size="14" /> Save
                </UiButton>
                <UiButton size="sm" variant="secondary" :disabled="ownerActionLoading || !selectedChannelType" @click="toggleOwnerEnabled(activeDetail?.enabled === false)">
                  <Power :size="14" /> {{ activeDetail?.enabled === false ? "Enable" : "Disable" }}
                </UiButton>
                <UiButton size="sm" variant="danger" :disabled="ownerActionLoading || !selectedChannelType" @click="removeOwnerProfile">
                  <Trash2 :size="14" /> Delete
                </UiButton>
              </div>
              <p v-if="ownerActionMessage" class="settings-tone-success">{{ ownerActionMessage }}</p>
              <p v-if="ownerActionError" class="settings-tone-danger">{{ ownerActionError }}</p>
              <p class="channel-owner-note">Writes go directly to <code>/channels/profiles</code>. Runtime readiness remains in Operations.</p>
            </article>
          </aside>
        </section>
      </div>
    </section>

    <footer class="settings-footer">
      <span><GitBranch :size="14" />Governance overlay: /ui/settings/channel-profiles</span>
      <span><MessageCircle :size="14" />Truth source: Channels module API</span>
      <a>Audit History <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.channel-page-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.channel-page-header p {
  margin: 0 0 6px;
  color: var(--text-muted);
  font-size: 12px;
}

.channel-page-header h1,
.channel-page-header h1 span,
.channel-id {
  display: flex;
  align-items: center;
}

.channel-page-header h1 {
  gap: 10px;
  margin: 0;
  font-size: 20px;
}

.channel-page-header h1 span {
  gap: 6px;
  min-height: 21px;
  padding: 3px 8px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
  font-size: 11px;
}

.channel-id {
  gap: 8px;
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.channel-layout {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
  gap: 12px;
}

.channel-picker {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 10px;
}

.channel-picker label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.channel-picker input,
.channel-picker select {
  width: 100%;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.channel-picker input {
  min-height: 0;
  border: 0;
  outline: 0;
  background: transparent;
}

.channel-picker select {
  padding: 0 8px;
}

.channel-list {
  display: grid;
  gap: 4px;
}

.channel-list button {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 58px;
  padding: 8px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.channel-list button.active {
  background: var(--surface-active);
}

.channel-list button > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--color-blue);
  border-radius: var(--radius-2);
  color: var(--color-blue);
}

.channel-list strong {
  display: grid;
  gap: 3px;
  font-size: 12px;
}

.channel-list small {
  color: var(--text-muted);
  font-size: 11px;
}

.channel-list em {
  color: var(--color-success);
  font-size: 10.5px;
  font-style: normal;
}

.channel-owner-note {
  margin: 0;
  padding: 8px 2px 0;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.channel-workspace {
  min-width: 0;
}

.channel-top-grid,
.channel-mid-grid,
.channel-bottom-grid {
  display: grid;
  gap: 10px;
}

.channel-top-grid {
  grid-template-columns: 0.9fr 1.05fr 1.05fr;
}

.channel-side-stack {
  display: grid;
  gap: 10px;
  align-content: start;
  min-width: 0;
}

.channel-owner-editor {
  display: grid;
  gap: 10px;
}

.channel-owner-editor textarea {
  min-height: 190px;
  resize: vertical;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
}

.compact-actions {
  flex-wrap: wrap;
  justify-content: flex-start;
}

.channel-mid-grid {
  grid-template-columns: 1fr 1fr 330px;
  margin-top: 10px;
}

.channel-bottom-grid {
  grid-template-columns: 1fr 1.2fr;
  margin-top: 10px;
}

.settings-form-grid small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.asset-list {
  display: grid;
  gap: 8px;
  margin: 10px 0 20px;
}

.asset-list span {
  display: flex;
  justify-content: space-between;
  min-height: 34px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-size: 11px;
}

.asset-list em {
  color: var(--text-muted);
  font-style: normal;
}

.binding-flow,
.mapping-grid {
  display: grid;
  align-items: center;
  gap: 10px;
}

.binding-flow {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
}

.binding-flow span {
  display: grid;
  gap: 4px;
  min-height: 70px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  font-size: 11px;
}

pre {
  min-height: 70px;
  margin: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10.5px;
  white-space: pre-wrap;
}

.binding-preview button,
.policy-stack button {
  min-height: 30px;
  margin-top: 10px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--color-accent);
  cursor: pointer;
}

.policy-stack {
  display: grid;
  gap: 10px;
}

.policy-stack article + article {
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

.policy-stack h3 {
  margin: 0 0 8px;
  font-size: 13px;
}

.mapping-preview {
  margin-top: 10px;
}

.mapping-grid {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) minmax(0, 1fr) auto minmax(0, 1fr);
}

.mapping-grid h3 {
  margin: 0 0 8px;
  font-size: 12px;
}

.channel-bottom-grid p {
  color: var(--text-muted);
  font-size: 11px;
}

.channel-status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-success);
}
</style>
