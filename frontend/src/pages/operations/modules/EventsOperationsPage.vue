<script setup lang="ts">
import {
  Activity,
  Bell,
  Database,
  GitBranch,
  HeartPulse,
  Layers,
  Radio,
  RefreshCcw,
  Search,
  ShieldAlert,
  X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime } from "@/shared/i18n/formatters";
import type {
  OperationsEventsEventDetail,
  OperationsEventsReadModel,
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
import {
  advanceEventObserversToHead,
  advanceEventSubscriptionsToHead,
  loadEventsOperations,
} from "../api";

interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

type DataTableRow = UiTableRow | Record<string, unknown>;

const { t } = useI18n();
const metricIconById: Record<string, unknown> = {
  health: HeartPulse,
  topics: Radio,
  recent_events: Activity,
  definitions: Database,
  subscriptions: Bell,
  lagging: ShieldAlert,
  dead_letters: ShieldAlert,
  observers: GitBranch,
};
const fallbackTabs: OperationsTab[] = [
  { id: "recent", label: "Recent Events" },
  { id: "topics", label: "Topics" },
  { id: "subscriptions", label: "Subscriptions" },
  { id: "observer", label: "Observer Health" },
  { id: "observer_coverage", label: "Observer Coverage" },
  { id: "contracts", label: "Contracts" },
  { id: "routes", label: "Routes" },
  { id: "dead_letters", label: "Dead Letters" },
  { id: "observer_lag", label: "Observer Lag" },
  { id: "owners", label: "Owners" },
];
const knownTabIds = new Set(fallbackTabs.map((tab) => tab.id));
const eventsTextKeys: Record<string, string> = {
  "Events": "operations.events.title",
  "聚合事件总线、事件合同、订阅游标、观察者消费与死信状态。": "operations.events.subtitle",
  "Events operator": "operations.events.role.operator",
  "Overall Health": "operations.events.metric.health",
  "Live Topics": "operations.events.metric.liveTopics",
  "Topic Contracts": "operations.events.kv.topicContracts",
  "Route Contracts": "operations.events.kv.routeContracts",
  "Recent Events": "operations.events.metric.recentEvents",
  "Definitions": "operations.events.metric.definitions",
  "Surfaces": "operations.events.kv.surfaces",
  "Subscriptions": "operations.events.metric.subscriptions",
  "Lagging": "operations.events.metric.lagging",
  "Lagging Subscriptions": "operations.events.kv.laggingSubscriptions",
  "Stuck Subscriptions": "operations.events.kv.stuckSubscriptions",
  "Dead Letters": "operations.events.metric.deadLetters",
  "Observers": "operations.events.metric.observers",
  "Observer Definitions": "operations.events.kv.observerDefinitions",
  "Observer Runtime": "operations.events.observer.runtime",
  "Uncovered Topics": "operations.events.kv.uncoveredTopics",
  "Uncovered Events": "operations.events.kv.uncoveredEvents",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "Error": "text.error",
  "healthy": "text.healthy",
  "warning": "text.warning",
  "error": "text.error",
  "Event bus state is queryable": "operations.events.delta.queryable",
  "Operator attention recommended": "operations.events.delta.attentionRecommended",
  "Operator action required": "operations.events.delta.actionRequired",
  "Insufficient data": "operations.events.delta.insufficientData",
  "event bus topics": "operations.events.delta.busTopics",
  "retained bus records": "operations.events.delta.retainedRecords",
  "registered event definitions": "operations.events.delta.registeredDefinitions",
  "recent dead-letter records": "operations.events.delta.deadLetterRecords",
  "observer subscriptions": "operations.events.delta.observerSubscriptions",
  "Open Trace": "text.openTrace",
  "Inspect Topic": "operations.events.action.inspectTopic",
  "Inspect Subscription": "operations.events.action.inspectSubscription",
  "Advance Stuck Subscriptions": "operations.events.action.advanceSubscriptions",
  "Advance Stuck Observers": "operations.events.action.advanceObservers",
  "Topics": "operations.events.tab.topics",
  "Observer Health": "operations.events.section.observerHealth",
  "Observer Coverage": "operations.events.section.observerCoverage",
  "Observer Lag": "operations.events.section.observerLag",
  "Contracts": "operations.events.tab.contracts",
  "Routes": "operations.events.tab.routes",
  "Owners": "operations.events.tab.owners",
  "Events by Kind": "operations.events.section.eventsByKind",
  "Events by Surface": "operations.events.section.eventsBySurface",
  "Owners by Volume": "operations.events.section.ownersByVolume",
  "Contract Compatibility": "operations.events.section.contractCompatibility",
  "Consumer Health": "operations.events.section.consumerHealth",
  "No operations observer subscriptions registered.": "operations.events.empty.noObservers",
  "No records.": "table.noRecords",
  "No event owners observed.": "operations.events.empty.noOwners",
  "No event bus records observed.": "operations.events.empty.noRecords",
  "No events match the current filters.": "operations.events.empty.noFilteredRecords",
  "No subscription cursors observed.": "operations.events.empty.noSubscriptions",
  "No observer lag or failed observer records observed.": "operations.events.empty.noObserverLag",
  "No event topics observed.": "operations.events.empty.noTopics",
  "No observer coverage definitions registered.": "operations.events.empty.noObserverCoverage",
  "No dead-letter events observed.": "operations.events.empty.noDeadLetters",
  "No topic contracts registered.": "operations.events.empty.noContracts",
  "No route contracts registered.": "operations.events.empty.noRoutes",
  "No contract matched this event.": "operations.events.empty.noEventContracts",
  "No subscription cursor for this topic.": "operations.events.empty.noEventSubscriptions",
  "Matched": "operations.events.status.matched",
  "Uncovered": "operations.events.status.uncovered",
  "Definition Only": "operations.events.status.definitionOnly",
  "Topic Contract Only": "operations.events.status.topicContractOnly",
  "Dead Letter": "operations.events.status.deadLetter",
  "At Head": "operations.events.status.atHead",
  "Stuck": "operations.events.status.stuck",
  "Idle": "operations.tool.worker.idle",
  "Missing Heartbeat": "operations.events.observer.missingHeartbeat",
  "Rebuilt": "operations.events.observer.rebuilt",
  "Stale": "operations.tool.worker.stale",
  "active": "text.active",
  "registered": "text.registered",
  "matched": "operations.events.status.matched",
  "uncovered": "operations.events.status.uncovered",
  "definition_only": "operations.events.status.definitionOnly",
  "topic_contract_only": "operations.events.status.topicContractOnly",
  "dead_letter": "operations.events.status.deadLetter",
  "at_head": "operations.events.status.atHead",
  "lagging": "operations.events.metric.lagging",
  "stuck": "operations.events.status.stuck",
  "idle": "operations.tool.worker.idle",
  "rebuilt": "operations.events.observer.rebuilt",
  "observed": "operations.events.status.observed",
  "observed_failure": "text.observedFailure",
  "Registered": "text.registered",
  "Fact": "operations.events.kind.fact",
  "Time": "table.time",
  "Topic": "table.topic",
  "Cursor": "table.cursor",
  "Owner": "table.owner",
  "Kind": "table.kind",
  "Contract": "table.contract",
  "Run ID": "table.runId",
  "Trace": "table.trace",
  "Subscription": "table.subscription",
  "Latest Event": "table.latestEvent",
  "Source Event ID": "table.sourceEventId",
  "Target Kind": "table.targetKind",
  "Event Contracts": "operations.events.drawer.contracts",
  "Event Subscriptions": "operations.events.drawer.subscriptions",
};

const page = ref<OperationsEventsReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedEventId = ref<string | null>(null);
const queryInput = ref("");
const submittedSearch = ref("");
const topicPrefixInput = ref("");
const submittedTopicPrefix = ref("");
const statusFilter = ref("all");
const ownerFilter = ref("all");
const refreshTimer = ref<number | null>(null);
const actionBusy = ref<"subscriptions" | "observers" | null>(null);
const actionNotice = ref<string | null>(null);

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "recent";
  return knownTabIds.has(candidate) ? candidate : "recent";
});
const mainTable = computed(() => {
  if (activeTab.value === "topics") return page.value?.topics ?? emptyTable("topics", "Topics");
  if (activeTab.value === "subscriptions") return page.value?.subscriptions ?? emptyTable("subscriptions", "Subscriptions");
  if (activeTab.value === "observer") return page.value?.observer_health ?? emptyTable("observer_health", "Observer Health");
  if (activeTab.value === "observer_coverage") return page.value?.observer_coverage ?? emptyTable("observer_coverage", "Observer Coverage");
  if (activeTab.value === "contracts") return page.value?.contracts ?? emptyTable("contracts", "Contracts");
  if (activeTab.value === "routes") return page.value?.routes ?? emptyTable("routes", "Routes");
  if (activeTab.value === "dead_letters") return page.value?.dead_letters ?? emptyTable("dead_letters", "Dead Letters");
  if (activeTab.value === "observer_lag") return page.value?.observer_lag ?? emptyTable("observer_lag", "Observer Lag");
  if (activeTab.value === "owners") return page.value?.owners_by_volume ?? emptyTable("owners_by_volume", "Owners by Volume");
  return page.value?.recent_events ?? emptyTable("recent_events", "Recent Events");
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
const ownerOptions = computed(() => {
  const values = new Set<string>();
  for (const row of page.value?.owners_by_volume.rows ?? []) {
    const owner = cellValueText(row.cells.owner);
    if (owner && owner !== "-") values.add(owner);
  }
  for (const item of page.value?.event_details ?? []) {
    const owner = item.summary.find((summary) => summary.label === "Owner")?.value;
    if (owner && owner !== "-") values.add(owner);
  }
  return [...values].sort();
});
const eventsByKindChart = computed(() => page.value?.events_over_time ?? emptyChart("events_over_time", "Events by Kind", "bar"));
const eventsBySurfaceChart = computed(() => page.value?.events_by_surface ?? emptyChart("events_by_surface", "Events by Surface", "donut"));
const ownersTable = computed(() => page.value?.owners_by_volume ?? emptyTable("owners_by_volume", "Owners by Volume"));
const observerHealthTable = computed(() => page.value?.observer_health ?? emptyTable("observer_health", "Observer Health"));
const observerPreviewRows = computed(() => observerHealthTable.value.rows.slice(0, 3));
const observerPreviewOverflow = computed(() => Math.max(
  (observerHealthTable.value.total ?? observerHealthTable.value.rows.length) - observerPreviewRows.value.length,
  0,
));
const deadLettersTable = computed(() => page.value?.dead_letters ?? emptyTable("dead_letters", "Dead Letters"));
const contractItems = computed(() => page.value?.contract_compatibility.items ?? []);
const surfaceSegments = computed(() => chartSegments(eventsBySurfaceChart.value));
const kindSegments = computed(() => chartSegments(eventsByKindChart.value));
const selectedDetail = computed(() => {
  if (!selectedEventId.value) return null;
  return (page.value?.event_details ?? []).find((item) => item.event_id === selectedEventId.value) ?? null;
});
const canSelectRows = computed(() => ["recent", "dead_letters", "observer_lag"].includes(activeTab.value));

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
}

function selectEventFromRow(row: DataTableRow) {
  const candidates = [
    rowId(row),
    cellText(row, "event_id"),
    cellText(row, "source_event_id"),
  ].filter((value): value is string => Boolean(value && value !== "-"));
  const detail = (page.value?.event_details ?? []).find((item) => candidates.includes(item.event_id));
  selectedEventId.value = detail?.event_id ?? null;
}

function rowId(row: DataTableRow): string | null {
  return "id" in row && typeof row.id === "string" ? row.id : null;
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

function openObserverHealth() {
  selectTab("observer");
}

function observerPreviewTitle(row: DataTableRow): string {
  const title = firstCellText(row, ["event", "event_name", "topic", "subscription", "observer", "consumer"]);
  return title !== "-" ? eventsText(title) : rowId(row) ?? "-";
}

function observerPreviewMeta(row: DataTableRow): string {
  const owner = firstCellText(row, ["owner", "surface", "module", "consumer"]);
  const lag = firstCellText(row, ["lag", "cursor_lag", "latest_event", "cursor", "updated_at"]);
  return [owner, lag].filter((value) => value && value !== "-").join(" / ") || "-";
}

function observerPreviewStatus(row: DataTableRow): string {
  const status = firstCellText(row, ["status", "health", "state"]);
  return status !== "-" ? eventsText(status) : "-";
}

function previewTone(row: DataTableRow): UiTone {
  const value = firstCellText(row, ["tone", "status", "health", "state"]).toLowerCase();
  if (/error|fail|dead|stuck|blocked/.test(value)) return "danger";
  if (/warn|lag|slow|behind|retry/.test(value)) return "warning";
  if (/healthy|ready|active|ok|at_head|head|matched/.test(value)) return "success";
  return "neutral";
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
  if (typeof value === "object" && "text" in value) {
    return String((value as { text: string }).text);
  }
  return String(value);
}

function chartSegments(section: UiChartSection): ChartSegmentView[] {
  const rawSegments = section.segments ?? [];
  const total = rawSegments.reduce((sum, segment) => sum + Number(segment.value || 0), 0);
  return rawSegments.map((segment) => ({
    id: segment.id,
    label: eventsText(segment.label),
    value: Number(segment.value || 0),
    tone: segment.tone,
    pct: total > 0 ? Math.round((Number(segment.value || 0) / total) * 100) : 0,
  }));
}

function metricIcon(metric: UiMetricCard, index: number) {
  return metricIconById[metric.id] ?? [HeartPulse, Radio, Activity, Database, Bell, ShieldAlert, GitBranch, Layers][index % 8];
}

function metricLabel(metric: UiMetricCard) {
  return eventsText(metric.label);
}

function metricDelta(metric: UiMetricCard) {
  return eventsText(metric.delta ?? "");
}

function tabLabel(tab: OperationsTab) {
  return eventsText(tab.label);
}

function sectionTitle(section: UiTableSection | UiChartSection) {
  return eventsText(section.title);
}

function emptyState(section: UiTableSection) {
  return eventsText(section.empty_state ?? "No records.");
}

function detailItems(items: UiKeyValueItem[]) {
  return items.map((item) => ({
    ...item,
    label: eventsText(item.label),
    value: eventsText(item.value),
  }));
}

function detailPayload(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function eventsText(value: string | null | undefined): string {
  if (!value) return "";
  const atHead = value.match(/^(\d+) at head$/);
  if (atHead) return t("operations.events.delta.atHead", { count: atHead[1] });
  const stuck = value.match(/^(\d+) stuck$/);
  if (stuck) return t("operations.events.delta.stuck", { count: stuck[1] });
  const observerRuntimeSplit = value.match(/^(\d+) runtimes \/ (\d+) subscriptions$/);
  if (observerRuntimeSplit) {
    return t("operations.events.delta.observerRuntimeSplit", {
      runtimes: observerRuntimeSplit[1],
      subscriptions: observerRuntimeSplit[2],
    });
  }
  const key = eventsTextKeys[value];
  return key ? t(key) : value;
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
  submittedTopicPrefix.value = topicPrefixInput.value.trim();
  selectedEventId.value = null;
  void refreshPage();
}

function resetSearch() {
  queryInput.value = "";
  submittedSearch.value = "";
  topicPrefixInput.value = "";
  submittedTopicPrefix.value = "";
  statusFilter.value = "all";
  ownerFilter.value = "all";
  selectedEventId.value = null;
  void refreshPage();
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadEventsOperations({
      status: statusFilter.value,
      topic_prefix: submittedTopicPrefix.value,
      search: submittedSearch.value,
      owner: ownerFilter.value,
      limit: 80,
    });
    page.value = loaded.page;
    loadError.value = null;
    if (selectedEventId.value && !loaded.page.event_details.some((item) => item.event_id === selectedEventId.value)) {
      selectedEventId.value = null;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function advanceStuckSubscriptions(observerOnly = false) {
  if (typeof window === "undefined") return;
  const reason = window.prompt(t("operations.events.action.reasonPrompt"));
  const normalizedReason = reason?.trim();
  if (!normalizedReason) return;
  const actionLabel = t(
    observerOnly
      ? "operations.events.action.advanceObservers"
      : "operations.events.action.advanceSubscriptions",
  );
  const confirmation = t("operations.events.action.advanceConfirm", {
    action: actionLabel,
    reason: normalizedReason,
  });
  const confirmed = window.confirm(confirmation);
  if (!confirmed) return;
  actionBusy.value = observerOnly ? "observers" : "subscriptions";
  actionNotice.value = null;
  loadError.value = null;
  try {
    const actionPayload = {
      status: "stuck",
      reason: normalizedReason,
      confirmation,
      risk_acknowledged: confirmed,
      metadata: {
        confirmation_prompt: confirmation,
      },
    };
    const result = observerOnly
      ? await advanceEventObserversToHead(actionPayload)
      : await advanceEventSubscriptionsToHead(actionPayload);
    actionNotice.value = t(
      observerOnly
        ? "operations.events.action.advanceObserversNotice"
        : "operations.events.action.advanceSubscriptionsNotice",
      {
        count: result.advanced_count,
        matched: result.matched_count,
      },
    );
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
  <main class="operations-module-console events-console scroll-area" :class="{ 'has-drawer': selectedDetail }">
    <header class="events-header">
      <div>
        <h2>{{ eventsText(page?.title ?? "Events") }} <span>{{ page?.health ? eventsText(page.health) : "-" }}</span></h2>
        <p>{{ eventsText(page?.subtitle ?? "聚合事件总线、事件合同、订阅游标、观察者消费与死信状态。") }}</p>
      </div>
      <div class="events-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton class="role-badge" size="sm" variant="secondary">
          <ShieldAlert :size="13" /> {{ t("operations.currentRoleLabel") }}: {{ eventsText(page?.role.label ?? "Events operator") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="events-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>
    <div v-if="actionNotice" class="events-alert events-alert--success">
      <StatusDot tone="success" />
      <span>{{ actionNotice }}</span>
    </div>

    <section class="events-action-strip">
      <span>{{ t("operations.events.action.stripLabel") }}</span>
      <UiButton
        size="sm"
        variant="danger"
        :disabled="loading || actionBusy !== null"
        @click="advanceStuckSubscriptions(false)"
      >
        <RefreshCcw :class="{ 'motion-spin': actionBusy === 'subscriptions' }" :size="13" />
        {{ t("operations.events.action.advanceSubscriptions") }}
      </UiButton>
      <UiButton
        size="sm"
        variant="secondary"
        :disabled="loading || actionBusy !== null"
        @click="advanceStuckSubscriptions(true)"
      >
        <RefreshCcw :class="{ 'motion-spin': actionBusy === 'observers' }" :size="13" />
        {{ t("operations.events.action.advanceObservers") }}
      </UiButton>
    </section>

    <section class="events-metrics">
      <template v-if="displayMetrics.length">
        <article v-for="(metric, index) in displayMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
          <span class="metric-icon"><component :is="metricIcon(metric, index)" :size="22" /></span>
          <span class="metric-copy">
            <em>{{ metricLabel(metric) }}</em>
            <strong>{{ eventsText(metric.value) }}</strong>
            <small>{{ metricDelta(metric) }}</small>
          </span>
        </article>
      </template>
      <template v-else>
        <article v-for="index in 8" :key="`metric-placeholder-${index}`" class="metric metric--placeholder" aria-hidden="true">
          <span class="metric-icon" />
          <span class="metric-copy">
            <em />
            <strong />
            <small />
          </span>
        </article>
      </template>
    </section>

    <section class="events-status-strip">
      <article class="contract-panel">
        <div class="panel-heading">
          <h3>{{ eventsText(page?.contract_compatibility.title ?? "Contract Compatibility") }}</h3>
        </div>
        <dl class="kv-grid">
          <div v-for="item in contractItems" :key="item.label" :class="`stat-tile stat-tile--${item.tone ?? 'neutral'}`">
            <dt>{{ eventsText(item.label) }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>
        <p v-if="!contractItems.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="surface-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(eventsBySurfaceChart) }}</h3>
        </div>
        <div v-if="surfaceSegments.length" class="chart-card-body">
          <div class="donut-visual">
            <strong>{{ eventsBySurfaceChart.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl class="segment-list">
            <div v-for="segment in surfaceSegments.slice(0, 6)" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }} <span>{{ segment.pct }}%</span></dd>
            </div>
          </dl>
        </div>
        <p v-if="!surfaceSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="observer-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(observerHealthTable) }}</h3>
          <a href="/operations/events?tab=observer" @click.prevent="selectTab('observer')">{{ t("common.viewAll") }}</a>
        </div>
        <div v-if="observerPreviewRows.length" class="status-preview-list">
          <button
            v-for="row in observerPreviewRows"
            :key="rowId(row) ?? observerPreviewTitle(row)"
            type="button"
            class="status-preview-row"
            @click="openObserverHealth"
          >
            <span class="status-preview-copy">
              <strong :title="observerPreviewTitle(row)">{{ observerPreviewTitle(row) }}</strong>
              <small :title="observerPreviewMeta(row)">{{ observerPreviewMeta(row) }}</small>
            </span>
            <span :class="`status-preview-pill status-preview-pill--${previewTone(row)}`">
              {{ observerPreviewStatus(row) }}
            </span>
          </button>
          <p v-if="observerPreviewOverflow" class="status-preview-more">+{{ observerPreviewOverflow }} {{ t("common.more") }}</p>
        </div>
        <p v-if="!observerHealthTable.rows.length" class="panel-empty">{{ emptyState(observerHealthTable) }}</p>
      </article>
    </section>

    <nav class="events-tabs">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: tab.id === activeTab }" type="button" @click="selectTab(tab.id)">
        {{ tabLabel(tab) }}<span v-if="tab.count != null">{{ tab.count }}</span>
      </button>
    </nav>

    <section class="events-main-grid">
      <article class="events-table-panel">
        <div class="panel-heading panel-heading--table">
          <h3>{{ sectionTitle(mainTable) }} <span>{{ mainTable.total ?? mainTable.rows.length }}</span></h3>
          <form class="table-controls" @submit.prevent="submitSearch">
            <label class="table-search">
              <Search :size="13" />
              <input v-model.trim="queryInput" type="search" :placeholder="t('operations.events.searchPlaceholder')" />
            </label>
            <label class="table-search table-search--topic">
              <span>{{ t("table.topic") }}</span>
              <input v-model.trim="topicPrefixInput" type="search" :placeholder="t('operations.events.topicPrefixPlaceholder')" />
            </label>
            <label class="status-filter">
              <span>{{ t("table.owner") }}</span>
              <select v-model="ownerFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="owner in ownerOptions" :key="owner" :value="owner">
                  {{ owner }}
                </option>
              </select>
            </label>
            <label class="status-filter">
              <span>{{ t("table.status") }}</span>
              <select v-model="statusFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option value="matched">{{ t("operations.events.status.matched") }}</option>
                <option value="uncovered">{{ t("operations.events.status.uncovered") }}</option>
                <option value="dead_letter">{{ t("operations.events.status.deadLetter") }}</option>
                <option value="lagging">{{ t("operations.events.metric.lagging") }}</option>
                <option value="stuck">{{ t("operations.events.status.stuck") }}</option>
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
          section-id="events-main-table"
          :page-size="12"
          :clickable-rows="canSelectRows"
          @row-click="selectEventFromRow"
        />
        <p v-else class="table-empty">{{ emptyState(mainTable) }}</p>
      </article>

      <aside class="events-side-panel">
        <article class="kind-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(eventsByKindChart) }}</h3>
          </div>
          <dl class="kind-bars">
            <div v-for="segment in kindSegments" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ eventsText(segment.label) }}</dt>
              <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
            </div>
          </dl>
          <p v-if="!kindSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
        </article>

        <article class="owners-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(ownersTable) }}</h3>
            <a href="/operations/events?tab=owners" @click.prevent="selectTab('owners')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable v-if="ownersTable.rows.length" :columns="ownersTable.columns" :rows="ownersTable.rows" section-id="events-owners" :page-size="3" />
          <p v-if="!ownersTable.rows.length" class="panel-empty">{{ emptyState(ownersTable) }}</p>
        </article>

        <article class="dead-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(deadLettersTable) }}</h3>
            <a href="/operations/events?tab=dead_letters" @click.prevent="selectTab('dead_letters')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable v-if="deadLettersTable.rows.length" :columns="deadLettersTable.columns" :rows="deadLettersTable.rows" section-id="events-dead-letters" :page-size="3" />
          <p v-if="!deadLettersTable.rows.length" class="panel-empty">{{ emptyState(deadLettersTable) }}</p>
        </article>
      </aside>
    </section>

    <aside v-if="selectedDetail" class="events-drawer">
      <header>
        <div>
          <span>{{ t("operations.events.drawer.event") }}</span>
          <h3>{{ selectedDetail.title }}</h3>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedEventId = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.events.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.events.drawer.payload") }}</h4>
        <pre>{{ detailPayload(selectedDetail.payload) }}</pre>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.events.drawer.trace") }}</h4>
        <pre>{{ detailPayload(selectedDetail.trace) }}</pre>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedDetail.contracts) }}</h4>
        <DataTable :columns="selectedDetail.contracts.columns" :rows="selectedDetail.contracts.rows" section-id="events-detail-contracts" :page-size="5" />
        <p v-if="!selectedDetail.contracts.rows.length" class="panel-empty">{{ emptyState(selectedDetail.contracts) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedDetail.subscriptions) }}</h4>
        <DataTable :columns="selectedDetail.subscriptions.columns" :rows="selectedDetail.subscriptions.rows" section-id="events-detail-subscriptions" :page-size="5" />
        <p v-if="!selectedDetail.subscriptions.rows.length" class="panel-empty">{{ emptyState(selectedDetail.subscriptions) }}</p>
      </section>
    </aside>
  </main>
</template>

<style scoped>
.events-console {
  height: 100%;
  overflow: auto;
  padding: 8px 12px 12px;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
}

.events-header,
.events-header__ops,
.events-metrics,
.events-tabs,
.panel-heading,
.chart-card-body,
.events-alert,
.events-action-strip,
.auto-toggle,
.table-controls,
.table-search,
.status-filter {
  display: flex;
  align-items: center;
}

.events-header {
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
  align-items: baseline;
  gap: 10px;
  font-size: 17px;
  line-height: 1.15;
}

h2 span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

h3 {
  font-size: 13px;
}

h4 {
  font-size: 12px;
}

.events-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.events-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.events-header__ops strong {
  color: var(--text-secondary);
}

.auto-toggle {
  gap: 6px;
}

.auto-toggle i {
  width: 20px;
  height: 10px;
  border-radius: 99px;
  background: color-mix(in srgb, var(--color-success) 62%, var(--surface-panel));
}

.events-alert {
  gap: 8px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, var(--border-subtle));
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-danger) 9%, var(--surface-panel));
  color: var(--text-secondary);
  font-size: 11px;
}

.events-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 35%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 9%, var(--surface-panel));
}

.events-action-strip {
  justify-content: flex-end;
  gap: 6px;
  min-height: 28px;
  margin-bottom: 4px;
  padding: 2px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 88%, transparent);
}

.events-action-strip span {
  margin-right: auto;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.events-metrics {
  display: grid;
  grid-template-columns: repeat(8, minmax(96px, 1fr));
  gap: 6px;
}

.metric,
.events-status-strip > article,
.events-table-panel,
.events-side-panel > article {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
}

.metric {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 6px;
  height: 64px;
  min-height: 0;
  padding: 7px 9px;
  overflow: hidden;
}

.metric-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-blue) 16%, transparent);
  color: var(--color-blue);
}

.metric--success .metric-icon {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.metric--warning .metric-icon {
  background: color-mix(in srgb, var(--color-warning) 20%, transparent);
  color: var(--color-warning);
}

.metric--danger .metric-icon {
  background: color-mix(in srgb, var(--color-danger) 18%, transparent);
  color: var(--color-danger);
}

.metric--placeholder {
  pointer-events: none;
}

.metric--placeholder .metric-icon,
.metric--placeholder .metric-copy em,
.metric--placeholder .metric-copy strong,
.metric--placeholder .metric-copy small {
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-raised) 86%, var(--border-subtle));
  color: transparent;
}

.metric--placeholder .metric-copy em {
  width: 68%;
  height: 10px;
}

.metric--placeholder .metric-copy strong {
  width: 42%;
  height: 16px;
}

.metric--placeholder .metric-copy small {
  width: 78%;
  height: 9px;
}

.metric-copy {
  min-width: 0;
}

.metric-copy em,
.metric-copy small {
  display: block;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-copy strong {
  display: block;
  margin: 3px 0 1px;
  overflow: hidden;
  font-size: 17px;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.events-status-strip {
  display: grid;
  grid-template-columns: minmax(250px, 0.72fr) minmax(220px, 0.64fr) minmax(360px, 1.22fr);
  gap: 6px;
  align-items: start;
  margin-top: 6px;
}

.events-status-strip > article,
.events-side-panel > article,
.events-table-panel {
  min-width: 0;
  padding: 8px;
}

.contract-panel,
.surface-panel,
.observer-panel {
  min-height: 128px;
  overflow: visible;
}

.panel-heading {
  justify-content: space-between;
  gap: 8px;
  min-height: 20px;
  margin-bottom: 5px;
}

.panel-heading a,
.panel-heading h3 span {
  color: var(--color-blue);
  font-size: 11px;
  font-weight: 600;
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
  gap: 6px;
}

.contract-panel .stat-tile {
  min-height: 42px;
  padding: 5px 6px;
}

.contract-panel .stat-tile dd {
  font-size: 14px;
}

.stat-tile {
  min-height: 44px;
  padding: 6px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
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
  border-color: color-mix(in srgb, var(--color-blue) 42%, var(--border-subtle));
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
  max-width: 108px;
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

.stat-tile dt {
  overflow-wrap: anywhere;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.2;
}

.stat-tile dd {
  margin: 2px 0 0;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 800;
}

.stat-tile--success dd {
  color: var(--color-success);
}

.stat-tile--warning dd {
  color: var(--color-warning);
}

.stat-tile--danger dd {
  color: var(--color-danger);
}

.chart-card-body {
  gap: 9px;
  min-height: 76px;
}

.donut-visual {
  display: grid;
  place-items: center;
  width: 76px;
  height: 76px;
  border: 1px solid color-mix(in srgb, var(--color-blue) 40%, var(--border-subtle));
  border-radius: 999px;
  background: var(--surface-panel-soft);
}

.donut-visual strong {
  font-size: 18px;
  line-height: 1;
}

.donut-visual span {
  color: var(--text-muted);
  font-size: 10px;
}

.segment-list,
.kind-bars,
.detail-grid {
  display: grid;
  gap: 8px;
}

.segment-list {
  flex: 1;
  min-width: 0;
}

.segment-list div,
.kind-bars div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 11px;
}

.segment-list dt,
.kind-bars dt {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.segment-list dd,
.kind-bars dd {
  margin: 0;
  font-weight: 700;
}

.segment-list dd span {
  color: var(--text-muted);
  font-size: 10px;
}

.events-tabs {
  gap: 14px;
  min-height: 29px;
  margin-top: 6px;
  padding: 0;
  overflow-x: auto;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  border-radius: 0;
  background: transparent;
}

.events-tabs button {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  height: 29px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
}

.events-tabs button.active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.events-tabs button span {
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--surface-panel-soft);
  color: var(--text-muted);
  font-size: 10px;
}

.events-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 6px;
  margin-top: 6px;
  align-items: start;
}

.events-table-panel {
  display: flex;
  flex-direction: column;
  min-height: clamp(340px, calc(100dvh - var(--shell-topbar-height) - 420px), 520px);
}

.events-table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.panel-heading--table {
  align-items: flex-start;
}

.panel-heading--table h3 {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.panel-heading--table h3 span {
  color: var(--text-muted);
}

.table-controls {
  flex: 1;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
  min-width: 0;
}

.table-search {
  width: min(280px, 28vw);
  height: 30px;
  gap: 6px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-muted);
}

.table-search--topic {
  width: min(220px, 22vw);
}

.table-search span,
.status-filter span {
  flex: 0 0 auto;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 600;
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

.status-filter {
  height: 30px;
  gap: 6px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.status-filter select {
  max-width: 128px;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.events-side-panel {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.events-side-panel > article {
  min-height: 118px;
  overflow: visible;
}

.kind-bars dd {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 92px;
  height: 16px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 10px;
}

.kind-bars dd span {
  position: absolute;
  inset-block: 4px;
  left: 0;
  border-radius: 99px;
  background: color-mix(in srgb, var(--color-blue) 38%, transparent);
}

.panel-empty {
  flex: 1 1 auto;
  display: grid;
  min-height: 54px;
  place-items: center;
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

.events-drawer {
  position: fixed;
  top: calc(var(--shell-topbar-height, 50px) + 16px);
  right: 20px;
  bottom: 20px;
  z-index: 30;
  width: min(460px, calc(100vw - 36px));
  overflow: auto;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 96%, var(--surface-page));
  box-shadow: var(--shadow-floating);
}

.events-drawer header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.events-drawer header span {
  color: var(--text-muted);
  font-size: 10px;
  text-transform: uppercase;
}

.events-drawer header h3 {
  margin-top: 3px;
  word-break: break-word;
}

.events-drawer button {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
}

.drawer-section {
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}

.drawer-section h4 {
  margin-bottom: 8px;
}

.detail-grid div {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 10px;
  font-size: 11px;
}

.detail-grid dt {
  color: var(--text-muted);
}

.detail-grid dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-weight: 700;
}

.tone-danger {
  color: var(--color-danger) !important;
}

.tone-warning {
  color: var(--color-warning) !important;
}

.tone-success {
  color: var(--color-success) !important;
}

pre {
  max-height: 240px;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  font-size: 10.5px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1400px) {
  .events-metrics {
    grid-template-columns: repeat(4, minmax(130px, 1fr));
  }

  .events-status-strip {
    grid-template-columns: minmax(0, 1fr);
  }

  .events-main-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .events-drawer {
    top: 70px;
    right: 12px;
    bottom: 12px;
    width: min(420px, calc(100vw - 24px));
  }
}

@media (max-width: 760px) {
  .events-console {
    padding: 8px 10px 10px;
  }

  .events-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .events-header__ops {
    justify-content: flex-start;
  }

  .events-metrics,
  .events-status-strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .metric {
    flex: 0 0 150px;
  }

  .events-status-strip > article {
    flex: 0 0 286px;
  }

  .kv-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-card-body {
    align-items: flex-start;
    flex-direction: column;
  }

  .table-search {
    width: 100%;
  }

  .table-controls {
    justify-content: flex-start;
  }

  .table-search--topic {
    width: 100%;
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
