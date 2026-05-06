<script setup lang="ts">
import { Brain, CircleX, Clock3, Database, Gauge, HeartPulse, Radio, RefreshCcw, Search, ShieldAlert, X } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime } from "@/shared/i18n/formatters";
import type {
  OperationsLlmInvocationDetail,
  OperationsLlmReadModel,
  OperationsTab,
  UiChartSection,
  UiKeyValueItem,
  UiKeyValueSection,
  UiMetricCard,
  UiTableColumn,
  UiTableRow,
  UiTableSection,
  UiTone,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { loadLlmInvocationDetail, loadLlmOperations } from "../api";

interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

type DataTableRow = UiTableRow | Record<string, unknown>;

const { t } = useI18n();
const metricIcons = [HeartPulse, Brain, Database, Radio, CircleX, Clock3] as const;
const metricIconById: Record<string, unknown> = {
  health: HeartPulse,
  invocations: Brain,
  tokens: Database,
  streaming: Radio,
  errors: CircleX,
  latency: Clock3,
  profiles: Brain,
  active_invocations: Radio,
  failed_invocations: CircleX,
  context: Gauge,
};
const knownTabIds = new Set([
  "invocations",
  "streaming",
  "rate_limits",
  "token_usage",
  "errors",
  "models",
  "providers",
  "events",
]);
const fallbackTabs: OperationsTab[] = [
  { id: "invocations", label: "Invocations" },
  { id: "streaming", label: "Streaming Requests" },
  { id: "rate_limits", label: "Rate Limits" },
  { id: "token_usage", label: "Token Usage" },
  { id: "errors", label: "Errors" },
  { id: "models", label: "Models" },
  { id: "providers", label: "Providers" },
  { id: "events", label: "Events" },
];
const llmTextKeys: Record<string, string> = {
  "LLM Runtime": "operations.llm.title",
  "模型调用、流式输出、限流等待、访问阻塞、Token 与错误的运维视图。": "operations.llm.subtitle",
  "Overall Health": "operations.llm.metric.health",
  "Invocations": "operations.llm.metric.invocations",
  "LLM Profiles": "operations.llm.metric.profiles",
  "Active Invocations": "operations.llm.metric.activeInvocations",
  "Failed Invocations": "operations.llm.metric.failedInvocations",
  "Tokens": "common.tokens",
  "Streaming": "operations.llm.metric.streaming",
  "Errors": "operations.llm.metric.errors",
  "Avg Latency": "operations.llm.metric.avgLatency",
  "Max Context": "operations.llm.metric.maxContext",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "LLM runtime state is queryable": "operations.llm.delta.queryable",
  "Operator attention recommended": "operations.llm.delta.attentionRecommended",
  "Operator action required": "operations.llm.delta.actionRequired",
  "Insufficient data": "operations.llm.delta.insufficientData",
  "reported by providers": "operations.llm.delta.reportedByProviders",
  "stream-capable or observed stream calls": "operations.llm.delta.streamCapable",
  "failed retained invocations": "operations.llm.delta.failedRetained",
  "retained invocation records": "operations.llm.delta.retainedInvocations",
  "largest configured window": "operations.llm.delta.largestConfiguredWindow",
  "Streaming Requests": "operations.llm.tab.streaming",
  "Rate Limits": "operations.llm.tab.rateLimits",
  "Token Usage": "operations.llm.tab.tokenUsage",
  "Models": "operations.llm.tab.models",
  "Providers": "operations.llm.tab.providers",
  "Events": "operations.llm.tab.events",
  "Provider Access & Health": "operations.llm.section.providerAccessHealth",
  "Provider Auth / Access Blocked": "operations.llm.section.providerAuthBlocked",
  "Model Resolver": "operations.llm.section.modelResolver",
  "LLM Rate Limiter": "operations.llm.section.rateLimiter",
  "Execution Blocking Risk": "operations.llm.section.executionBlockingRisk",
  "Recent Invocations": "operations.llm.section.recentInvocations",
  "Latency": "operations.llm.section.latency",
  "Invocation Rate": "operations.llm.section.invocationRate",
  "Stream Health": "operations.llm.section.streamHealth",
  "Model Availability": "operations.llm.section.modelAvailability",
  "Error Summary": "operations.llm.section.errorSummary",
  "LLM Lifecycle Events": "operations.llm.section.lifecycleEvents",
  "Context Window Pressure": "operations.llm.section.contextPressure",
  "Fallback / Resolver Problems": "operations.llm.section.fallbackProblems",
  "Active": "common.active",
  "Waiting": "status.waiting",
  "Configured Capacity": "operations.llm.kv.configuredCapacity",
  "Constrained Profiles": "operations.llm.kv.constrainedProfiles",
  "Avg Wait": "operations.llm.kv.avgWait",
  "Max Wait": "operations.llm.kv.maxWait",
  "Running Invocations": "operations.llm.kv.runningInvocations",
  "Limiter Waiters": "operations.llm.kv.limiterWaiters",
  "Saturated Profiles": "operations.llm.kv.saturatedProfiles",
  "Oldest Running": "operations.llm.kv.oldestRunning",
  "Active Streams": "operations.llm.kv.activeStreams",
  "Completed Streams": "operations.llm.kv.completedStreams",
  "Failed Streams": "operations.llm.kv.failedStreams",
  "Delta Events": "operations.llm.kv.deltaEvents",
  "Longest Active": "operations.llm.kv.longestActive",
  "Stream-capable Profiles": "operations.llm.kv.streamCapableProfiles",
  "Agent Default": "text.agentDefault",
  "Explicit Override": "text.explicitOverride",
  "Fallback Used": "text.fallbackUsed",
  "No Match / Error": "text.noMatchError",
  "Input": "text.input",
  "Output": "text.output",
  "Reasoning": "text.reasoning",
  "Unclassified": "text.unclassified",
  "Succeeded": "status.success",
  "Failed": "status.failed",
  "Running": "status.running",
  "Created": "status.created",
  "Yes": "common.yes",
  "No": "common.no",
  "Configured": "text.configured",
  "Status": "table.status",
  "Level": "table.level",
  "Event": "table.event",
  "Entity": "table.entity",
  "Profile": "table.profile",
  "Provider": "table.provider",
  "Model": "common.model",
  "Started At": "table.startedAt",
  "Completed At": "table.completedAt",
  "Duration": "table.duration",
  "Messages": "operations.llm.kv.messages",
  "Tool Schemas": "operations.llm.kv.toolSchemas",
  "Response Format": "operations.llm.kv.responseFormat",
  "Provider Request ID": "operations.llm.kv.providerRequestId",
  "Requested": "operations.llm.kv.requested",
  "Resolved": "operations.llm.kv.resolved",
  "Strategy": "operations.llm.kv.strategy",
  "Decision": "operations.llm.kv.decision",
  "Run ID": "table.runId",
  "Turn ID": "table.turnId",
  "Trace": "table.trace",
  "Category": "table.category",
  "Error Code": "table.errorCode",
  "Retryable": "table.retryable",
  "Error Facts": "operations.llm.section.errorFacts",
  "Invocation Events": "operations.llm.section.invocationEvents",
  "Limiter Queue": "operations.llm.section.limiterQueue",
  "Resolver Decision": "operations.llm.section.resolverDecision",
  "Connecting": "operations.llm.stream.connecting",
  "Completed": "status.completed",
  "completed": "status.completed",
  "credential binding": "text.credentialBinding",
  "waiting for limiter slot": "operations.llm.limiter.waitingForSlot",
  "profile saturated": "operations.llm.limiter.profileSaturated",
  "capacity available": "operations.llm.limiter.capacityAvailable",
  "No LLM limiter queue observed.": "operations.llm.empty.noLimiterQueue",
  "No records.": "table.noRecords",
  "No LLM invocations match the current filters.": "operations.llm.empty.noMatches",
  "No LLM invocations recorded yet.": "operations.llm.empty.noInvocations",
  "No LLM profiles configured.": "operations.llm.empty.noProfiles",
  "No provider access blockers.": "operations.llm.empty.noAccessBlockers",
  "No streaming LLM invocations observed.": "operations.llm.empty.noStreaming",
  "No failed LLM invocations.": "operations.llm.empty.noFailures",
  "No LLM lifecycle events observed yet.": "operations.llm.empty.noLifecycle",
  "No observed events for this invocation.": "operations.llm.empty.noInvocationEvents",
  "No resolver fallback problems observed.": "operations.llm.empty.noResolverProblems",
};

const page = ref<OperationsLlmReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedInvocationId = ref<string | null>(null);
const selectedEventRow = ref<UiTableRow | null>(null);
const loadedInvocationDetails = ref<Record<string, OperationsLlmInvocationDetail>>({});
const invocationDetailLoading = ref(false);
const invocationDetailError = ref<string | null>(null);
const searchFilter = ref("");
const statusFilter = ref("all");
const streamingFilter = ref("all");
const invocationOffset = ref(0);
const refreshTimer = ref<number | null>(null);

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "invocations";
  return knownTabIds.has(candidate) ? candidate : "invocations";
});
const providerAccessTable = computed(() => page.value?.provider_access_health ?? emptyTable("provider_access_health", "Provider Access & Health"));
const authBlockedTable = computed(() => page.value?.provider_auth_blocked ?? emptyTable("provider_auth_blocked", "Provider Auth / Access Blocked"));
const recentInvocationsTable = computed(() => page.value?.recent_invocations ?? emptyTable("recent_invocations", "Recent Invocations"));
const failedInvocationsTable = computed(() => page.value?.failed_invocations ?? emptyTable("failed_invocations", "Failed Invocations"));
const streamingRequestsTable = computed(() => page.value?.streaming_requests ?? emptyTable("streaming_requests", "Streaming Requests"));
const limiterQueueTable = computed(() => page.value?.limiter_queue ?? emptyTable("limiter_queue", "Limiter Queue"));
const modelAvailabilityTable = computed(() => page.value?.model_availability ?? emptyTable("model_availability", "Model Availability"));
const errorSummaryTable = computed(() => page.value?.error_summary ?? emptyTable("error_summary", "Error Summary"));
const fallbackProblemsTable = computed(() => page.value?.fallback_problems ?? emptyTable("fallback_problems", "Fallback / Resolver Problems"));
const lifecycleEventsTable = computed(() => page.value?.llm_lifecycle_events ?? emptyTable("llm_lifecycle_events", "LLM Lifecycle Events"));
const rateLimiterSection = computed(() => page.value?.rate_limiter ?? emptyKeyValue("rate_limiter", "LLM Rate Limiter"));
const streamHealthSection = computed(() => page.value?.stream_health ?? emptyKeyValue("stream_health", "Stream Health"));
const blockingRiskSection = computed(() => page.value?.execution_blocking_risk ?? emptyKeyValue("execution_blocking_risk", "Execution Blocking Risk"));
const resolverChart = computed(() => chartFromSection(page.value?.model_resolver));
const tokenChart = computed(() => page.value?.token_usage);
const latencyChart = computed(() => page.value?.latency);
const invocationRateChart = computed(() => page.value?.invocation_rate);
const contextPressureChart = computed(() => page.value?.context_pressure);
const chartCards = computed(() => [
  tokenChart.value,
  invocationRateChart.value,
  latencyChart.value,
  contextPressureChart.value,
].filter(Boolean) as UiChartSection[]);
const providerAccessCompactTable = computed<UiTableSection>(() => ({
  ...providerAccessTable.value,
  columns: [
    { key: "profile", label: "LLM Profile" },
    { key: "provider", label: "Provider" },
    { key: "model", label: "Model" },
    { key: "status", label: "Status" },
    { key: "invocations", label: "Invocations" },
    { key: "last_invocation", label: "Last Invocation" },
  ],
}));
const recentInvocationsCompactTable = computed<UiTableSection>(() => ({
  ...recentInvocationsTable.value,
  columns: [
    { key: "time", label: "Time" },
    { key: "invocation_id", label: "Invocation ID" },
    { key: "provider_model", label: "Provider / Model" },
    { key: "status", label: "Status" },
    { key: "run_id", label: "Run ID" },
    { key: "trace", label: "Trace" },
    { key: "duration", label: "Duration" },
    { key: "streaming", label: "Streaming" },
    { key: "tokens", label: "Tokens" },
    { key: "finish_reason", label: "Finish Reason" },
    { key: "error_code", label: "Error Code" },
    { key: "actions", label: "Actions" },
  ],
}));
const streamTrendItems = computed(() => {
  const items = streamHealthSection.value.items.slice(0, 3);
  const max = Math.max(...items.map((item) => numericValue(item.value)), 1);
  return items.map((item) => ({
    id: item.label,
    label: opsText(item.label),
    value: opsText(item.value),
    tone: item.tone ?? "neutral",
    pct: Math.max(4, Math.min(100, Math.round((numericValue(item.value) / max) * 100))),
  }));
});
const streamHealthVisibleItems = computed(() => streamHealthSection.value.items.slice(0, 4));
const mainTable = computed(() => {
  if (activeTab.value === "streaming") return streamingRequestsTable.value;
  if (activeTab.value === "rate_limits") return limiterQueueTable.value;
  if (activeTab.value === "token_usage") return chartAsTable(page.value?.token_usage, "token_usage_table", "Token Usage");
  if (activeTab.value === "errors") return failedInvocationsTable.value;
  if (activeTab.value === "models") return modelAvailabilityTable.value;
  if (activeTab.value === "providers") return providerAccessTable.value;
  if (activeTab.value === "events") return lifecycleEventsTable.value;
  return recentInvocationsTable.value;
});
const displayMainTable = computed(() => displayTableSection(mainTable.value));
const displayInvocationTable = computed(() => displayTableSection(recentInvocationsCompactTable.value));
const mainTablePageSize = computed(() => {
  if (activeTab.value === "events") return 6;
  if (activeTab.value === "invocations") return 8;
  return 6;
});
const selectedDetail = computed(() => {
  if (!selectedInvocationId.value) return null;
  const details = [
    ...(page.value?.invocation_details ?? []),
    ...Object.values(loadedInvocationDetails.value),
  ];
  return details.find((item) => item.invocation_id === selectedInvocationId.value) ?? null;
});
const activeStreamItem = computed(() => streamHealthSection.value.items.find((item) => item.label === "Active Streams") ?? null);
const limiterWaiterItem = computed(() => rateLimiterSection.value.items.find((item) => item.label === "Waiting" || item.label === "Limiter Waiters") ?? null);
const riskItems = computed(() => [
  { id: "auth", label: t("operations.llm.risk.accessBlocked"), value: String(authBlockedTable.value.total ?? authBlockedTable.value.rows.length), tone: (authBlockedTable.value.rows.length ? "warning" : "success") as UiTone },
  { id: "stream", label: t("operations.llm.risk.activeStreaming"), value: activeStreamItem.value?.value ?? "0", tone: (Number(activeStreamItem.value?.value ?? 0) ? "info" : "success") as UiTone },
  { id: "waiters", label: t("operations.llm.risk.rateLimitWaiters"), value: limiterWaiterItem.value?.value ?? "0", tone: (Number(limiterWaiterItem.value?.value ?? 0) ? "warning" : "success") as UiTone },
  { id: "fallback", label: t("operations.llm.risk.resolverIssues"), value: String(fallbackProblemsTable.value.total ?? fallbackProblemsTable.value.rows.length), tone: (fallbackProblemsTable.value.rows.length ? "warning" : "success") as UiTone },
]);
const hasDrawer = computed(() => Boolean(selectedDetail.value || selectedInvocationId.value || selectedEventRow.value));
const selectedEventTitle = computed(() => {
  const row = selectedEventRow.value;
  if (!row) return "";
  return cellText(row, "event") ?? row.id;
});
const selectedEventSubtitle = computed(() => {
  const row = selectedEventRow.value;
  if (!row) return "";
  return [cellText(row, "level"), cellText(row, "status"), cellText(row, "entity")]
    .filter((item) => item && item !== "-")
    .join(" · ");
});
const selectedEventFields = computed(() => {
  const row = selectedEventRow.value;
  if (!row) return [];
  return ["time", "level", "event", "entity", "status", "trace"]
    .map((key) => ({
      key,
      label: eventFieldLabel(key),
      value: eventFieldValue(row, key),
    }))
    .filter((item) => item.value && item.value !== "-");
});
const selectedEventDetails = computed(() => {
  const row = selectedEventRow.value;
  if (!row) return "-";
  return cellText(row, "details") ?? "-";
});

watch([statusFilter, streamingFilter], () => {
  invocationOffset.value = 0;
  void refreshPage();
});

let searchTimer: number | null = null;
watch(searchFilter, () => {
  invocationOffset.value = 0;
  if (searchTimer !== null) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    void refreshPage();
  }, 220);
});

function metricIcon(metric: UiMetricCard, index: number) {
  return metricIconById[metric.id] ?? metricIcons[index % metricIcons.length];
}

function opsText(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const key = llmTextKeys[value];
  if (key) return t(key);
  const unsupportedCredentialBindingSource = value.match(/^unsupported credential binding source '(.+)'\.$/i);
  if (unsupportedCredentialBindingSource) {
    return t("operations.llm.reason.unsupportedCredentialBindingSource", {
      source: unsupportedCredentialBindingSource[1],
    });
  }
  const running = value.match(/^(\d+) running$/);
  if (running) return t("operations.llm.delta.running", { count: running[1] });
  const configuredProfiles = value.match(/^(\d+) configured profiles$/);
  if (configuredProfiles) {
    return t("operations.llm.delta.configuredProfiles", { count: configuredProfiles[1] });
  }
  return value;
}

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
  closeDrawer();
}

function selectMainTableRow(row: DataTableRow) {
  if (activeTab.value === "events") {
    selectEventFromRow(row);
    return;
  }
  selectInvocationFromRow(row);
}

function selectInvocationFromRow(row: DataTableRow) {
  selectedEventRow.value = null;
  const candidates = [
    rowId(row),
    cellText(row, "invocation_id"),
    cellText(row, "last_invocation"),
    cellText(row, "entity"),
  ].filter(Boolean) as string[];
  const invocationId = candidates.find((item) => item && item !== "-") ?? null;
  selectedInvocationId.value = invocationId;
  if (invocationId) void ensureInvocationDetail(invocationId);
}

function selectEventFromRow(row: DataTableRow) {
  if (!isUiTableRow(row)) return;
  selectedInvocationId.value = null;
  selectedEventRow.value = row;
}

function closeDrawer() {
  selectedInvocationId.value = null;
  selectedEventRow.value = null;
  invocationDetailError.value = null;
}

function isUiTableRow(row: DataTableRow): row is UiTableRow {
  return Boolean("cells" in row && row.cells && typeof row.cells === "object");
}

function rowId(row: DataTableRow): string | null {
  if ("id" in row && typeof row.id === "string") return row.id;
  return null;
}

function cellText(row: DataTableRow, key: string): string | null {
  const raw = "cells" in row && row.cells
    ? (row.cells as Record<string, unknown>)[key]
    : (row as Record<string, unknown>)[key];
  if (raw === null || raw === undefined || raw === "") return null;
  if (typeof raw === "object" && "text" in raw) return String(raw.text);
  return String(raw);
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

function emptyKeyValue(id: string, title: string): UiKeyValueSection {
  return { id, title, items: [] };
}

function displayTableSection(section: UiTableSection): UiTableSection {
  if (section.id !== "llm_lifecycle_events") return section;
  return {
    ...section,
    columns: section.columns.filter((column) => normalizeColumnKey(column.key) !== "details"),
  };
}

function normalizeColumnKey(key: string): string {
  return key.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function eventFieldLabel(key: string): string {
  return {
    time: t("table.time"),
    level: t("table.level"),
    event: t("table.event"),
    entity: t("table.entity"),
    status: t("table.status"),
    trace: t("table.trace"),
  }[key] ?? key;
}

function eventFieldValue(row: UiTableRow, key: string): string {
  const value = cellText(row, key) ?? "-";
  return key === "time" && /^\d{4}-\d{2}-\d{2}T/.test(value)
    ? formatLocalTime(value)
    : opsText(value);
}

function chartFromSection(section: UiChartSection | UiTableSection | undefined): UiChartSection | null {
  if (!section || !("kind" in section)) return null;
  return section;
}

function chartSegments(chart: UiChartSection | null | undefined): ChartSegmentView[] {
  const segments = chart?.segments ?? [];
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  return segments.map((item) => ({
    ...item,
    pct: total ? Math.round((item.value / total) * 100) : 0,
  }));
}

function chartTotal(chart: UiChartSection | null | undefined): string {
  const total = chart?.total ?? 0;
  return String(total);
}

function donutStyle(chart: UiChartSection | null | undefined) {
  const segments = chartSegments(chart);
  if (!segments.length) {
    return { background: "var(--surface-panel-soft)" };
  }
  let cursor = 0;
  const stops = segments.map((segment) => {
    const next = cursor + segment.pct;
    const stop = `${toneColor(segment.tone)} ${cursor}% ${Math.max(next, cursor + 1)}%`;
    cursor = next;
    return stop;
  });
  return { background: `conic-gradient(${stops.join(", ")})` };
}

function toneColor(tone: UiTone): string {
  return {
    neutral: "var(--text-muted)",
    info: "var(--color-blue)",
    success: "var(--color-success)",
    warning: "var(--color-warning)",
    danger: "var(--color-danger)",
  }[tone];
}

function numericValue(value: string | number): number {
  const parsed = Number(String(value).replace(/[^\d.-]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function keyValueAsTable(section: UiKeyValueSection): UiTableSection {
  return {
    id: `${section.id}_table`,
    title: section.title,
    columns: [
      { key: "label", label: "Name" },
      { key: "value", label: "Value" },
      { key: "tone", label: "Status" },
    ],
    rows: section.items.map((item) => ({
      id: item.label,
      cells: { label: item.label, value: item.value, tone: item.tone ?? "neutral" },
      status: item.tone ?? "neutral",
      tone: item.tone ?? "neutral",
    })),
    total: section.items.length,
    empty_state: "No records.",
  };
}

function chartAsTable(chart: UiChartSection | null | undefined, id: string, title: string): UiTableSection {
  const segments = chartSegments(chart);
  return {
    id,
    title: chart?.title ?? title,
    columns: [
      { key: "label", label: "Category" },
      { key: "value", label: "Count" },
      { key: "percent", label: "Percent" },
    ],
    rows: segments.map((segment) => ({
      id: segment.id,
      cells: {
        label: segment.label,
        value: String(segment.value),
        percent: `${segment.pct}%`,
      },
      status: segment.tone,
      tone: segment.tone,
    })),
    total: segments.length,
    empty_state: "No records.",
  };
}

function detailPayload(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function detailItems(section: UiKeyValueItem[]) {
  return section.length ? section : [{ label: "-", value: "-", tone: "neutral" as UiTone }];
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadLlmOperations({
      status: statusFilter.value,
      streaming: streamingFilter.value,
      search: searchFilter.value.trim(),
      limit: 80,
      offset: invocationOffset.value,
    });
    page.value = loaded.page;
    loadError.value = null;
    if (selectedEventRow.value && !loaded.page.llm_lifecycle_events.rows.some((item) => item.id === selectedEventRow.value?.id)) {
      selectedEventRow.value = null;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function ensureInvocationDetail(invocationId: string) {
  if (loadedInvocationDetails.value[invocationId]) return;
  invocationDetailLoading.value = true;
  invocationDetailError.value = null;
  try {
    const detail = await loadLlmInvocationDetail(invocationId);
    if (detail) {
      loadedInvocationDetails.value = {
        ...loadedInvocationDetails.value,
        [detail.invocation_id]: detail,
      };
    }
  } catch (error) {
    invocationDetailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    invocationDetailLoading.value = false;
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
  if (searchTimer !== null) {
    window.clearTimeout(searchTimer);
    searchTimer = null;
  }
});
</script>

<template>
  <main class="operations-module-console llm-console scroll-area" :class="{ 'has-drawer': hasDrawer }">
    <header class="llm-header">
      <div>
        <h2>{{ opsText(page?.title ?? "LLM Runtime") }}</h2>
        <p>{{ opsText(page?.subtitle ?? "模型调用、流式输出、限流等待、访问阻塞、Token 与错误的运维视图。") }}</p>
      </div>
      <div class="llm-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <span class="role-badge"><ShieldAlert :size="13" /> {{ t("common.roleAdminOperable") }}</span>
      </div>
    </header>

    <div v-if="loadError" class="llm-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>

    <section class="llm-metrics">
      <article v-for="(metric, index) in displayMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
        <span class="metric-icon"><component :is="metricIcon(metric, index)" :size="19" /></span>
        <span class="metric-copy">
          <em>{{ opsText(metric.label) }}</em>
          <strong>{{ metric.value }}</strong>
          <small>{{ opsText(metric.delta) }}</small>
        </span>
      </article>
    </section>

    <section class="llm-status-strip">
      <article v-for="item in riskItems" :key="item.id" :class="`strip-item strip-item--${item.tone}`">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <section class="llm-overview-grid">
      <article class="panel panel--profiles">
        <div class="panel-heading">
          <h3>{{ opsText(providerAccessTable.title) }}</h3>
          <span>{{ providerAccessTable.total ?? providerAccessTable.rows.length }}</span>
        </div>
        <DataTable :columns="providerAccessCompactTable.columns" :rows="providerAccessCompactTable.rows" section-id="provider-access-health" :page-size="3" />
      </article>

      <article class="panel">
        <div class="panel-heading">
          <h3>{{ opsText(rateLimiterSection.title) }}</h3>
        </div>
        <dl class="kv-grid">
          <div v-for="item in rateLimiterSection.items" :key="item.label">
            <dt>{{ opsText(item.label) }}</dt>
            <dd><StatusDot :tone="item.tone ?? 'neutral'" />{{ opsText(item.value) }}</dd>
          </div>
        </dl>
      </article>

      <article class="panel panel--resolver">
        <div class="panel-heading">
          <h3>{{ opsText(resolverChart?.title ?? "Model Resolver") }}</h3>
          <span>{{ chartTotal(resolverChart) }}</span>
        </div>
        <div class="donut-row">
          <div class="donut" :style="donutStyle(resolverChart)">
            <strong>{{ chartTotal(resolverChart) }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <ul>
            <li v-for="segment in chartSegments(resolverChart)" :key="segment.id">
              <StatusDot :tone="segment.tone" />
              <span>{{ opsText(segment.label) }}</span>
              <strong>{{ segment.value }}</strong>
            </li>
            <li v-if="!chartSegments(resolverChart).length" class="empty-inline">{{ t("operations.llm.empty.noResolverEvents") }}</li>
          </ul>
        </div>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <h3>{{ opsText(blockingRiskSection.title) }}</h3>
        </div>
        <dl class="kv-grid">
          <div v-for="item in blockingRiskSection.items" :key="item.label">
            <dt>{{ opsText(item.label) }}</dt>
            <dd><StatusDot :tone="item.tone ?? 'neutral'" />{{ opsText(item.value) }}</dd>
          </div>
        </dl>
      </article>
    </section>

    <section class="llm-workspace">
      <div class="llm-main">
        <article class="panel table-panel">
          <nav class="llm-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              :class="{ active: activeTab === tab.id }"
              @click="selectTab(tab.id)"
            >
              <span>{{ opsText(tab.label) }}</span>
              <em v-if="tab.count !== undefined">{{ tab.count }}</em>
            </button>
          </nav>
          <div class="table-toolbar">
            <label class="search-box">
              <Search :size="13" />
              <input v-model="searchFilter" type="search" :placeholder="t('operations.llm.searchPlaceholder')" />
            </label>
            <select v-model="statusFilter">
              <option value="all">{{ t("operations.llm.filter.allStatuses") }}</option>
              <option value="running">{{ t("status.running") }}</option>
              <option value="succeeded">{{ t("status.success") }}</option>
              <option value="failed">{{ t("status.failed") }}</option>
            </select>
            <select v-model="streamingFilter">
              <option value="all">{{ t("operations.llm.filter.allModes") }}</option>
              <option value="yes">{{ t("operations.llm.filter.streamingOnly") }}</option>
              <option value="no">{{ t("operations.llm.filter.nonStreaming") }}</option>
            </select>
          </div>
          <div class="panel-heading">
            <h3>{{ opsText(mainTable.title) }}</h3>
            <span>{{ mainTable.total ?? mainTable.rows.length }}</span>
          </div>
          <DataTable
            :columns="activeTab === 'invocations' ? displayInvocationTable.columns : displayMainTable.columns"
            :rows="activeTab === 'invocations' ? displayInvocationTable.rows : displayMainTable.rows"
            :section-id="activeTab === 'invocations' ? displayInvocationTable.id : displayMainTable.id"
            :page-size="activeTab === 'invocations' ? 6 : mainTablePageSize"
            clickable-rows
            @row-click="selectMainTableRow"
          />
          <p v-if="!mainTable.rows.length" class="table-empty">{{ opsText(mainTable.empty_state ?? "No records.") }}</p>
        </article>

        <section class="llm-bottom-grid">
          <article class="panel side-table">
            <div class="panel-heading">
              <h3>{{ opsText(authBlockedTable.title) }}</h3>
              <span>{{ authBlockedTable.total ?? authBlockedTable.rows.length }}</span>
            </div>
            <DataTable :columns="authBlockedTable.columns" :rows="authBlockedTable.rows" section-id="provider-auth-blocked" :page-size="3" />
            <p v-if="!authBlockedTable.rows.length" class="table-empty">{{ t("operations.llm.empty.accessHealthy") }}</p>
          </article>

          <article class="panel stream-trend-panel">
            <div class="panel-heading">
              <h3>{{ t("operations.llm.section.streamTrend") }}</h3>
              <span>{{ streamHealthSection.items.length }}</span>
            </div>
            <div class="stream-trend-chart">
              <div class="stream-trend-lines">
                <i />
                <i />
                <i />
                <b />
              </div>
              <ul>
                <li v-for="item in streamTrendItems" :key="item.id">
                  <span><StatusDot :tone="item.tone" />{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                  <em><i :style="{ width: `${item.pct}%` }" /></em>
                </li>
              </ul>
            </div>
          </article>
        </section>
      </div>

      <aside class="llm-side">
        <article class="panel chart-board">
          <div class="panel-heading">
            <h3>{{ t("operations.llm.section.runtimeStats") }}</h3>
            <span>{{ chartCards.length }}</span>
          </div>
          <div v-if="chartCards.length" class="mini-chart-grid">
            <div v-for="chart in chartCards" :key="chart.id" class="mini-chart">
              <div class="mini-chart__head">
                <strong>{{ opsText(chart.title) }}</strong>
                <span>{{ chartTotal(chart) }}</span>
              </div>
              <div class="mini-chart__body">
                <div class="donut donut--xs" :style="donutStyle(chart)">
                  <strong>{{ chartTotal(chart) }}</strong>
                </div>
                <div class="mini-chart__bars">
                  <div v-for="segment in chartSegments(chart).slice(0, 3)" :key="segment.id">
                    <span :title="opsText(segment.label)">{{ opsText(segment.label) }}</span>
                    <em>{{ segment.value }}</em>
                    <i :style="{ width: `${Math.max(segment.pct, 4)}%` }" />
                  </div>
                  <p v-if="!chartSegments(chart).length">{{ t("operations.llm.empty.noData") }}</p>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="table-empty">{{ t("operations.llm.empty.noData") }}</p>
        </article>

        <article class="panel side-table">
          <div class="panel-heading">
            <h3>{{ opsText(errorSummaryTable.title) }}</h3>
            <span>{{ errorSummaryTable.total ?? errorSummaryTable.rows.length }}</span>
          </div>
          <DataTable
            :columns="errorSummaryTable.columns"
            :rows="errorSummaryTable.rows"
            section-id="llm-error-summary"
            :page-size="4"
            clickable-rows
            @row-click="selectInvocationFromRow"
          />
          <p v-if="!errorSummaryTable.rows.length" class="table-empty">{{ opsText(errorSummaryTable.empty_state ?? "No failed LLM invocations.") }}</p>
        </article>

        <article class="panel">
          <div class="panel-heading">
            <h3>{{ opsText(streamHealthSection.title) }}</h3>
          </div>
          <dl class="kv-grid">
            <div v-for="item in streamHealthVisibleItems" :key="item.label">
              <dt>{{ opsText(item.label) }}</dt>
              <dd><StatusDot :tone="item.tone ?? 'neutral'" />{{ opsText(item.value) }}</dd>
            </div>
          </dl>
        </article>
      </aside>
    </section>

    <aside v-if="selectedEventRow" class="llm-drawer">
      <header>
        <div>
          <span>{{ opsText(lifecycleEventsTable.title) }}</span>
          <h3>{{ selectedEventTitle }}</h3>
          <p v-if="selectedEventSubtitle">{{ selectedEventSubtitle }}</p>
        </div>
        <button type="button" aria-label="Close" @click="closeDrawer">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("table.details") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in selectedEventFields" :key="item.key">
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("trace.tabs.payload") }}</h4>
        <pre>{{ selectedEventDetails }}</pre>
      </section>
    </aside>

    <aside v-else-if="selectedInvocationId" class="llm-drawer">
      <template v-if="selectedDetail">
      <header>
        <div>
          <span>{{ t("operations.llm.drawer.invocation") }}</span>
          <h3>{{ selectedDetail.title }}</h3>
        </div>
        <button type="button" aria-label="Close" @click="closeDrawer">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.llm.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedDetail.summary)" :key="item.label">
            <dt>{{ opsText(item.label) }}</dt>
            <dd><StatusDot :tone="item.tone ?? 'neutral'" />{{ opsText(item.value) }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.llm.drawer.requestContext") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedDetail.request_context)" :key="item.label">
            <dt>{{ opsText(item.label) }}</dt>
            <dd><StatusDot :tone="item.tone ?? 'neutral'" />{{ opsText(item.value) }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ opsText(selectedDetail.resolver.title) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in selectedDetail.resolver.items" :key="item.label">
            <dt>{{ opsText(item.label) }}</dt>
            <dd><StatusDot :tone="item.tone ?? 'neutral'" />{{ opsText(item.value) }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.llm.drawer.requestPayload") }}</h4>
        <pre>{{ detailPayload(selectedDetail.request_payload) }}</pre>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.llm.drawer.resultError") }}</h4>
        <p v-if="selectedDetail.result_summary">{{ selectedDetail.result_summary }}</p>
        <p v-if="selectedDetail.error" class="drawer-error">{{ selectedDetail.error }}</p>
        <pre>{{ detailPayload(selectedDetail.result_payload) }}</pre>
      </section>

      <section class="drawer-section">
        <h4>{{ opsText(selectedDetail.error_facts.title) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in selectedDetail.error_facts.items" :key="item.label">
            <dt>{{ opsText(item.label) }}</dt>
            <dd><StatusDot :tone="item.tone ?? 'neutral'" />{{ opsText(item.value) }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ opsText(selectedDetail.events.title) }}</h4>
        <DataTable :columns="selectedDetail.events.columns" :rows="selectedDetail.events.rows" section-id="llm-invocation-events" :page-size="5" />
      </section>
      </template>
      <template v-else>
        <header>
          <div>
            <span>{{ t("operations.llm.drawer.invocation") }}</span>
            <h3>{{ selectedInvocationId }}</h3>
            <p>{{ invocationDetailLoading ? t("common.loading") : (invocationDetailError ?? t("table.noRecords")) }}</p>
          </div>
          <button type="button" aria-label="Close" @click="closeDrawer">
            <X :size="16" />
          </button>
        </header>
      </template>
    </aside>
  </main>
</template>

<style scoped>
.llm-console {
  height: calc(100dvh - var(--shell-topbar-height));
  min-width: 0;
  padding: 7px 10px 10px;
  overflow: auto;
  scrollbar-gutter: stable;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
}

.llm-header,
.llm-header__ops,
.llm-metrics,
.llm-tabs,
.panel-heading,
.table-toolbar,
.donut-row,
.chart-body {
  display: flex;
  align-items: center;
}

.llm-header {
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  margin-bottom: 6px;
}

h2,
h3,
h4,
p,
dl,
ul {
  margin: 0;
}

h2 {
  font-size: 17px;
  line-height: 1.12;
}

.llm-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.llm-header__ops span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.llm-header__ops strong {
  color: var(--text-primary);
}

.auto-toggle i {
  width: 24px;
  height: 14px;
  border-radius: 999px;
  background: var(--color-success);
  box-shadow: inset 10px 0 0 color-mix(in srgb, #ffffff 92%, transparent);
}

.role-badge {
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 52%, var(--border-subtle));
  border-radius: var(--radius-1);
  color: var(--color-warning);
}

.llm-alert {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 42%, var(--border-subtle));
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 88%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
}

.llm-alert span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(112px, 1fr));
  gap: 7px;
}

.metric,
.panel,
.strip-item {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 91%, transparent);
}

.metric {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 6px;
  align-items: center;
  height: 72px;
  min-height: 0;
  padding: 9px 10px;
  overflow: hidden;
}

.metric-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
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

.metric-copy {
  min-width: 0;
}

.metric-copy em,
.metric-copy small {
  display: block;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-copy strong {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 17px;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-status-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 7px;
  margin-top: 7px;
}

.strip-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 34px;
  padding: 0 9px;
  color: var(--text-muted);
  font-size: 11px;
}

.strip-item strong {
  color: var(--text-primary);
  font-size: 15px;
}

.strip-item--warning strong {
  color: var(--color-warning);
}

.strip-item--danger strong {
  color: var(--color-danger);
}

.strip-item--success strong {
  color: var(--color-success);
}

.llm-overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.56fr) minmax(210px, 0.78fr) minmax(260px, 0.92fr) minmax(220px, 0.82fr);
  gap: 7px;
  margin-top: 7px;
}

.panel {
  min-width: 0;
  min-height: 0;
  padding: 8px;
  overflow: hidden;
}

.llm-overview-grid > .panel {
  min-height: 140px;
  height: auto;
  overflow: hidden;
}

.panel--profiles {
  min-height: 136px;
}

.panel--profiles :deep(.data-table) {
  max-height: none;
}

.panel--profiles :deep(.data-table--provider-access-health) {
  --data-table-min-width: 100%;
}

.panel--profiles :deep(th),
.panel--profiles :deep(td) {
  height: 26px;
  min-height: 26px;
  padding-inline: 6px;
  font-size: 10.5px;
}

.panel--profiles :deep(.column-profile),
.panel--profiles :deep(.column-provider),
.panel--profiles :deep(.column-model) {
  width: 128px;
}

.panel--profiles :deep(.column-status),
.panel--profiles :deep(.column-invocations) {
  width: 76px;
}

.panel--profiles :deep(.column-last-invocation) {
  width: 110px;
}

.panel-heading {
  justify-content: space-between;
  gap: 8px;
  min-height: 20px;
  margin-bottom: 5px;
}

.panel-heading h3 {
  overflow: hidden;
  font-size: 12.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-heading span {
  color: var(--text-muted);
  font-size: 11px;
}

.kv-grid,
.detail-grid {
  display: grid;
  gap: 7px;
}

.kv-grid div,
.detail-grid div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 22px;
  color: var(--text-secondary);
  font-size: 11px;
}

dt {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

dd {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  font-weight: 800;
}

.donut-row,
.chart-body {
  gap: 12px;
}

.donut {
  display: grid;
  place-items: center;
  align-content: center;
  width: 92px;
  height: 92px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
}

.donut--sm {
  width: 62px;
  height: 62px;
}

.donut--xs {
  width: 30px;
  height: 30px;
}

.donut--xs strong {
  display: none;
}

.donut strong {
  color: var(--text-primary);
  font-size: 18px;
  line-height: 1;
}

.donut span {
  color: var(--text-muted);
  font-size: 10px;
}

.donut-row ul,
.chart-body ul {
  display: grid;
  flex: 1;
  gap: 7px;
  min-width: 0;
  padding: 0;
  list-style: none;
}

.donut-row li,
.chart-body li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 11px;
}

.donut-row li span,
.chart-body li span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-inline {
  display: block !important;
  color: var(--text-muted);
}

.llm-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 304px;
  gap: 7px;
  margin-top: 7px;
}

.llm-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 7px;
  min-width: 0;
  min-height: 0;
}

.llm-tabs {
  gap: 4px;
  flex: 0 0 auto;
  min-height: 30px;
  overflow: auto hidden;
  border-bottom: 1px solid var(--border-subtle);
}

.llm-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 29px;
  padding: 0 8px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11.5px;
  white-space: nowrap;
}

.llm-tabs button.active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.llm-tabs em {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--surface-panel-soft);
  color: var(--text-muted);
  font-style: normal;
  font-size: 10px;
  text-align: center;
}

.table-toolbar {
  flex: 0 0 auto;
  gap: 6px;
  min-height: 30px;
  margin: 6px 0;
  overflow-x: auto;
  scrollbar-width: thin;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 220px;
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel);
  color: var(--text-muted);
}

.search-box input,
.table-toolbar select {
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
  outline: none;
}

.search-box input {
  flex: 1;
}

.table-toolbar select {
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel);
}

.table-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin-top: 0;
}

.table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
  max-height: 100%;
}

.table-panel :deep(.data-table--recent-invocations) {
  --data-table-min-width: 100%;
}

.table-panel :deep(th),
.table-panel :deep(td) {
  height: 21px;
  min-height: 21px;
  padding-top: 1px;
  padding-bottom: 1px;
  font-size: 10.5px;
}

.table-panel :deep(.data-table__pager) {
  min-height: 22px;
  padding-top: 2px;
}

.table-panel :deep(.data-table__pager button) {
  min-height: 20px;
  padding: 0 7px;
}

.table-panel :deep(.column-time) {
  width: 76px;
}

.table-panel :deep(.column-invocation-id),
.table-panel :deep(.column-run-id),
.table-panel :deep(.column-trace) {
  width: 108px;
}

.table-panel :deep(.column-provider-model) {
  width: 160px;
}

.table-panel :deep(.column-status) {
  width: 72px;
}

.table-panel :deep(.column-duration),
.table-panel :deep(.column-streaming),
.table-panel :deep(.column-tokens),
.table-panel :deep(.column-error-code) {
  width: 78px;
}

.table-panel :deep(.column-finish-reason) {
  width: 92px;
}

.table-panel :deep(.column-actions) {
  width: 62px;
}

.table-empty {
  flex: 1 1 auto;
  display: grid;
  place-items: center;
  min-height: 54px;
  color: var(--text-muted);
  font-size: 11px;
}

.llm-side {
  display: grid;
  gap: 7px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.llm-bottom-grid {
  display: grid;
  grid-template-columns: minmax(340px, 0.62fr) minmax(0, 1fr);
  gap: 7px;
  min-height: 0;
}

.llm-bottom-grid > .panel {
  min-height: 0;
}

.mini-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: repeat(2, minmax(0, 1fr));
  gap: 6px;
  flex: 1 1 auto;
  min-height: 0;
}

.mini-chart {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 4px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.mini-chart__head {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 2px;
  min-width: 0;
}

.mini-chart__head strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-chart__head span {
  flex: 0 0 auto;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
}

.mini-chart__body {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 5px;
  align-items: center;
  flex: 1 1 auto;
  min-height: 0;
}

.mini-chart__bars {
  display: grid;
  gap: 3px;
  min-width: 0;
  min-height: 0;
}

.mini-chart__bars div {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px;
  min-height: 10px;
  color: var(--text-secondary);
  font-size: 9.5px;
}

.mini-chart__bars span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-chart__bars em {
  color: var(--text-primary);
  font-style: normal;
  font-weight: 800;
}

.mini-chart__bars i {
  position: absolute;
  left: 0;
  right: auto;
  bottom: -2px;
  height: 2px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-blue) 70%, transparent);
}

.mini-chart__bars p {
  margin: 0;
  color: var(--text-muted);
  font-size: 10px;
}

.side-table {
  min-height: 0;
}

.chart-board {
  display: flex;
  flex-direction: column;
}

.side-table :deep(.data-table) {
  max-height: 100%;
}

.side-table :deep(th),
.side-table :deep(td) {
  height: 25px;
  min-height: 25px;
  padding-inline: 6px;
  font-size: 10.5px;
}

.stream-trend-panel {
  display: flex;
  flex-direction: column;
}

.stream-trend-chart {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 210px;
  gap: 14px;
  flex: 1 1 auto;
  min-height: 0;
}

.stream-trend-lines {
  position: relative;
  min-height: 96px;
  overflow: hidden;
  border-bottom: 1px solid var(--border-subtle);
  background:
    repeating-linear-gradient(0deg, color-mix(in srgb, var(--border-subtle) 42%, transparent) 0 1px, transparent 1px 18px),
    repeating-linear-gradient(90deg, transparent 0 70px, color-mix(in srgb, var(--border-subtle) 32%, transparent) 70px 71px);
}

.stream-trend-lines i {
  position: absolute;
  right: 0;
  left: 0;
  height: 2px;
  border-radius: 999px;
}

.stream-trend-lines i:nth-child(1) {
  bottom: 17px;
  background: linear-gradient(90deg, transparent, var(--color-accent), transparent);
}

.stream-trend-lines i:nth-child(2) {
  bottom: 31px;
  background: linear-gradient(90deg, transparent, var(--color-success), transparent);
  opacity: 0.76;
}

.stream-trend-lines i:nth-child(3) {
  bottom: 9px;
  background: linear-gradient(90deg, transparent, var(--color-warning), transparent);
  opacity: 0.52;
}

.stream-trend-lines b {
  position: absolute;
  inset: auto 0 0;
  height: 62px;
  clip-path: polygon(0 76%, 10% 70%, 18% 72%, 27% 61%, 36% 68%, 45% 58%, 55% 65%, 64% 54%, 73% 62%, 84% 46%, 94% 54%, 100% 42%, 100% 100%, 0 100%);
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-blue) 34%, transparent), transparent 86%);
}

.stream-trend-chart ul {
  display: grid;
  gap: 6px;
  align-content: center;
  min-width: 0;
  padding: 0;
  margin: 0;
  list-style: none;
}

.stream-trend-chart li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 10.5px;
}

.stream-trend-chart li span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stream-trend-chart li strong {
  color: var(--text-primary);
  font-size: 10.5px;
}

.stream-trend-chart li em {
  grid-column: 1 / -1;
  display: block;
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-raised) 78%, transparent);
}

.stream-trend-chart li em i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-blue);
}

.llm-drawer {
  position: fixed;
  top: calc(var(--shell-topbar-height) + 10px);
  right: 12px;
  bottom: 12px;
  z-index: 40;
  width: min(470px, calc(100vw - 28px));
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 96%, transparent);
  box-shadow: var(--shadow-xl);
}

.llm-drawer header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.llm-drawer header span {
  color: var(--text-muted);
  font-size: 10px;
}

.llm-drawer header h3 {
  margin-top: 3px;
  overflow-wrap: anywhere;
  font-size: 13px;
}

.llm-drawer header p {
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.llm-drawer button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  cursor: pointer;
}

.drawer-section {
  display: grid;
  gap: 8px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.drawer-section h4 {
  color: var(--text-secondary);
  font-size: 12px;
}

.drawer-section p {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.drawer-error {
  color: var(--color-danger) !important;
}

pre {
  max-height: 240px;
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

.motion-spin {
  animation: llm-spin 0.9s linear infinite;
}

@keyframes llm-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (min-width: 1241px) {
  .llm-console {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    overscroll-behavior: contain;
  }

  .llm-header,
  .llm-alert,
  .llm-metrics,
  .llm-status-strip,
  .llm-overview-grid {
    flex: 0 0 auto;
  }

  .llm-workspace {
    flex: 1 1 auto;
    grid-template-rows: minmax(0, 1fr);
    min-height: 0;
    overflow: hidden;
  }

  .llm-main {
    grid-template-rows: minmax(0, 1fr) minmax(146px, 0.42fr);
    height: 100%;
    overflow: hidden;
  }

  .llm-side {
    grid-template-rows: minmax(158px, 0.82fr) minmax(126px, 0.58fr) minmax(142px, 0.72fr);
    height: 100%;
  }

  .table-panel,
  .llm-bottom-grid,
  .llm-side > .panel {
    min-height: 0;
    overflow: hidden;
  }

  .table-panel :deep(.data-table),
  .side-table :deep(.data-table) {
    overflow: auto;
  }
}

@media (max-width: 1320px) {
  .llm-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .llm-overview-grid,
  .llm-workspace,
  .llm-bottom-grid,
  .stream-trend-chart {
    grid-template-columns: 1fr;
  }

  .llm-side {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .llm-console {
    padding: 8px 10px 10px;
  }

  .llm-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .llm-metrics,
  .llm-status-strip,
  .llm-overview-grid {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .metric {
    flex: 0 0 156px;
  }

  .strip-item {
    flex: 0 0 148px;
  }

  .llm-overview-grid > .panel {
    flex: 0 0 282px;
  }

  .llm-side {
    grid-template-columns: 1fr;
  }

  .table-toolbar {
    align-items: center;
    flex-direction: row;
  }

  .search-box {
    flex: 0 0 210px;
    min-width: 0;
  }
}
</style>
