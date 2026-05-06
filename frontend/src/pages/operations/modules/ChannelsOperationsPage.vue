<script setup lang="ts">
import {
  Activity,
  Cable,
  Database,
  GitBranch,
  HeartPulse,
  MessageCircle,
  RadioTower,
  RefreshCcw,
  Search,
  ShieldAlert,
  X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime, formatRawKeyLabel } from "@/shared/i18n/formatters";
import type {
  OperationsChannelInteractionDetail,
  OperationsChannelRecordDetail,
  OperationsChannelRuntimeDetail,
  OperationsChannelsReadModel,
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
import { loadChannelsOperations, pruneStaleChannelRuntimes, replayChannelDeadLetter } from "../api";

interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

type DataTableRow = UiTableRow | Record<string, unknown>;
type SelectedDetail = { type: "runtime" | "record" | "interaction"; id: string } | null;
type ChannelActionBusy = "prune" | "replay" | null;

interface DeadLetterReplayTarget {
  channelType: string;
  runtimeId: string | null;
  cursor: string | null;
  eventId: string | null;
}

const { t } = useI18n();
const metricIconById: Record<string, unknown> = {
  health: HeartPulse,
  runtimes: RadioTower,
  profiles: Database,
  connections: Cable,
  accounts: MessageCircle,
  interactions: GitBranch,
  dead_letters: ShieldAlert,
  events: Activity,
};
const fallbackTabs: OperationsTab[] = [
  { id: "runtimes", label: "Runtimes" },
  { id: "interactions", label: "Interactions" },
  { id: "connections", label: "Connections" },
  { id: "accounts", label: "Accounts" },
  { id: "profiles", label: "Profiles" },
  { id: "messages", label: "Recent Messages" },
  { id: "dead_letters", label: "Dead Letters" },
  { id: "events", label: "Channel Events" },
  { id: "contracts", label: "Contracts" },
];
const knownTabIds = new Set(fallbackTabs.map((tab) => tab.id));
const selectableTabs = new Set(["runtimes", "interactions", "messages", "dead_letters", "events"]);
const channelsTextKeys: Record<string, string> = {
  "Channels": "operations.channels.title",
  "聚合通道配置、runtime、绑定、死信与通道事件的运维视图。": "operations.channels.subtitle",
  "聚合通道配置、运行时、绑定、死信与通道事件的运维视图。": "operations.channels.subtitle",
  "Channels operator": "operations.channels.role.operator",
  "Overall Health": "operations.channels.metric.health",
  "Runtimes": "operations.channels.metric.runtimes",
  "Channel Profiles": "operations.channels.metric.profiles",
  "Connections": "operations.channels.metric.connections",
  "Accounts": "operations.channels.metric.accounts",
  "Interactions": "operations.channels.metric.interactions",
  "Dead Letters": "operations.channels.metric.deadLetters",
  "Channel Events": "operations.channels.metric.events",
  "Channel runtime state is queryable": "operations.channels.delta.queryable",
  "Operator attention recommended": "operations.channels.delta.attentionRecommended",
  "Operator action required": "operations.channels.delta.actionRequired",
  "Insufficient data": "operations.channels.delta.insufficientData",
  "retained channel failures": "operations.channels.delta.retainedFailures",
  "runtime connection bindings": "operations.channels.delta.connectionBindings",
  "runtime account bindings": "operations.channels.delta.accountBindings",
  "recent event-bus records": "operations.channels.delta.eventBusRecords",
  "Profiles": "operations.channels.tab.profiles",
  "Recent Messages": "operations.channels.tab.messages",
  "Contracts": "operations.channels.tab.contracts",
  "Channel Runtimes": "operations.channels.section.runtimes",
  "Message Flow": "operations.channels.section.messageFlow",
  "Runtime / Delivery Status": "operations.channels.section.deliveryStatus",
  "Top Channels": "operations.channels.section.topChannels",
  "Dead Letter Queue": "operations.channels.section.deadLetterQueue",
  "Failures by Category": "operations.channels.section.failures",
  "Account Bindings": "operations.channels.section.accountBindings",
  "Connection Bindings": "operations.channels.section.connectionBindings",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "Error": "text.error",
  "healthy": "text.healthy",
  "warning": "text.warning",
  "error": "text.error",
  "Online": "text.online",
  "Received": "operations.channels.status.received",
  "Submitted": "operations.channels.status.submitted",
  "Queued": "text.queued",
  "Running": "text.running",
  "Completed": "text.completed",
  "Delivered": "operations.channels.status.delivered",
  "Stale": "operations.channels.status.stale",
  "Dead Letter": "operations.channels.status.deadLetter",
  "Enabled": "operations.channels.status.enabled",
  "Disabled": "operations.channels.status.disabled",
  "Offline": "operations.channels.status.offline",
  "Open Runtime": "operations.channels.action.openRuntime",
  "Inspect Dead Letter": "operations.channels.action.inspectDeadLetter",
  "Replay Dead Letter": "operations.channels.action.replayDeadLetter",
  "Prune Stale Runtimes": "operations.channels.action.pruneStaleRuntimes",
  "Runtime ID": "table.runtimeId",
  "Interaction ID": "table.interactionId",
  "Channel Type": "table.channelType",
  "Status": "table.status",
  "Service Key": "table.serviceKey",
  "Heartbeat Age": "table.heartbeatAge",
  "Event ID": "table.eventId",
  "Topic": "table.topic",
  "Cursor": "table.cursor",
  "Trace": "table.trace",
  "Connection ID": "table.connectionId",
  "Conversation ID": "table.conversationId",
  "Run ID": "table.runId",
  "Session Key": "table.sessionKey",
  "Agent": "common.agent",
  "Agent ID": "table.agentId",
  "Last Error": "table.lastError",
  "Updated At": "table.updatedAt",
  "Observe Cursor": "table.observeCursor",
  "Live Cursor": "table.liveCursor",
  "External Event ID": "table.externalEventId",
  "External Message ID": "table.externalMessageId",
  "External Conversation ID": "table.externalConversationId",
  "External User ID": "table.externalUserId",
  "Active Session ID": "table.activeSessionId",
  "Routing": "operations.channels.drawer.routing",
  "Reply Address": "operations.channels.drawer.replyAddress",
  "Metadata": "table.metadata",
  "true": "common.yes",
  "false": "common.no",
  "Active": "text.active",
  "Registered": "text.registered",
  "Intake": "operations.channels.direction.intake",
  "Observe": "operations.channels.direction.observe",
  "Live": "operations.channels.direction.live",
  "Broadcast": "operations.channels.direction.broadcast",
  "Control": "operations.channels.direction.control",
  "Other": "operations.channels.direction.other",
  "Subscription Updated": "operations.channels.event.subscriptionUpdated",
  "Appended": "operations.channels.event.appended",
  "Topic Contract": "operations.channels.contract.topic",
  "Route Contract": "operations.channels.contract.route",
  "Definition": "operations.channels.contract.definition",
  "Surface": "operations.channels.contract.surface",
  "No channel runtimes registered.": "operations.channels.empty.runtimes",
  "No channel dead letters observed.": "operations.channels.empty.deadLetters",
  "No channel messages or channel events observed.": "operations.channels.empty.messages",
  "No channel interactions registered.": "operations.channels.empty.interactions",
  "No channel account bindings registered.": "operations.channels.empty.accounts",
  "No channel connection bindings registered.": "operations.channels.empty.connections",
  "No channel profiles configured.": "operations.channels.empty.profiles",
  "No channel event records observed.": "operations.channels.empty.events",
  "No channel event contracts registered.": "operations.channels.empty.contracts",
  "No related routing identifiers.": "operations.channels.empty.related",
  "No records.": "table.noRecords",
};

const page = ref<OperationsChannelsReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedDetail = ref<SelectedDetail>(null);
const queryInput = ref("");
const submittedSearch = ref("");
const statusFilter = ref("all");
const channelTypeFilter = ref("all");
const refreshTimer = ref<number | null>(null);
const actionBusy = ref<ChannelActionBusy>(null);
const actionNotice = ref<string | null>(null);

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "runtimes";
  return knownTabIds.has(candidate) ? candidate : "runtimes";
});
const mainTable = computed(() => {
  if (activeTab.value === "interactions") return page.value?.interactions ?? emptyTable("interactions", "Interactions");
  if (activeTab.value === "connections") return page.value?.connection_bindings ?? emptyTable("connection_bindings", "Connection Bindings");
  if (activeTab.value === "accounts") return page.value?.channel_bindings ?? emptyTable("channel_bindings", "Account Bindings");
  if (activeTab.value === "profiles") return page.value?.channel_profiles ?? emptyTable("channel_profiles", "Channel Profiles");
  if (activeTab.value === "messages") return page.value?.recent_messages ?? emptyTable("recent_messages", "Recent Messages");
  if (activeTab.value === "dead_letters") return page.value?.dead_letter_queue ?? emptyTable("dead_letter_queue", "Dead Letter Queue");
  if (activeTab.value === "events") return page.value?.channel_events ?? emptyTable("channel_events", "Channel Events");
  if (activeTab.value === "contracts") return page.value?.contracts ?? emptyTable("contracts", "Contracts");
  return page.value?.channel_status ?? emptyTable("channel_status", "Channel Runtimes");
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
const channelTypeOptions = computed(() => {
  const values = new Set<string>();
  const sections = [
    page.value?.channel_status,
    page.value?.interactions,
    page.value?.connection_bindings,
    page.value?.channel_bindings,
    page.value?.channel_profiles,
  ];
  for (const section of sections) {
    for (const row of section?.rows ?? []) {
      const value = cellValueText(row.cells.channel_type);
      if (value && value !== "-") values.add(value);
    }
  }
  for (const segment of page.value?.top_channels.segments ?? []) {
    if (segment.label && segment.label !== "unknown") values.add(segment.label);
  }
  return [...values].sort();
});
const messageFlow = computed(() => page.value?.message_flow ?? emptyChart("message_flow", "Message Flow", "donut"));
const deliveryTrend = computed(() => page.value?.delivery_trend ?? emptyChart("delivery_trend", "Runtime / Delivery Status", "bar"));
const topChannels = computed(() => page.value?.top_channels ?? emptyChart("top_channels", "Top Channels", "bar"));
const failuresByCategory = computed(() => page.value?.failures_by_category ?? emptyChart("failures_by_category", "Failures by Category", "bar"));
const deadLettersTable = computed(() => page.value?.dead_letter_queue ?? emptyTable("dead_letter_queue", "Dead Letter Queue"));
const profilesTable = computed(() => page.value?.channel_profiles ?? emptyTable("channel_profiles", "Channel Profiles"));
const flowSegments = computed(() => chartSegments(messageFlow.value));
const deliverySegments = computed(() => chartSegments(deliveryTrend.value));
const channelSegments = computed(() => chartSegments(topChannels.value));
const failureSegments = computed(() => chartSegments(failuresByCategory.value));
const selectedRuntimeDetail = computed<OperationsChannelRuntimeDetail | null>(() => {
  if (selectedDetail.value?.type !== "runtime") return null;
  return (page.value?.runtime_details ?? []).find((item) => item.runtime_id === selectedDetail.value?.id) ?? null;
});
const selectedRecordDetail = computed<OperationsChannelRecordDetail | null>(() => {
  if (selectedDetail.value?.type !== "record") return null;
  return (page.value?.record_details ?? []).find((item) => item.record_id === selectedDetail.value?.id) ?? null;
});
const selectedInteractionDetail = computed<OperationsChannelInteractionDetail | null>(() => {
  if (selectedDetail.value?.type !== "interaction") return null;
  return (page.value?.interaction_details ?? []).find((item) => item.interaction_id === selectedDetail.value?.id) ?? null;
});
const drawerOpen = computed(() => Boolean(selectedRuntimeDetail.value || selectedRecordDetail.value || selectedInteractionDetail.value));
const selectedDeadLetterReplayTarget = computed<DeadLetterReplayTarget | null>(() => {
  const detail = selectedRecordDetail.value;
  if (!detail) return null;
  if (detail.status.toLowerCase() !== "dead letter") return null;
  const channelType = normalizedReplayValue(detailSummaryValue(detail.summary, "Channel Type"))?.toLowerCase() ?? null;
  const cursor = normalizedReplayValue(detailSummaryValue(detail.summary, "Cursor"));
  const eventId = normalizedReplayValue(detailSummaryValue(detail.summary, "Event ID"));
  const runtimeId = normalizedReplayValue(detailSummaryValue(detail.summary, "Runtime ID"));
  if (channelType !== "webhook" || (!cursor && !eventId)) return null;
  return {
    channelType,
    runtimeId,
    cursor,
    eventId,
  };
});

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
  selectedDetail.value = null;
}

function selectRow(row: DataTableRow) {
  if (!selectableTabs.has(activeTab.value)) return;
  const id = rowId(row);
  if (!id) return;
  if (activeTab.value === "runtimes") {
    selectedDetail.value = { type: "runtime", id };
    return;
  }
  if (activeTab.value === "interactions") {
    selectedDetail.value = { type: "interaction", id };
    return;
  }
  selectedDetail.value = { type: "record", id };
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
    label: channelsText(segment.label),
    value: Number(segment.value || 0),
    tone: segment.tone,
    pct: total > 0 ? Math.round((Number(segment.value || 0) / total) * 100) : 0,
  }));
}

function metricIcon(metric: UiMetricCard, index: number) {
  return metricIconById[metric.id] ?? [HeartPulse, RadioTower, Cable, Database, ShieldAlert, Activity, GitBranch][index % 7];
}

function metricLabel(metric: UiMetricCard) {
  return channelsText(metric.label);
}

function metricDelta(metric: UiMetricCard) {
  return channelsText(metric.delta ?? "");
}

function tabLabel(tab: OperationsTab) {
  return channelsText(tab.label);
}

function sectionTitle(section: UiTableSection | UiChartSection) {
  return channelsText(section.title);
}

function emptyState(section: UiTableSection) {
  return channelsText(section.empty_state ?? "No records.");
}

function detailItems(items: UiKeyValueItem[]) {
  return items.map((item) => ({
    ...item,
    label: channelsText(item.label),
    value: channelsText(item.value),
  }));
}

function detailPayload(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function detailSummaryValue(items: UiKeyValueItem[], label: string): string | null {
  return items.find((item) => item.label === label)?.value ?? null;
}

function normalizedReplayValue(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  if (!normalized || normalized === "-") return null;
  return normalized;
}

function channelsText(value: string | null | undefined): string {
  if (!value) return "";
  const runtimeSplit = value.match(/^(\d+) online \/ (\d+) stale$/);
  if (runtimeSplit) {
    return t("operations.channels.delta.runtimeSplit", {
      online: runtimeSplit[1],
      stale: runtimeSplit[2],
    });
  }
  const enabled = value.match(/^(\d+) enabled$/);
  if (enabled) return t("operations.channels.delta.enabled", { count: enabled[1] });
  const interactionSplit = value.match(/^(\d+) bound \/ (\d+) failed$/);
  if (interactionSplit) {
    return t("operations.channels.delta.interactionSplit", {
      bound: interactionSplit[1],
      failed: interactionSplit[2],
    });
  }
  const key = channelsTextKeys[value];
  return key ? t(key) : formatRawKeyLabel(value);
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
  selectedDetail.value = null;
  void refreshPage();
}

function resetSearch() {
  queryInput.value = "";
  submittedSearch.value = "";
  statusFilter.value = "all";
  channelTypeFilter.value = "all";
  selectedDetail.value = null;
  void refreshPage();
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadChannelsOperations({
      status: statusFilter.value,
      channel_type: channelTypeFilter.value,
      search: submittedSearch.value,
      limit: 80,
    });
    page.value = loaded.page;
    loadError.value = null;
    if (selectedDetail.value?.type === "runtime" && !loaded.page.runtime_details.some((item) => item.runtime_id === selectedDetail.value?.id)) {
      selectedDetail.value = null;
    }
    if (selectedDetail.value?.type === "record" && !loaded.page.record_details.some((item) => item.record_id === selectedDetail.value?.id)) {
      selectedDetail.value = null;
    }
    if (selectedDetail.value?.type === "interaction" && !loaded.page.interaction_details.some((item) => item.interaction_id === selectedDetail.value?.id)) {
      selectedDetail.value = null;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function pruneStaleRuntimes() {
  if (typeof window === "undefined") return;
  const reason = window.prompt(t("operations.channels.action.reasonPrompt"));
  const normalizedReason = reason?.trim();
  if (!normalizedReason) return;
  const confirmation = t("operations.channels.action.pruneStaleRuntimesConfirm", {
    reason: normalizedReason,
  });
  const confirmed = window.confirm(confirmation);
  if (!confirmed) return;
  actionBusy.value = "prune";
  actionNotice.value = null;
  loadError.value = null;
  try {
    const result = await pruneStaleChannelRuntimes({
      reason: normalizedReason,
      confirmation,
      risk_acknowledged: confirmed,
      metadata: {
        confirmation_prompt: confirmation,
      },
    });
    actionNotice.value = t("operations.channels.action.pruneStaleRuntimesNotice", {
      count: result.pruned_count,
      matched: result.matched_count,
    });
    selectedDetail.value = null;
    await refreshPage();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

async function replaySelectedDeadLetter() {
  if (typeof window === "undefined") return;
  const target = selectedDeadLetterReplayTarget.value;
  if (!target) return;
  const replayId = target.eventId ?? target.cursor ?? "-";
  const confirmation = t("operations.channels.action.replayDeadLetterConfirm", { id: replayId });
  const confirmed = window.confirm(confirmation);
  if (!confirmed) {
    return;
  }
  actionBusy.value = "replay";
  actionNotice.value = null;
  loadError.value = null;
  try {
    const result = await replayChannelDeadLetter(target.channelType, {
      runtime_id: target.runtimeId,
      cursor: target.cursor,
      event_id: target.eventId,
      confirmation,
      risk_acknowledged: confirmed,
      metadata: {
        confirmation_prompt: confirmation,
      },
    });
    actionNotice.value = t("operations.channels.action.replayDeadLetterNotice", {
      outboundId: result.outbound_id,
      mode: result.replay_mode,
      status: result.callback_status ?? "-",
    });
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
  <main class="operations-module-console channels-console scroll-area" :class="{ 'has-drawer': drawerOpen }">
    <header class="channels-header">
      <div>
        <h2>{{ channelsText(page?.title ?? "Channels") }} <span>{{ page?.health ? channelsText(page.health) : "-" }}</span></h2>
        <p>{{ channelsText(page?.subtitle ?? "聚合通道配置、运行时、绑定、死信与通道事件的运维视图。") }}</p>
      </div>
      <div class="channels-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton class="role-badge" size="sm" variant="secondary">
          <ShieldAlert :size="13" /> {{ t("operations.currentRoleLabel") }}: {{ channelsText(page?.role.label ?? "Channels operator") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="channels-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>
    <div v-if="actionNotice" class="channels-alert channels-alert--success">
      <StatusDot tone="success" />
      <span>{{ actionNotice }}</span>
    </div>

    <section class="channels-action-strip">
      <span>{{ t("operations.channels.action.stripLabel") }}</span>
      <UiButton
        size="sm"
        variant="danger"
        :disabled="loading || actionBusy !== null"
        @click="pruneStaleRuntimes"
      >
        <RefreshCcw :class="{ 'motion-spin': actionBusy === 'prune' }" :size="13" />
        {{ t("operations.channels.action.pruneStaleRuntimes") }}
      </UiButton>
    </section>

    <section class="channels-metrics">
      <template v-if="displayMetrics.length">
        <article v-for="(metric, index) in displayMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
          <span class="metric-icon"><component :is="metricIcon(metric, index)" :size="22" /></span>
          <span class="metric-copy">
            <em>{{ metricLabel(metric) }}</em>
            <strong>{{ channelsText(metric.value) }}</strong>
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

    <section class="channels-status-strip">
      <article class="flow-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(messageFlow) }}</h3>
        </div>
        <div v-if="flowSegments.length" class="chart-card-body">
          <div class="donut-visual">
            <strong>{{ messageFlow.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl class="segment-list">
            <div v-for="segment in flowSegments.slice(0, 6)" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }} <span>{{ segment.pct }}%</span></dd>
            </div>
          </dl>
        </div>
        <p v-if="!flowSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="top-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(topChannels) }}</h3>
        </div>
        <dl class="bar-list">
          <div v-for="segment in channelSegments.slice(0, 6)" :key="segment.id">
            <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
            <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
          </div>
        </dl>
        <p v-if="!channelSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="dead-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(deadLettersTable) }}</h3>
          <a href="/operations/channels?tab=dead_letters" @click.prevent="selectTab('dead_letters')">{{ t("common.viewAll") }}</a>
        </div>
        <DataTable v-if="deadLettersTable.rows.length" :columns="deadLettersTable.columns" :rows="deadLettersTable.rows" section-id="channels-dead-letters" :page-size="3" :clickable-rows="true" @row-click="selectRow" />
        <p v-if="!deadLettersTable.rows.length" class="panel-empty">{{ emptyState(deadLettersTable) }}</p>
      </article>
    </section>

    <nav class="channels-tabs">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: tab.id === activeTab }" type="button" @click="selectTab(tab.id)">
        {{ tabLabel(tab) }}<span v-if="tab.count != null">{{ tab.count }}</span>
      </button>
    </nav>

    <section class="channels-main-grid">
      <article class="channels-table-panel">
        <div class="panel-heading panel-heading--table">
          <h3>{{ sectionTitle(mainTable) }} <span>{{ mainTable.total ?? mainTable.rows.length }}</span></h3>
          <form class="table-controls" @submit.prevent="submitSearch">
            <label class="table-search">
              <Search :size="13" />
              <input v-model.trim="queryInput" type="search" :placeholder="t('operations.channels.searchPlaceholder')" />
            </label>
            <label class="status-filter">
              <span>{{ t("table.channelType") }}</span>
              <select v-model="channelTypeFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="channelType in channelTypeOptions" :key="channelType" :value="channelType">
                  {{ channelType }}
                </option>
              </select>
            </label>
            <label class="status-filter">
              <span>{{ t("table.status") }}</span>
              <select v-model="statusFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option value="online">{{ t("text.online") }}</option>
                <option value="stale">{{ t("operations.channels.status.stale") }}</option>
                <option value="error">{{ t("text.error") }}</option>
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
          section-id="channels-main-table"
          :page-size="12"
          :clickable-rows="selectableTabs.has(activeTab)"
          @row-click="selectRow"
        />
        <p v-else class="table-empty">{{ emptyState(mainTable) }}</p>
      </article>

      <aside class="channels-side-panel">
        <article class="delivery-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(deliveryTrend) }}</h3>
          </div>
          <dl class="bar-list">
            <div v-for="segment in deliverySegments" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
            </div>
          </dl>
          <p v-if="!deliverySegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
        </article>

        <article class="failure-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(failuresByCategory) }}</h3>
            <a href="/operations/channels?tab=dead_letters" @click.prevent="selectTab('dead_letters')">{{ t("common.viewAll") }}</a>
          </div>
          <dl class="bar-list">
            <div v-for="segment in failureSegments.slice(0, 6)" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
            </div>
          </dl>
          <p v-if="!failureSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
        </article>

        <article class="profiles-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(profilesTable) }}</h3>
            <a href="/operations/channels?tab=profiles" @click.prevent="selectTab('profiles')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable v-if="profilesTable.rows.length" :columns="profilesTable.columns" :rows="profilesTable.rows" section-id="channels-profiles" :page-size="3" />
          <p v-if="!profilesTable.rows.length" class="panel-empty">{{ emptyState(profilesTable) }}</p>
        </article>
      </aside>
    </section>

    <aside v-if="selectedRuntimeDetail" class="channels-drawer">
      <header>
        <div>
          <span>{{ t("operations.channels.drawer.runtime") }}</span>
          <h3>{{ selectedRuntimeDetail.title }}</h3>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedDetail = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.channels.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedRuntimeDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ channelsText(selectedRuntimeDetail.capabilities.title) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedRuntimeDetail.capabilities.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedRuntimeDetail.connection_bindings) }}</h4>
        <DataTable :columns="selectedRuntimeDetail.connection_bindings.columns" :rows="selectedRuntimeDetail.connection_bindings.rows" section-id="channels-detail-connections" :page-size="5" />
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedRuntimeDetail.account_bindings) }}</h4>
        <DataTable :columns="selectedRuntimeDetail.account_bindings.columns" :rows="selectedRuntimeDetail.account_bindings.rows" section-id="channels-detail-accounts" :page-size="5" />
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedRuntimeDetail.events) }}</h4>
        <DataTable :columns="selectedRuntimeDetail.events.columns" :rows="selectedRuntimeDetail.events.rows" section-id="channels-detail-events" :page-size="5" />
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedRuntimeDetail.dead_letters) }}</h4>
        <DataTable :columns="selectedRuntimeDetail.dead_letters.columns" :rows="selectedRuntimeDetail.dead_letters.rows" section-id="channels-detail-dead-letters" :page-size="5" />
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.channels.drawer.raw") }}</h4>
        <pre>{{ detailPayload(selectedRuntimeDetail.raw_payload) }}</pre>
      </section>
    </aside>

    <aside v-else-if="selectedInteractionDetail" class="channels-drawer">
      <header>
        <div>
          <span>{{ t("operations.channels.drawer.interaction") }}</span>
          <h3>{{ selectedInteractionDetail.title }}</h3>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedDetail = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.channels.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedInteractionDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ channelsText(selectedInteractionDetail.routing.title) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedInteractionDetail.routing.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ channelsText(selectedInteractionDetail.reply_address.title) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedInteractionDetail.reply_address.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ channelsText(selectedInteractionDetail.metadata.title) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedInteractionDetail.metadata.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedInteractionDetail.events) }}</h4>
        <DataTable :columns="selectedInteractionDetail.events.columns" :rows="selectedInteractionDetail.events.rows" section-id="channels-interaction-events" :page-size="5" />
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.channels.drawer.raw") }}</h4>
        <pre>{{ detailPayload(selectedInteractionDetail.raw_payload) }}</pre>
      </section>
    </aside>

    <aside v-else-if="selectedRecordDetail" class="channels-drawer">
      <header>
        <div>
          <span>{{ t("operations.channels.drawer.record") }}</span>
          <h3>{{ selectedRecordDetail.title }}</h3>
        </div>
        <div class="drawer-actions">
          <button
            v-if="selectedDeadLetterReplayTarget"
            class="drawer-command drawer-command--danger"
            type="button"
            :disabled="loading || actionBusy !== null"
            @click="replaySelectedDeadLetter"
          >
            <RefreshCcw :class="{ 'motion-spin': actionBusy === 'replay' }" :size="13" />
            {{ t("operations.channels.action.replayDeadLetter") }}
          </button>
          <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedDetail = null">
            <X :size="16" />
          </button>
        </div>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.channels.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedRecordDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.channels.drawer.payload") }}</h4>
        <pre>{{ detailPayload(selectedRecordDetail.payload) }}</pre>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.channels.drawer.trace") }}</h4>
        <pre>{{ detailPayload(selectedRecordDetail.trace) }}</pre>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedRecordDetail.related) }}</h4>
        <DataTable :columns="selectedRecordDetail.related.columns" :rows="selectedRecordDetail.related.rows" section-id="channels-record-related" :page-size="5" />
      </section>
    </aside>
  </main>
</template>

<style scoped>
.channels-console {
  height: 100%;
  overflow: auto;
  padding: 8px 12px 12px;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
  scrollbar-gutter: stable;
}

.channels-header,
.channels-header__ops,
.channels-metrics,
.channels-tabs,
.panel-heading,
.chart-card-body,
.channels-alert,
.channels-action-strip,
.auto-toggle,
.table-controls,
.table-search,
.status-filter {
  display: flex;
  align-items: center;
}

.channels-header {
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

.channels-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channels-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.channels-header__ops strong {
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

.channels-alert {
  gap: 8px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, var(--border-subtle));
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--surface-panel));
  color: var(--text-secondary);
  font-size: 11px;
}

.channels-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 35%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 9%, var(--surface-panel));
}

.channels-action-strip {
  justify-content: flex-end;
  gap: 6px;
  min-height: 28px;
  margin-bottom: 4px;
  padding: 2px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 88%, transparent);
}

.channels-action-strip span {
  margin-right: auto;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.channels-metrics {
  display: grid;
  grid-template-columns: repeat(8, minmax(96px, 1fr));
  gap: 6px;
}

.metric,
.channels-status-strip > article,
.channels-table-panel,
.channels-side-panel > article {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
}

.metric {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 6px;
  align-items: center;
  height: 64px;
  min-height: 0;
  padding: 5px 9px;
  overflow: hidden;
}

.metric-icon {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
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
  line-height: 1.1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-copy strong {
  display: block;
  margin: 2px 0 1px;
  font-size: 16px;
  line-height: 1;
}

.metric--success .metric-icon,
.metric--success strong {
  color: var(--color-success);
}

.metric--warning .metric-icon,
.metric--warning strong {
  color: var(--color-warning);
}

.metric--danger .metric-icon,
.metric--danger strong {
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

.channels-status-strip {
  display: grid;
  grid-template-columns: minmax(220px, 0.72fr) minmax(220px, 0.7fr) minmax(360px, 1.25fr);
  gap: 6px;
  margin-top: 6px;
}

.channels-status-strip > article,
.channels-side-panel > article,
.channels-table-panel {
  min-width: 0;
  padding: 8px;
}

.flow-panel,
.top-panel,
.dead-panel {
  min-height: 118px;
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
  text-decoration: none;
}

.panel-heading h3 span {
  color: var(--text-muted);
}

.chart-card-body {
  gap: 9px;
  min-height: 76px;
}

.donut-visual {
  display: grid;
  flex: 0 0 76px;
  width: 76px;
  height: 76px;
  place-items: center;
  align-content: center;
  border: 10px solid color-mix(in srgb, var(--color-blue) 46%, var(--border-subtle));
  border-radius: 50%;
}

.donut-visual strong {
  font-size: 20px;
  line-height: 1;
}

.donut-visual span {
  color: var(--text-muted);
  font-size: 10px;
}

.segment-list,
.bar-list {
  display: grid;
  flex: 1;
  gap: 8px;
  min-width: 0;
}

.segment-list div,
.bar-list div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 11px;
}

.segment-list dt,
.bar-list dt {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.segment-list dd,
.bar-list dd {
  display: grid;
  grid-template-columns: minmax(44px, 1fr) 34px;
  gap: 8px;
  align-items: center;
  margin: 0;
  font-weight: 700;
  text-align: right;
}

.segment-list dd span {
  color: var(--text-muted);
  font-weight: 500;
}

.bar-list dd span {
  display: block;
  height: 4px;
  border-radius: 99px;
  background: var(--color-blue);
}

.panel-empty,
.table-empty {
  display: grid;
  flex: 1 1 auto;
  min-height: 54px;
  place-items: center;
  color: var(--text-muted);
  font-size: 11px;
  text-align: center;
}

.channels-tabs {
  gap: 8px;
  min-height: 29px;
  margin-top: 6px;
  padding: 0;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  border-radius: 0;
  overflow-x: auto;
}

.channels-tabs button {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
  height: 29px;
  padding: 0 8px;
  border: 0;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
}

.channels-tabs button.active {
  background: var(--surface-panel-soft);
  color: var(--text-primary);
}

.channels-tabs span {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 99px;
  background: color-mix(in srgb, var(--color-blue) 16%, transparent);
  color: var(--color-blue);
  font-size: 10px;
  text-align: center;
}

.channels-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 6px;
  margin-top: 6px;
  align-items: start;
}

.channels-table-panel {
  display: flex;
  flex-direction: column;
  min-height: clamp(340px, calc(100dvh - var(--shell-topbar-height) - 420px), 520px);
}

.channels-table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.panel-heading--table {
  align-items: flex-start;
  margin-bottom: 10px;
}

.table-controls {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

.table-search {
  gap: 7px;
  width: min(320px, 34vw);
  height: 30px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-muted);
}

.table-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
}

.status-filter {
  gap: 6px;
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-muted);
  font-size: 11px;
}

.status-filter select {
  max-width: 130px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.channels-side-panel {
  display: grid;
  gap: 6px;
}

.delivery-panel,
.failure-panel,
.profiles-panel {
  min-height: 118px;
  overflow: visible;
}

.channels-drawer {
  position: fixed;
  top: calc(var(--shell-topbar-height) + 16px);
  right: 20px;
  bottom: 20px;
  z-index: 20;
  width: min(460px, calc(100vw - 36px));
  overflow: auto;
  padding: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 96%, var(--surface-page));
  box-shadow: var(--shadow-floating);
}

.channels-drawer > header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.channels-drawer > header span {
  color: var(--text-muted);
  font-size: 11px;
  text-transform: uppercase;
}

.channels-drawer > header h3 {
  margin-top: 3px;
  word-break: break-word;
}

.channels-drawer > header button {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  cursor: pointer;
}

.drawer-actions {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.channels-drawer > header .drawer-actions .drawer-command {
  display: inline-flex;
  width: auto;
  min-width: 0;
  gap: 6px;
  padding: 0 9px;
  font-size: 12px;
  font-weight: 650;
  white-space: nowrap;
}

.channels-drawer > header .drawer-actions .drawer-command--danger {
  border-color: color-mix(in srgb, var(--color-danger) 38%, var(--border-subtle));
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, var(--surface-panel-soft));
}

.channels-drawer > header .drawer-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.drawer-section {
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}

.drawer-section h4 {
  margin-bottom: 8px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.detail-grid div {
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.detail-grid dt {
  color: var(--text-muted);
  font-size: 10px;
}

.detail-grid dd {
  margin: 4px 0 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
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

.tone-info {
  color: var(--color-blue);
}

pre {
  max-height: 260px;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1280px) {
  .channels-metrics {
    grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  }

  .channels-status-strip,
  .channels-main-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .channels-drawer {
    top: 70px;
    right: 12px;
    bottom: 12px;
    width: min(420px, calc(100vw - 24px));
  }
}

@media (max-width: 760px) {
  .channels-console {
    padding: 8px 10px 10px;
  }

  .channels-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .channels-header__ops {
    justify-content: flex-start;
  }

  .channels-metrics,
  .channels-status-strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .metric {
    flex: 0 0 150px;
  }

  .channels-status-strip > article {
    flex: 0 0 286px;
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
}
</style>
