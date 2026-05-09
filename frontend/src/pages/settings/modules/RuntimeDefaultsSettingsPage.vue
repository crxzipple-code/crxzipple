<script setup lang="ts">
import { ArrowRight, CheckCircle2, GitBranch, RefreshCcw, Shield, SlidersHorizontal, Wrench, Zap } from "lucide-vue-next";
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

const runtimeRows = computed<TableRow[]>(() =>
  resources.value.map((resource) => {
    const config = resource.effective_config ?? {};
    return {
      Name: textValue(resource.display_name, resource.resource_id),
      ID: resource.resource_id,
      Status: titleize(resource.status),
      Enabled: yesNo(resource.enabled),
      "Orchestration Settings": runtimeGroupRows(config, ["orchestration_"], ["orchestration"], "orchestration").length,
      "Tool Settings": runtimeGroupRows(config, ["tool_run_", "tool_worker_", "tool_remote_"], ["tool", "tool_worker"], "tool").length,
      "Daemon Settings": runtimeGroupRows(config, ["daemon_"], ["daemon"], "daemon").length,
      Source: textValue(resource.source),
      Version: textValue(resource.version),
    };
  }),
);

const selectedConfig = computed(() => selectedDetail.value?.effective_config ?? {});
const selectedResolution = computed(() => selectedDetail.value?.resolution ?? null);
const selectedSource = computed(() => selectedResolution.value?.source ?? null);
const selectedTitle = computed(() => selectedDetail.value?.title ?? selectedDetail.value?.display_name ?? selectedDetail.value?.resource_id ?? "No runtime defaults selected");
const selectedStatusTone = computed<StatusTone>(() => toneForStatus(selectedDetail.value?.status));
const sourceCount = computed(() => selectedResolution.value?.sources?.length ?? 0);
const overrideCount = computed(() => selectedResolution.value?.override_trace?.length ?? 0);
const validationStatus = computed(() => {
  const explicit = selectedDetail.value?.validation?.status;
  if (explicit) return explicit;
  return selectedResolution.value?.validation?.ok === true ? "valid" : "unknown";
});
const validationTone = computed<StatusTone>(() => toneForStatus(validationStatus.value));

const orchestrationRows = computed<TableRow[]>(() =>
  runtimeGroupRows(selectedConfig.value, ["orchestration_"], ["orchestration"], "orchestration"),
);
const toolRows = computed<TableRow[]>(() =>
  runtimeGroupRows(selectedConfig.value, ["tool_run_", "tool_worker_", "tool_remote_"], ["tool", "tool_worker"], "tool"),
);
const daemonRows = computed<TableRow[]>(() =>
  runtimeGroupRows(selectedConfig.value, ["daemon_"], ["daemon"], "daemon"),
);
const remainingRows = computed<TableRow[]>(() => {
  const consumed = new Set<string>();
  collectGroupKeys(selectedConfig.value, consumed, ["orchestration_"], ["orchestration"]);
  collectGroupKeys(selectedConfig.value, consumed, ["tool_run_", "tool_worker_", "tool_remote_"], ["tool", "tool_worker"]);
  collectGroupKeys(selectedConfig.value, consumed, ["daemon_"], ["daemon"]);
  return Object.entries(selectedConfig.value)
    .filter(([key]) => key !== "id" && !consumed.has(key))
    .map(([key, value]) => ({ Setting: humanizeKey(key), Value: shortValue(value) }));
});

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
  void loadRuntimeDefaults();
});

async function loadRuntimeDefaults(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const payload = await listSettingsResources("runtime-defaults", { limit: 50, offset: 0 }) as SettingsKindPayload;
    page.value = payload;
    const firstResourceId = payload.resources?.[0]?.resource_id ?? null;
    selectedResourceId.value = firstResourceId;
    selectedDetail.value = payload.detail ?? null;
    if (firstResourceId && selectedDetail.value?.resource_id !== firstResourceId) {
      await loadRuntimeDetail(firstResourceId);
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

async function loadRuntimeDetail(resourceId: string): Promise<void> {
  detailLoading.value = true;
  detailError.value = null;
  selectedResourceId.value = resourceId;
  try {
    selectedDetail.value = await getSettingsResource("runtime-defaults", resourceId) as SettingsResourceDetail;
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

async function handleSettingsActionCompleted(): Promise<void> {
  const resourceId = selectedResourceId.value;
  await loadRuntimeDefaults();
  if (resourceId) {
    await loadRuntimeDetail(resourceId);
  }
}

function selectRuntimeResource(row: unknown): void {
  const resourceId = rowValue(row, "ID");
  if (resourceId && resourceId !== selectedResourceId.value) {
    void loadRuntimeDetail(resourceId);
  }
}

function runtimeGroupRows(
  config: Record<string, unknown>,
  prefixes: string[],
  nestedKeys: string[],
  groupLabel: string,
): TableRow[] {
  const rows: TableRow[] = [];
  const seen = new Set<string>();
  for (const nestedKey of nestedKeys) {
    const nested = config[nestedKey];
    if (!isRecord(nested)) continue;
    for (const [key, value] of Object.entries(nested)) {
      rows.push({ Setting: humanizeKey(key), Value: shortValue(value), Source: humanizeKey(nestedKey) });
      seen.add(`${nestedKey}.${key}`);
    }
  }
  for (const [key, value] of Object.entries(config)) {
    const prefix = prefixes.find((candidate) => key.startsWith(candidate));
    if (!prefix) continue;
    const setting = key.slice(prefix.length);
    const source = prefix.replace(/_$/, "");
    const seenKey = `${source}.${setting}`;
    if (seen.has(seenKey)) continue;
    rows.push({
      Setting: humanizeKey(setting || key),
      Value: shortValue(value),
      Source: humanizeKey(source || groupLabel),
    });
  }
  return rows;
}

function collectGroupKeys(
  config: Record<string, unknown>,
  consumed: Set<string>,
  prefixes: string[],
  nestedKeys: string[],
): void {
  for (const nestedKey of nestedKeys) {
    if (isRecord(config[nestedKey])) consumed.add(nestedKey);
  }
  for (const key of Object.keys(config)) {
    if (prefixes.some((prefix) => key.startsWith(prefix))) consumed.add(key);
  }
}

function rowValue(row: unknown, key: string): string | null {
  if (!isRecord(row)) return null;
  const value = row[key];
  return typeof value === "string" && value.trim() ? value : null;
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
  <main class="settings-module runtime-settings scroll-area">
    <header class="settings-page-header runtime-header">
      <div>
        <h1>Runtime Defaults</h1>
        <p><span>Read-only effective view</span> Settings-owned defaults from <code>/ui/settings/runtime-defaults</code>. Writes require audited Settings actions with a reason.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" @click="loadRuntimeDefaults"><RefreshCcw :size="14" /> Refresh</UiButton>
      </div>
    </header>

    <section class="runtime-summary-grid">
      <article class="settings-panel summary-card">
        <span><SlidersHorizontal :size="20" /></span>
        <div><small>Backend total</small><strong>{{ backendTotal }}</strong><p>Count from list.total.</p></div>
      </article>
      <article class="settings-panel summary-card">
        <span><GitBranch :size="20" /></span>
        <div><small>Source</small><strong>{{ textValue(selectedSource?.name ?? selectedDetail?.source) }}</strong><p>{{ sourceCount }} resolution sources, {{ overrideCount }} overrides.</p></div>
      </article>
      <article class="settings-panel summary-card">
        <span><Shield :size="20" /></span>
        <div><small>Selected resource</small><strong>{{ selectedResourceId ?? "-" }}</strong><p>{{ selectedTitle }}</p></div>
      </article>
      <article class="settings-panel summary-card">
        <span class="success"><CheckCircle2 :size="20" /></span>
        <div><small>Validation</small><strong>{{ titleize(validationStatus) }}</strong><p>{{ selectedDetail?.validation?.last_validated_at ?? "No validation timestamp yet." }}</p></div>
      </article>
    </section>

    <section class="settings-panel runtime-list">
      <div v-if="isLoading" class="settings-state">Loading runtime defaults from Settings...</div>
      <div v-else-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
      <div v-else-if="!resources.length" class="settings-state">No Settings-owned runtime defaults have been imported yet.</div>
      <DataTable
        v-else
        :columns="['Name', 'ID', 'Status', 'Enabled', 'Orchestration Settings', 'Tool Settings', 'Daemon Settings', 'Source', 'Version']"
        :rows="runtimeRows"
        section-id="runtime-defaults"
        clickable-rows
        @row-click="selectRuntimeResource"
      />
      <footer>Showing {{ runtimeRows.length }} loaded rows from {{ backendTotal }} backend resources (limit {{ listLimit }}, offset {{ listOffset }}).</footer>
    </section>

    <section v-if="resources.length || selectedDetail || detailLoading" class="runtime-body-grid">
      <div class="runtime-main-column">
        <article class="settings-panel precedence-card">
          <div class="settings-panel-heading"><h2>Resolution Precedence</h2><span>{{ selectedDetail?.resource_id ?? "-" }}</span></div>
          <p>Runtime defaults are the Settings baseline. Higher layers can override them, and the trace below shows the sources that produced this effective value.</p>
          <div class="precedence-flow">
            <span class="active"><em>1</em><strong>Runtime Defaults</strong><small>{{ textValue(selectedSource?.name) }}</small></span>
            <ArrowRight :size="15" />
            <span><em>2</em><strong>Environment</strong><small>owned outside this page</small></span>
            <ArrowRight :size="15" />
            <span><em>3</em><strong>Agent / Session</strong><small>consumer override</small></span>
            <ArrowRight :size="15" />
            <span><em>4</em><strong>Run</strong><small>highest precedence</small></span>
          </div>
        </article>

        <div v-if="detailLoading" class="settings-panel settings-state detail-state">Loading selected defaults...</div>
        <div v-else-if="detailError" class="settings-panel settings-state settings-state--error detail-state">{{ detailError }}</div>
        <section v-else class="defaults-grid">
          <article class="settings-panel defaults-card">
            <div class="settings-panel-heading"><h3><SlidersHorizontal :size="16" />Orchestration</h3><span>{{ orchestrationRows.length }}</span></div>
            <DataTable v-if="orchestrationRows.length" :columns="['Setting', 'Value', 'Source']" :rows="orchestrationRows" section-id="runtime-orchestration" />
            <div v-else class="settings-state settings-state--compact">No orchestration defaults returned.</div>
          </article>

          <article class="settings-panel defaults-card">
            <div class="settings-panel-heading"><h3><Wrench :size="16" />Tool</h3><span>{{ toolRows.length }}</span></div>
            <DataTable v-if="toolRows.length" :columns="['Setting', 'Value', 'Source']" :rows="toolRows" section-id="runtime-tool" />
            <div v-else class="settings-state settings-state--compact">No tool defaults returned.</div>
          </article>

          <article class="settings-panel defaults-card">
            <div class="settings-panel-heading"><h3><Zap :size="16" />Daemon</h3><span>{{ daemonRows.length }}</span></div>
            <DataTable v-if="daemonRows.length" :columns="['Setting', 'Value', 'Source']" :rows="daemonRows" section-id="runtime-daemon" />
            <div v-else class="settings-state settings-state--compact">No daemon defaults returned by Settings yet.</div>
          </article>
        </section>

        <article class="settings-panel defaults-preview">
          <div class="settings-panel-heading"><h3>Other Effective Values</h3><span>{{ remainingRows.length }}</span></div>
          <DataTable v-if="remainingRows.length" :columns="['Setting', 'Value']" :rows="remainingRows" section-id="runtime-other-values" />
          <div v-else class="settings-state settings-state--compact">No ungrouped effective values.</div>
        </article>
      </div>

      <aside class="runtime-side-column">
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Resolution Trace</h2><span>{{ sourceCount }}</span></div>
          <DataTable v-if="resolutionRows.length" :columns="['Step', 'Kind', 'Source', 'Version', 'Applied', 'Reason']" :rows="resolutionRows" section-id="runtime-resolution" />
          <div v-else class="settings-state settings-state--compact">No resolution sources returned.</div>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Validation</h2><span><StatusDot :tone="validationTone" />{{ titleize(validationStatus) }}</span></div>
          <DataTable :columns="['Check', 'Result']" :rows="validationRows" section-id="runtime-validation" />
        </article>

        <SettingsActionPanel
          kind="runtime-defaults"
          :resource-id="selectedResourceId"
          :enabled="selectedDetail?.enabled ?? null"
          @completed="handleSettingsActionCompleted"
        />

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Versions</h2><span>{{ versionRows.length }}</span></div>
          <DataTable v-if="versionRows.length" :columns="['Version', 'Status', 'Source', 'Created By', 'Created At', 'Published At', 'Reason']" :rows="versionRows" section-id="runtime-versions" />
          <div v-else class="settings-state settings-state--compact">No versions returned for this resource.</div>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Settings Audit</h2><span>{{ auditRows.length }}</span></div>
          <DataTable v-if="auditRows.length" :columns="['Audit ID', 'Action', 'Target', 'Status', 'Actor', 'Reason']" :rows="auditRows" section-id="runtime-audit" />
          <div v-else class="settings-state settings-state--compact">No Settings audit entries yet.</div>
          <a class="panel-link" href="/settings/audit-logs">Open audit logs <ArrowRight :size="12" /></a>
        </article>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><SlidersHorizontal :size="14" />Config Source: Settings Runtime Defaults</span>
      <span><GitBranch :size="14" />Detail: /ui/settings/runtime-defaults/{{ selectedResourceId ?? ":id" }}</span>
      <span><CheckCircle2 :size="14" />No fake save action is rendered.</span>
    </footer>
  </main>
</template>

<style scoped>
.runtime-header {
  align-items: start;
}

.runtime-header p span {
  display: inline-flex;
  min-height: 18px;
  margin-right: 10px;
  padding: 2px 7px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 50%, transparent);
  border-radius: var(--radius-1);
  color: var(--color-warning);
  font-size: 11px;
}

.runtime-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.summary-card {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  min-height: 108px;
}

.summary-card > span {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: var(--radius-3);
  background: color-mix(in srgb, var(--color-accent) 24%, transparent);
  color: var(--color-accent);
}

.summary-card > span.success {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.summary-card small,
.summary-card p,
.runtime-main-column p {
  color: var(--text-muted);
  font-size: 11px;
}

.summary-card strong {
  display: block;
  overflow: hidden;
  margin: 4px 0;
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-list {
  padding: 0;
  overflow: hidden;
}

.runtime-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.runtime-body-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.runtime-main-column,
.runtime-side-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.runtime-side-column .settings-panel {
  padding: 10px 12px;
}

.runtime-side-column :deep(th),
.runtime-side-column :deep(td),
.defaults-card :deep(th),
.defaults-card :deep(td),
.defaults-preview :deep(th),
.defaults-preview :deep(td) {
  padding-block: 4px;
  font-size: 10.5px;
}

.precedence-card {
  min-height: 154px;
}

.precedence-card p {
  margin-bottom: 14px;
}

.precedence-flow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.precedence-flow span {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 3px 9px;
  min-height: 72px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 72%, transparent);
}

.precedence-flow span.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-accent) 12%, var(--surface-raised));
}

.precedence-flow em {
  grid-row: span 2;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-1);
  background: var(--surface-input);
  color: var(--color-accent);
  font-style: normal;
  font-weight: 800;
}

.precedence-flow strong {
  font-size: 13px;
}

.precedence-flow small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.defaults-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.defaults-grid h3 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
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
