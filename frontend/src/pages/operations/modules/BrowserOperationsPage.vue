<script setup lang="ts">
import { Activity, Bug, Fingerprint, Globe2, PanelTop, RefreshCcw, Search, ServerCog } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime } from "@/shared/i18n/formatters";
import type {
  OperationsBrowserReadModel,
  OperationsTab,
  UiMetricCard,
  UiTableColumn,
  UiTableRow,
  UiTableSection,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { loadBrowserOperations } from "../api";
import { useOperationsProjectionRefresh } from "../useOperationsProjectionRefresh";

const { t } = useI18n();

const fallbackTabs: OperationsTab[] = [
  { id: "profiles", label: "Browser Profiles" },
  { id: "pools", label: "Profile Pools" },
  { id: "allocations", label: "Profile Allocations" },
  { id: "pages", label: "Page Observations" },
  { id: "daemon", label: "Browser Daemon Runtimes" },
  { id: "network", label: "Network Activity" },
  { id: "diagnostics", label: "Diagnostics" },
];
const knownTabIds = new Set(fallbackTabs.map((tab) => tab.id));
const fallbackMetrics: UiMetricCard[] = [
  { id: "health", label: "Overall Health", value: "-", delta: "-", tone: "neutral" },
  { id: "profiles", label: "Profiles", value: "-", delta: "-", tone: "neutral" },
  { id: "profile_pools", label: "Profile Pools", value: "-", delta: "-", tone: "neutral" },
  { id: "profile_allocations", label: "Profile Allocations", value: "-", delta: "-", tone: "neutral" },
  { id: "pages", label: "Page Observations", value: "-", delta: "-", tone: "neutral" },
  { id: "daemon_runtimes", label: "Daemon Runtimes", value: "-", delta: "-", tone: "neutral" },
  { id: "network_activity", label: "Network Activity", value: "-", delta: "-", tone: "neutral" },
  { id: "diagnostics", label: "Diagnostics", value: "-", delta: "-", tone: "neutral" },
];
const fallbackColumns: Record<string, UiTableColumn[]> = {
  profiles: [
    { key: "profile", label: "Profile" },
    { key: "driver", label: "Driver" },
    { key: "status", label: "Status" },
    { key: "endpoint", label: "CDP Endpoint" },
    { key: "host_generation", label: "Host Gen" },
    { key: "active_target", label: "Active Target" },
    { key: "pages", label: "Pages" },
    { key: "snapshot_generation", label: "Snapshot Gen" },
    { key: "proxy", label: "Proxy" },
    { key: "proxy_readiness", label: "Proxy Ready" },
    { key: "proxy_egress", label: "Egress" },
  ],
  profile_pools: [
    { key: "pool", label: "Pool" },
    { key: "status", label: "Status" },
    { key: "profiles", label: "Profiles" },
    { key: "ready_profiles", label: "Ready" },
    { key: "available_profiles", label: "Available" },
    { key: "active_allocations", label: "Active" },
    { key: "cooling", label: "Cooling" },
    { key: "recent_failures", label: "Failures" },
    { key: "strategy", label: "Strategy" },
    { key: "concurrency", label: "Concurrency" },
    { key: "ttl", label: "TTL" },
    { key: "cooldown", label: "Cooldown" },
    { key: "target_hosts", label: "Target Hosts" },
    { key: "missing", label: "Missing" },
  ],
  profile_allocations: [
    { key: "allocation", label: "Allocation" },
    { key: "pool", label: "Pool" },
    { key: "profile", label: "Profile" },
    { key: "consumer", label: "Consumer" },
    { key: "target_host", label: "Target Host" },
    { key: "age", label: "Age" },
    { key: "ttl", label: "TTL" },
    { key: "status", label: "Status" },
    { key: "release_reason", label: "Release Reason" },
  ],
  page_observations: [
    { key: "profile", label: "Profile" },
    { key: "target_id", label: "Target" },
    { key: "page_generation", label: "Page Gen" },
    { key: "reason", label: "Reason" },
    { key: "snapshot_generation", label: "Snapshot Gen" },
    { key: "ref_generation", label: "Ref Gen" },
    { key: "last_action", label: "Last Action" },
    { key: "refs", label: "Refs" },
    { key: "stale", label: "Stale" },
  ],
  daemon_runtimes: [
    { key: "service_key", label: "Service Key" },
    { key: "runtime", label: "Runtime" },
    { key: "status", label: "Status" },
    { key: "profile", label: "Profile" },
    { key: "endpoint", label: "Endpoint" },
    { key: "pid", label: "PID" },
    { key: "manifest", label: "Manifest" },
    { key: "required", label: "Requires" },
    { key: "proxy_egress", label: "Egress" },
  ],
  network_activity: [
    { key: "time", label: "Time" },
    { key: "event", label: "Event" },
    { key: "status", label: "Status" },
    { key: "profile", label: "Profile" },
    { key: "target_id", label: "Target" },
    { key: "capture", label: "Capture" },
    { key: "request", label: "Request" },
    { key: "method", label: "Method" },
    { key: "http_status", label: "HTTP" },
    { key: "resource", label: "Resource" },
    { key: "url", label: "URL" },
    { key: "summary", label: "Summary" },
  ],
  diagnostics: [
    { key: "time", label: "Time" },
    { key: "event", label: "Event" },
    { key: "kind", label: "Kind" },
    { key: "status", label: "Status" },
    { key: "profile", label: "Profile" },
    { key: "target_id", label: "Target" },
    { key: "issues", label: "Issues" },
    { key: "console", label: "Console" },
    { key: "errors", label: "Errors" },
    { key: "ready_state", label: "Ready" },
    { key: "trace", label: "Trace" },
    { key: "trace_size", label: "Trace Size" },
    { key: "changed", label: "Changed" },
    { key: "summary", label: "Summary" },
  ],
};
const metricIconById: Record<string, unknown> = {
  health: Globe2,
  profiles: Globe2,
  profile_pools: Fingerprint,
  profile_allocations: Fingerprint,
  pages: PanelTop,
  daemon_runtimes: ServerCog,
  network_activity: Activity,
  diagnostics: Bug,
};

const page = ref<OperationsBrowserReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const statusFilter = ref("all");
const profileFilter = ref("all");
const searchInput = ref("");
const submittedSearch = ref("");
const refreshTimer = ref<number | null>(null);

const metrics = computed(() => page.value?.metrics?.length ? page.value.metrics : fallbackMetrics);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceById = new Map((page.value?.tabs ?? []).map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "profiles";
  return knownTabIds.has(candidate) ? candidate : "profiles";
});
const profilesTable = computed(() => page.value?.profiles ?? emptyTable("profiles", "Browser Profiles"));
const poolsTable = computed(() => page.value?.profile_pools ?? emptyTable("profile_pools", "Profile Pools"));
const allocationsTable = computed(() => page.value?.profile_allocations ?? emptyTable("profile_allocations", "Profile Allocations"));
const pagesTable = computed(() => page.value?.page_observations ?? emptyTable("page_observations", "Page Observations"));
const daemonTable = computed(() => page.value?.daemon_runtimes ?? emptyTable("daemon_runtimes", "Browser Daemon Runtimes"));
const networkTable = computed(() => page.value?.network_activity ?? emptyTable("network_activity", "Browser Network Activity"));
const diagnosticsTable = computed(() => page.value?.diagnostics ?? emptyTable("diagnostics", "Browser Diagnostics"));
const mainTable = computed(() => {
  if (activeTab.value === "pools") return poolsTable.value;
  if (activeTab.value === "allocations") return allocationsTable.value;
  if (activeTab.value === "pages") return pagesTable.value;
  if (activeTab.value === "daemon") return daemonTable.value;
  if (activeTab.value === "network") return networkTable.value;
  if (activeTab.value === "diagnostics") return diagnosticsTable.value;
  return profilesTable.value;
});
const filteredMainRows = computed(() => mainTable.value.rows.filter((row) => rowMatchesFilters(row)));
const profileOptions = computed(() => {
  const names = new Set<string>();
  for (const row of [...profilesTable.value.rows, ...allocationsTable.value.rows]) {
    const name = cellText(row, "profile");
    if (name && name !== "-") names.add(name);
  }
  return [...names].sort((left, right) => left.localeCompare(right));
});
const activeMetric = computed(() => metricById("profiles")?.value ?? "0");
const stalePageMetric = computed(() => localize(metricById("pages")?.delta ?? "0 stale"));
const daemonMetric = computed(() => localize(metricById("daemon_runtimes")?.delta ?? "0 ready"));

useOperationsProjectionRefresh("browser", () => {
  void loadPage();
});

onMounted(() => {
  void loadPage();
  refreshTimer.value = window.setInterval(() => {
    void loadPage();
  }, 15_000);
});

onUnmounted(() => {
  if (refreshTimer.value !== null) window.clearInterval(refreshTimer.value);
});

async function loadPage() {
  loading.value = true;
  loadError.value = null;
  try {
    const response = await loadBrowserOperations({
      limit: 120,
      offset: 0,
    });
    page.value = response.page;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

function submitFilters() {
  submittedSearch.value = searchInput.value.trim();
  void loadPage();
}

function resetFilters() {
  statusFilter.value = "all";
  profileFilter.value = "all";
  searchInput.value = "";
  submittedSearch.value = "";
  void loadPage();
}

function selectTab(tabId: string) {
  selectedTabId.value = knownTabIds.has(tabId) ? tabId : "profiles";
}

function metricById(id: string): UiMetricCard | null {
  return metrics.value.find((metric) => metric.id === id) ?? null;
}

function metricToneClass(metric: UiMetricCard) {
  return `browser-metric--${metric.tone ?? "neutral"}`;
}

function metricIcon(metric: UiMetricCard) {
  return metricIconById[metric.id] ?? Fingerprint;
}

function tableTitle(table: UiTableSection): string {
  return localize(table.title);
}

function emptyTable(id: string, title: string): UiTableSection {
  return {
    id,
    title,
    columns: fallbackColumns[id] ?? [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  };
}

function emptyState(table: UiTableSection): string {
  return localize(table.empty_state ?? "No records.");
}

function localize(value: string): string {
  const staleDelta = value.match(/^(\d+) stale$/);
  if (staleDelta) return t("operations.browser.delta.stale", { count: staleDelta[1] });
  const readyDelta = value.match(/^(\d+) ready$/);
  if (readyDelta) return t("operations.browser.delta.ready", { count: readyDelta[1] });
  const attachedDelta = value.match(/^(\d+) attached$/);
  if (attachedDelta) return t("operations.browser.delta.attached", { count: attachedDelta[1] });
  const activeDelta = value.match(/^(\d+) active$/);
  if (activeDelta) return t("operations.browser.delta.active", { count: activeDelta[1] });
  const failedDelta = value.match(/^(\d+) failed$/);
  if (failedDelta) return t("operations.browser.delta.failed", { count: failedDelta[1] });
  const warningsDelta = value.match(/^(\d+) warnings$/);
  if (warningsDelta) return t("operations.browser.delta.warnings", { count: warningsDelta[1] });
  const activeCoolingDelta = value.match(/^(\d+) active · (\d+) cooling$/);
  if (activeCoolingDelta) {
    return t("operations.browser.delta.activeCooling", {
      active: activeCoolingDelta[1],
      cooling: activeCoolingDelta[2],
    });
  }
  const activeFailedDelta = value.match(/^(\d+) active · (\d+) failed$/);
  if (activeFailedDelta) {
    return t("operations.browser.delta.activeFailed", {
      active: activeFailedDelta[1],
      failed: activeFailedDelta[2],
    });
  }
  const key = browserTextKeys[value];
  return key ? t(key) : value;
}

function cellText(row: UiTableRow, key: string): string {
  const value = row.cells[key];
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object" && "text" in value) return String(value.text || "-");
  return String(value);
}

function rowMatchesFilters(row: UiTableRow): boolean {
  const status = statusFilter.value.trim().toLowerCase();
  if (status !== "all") {
    const rowStatus = String(row.status ?? cellText(row, "status")).trim().toLowerCase();
    if (rowStatus !== status) return false;
  }
  const profile = profileFilter.value.trim().toLowerCase();
  if (profile !== "all" && cellText(row, "profile").trim().toLowerCase() !== profile) {
    return false;
  }
  const search = submittedSearch.value.trim().toLowerCase();
  if (!search) return true;
  return [
    row.id,
    String(row.status ?? ""),
    ...Object.values(row.cells).map((value) => {
      if (value === null || value === undefined) return "";
      if (typeof value === "object" && "text" in value) return String(value.text ?? "");
      return String(value);
    }),
  ].join(" ").toLowerCase().includes(search);
}

const browserTextKeys: Record<string, string> = {
  "Browser Runtime": "operations.browser.title",
  "Overall Health": "operations.browser.metric.health",
  "Profiles": "operations.browser.metric.profiles",
  "Profile Pools": "operations.browser.metric.profilePools",
  "Profile Allocations": "operations.browser.metric.profileAllocations",
  "Daemon Runtimes": "operations.browser.metric.daemonRuntimes",
  "Network Activity": "operations.browser.metric.networkActivity",
  "Diagnostics": "operations.browser.metric.diagnostics",
  "Browser Profiles": "operations.browser.section.profiles",
  "Browser Profile Pools": "operations.browser.section.profilePools",
  "Browser Profile Allocations": "operations.browser.section.profileAllocations",
  "Page Observations": "operations.browser.section.pages",
  "Browser Daemon Runtimes": "operations.browser.section.daemon",
  "Browser Network Activity": "operations.browser.section.network",
  "Browser Diagnostics": "operations.browser.section.diagnostics",
  "Pools": "operations.browser.tab.pools",
  "Allocations": "operations.browser.tab.allocations",
  "Pages": "operations.browser.tab.pages",
  "Daemon": "operations.browser.tab.daemon",
  "Network": "operations.browser.tab.network",
  "No browser profiles configured.": "operations.browser.empty.noProfiles",
  "No browser profile pools configured.": "operations.browser.empty.noProfilePools",
  "No browser profile allocations recorded.": "operations.browser.empty.noProfileAllocations",
  "No browser page observations yet.": "operations.browser.empty.noPages",
  "No browser daemon runtimes registered.": "operations.browser.empty.noDaemon",
  "No browser network activity observed.": "operations.browser.empty.noNetwork",
  "No browser diagnostics observed.": "operations.browser.empty.noDiagnostics",
  "No records.": "table.noRecords",
};
</script>

<template>
  <main class="browser-console operations-module-console">
    <header class="browser-header">
      <div>
        <p class="eyebrow">{{ t("operations.module.browser") }}</p>
        <h1>{{ t("operations.browser.title") }}</h1>
        <span>{{ t("operations.browser.subtitle") }}</span>
      </div>
      <div class="browser-header__status">
        <span>{{ t("common.lastUpdated") }}: {{ lastUpdatedLabel }}</span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="loadPage">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="browser-alert">
      {{ loadError }}
    </div>

    <div class="browser-metrics">
      <article
        v-for="metric in metrics"
        :key="metric.id"
        class="browser-metric"
        :class="metricToneClass(metric)"
      >
        <component :is="metricIcon(metric)" :size="17" />
        <div>
          <span>{{ localize(metric.label) }}</span>
          <strong>{{ metric.value }}</strong>
          <small>{{ localize(metric.delta ?? "") }}</small>
        </div>
      </article>
    </div>

    <div class="browser-status-strip">
      <article>
        <span>{{ t("operations.browser.kpi.profiles") }}</span>
        <strong>{{ activeMetric }}</strong>
      </article>
      <article>
        <span>{{ t("operations.browser.kpi.pages") }}</span>
        <strong>{{ stalePageMetric }}</strong>
      </article>
      <article>
        <span>{{ t("operations.browser.kpi.daemon") }}</span>
        <strong>{{ daemonMetric }}</strong>
      </article>
    </div>

    <div class="browser-main-grid">
      <article class="browser-panel browser-panel--main">
        <div class="browser-tabs">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            :class="{ active: activeTab === tab.id }"
            @click="selectTab(tab.id)"
          >
            {{ localize(tab.label) }}
            <span v-if="tab.count !== undefined">{{ tab.count }}</span>
          </button>
        </div>

        <form class="browser-filters" @submit.prevent="submitFilters">
          <label>
            <span>{{ t("table.status") }}</span>
            <select v-model="statusFilter" @change="submitFilters">
              <option value="all">{{ t("common.all") }}</option>
              <option value="attached">{{ t("operations.browser.status.attached") }}</option>
              <option value="stale">{{ t("operations.browser.status.stale") }}</option>
              <option value="failed">{{ t("status.failed") }}</option>
              <option value="degraded">{{ t("text.degraded") }}</option>
              <option value="ready">{{ t("text.ready") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("table.profile") }}</span>
            <select v-model="profileFilter" @change="submitFilters">
              <option value="all">{{ t("common.all") }}</option>
              <option v-for="profile in profileOptions" :key="profile" :value="profile">
                {{ profile }}
              </option>
            </select>
          </label>
          <label class="browser-filters__search">
            <span>{{ t("common.search") }}</span>
            <input v-model="searchInput" type="search" />
          </label>
          <UiButton size="sm" variant="secondary" type="submit" :disabled="loading">
            <Search :size="13" /> {{ t("common.searchAction") }}
          </UiButton>
          <UiButton size="sm" variant="ghost" type="button" :disabled="loading" @click="resetFilters">
            {{ t("common.reset") }}
          </UiButton>
        </form>

        <div class="browser-table-frame">
          <DataTable
            :columns="mainTable.columns"
            :rows="filteredMainRows"
            section-id="browser-main-table"
            :page-size="12"
          />
          <p v-if="!filteredMainRows.length" class="browser-empty">{{ emptyState(mainTable) }}</p>
        </div>
      </article>

      <aside class="browser-side-stack">
        <article class="browser-panel">
          <div class="panel-heading">
            <h3>{{ tableTitle(pagesTable) }}</h3>
            <button type="button" @click="selectTab('pages')">{{ t("common.viewAll") }}</button>
          </div>
          <div class="browser-table-frame compact">
            <DataTable
              :columns="pagesTable.columns"
              :rows="pagesTable.rows"
              section-id="browser-pages-side"
              :page-size="5"
            />
            <p v-if="!pagesTable.rows.length" class="browser-empty compact">{{ emptyState(pagesTable) }}</p>
          </div>
        </article>

        <article class="browser-panel">
          <div class="panel-heading">
            <h3>{{ tableTitle(daemonTable) }}</h3>
            <button type="button" @click="selectTab('daemon')">{{ t("common.viewAll") }}</button>
          </div>
          <div class="browser-table-frame compact">
            <DataTable
              :columns="daemonTable.columns"
              :rows="daemonTable.rows"
              section-id="browser-daemon-side"
              :page-size="5"
            />
            <p v-if="!daemonTable.rows.length" class="browser-empty compact">{{ emptyState(daemonTable) }}</p>
          </div>
        </article>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.browser-console {
  display: flex;
  min-height: calc(100vh - 56px);
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  color: var(--text-primary);
}

.browser-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.browser-header h1 {
  margin: 2px 0 3px;
  font-size: 24px;
  line-height: 1.1;
}

.browser-header span,
.browser-header__status {
  color: var(--text-secondary);
  font-size: 12px;
}

.eyebrow {
  margin: 0;
  color: var(--color-blue);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.browser-header__status {
  display: flex;
  align-items: center;
  gap: 10px;
}

.browser-alert {
  border: 1px solid rgba(248, 113, 113, 0.35);
  border-radius: 8px;
  padding: 8px 10px;
  background: rgba(127, 29, 29, 0.18);
  color: var(--color-danger);
  font-size: 12px;
}

.browser-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.browser-metric,
.browser-panel,
.browser-status-strip > article {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.64);
}

.browser-metric {
  display: flex;
  min-height: 68px;
  align-items: center;
  gap: 10px;
  padding: 10px;
}

.browser-metric svg {
  color: var(--color-blue);
}

.browser-metric span,
.browser-status-strip span {
  display: block;
  color: var(--text-secondary);
  font-size: 11px;
}

.browser-metric strong {
  display: block;
  margin-top: 3px;
  font-size: 18px;
}

.browser-metric small {
  display: block;
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
}

.browser-metric--success svg {
  color: var(--color-success);
}

.browser-metric--warning svg {
  color: var(--color-warning);
}

.browser-metric--danger svg {
  color: var(--color-danger);
}

.browser-status-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.browser-status-strip > article {
  padding: 10px 12px;
}

.browser-status-strip strong {
  display: block;
  margin-top: 2px;
  font-size: 15px;
}

.browser-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.38fr);
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.browser-panel {
  min-width: 0;
  padding: 12px;
}

.browser-panel--main {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 10px;
}

.browser-table-frame {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
}

.browser-table-frame.compact {
  flex: 1;
}

.browser-side-stack {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 12px;
  min-height: 0;
}

.browser-tabs,
.browser-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.browser-tabs button {
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 6px 8px;
  font-size: 13px;
}

.browser-tabs button.active {
  border-bottom-color: var(--color-blue);
  color: var(--text-primary);
}

.browser-tabs span {
  margin-left: 5px;
  color: var(--text-muted);
  font-size: 11px;
}

.browser-filters label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 11px;
}

.browser-filters select,
.browser-filters input {
  height: 30px;
  min-width: 124px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.8);
  color: var(--text-primary);
  padding: 0 9px;
}

.browser-filters__search {
  flex: 1;
  min-width: 220px;
}

.browser-filters__search input {
  width: 100%;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-heading h3 {
  margin: 0;
  font-size: 14px;
}

.panel-heading button {
  border: 0;
  background: transparent;
  color: var(--color-blue);
  cursor: pointer;
  font-size: 12px;
}

.browser-empty {
  display: grid;
  min-height: 220px;
  flex: 1;
  margin: 0;
  place-items: center;
  color: var(--text-muted);
  font-size: 12px;
}

.browser-empty.compact {
  min-height: 120px;
}

.browser-panel :deep(.data-table) {
  min-height: 0;
}

.browser-panel--main :deep(.data-table) {
  flex: 0 0 auto;
}

.browser-panel :deep(th),
.browser-panel :deep(td) {
  padding-top: 7px;
  padding-bottom: 7px;
}

.browser-panel :deep(.column-endpoint),
.browser-panel :deep(.column-service-key) {
  max-width: 220px;
}

@media (max-width: 1180px) {
  .browser-status-strip,
  .browser-main-grid {
    grid-template-columns: 1fr;
  }

  .browser-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .browser-side-stack {
    grid-template-rows: auto;
  }
}

@media (min-width: 1181px) and (max-width: 1440px) {
  .browser-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
