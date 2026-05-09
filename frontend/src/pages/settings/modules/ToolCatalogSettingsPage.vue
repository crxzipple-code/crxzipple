<script setup lang="ts">
import {
  ArrowRight,
  CheckCircle2,
  Copy,
  GitBranch,
  LayoutList,
  ListFilter,
  Package,
  Play,
  RefreshCcw,
  Search,
  Shield,
  Wrench,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { listSettingsResources } from "../api";
import {
  discoverTools,
  listDiscoveryProviders,
  listToolRoots,
  listToolRuns,
  listTools,
  type ToolApiPayload,
  type ToolDiscoveryProviderApiPayload,
  type ToolRootApiPayload,
  type ToolRunApiPayload,
} from "../ownerApis/toolCatalog";

type TableRow = Record<string, string | number | null>;
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

interface SettingsSourcePayload {
  kind?: string;
  name?: string;
  source_id?: string;
  version?: number | string | null;
  version_id?: string | null;
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
}

const tools = ref<ToolApiPayload[]>([]);
const roots = ref<ToolRootApiPayload[]>([]);
const providers = ref<ToolDiscoveryProviderApiPayload[]>([]);
const settingsOverlay = ref<SettingsKindPayload | null>(null);
const selectedToolId = ref<string | null>(null);
const selectedRuns = ref<ToolRunApiPayload[]>([]);
const isLoading = ref(false);
const runsLoading = ref(false);
const isDiscovering = ref(false);
const loadError = ref<string | null>(null);
const runsError = ref<string | null>(null);
const actionMessage = ref<string | null>(null);
const actionError = ref<string | null>(null);
const kindFilter = ref<"all" | "enabled" | "disabled" | "mutating">("all");

const overlayResources = computed(() => settingsOverlay.value?.resources ?? []);
const backendTotal = computed(() => tools.value.length);
const overlayTotal = computed(() => settingsOverlay.value?.list?.total ?? overlayResources.value.length);
const providerCount = computed(() => providers.value.length);
const rootCount = computed(() => roots.value.length);
const enabledCount = computed(() => tools.value.filter((tool) => tool.enabled).length);
const disabledCount = computed(() => tools.value.filter((tool) => !tool.enabled).length);
const mutatingCount = computed(() => tools.value.filter((tool) => tool.execution_policy.mutates_state).length);

const overlayById = computed(() => {
  const lookup = new Map<string, SettingsResourceSummary>();
  for (const resource of overlayResources.value) {
    lookup.set(resource.resource_id, resource);
    if (resource.id) lookup.set(resource.id, resource);
  }
  return lookup;
});

const filteredTools = computed(() => {
  if (kindFilter.value === "enabled") return tools.value.filter((tool) => tool.enabled);
  if (kindFilter.value === "disabled") return tools.value.filter((tool) => !tool.enabled);
  if (kindFilter.value === "mutating") return tools.value.filter((tool) => tool.execution_policy.mutates_state);
  return tools.value;
});

const toolRows = computed<TableRow[]>(() =>
  filteredTools.value.map((tool) => {
    const overlay = overlayFor(tool.id);
    return {
      Name: textValue(tool.name, tool.id),
      ID: tool.id,
      Kind: titleize(tool.kind),
      Runtime: textValue(tool.runtime_key, "-"),
      Modes: textValue(tool.execution_support.supported_modes),
      Strategies: textValue(tool.execution_support.supported_strategies),
      Effects: textValue(tool.required_effect_ids),
      Enabled: yesNo(tool.enabled),
      Governance: overlay ? titleize(overlay.status, "overlay") : "-",
    };
  }),
);

const selectedTool = computed(() =>
  tools.value.find((tool) => tool.id === selectedToolId.value) ?? null,
);
const selectedOverlay = computed(() =>
  selectedToolId.value ? overlayFor(selectedToolId.value) : null,
);
const selectedTitle = computed(() => selectedTool.value?.name ?? selectedTool.value?.id ?? "No tool selected");
const selectedStatusTone = computed<StatusTone>(() => selectedTool.value?.enabled === false ? "danger" : "success");
const selectedOverlayTone = computed<StatusTone>(() => toneForStatus(selectedOverlay.value?.status));
const selectedOverlaySources = computed(() => selectedOverlay.value?.resolution?.sources?.length ?? 0);
const selectedConfig = computed(() => selectedTool.value ? toolConfig(selectedTool.value) : {});

const effectiveRows = computed<TableRow[]>(() =>
  objectRows(selectedConfig.value, [
    "id",
    "name",
    "description",
    "kind",
    "enabled",
    "source_kind",
    "runtime_key",
    "parameters",
    "tags",
    "required_effect_ids",
    "access_requirements",
    "access_requirement_sets",
    "supported_modes",
    "supported_strategies",
    "supported_environments",
    "timeout_seconds",
    "requires_confirmation",
    "mutates_state",
  ]),
);

const runRows = computed<TableRow[]>(() =>
  [...selectedRuns.value]
    .sort((left, right) => timestampValue(right.created_at) - timestampValue(left.created_at))
    .slice(0, 8)
    .map((run) => ({
      "Run ID": run.id,
      Status: titleize(run.status),
      Mode: titleize(run.target.mode),
      Strategy: titleize(run.target.strategy),
      Environment: titleize(run.target.environment),
      Attempts: `${run.attempt_count}/${run.max_attempts}`,
      "Created At": textValue(run.created_at),
      "Completed At": textValue(run.completed_at),
    })),
);

const providerRows = computed<TableRow[]>(() =>
  providers.value.map((provider) => ({
    Name: provider.name,
    Source: titleize(provider.source_kind),
    Description: textValue(provider.description),
  })),
);

const rootRows = computed<TableRow[]>(() =>
  roots.value.map((root) => ({
    Path: root.path,
    Exists: yesNo(root.exists),
  })),
);

const overlayRows = computed<TableRow[]>(() =>
  overlayResources.value.slice(0, 8).map((resource) => ({
    Resource: resource.resource_id,
    Status: titleize(resource.status),
    Enabled: yesNo(resource.enabled),
    Source: textValue(resource.source),
    Version: textValue(resource.version),
    "Updated At": textValue(resource.updated_at),
  })),
);

const coverageRows = computed<TableRow[]>(() => [
  { Capability: "List tools", Endpoint: "GET /tools", Status: "wired" },
  { Capability: "List roots", Endpoint: "GET /tools/roots", Status: "wired" },
  { Capability: "List providers", Endpoint: "GET /tools/providers", Status: "wired" },
  { Capability: "List selected tool runs", Endpoint: "GET /tools/{id}/runs", Status: "wired" },
  { Capability: "Discover catalog", Endpoint: "POST /tools/discover", Status: "wired" },
  { Capability: "Create/update/delete tool definition", Endpoint: "not exposed by Tool HTTP", Status: "disabled" },
  { Capability: "Enable/disable tool definition", Endpoint: "not exposed by Tool HTTP", Status: "disabled" },
]);

onMounted(() => {
  void loadToolCatalog();
});

async function loadToolCatalog(preferredToolId = selectedToolId.value): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [ownerTools, ownerRoots, ownerProviders, overlay] = await Promise.all([
      listTools(),
      listToolRoots(),
      listDiscoveryProviders(),
      loadSettingsOverlay(),
    ]);
    tools.value = ownerTools;
    roots.value = ownerRoots;
    providers.value = ownerProviders;
    settingsOverlay.value = overlay;

    const nextToolId =
      preferredToolId && ownerTools.some((tool) => tool.id === preferredToolId)
        ? preferredToolId
        : ownerTools[0]?.id ?? null;
    selectedToolId.value = nextToolId;
    await loadRunsForTool(nextToolId);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    tools.value = [];
    roots.value = [];
    providers.value = [];
    settingsOverlay.value = null;
    selectedToolId.value = null;
    selectedRuns.value = [];
  } finally {
    isLoading.value = false;
  }
}

async function loadRunsForTool(toolId: string | null): Promise<void> {
  selectedRuns.value = [];
  runsError.value = null;
  if (!toolId) return;
  runsLoading.value = true;
  try {
    selectedRuns.value = await listToolRuns(toolId);
  } catch (error) {
    runsError.value = error instanceof Error ? error.message : String(error);
  } finally {
    runsLoading.value = false;
  }
}

async function discoverFromOwner(): Promise<void> {
  isDiscovering.value = true;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const discovered = await discoverTools();
    actionMessage.value = `Discovered ${discovered.length} tools through /tools/discover.`;
    await loadToolCatalog(selectedToolId.value);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isDiscovering.value = false;
  }
}

async function loadSettingsOverlay(): Promise<SettingsKindPayload | null> {
  try {
    return await listSettingsResources("tool-catalog", { limit: 50, offset: 0 }) as SettingsKindPayload;
  } catch {
    return null;
  }
}

function selectToolResource(row: unknown): void {
  const toolId = rowValue(row, "ID");
  if (toolId && toolId !== selectedToolId.value) {
    selectedToolId.value = toolId;
    void loadRunsForTool(toolId);
  }
}

function refreshSelectedRuns(): void {
  void loadRunsForTool(selectedToolId.value);
}

function overlayFor(resourceId: string): SettingsResourceSummary | null {
  return overlayById.value.get(resourceId) ?? null;
}

function toolConfig(tool: ToolApiPayload): Record<string, unknown> {
  return {
    id: tool.id,
    name: tool.name,
    description: tool.description,
    kind: tool.kind,
    enabled: tool.enabled,
    source_kind: tool.source_kind,
    runtime_key: tool.runtime_key,
    parameters: tool.parameters.map((parameter) => ({
      name: parameter.name,
      data_type: parameter.data_type,
      required: parameter.required,
      description: parameter.description,
    })),
    tags: tool.tags,
    required_effect_ids: tool.required_effect_ids,
    access_requirements: tool.access_requirements,
    access_requirement_sets: tool.access_requirement_sets,
    supported_modes: tool.execution_support.supported_modes,
    supported_strategies: tool.execution_support.supported_strategies,
    supported_environments: tool.execution_support.supported_environments,
    timeout_seconds: tool.execution_policy.timeout_seconds,
    requires_confirmation: tool.execution_policy.requires_confirmation,
    mutates_state: tool.execution_policy.mutates_state,
  };
}

function rowValue(row: unknown, key: string): string | null {
  const value = tableCellValue(row, key);
  return typeof value === "string" && value.trim() ? value : null;
}

function tableCellValue(row: unknown, key: string): unknown {
  if (!isRecord(row)) return null;
  const cells = row.cells;
  if (isRecord(cells)) return cells[key];
  return row[key];
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
  return text.length > 180 ? `${text.slice(0, 177)}...` : text;
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
  if (/(failed|invalid|error|disabled|blocked|missing)/.test(text)) return "danger";
  if (/(warning|draft|pending|unknown|overlay)/.test(text)) return "warning";
  if (/(active|ready|valid|success|published|enabled|wired)/.test(text)) return "success";
  if (text) return "info";
  return "neutral";
}

function timestampValue(value: string | null): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
</script>

<template>
  <main class="settings-module tool-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Tool Catalog</h1>
        <p>Owner view from <code>/tools</code>. Settings contributes read-only governance overlay only.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isDiscovering || isLoading" @click="discoverFromOwner">
          <Search :size="14" /> Discover
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadToolCatalog()">
          <RefreshCcw :size="14" /> Refresh
        </UiButton>
      </div>
    </header>

    <section v-if="actionMessage || actionError" class="settings-panel tool-notice">
      <p v-if="actionError" class="settings-state--error">{{ actionError }}</p>
      <p v-else>{{ actionMessage }}</p>
    </section>

    <section class="tool-summary-grid">
      <article class="settings-panel tool-summary-card">
        <span><Package :size="18" /></span>
        <div><small>Owner Tools</small><strong>{{ backendTotal }}</strong><p>Loaded from GET /tools.</p></div>
      </article>
      <article class="settings-panel tool-summary-card">
        <span><Wrench :size="18" /></span>
        <div><small>Providers</small><strong>{{ providerCount }}</strong><p>Loaded from GET /tools/providers.</p></div>
      </article>
      <article class="settings-panel tool-summary-card">
        <span><GitBranch :size="18" /></span>
        <div><small>Roots</small><strong>{{ rootCount }}</strong><p>Loaded from GET /tools/roots.</p></div>
      </article>
      <article class="settings-panel tool-summary-card">
        <span><Shield :size="18" /></span>
        <div><small>Governance Overlay</small><strong>{{ overlayTotal }}</strong><p>Read-only Settings status.</p></div>
      </article>
    </section>

    <section class="tool-tabs-row">
      <nav class="settings-tabs">
        <button :class="{ active: kindFilter === 'all' }" type="button" @click="kindFilter = 'all'">All Tools</button>
        <button :class="{ active: kindFilter === 'enabled' }" type="button" @click="kindFilter = 'enabled'">Enabled ({{ enabledCount }})</button>
        <button :class="{ active: kindFilter === 'disabled' }" type="button" @click="kindFilter = 'disabled'">Disabled ({{ disabledCount }})</button>
        <button :class="{ active: kindFilter === 'mutating' }" type="button" @click="kindFilter = 'mutating'">Mutating ({{ mutatingCount }})</button>
      </nav>

      <div class="tool-filter-row">
        <button type="button" aria-label="Filter loaded owner tools"><ListFilter :size="14" /></button>
        <button class="active" type="button" aria-label="List view"><LayoutList :size="14" /></button>
      </div>
    </section>

    <section class="settings-panel tool-list">
      <div v-if="isLoading" class="settings-state">Loading owner tool catalog...</div>
      <div v-else-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
      <div v-else-if="!tools.length" class="settings-state">GET /tools returned no tools.</div>
      <DataTable
        v-else
        :columns="['Name', 'ID', 'Kind', 'Runtime', 'Modes', 'Strategies', 'Effects', 'Enabled', 'Governance']"
        :rows="toolRows"
        section-id="tool-catalog"
        clickable-rows
        @row-click="selectToolResource"
      />
      <footer>Showing {{ toolRows.length }} loaded rows from {{ backendTotal }} owner tools.</footer>
    </section>

    <section v-if="tools.length || selectedTool" class="tool-detail-layout">
      <article class="settings-panel tool-editor">
        <aside class="tool-tabs">
          <button class="active" type="button">Owner Definition</button>
          <button type="button" disabled>Parameters</button>
          <button type="button" disabled>Access</button>
          <button type="button" disabled>Runs</button>
        </aside>

        <div class="tool-form">
          <template v-if="selectedTool">
            <header>
              <h2>
                <Wrench :size="18" />{{ selectedTitle }}
                <span><StatusDot :tone="selectedStatusTone" />{{ selectedTool.enabled ? "Enabled" : "Disabled" }}</span>
              </h2>
              <em>{{ titleize(selectedTool.kind) }}</em>
            </header>
            <div class="tool-meta-grid">
              <span><strong>ID</strong>{{ selectedTool.id }}</span>
              <span><strong>Runtime</strong>{{ textValue(selectedTool.runtime_key) }}</span>
              <span><strong>Source Kind</strong>{{ titleize(selectedTool.source_kind) }}</span>
              <span><strong>Timeout</strong>{{ selectedTool.execution_policy.timeout_seconds }}s</span>
              <span><strong>Confirmation</strong>{{ yesNo(selectedTool.execution_policy.requires_confirmation) }}</span>
              <span><strong>Mutates State</strong>{{ yesNo(selectedTool.execution_policy.mutates_state) }}</span>
            </div>

            <article class="tool-config-table">
              <div class="settings-panel-heading"><h3>Owner Definition</h3><span>GET /tools</span></div>
              <DataTable v-if="effectiveRows.length" :columns="['Setting', 'Value']" :rows="effectiveRows" section-id="tool-effective-config" allow-raw-keys />
              <div v-else class="settings-state settings-state--compact">No owner definition returned.</div>
            </article>
          </template>
          <div v-else class="settings-state detail-state">Select a tool to inspect the Tool module definition.</div>
        </div>
      </article>

      <aside class="tool-summary-stack">
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Selected Tool</h2><span>{{ selectedTool?.id ?? "-" }}</span></div>
          <dl class="settings-kv">
            <div><dt>Modes</dt><dd>{{ textValue(selectedTool?.execution_support.supported_modes) }}</dd></div>
            <div><dt>Strategies</dt><dd>{{ textValue(selectedTool?.execution_support.supported_strategies) }}</dd></div>
            <div><dt>Environments</dt><dd>{{ textValue(selectedTool?.execution_support.supported_environments) }}</dd></div>
            <div><dt>Access Requirements</dt><dd>{{ textValue(selectedTool?.access_requirements) }}</dd></div>
          </dl>
        </article>
        <article class="settings-panel">
          <div class="settings-panel-heading">
            <h2>Governance Overlay</h2>
            <span><StatusDot :tone="selectedOverlayTone" />{{ titleize(selectedOverlay?.status, "no overlay") }}</span>
          </div>
          <dl class="settings-kv">
            <div><dt>Source</dt><dd>{{ textValue(selectedOverlay?.source) }}</dd></div>
            <div><dt>Version</dt><dd>{{ textValue(selectedOverlay?.version) }}</dd></div>
            <div><dt>Sources</dt><dd>{{ selectedOverlaySources }}</dd></div>
            <div><dt>Updated At</dt><dd>{{ textValue(selectedOverlay?.updated_at) }}</dd></div>
          </dl>
        </article>
        <article class="settings-panel tool-owner-actions">
          <div class="settings-panel-heading"><h2>Owner Mutations</h2><span>Tool API gaps</span></div>
          <p>Create, update, delete, enable, and disable endpoints are not exposed by <code>/tools</code>. Settings action proxy writes are intentionally not used here.</p>
          <div class="tool-disabled-actions">
            <button type="button" disabled><Wrench :size="14" /><span>Register Tool<small>No Tool owner endpoint</small></span></button>
            <button type="button" disabled><Copy :size="14" /><span>Edit Definition<small>No Tool owner endpoint</small></span></button>
            <button type="button" disabled><Shield :size="14" /><span>Enable / Disable<small>No Tool owner endpoint</small></span></button>
            <button type="button" disabled><Play :size="14" /><span>Manual Run<small>POST /tools/{id}/runs exists; argument editor not part of this compact pass</small></span></button>
          </div>
        </article>
      </aside>
    </section>

    <section class="tool-support-grid">
      <article class="settings-panel runs-panel">
        <div class="settings-panel-heading">
          <h3>Recent Runs</h3>
          <button type="button" :disabled="!selectedToolId || runsLoading" @click="refreshSelectedRuns"><RefreshCcw :size="13" /></button>
        </div>
        <div v-if="runsLoading" class="settings-state settings-state--compact">Loading /tools/{{ selectedToolId }}/runs...</div>
        <div v-else-if="runsError" class="settings-state settings-state--error settings-state--compact">{{ runsError }}</div>
        <DataTable v-else-if="runRows.length" :columns="['Run ID', 'Status', 'Mode', 'Strategy', 'Environment', 'Attempts', 'Created At', 'Completed At']" :rows="runRows" section-id="tool-runs" allow-raw-keys />
        <div v-else class="settings-state settings-state--compact">No runs returned for the selected tool.</div>
      </article>
      <article class="settings-panel provider-panel">
        <div class="settings-panel-heading"><h3>Discovery Providers</h3><span>{{ providerRows.length }}</span></div>
        <DataTable v-if="providerRows.length" :columns="['Name', 'Source', 'Description']" :rows="providerRows" section-id="tool-providers" />
        <div v-else class="settings-state settings-state--compact">No providers returned.</div>
      </article>
      <article class="settings-panel root-panel">
        <div class="settings-panel-heading"><h3>Tool Roots</h3><span>{{ rootRows.length }}</span></div>
        <DataTable v-if="rootRows.length" :columns="['Path', 'Exists']" :rows="rootRows" section-id="tool-roots" allow-raw-keys />
        <div v-else class="settings-state settings-state--compact">No roots returned.</div>
      </article>
      <article class="settings-panel overlay-panel">
        <div class="settings-panel-heading"><h3>Settings Overlay</h3><span>{{ overlayRows.length }}</span></div>
        <DataTable v-if="overlayRows.length" :columns="['Resource', 'Status', 'Enabled', 'Source', 'Version', 'Updated At']" :rows="overlayRows" section-id="tool-overlay" allow-raw-keys />
        <div v-else class="settings-state settings-state--compact">No Settings governance overlay returned.</div>
        <a class="panel-link" href="/settings/audit-logs">Open audit logs <ArrowRight :size="12" /></a>
      </article>
      <article class="settings-panel coverage-panel">
        <div class="settings-panel-heading"><h3><CheckCircle2 :size="14" />Endpoint Coverage</h3><span>owner API</span></div>
        <DataTable :columns="['Capability', 'Endpoint', 'Status']" :rows="coverageRows" section-id="tool-endpoint-coverage" allow-raw-keys />
      </article>
    </section>

    <footer class="settings-footer">
      <span><Wrench :size="14" />Owner Source: /tools</span>
      <span><GitBranch :size="14" />Runs: /tools/{{ selectedToolId ?? ":id" }}/runs</span>
      <span><Copy :size="14" />Settings remains a governance overlay.</span>
    </footer>
  </main>
</template>

<style scoped>
.tool-notice {
  margin-bottom: 10px;
  padding: 8px 12px;
}

.tool-notice p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.tool-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.tool-summary-card {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 88px;
}

.tool-summary-card > span {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
  color: var(--color-accent);
}

.tool-summary-card small,
.tool-summary-card p,
.tool-owner-actions p {
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.45;
}

.tool-summary-card strong {
  display: block;
  margin: 3px 0;
  color: var(--text-primary);
  font-size: 14px;
}

.tool-tabs-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: end;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.tool-tabs-row .settings-tabs {
  min-height: 40px;
  margin-bottom: 0;
  border-bottom: 0;
}

.tool-filter-row {
  display: grid;
  grid-template-columns: 34px 34px;
  gap: 8px;
  align-items: center;
  margin-bottom: 5px;
}

.tool-filter-row button {
  display: grid;
  place-items: center;
  min-height: 30px;
  padding: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  cursor: pointer;
}

.tool-filter-row button.active {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--color-accent);
}

.tool-list {
  padding: 0;
  overflow: hidden;
}

.tool-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.tool-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.tool-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 17px;
  height: 17px;
  transform: translateY(-50%);
  border: 1px solid color-mix(in srgb, var(--color-success) 70%, transparent);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
}

.tool-list footer {
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.tool-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.tool-editor {
  display: grid;
  grid-template-columns: 154px minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.tool-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.tool-tabs button {
  min-height: 27px;
  padding: 0 8px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.tool-tabs button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.tool-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.tool-form {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
}

.tool-form header,
.tool-form h2 {
  display: flex;
  align-items: center;
}

.tool-form header {
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.tool-form h2 {
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
  font-size: 16px;
}

.tool-form h2 span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-secondary);
  font-size: 11px;
}

.tool-form header em {
  min-height: 20px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-accent);
  font-size: 11px;
  font-style: normal;
}

.tool-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
}

.tool-meta-grid span {
  display: grid;
  gap: 4px;
  min-height: 48px;
  overflow: hidden;
  padding: 8px;
  border-right: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
}

.tool-meta-grid strong {
  color: var(--text-muted);
  font-weight: 600;
}

.tool-config-table {
  min-width: 0;
}

.tool-summary-stack {
  display: grid;
  align-content: start;
  gap: 8px;
}

.tool-summary-stack .settings-panel {
  padding: 10px 12px;
}

.tool-summary-stack .settings-kv {
  gap: 6px;
}

.tool-owner-actions {
  display: grid;
  gap: 8px;
}

.tool-disabled-actions {
  display: grid;
  gap: 7px;
}

.tool-disabled-actions button {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 42px;
  padding: 7px;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-primary);
  cursor: not-allowed;
  opacity: 0.68;
  text-align: left;
}

.tool-disabled-actions span {
  display: grid;
  gap: 2px;
}

.tool-disabled-actions small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.tool-summary-stack :deep(th),
.tool-summary-stack :deep(td),
.tool-config-table :deep(th),
.tool-config-table :deep(td),
.tool-support-grid :deep(th),
.tool-support-grid :deep(td) {
  padding-block: 4px;
  font-size: 10.5px;
}

.tool-support-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.runs-panel,
.overlay-panel {
  grid-column: span 2;
}

.coverage-panel {
  grid-column: span 3;
}

.settings-panel-heading button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  cursor: pointer;
}

.settings-panel-heading button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.coverage-panel h3 {
  display: inline-flex;
  align-items: center;
  gap: 5px;
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
