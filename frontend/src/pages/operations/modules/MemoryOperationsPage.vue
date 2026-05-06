<script setup lang="ts">
import {
  Activity,
  Database,
  FileText,
  Gauge,
  Layers,
  RefreshCcw,
  Search,
  X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, type Component } from "vue";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime, formatRawKeyLabel } from "@/shared/i18n/formatters";
import type {
  OperationsMemoryFileDetail,
  OperationsMemoryReadModel,
  OperationsTab,
  UiChartSection,
  UiKeyValueItem,
  UiMetricCard,
  UiTableRow,
  UiTableSection,
  UiTone,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { loadMemoryOperations, writeLongTermMemory } from "../api";

interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

type DataTableRow = UiTableRow | Record<string, unknown>;

const { t } = useI18n();
const metricIconById: Record<string, Component> = {
  health: Gauge,
  memory_stores: Database,
  source_documents: FileText,
  indexed_files: Layers,
  retrieval_hits: Search,
  watch_failures: Activity,
};
const fallbackTabs: OperationsTab[] = [
  { id: "files", label: "Source Files" },
  { id: "stores", label: "Memory Stores" },
  { id: "context", label: "Context Resolution" },
  { id: "index", label: "Index Jobs" },
  { id: "sync", label: "Index Sync Activity" },
  { id: "retrieval", label: "Retrieval Trace" },
  { id: "writes", label: "Write / Flush" },
  { id: "usage", label: "Memory Usage" },
  { id: "scan", label: "Source Scan Status" },
  { id: "events", label: "Retrieval Logs" },
];
const knownTabIds = new Set(fallbackTabs.map((tab) => tab.id));
const selectableTabs = new Set(["files"]);
const memoryTextKeys: Record<string, string> = {
  "Memory": "operations.memory.title",
  "观察 file-backed memory 空间、记忆文件、索引同步、检索与写入事件的运维视图。": "operations.memory.subtitle",
  "观察文件存储记忆空间、记忆文件、索引同步、检索与写入事件的运维视图。": "operations.memory.subtitle",
  "Memory operator": "operations.memory.role.operator",
  "Overall Health": "operations.memory.metric.health",
  "Memory Stores": "operations.memory.metric.stores",
  "Source Documents": "operations.memory.metric.sources",
  "Indexed Files": "operations.memory.metric.indexed",
  "Retrieval Hits": "operations.memory.metric.retrievalHits",
  "Watch Failures": "operations.memory.metric.watchFailures",
  "Source Files": "operations.memory.tab.files",
  "Context Resolution": "operations.memory.tab.context",
  "Index Jobs": "operations.memory.tab.index",
  "Index Sync Activity": "operations.memory.tab.sync",
  "Retrieval Trace": "operations.memory.tab.retrieval",
  "Write / Flush": "operations.memory.tab.writes",
  "Memory Usage": "operations.memory.tab.usage",
  "Source Scan Status": "operations.memory.tab.scan",
  "Retrieval Logs": "operations.memory.tab.events",
  "Recent Retrieval Logs": "operations.memory.section.retrievalLogs",
  "Memory Events": "operations.memory.section.memoryEvents",
  "Index Health": "operations.memory.section.indexHealth",
  "Retrieval Backend Mix": "operations.memory.section.backendMix",
  "Current Retrieval Trace": "operations.memory.section.currentTrace",
  "Ready": "text.ready",
  "Resolved": "status.resolved",
  "Resolve Failed": "operations.memory.status.resolveFailed",
  "Started": "status.started",
  "Succeeded": "status.success",
  "Failed": "status.failed",
  "Dirty": "operations.memory.status.dirty",
  "Missing Index": "operations.memory.status.missingIndex",
  "No Context": "operations.memory.status.noContext",
  "File Only": "operations.memory.status.fileOnly",
  "Long Term": "operations.memory.kind.longTerm",
  "Daily": "operations.memory.kind.daily",
  "Archive": "operations.memory.kind.archive",
  "Agent": "common.agent",
  "Kind": "table.kind",
  "Type": "table.type",
  "Watcher": "table.watcher",
  "Last scanned": "table.lastScanned",
  "Last Scanned": "table.lastScanned",
  "Next scan": "table.nextScan",
  "Next Scan": "table.nextScan",
  "Not Configured": "operations.memory.status.notConfigured",
  "directory": "operations.memory.source.directory",
  "Hits": "operations.memory.segment.hits",
  "Misses": "operations.memory.segment.misses",
  "Hybrid": "operations.memory.backend.hybrid",
  "hybrid": "operations.memory.backend.hybrid",
  "No memory files.": "operations.memory.empty.files",
  "No memory stores.": "operations.memory.empty.stores",
  "No memory context resolution events.": "operations.memory.empty.context",
  "No index state.": "operations.memory.empty.index",
  "No memory index sync activity.": "operations.memory.empty.sync",
  "No memory usage.": "operations.memory.empty.usage",
  "No memory retrieval events.": "operations.memory.empty.retrievalEvents",
  "No memory write or flush events.": "operations.memory.empty.writeEvents",
  "No source scan state.": "operations.memory.empty.scan",
  "Set a search query to run retrieval trace.": "operations.memory.empty.tracePrompt",
  "No retrieval hits.": "operations.memory.empty.traceEmpty",
  "No related events.": "operations.memory.empty.relatedEvents",
  "No records.": "table.noRecords",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "Error": "text.error",
  "healthy": "text.healthy",
  "warning": "text.warning",
  "error": "text.error",
};

const page = ref<OperationsMemoryReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedFileId = ref<string | null>(null);
const queryInput = ref("");
const submittedSearch = ref("");
const kindFilter = ref("all");
const agentFilter = ref("");
const refreshTimer = ref<number | null>(null);
const writeAgentId = ref("");
const writeContent = ref("");
const writeComposerOpen = ref(false);
const actionBusy = ref<"write" | null>(null);
const actionNotice = ref<string | null>(null);

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "files";
  return knownTabIds.has(candidate) ? candidate : "files";
});
const mainTable = computed(() => {
  if (activeTab.value === "stores") return page.value?.memory_stores ?? emptyTable("memory_stores", "Memory Stores");
  if (activeTab.value === "context") return page.value?.context_resolution ?? emptyTable("context_resolution", "Context Resolution");
  if (activeTab.value === "index") return page.value?.index_jobs ?? emptyTable("index_jobs", "Index Jobs");
  if (activeTab.value === "sync") return page.value?.index_sync_activity ?? emptyTable("index_sync_activity", "Index Sync Activity");
  if (activeTab.value === "retrieval") return page.value?.retrieval_trace ?? emptyTable("retrieval_trace", "Retrieval Trace");
  if (activeTab.value === "writes") return page.value?.write_flush ?? emptyTable("write_flush", "Write / Flush");
  if (activeTab.value === "usage") return page.value?.memory_usage ?? emptyTable("memory_usage", "Memory Usage");
  if (activeTab.value === "scan") return page.value?.source_scan_status ?? emptyTable("source_scan_status", "Source Scan Status");
  if (activeTab.value === "events") return page.value?.recent_retrieval_logs ?? emptyTable("recent_retrieval_logs", "Recent Retrieval Logs");
  return page.value?.source_files ?? emptyTable("source_files", "Source Files");
});
const filteredMainRows = computed(() => {
  const rows = mainTable.value.rows;
  const needle = queryInput.value.trim().toLowerCase();
  if (!needle || submittedSearch.value === needle) return rows;
  return rows.filter((row) => {
    const values = isUiTableRow(row) ? Object.values(row.cells) : Object.values(row);
    return values.some((value) => cellValueText(value).toLowerCase().includes(needle));
  });
});
const indexHealth = computed(() => page.value?.index_health ?? emptyChart("index_health", "Index Health", "donut"));
const retrievalPerformance = computed(() => page.value?.retrieval_performance ?? emptyChart("retrieval_performance", "Retrieval Backend Mix", "donut"));
const sourceScan = computed(() => page.value?.source_scan_status ?? emptyTable("source_scan_status", "Source Scan Status"));
const memoryUsage = computed(() => page.value?.memory_usage ?? emptyTable("memory_usage", "Memory Usage"));
const recentRetrievalLogs = computed(() => page.value?.recent_retrieval_logs ?? emptyTable("recent_retrieval_logs", "Recent Retrieval Logs"));
const writeFlush = computed(() => page.value?.write_flush ?? emptyTable("write_flush", "Write / Flush"));
const indexSegments = computed(() => chartSegments(indexHealth.value));
const retrievalSegments = computed(() => chartSegments(retrievalPerformance.value));
const sourceScanPreviewRows = computed(() => sourceScan.value.rows.slice(0, 2).map((row) => ({
  id: row.id,
  title: scanCellText(row, ["source", "path", "root", "file"]) || row.id,
  status: scanCellText(row, ["status", "state", "health"]) || "-",
  tone: row.tone ?? "neutral",
  fields: [
    scanPreviewField(row, ["agent", "agent_id"], "Agent"),
    scanPreviewField(row, ["kind", "type"], "Kind"),
    scanPreviewField(row, ["watcher", "watch"], "Watcher"),
    scanPreviewField(row, ["last_scanned", "last_scan", "scanned_at"], "Last scanned"),
    scanPreviewField(row, ["next_scan", "next_scanned", "next_scan_at"], "Next scan"),
  ].filter((item) => item.value && item.value !== "-"),
})));
const sourceScanPreviewOverflow = computed(() => Math.max(0, sourceScan.value.rows.length - sourceScanPreviewRows.value.length));
const memoryAgentOptions = computed(() => {
  const values = new Set<string>();
  for (const row of page.value?.memory_stores.rows ?? []) {
    const agent = cellValueText(row.cells.agent);
    if (agent && agent !== "-") values.add(agent);
  }
  return [...values].sort();
});
const selectedWriteAgentId = computed(() => writeAgentId.value.trim() || defaultMemoryAgentId(page.value) || "");
const drawerDetail = computed<OperationsMemoryFileDetail | null>(() => {
  if (!selectedFileId.value) return null;
  return page.value?.file_details.find((item) => item.file_id === selectedFileId.value) ?? null;
});
const drawerOpen = computed(() => Boolean(drawerDetail.value));

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
  if (!selectableTabs.has(tabId)) selectedFileId.value = null;
}

function selectRow(row: DataTableRow) {
  if (!selectableTabs.has(activeTab.value)) return;
  selectedFileId.value = resolveFileId(row);
}

function resolveFileId(row: DataTableRow): string | null {
  const id = rowId(row);
  const details = page.value?.file_details ?? [];
  if (id && details.some((item) => item.file_id === id)) return id;
  const file = isUiTableRow(row) ? cellValueText(row.cells.file) : cellValueText(row.file);
  return details.find((item) => item.file_id.endsWith(`:${file}`))?.file_id ?? null;
}

function rowId(row: DataTableRow): string | null {
  return "id" in row && typeof row.id === "string" ? row.id : null;
}

function isUiTableRow(row: DataTableRow): row is UiTableRow {
  return typeof row === "object"
    && row !== null
    && "cells" in row
    && typeof (row as { cells?: unknown }).cells === "object"
    && (row as { cells?: unknown }).cells !== null;
}

function cellValueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object" && value !== null && "text" in value) {
    return String((value as { text: string }).text);
  }
  return String(value);
}

function scanCellText(row: UiTableRow, keys: string[]): string {
  for (const key of keys) {
    const value = row.cells[key];
    const text = cellValueText(value);
    if (text && text !== "-") return memoryText(text);
  }
  const normalizedKeys = new Set(keys.map(normalizedColumnKey));
  const matchedKey = Object.keys(row.cells).find((key) => normalizedKeys.has(normalizedColumnKey(key)));
  return matchedKey ? memoryText(cellValueText(row.cells[matchedKey])) : "";
}

function scanPreviewField(row: UiTableRow, keys: string[], fallback: string) {
  return {
    label: scanColumnLabel(keys, fallback),
    value: scanCellText(row, keys),
  };
}

function scanColumnLabel(keys: string[], fallback: string): string {
  const normalizedKeys = new Set(keys.map(normalizedColumnKey));
  const column = sourceScan.value.columns.find((item) => normalizedKeys.has(normalizedColumnKey(item.key)));
  return memoryText(column?.label ?? fallback);
}

function normalizedColumnKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

function chartSegments(section: UiChartSection): ChartSegmentView[] {
  const rawSegments = section.segments ?? [];
  const total = rawSegments.reduce((sum, segment) => sum + Number(segment.value || 0), 0);
  return rawSegments.map((segment) => ({
    id: segment.id,
    label: memoryText(segment.label),
    value: Number(segment.value || 0),
    tone: segment.tone,
    pct: total > 0 ? Math.round((Number(segment.value || 0) / total) * 100) : 0,
  }));
}

function metricIcon(metric: UiMetricCard, index: number): Component {
  return metricIconById[metric.id] ?? [Gauge, Database, FileText, Layers, Search, Activity][index % 6];
}

function metricLabel(metric: UiMetricCard) {
  return memoryText(metric.label);
}

function metricDelta(metric: UiMetricCard) {
  return memoryText(metric.delta ?? "");
}

function tabLabel(tab: OperationsTab) {
  return memoryText(tab.label);
}

function sectionTitle(section: UiTableSection | UiChartSection | { title: string }) {
  return memoryText(section.title);
}

function emptyState(section: UiTableSection) {
  return memoryText(section.empty_state ?? "No records.");
}

function detailItems(items: UiKeyValueItem[]) {
  return items.map((item) => ({
    ...item,
    label: memoryText(item.label),
    value: memoryText(item.value),
  }));
}

function detailPayload(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function defaultMemoryAgentId(memoryPage: OperationsMemoryReadModel | null): string | null {
  if (!memoryPage) return null;
  const action = memoryPage.actions.find((item) => item.id === "open_memory_overview");
  const query = action?.endpoint?.split("?")[1];
  if (query) {
    const agentId = new URLSearchParams(query).get("agent_id")?.trim();
    if (agentId) return agentId;
  }
  const firstStore = memoryPage.memory_stores.rows[0];
  return firstStore ? normalizedActionValue(cellValueText(firstStore.cells.agent)) : null;
}

function normalizedActionValue(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  if (!normalized || normalized === "-") return null;
  return normalized;
}

function memoryText(value: string | null | undefined): string {
  if (!value) return "";
  const agents = value.match(/^(\d+) agents$/);
  if (agents) return t("operations.memory.delta.agents", { count: agents[1] });
  const key = memoryTextKeys[value];
  if (key) return t(key);
  if (value === "selected memory files") return t("operations.memory.delta.selectedFiles");
  if (value === "files present in index store") return t("operations.memory.delta.indexStore");
  if (value === "current retrieval trace query") return t("operations.memory.delta.currentQuery");
  if (value === "watcher and observed memory errors") return t("operations.memory.delta.watchErrors");
  if (value === "Memory state is queryable") return t("operations.memory.delta.queryable");
  if (value === "Memory context needs attention") return t("operations.memory.delta.attention");
  if (value === "Memory service is not connected") return t("operations.memory.delta.disconnected");
  return formatRawKeyLabel(value);
}

function emptyTable(id: string, title: string): UiTableSection {
  return {
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  };
}

function emptyChart(id: string, title: string, kind: "bar" | "donut"): UiChartSection {
  return {
    id,
    title,
    kind,
    total: 0,
    segments: [],
  };
}

function submitSearch() {
  submittedSearch.value = queryInput.value.trim();
  selectedFileId.value = null;
  void refreshPage();
}

function resetSearch() {
  queryInput.value = "";
  submittedSearch.value = "";
  kindFilter.value = "all";
  selectedFileId.value = null;
  void refreshPage();
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadMemoryOperations(agentFilter.value.trim() || undefined, {
      kind: kindFilter.value,
      search: submittedSearch.value,
      limit: 80,
    });
    page.value = loaded.page;
    if (!writeAgentId.value.trim()) {
      writeAgentId.value = defaultMemoryAgentId(loaded.page) ?? "";
    }
    loadError.value = null;
    if (selectedFileId.value && !loaded.page.file_details.some((item) => item.file_id === selectedFileId.value)) {
      selectedFileId.value = null;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

function openWriteComposer() {
  writeAgentId.value = selectedWriteAgentId.value;
  writeComposerOpen.value = true;
}

function cancelWriteComposer() {
  writeComposerOpen.value = false;
  writeContent.value = "";
}

async function submitLongTermWrite() {
  if (typeof window === "undefined") return;
  const agentId = selectedWriteAgentId.value;
  const content = writeContent.value.trim();
  if (!agentId) {
    loadError.value = t("operations.memory.action.missingAgent");
    return;
  }
  if (!content) {
    loadError.value = t("operations.memory.action.missingContent");
    return;
  }
  if (!window.confirm(t("operations.memory.action.writeConfirm", { agentId }))) return;
  actionBusy.value = "write";
  actionNotice.value = null;
  loadError.value = null;
  try {
    const result = await writeLongTermMemory(agentId, content);
    actionNotice.value = t("operations.memory.action.writeNotice", {
      path: result.path,
      start: result.line_start,
      end: result.line_end,
    });
    writeContent.value = "";
    writeComposerOpen.value = false;
    selectedTabId.value = "writes";
    await refreshPage();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

onMounted(() => {
  void refreshPage();
  refreshTimer.value = window.setInterval(() => {
    void refreshPage();
  }, 30000);
});

onUnmounted(() => {
  if (refreshTimer.value !== null) {
    window.clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
});
</script>

<template>
  <main class="operations-module-console memory-console scroll-area" :class="{ 'has-drawer': drawerOpen }">
    <header class="memory-header">
      <div>
        <h2>{{ memoryText(page?.title ?? "Memory") }} <span>{{ page?.health ? memoryText(page.health) : "-" }}</span></h2>
        <p>{{ memoryText(page?.subtitle ?? "观察文件存储记忆空间、记忆文件、索引同步、检索与写入事件的运维视图。") }}</p>
      </div>
      <div class="memory-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton class="role-badge" size="sm" variant="secondary">
          <Database :size="13" /> {{ t("operations.currentRoleLabel") }}: {{ memoryText(page?.role.label ?? "Memory operator") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="memory-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>
    <div v-if="actionNotice" class="memory-alert memory-alert--success">
      <StatusDot tone="success" />
      <span>{{ actionNotice }}</span>
    </div>

    <section class="memory-action-strip">
      <span>{{ t("operations.memory.action.stripLabel") }}</span>
      <label class="memory-agent-field">
        <span>{{ t("operations.memory.action.targetAgent") }}</span>
        <input
          v-model.trim="writeAgentId"
          list="memory-agent-options"
          :placeholder="t('operations.memory.action.agentPlaceholder')"
        />
      </label>
      <datalist id="memory-agent-options">
        <option v-for="agent in memoryAgentOptions" :key="agent" :value="agent" />
      </datalist>
      <UiButton
        size="sm"
        variant="secondary"
        :disabled="loading || actionBusy !== null"
        @click="openWriteComposer"
      >
        <FileText :size="13" /> {{ t("operations.memory.action.writeLongTerm") }}
      </UiButton>
    </section>

    <section v-if="writeComposerOpen" class="memory-write-composer">
      <textarea
        v-model="writeContent"
        :disabled="actionBusy !== null"
        :placeholder="t('operations.memory.action.contentPlaceholder')"
      />
      <div class="memory-write-composer__footer">
        <span>{{ t("operations.memory.action.targetAgent") }}: <strong>{{ selectedWriteAgentId || "-" }}</strong></span>
        <div>
          <UiButton size="sm" variant="ghost" :disabled="actionBusy !== null" @click="cancelWriteComposer">
            {{ t("operations.memory.action.cancel") }}
          </UiButton>
          <UiButton size="sm" variant="secondary" :disabled="loading || actionBusy !== null" @click="submitLongTermWrite">
            <RefreshCcw :class="{ 'motion-spin': actionBusy === 'write' }" :size="13" />
            {{ t("operations.memory.action.submitWrite") }}
          </UiButton>
        </div>
      </div>
    </section>

    <section class="memory-metrics">
      <article v-for="(metric, index) in displayMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
        <span class="metric-icon"><component :is="metricIcon(metric, index)" :size="21" /></span>
        <span class="metric-copy">
          <em>{{ metricLabel(metric) }}</em>
          <strong>{{ memoryText(metric.value) }}</strong>
          <small>{{ metricDelta(metric) }}</small>
        </span>
      </article>
    </section>

    <section class="memory-status-strip">
      <article class="index-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(indexHealth) }}</h3>
        </div>
        <div class="chart-card-body">
          <div class="donut-visual">
            <strong>{{ indexHealth.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl class="segment-list">
            <div v-for="segment in indexSegments.slice(0, 5)" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }} <span>{{ segment.pct }}%</span></dd>
            </div>
          </dl>
        </div>
        <p v-if="!indexSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="backend-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(retrievalPerformance) }}</h3>
        </div>
        <dl class="bar-list">
          <div v-for="segment in retrievalSegments.slice(0, 6)" :key="segment.id">
            <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
            <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
          </div>
        </dl>
        <p v-if="!retrievalSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="scan-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(sourceScan) }}</h3>
          <a href="/operations/memory?tab=scan" @click.prevent="selectTab('scan')">{{ t("common.viewAll") }}</a>
        </div>
        <div v-if="sourceScanPreviewRows.length" class="scan-preview-list">
          <button
            v-for="row in sourceScanPreviewRows"
            :key="row.id"
            type="button"
            class="scan-preview-row"
            @click="selectTab('scan')"
          >
            <span class="scan-preview-main">
              <strong :title="row.title">{{ row.title }}</strong>
              <small>
                <span v-for="field in row.fields" :key="field.label">{{ field.label }}: {{ field.value }}</span>
              </small>
            </span>
            <span :class="`scan-preview-status scan-preview-status--${row.tone}`">{{ memoryText(row.status) }}</span>
          </button>
          <p v-if="sourceScanPreviewOverflow" class="scan-preview-more">+{{ sourceScanPreviewOverflow }} {{ t("common.more") }}</p>
        </div>
        <p v-else class="panel-empty">{{ emptyState(sourceScan) }}</p>
      </article>
    </section>

    <nav class="memory-tabs">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: tab.id === activeTab }" type="button" @click="selectTab(tab.id)">
        {{ tabLabel(tab) }}<span v-if="tab.count != null">{{ tab.count }}</span>
      </button>
    </nav>

    <section class="memory-main-grid">
      <article class="memory-table-panel">
        <div class="panel-heading panel-heading--table">
          <h3>{{ sectionTitle(mainTable) }} <span>{{ mainTable.total ?? mainTable.rows.length }}</span></h3>
          <form class="table-controls" @submit.prevent="submitSearch">
            <label class="table-search">
              <Search :size="13" />
              <input v-model.trim="queryInput" type="search" :placeholder="t('operations.memory.searchPlaceholder')" />
            </label>
            <label class="kind-filter">
              <span>{{ t("table.kind") }}</span>
              <select v-model="kindFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option value="long_term">{{ t("operations.memory.kind.longTerm") }}</option>
                <option value="daily">{{ t("operations.memory.kind.daily") }}</option>
                <option value="archive">{{ t("operations.memory.kind.archive") }}</option>
              </select>
            </label>
            <UiButton size="sm" variant="secondary" type="submit" :disabled="loading">
              <Search :size="13" /> {{ t("common.searchAction") }}
            </UiButton>
            <UiButton size="sm" variant="ghost" type="button" :disabled="loading" @click="resetSearch">
              {{ t("common.reset") }}
            </UiButton>
          </form>
        </div>
        <DataTable
          v-if="filteredMainRows.length"
          :columns="mainTable.columns"
          :rows="filteredMainRows"
          section-id="memory-main-table"
          :page-size="10"
          :clickable-rows="selectableTabs.has(activeTab)"
          @row-click="selectRow"
        />
        <p v-else class="table-empty">{{ emptyState(mainTable) }}</p>
      </article>

      <aside class="memory-side-panel">
        <article class="usage-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(memoryUsage) }}</h3>
            <a href="/operations/memory?tab=usage" @click.prevent="selectTab('usage')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable :columns="memoryUsage.columns" :rows="memoryUsage.rows" section-id="memory-usage" :page-size="5" />
        </article>

        <article class="retrieval-events-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(recentRetrievalLogs) }}</h3>
            <a href="/operations/memory?tab=events" @click.prevent="selectTab('events')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable :columns="recentRetrievalLogs.columns" :rows="recentRetrievalLogs.rows" section-id="recent-retrieval-logs" :page-size="3" />
          <p v-if="!recentRetrievalLogs.rows.length" class="panel-empty">{{ emptyState(recentRetrievalLogs) }}</p>
        </article>

        <article class="write-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(writeFlush) }}</h3>
            <a href="/operations/memory?tab=writes" @click.prevent="selectTab('writes')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable :columns="writeFlush.columns" :rows="writeFlush.rows" section-id="write-flush" :page-size="4" />
          <p v-if="!writeFlush.rows.length" class="panel-empty">{{ emptyState(writeFlush) }}</p>
        </article>
      </aside>
    </section>

    <aside v-if="drawerDetail" class="detail-drawer">
      <header>
        <div>
          <span>{{ t("operations.memory.drawer.file") }}</span>
          <h3>{{ drawerDetail.title }}</h3>
          <p><StatusDot :tone="drawerDetail.tone" />{{ memoryText(drawerDetail.status) }}</p>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedFileId = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.memory.drawer.summary") }}</h4>
        <dl class="drawer-kv">
          <div v-for="item in detailItems(drawerDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.memory.drawer.excerpt") }}</h4>
        <pre class="excerpt">{{ drawerDetail.excerpt || t("operations.memory.empty.excerpt") }}</pre>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.memory.drawer.related") }}</h4>
        <DataTable :columns="drawerDetail.related.columns" :rows="drawerDetail.related.rows" section-id="memory-detail-events" :page-size="4" />
        <p v-if="!drawerDetail.related.rows.length" class="panel-empty">{{ emptyState(drawerDetail.related) }}</p>
      </section>

      <section class="drawer-section raw-section">
        <h4>{{ t("operations.memory.drawer.raw") }}</h4>
        <pre>{{ detailPayload(drawerDetail.raw_payload) }}</pre>
      </section>
    </aside>
  </main>
</template>

<style scoped>
.memory-console {
  position: relative;
  height: 100%;
  overflow: auto;
  padding: 8px 12px 12px;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
}

.memory-header,
.memory-header__ops,
.memory-metrics,
.panel-heading,
.memory-tabs,
.auto-toggle,
.metric,
.metric-copy,
.chart-card-body,
.segment-list div,
.bar-list div,
.table-controls,
.table-search,
.kind-filter,
.memory-action-strip,
.memory-agent-field,
.memory-write-composer__footer,
.memory-write-composer__footer > div,
.detail-drawer header,
.drawer-kv div {
  display: flex;
  align-items: center;
}

.memory-header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

h2,
h3,
h4,
p,
dl {
  margin: 0;
}

h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  line-height: 1.15;
}

h2 span {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10.5px;
}

h3 {
  font-size: 13px;
  line-height: 1.2;
}

h4 {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 750;
  text-transform: uppercase;
}

.memory-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.memory-header__ops span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.auto-toggle i {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--color-success);
}

.role-badge {
  color: var(--text-secondary);
}

.memory-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 36%, var(--border-subtle));
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-danger) 9%, var(--surface-panel));
  color: var(--text-secondary);
  font-size: 11px;
}

.memory-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 36%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 9%, var(--surface-panel));
}

.memory-action-strip {
  flex-wrap: wrap;
  gap: 6px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 4px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel) 86%, transparent);
  color: var(--text-muted);
  font-size: 11px;
}

.memory-action-strip > span {
  font-weight: 750;
}

.memory-agent-field {
  gap: 6px;
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
}

.memory-agent-field input {
  width: min(190px, 32vw);
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.memory-write-composer {
  display: grid;
  gap: 6px;
  margin-bottom: 6px;
  padding: 8px;
  border: 1px solid color-mix(in srgb, var(--color-accent) 28%, var(--border-subtle));
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 7%, var(--surface-panel));
}

.memory-write-composer textarea {
  min-height: 72px;
  resize: vertical;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  outline: 0;
  padding: 9px;
  background: var(--surface-raised);
  color: var(--text-primary);
  font: inherit;
  font-size: 12px;
  line-height: 1.45;
}

.memory-write-composer__footer {
  justify-content: space-between;
  gap: 12px;
  color: var(--text-muted);
  font-size: 11px;
}

.memory-write-composer__footer > div {
  justify-content: flex-end;
  gap: 8px;
}

.memory-write-composer__footer strong {
  color: var(--text-secondary);
}

.memory-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(112px, 1fr));
  gap: 6px;
}

.metric,
.memory-status-strip > article,
.memory-table-panel,
.memory-side-panel > article,
.detail-drawer {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
}

.metric {
  gap: 6px;
  height: 64px;
  min-height: 0;
  padding: 7px 9px;
  overflow: hidden;
}

.metric-icon {
  display: grid;
  flex: 0 0 28px;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--color-accent);
}

.metric-copy {
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
}

.metric em,
.metric small {
  overflow: hidden;
  max-width: 100%;
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric strong {
  font-size: 17px;
  line-height: 1;
}

.metric--success strong {
  color: var(--color-success);
}

.metric--warning strong {
  color: var(--color-warning);
}

.metric--danger strong {
  color: var(--color-danger);
}

.memory-status-strip {
  display: grid;
  grid-template-columns: minmax(250px, 0.82fr) minmax(260px, 0.88fr) minmax(410px, 1.3fr);
  gap: 6px;
  align-items: start;
  margin-top: 6px;
}

.memory-status-strip > article,
.memory-side-panel > article {
  min-width: 0;
  padding: 8px;
}

.memory-status-strip > article {
  min-height: 124px;
  overflow: visible;
}

.index-panel,
.backend-panel,
.scan-panel {
  min-height: 118px;
  overflow: visible;
}

.scan-preview-list {
  display: grid;
  gap: 6px;
}

.scan-preview-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-width: 0;
  padding: 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.scan-preview-main {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.scan-preview-main strong,
.scan-preview-main small,
.scan-preview-main small span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scan-preview-main strong {
  color: var(--text-secondary);
  font-size: 11.5px;
  font-weight: 750;
}

.scan-preview-main small {
  display: flex;
  gap: 8px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 10px;
}

.scan-preview-status {
  max-width: 84px;
  padding: 2px 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scan-preview-status--success {
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
  color: var(--color-success);
}

.scan-preview-status--warning {
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
  color: var(--color-warning);
}

.scan-preview-status--danger {
  background: color-mix(in srgb, var(--color-danger) 14%, transparent);
  color: var(--color-danger);
}

.scan-preview-more {
  margin: 0;
  color: var(--text-muted);
  font-size: 10px;
  text-align: right;
}

.panel-heading {
  justify-content: space-between;
  gap: 8px;
  min-height: 20px;
  margin-bottom: 5px;
}

.panel-heading a {
  color: var(--color-accent);
  font-size: 11px;
  font-weight: 650;
  text-decoration: none;
}

.panel-heading--table {
  align-items: flex-start;
  margin-bottom: 9px;
}

.panel-heading--table h3 span {
  margin-left: 6px;
  color: var(--text-muted);
  font-weight: 500;
}

.chart-card-body {
  gap: 9px;
  min-height: 76px;
}

.donut-visual {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 76px;
  height: 76px;
  border: 1px solid var(--border-default);
  border-radius: 999px;
  background: radial-gradient(circle, var(--surface-panel) 58%, var(--surface-raised) 59%);
}

.donut-visual strong {
  font-size: 20px;
}

.donut-visual span {
  margin-top: -28px;
  color: var(--text-muted);
  font-size: 10px;
}

.segment-list,
.bar-list {
  display: grid;
  gap: 8px;
  width: 100%;
}

.segment-list div,
.bar-list div {
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.segment-list dt,
.bar-list dt {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 11px;
}

.segment-list dd,
.bar-list dd {
  margin: 0;
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
}

.segment-list dd span {
  color: var(--text-muted);
  font-weight: 500;
}

.bar-list dd {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 96px;
  height: 16px;
}

.bar-list dd span {
  position: absolute;
  left: 0;
  z-index: 0;
  height: 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent) 36%, var(--surface-raised));
}

.bar-list dd {
  z-index: 1;
}

.panel-empty,
.table-empty {
  display: grid;
  place-items: center;
  flex: 1 1 auto;
  min-height: 54px;
  color: var(--text-muted);
  font-size: 11px;
  text-align: center;
}

.memory-tabs {
  gap: 6px;
  margin-top: 6px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.memory-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 0 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
  font-weight: 650;
  white-space: nowrap;
}

.memory-tabs .active {
  border-color: color-mix(in srgb, var(--color-accent) 42%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-accent) 11%, var(--surface-panel));
  color: var(--text-primary);
}

.memory-tabs span {
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10px;
}

.memory-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 6px;
  margin-top: 6px;
}

.memory-table-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: clamp(340px, calc(100dvh - var(--shell-topbar-height) - 450px), 460px);
  padding: 8px;
}

.memory-table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.memory-side-panel {
  display: grid;
  align-content: start;
  gap: 6px;
  min-width: 0;
}

.memory-side-panel > article {
  min-height: 136px;
}

.table-controls {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

.table-search,
.kind-filter {
  gap: 6px;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-muted);
}

.table-search {
  width: min(320px, 34vw);
  padding: 0 9px;
}

.table-search input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.kind-filter {
  padding: 0 8px;
  font-size: 11px;
}

.kind-filter select {
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.detail-drawer {
  position: fixed;
  top: 84px;
  right: 20px;
  bottom: 20px;
  z-index: 30;
  width: min(438px, calc(100vw - 36px));
  overflow: auto;
  padding: 14px;
  box-shadow: var(--shadow-floating);
}

.detail-drawer header {
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.detail-drawer header span {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 750;
  text-transform: uppercase;
}

.detail-drawer header h3 {
  margin-top: 3px;
  font-size: 16px;
}

.detail-drawer header p {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 11px;
}

.detail-drawer header button {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-muted);
  cursor: pointer;
}

.drawer-section {
  display: grid;
  gap: 8px;
  padding-top: 13px;
}

.drawer-kv {
  display: grid;
  gap: 7px;
}

.drawer-kv div {
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.drawer-kv dt {
  flex: 0 0 104px;
  color: var(--text-muted);
  font-size: 11px;
}

.drawer-kv dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 650;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.excerpt,
.raw-section pre {
  overflow: auto;
  max-height: 260px;
  margin: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
}

@media (max-width: 1180px) {
  .memory-metrics {
    grid-template-columns: repeat(3, minmax(140px, 1fr));
  }

  .memory-status-strip,
  .memory-main-grid {
    grid-template-columns: 1fr;
  }

  .memory-side-panel {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .memory-console {
    padding: 8px 10px 10px;
  }

  .memory-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .memory-header__ops {
    justify-content: flex-start;
  }

  .memory-metrics,
  .memory-status-strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .metric {
    flex: 0 0 156px;
  }

  .memory-status-strip > article {
    flex: 0 0 286px;
  }

  .memory-side-panel {
    grid-template-columns: 1fr;
  }

  .panel-heading--table {
    flex-direction: column;
    align-items: stretch;
  }

  .table-controls {
    justify-content: flex-start;
  }

  .table-search {
    width: 100%;
  }

  .memory-agent-field,
  .memory-agent-field input,
  .memory-write-composer__footer,
  .memory-write-composer__footer > div {
    width: 100%;
  }

  .memory-write-composer__footer {
    align-items: stretch;
    flex-direction: column;
  }

  .detail-drawer {
    top: 70px;
    right: 12px;
    bottom: 12px;
  }
}
</style>
