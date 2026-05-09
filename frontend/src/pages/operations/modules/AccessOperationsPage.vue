<script setup lang="ts">
import {
  Database,
  GitBranch,
  HeartPulse,
  KeyRound,
  RefreshCcw,
  Search,
  Settings,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, type Component } from "vue";
import { useRouter } from "vue-router";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime, formatRawKeyLabel } from "@/shared/i18n/formatters";
import type {
  OperationsAccessReadModel,
  OperationsAccessTargetDetail,
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
import { loadAccessOperations } from "../api";
import { useOperationsProjectionRefresh } from "../useOperationsProjectionRefresh";

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
  health: HeartPulse,
  access_assets: KeyRound,
  missing_access: ShieldAlert,
  setup_available: Settings,
  usage: GitBranch,
  failed_auth: Database,
};
const fallbackTabs: OperationsTab[] = [
  { id: "targets", label: "Access Targets" },
  { id: "missing", label: "Missing Access" },
  { id: "auth_status", label: "Authentication Status" },
  { id: "usage", label: "Access Usage" },
  { id: "setup", label: "Setup Flows" },
  { id: "events", label: "Access Events" },
  { id: "fallbacks", label: "Fallback Problems" },
];
const knownTabIds = new Set(fallbackTabs.map((tab) => tab.id));
const selectableTabs = new Set(["targets", "missing", "auth_status", "usage", "setup", "fallbacks"]);
const accessTextKeys: Record<string, string> = {
  "Access": "operations.access.title",
  "观察凭证绑定、外部访问要求、访问缺口、setup flow 与访问相关事件的运维视图。": "operations.access.subtitle",
  "Access operator": "operations.access.role.operator",
  "Overall Health": "operations.access.metric.health",
  "Access Assets": "operations.access.metric.assets",
  "Missing Access": "operations.access.metric.missing",
  "Setup Available": "operations.access.metric.setup",
  "Consumers": "operations.access.metric.usage",
  "Failed Auth": "operations.access.metric.failedAuth",
  "Access Targets": "operations.access.tab.targets",
  "Authentication Status": "operations.access.tab.authStatus",
  "Access Usage": "operations.access.tab.usage",
  "Setup Flows": "operations.access.tab.setup",
  "Access Events": "operations.access.tab.events",
  "Recent Access Events": "operations.access.tab.events",
  "Fallback Problems": "operations.access.tab.fallbacks",
  "Fallback / Resolver Problems": "operations.access.tab.fallbacks",
  "Credential Health": "operations.access.section.credentialHealth",
  "Credentials by Kind": "operations.access.section.credentialsByKind",
  "Access Readiness Share": "operations.access.section.readinessShare",
  "Provider Auth / Access Blocked": "operations.access.section.providerBlocked",
  "Asset": "table.asset",
  "Kind": "table.kind",
  "Status": "table.status",
  "Usage Count": "operations.access.kv.usageCount",
  "Requirements": "table.requirements",
  "Reason": "table.reason",
  "Yes": "common.yes",
  "No": "common.no",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "Error": "text.error",
  "healthy": "text.healthy",
  "warning": "text.warning",
  "error": "text.error",
  "Ready": "text.ready",
  "Blocked": "text.blocked",
  "ready": "text.ready",
  "blocked": "text.blocked",
  "Setup Needed": "text.setupNeeded",
  "setup_needed": "text.setupNeeded",
  "Waiting User": "text.waitingUser",
  "waiting_user": "text.waitingUser",
  "Unsupported": "text.unsupported",
  "unsupported": "text.unsupported",
  "Expired": "text.expired",
  "expired": "text.expired",
  "Env": "text.env",
  "env": "text.env",
  "File Credential": "text.fileCredential",
  "file_credential": "text.fileCredential",
  "Codex Auth JSON": "text.codexAuthJson",
  "codex_auth_json": "text.codexAuthJson",
  "Inline Credential": "text.inlineCredential",
  "inline_credential": "text.inlineCredential",
  "Credential Set": "text.credentialSet",
  "credential_set": "text.credentialSet",
  "Access Requirement": "text.accessRequirement",
  "access_requirement": "text.accessRequirement",
  "credential_binding": "text.credentialBinding",
  "llm_profile": "text.llmProfile",
  "tool": "text.tool",
  "channel": "text.channel",
  "Unknown": "status.unknown",
  "No missing access.": "operations.access.empty.noMissing",
  "No provider access blockers.": "operations.access.empty.noProviderBlockers",
  "No access usage records.": "operations.access.empty.noUsage",
  "No setup flows.": "operations.access.empty.noSetup",
  "No access events.": "operations.access.empty.noEvents",
  "No fallback problems.": "operations.access.empty.noFallbacks",
  "No check records.": "operations.access.empty.noChecks",
  "No usages.": "operations.access.empty.noUsages",
  "No setup flow.": "operations.access.empty.noSetupFlow",
  "No records.": "table.noRecords",
};

const page = ref<OperationsAccessReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedTargetId = ref<string | null>(null);
const queryInput = ref("");
const submittedSearch = ref("");
const statusFilter = ref("all");
const kindFilter = ref("all");
const usageTypeFilter = ref("all");
const refreshTimer = ref<number | null>(null);
const router = useRouter();

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "targets";
  return knownTabIds.has(candidate) ? candidate : "targets";
});
const mainTable = computed(() => {
  if (activeTab.value === "missing") return page.value?.missing_access ?? emptyTable("missing_access", "Missing Access");
  if (activeTab.value === "auth_status") return page.value?.authentication_status ?? emptyTable("authentication_status", "Authentication Status");
  if (activeTab.value === "usage") return page.value?.access_usage ?? emptyTable("access_usage", "Access Usage");
  if (activeTab.value === "setup") return page.value?.setup_flows ?? emptyTable("setup_flows", "Setup Flows");
  if (activeTab.value === "events") return page.value?.recent_access_events ?? emptyTable("recent_access_events", "Recent Access Events");
  if (activeTab.value === "fallbacks") return page.value?.fallback_problems ?? emptyTable("fallback_problems", "Fallback / Resolver Problems");
  return page.value?.access_targets ?? emptyTable("access_targets", "Access Targets");
});
const filteredMainRows = computed(() => {
  const rows = mainTable.value.rows;
  const needle = queryInput.value.trim().toLowerCase();
  if (!needle || submittedSearch.value.toLowerCase() === needle) return rows;
  return rows.filter((row) => {
    const values = isUiTableRow(row) ? Object.values(row.cells) : Object.values(row);
    return values.some((value) => cellValueText(value).toLowerCase().includes(needle));
  });
});
const kindOptions = computed(() => {
  const values = new Set<string>();
  for (const row of page.value?.access_targets.rows ?? []) {
    const kind = cellValueText(row.cells.kind);
    if (kind && kind !== "-") values.add(kind);
  }
  return [...values].sort();
});
const usageTypeOptions = computed(() => {
  const values = new Set<string>();
  for (const row of page.value?.access_usage.rows ?? []) {
    const usageType = cellValueText(row.cells.usage_type);
    if (usageType && usageType !== "-") values.add(usageType);
  }
  for (const detail of page.value?.target_details ?? []) {
    const raw = detail.raw_payload as { metadata?: { usage_types?: unknown } };
    const usageTypes = raw.metadata?.usage_types;
    if (Array.isArray(usageTypes)) {
      for (const item of usageTypes) {
        const value = cellValueText(item);
        if (value && value !== "-") values.add(value);
      }
    }
  }
  return [...values].sort();
});
const credentialHealth = computed(() => page.value?.credential_health ?? emptyChart("credential_health", "Credential Health", "donut"));
const credentialsByKind = computed(() => page.value?.credentials_by_kind ?? emptyChart("credentials_by_kind", "Credentials by Kind", "donut"));
const readinessShare = computed(() => page.value?.auth_success_rate ?? emptyChart("auth_success_rate", "Access Readiness Share", "donut"));
const providerBlocked = computed(() => page.value?.provider_auth_blocked ?? emptyTable("provider_auth_blocked", "Provider Auth / Access Blocked"));
const providerBlockedPreviewRows = computed(() => providerBlocked.value.rows.slice(0, 3));
const providerBlockedPreviewOverflow = computed(() => Math.max(
  (providerBlocked.value.total ?? providerBlocked.value.rows.length) - providerBlockedPreviewRows.value.length,
  0,
));
const setupFlows = computed(() => page.value?.setup_flows ?? emptyTable("setup_flows", "Setup Flows"));
const recentEvents = computed(() => page.value?.recent_access_events ?? emptyTable("recent_access_events", "Recent Access Events"));
const credentialSegments = computed(() => chartSegments(credentialHealth.value));
const kindSegments = computed(() => chartSegments(credentialsByKind.value));
const readinessSegments = computed(() => chartSegments(readinessShare.value));
const drawerDetail = computed<OperationsAccessTargetDetail | null>(() => {
  if (!selectedTargetId.value) return null;
  return page.value?.target_details.find((item) => item.target_id === selectedTargetId.value) ?? null;
});
const drawerOpen = computed(() => Boolean(drawerDetail.value));

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
  selectedTargetId.value = null;
}

function selectRow(row: DataTableRow) {
  if (!selectableTabs.has(activeTab.value)) return;
  selectedTargetId.value = resolveTargetId(row);
}

function openProviderBlocked(row: DataTableRow) {
  selectTab("missing");
  selectedTargetId.value = resolveTargetId(row);
}

function resolveTargetId(row: DataTableRow): string | null {
  const id = rowId(row);
  const details = page.value?.target_details ?? [];
  if (!id) return null;
  if (details.some((item) => item.target_id === id)) return id;
  const prefixMatch = details.find((item) => id.startsWith(`${item.target_id}:`));
  if (prefixMatch) return prefixMatch.target_id;
  const asset = isUiTableRow(row) ? cellValueText(row.cells.asset) : cellValueText(row.asset);
  return details.find((item) => item.title === asset)?.target_id ?? null;
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

function cellText(row: DataTableRow, key: string): string | null {
  if (isUiTableRow(row)) {
    return cellValueText(row.cells[key]);
  }
  const value = row[key];
  return value == null ? null : String(value);
}

function firstCellText(row: DataTableRow, keys: string[]): string {
  for (const key of keys) {
    const value = cellText(row, key);
    if (value && value !== "-") return value;
  }
  return "-";
}

function providerBlockedTitle(row: DataTableRow): string {
  const value = firstCellText(row, ["asset", "provider", "target", "requirement", "missing_access", "kind"]);
  return value !== "-" ? accessText(value) : rowId(row) ?? "-";
}

function providerBlockedMeta(row: DataTableRow): string {
  const kind = firstCellText(row, ["kind", "asset_type", "usage_type", "consumer"]);
  const reason = firstCellText(row, ["reason", "status", "missing_access", "requirements"]);
  return [kind, reason].filter((value) => value && value !== "-").map(accessText).join(" / ") || "-";
}

function providerBlockedStatus(row: DataTableRow): string {
  const value = firstCellText(row, ["status", "health", "state"]);
  return value !== "-" ? accessText(value) : accessText("Blocked");
}

function providerBlockedTone(row: DataTableRow): UiTone {
  const value = firstCellText(row, ["tone", "status", "health", "state"]).toLowerCase();
  if (/error|fail|blocked|expired|unsupported|missing/.test(value)) return "danger";
  if (/setup|waiting|warning/.test(value)) return "warning";
  if (/ready|healthy|ok/.test(value)) return "success";
  return "neutral";
}

function cellValueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object" && value !== null && "text" in value) {
    return String((value as { text: string }).text);
  }
  return String(value);
}

function chartSegments(section: UiChartSection): ChartSegmentView[] {
  const rawSegments = section.segments ?? [];
  const total = rawSegments.reduce((sum, segment) => sum + Number(segment.value || 0), 0);
  return rawSegments.map((segment) => ({
    id: segment.id,
    label: accessText(segment.label),
    value: Number(segment.value || 0),
    tone: segment.tone,
    pct: total > 0 ? Math.round((Number(segment.value || 0) / total) * 100) : 0,
  }));
}

function metricIcon(metric: UiMetricCard, index: number): Component {
  return metricIconById[metric.id] ?? [HeartPulse, KeyRound, ShieldAlert, Settings, GitBranch, Database][index % 6];
}

function metricLabel(metric: UiMetricCard) {
  return accessText(metric.label);
}

function metricDelta(metric: UiMetricCard) {
  return accessText(metric.delta ?? "");
}

function tabLabel(tab: OperationsTab) {
  return accessText(tab.label);
}

function sectionTitle(section: UiTableSection | UiChartSection | { title: string }) {
  return accessText(section.title);
}

function emptyState(section: UiTableSection) {
  return accessText(section.empty_state ?? "No records.");
}

function detailItems(items: UiKeyValueItem[]) {
  return items.map((item) => ({
    ...item,
    label: accessText(item.label),
    value: accessText(item.value),
  }));
}

function detailPayload(value: unknown): string {
  try {
    return JSON.stringify(redactAccessPayload(value ?? {}), null, 2);
  } catch {
    return String(value ?? "");
  }
}

function redactAccessPayload(value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => redactAccessPayload(item));
  if (value === null || typeof value !== "object") return value;

  const redacted: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    redacted[key] = isSensitiveAccessKey(key) ? "[redacted]" : redactAccessPayload(item);
  }
  return redacted;
}

function isSensitiveAccessKey(key: string): boolean {
  return /(^|_)(secret|token|password|api[_-]?key|private[_-]?key|source_ref|storage_key|credential_value)(_|$)/i.test(key);
}

function accessText(value: string | null | undefined): string {
  if (!value) return "";
  const readyTargets = value.match(/^(\d+) ready$/);
  if (readyTargets) return t("operations.access.delta.readyTargets", { count: readyTargets[1] });
  const key = accessTextKeys[value];
  if (key) return t(key);
  if (value === "blocked or missing targets") return t("operations.access.delta.blockedTargets");
  if (value === "targets with setup flow") return t("operations.access.delta.setupFlows");
  if (value === "declared LLM/tool/channel usages") return t("operations.access.delta.consumers");
  if (value === "observed access error events") return t("operations.access.delta.errorEvents");
  if (value === "Access inventory is ready") return t("operations.access.delta.readyInventory");
  if (value === "Access setup is required") return t("operations.access.delta.setupRequired");
  if (value === "Access service is not connected") return t("operations.access.delta.disconnected");
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
  selectedTargetId.value = null;
  void refreshPage();
}

function resetSearch() {
  queryInput.value = "";
  submittedSearch.value = "";
  statusFilter.value = "all";
  kindFilter.value = "all";
  usageTypeFilter.value = "all";
  selectedTargetId.value = null;
  void refreshPage();
}

function openAccessSettings() {
  void router.push("/settings/access-assets");
}

function openTrace() {
  void router.push("/trace");
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadAccessOperations({
      status: statusFilter.value,
      kind: kindFilter.value,
      usage_type: usageTypeFilter.value,
      search: submittedSearch.value,
      include_ready: true,
      include_disabled: false,
      limit: 80,
    });
    page.value = loaded.page;
    loadError.value = null;
    if (selectedTargetId.value && !loaded.page.target_details.some((item) => item.target_id === selectedTargetId.value)) {
      selectedTargetId.value = null;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

useOperationsProjectionRefresh("access", refreshPage);

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
  <main class="operations-module-console access-console scroll-area" :class="{ 'has-drawer': drawerOpen }">
    <header class="access-header">
      <div>
        <h2>{{ accessText(page?.title ?? "Access") }} <span>{{ page?.health ? accessText(page.health) : "-" }}</span></h2>
        <p>{{ accessText(page?.subtitle ?? "观察凭证绑定、外部访问要求、访问缺口、setup flow 与访问相关事件的运维视图。") }}</p>
      </div>
      <div class="access-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton class="role-badge" size="sm" variant="secondary">
          <ShieldCheck :size="13" /> {{ t("operations.currentRoleLabel") }}: {{ accessText(page?.role.label ?? "Access operator") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="access-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>

    <section class="access-action-strip">
      <div class="access-action-target">
        <span>{{ t("operations.access.boundary.label") }}</span>
        <strong>{{ t("operations.access.boundary.observeOnly") }}</strong>
      </div>
      <UiButton size="sm" variant="secondary" @click="openAccessSettings">
        <Settings :size="13" /> {{ t("operations.access.nav.openSettings") }}
      </UiButton>
      <UiButton size="sm" variant="secondary" @click="openTrace">
        <Database :size="13" /> {{ t("operations.access.nav.openTrace") }}
      </UiButton>
    </section>

    <section class="access-metrics">
      <article v-for="(metric, index) in displayMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
        <span class="metric-icon"><component :is="metricIcon(metric, index)" :size="22" /></span>
        <span class="metric-copy">
          <em>{{ metricLabel(metric) }}</em>
          <strong>{{ accessText(metric.value) }}</strong>
          <small>{{ metricDelta(metric) }}</small>
        </span>
      </article>
    </section>

    <section class="access-status-strip">
      <article class="health-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(credentialHealth) }}</h3>
        </div>
        <div class="chart-card-body">
          <div class="donut-visual">
            <strong>{{ credentialHealth.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl class="segment-list">
            <div v-for="segment in credentialSegments.slice(0, 5)" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }} <span>{{ segment.pct }}%</span></dd>
            </div>
          </dl>
        </div>
        <p v-if="!credentialSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="kind-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(credentialsByKind) }}</h3>
        </div>
        <dl class="bar-list">
          <div v-for="segment in kindSegments.slice(0, 6)" :key="segment.id">
            <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
            <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
          </div>
        </dl>
        <p v-if="!kindSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="blocked-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(providerBlocked) }}</h3>
          <a href="/operations/access?tab=missing" @click.prevent="selectTab('missing')">{{ t("common.viewAll") }}</a>
        </div>
        <div v-if="providerBlockedPreviewRows.length" class="status-preview-list">
          <button
            v-for="(row, index) in providerBlockedPreviewRows"
            :key="rowId(row) ?? `${providerBlockedTitle(row)}-${index}`"
            type="button"
            class="status-preview-row"
            @click="openProviderBlocked(row)"
          >
            <span class="status-preview-copy">
              <strong :title="providerBlockedTitle(row)">{{ providerBlockedTitle(row) }}</strong>
              <small :title="providerBlockedMeta(row)">{{ providerBlockedMeta(row) }}</small>
            </span>
            <span :class="`status-preview-pill status-preview-pill--${providerBlockedTone(row)}`">
              {{ providerBlockedStatus(row) }}
            </span>
          </button>
          <p v-if="providerBlockedPreviewOverflow" class="status-preview-more">+{{ providerBlockedPreviewOverflow }} {{ t("common.more") }}</p>
        </div>
        <p v-if="!providerBlocked.rows.length" class="panel-empty">{{ emptyState(providerBlocked) }}</p>
      </article>
    </section>

    <nav class="access-tabs">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: tab.id === activeTab }" type="button" @click="selectTab(tab.id)">
        {{ tabLabel(tab) }}<span v-if="tab.count != null">{{ tab.count }}</span>
      </button>
    </nav>

    <section class="access-main-grid">
      <article class="access-table-panel">
        <div class="panel-heading panel-heading--table">
          <h3>{{ sectionTitle(mainTable) }} <span>{{ mainTable.total ?? mainTable.rows.length }}</span></h3>
          <form class="table-controls" @submit.prevent="submitSearch">
            <label class="table-search">
              <Search :size="13" />
              <input v-model.trim="queryInput" type="search" :placeholder="t('operations.access.searchPlaceholder')" />
            </label>
            <label class="status-filter">
              <span>{{ t("table.status") }}</span>
              <select v-model="statusFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option value="ready">{{ t("text.ready") }}</option>
                <option value="blocked">{{ t("text.blocked") }}</option>
                <option value="setup_needed">{{ t("text.setupNeeded") }}</option>
                <option value="waiting_user">{{ t("text.waitingUser") }}</option>
                <option value="unsupported">{{ t("text.unsupported") }}</option>
                <option value="expired">{{ t("text.expired") }}</option>
              </select>
            </label>
            <label class="status-filter">
              <span>{{ t("table.kind") }}</span>
              <select v-model="kindFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="kind in kindOptions" :key="kind" :value="kind">
                  {{ accessText(kind) }}
                </option>
              </select>
            </label>
            <label class="status-filter">
              <span>{{ t("table.usageType") }}</span>
              <select v-model="usageTypeFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="usageType in usageTypeOptions" :key="usageType" :value="usageType">
                  {{ accessText(usageType) }}
                </option>
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
          section-id="access-main-table"
          :page-size="10"
          :clickable-rows="selectableTabs.has(activeTab)"
          @row-click="selectRow"
        />
        <p v-else class="table-empty">{{ emptyState(mainTable) }}</p>
      </article>

      <aside class="access-side-panel">
        <article class="readiness-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(readinessShare) }}</h3>
          </div>
          <div class="side-donut">
            <strong>{{ readinessShare.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl class="segment-list compact">
            <div v-for="segment in readinessSegments" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }}</dd>
            </div>
          </dl>
          <p v-if="!readinessSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
        </article>

        <article class="setup-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(setupFlows) }}</h3>
            <a href="/operations/access?tab=setup" @click.prevent="selectTab('setup')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable :columns="setupFlows.columns" :rows="setupFlows.rows" section-id="setup-flows" :page-size="4" :clickable-rows="true" @row-click="selectRow" />
          <p v-if="!setupFlows.rows.length" class="panel-empty">{{ emptyState(setupFlows) }}</p>
        </article>

        <article class="events-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(recentEvents) }}</h3>
            <a href="/operations/access?tab=events" @click.prevent="selectTab('events')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable :columns="recentEvents.columns" :rows="recentEvents.rows" section-id="recent-access-events" :page-size="4" />
          <p v-if="!recentEvents.rows.length" class="panel-empty">{{ emptyState(recentEvents) }}</p>
        </article>
      </aside>
    </section>

    <aside v-if="drawerDetail" class="detail-drawer">
      <header>
        <div>
          <span>{{ t("operations.access.drawer.target") }}</span>
          <h3>{{ drawerDetail.title }}</h3>
          <p><StatusDot :tone="drawerDetail.tone" />{{ accessText(drawerDetail.status) }}</p>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedTargetId = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.access.drawer.summary") }}</h4>
        <dl class="drawer-kv">
          <div v-for="item in detailItems(drawerDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.access.drawer.checks") }}</h4>
        <DataTable :columns="drawerDetail.checks.columns" :rows="drawerDetail.checks.rows" section-id="access-detail-checks" :page-size="5" />
        <p v-if="!drawerDetail.checks.rows.length" class="panel-empty">{{ emptyState(drawerDetail.checks) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.access.drawer.usages") }}</h4>
        <DataTable :columns="drawerDetail.usages.columns" :rows="drawerDetail.usages.rows" section-id="access-detail-usages" :page-size="5" />
        <p v-if="!drawerDetail.usages.rows.length" class="panel-empty">{{ emptyState(drawerDetail.usages) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.access.drawer.setup") }}</h4>
        <DataTable :columns="drawerDetail.setup.columns" :rows="drawerDetail.setup.rows" section-id="access-detail-setup" :page-size="5" />
        <p v-if="!drawerDetail.setup.rows.length" class="panel-empty">{{ emptyState(drawerDetail.setup) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.access.drawer.events") }}</h4>
        <DataTable :columns="drawerDetail.events.columns" :rows="drawerDetail.events.rows" section-id="access-detail-events" :page-size="4" />
        <p v-if="!drawerDetail.events.rows.length" class="panel-empty">{{ emptyState(drawerDetail.events) }}</p>
      </section>

      <section class="drawer-section raw-section">
        <h4>{{ t("operations.access.drawer.raw") }}</h4>
        <pre>{{ detailPayload(drawerDetail.raw_payload) }}</pre>
      </section>
    </aside>
  </main>
</template>

<style scoped>
.access-console {
  position: relative;
  height: 100%;
  overflow: auto;
  padding: 8px 12px 12px;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
}

.access-header,
.access-header__ops,
.access-metrics,
.panel-heading,
.access-tabs,
.access-action-strip,
.access-action-target,
.auto-toggle,
.table-controls,
.metric,
.metric-copy,
.chart-card-body,
.segment-list div,
.bar-list div,
.detail-drawer header,
.drawer-kv div {
  display: flex;
  align-items: center;
}

.access-header {
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

.access-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.access-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.access-header__ops span {
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

.access-alert {
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

.access-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 34%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 9%, var(--surface-panel));
}

.access-action-strip {
  flex-wrap: wrap;
  gap: 6px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 4px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.access-action-target {
  min-width: min(260px, 100%);
  gap: 8px;
  min-height: 30px;
  padding: 0 10px;
  border-right: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.access-action-target strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.access-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(112px, 1fr));
  gap: 6px;
}

.metric,
.access-status-strip > article,
.access-table-panel,
.access-side-panel > article,
.detail-drawer {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
}

.metric {
  gap: 6px;
  height: 68px;
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

.access-status-strip {
  display: grid;
  grid-template-columns: minmax(260px, 0.86fr) minmax(260px, 0.92fr) minmax(360px, 1.25fr);
  gap: 6px;
  align-items: start;
  margin-top: 6px;
}

.access-status-strip > article,
.access-side-panel > article {
  min-width: 0;
  padding: 8px;
}

.health-panel,
.kind-panel,
.blocked-panel {
  min-height: 118px;
  overflow: visible;
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

.status-preview-list {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.status-preview-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 27px;
  padding: 4px 6px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.status-preview-row:hover,
.status-preview-row:focus-visible {
  border-color: color-mix(in srgb, var(--color-accent) 42%, var(--border-subtle));
  outline: none;
}

.status-preview-copy {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.status-preview-copy strong,
.status-preview-copy small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-preview-copy strong {
  color: var(--text-primary);
  font-size: 11px;
  line-height: 1.12;
}

.status-preview-copy small {
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.1;
}

.status-preview-pill {
  max-width: 110px;
  padding: 2px 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-preview-pill--success {
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
  color: var(--color-success);
}

.status-preview-pill--warning {
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
  color: var(--color-warning);
}

.status-preview-pill--danger {
  background: color-mix(in srgb, var(--color-danger) 14%, transparent);
  color: var(--color-danger);
}

.status-preview-more {
  margin: 0;
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1;
  text-align: right;
}

.panel-heading--table {
  align-items: flex-start;
  margin-bottom: 9px;
}

.panel-heading--table h3 {
  flex: 0 0 auto;
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

.donut-visual,
.side-donut {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 76px;
  height: 76px;
  border: 1px solid var(--border-default);
  border-radius: 999px;
  background: radial-gradient(circle, var(--surface-panel) 58%, var(--surface-raised) 59%);
}

.side-donut {
  width: 108px;
  height: 108px;
  margin: 4px auto 10px;
}

.donut-visual strong,
.side-donut strong {
  color: var(--text-primary);
  font-size: 23px;
  line-height: 1;
}

.donut-visual span,
.side-donut span {
  color: var(--text-muted);
  font-size: 10px;
}

.segment-list,
.bar-list,
.drawer-kv {
  display: grid;
  gap: 7px;
}

.segment-list {
  min-width: 0;
  flex: 1;
}

.segment-list div,
.bar-list div,
.drawer-kv div {
  justify-content: space-between;
  gap: 10px;
}

.segment-list dt,
.bar-list dt {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 11px;
}

.segment-list dd,
.bar-list dd,
.drawer-kv dd {
  margin: 0;
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 750;
}

.segment-list dd span {
  color: var(--text-muted);
  font-weight: 500;
}

.segment-list.compact {
  padding-inline: 6px;
}

.bar-list dd {
  position: relative;
  display: grid;
  grid-template-columns: minmax(58px, 1fr) 28px;
  align-items: center;
  gap: 8px;
  min-width: 110px;
}

.bar-list dd span {
  display: block;
  height: 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent) 50%, var(--surface-raised));
}

.panel-empty {
  flex: 1 1 auto;
  display: grid;
  place-items: center;
  min-height: 54px;
  color: var(--text-muted);
  font-size: 11px;
}

.table-empty {
  flex: 1 1 auto;
  display: grid;
  min-height: 54px;
  place-items: center;
  color: var(--text-muted);
  font-size: 11px;
}

.access-tabs {
  gap: 6px;
  min-height: 29px;
  margin-top: 6px;
  padding: 0;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  border-radius: 0;
  background: transparent;
  overflow-x: auto;
  scrollbar-gutter: stable;
}

.access-tabs button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: max-content;
  height: 29px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}

.access-tabs button.active {
  border-color: var(--border-default);
  background: var(--surface-active);
  color: var(--text-primary);
}

.access-tabs span {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10px;
}

.access-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 6px;
  margin-top: 6px;
  align-items: start;
}

.access-table-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: clamp(340px, calc(100dvh - var(--shell-topbar-height) - 450px), 500px);
  padding: 8px;
}

.access-table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.access-side-panel {
  display: grid;
  gap: 6px;
}

.access-side-panel > article {
  min-height: 136px;
}

.events-panel,
.setup-panel {
  min-height: 196px;
}

.table-search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: min(260px, 42vw);
  min-height: 30px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-muted);
}

.table-controls {
  flex: 1;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
  min-width: 0;
}

.table-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  font-size: 11px;
}

.status-filter {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
}

.status-filter span {
  flex: 0 0 auto;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 650;
}

.status-filter select {
  max-width: 120px;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.detail-drawer {
  position: fixed;
  top: calc(var(--shell-topbar-height, 50px) + 16px);
  right: 20px;
  bottom: 20px;
  z-index: 30;
  width: min(460px, calc(100vw - 36px));
  overflow: auto;
  padding: 14px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 96%, var(--surface-page));
  box-shadow: var(--shadow-floating);
}

.detail-drawer header {
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.detail-drawer header span {
  color: var(--text-muted);
  font-size: 11px;
}

.detail-drawer header h3 {
  margin-top: 3px;
  overflow-wrap: anywhere;
  font-size: 15px;
}

.detail-drawer header p {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  color: var(--text-secondary);
  font-size: 11px;
}

.detail-drawer header button {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
}

.drawer-section {
  display: grid;
  gap: 8px;
  padding: 13px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.drawer-kv div {
  align-items: flex-start;
}

.drawer-kv dt {
  color: var(--text-muted);
  font-size: 11px;
}

.drawer-kv dd {
  max-width: 245px;
  overflow-wrap: anywhere;
  text-align: right;
}

.tone-success {
  color: var(--color-success);
}

.tone-warning {
  color: var(--color-warning);
}

.tone-danger {
  color: var(--color-danger);
}

.raw-section pre {
  max-height: 280px;
  overflow: auto;
  margin: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 10.5px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.motion-spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1180px) {
  .access-metrics {
    grid-template-columns: repeat(3, minmax(150px, 1fr));
  }

  .access-status-strip,
  .access-main-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .access-side-panel {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .detail-drawer {
    top: 70px;
    right: 12px;
    bottom: 12px;
    width: min(420px, calc(100vw - 24px));
  }

  .access-action-target {
    flex: 1 1 100%;
    border-right: 0;
  }
}

@media (max-width: 760px) {
  .access-console {
    padding: 8px 10px 10px;
  }

  .access-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .access-header__ops {
    justify-content: flex-start;
  }

  .access-metrics,
  .access-status-strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .metric {
    flex: 0 0 156px;
  }

  .access-status-strip > article {
    flex: 0 0 286px;
  }

  .access-side-panel {
    grid-template-columns: minmax(0, 1fr);
  }

  .chart-card-body {
    align-items: flex-start;
    flex-direction: column;
  }

  .access-table-panel {
    min-height: 420px;
  }

  .table-search {
    width: 100%;
  }

  .table-controls {
    justify-content: flex-start;
  }

  .status-filter {
    flex: 1 1 150px;
  }

  .panel-heading--table {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
