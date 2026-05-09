<script setup lang="ts">
import { ArrowRight, CheckCircle2, Database, GitBranch, LayoutList, RefreshCcw, Shield } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { getSettingsResource, listSettingsResources } from "../api";
import SettingsActionPanel from "../components/SettingsActionPanel.vue";

type TableRow = Record<string, string | number | null>;
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

interface SettingsSourcePayload {
  kind?: string;
  name?: string;
  source_id?: string;
  version?: number | string | null;
  version_id?: string | null;
  override_id?: string | null;
  applied?: boolean;
  reason?: string | null;
}

interface SettingsResolutionPayload {
  source?: SettingsSourcePayload;
  sources?: SettingsSourcePayload[];
  override_trace?: SettingsSourcePayload[];
  snapshot_id?: string | null;
  resolved_at?: string | null;
  validation?: {
    ok?: boolean;
    errors?: unknown[];
    warnings?: unknown[];
    metadata?: Record<string, unknown>;
  };
}

interface SettingsResourceSummary {
  resource_id: string;
  id?: string;
  display_name?: string;
  status?: string;
  enabled?: boolean;
  source?: string | null;
  version?: number | string | null;
  updated_at?: string | null;
  metadata?: Record<string, unknown>;
  effective_config?: Record<string, unknown>;
  resolution?: SettingsResolutionPayload;
}

interface SettingsVersionPayload {
  id?: string;
  version_number?: number | string | null;
  status?: string;
  source?: string | null;
  reason?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  published_at?: string | null;
  validation?: {
    ok?: boolean;
    errors?: unknown[];
    warnings?: unknown[];
  };
}

interface SettingsValidationPayload {
  status?: string;
  last_validated_at?: string | null;
  checks?: {
    columns?: string[];
    rows?: TableRow[];
  };
  result?: {
    ok?: boolean;
    errors?: unknown[];
    warnings?: unknown[];
  };
}

interface SettingsAuditPayload {
  recent_changes?: {
    columns?: string[];
    rows?: TableRow[];
  };
  reason_required?: boolean;
  audit_history_route?: string;
}

interface SettingsResourceDetail extends SettingsResourceSummary {
  title?: string;
  payload?: Record<string, unknown>;
  validation?: SettingsValidationPayload;
  audit?: SettingsAuditPayload;
  versions?: SettingsVersionPayload[];
}

interface SettingsListPayload {
  total?: number;
  limit?: number;
  offset?: number;
}

interface SettingsKindPayload {
  title?: string;
  description?: string;
  status?: string;
  resources?: SettingsResourceSummary[];
  list?: SettingsListPayload;
  detail?: SettingsResourceDetail | null;
}

const page = ref<SettingsKindPayload | null>(null);
const selectedDetail = ref<SettingsResourceDetail | null>(null);
const selectedResourceId = ref<string | null>(null);
const isLoading = ref(false);
const detailLoading = ref(false);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);

const resources = computed(() => page.value?.resources ?? []);
const backendTotal = computed(() => page.value?.list?.total ?? resources.value.length);
const listLimit = computed(() => page.value?.list?.limit ?? resources.value.length);
const listOffset = computed(() => page.value?.list?.offset ?? 0);

const memoryRows = computed<TableRow[]>(() =>
  resources.value.map((resource) => {
    const config = resource.effective_config ?? {};
    return {
      Name: textValue(resource.display_name, resource.resource_id),
      ID: resource.resource_id,
      "Retrieval Backend": textValue(config.retrieval_backend),
      "Vector Provider": textValue(config.vector_provider),
      "Vector Model": textValue(config.vector_model),
      "Watch Interval": secondsText(config.watch_interval_seconds),
      Status: titleize(resource.status),
      Enabled: yesNo(resource.enabled),
      Source: textValue(resource.source),
      Version: textValue(resource.version),
    };
  }),
);

const selectedConfig = computed(() => selectedDetail.value?.effective_config ?? {});
const selectedResolution = computed(() => selectedDetail.value?.resolution ?? null);
const selectedSource = computed(() => selectedResolution.value?.source ?? null);
const selectedTitle = computed(() => selectedDetail.value?.title ?? selectedDetail.value?.display_name ?? selectedDetail.value?.resource_id ?? "No memory config selected");
const selectedStatusTone = computed<StatusTone>(() => toneForStatus(selectedDetail.value?.status));
const sourceCount = computed(() => selectedResolution.value?.sources?.length ?? 0);
const overrideCount = computed(() => selectedResolution.value?.override_trace?.length ?? 0);
const validationStatus = computed(() => {
  const explicit = selectedDetail.value?.validation?.status;
  if (explicit) return explicit;
  return selectedResolution.value?.validation?.ok === true ? "valid" : "unknown";
});
const validationTone = computed<StatusTone>(() => toneForStatus(validationStatus.value));

const defaultConfigRows = computed<TableRow[]>(() =>
  objectRows(selectedConfig.value, [
    "id",
    "retrieval_backend",
    "vector_provider",
    "vector_model",
    "vector_base_url",
    "vector_credential_binding",
    "vector_timeout_seconds",
    "watch_interval_seconds",
    "enabled",
  ]),
);

const resolutionRows = computed<TableRow[]>(() => {
  const sources = selectedResolution.value?.sources ?? [];
  return sources.map((source, index) => ({
    Step: index + 1,
    Kind: titleize(source.kind),
    Source: textValue(source.name ?? source.source_id),
    Version: textValue(source.version ?? source.version_id),
    Applied: yesNo(source.applied),
    Reason: textValue(source.reason),
  }));
});

const overrideRows = computed<TableRow[]>(() =>
  (selectedResolution.value?.override_trace ?? []).map((source, index) => ({
    Step: index + 1,
    Kind: titleize(source.kind),
    Source: textValue(source.name ?? source.source_id),
    Version: textValue(source.version ?? source.version_id),
    Applied: yesNo(source.applied),
    Reason: textValue(source.reason),
  })),
);

const validationRows = computed<TableRow[]>(() => {
  const checkRows = selectedDetail.value?.validation?.checks?.rows;
  if (checkRows?.length) return checkRows;
  const validation = selectedDetail.value?.validation?.result ?? selectedResolution.value?.validation;
  return [
    { Check: "schema", Result: validation?.ok === false ? "failed" : textValue(validationStatus.value) },
    { Check: "warnings", Result: String(validation?.warnings?.length ?? 0) },
    { Check: "errors", Result: String(validation?.errors?.length ?? 0) },
  ];
});

const versionRows = computed<TableRow[]>(() =>
  (selectedDetail.value?.versions ?? []).map((version) => ({
    Version: textValue(version.version_number, version.id ?? "-"),
    Status: titleize(version.status),
    Source: textValue(version.source),
    "Created By": textValue(version.created_by),
    "Created At": textValue(version.created_at),
    "Published At": textValue(version.published_at),
    Reason: textValue(version.reason),
  })),
);

const auditRows = computed<TableRow[]>(() => selectedDetail.value?.audit?.recent_changes?.rows ?? []);

onMounted(() => {
  void loadMemoryConfig();
});

async function loadMemoryConfig(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const payload = await listSettingsResources("memory-config", { limit: 50, offset: 0 }) as SettingsKindPayload;
    page.value = payload;
    const firstResourceId = payload.resources?.[0]?.resource_id ?? null;
    selectedResourceId.value = firstResourceId;
    selectedDetail.value = payload.detail ?? null;
    if (firstResourceId && selectedDetail.value?.resource_id !== firstResourceId) {
      await loadMemoryDetail(firstResourceId);
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    page.value = null;
    selectedDetail.value = null;
    selectedResourceId.value = null;
  } finally {
    isLoading.value = false;
  }
}

async function loadMemoryDetail(resourceId: string): Promise<void> {
  detailLoading.value = true;
  detailError.value = null;
  selectedResourceId.value = resourceId;
  try {
    selectedDetail.value = await getSettingsResource("memory-config", resourceId) as SettingsResourceDetail;
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

async function handleSettingsActionCompleted(): Promise<void> {
  const resourceId = selectedResourceId.value;
  await loadMemoryConfig();
  if (resourceId) {
    await loadMemoryDetail(resourceId);
  }
}

function selectMemoryResource(row: unknown): void {
  const resourceId = rowValue(row, "ID");
  if (resourceId && resourceId !== selectedResourceId.value) {
    void loadMemoryDetail(resourceId);
  }
}

function rowValue(row: unknown, key: string): string | null {
  if (!isRecord(row)) return null;
  const value = row[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function objectRows(source: Record<string, unknown>, preferredKeys: string[]): TableRow[] {
  const keys = [
    ...preferredKeys.filter((key) => Object.prototype.hasOwnProperty.call(source, key)),
    ...Object.keys(source).filter((key) => !preferredKeys.includes(key)),
  ];
  return keys.map((key) => ({
    Setting: humanizeKey(key),
    Value: shortValue(source[key]),
  }));
}

function secondsText(value: unknown): string {
  const text = textValue(value);
  return text === "-" ? text : `${text}s`;
}

function textValue(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return yesNo(value);
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    const items = value.map((item) => textValue(item, "")).filter(Boolean);
    return items.length ? items.join(", ") : fallback;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return fallback;
  }
}

function shortValue(value: unknown): string {
  const text = textValue(value);
  return text.length > 160 ? `${text.slice(0, 157)}...` : text;
}

function yesNo(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return textValue(value);
}

function titleize(value: unknown, fallback = "-"): string {
  const text = textValue(value, fallback);
  if (text === "-") return text;
  return text
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function humanizeKey(value: string): string {
  return titleize(value);
}

function toneForStatus(value: unknown): StatusTone {
  const text = textValue(value, "").toLowerCase();
  if (/(failed|invalid|error|disabled|blocked)/.test(text)) return "danger";
  if (/(warning|draft|pending|unknown)/.test(text)) return "warning";
  if (/(active|ready|valid|success|published|enabled)/.test(text)) return "success";
  if (text) return "info";
  return "neutral";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
</script>

<template>
  <main class="settings-module memory-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Memory Config</h1>
        <p>Settings-owned memory defaults from <code>/ui/settings/memory-config</code>.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" @click="loadMemoryConfig"><RefreshCcw :size="14" /> Refresh</UiButton>
      </div>
    </header>

    <section class="memory-summary-grid">
      <article class="settings-panel memory-summary-card">
        <span><Database :size="18" /></span>
        <div><small>Backend total</small><strong>{{ backendTotal }}</strong><p>Count from list.total.</p></div>
      </article>
      <article class="settings-panel memory-summary-card">
        <span><LayoutList :size="18" /></span>
        <div><small>Default backend</small><strong>{{ textValue(selectedConfig.retrieval_backend) }}</strong><p>Selected resource {{ selectedResourceId ?? "-" }}.</p></div>
      </article>
      <article class="settings-panel memory-summary-card">
        <span><GitBranch :size="18" /></span>
        <div><small>Resolution source</small><strong>{{ textValue(selectedSource?.name ?? selectedDetail?.source) }}</strong><p>{{ sourceCount }} sources, {{ overrideCount }} overrides.</p></div>
      </article>
      <article class="settings-panel memory-summary-card">
        <span><CheckCircle2 :size="18" /></span>
        <div><small>Validation</small><strong>{{ titleize(validationStatus) }}</strong><p>{{ selectedDetail?.validation?.last_validated_at ?? "No validation timestamp yet." }}</p></div>
      </article>
    </section>

    <section class="settings-panel memory-list">
      <div v-if="isLoading" class="settings-state">Loading memory config from Settings...</div>
      <div v-else-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
      <div v-else-if="!resources.length" class="settings-state">No Settings-owned memory config has been imported yet.</div>
      <DataTable
        v-else
        :columns="['Name', 'ID', 'Retrieval Backend', 'Vector Provider', 'Vector Model', 'Watch Interval', 'Status', 'Enabled', 'Source', 'Version']"
        :rows="memoryRows"
        section-id="memory-config"
        clickable-rows
        @row-click="selectMemoryResource"
      />
      <footer>Showing {{ memoryRows.length }} loaded rows from {{ backendTotal }} backend resources (limit {{ listLimit }}, offset {{ listOffset }}).</footer>
    </section>

    <section v-if="resources.length || selectedDetail || detailLoading" class="memory-detail-layout">
      <div class="memory-main-column">
        <article class="settings-panel memory-editor">
          <aside class="memory-editor-tabs">
            <button class="active" type="button">Default Config</button>
            <button type="button">Resolution</button>
            <button type="button">Validation</button>
            <button type="button">Versions</button>
            <button type="button">Audit</button>
          </aside>

          <div class="memory-form">
            <div v-if="detailLoading" class="settings-state detail-state">Loading selected memory config...</div>
            <div v-else-if="detailError" class="settings-state settings-state--error detail-state">{{ detailError }}</div>
            <template v-else-if="selectedDetail">
              <header>
                <div class="memory-title">
                  <span><Database :size="18" /></span>
                  <div>
                    <h2>{{ selectedTitle }} <em><StatusDot :tone="selectedStatusTone" />{{ titleize(selectedDetail.status) }}</em></h2>
                    <p>Resource <code>{{ selectedDetail.resource_id }}</code> from {{ textValue(selectedDetail.source) }}.</p>
                  </div>
                </div>
              </header>

              <section class="memory-config-cards">
                <article><h3>Retrieval</h3><dl class="settings-kv"><div><dt>Backend</dt><dd>{{ textValue(selectedConfig.retrieval_backend) }}</dd></div><div><dt>Enabled</dt><dd>{{ yesNo(selectedConfig.enabled) }}</dd></div></dl></article>
                <article><h3>Vector</h3><dl class="settings-kv"><div><dt>Provider</dt><dd>{{ textValue(selectedConfig.vector_provider) }}</dd></div><div><dt>Model</dt><dd>{{ textValue(selectedConfig.vector_model) }}</dd></div></dl></article>
                <article><h3>Credential</h3><dl class="settings-kv"><div><dt>Binding</dt><dd>{{ textValue(selectedConfig.vector_credential_binding) }}</dd></div><div><dt>Base URL</dt><dd>{{ textValue(selectedConfig.vector_base_url) }}</dd></div></dl></article>
                <article><h3>Timing</h3><dl class="settings-kv"><div><dt>Vector Timeout</dt><dd>{{ secondsText(selectedConfig.vector_timeout_seconds) }}</dd></div><div><dt>Watch Interval</dt><dd>{{ secondsText(selectedConfig.watch_interval_seconds) }}</dd></div></dl></article>
              </section>

              <article class="memory-config-table">
                <div class="settings-panel-heading"><h3>Effective Default Config</h3><span>Redacted by backend</span></div>
                <DataTable v-if="defaultConfigRows.length" :columns="['Setting', 'Value']" :rows="defaultConfigRows" section-id="memory-effective-config" />
                <div v-else class="settings-state settings-state--compact">No effective memory config returned.</div>
              </article>
            </template>
            <div v-else class="settings-state detail-state">Select a memory config resource to inspect its Settings detail.</div>
          </div>
        </article>
      </div>

      <aside class="memory-side-stack">
        <article class="settings-panel resolution-preview">
          <div class="settings-panel-heading"><h2>Resolution Trace</h2><span>{{ sourceCount }} sources</span></div>
          <DataTable v-if="resolutionRows.length" :columns="['Step', 'Kind', 'Source', 'Version', 'Applied', 'Reason']" :rows="resolutionRows" section-id="memory-resolution" />
          <div v-else class="settings-state settings-state--compact">No resolution sources returned.</div>
          <DataTable v-if="overrideRows.length" class="memory-overrides" :columns="['Step', 'Kind', 'Source', 'Version', 'Applied', 'Reason']" :rows="overrideRows" section-id="memory-overrides" />
          <strong>Status <em>{{ titleize(validationStatus) }}</em></strong>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Validation</h2><span><StatusDot :tone="validationTone" />{{ titleize(validationStatus) }}</span></div>
          <DataTable :columns="['Check', 'Result']" :rows="validationRows" section-id="memory-validation" />
        </article>

        <SettingsActionPanel
          kind="memory-config"
          :resource-id="selectedResourceId"
          :enabled="selectedDetail?.enabled ?? null"
          @completed="handleSettingsActionCompleted"
        />

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Versions</h2><span>{{ versionRows.length }}</span></div>
          <DataTable v-if="versionRows.length" :columns="['Version', 'Status', 'Source', 'Created By', 'Created At', 'Published At', 'Reason']" :rows="versionRows" section-id="memory-versions" />
          <div v-else class="settings-state settings-state--compact">No versions returned for this resource.</div>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Settings Audit</h2><span>{{ auditRows.length }}</span></div>
          <DataTable v-if="auditRows.length" :columns="['Audit ID', 'Action', 'Target', 'Status', 'Actor', 'Reason']" :rows="auditRows" section-id="memory-audit" />
          <div v-else class="settings-state settings-state--compact">No Settings audit entries yet.</div>
          <a class="panel-link" href="/settings/audit-logs">Open audit logs <ArrowRight :size="12" /></a>
        </article>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><Database :size="14" />Config Source: Settings Memory Config</span>
      <span><GitBranch :size="14" />Detail: /ui/settings/memory-config/{{ selectedResourceId ?? ":id" }}</span>
      <span><Shield :size="14" />Runtime indexing and query health are owned outside Settings.</span>
    </footer>
  </main>
</template>

<style scoped>
.memory-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.memory-summary-card {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 88px;
}

.memory-summary-card > span {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
  color: var(--color-accent);
}

.memory-summary-card small,
.memory-summary-card p,
.memory-form p {
  color: var(--text-muted);
  font-size: 11px;
}

.memory-summary-card strong {
  display: block;
  overflow: hidden;
  margin: 3px 0;
  color: var(--text-primary);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-list,
.memory-editor {
  padding: 0;
  overflow: hidden;
}

.memory-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.memory-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.memory-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 70%, var(--surface-raised));
}

.memory-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.memory-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.memory-side-stack,
.memory-main-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.memory-side-stack {
  align-content: start;
}

.memory-side-stack .settings-panel {
  padding: 10px 12px;
}

.memory-side-stack :deep(th),
.memory-side-stack :deep(td),
.memory-config-table :deep(th),
.memory-config-table :deep(td) {
  padding-block: 4px;
  font-size: 10.5px;
}

.memory-editor {
  display: grid;
  grid-template-columns: 164px minmax(0, 1fr);
}

.memory-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.memory-editor-tabs button {
  min-height: 27px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.memory-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.memory-form {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
}

.memory-form header,
.memory-title,
.memory-title h2 {
  display: flex;
  align-items: center;
}

.memory-title {
  gap: 10px;
}

.memory-title > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 72%, var(--surface-raised));
}

.memory-title h2 {
  flex-wrap: wrap;
  gap: 8px;
  font-size: 16px;
}

.memory-title em {
  display: inline-flex;
  gap: 5px;
  color: var(--text-secondary);
  font-size: 11px;
  font-style: normal;
}

.memory-config-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.memory-config-cards article,
.memory-config-table {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.memory-config-cards h3 {
  margin-bottom: 8px;
  font-size: 13px;
}

.resolution-preview {
  display: grid;
  gap: 9px;
}

.resolution-preview strong {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 12px;
}

.resolution-preview em {
  color: var(--color-success);
  font-style: normal;
}

.memory-overrides {
  margin-top: 8px;
}

.panel-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}

.settings-state {
  display: grid;
  place-items: center;
  min-height: 168px;
  padding: 18px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

.settings-state--compact {
  min-height: 74px;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-2);
}

.settings-state--error {
  color: var(--color-danger);
}

.detail-state {
  min-height: 300px;
}
</style>
