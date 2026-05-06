<script setup lang="ts">
import { Activity, Archive, CheckCircle2, CircleX, Clock3, ExternalLink, FileText, Hourglass, ListFilter, Pause, RefreshCcw, ShieldAlert, Square, Timer, TrendingUp, X, Zap } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { buildApiUrl } from "@/shared/api/client";
import { hasI18nMessage, useI18n } from "@/shared/i18n";
import { formatLocalTime } from "@/shared/i18n/formatters";
import type {
  OperationsTab,
  OperationsToolRunDetail,
  OperationsToolWorkerDetail,
  OperationsToolReadModel,
  UiChartSection,
  UiMetricCard,
  UiTableSection,
  UiTableRow,
  UiTone,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { cancelToolRun, loadToolOperations, loadToolRunDetail, pruneExpiredToolWorkers, retryToolRun } from "../api";
import { dynamicValueKeyPart, titleCaseDynamicValue } from "../mapping";

interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

interface ToolLifecycleEventCardView {
  id: string;
  time: string;
  level: string;
  event: string;
  tool: string;
  toolFull: string;
  runId: string;
  source: string;
  sourceRoute: string | null;
  assignment: string;
  worker: string;
  status: string;
  tone: UiTone;
  details: string[];
  detailsTitle: string;
  trace: string;
  traceRoute: string | null;
}

interface ToolArtifactPreviewItem {
  id: string;
  name: string;
  kind: string;
  mimeType: string;
  size: string;
  dimensions: string;
  tool: string;
  runId: string;
  time: string;
  route: string | null;
  trace: string;
  traceRoute: string | null;
  imageSrc: string | null;
  isImage: boolean;
}

interface ToolDashboardMetric {
  id: string;
  label: string;
  value: string;
  helper: string;
  tone: UiTone;
  icon: unknown;
  fillPct: number;
}

interface ToolInfoItem {
  id: string;
  label: string;
  value: string;
  tone?: UiTone;
}

interface ToolProviderHealthItem {
  id: string;
  name: string;
  state: string;
  latency: string;
  tone: UiTone;
}

interface ToolFailureSummaryItem {
  id: string;
  label: string;
  count: number;
  pct: number;
  tone: UiTone;
}

type ToolStatusFilter = "all" | "active" | "running" | "waiting" | "failed" | "long_running" | "succeeded" | "cancelled";
type ToolTimeFilter = "all" | "24h";
type ToolModeFilter = "all" | "inline" | "background";
type ToolStrategyFilter = "all" | "async" | "thread" | "process";
type ToolEnvironmentFilter = "all" | "local" | "sandbox" | "remote";
type ToolTernaryFilter = "all" | "yes" | "no";

const toolRunPageSize = 7;
const lifecycleEventPageSize = 5;
const { t } = useI18n();
const knownToolTabIds = new Set([
  "runs",
  "workers",
  "queue",
  "waiting_io",
  "capabilities",
  "provider_limits",
  "provider_history",
  "diagnostics",
  "risk",
  "artifacts",
  "events",
  "strategies",
]);
const knownToolRunFilters = new Set<ToolStatusFilter>([
  "all",
  "active",
  "running",
  "waiting",
  "failed",
  "long_running",
  "succeeded",
  "cancelled",
]);
const knownToolModeFilters = new Set<ToolModeFilter>([
  "all",
  "inline",
  "background",
]);
const knownToolStrategyFilters = new Set<ToolStrategyFilter>([
  "all",
  "async",
  "thread",
  "process",
]);
const knownToolEnvironmentFilters = new Set<ToolEnvironmentFilter>([
  "all",
  "local",
  "sandbox",
  "remote",
]);
const knownToolTernaryFilters = new Set<ToolTernaryFilter>([
  "all",
  "yes",
  "no",
]);
const fallbackTabs: OperationsTab[] = [
  { id: "runs", label: "Tool Runs" },
  { id: "workers", label: "Workers" },
  { id: "queue", label: "Queue" },
  { id: "waiting_io", label: "Waiting IO" },
  { id: "capabilities", label: "Capabilities" },
  { id: "provider_limits", label: "Provider Limits" },
  { id: "provider_history", label: "Provider History" },
  { id: "diagnostics", label: "Diagnostics" },
  { id: "risk", label: "Risk" },
  { id: "artifacts", label: "Artifacts" },
  { id: "events", label: "Events" },
  { id: "strategies", label: "Strategies" },
];

const page = ref<OperationsToolReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const actionError = ref<string | null>(null);
const actionNotice = ref<string | null>(null);
const cancelBusyRunId = ref<string | null>(null);
const retryBusyRunId = ref<string | null>(null);
const pruneWorkersBusy = ref(false);
const selectedRunId = ref<string | null>(null);
const selectedWorkerId = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedLifecycleEventId = ref<string | null>(null);
const selectedArtifactId = ref<string | null>(null);
const loadedRunDetails = ref<Record<string, OperationsToolRunDetail>>({});
const runDetailLoading = ref(false);
const runDetailError = ref<string | null>(null);
const toolStatusFilter = ref<ToolStatusFilter>("all");
const toolTimeFilter = ref<ToolTimeFilter>("all");
const toolSearchFilter = ref("");
const toolIdFilter = ref("");
const toolProviderFilter = ref("");
const toolModeFilter = ref<ToolModeFilter>("all");
const toolStrategyFilter = ref<ToolStrategyFilter>("all");
const toolEnvironmentFilter = ref<ToolEnvironmentFilter>("all");
const toolWorkerFilter = ref("");
const toolArtifactFilter = ref<ToolTernaryFilter>("all");
const toolRetryableFilter = ref<ToolTernaryFilter>("all");
const toolRunOffset = ref(0);
const refreshTimer = ref<number | null>(null);

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "runs";
  return knownToolTabIds.has(candidate) ? candidate : "runs";
});
const activeToolRunsTable = computed(() => page.value?.active_tool_runs ?? emptyTable("active_tool_runs", "Active Tool Runs"));
const toolQueueRunsTable = computed(() => page.value?.tool_queue_runs ?? emptyTable("tool_queue_runs", "Queued Tool Runs"));
const toolWaitingIoTable = computed(() => page.value?.tool_waiting_io ?? emptyTable("tool_waiting_io", "Waiting IO"));
const toolRunsTable = computed(() => page.value?.tool_runs ?? emptyTable("tool_runs", "Recent Tool Runs"));
const riskTable = computed(() => page.value?.auth_missing ?? emptyTable("auth_missing", "Runtime Risk / Access"));
const workersTable = computed(() => page.value?.workers ?? emptyTable("workers", "Workers"));
const capabilityLimitsTable = computed(() => page.value?.capability_limits ?? emptyTable("capability_limits", "Capability Concurrency"));
const providerLimitsTable = computed(() => page.value?.provider_limits ?? emptyTable("provider_limits", "Provider Limits"));
const providerHistoryTable = computed(() => page.value?.provider_history ?? emptyTable("provider_history", "Provider History"));
const runBlockersTable = computed(() => page.value?.run_blockers ?? emptyTable("run_blockers", "Run Scheduling Diagnostics"));
const artifactsTable = computed(() => page.value?.recent_artifacts ?? emptyTable("recent_artifacts", "Recent Artifacts"));
const lifecycleEventsTable = computed(() => page.value?.tool_lifecycle_events ?? emptyTable("tool_lifecycle_events", "Tool Lifecycle Events"));
const strategiesTable = computed(() => page.value?.strategies ?? emptyTable("strategies", "Execution Strategies"));
const toolTypeSegments = computed(() => chartSegments(page.value?.tool_types));
const metricsById = computed(() => new Map(displayMetrics.value.map((metric) => [metric.id, metric])));
const toolTypeDonutStyle = computed(() => ({
  background: donutGradient(toolTypeSegments.value),
}));
const totalToolRunCount = computed(() => toolRunsTable.value.total ?? toolRunsTable.value.rows.length);
const activeToolRunCount = computed(() => metricNumber("active_runs"));
const queuedToolRunCount = computed(() => toolQueueRunsTable.value.total ?? 0);
const waitingIoCount = computed(() => toolWaitingIoTable.value.total ?? 0);
const failedToolRunCount = computed(() => metricNumber("failed_runs"));
const workerCapacity = computed(() => workersTable.value.rows.reduce((sum, row) => (
  row.tone === "success" ? sum + workerLoadLimit(cellText(row, "load")) : sum
), 0));
const executionModeLabel = computed(() => {
  const ranked = [...strategiesTable.value.rows].sort((left, right) => numberCell(right, "runs") - numberCell(left, "runs"));
  const row = ranked[0];
  if (!row) return "-";
  const mode = detailSummaryText(cellText(row, "mode"));
  const strategy = detailSummaryText(cellText(row, "strategy"));
  return [mode, strategy].filter((item) => item && item !== "-").join(" / ") || "-";
});
const dominantStrategyLabel = computed(() => {
  const ranked = [...strategiesTable.value.rows].sort((left, right) => numberCell(right, "runs") - numberCell(left, "runs"));
  const row = ranked[0];
  return row ? detailSummaryText(cellText(row, "strategy")) : "-";
});
const weightedAvgDurationSeconds = computed(() => {
  let weighted = 0;
  let runs = 0;
  for (const row of providerHistoryTable.value.rows) {
    const runCount = numberCell(row, "runs");
    const duration = durationSecondsFromLabel(cellText(row, "avg_duration"));
    if (runCount <= 0 || duration === null) continue;
    weighted += runCount * duration;
    runs += runCount;
  }
  return runs ? Math.round(weighted / runs) : null;
});
const maxDurationSeconds = computed(() => {
  const durations = providerHistoryTable.value.rows
    .map((row) => durationSecondsFromLabel(cellText(row, "max_duration")))
    .filter((value): value is number => value !== null);
  return durations.length ? Math.max(...durations) : null;
});
const avgLatencyMetric = computed(() => metricCard("avg_latency")?.value ?? formatDurationSeconds(weightedAvgDurationSeconds.value));
const p95LatencyMetric = computed(() => metricCard("p95_latency")?.value ?? formatDurationSeconds(maxDurationSeconds.value));
const throughputMetric = computed(() => metricCard("throughput")?.value ?? String(totalToolRunCount.value));
const dashboardMetrics = computed<ToolDashboardMetric[]>(() => [
  {
    id: "active_runs",
    label: t("operations.tool.dashboard.activeRuns"),
    value: String(activeToolRunCount.value),
    helper: t("operations.tool.dashboard.activeRunsHint"),
    tone: activeToolRunCount.value ? "info" : "success",
    icon: Activity,
    fillPct: ratioPct(activeToolRunCount.value, Math.max(totalToolRunCount.value, 1)),
  },
  {
    id: "queue",
    label: t("operations.tool.dashboard.queueWaiting"),
    value: String(queuedToolRunCount.value),
    helper: t("operations.tool.dashboard.queueWaitingHint"),
    tone: queuedToolRunCount.value ? "warning" : "success",
    icon: Archive,
    fillPct: ratioPct(queuedToolRunCount.value, Math.max(activeToolRunCount.value + queuedToolRunCount.value, 1)),
  },
  {
    id: "waiting_io",
    label: t("operations.tool.dashboard.waitingIo"),
    value: String(waitingIoCount.value),
    helper: t("operations.tool.dashboard.waitingIoHint"),
    tone: waitingIoCount.value ? "warning" : "success",
    icon: Hourglass,
    fillPct: ratioPct(waitingIoCount.value, Math.max(waitingIoCount.value + activeToolRunCount.value, 1)),
  },
  {
    id: "failed_runs",
    label: t("operations.tool.dashboard.failedRuns"),
    value: String(failedToolRunCount.value),
    helper: metricDelta(metricCard("failed_runs") ?? fallbackMetric("failed_runs")),
    tone: failedToolRunCount.value ? "danger" : "success",
    icon: CircleX,
    fillPct: ratioPct(failedToolRunCount.value, Math.max(totalToolRunCount.value, 1)),
  },
  {
    id: "avg_latency",
    label: t("operations.tool.dashboard.avgLatency"),
    value: avgLatencyMetric.value,
    helper: metricDelta(metricCard("avg_latency") ?? fallbackMetric("avg_latency")),
    tone: weightedAvgDurationSeconds.value && weightedAvgDurationSeconds.value > 30 ? "warning" : "info",
    icon: Timer,
    fillPct: durationPct(weightedAvgDurationSeconds.value, maxDurationSeconds.value),
  },
  {
    id: "p95_latency",
    label: t("operations.tool.dashboard.p95Latency"),
    value: p95LatencyMetric.value,
    helper: metricDelta(metricCard("p95_latency") ?? fallbackMetric("p95_latency")),
    tone: maxDurationSeconds.value && maxDurationSeconds.value > 120 ? "warning" : "info",
    icon: Clock3,
    fillPct: maxDurationSeconds.value ? 100 : 0,
  },
  {
    id: "throughput",
    label: t("operations.tool.dashboard.throughput"),
    value: throughputMetric.value,
    helper: metricDelta(metricCard("throughput") ?? fallbackMetric("throughput")),
    tone: metricCard("throughput")?.tone ?? "neutral",
    icon: TrendingUp,
    fillPct: totalToolRunCount.value ? 100 : 0,
  },
]);
const runtimeInfoItems = computed<ToolInfoItem[]>(() => [
  {
    id: "mode",
    label: t("operations.tool.dashboard.executionMode"),
    value: executionModeLabel.value,
  },
  {
    id: "concurrency",
    label: t("operations.tool.dashboard.concurrencyLimit"),
    value: workerCapacity.value ? String(workerCapacity.value) : "-",
  },
  {
    id: "retryable",
    label: t("operations.tool.dashboard.retryableFailures"),
    value: String(retryableToolRuns.value.length),
    tone: retryableToolRuns.value.length ? "warning" : "success",
  },
  {
    id: "catalog",
    label: metricLabel(metricCard("catalog") ?? fallbackMetric("catalog")),
    value: metricCard("catalog")?.value ?? "0",
  },
]);
const headerControlItems = computed<ToolInfoItem[]>(() => [
  {
    id: "mode",
    label: t("operations.tool.dashboard.executionMode"),
    value: executionModeLabel.value,
  },
  {
    id: "concurrency",
    label: t("operations.tool.dashboard.concurrencyLimit"),
    value: workerCapacity.value ? String(workerCapacity.value) : "-",
  },
  {
    id: "retry_strategy",
    label: t("operations.tool.dashboard.retryStrategy"),
    value: dominantStrategyLabel.value,
  },
]);
const artifactDetailItems = computed<ToolArtifactPreviewItem[]>(() => (
  artifactsTable.value.rows.map(artifactPreviewItem)
));
const lifecycleEventCards = computed(() => lifecycleEventsTable.value.rows.map(lifecycleEventCard));
const lifecycleEventsDisplayTable = computed<UiTableSection>(() => ({
  ...lifecycleEventsTable.value,
  id: "tool_lifecycle_events",
  columns: [
    { key: "time", label: "Time" },
    { key: "event", label: "Event" },
    { key: "status", label: "Status" },
    { key: "tool", label: "Tool" },
    { key: "run_id", label: "Run ID" },
    { key: "source", label: "Source" },
    { key: "worker_id", label: "Worker ID" },
  ],
  rows: lifecycleEventCards.value.map(lifecycleEventTableRow),
  total: lifecycleEventsTable.value.total ?? lifecycleEventCards.value.length,
}));
const filteredToolRunsTable = computed<UiTableSection>(() => toolRunsTable.value);
const activeDashboardTable = computed<UiTableSection>(() => ({
  ...activeToolRunsTable.value,
  title: "Active Tool Runs",
  columns: [
    { key: "tool", label: "Tool" },
    { key: "source", label: "Parent Run" },
    { key: "worker", label: "Worker" },
    { key: "duration", label: "Duration" },
    { key: "progress", label: "Progress" },
    { key: "actions", label: "Actions" },
  ],
  total: activeToolRunsTable.value.total ?? activeToolRunsTable.value.rows.length,
}));
const queueDashboardTable = computed<UiTableSection>(() => ({
  ...toolQueueRunsTable.value,
  title: "Queued Tool Runs",
  columns: [
    { key: "tool", label: "Tool" },
    { key: "source", label: "Parent Run" },
    { key: "priority", label: "Priority" },
    { key: "wait_time", label: "Wait Time" },
    { key: "actions", label: "Actions" },
  ],
  total: toolQueueRunsTable.value.total ?? toolQueueRunsTable.value.rows.length,
}));
const waitingDashboardTable = computed<UiTableSection>(() => ({
  ...toolWaitingIoTable.value,
  title: "Waiting IO",
  columns: [
    { key: "tool", label: "Tool" },
    { key: "source", label: "Parent Run" },
    { key: "external_service", label: "External Service" },
    { key: "wait_time", label: "Wait Time" },
  ],
  total: toolWaitingIoTable.value.total ?? toolWaitingIoTable.value.rows.length,
}));
const toolRunRecordsTable = computed<UiTableSection>(() => ({
  ...filteredToolRunsTable.value,
  title: "Tool Run Records",
  columns: [
    { key: "time", label: "Time" },
    { key: "tool", label: "Tool" },
    { key: "run_id", label: "Tool Run ID" },
    { key: "source", label: "Parent Run" },
    { key: "worker", label: "Worker" },
    { key: "mode", label: "Mode" },
    { key: "status", label: "Status" },
    { key: "duration", label: "Duration" },
    { key: "actions", label: "Actions" },
  ],
  total: filteredToolRunsTable.value.total ?? filteredToolRunsTable.value.rows.length,
}));
const compactToolRunsTable = computed<UiTableSection>(() => ({
  ...activeToolRunsTable.value,
  title: "Active Tool Runs",
  columns: [
    { key: "run_id", label: "Run ID" },
    { key: "tool", label: "Tool" },
    { key: "source", label: "Source" },
    { key: "worker", label: "Worker ID" },
    { key: "duration", label: "Duration" },
    { key: "progress", label: "Progress" },
    { key: "status", label: "Status" },
    { key: "actions", label: "Actions" },
  ],
  total: activeToolRunsTable.value.total ?? activeToolRunsTable.value.rows.length,
}));
const compactWorkersTable = computed<UiTableSection>(() => ({
  ...workersTable.value,
  title: "Workers",
  columns: [
    { key: "worker", label: "Worker" },
    { key: "status", label: "Status" },
    { key: "load", label: "Load" },
    { key: "running", label: "Running" },
    { key: "last_heartbeat", label: "Last Heartbeat" },
  ],
}));
const waitingIoTable = computed<UiTableSection>(() => toolWaitingIoTable.value);
const compactQueueTable = computed<UiTableSection>(() => ({
  ...toolQueueRunsTable.value,
  title: "Queued Tool Runs",
  columns: [
    { key: "run_id", label: "Run ID" },
    { key: "tool", label: "Tool" },
    { key: "source", label: "Source" },
    { key: "priority", label: "Priority" },
    { key: "wait_time", label: "Wait Time" },
    { key: "reason", label: "Reason" },
    { key: "actions", label: "Actions" },
  ],
}));
const mainTable = computed<UiTableSection>(() => {
  switch (activeTab.value) {
    case "workers":
      return compactWorkersTable.value;
    case "queue":
      return compactQueueTable.value;
    case "waiting_io":
      return waitingIoTable.value;
    case "capabilities":
      return capabilityLimitsTable.value;
    case "provider_limits":
      return providerLimitsTable.value;
    case "provider_history":
      return providerHistoryTable.value;
    case "diagnostics":
      return runBlockersTable.value;
    case "risk":
      return riskTable.value;
    case "artifacts":
      return artifactsTable.value;
    case "events":
      return lifecycleEventsDisplayTable.value;
    case "strategies":
      return strategiesTable.value;
    default:
      return compactToolRunsTable.value;
  }
});
const mainSectionId = computed(() => {
  const sectionIds: Record<string, string> = {
    runs: "tool-runs",
    workers: "workers",
    queue: "tool-queue",
    waiting_io: "waiting-io",
    capabilities: "capability-limits",
    provider_limits: "provider-limits",
    provider_history: "provider-history",
    diagnostics: "run-blockers",
    risk: "auth-missing",
    artifacts: "recent-artifacts",
    events: "tool-lifecycle-events",
    strategies: "strategies",
  };
  return sectionIds[activeTab.value] ?? (mainTable.value.id || activeTab.value).replace(/_/g, "-");
});
const mainPageSize = computed(() => activeTab.value === "events" ? lifecycleEventPageSize : 5);
const mainClickableRows = computed(() => ["runs", "queue", "waiting_io", "workers", "artifacts", "events"].includes(activeTab.value));
const isToolRunFiltered = computed(() =>
  toolStatusFilter.value !== "all"
  || toolTimeFilter.value !== "all"
  || Boolean(toolSearchFilter.value.trim())
  || Boolean(toolIdFilter.value.trim())
  || Boolean(toolProviderFilter.value.trim())
  || toolModeFilter.value !== "all"
  || toolStrategyFilter.value !== "all"
  || toolEnvironmentFilter.value !== "all"
  || Boolean(toolWorkerFilter.value.trim())
  || toolArtifactFilter.value !== "all"
  || toolRetryableFilter.value !== "all",
);
const mainEmptyTitleKey = computed(() => {
  if (activeTab.value === "runs" && isToolRunFiltered.value) {
    return "operations.tool.emptyTitle.noFilteredRuns";
  }
  const keys: Record<string, string> = {
    runs: "operations.tool.emptyTitle.noRuns",
    workers: "operations.tool.emptyTitle.workersClear",
    queue: "operations.tool.emptyTitle.queueClear",
    waiting_io: "operations.tool.emptyTitle.waitingIoClear",
    capabilities: "operations.tool.emptyTitle.capabilitiesClear",
    provider_limits: "operations.tool.emptyTitle.providerLimitsClear",
    provider_history: "operations.tool.emptyTitle.providerHistoryClear",
    diagnostics: "operations.tool.emptyTitle.diagnosticsClear",
    risk: "operations.tool.emptyTitle.accessClear",
    artifacts: "operations.tool.emptyTitle.artifactsClear",
    events: "operations.tool.emptyTitle.eventsClear",
    strategies: "operations.tool.emptyTitle.strategiesClear",
  };
  return keys[activeTab.value] ?? "table.noRecords";
});
const mainTableFooter = computed(() => {
  const table = mainTable.value;
  return t("operations.tool.footer.visibleTotal", {
    visible: table.rows.length,
    total: table.total ?? table.rows.length,
  });
});
const cancelableToolRuns = computed(() => activeToolRunsTable.value.rows.filter(canCancelToolRun));
const retryableToolRuns = computed(() => filteredToolRunsTable.value.rows.filter(canRetryToolRun));
const detailByRunId = computed(() => {
  const pairs = [
    ...(page.value?.tool_run_details ?? []),
    ...Object.values(loadedRunDetails.value),
  ].map((detail) => [detail.run_id, detail] as const);
  return new Map(pairs);
});
const workerDetailById = computed(() => {
  const pairs = (page.value?.worker_details ?? []).map((detail) => [detail.worker_id, detail] as const);
  return new Map(pairs);
});
const selectedRunDetail = computed(() => selectedRunId.value ? detailByRunId.value.get(selectedRunId.value) ?? null : null);
const selectedWorkerDetail = computed(() => selectedWorkerId.value ? workerDetailById.value.get(selectedWorkerId.value) ?? null : null);
const selectedLifecycleEvent = computed(() => {
  if (!selectedLifecycleEventId.value) return null;
  return lifecycleEventCards.value.find((event) => event.id === selectedLifecycleEventId.value) ?? null;
});
const selectedArtifact = computed(() => {
  if (!selectedArtifactId.value) return null;
  return artifactDetailItems.value.find((artifact) => artifact.id === selectedArtifactId.value) ?? null;
});
const latencyProviderItems = computed(() => {
  const maxDuration = maxDurationSeconds.value ?? 0;
  return providerHistoryTable.value.rows.slice(0, 3).map((row) => {
    const duration = durationSecondsFromLabel(cellText(row, "avg_duration"));
    return {
      id: row.id,
      provider: cellText(row, "provider"),
      avg: cellText(row, "avg_duration"),
      max: cellText(row, "max_duration"),
      pct: durationPct(duration, maxDuration),
    };
  });
});
const providerHealthItems = computed<ToolProviderHealthItem[]>(() => (
  providerHistoryTable.value.rows.slice(0, 4).map((row) => ({
    id: row.id,
    name: cellText(row, "provider"),
    state: detailSummaryText(cellText(row, "state")),
    latency: cellText(row, "avg_duration"),
    tone: row.tone ?? "neutral",
  }))
));
const failedToolRunRows = computed(() => filteredToolRunsTable.value.rows.filter((row) => isFailureStatus(rowStatus(row))));
const failureSummaryItems = computed<ToolFailureSummaryItem[]>(() => {
  const failedRows = failedToolRunRows.value;
  const total = failedRows.length;
  const counts = new Map<string, { count: number; tone: UiTone }>();
  for (const row of failedRows) {
    const status = detailSummaryText(cellText(row, "status"));
    const key = status && status !== "-" ? status : t("status.failed");
    const tone = row.tone ?? "danger";
    const current = counts.get(key) ?? { count: 0, tone };
    current.count += 1;
    current.tone = tone;
    counts.set(key, current);
  }
  return [...counts.entries()].map(([label, item]) => ({
    id: label,
    label,
    count: item.count,
    pct: ratioPct(item.count, Math.max(total, 1)),
    tone: item.tone,
  }));
});
const tableTabCountById = computed(() => {
  const counts = new Map<string, number | null>();
  for (const tab of tabs.value) counts.set(tab.id, tab.count ?? null);
  counts.set("runs", activeToolRunsTable.value.total ?? activeToolRunsTable.value.rows.length);
  counts.set("queue", toolQueueRunsTable.value.total ?? 0);
  counts.set("waiting_io", toolWaitingIoTable.value.total ?? 0);
  counts.set("provider_limits", providerLimitsTable.value.total ?? providerLimitsTable.value.rows.length);
  counts.set("provider_history", providerHistoryTable.value.total ?? providerHistoryTable.value.rows.length);
  return counts;
});
const primaryTableTabs = computed(() => tabs.value.filter((tab) => ["runs", "queue", "waiting_io"].includes(tab.id)));
const toolRunRecordsFooter = computed(() => t("operations.tool.footer.visibleTotal", {
  visible: toolRunRecordsTable.value.rows.length,
  total: toolRunRecordsTable.value.total ?? toolRunRecordsTable.value.rows.length,
}));

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

function chartTotal(section: UiChartSection | null | undefined): number {
  const raw = typeof section?.total === "number" ? section.total : Number(section?.total ?? 0);
  if (Number.isFinite(raw) && raw > 0) return raw;
  return section?.segments?.reduce((sum, segment) => sum + segment.value, 0) ?? 0;
}

function chartSegments(section: UiChartSection | null | undefined): ChartSegmentView[] {
  const total = chartTotal(section);
  return (section?.segments ?? []).map((segment) => ({
    ...segment,
    pct: total ? Math.round((segment.value / total) * 100) : 0,
  }));
}

function metricCard(id: string): UiMetricCard | undefined {
  return metricsById.value.get(id);
}

function fallbackMetric(id: string): UiMetricCard {
  return {
    id,
    label: id,
    value: "0",
    delta: "",
    tone: "neutral",
  };
}

function metricNumber(id: string): number {
  const raw = metricCard(id)?.value ?? "0";
  const value = Number(String(raw).replace(/[^\d.-]/g, ""));
  return Number.isFinite(value) ? value : 0;
}

function numberCell(row: UiTableRow, key: string): number {
  const value = Number(cellText(row, key).replace(/[^\d.-]/g, ""));
  return Number.isFinite(value) ? value : 0;
}

function workerLoadLimit(value: string): number {
  const match = value.match(/\/\s*(\d+)/);
  return match ? Number(match[1]) : 0;
}

function ratioPct(value: number, total: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
}

function durationPct(value: number | null | undefined, maxValue: number | null | undefined): number {
  if (value == null || maxValue == null || maxValue <= 0) return 0;
  return ratioPct(value, maxValue);
}

function durationSecondsFromLabel(value: string): number | null {
  if (!value || value === "-") return null;
  const normalized = value.trim().toLowerCase();
  let seconds = 0;
  let matched = false;
  const hours = normalized.match(/(\d+(?:\.\d+)?)\s*h/);
  const minutes = normalized.match(/(\d+(?:\.\d+)?)\s*m(?!s)/);
  const secs = normalized.match(/(\d+(?:\.\d+)?)\s*s/);
  if (hours) {
    seconds += Number(hours[1]) * 3600;
    matched = true;
  }
  if (minutes) {
    seconds += Number(minutes[1]) * 60;
    matched = true;
  }
  if (secs) {
    seconds += Number(secs[1]);
    matched = true;
  }
  const numeric = Number(normalized.replace(/[^\d.]/g, ""));
  if (!matched && Number.isFinite(numeric)) return numeric;
  return matched && Number.isFinite(seconds) ? Math.round(seconds) : null;
}

function formatDurationSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  if (value >= 3600) return `${Math.floor(value / 3600)}h ${Math.round((value % 3600) / 60)}m`;
  if (value >= 60) return `${Math.floor(value / 60)}m ${value % 60}s`;
  return `${value}s`;
}

function donutGradient(segments: ChartSegmentView[]): string {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  if (!segments.length || total <= 0) return "var(--surface-raised)";
  let cursor = 0;
  const stops = segments.map((segment, index) => {
    const start = cursor;
    const end = index === segments.length - 1 ? 100 : Math.min(100, cursor + (segment.value / total) * 100);
    cursor = end;
    return `${toneColor(segment.tone)} ${start}% ${end}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

function toneColor(tone: UiTone): string {
  const colors: Record<UiTone, string> = {
    success: "var(--color-success)",
    info: "var(--color-blue)",
    warning: "var(--color-warning)",
    danger: "var(--color-danger)",
    neutral: "var(--color-gray)",
  };
  return colors[tone] ?? colors.neutral;
}

function toolText(value: string | null | undefined): string {
  if (!value) return "";
  const key = toolTextKeys[value];
  if (key) return t(key);

  const enabled = value.match(/^(\d+) enabled$/);
  if (enabled) return t("operations.tool.delta.enabled", { count: enabled[1] });

  const queued = value.match(/^(\d+) queued$/);
  if (queued) return t("operations.tool.delta.queued", { count: queued[1] });

  const retainedFailures = value.match(/^(\d+) retained failures$/);
  if (retainedFailures) return t("operations.tool.delta.retainedFailures", { count: retainedFailures[1] });

  return value;
}

function metricLabel(metric: UiMetricCard): string {
  return dynamicToolLabel("operations.tool.metric", metric.id, metric.label);
}

function metricDelta(metric: UiMetricCard): string {
  return toolText(metric.delta);
}

function tabLabel(tab: OperationsTab): string {
  return dynamicToolLabel("operations.tool.tab", tab.id, tab.label);
}

function primaryTableTabLabel(tab: OperationsTab): string {
  const key = {
    runs: "operations.tool.dashboard.tab.running",
    queue: "operations.tool.dashboard.tab.queued",
    waiting_io: "operations.tool.dashboard.tab.waitingIo",
  }[tab.id];
  return key ? t(key) : tabLabel(tab);
}

function cellText(row: UiTableRow, key: string): string {
  const value = row.cells[key];
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return value.text;
  return String(value);
}

function dynamicToolLabel(prefix: string, value: string, fallback?: string | null): string {
  const key = `${prefix}.${dynamicValueKeyPart(value)}`;
  if (hasI18nMessage(key)) return t(key);
  return titleCaseDynamicValue(fallback || value);
}

function resetToolRunFilters() {
  const filtersChanged = isToolRunFiltered.value;
  const offsetChanged = toolRunOffset.value !== 0;
  toolRunOffset.value = 0;
  toolStatusFilter.value = "all";
  toolTimeFilter.value = "all";
  toolSearchFilter.value = "";
  toolIdFilter.value = "";
  toolProviderFilter.value = "";
  toolModeFilter.value = "all";
  toolStrategyFilter.value = "all";
  toolEnvironmentFilter.value = "all";
  toolWorkerFilter.value = "";
  toolArtifactFilter.value = "all";
  toolRetryableFilter.value = "all";
  if (!filtersChanged && offsetChanged) void refreshPage();
}

function isKnownRunFilter(value: string | null): value is ToolStatusFilter {
  return Boolean(value && knownToolRunFilters.has(value as ToolStatusFilter));
}

function isKnownModeFilter(value: string | null): value is ToolModeFilter {
  return Boolean(value && knownToolModeFilters.has(value as ToolModeFilter));
}

function isKnownStrategyFilter(value: string | null): value is ToolStrategyFilter {
  return Boolean(value && knownToolStrategyFilters.has(value as ToolStrategyFilter));
}

function isKnownEnvironmentFilter(value: string | null): value is ToolEnvironmentFilter {
  return Boolean(value && knownToolEnvironmentFilters.has(value as ToolEnvironmentFilter));
}

function isKnownTernaryFilter(value: string | null): value is ToolTernaryFilter {
  return Boolean(value && knownToolTernaryFilters.has(value as ToolTernaryFilter));
}

function cellRouteValue(row: UiTableRow, key: string): string | null {
  const value = row.cells[key];
  const route = value && typeof value === "object" ? value.route : value;
  if (typeof route !== "string" || route === "-") return null;
  return route.replace(/^\/ui(?=\/)/, "");
}

function artifactPreviewItem(row: UiTableRow): ToolArtifactPreviewItem {
  const kind = cellText(row, "kind");
  const mimeType = cellText(row, "mime_type");
  const route = cellRouteValue(row, "route");
  const isImage = kind.toLowerCase() === "image" || mimeType.toLowerCase().startsWith("image/");
  const rawTime = cellText(row, "time");
  return {
    id: row.id,
    name: cellText(row, "name"),
    kind,
    mimeType,
    size: cellText(row, "size"),
    dimensions: cellText(row, "dimensions"),
    tool: compactToolLabel(cellText(row, "tool")),
    runId: cellText(row, "run_id"),
    time: /^(\d{4})-(\d{2})-(\d{2})T/.test(rawTime) ? formatLocalTime(rawTime) : rawTime,
    route,
    trace: cellText(row, "trace"),
    traceRoute: cellRouteValue(row, "trace_route"),
    imageSrc: isImage ? artifactAssetUrl(route) : null,
    isImage,
  };
}

function artifactAssetUrl(route: string | null): string | null {
  if (!route) return null;
  if (/^https?:\/\//.test(route)) return route;
  return buildApiUrl(route.startsWith("/") ? route : `/${route}`);
}

function rowRunId(row: UiTableRow): string {
  const runId = cellText(row, "run_id");
  return runId === "-" ? row.id : runId;
}

function rowWorkerId(row: UiTableRow): string {
  const workerId = cellText(row, "worker");
  return workerId === "-" ? row.id : workerId;
}

function lifecycleEventCard(row: UiTableRow, index: number): ToolLifecycleEventCardView {
  const details = splitEventDetails(cellText(row, "details"));
  const time = cellText(row, "time");
  const toolFull = cellText(row, "tool");
  return {
    id: `${row.id}:${index}`,
    time: /^(\d{4})-(\d{2})-(\d{2})T/.test(time) ? formatLocalTime(time) : time,
    level: eventLevelLabel(cellText(row, "level")),
    event: eventNameLabel(cellText(row, "event")),
    tool: compactToolLabel(toolFull),
    toolFull,
    runId: cellText(row, "run_id"),
    source: toolText(cellText(row, "source")),
    sourceRoute: cellRouteValue(row, "route"),
    assignment: cellText(row, "assignment"),
    worker: cellText(row, "worker"),
    status: eventStatusLabel(cellText(row, "status")),
    tone: row.tone ?? "neutral",
    details,
    detailsTitle: cellText(row, "details"),
    trace: cellText(row, "trace"),
    traceRoute: cellRouteValue(row, "trace_route"),
  };
}

function lifecycleEventTableRow(event: ToolLifecycleEventCardView): UiTableRow {
  return {
    id: event.id,
    status: event.status,
    tone: event.tone,
    cells: {
      time: event.time,
      event: event.event,
      status: event.status,
      tool: event.tool,
      run_id: linkCell(compactEntityId(event.runId), event.sourceRoute),
      source: linkCell(compactEntityId(event.source), event.sourceRoute),
      worker_id: compactEntityId(event.worker),
      route: event.sourceRoute ?? "-",
      trace_route: event.traceRoute ?? "-",
    },
  };
}

function linkCell(text: string, route: string | null) {
  return route ? { text, route } : text;
}

function splitEventDetails(value: string): string[] {
  if (!value || value === "-") return [];
  return value
    .split(/,\s*/)
    .map((item) => item.trim())
    .filter((item) => !duplicatedEventDetailKeys.has(item.split("=", 1)[0]?.toLowerCase()))
    .map((item) => item.replace(/^([a-z_]+)=/i, (_, key: string) => `${titleLabel(key)}: `))
    .filter(Boolean)
    .slice(0, 4);
}

const duplicatedEventDetailKeys = new Set([
  "assignment_id",
  "run_id",
  "tool_id",
  "worker_id",
]);

function compactToolLabel(value: string): string {
  return value.replace(/\s+\([^)]+\)$/, "");
}

function titleLabel(value: string): string {
  return titleCaseDynamicValue(value, value);
}

function eventLevelLabel(value: string): string {
  const normalized = titleLabel(value);
  return {
    Info: t("text.info"),
    Warning: t("text.warning"),
    Error: t("text.error"),
  }[normalized] ?? normalized;
}

function eventStatusLabel(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const key = {
    succeeded: "status.success",
    success: "status.success",
    failed: "status.failed",
    timed_out: "status.timedOut",
    cancelled: "status.cancelled",
    cancel_requested: "status.cancelRequested",
    running: "status.running",
    queued: "status.queued",
    dispatching: "status.dispatching",
    created: "status.created",
    expired: "text.expired",
    released: "text.released",
    assigned: "text.assigned",
    started: "text.started",
  }[normalized];
  return key ? t(key) : titleLabel(value);
}

function eventNameLabel(value: string): string {
  const normalized = value.replace(/^events\.named\./, "");
  const explicitKey = toolEventTextKeys[value] ?? toolEventTextKeys[normalized];
  if (explicitKey) return t(explicitKey);
  return dynamicToolLabel("operations.tool.event", normalized);
}

function compactEntityId(value: string): string {
  if (!value || value === "-") return "-";
  if (value.length <= 16) return value;
  return `${value.slice(0, 7)}...${value.slice(-5)}`;
}

function rowStatus(row: UiTableRow): string {
  return String(row.status ?? cellText(row, "status")).trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function isFailureStatus(status: string): boolean {
  return ["failed", "timed_out", "timeout", "cancelled", "error"].includes(status);
}

function canCancelToolRun(row: UiTableRow): boolean {
  const actions = cellText(row, "actions").toLowerCase();
  const status = rowStatus(row);
  return actions.includes("cancel") && !["succeeded", "failed", "cancelled", "timed_out"].includes(status);
}

function canRetryToolRun(row: UiTableRow): boolean {
  return cellText(row, "actions").toLowerCase().includes("retry");
}

function cancelFirstActiveRun() {
  const row = cancelableToolRuns.value[0];
  if (row) void cancelRun(row);
}

function isKnownTab(tabId: string | null): tabId is string {
  return Boolean(tabId && knownToolTabIds.has(tabId));
}

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
  if (tabId !== "events") {
    selectedLifecycleEventId.value = null;
  }
  if (tabId !== "workers") {
    selectedWorkerId.value = null;
  }
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (selectedTabId.value === "runs") {
    url.searchParams.delete("tab");
    if (toolStatusFilter.value === "all") {
      url.searchParams.delete("run_status");
    } else {
      url.searchParams.set("run_status", toolStatusFilter.value);
    }
  } else {
    url.searchParams.set("tab", selectedTabId.value);
    url.searchParams.delete("run_status");
  }
  window.history.replaceState({}, "", url);
}

function selectFailedRuns() {
  const failedRow = failedToolRunRows.value[0];
  if (failedRow) {
    openRunDetail(failedRow);
    return;
  }
  selectedTabId.value = "runs";
  toolStatusFilter.value = "failed";
  syncRunFilterUrl();
  void refreshPage();
}

function syncRunFilterUrl() {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (activeTab.value === "runs" && toolStatusFilter.value !== "all") {
    url.searchParams.delete("tab");
    url.searchParams.set("run_status", toolStatusFilter.value);
  } else {
    url.searchParams.delete("run_status");
  }
  const keyedFilters = [
    ["q", toolSearchFilter.value.trim()],
    ["tool_id", toolIdFilter.value.trim()],
    ["provider", toolProviderFilter.value.trim()],
    ["worker_id", toolWorkerFilter.value.trim()],
  ] as const;
  for (const [key, value] of keyedFilters) {
    if (activeTab.value === "runs" && value) {
      url.searchParams.set(key, value);
    } else {
      url.searchParams.delete(key);
    }
  }
  const enumFilters = [
    ["time_window", toolTimeFilter.value],
    ["mode", toolModeFilter.value],
    ["strategy", toolStrategyFilter.value],
    ["environment", toolEnvironmentFilter.value],
    ["has_artifact", toolArtifactFilter.value],
    ["retryable", toolRetryableFilter.value],
  ] as const;
  for (const [key, value] of enumFilters) {
    if (activeTab.value === "runs" && value !== "all") {
      url.searchParams.set(key, value);
    } else {
      url.searchParams.delete(key);
    }
  }
  window.history.replaceState({}, "", url);
}

function closeLifecycleEventDetail() {
  selectedLifecycleEventId.value = null;
}

function closeArtifactDetail() {
  selectedArtifactId.value = null;
}

function isUiTableRow(row: unknown): row is UiTableRow {
  return Boolean(row && typeof row === "object" && "cells" in row);
}

function openRunDetail(row: UiTableRow | Record<string, unknown>) {
  if (!isUiTableRow(row)) return;
  const runId = rowRunId(row);
  if (!runId || runId === "-") return;
  selectedArtifactId.value = null;
  selectedLifecycleEventId.value = null;
  selectedRunId.value = runId;
  void ensureRunDetail(runId);
}

function openWorkerDetail(row: UiTableRow | Record<string, unknown>) {
  if (!isUiTableRow(row)) return;
  const workerId = rowWorkerId(row);
  if (!workerId || workerId === "-") return;
  selectedArtifactId.value = null;
  selectedLifecycleEventId.value = null;
  selectedWorkerId.value = workerId;
}

function openLifecycleEventDetail(row: UiTableRow | Record<string, unknown>) {
  if (!isUiTableRow(row)) return;
  selectedArtifactId.value = null;
  selectedRunId.value = null;
  selectedWorkerId.value = null;
  selectedLifecycleEventId.value = row.id;
}

function openArtifactDetail(row: UiTableRow | ToolArtifactPreviewItem | Record<string, unknown>) {
  selectedRunId.value = null;
  selectedWorkerId.value = null;
  selectedLifecycleEventId.value = null;
  if (isUiTableRow(row)) {
    selectedArtifactId.value = row.id;
    return;
  }
  const id = typeof row.id === "string" ? row.id : null;
  if (id) selectedArtifactId.value = id;
}

function openMainTableRow(row: UiTableRow | Record<string, unknown>) {
  if (activeTab.value === "events") {
    openLifecycleEventDetail(row);
    return;
  }
  if (activeTab.value === "workers") {
    openWorkerDetail(row);
    return;
  }
  if (activeTab.value === "artifacts") {
    openArtifactDetail(row);
    return;
  }
  openRunDetail(row);
}

function closeRunDetail() {
  selectedRunId.value = null;
  runDetailError.value = null;
}

function closeWorkerDetail() {
  selectedWorkerId.value = null;
}

function formatPayload(payload: unknown): string {
  if (payload === null || payload === undefined || payload === "") return "-";
  if (typeof payload === "string") return payload;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function hasPayload(payload: unknown): boolean {
  if (payload === null || payload === undefined) return false;
  if (typeof payload === "string") return payload.trim().length > 0;
  if (Array.isArray(payload)) return payload.length > 0;
  if (typeof payload === "object") return Object.keys(payload).length > 0;
  return true;
}

function detailValue(detail: OperationsToolRunDetail, label: string): string {
  return detail.summary.find((item) => item.label === label)?.value ?? "-";
}

function contextValue(detail: OperationsToolRunDetail, label: string): string {
  return detail.invocation_context.find((item) => item.label === label)?.value ?? "-";
}

function detailTraceRoute(detail: OperationsToolRunDetail): string | null {
  const trace = detailValue(detail, "Trace");
  return trace && trace !== "-" ? `/trace/${encodeURIComponent(trace)}` : null;
}

function detailRunRoute(detail: OperationsToolRunDetail): string | null {
  const runId = contextValue(detail, "run_id");
  return runId && runId !== "-" ? `/workbench/runs/${encodeURIComponent(runId)}` : null;
}

function workerDetailHeaderTitle(detail: OperationsToolWorkerDetail): string {
  return detail.title || detail.worker_id;
}

function detailSectionTitle(title: string): string {
  return {
    "Assignment History": t("operations.toolDetail.assignmentHistory"),
    "Run Events": t("operations.toolDetail.runEvents"),
    "Artifacts": t("operations.toolDetail.artifacts"),
    "Worker Capabilities": t("operations.toolWorkerDetail.capabilities"),
    "Worker Runtime Registry": t("operations.toolWorkerDetail.runtimes"),
    "Worker Provider Limits": t("operations.toolWorkerDetail.providerLimits"),
    "Worker Events": t("operations.toolWorkerDetail.events"),
  }[title] ?? title;
}

function detailEmptyState(value: string | null | undefined): string {
  if (!value) return "";
  return {
    "No assignments recorded for this run.": t("operations.toolDetail.noAssignments"),
    "No observed events retained for this run.": t("operations.toolDetail.noEvents"),
    "No artifacts recorded for this run.": t("operations.toolDetail.noArtifacts"),
    "No runtime registrations reported by this worker.": t("operations.toolWorkerDetail.noRuntimes"),
    "No provider limiter metrics reported by this worker.": t("operations.toolWorkerDetail.noProviderLimits"),
    "No observed events retained for this worker.": t("operations.toolWorkerDetail.noEvents"),
  }[value] ?? value;
}

function detailSummaryLabel(label: string): string {
  return {
    "Tool": t("text.tool"),
    "Status": t("table.status"),
    "Mode": t("table.mode"),
    "Strategy": t("table.strategy"),
    "Environment": t("table.environment"),
    "Attempt": t("table.attempt"),
    "Worker ID": t("table.workerId"),
    "Assignment": t("table.assignment"),
    "Lease": t("table.lease"),
    "Duration": t("table.duration"),
    "Source": t("table.source"),
    "Trace": t("table.trace"),
    "Worker Load": t("table.workerLoad"),
    "Current Run": t("table.currentRun"),
    "Last Heartbeat": t("table.lastHeartbeat"),
    "Lease Expires At": t("table.leaseExpiresAt"),
    "Registered At": t("table.registeredAt"),
    "Age": t("table.age"),
    "Error Family": t("operations.toolDetail.errorFamily"),
    "Error Code": t("operations.toolDetail.errorCode"),
    "HTTP Status": t("operations.toolDetail.httpStatus"),
    "Retryable": t("operations.toolDetail.retryable"),
    "Root Cause": t("operations.toolDetail.rootCause"),
    "Runtime Count": t("table.runtimeCount"),
    "Providers": t("table.providers"),
    "Max In Flight": t("operations.toolWorkerDetail.maxInFlight"),
    "Current In Flight": t("operations.toolWorkerDetail.currentInFlight"),
    "Default Max In Flight": t("operations.toolWorkerDetail.defaultMaxInFlight"),
    "Image Max In Flight": t("operations.toolWorkerDetail.imageMaxInFlight"),
    "Shared State Max In Flight": t("operations.toolWorkerDetail.sharedStateMaxInFlight"),
    "Capability Groups": t("operations.toolWorkerDetail.capabilityGroups"),
  }[label] ?? label;
}

function detailSummaryText(value: string): string {
  if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return formatLocalTime(value);
  }
  const key = {
    "Running": t("status.running"),
    "Queued": t("status.queued"),
    "Failed": t("status.failed"),
    "Success": t("status.success"),
    "Succeeded": t("status.success"),
    "Cancelled": t("status.cancelled"),
    "Timed Out": t("status.timedOut"),
    "Cancel Requested": t("status.cancelRequested"),
    "Dispatching": t("status.dispatching"),
    "Created": t("status.created"),
    "background": t("text.background"),
    "inline": t("text.inline"),
    "async": t("text.async"),
    "local": t("text.local"),
    "remote": t("text.remote"),
    "Active": t("text.active"),
    "Online": t("text.online"),
    "Busy": t("operations.tool.worker.busy"),
    "Stale": t("operations.tool.worker.stale"),
    "Lease Expired": t("operations.tool.worker.leaseExpired"),
    "Expired": t("text.expired"),
    "Released": t("text.released"),
    "Started": t("text.started"),
    "Yes": t("common.yes"),
    "No": t("common.no"),
    "access": t("operations.tool.errorFamily.access"),
    "timeout": t("operations.tool.errorFamily.timeout"),
    "provider_limit": t("operations.tool.errorFamily.providerLimit"),
    "worker_lease": t("operations.tool.errorFamily.workerLease"),
    "network": t("operations.tool.errorFamily.network"),
    "validation": t("operations.tool.errorFamily.validation"),
    "execution": t("operations.tool.errorFamily.execution"),
    "access_denied": t("operations.tool.errorCode.accessDenied"),
    "tool_timeout": t("operations.tool.errorCode.toolTimeout"),
    "rate_limited": t("operations.tool.errorCode.rateLimited"),
    "lease_expired": t("operations.tool.errorCode.leaseExpired"),
    "network_error": t("operations.tool.errorCode.networkError"),
    "invalid_payload": t("operations.tool.errorCode.invalidPayload"),
    "tool_execution_failed": t("operations.tool.errorCode.executionFailed"),
  }[value];
  if (key) return key;
  return isEnumLikeValue(value) ? titleLabel(value) : value;
}

function isEnumLikeValue(value: string): boolean {
  return /^[a-z][a-z0-9_-]+$/.test(value) || /^[A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+)+$/.test(value);
}

async function cancelRun(row: UiTableRow) {
  const runId = rowRunId(row);
  if (!runId || runId === "-" || cancelBusyRunId.value || retryBusyRunId.value) return;
  const confirmed = window.confirm(t("operations.tool.action.cancelConfirm", { runId }));
  if (!confirmed) return;
  cancelBusyRunId.value = runId;
  actionError.value = null;
  actionNotice.value = null;
  try {
    const result = await cancelToolRun(runId);
    actionNotice.value = t("operations.tool.action.cancelNotice", {
      runId: result.id,
      status: eventStatusLabel(result.status),
    });
    await refreshPage();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    cancelBusyRunId.value = null;
  }
}

async function retryRun(row: UiTableRow) {
  const runId = rowRunId(row);
  if (!runId || runId === "-" || retryBusyRunId.value || cancelBusyRunId.value) return;
  const confirmed = window.confirm(t("operations.tool.action.retryConfirm", { runId }));
  if (!confirmed) return;
  retryBusyRunId.value = runId;
  actionError.value = null;
  actionNotice.value = null;
  try {
    const result = await retryToolRun(runId);
    actionNotice.value = t("operations.tool.action.retryNotice", {
      runId: result.id,
      status: eventStatusLabel(result.status),
    });
    await refreshPage();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    retryBusyRunId.value = null;
  }
}

async function pruneExpiredWorkers() {
  if (pruneWorkersBusy.value) return;
  const confirmed = window.confirm(t("operations.tool.action.pruneWorkersConfirm"));
  if (!confirmed) return;
  pruneWorkersBusy.value = true;
  actionError.value = null;
  actionNotice.value = null;
  try {
    const result = await pruneExpiredToolWorkers();
    actionNotice.value = t("operations.tool.action.pruneWorkersNotice", {
      count: result.pruned_count,
    });
    await refreshPage();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    pruneWorkersBusy.value = false;
  }
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadToolOperations({
      status: toolStatusFilter.value,
      time_window: toolTimeFilter.value,
      search: toolSearchFilter.value.trim() || undefined,
      tool_id: toolIdFilter.value.trim() || undefined,
      provider: toolProviderFilter.value.trim() || undefined,
      mode: toolModeFilter.value,
      strategy: toolStrategyFilter.value,
      environment: toolEnvironmentFilter.value,
      worker_id: toolWorkerFilter.value.trim() || undefined,
      has_artifact: toolArtifactFilter.value,
      retryable: toolRetryableFilter.value,
      limit: toolRunPageSize,
      offset: toolRunOffset.value,
    });
    page.value = loaded.page;
    loadError.value = null;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function ensureRunDetail(runId: string) {
  if (loadedRunDetails.value[runId]) return;
  runDetailLoading.value = true;
  runDetailError.value = null;
  try {
    const detail = await loadToolRunDetail(runId);
    if (detail) {
      loadedRunDetails.value = {
        ...loadedRunDetails.value,
        [detail.run_id]: detail,
      };
    }
  } catch (error) {
    runDetailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    runDetailLoading.value = false;
  }
}

watch(page, () => {
  if (selectedWorkerId.value && !workerDetailById.value.has(selectedWorkerId.value)) {
    selectedWorkerId.value = null;
  }
  if (
    selectedLifecycleEventId.value
    && !lifecycleEventCards.value.some((event) => event.id === selectedLifecycleEventId.value)
  ) {
    selectedLifecycleEventId.value = null;
  }
  if (
    selectedArtifactId.value
    && !artifactDetailItems.value.some((artifact) => artifact.id === selectedArtifactId.value)
  ) {
    selectedArtifactId.value = null;
  }
});

watch([
  toolStatusFilter,
  toolTimeFilter,
  toolSearchFilter,
  toolIdFilter,
  toolProviderFilter,
  toolModeFilter,
  toolStrategyFilter,
  toolEnvironmentFilter,
  toolWorkerFilter,
  toolArtifactFilter,
  toolRetryableFilter,
], () => {
  toolRunOffset.value = 0;
  syncRunFilterUrl();
  void refreshPage();
});

onMounted(() => {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const tabId = params.get("tab");
    const runFilter = params.get("run_status") ?? params.get("status");
    if (isKnownTab(tabId)) selectedTabId.value = tabId;
    if (isKnownRunFilter(runFilter)) toolStatusFilter.value = runFilter;
    if (params.get("time_window") === "24h") toolTimeFilter.value = "24h";
    toolSearchFilter.value = params.get("q") ?? "";
    toolIdFilter.value = params.get("tool_id") ?? "";
    toolProviderFilter.value = params.get("provider") ?? "";
    const modeFilter = params.get("mode");
    const strategyFilter = params.get("strategy");
    const environmentFilter = params.get("environment");
    if (isKnownModeFilter(modeFilter)) toolModeFilter.value = modeFilter;
    if (isKnownStrategyFilter(strategyFilter)) toolStrategyFilter.value = strategyFilter;
    if (isKnownEnvironmentFilter(environmentFilter)) toolEnvironmentFilter.value = environmentFilter;
    toolWorkerFilter.value = params.get("worker_id") ?? "";
    const artifactFilter = params.get("has_artifact");
    const retryableFilter = params.get("retryable");
    if (isKnownTernaryFilter(artifactFilter)) toolArtifactFilter.value = artifactFilter;
    if (isKnownTernaryFilter(retryableFilter)) toolRetryableFilter.value = retryableFilter;
  }
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

const toolTextKeys: Record<string, string> = {
  "Tool Runtime": "operations.tool.title",
  "Tool Runs": "operations.tool.tab.runs",
  "Workers": "operations.tool.tab.workers",
  "Queue": "operations.tool.tab.queue",
  "Capabilities": "operations.tool.tab.capabilities",
  "Diagnostics": "operations.tool.tab.diagnostics",
  "Risk": "operations.tool.tab.risk",
  "Artifacts": "operations.tool.tab.artifacts",
  "Events": "operations.tool.tab.events",
  "Strategies": "operations.tool.tab.strategies",
  "Waiting IO": "operations.tool.dashboard.waitingIo",
  "Active Tool Runs": "operations.tool.dashboard.tab.running",
  "Queued Tool Runs": "operations.tool.dashboard.tab.queued",
  "Failed Tool Runs (24h)": "operations.tool.dashboard.failedRuns",
  "Average Latency": "operations.tool.dashboard.avgLatency",
  "P95 Latency": "operations.tool.dashboard.p95Latency",
  "Throughput": "operations.tool.dashboard.throughput",
  "Tool Run Records": "operations.tool.section.runRecords",
  "Recent Tool Runs": "operations.tool.section.recentRuns",
  "Tool Types": "operations.tool.section.toolTypes",
  "Tool Call Share": "operations.tool.section.toolCallShare",
  "Tool Types by Runs": "operations.tool.section.toolTypesByRuns",
  "Tool Types by Catalog": "operations.tool.section.toolTypesByCatalog",
  "Other Tools": "operations.tool.section.otherTools",
  "Runtime Risk / Access": "operations.tool.section.runtimeRiskAccess",
  "Worker Pool Overview": "operations.tool.section.workerPool",
  "Worker Pool by Registrations": "operations.tool.section.workerPoolRegistrations",
  "Worker Pool by Current Registrations": "operations.tool.section.workerPoolCurrentRegistrations",
  "Worker Pool by Active Runs": "operations.tool.section.workerPoolActiveRuns",
  "No tool workers registered.": "operations.tool.empty.noWorkers",
  "Tool Queue": "operations.tool.section.queue",
  "Capability Concurrency": "operations.tool.section.capabilityConcurrency",
  "Provider Limits": "operations.tool.section.providerLimits",
  "Provider History": "operations.tool.section.providerHistory",
  "Run Scheduling Diagnostics": "operations.tool.section.runDiagnostics",
  "Inline Risk": "operations.tool.section.inlineRisk",
  "Active Inline Runs": "operations.tool.inlineRisk.activeRuns",
  "Inline Share": "operations.tool.inlineRisk.share",
  "Inline Failures": "operations.tool.inlineRisk.failures",
  "Longest Inline Duration": "operations.tool.inlineRisk.longestDuration",
  "Recent Artifacts": "operations.tool.section.recentArtifacts",
  "Tool Lifecycle Events": "operations.tool.section.lifecycleEvents",
  "Execution Strategies": "operations.tool.section.executionStrategies",
  "Admin": "common.admin",
  "No records.": "table.noRecords",
  "No tool runs recorded.": "operations.tool.empty.noRuns",
  "No tool runs match the current filters.": "operations.tool.empty.noFilteredRuns",
  "No tool type data.": "operations.tool.empty.noToolTypes",
  "No access or confirmation risks detected.": "operations.tool.empty.noRisk",
  "No active worker-held runs.": "operations.tool.empty.noWorkerRuns",
  "No active tool runs.": "operations.tool.empty.noActiveRuns",
  "No waiting tool runs.": "operations.tool.empty.noWaitingRuns",
  "No provider I/O waits.": "operations.tool.dashboard.noWaitingIo",
  "No tool capability groups observed.": "operations.tool.empty.noCapabilityGroups",
  "No remote provider limiter metrics observed.": "operations.tool.empty.noProviderLimits",
  "No provider runtime history observed.": "operations.tool.empty.noProviderHistory",
  "No active tool runs need scheduling diagnostics.": "operations.tool.empty.noDiagnostics",
  "No active tool run has exceeded 5 minutes.": "operations.tool.empty.noLongRunning",
  "No inline risk data.": "operations.tool.empty.noInlineRisk",
  "No tool artifacts observed.": "operations.tool.empty.noArtifacts",
  "No tool lifecycle events observed yet.": "operations.tool.empty.noLifecycleEvents",
  "No tool execution strategies observed.": "operations.tool.empty.noStrategies",
  "Tool runtime state is queryable": "operations.tool.delta.queryable",
  "Operator attention recommended": "operations.tool.delta.attentionRecommended",
  "Operator action required": "operations.tool.delta.actionRequired",
  "Insufficient data": "operations.tool.delta.insufficientData",
  "retained tool run records": "operations.tool.delta.retainedRecords",
  "terminal tool runs": "operations.tool.delta.terminalRuns",
  "24h when available": "operations.tool.delta.window24hAvailable",
  "last 24h": "operations.tool.delta.last24h",
  "tools require operator consent": "operations.tool.delta.confirmationRequired",
  "tools with access requirements": "operations.tool.delta.accessGated",
  "监控工具执行、队列、worker、产物与策略": "operations.tool.subtitleShort",
  "监控工具从触发到完成的全链路：排队、调度、执行、I/O 等待、产物产出与策略治理。": "operations.tool.subtitleFull",
  "工具目录、运行队列、worker 占用、权限风险、失败和产物的运维视图。": "operations.tool.subtitle",
  "Function": "operations.tool.kind.function",
  "Http": "operations.tool.kind.http",
  "Mcp": "operations.tool.kind.mcp",
  "Workflow": "operations.tool.kind.workflow",
  "Unknown": "status.unknown",
  "Ready": "text.ready",
  "Saturated": "text.saturated",
  "Started": "text.started",
  "No Worker": "text.noWorker",
  "No worker": "text.noWorker",
  "Default tool groups": "text.defaultToolGroups",
  "Image generation": "text.imageGeneration",
  "Browser shared state": "text.browserSharedState",
  "Workspace shared state": "text.workspaceSharedState",
  "Mobile shared state": "text.mobileSharedState",
  "Session shared state": "text.sessionSharedState",
  "Command shared state": "text.commandSharedState",
  "System shared state": "text.systemSharedState",
  "capacity available": "text.capacityAvailable",
  "worker slots full": "text.workerSlotsFull",
  "no online worker": "text.noOnlineWorker",
  "Idle": "operations.tool.worker.idle",
  "Busy": "operations.tool.worker.busy",
  "Stale": "operations.tool.worker.stale",
  "Lease Expired": "operations.tool.worker.leaseExpired",
  "worker.capabilities_updated": "operations.tool.event.workerCapabilitiesUpdated",
  "worker.recovered": "operations.tool.event.workerRecovered",
  "worker.pruned": "operations.tool.event.workerPruned",
  "Event Bus": "operations.tool.source.eventBus",
};

const toolEventTextKeys: Record<string, string> = {
  "tool.run.created": "operations.tool.event.toolRunCreated",
  "tool.run.queued": "operations.tool.event.toolRunQueued",
  "tool.run.dispatching": "operations.tool.event.toolRunDispatching",
  "tool.run.started": "operations.tool.event.toolRunStarted",
  "tool.run.succeeded": "operations.tool.event.toolRunSucceeded",
  "tool.run.failed": "operations.tool.event.toolRunFailed",
  "tool.run.requeued": "operations.tool.event.toolRunRequeued",
  "tool.run.cancel_requested": "operations.tool.event.toolRunCancelRequested",
  "tool.run.cancelled": "operations.tool.event.toolRunCancelled",
  "tool.run.timed_out": "operations.tool.event.toolRunTimedOut",
  "tool.assignment.created": "operations.tool.event.toolAssignmentCreated",
  "tool.assignment.started": "operations.tool.event.toolAssignmentStarted",
  "tool.assignment.succeeded": "operations.tool.event.toolAssignmentSucceeded",
  "tool.assignment.failed": "operations.tool.event.toolAssignmentFailed",
  "tool.assignment.cancelled": "operations.tool.event.toolAssignmentCancelled",
  "tool.assignment.expired": "operations.tool.event.toolAssignmentExpired",
  "tool.worker.registered": "operations.tool.event.toolWorkerRegistered",
  "tool.worker.recovered": "operations.tool.event.workerRecovered",
  "tool.worker.capabilities_updated": "operations.tool.event.workerCapabilitiesUpdated",
  "tool.worker.stale": "operations.tool.event.toolWorkerStale",
  "tool.worker.pruned": "operations.tool.event.workerPruned",
};
</script>

<template>
  <main class="operations-module-console tool-console scroll-area">
    <header class="tool-header">
      <div class="tool-title-block">
        <h2>{{ toolText(page?.title ?? "Tool Runtime") }}</h2>
        <p>{{ toolText(page?.subtitle ?? "监控工具从触发到完成的全链路：排队、调度、执行、I/O 等待、产物产出与策略治理。") }}</p>
      </div>
      <dl class="tool-header__controls">
        <div v-for="item in headerControlItems" :key="item.id">
          <dt>{{ item.label }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>
      <div class="tool-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton class="role-badge" size="sm" variant="secondary">
          <ShieldAlert :size="13" /> {{ t("operations.currentRoleLabel") }}: {{ toolText(page?.role.label ?? "Admin") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" disabled>
          <Pause :size="13" />
          {{ t("operations.tool.action.pauseCalls") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" disabled>
          <Zap :size="13" />
          {{ t("operations.tool.action.drainQueue") }}
        </UiButton>
        <UiButton
          size="sm"
          variant="danger"
          :disabled="!cancelableToolRuns.length || cancelBusyRunId !== null"
          @click="cancelFirstActiveRun"
        >
          <Square :class="{ 'motion-spin': cancelBusyRunId !== null }" :size="13" />
          {{ t("operations.tool.action.stopRuns") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="tool-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>
    <div v-if="actionError || actionNotice" class="tool-alert" :class="{ 'tool-alert--success': actionNotice && !actionError }">
      <StatusDot :tone="actionError ? 'danger' : 'success'" />
      <span>{{ actionError ?? actionNotice }}</span>
    </div>

    <section class="tool-metrics">
      <article v-for="metric in dashboardMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
        <span class="metric-copy">
          <em>{{ metric.label }}</em>
          <strong>{{ metric.value }}</strong>
          <small>{{ metric.helper }}</small>
        </span>
        <i class="metric-spark"><span :style="{ width: `${Math.max(12, metric.fillPct)}%` }" /></i>
      </article>
    </section>

    <section class="tool-dashboard-grid">
      <div class="tool-dashboard-main">
        <section class="tool-live-grid">
          <article class="tool-runs-panel tool-live-card tool-live-card--active">
            <div class="panel-heading">
              <h3>{{ t("operations.tool.dashboard.tab.running") }} <span>{{ activeDashboardTable.total ?? activeDashboardTable.rows.length }}</span></h3>
              <a href="/operations/tool?tab=runs" @click.prevent="selectTab('runs')">{{ t("common.viewAll") }}</a>
            </div>
            <DataTable
              v-if="activeDashboardTable.rows.length"
              :columns="activeDashboardTable.columns"
              :rows="activeDashboardTable.rows"
              section-id="active-tool-runs"
              :page-size="5"
              clickable-rows
              @row-click="openRunDetail"
            />
            <p v-else class="panel-empty">{{ t("operations.tool.empty.noActiveRuns") }}</p>
          </article>
          <article class="tool-runs-panel tool-live-card">
            <div class="panel-heading">
              <h3>{{ t("operations.tool.dashboard.tab.queued") }} <span>{{ queueDashboardTable.total ?? queueDashboardTable.rows.length }}</span></h3>
              <a href="/operations/tool?tab=queue" @click.prevent="selectTab('queue')">{{ t("common.viewAll") }}</a>
            </div>
            <DataTable
              v-if="queueDashboardTable.rows.length"
              :columns="queueDashboardTable.columns"
              :rows="queueDashboardTable.rows"
              section-id="tool-queue-runs"
              :page-size="5"
              clickable-rows
              @row-click="openRunDetail"
            />
            <p v-else class="panel-empty">{{ t("operations.tool.empty.noWaitingRuns") }}</p>
          </article>
          <article class="tool-runs-panel tool-live-card">
            <div class="panel-heading">
              <h3>{{ t("operations.tool.dashboard.waitingIo") }} <span>{{ waitingDashboardTable.total ?? waitingDashboardTable.rows.length }}</span></h3>
              <a href="/operations/tool?tab=waiting_io" @click.prevent="selectTab('waiting_io')">{{ t("common.viewAll") }}</a>
            </div>
            <DataTable
              v-if="waitingDashboardTable.rows.length"
              :columns="waitingDashboardTable.columns"
              :rows="waitingDashboardTable.rows"
              section-id="waiting-io-runs"
              :page-size="5"
              clickable-rows
              @row-click="openRunDetail"
            />
            <p v-else class="panel-empty">{{ t("operations.tool.dashboard.noWaitingIo") }}</p>
          </article>
        </section>

        <article class="tool-runs-panel tool-records-panel">
          <div class="panel-heading panel-heading--records">
            <h3>{{ t("operations.tool.section.runRecords") }}</h3>
            <button class="tool-filter-button" type="button" @click="resetToolRunFilters">
              <ListFilter :size="13" /> {{ t("operations.tool.filter.filters") }}
            </button>
          </div>
          <div class="tool-record-toolbar">
            <label>
              <span>{{ t("operations.tool.filter.status") }}</span>
              <select v-model="toolStatusFilter">
                <option value="all">{{ t("operations.tool.filter.allStatuses") }}</option>
                <option value="active">{{ t("operations.tool.filter.active") }}</option>
                <option value="running">{{ t("operations.tool.filter.running") }}</option>
                <option value="waiting">{{ t("operations.tool.filter.waiting") }}</option>
                <option value="succeeded">{{ t("operations.tool.filter.succeeded") }}</option>
                <option value="failed">{{ t("operations.tool.filter.failed") }}</option>
                <option value="cancelled">{{ t("operations.tool.filter.cancelled") }}</option>
              </select>
            </label>
            <label>
              <span>{{ t("operations.tool.filter.tool") }}</span>
              <input v-model="toolIdFilter" type="search" :placeholder="t('operations.tool.filter.toolPlaceholder')" />
            </label>
            <label>
              <span>{{ t("operations.tool.filter.time") }}</span>
              <select v-model="toolTimeFilter">
                <option value="all">{{ t("operations.tool.filter.allTime") }}</option>
                <option value="24h">{{ t("operations.tool.filter.last24h") }}</option>
              </select>
            </label>
            <label class="tool-record-toolbar__search">
              <span>{{ t("operations.tool.filter.search") }}</span>
              <input v-model="toolSearchFilter" type="search" :placeholder="t('operations.tool.filter.searchPlaceholder')" />
            </label>
            <label>
              <span>{{ t("operations.tool.filter.worker") }}</span>
              <input v-model="toolWorkerFilter" type="search" :placeholder="t('operations.tool.filter.workerPlaceholder')" />
            </label>
          </div>
          <DataTable
            v-if="toolRunRecordsTable.rows.length"
            :columns="toolRunRecordsTable.columns"
            :rows="toolRunRecordsTable.rows"
            section-id="tool-run-records"
            :page-size="7"
            clickable-rows
            @row-click="openRunDetail"
          />
          <div v-else class="state-empty state-empty--success">
            <span><CheckCircle2 :size="18" /></span>
            <strong>{{ t(isToolRunFiltered ? 'operations.tool.emptyTitle.noFilteredRuns' : 'operations.tool.emptyTitle.noRuns') }}</strong>
            <p>{{ toolText(toolRunRecordsTable.empty_state) }}</p>
          </div>
          <footer class="tool-table-footer">
            <div class="tool-table-footer__copy">
              <span>{{ toolRunRecordsFooter }}</span>
              <span v-if="toolRunRecordsTable.rows.length">{{ t("operations.tool.hint.clickRow") }}</span>
            </div>
          </footer>
        </article>

        <article class="tool-runs-panel tool-artifacts-panel tool-artifacts-panel--wide">
          <div class="panel-heading">
            <h3>{{ toolText(artifactsTable.title) }} <span>{{ artifactsTable.total ?? artifactDetailItems.length }}</span></h3>
            <a href="/operations/tool?tab=artifacts" @click.prevent="selectTab('artifacts')">{{ t("operations.tool.action.viewAllArtifacts") }}</a>
          </div>
          <div v-if="artifactDetailItems.length" class="artifact-preview-grid">
            <button
              v-for="artifact in artifactDetailItems.slice(0, 6)"
              :key="artifact.id"
              type="button"
              class="artifact-preview-card"
              @click="openArtifactDetail(artifact)"
            >
              <span class="artifact-preview-media">
                <img v-if="artifact.imageSrc" :src="artifact.imageSrc" :alt="artifact.name" />
                <FileText v-else :size="24" />
                <em>{{ artifact.kind }}</em>
              </span>
              <span class="artifact-preview-copy">
                <strong :title="artifact.name">{{ artifact.name }}</strong>
                <small :title="artifact.runId">{{ artifact.runId }} · {{ artifact.time }}</small>
                <em :title="artifact.mimeType">{{ artifact.dimensions }} · {{ artifact.size }}</em>
              </span>
            </button>
          </div>
          <p v-else class="panel-empty">{{ t("operations.tool.empty.noArtifacts") }}</p>
        </article>
      </div>

      <aside class="tool-side-stack">
        <article class="tool-types-panel tool-donut-panel">
          <div class="panel-heading">
            <h3>{{ toolText(page?.tool_types.title ?? "Tool Types") }} <span>{{ page?.tool_types.total ?? 0 }}</span></h3>
            <a href="/operations/tool?tab=runs" @click.prevent="selectTab('runs')">{{ t("common.viewAll") }}</a>
          </div>
          <div v-if="toolTypeSegments.length" class="tool-donut-body">
            <div class="tool-donut" :style="toolTypeDonutStyle">
              <strong>{{ page?.tool_types.total ?? 0 }}</strong>
              <span>{{ t("operations.tool.dashboard.totalCallsShort") }}</span>
            </div>
            <ul>
              <li v-for="type in toolTypeSegments" :key="type.id">
                <span><StatusDot :tone="type.tone" />{{ toolText(type.label) }}</span>
                <em>{{ type.pct }}% ({{ type.value }})</em>
              </li>
            </ul>
          </div>
          <p v-else class="panel-empty">{{ t("operations.tool.empty.noToolTypes") }}</p>
        </article>

        <article class="tool-side-card">
          <div class="panel-heading">
            <h3>{{ t("operations.tool.dashboard.latencyDistribution") }}</h3>
            <a href="/operations/tool?tab=provider_history" @click.prevent="selectTab('provider_history')">{{ t("common.viewAll") }}</a>
          </div>
          <dl class="latency-summary">
            <div><dt>{{ t("operations.tool.dashboard.avgLatency") }}</dt><dd>{{ formatDurationSeconds(weightedAvgDurationSeconds) }}</dd></div>
            <div><dt>{{ t("operations.tool.dashboard.maxLatency") }}</dt><dd>{{ formatDurationSeconds(maxDurationSeconds) }}</dd></div>
            <div><dt>{{ t("table.providers") }}</dt><dd>{{ providerHistoryTable.total ?? providerHistoryTable.rows.length }}</dd></div>
          </dl>
          <ul v-if="latencyProviderItems.length" class="latency-bars">
            <li v-for="item in latencyProviderItems" :key="item.id">
              <span>{{ item.provider }}</span>
              <strong>{{ item.avg }}</strong>
              <i><em :style="{ width: `${item.pct}%` }" /></i>
            </li>
          </ul>
          <p v-else class="panel-empty">{{ t("operations.tool.empty.noProviderHistory") }}</p>
        </article>

        <article class="tool-side-card">
          <div class="panel-heading">
            <h3>{{ t("operations.tool.dashboard.failureAnalysis") }}</h3>
            <a href="/operations/tool?run_status=failed" @click.prevent="selectFailedRuns">{{ t("operations.tool.action.viewFailureDetails") }}</a>
          </div>
          <ul v-if="failureSummaryItems.length" class="failure-list">
            <li v-for="item in failureSummaryItems" :key="item.id">
              <span><StatusDot :tone="item.tone" />{{ item.label }}</span>
              <strong>{{ item.count }} <em>({{ item.pct }}%)</em></strong>
            </li>
          </ul>
          <p v-else class="panel-empty">{{ t("operations.tool.dashboard.noFailures") }}</p>
        </article>

        <article class="tool-side-card">
          <div class="panel-heading">
            <h3>{{ t("operations.tool.dashboard.externalHealth") }}</h3>
            <a href="/operations/tool?tab=provider_history" @click.prevent="selectTab('provider_history')">{{ t("common.viewAll") }}</a>
          </div>
          <ul v-if="providerHealthItems.length" class="provider-health-list">
            <li v-for="item in providerHealthItems" :key="item.id">
              <span><StatusDot :tone="item.tone" />{{ item.name }}</span>
              <strong :class="`provider-state provider-state--${item.tone}`">{{ item.state }}</strong>
              <em>{{ item.latency }}</em>
            </li>
          </ul>
          <p v-else class="panel-empty">{{ t("operations.tool.empty.noProviderHistory") }}</p>
        </article>
      </aside>
    </section>

    <Teleport to="body">
      <div v-if="selectedRunId" class="run-detail-overlay" @click.self="closeRunDetail">
        <aside class="run-detail-drawer" role="dialog" aria-modal="true" :aria-label="t('operations.toolDetail.ariaLabel')">
          <template v-if="selectedRunDetail">
          <header class="run-detail-header">
            <div>
              <span class="run-detail-kicker">{{ t("operations.toolDetail.title") }}</span>
              <h2>{{ selectedRunDetail.title }}</h2>
              <p>{{ selectedRunDetail.run_id }}</p>
            </div>
            <div class="run-detail-actions">
              <a v-if="detailRunRoute(selectedRunDetail)" :href="detailRunRoute(selectedRunDetail) ?? '#'" class="drawer-link">
                <ExternalLink :size="13" /> {{ t("operations.toolDetail.workbench") }}
              </a>
              <a v-if="detailTraceRoute(selectedRunDetail)" :href="detailTraceRoute(selectedRunDetail) ?? '#'" class="drawer-link">
                <ExternalLink :size="13" /> {{ t("operations.toolDetail.trace") }}
              </a>
              <button type="button" class="drawer-close" :aria-label="t('operations.toolDetail.close')" @click="closeRunDetail">
                <X :size="15" />
              </button>
            </div>
          </header>

          <section class="run-detail-summary">
            <dl>
              <div v-for="item in selectedRunDetail.summary" :key="item.label" :class="`summary-item summary-item--${item.tone ?? 'neutral'}`">
                <dt>{{ detailSummaryLabel(item.label) }}</dt>
                <dd>{{ detailSummaryText(item.value) }}</dd>
              </div>
            </dl>
          </section>

          <section v-if="selectedRunDetail.error !== '-'" class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ t("operations.toolDetail.error") }}</h3>
            </div>
            <dl v-if="selectedRunDetail.error_facts.items.length" class="context-list error-facts-list">
              <div v-for="item in selectedRunDetail.error_facts.items" :key="item.label" :class="`summary-item--${item.tone ?? 'neutral'}`">
                <dt>{{ detailSummaryLabel(item.label) }}</dt>
                <dd>{{ detailSummaryText(item.value) }}</dd>
              </div>
            </dl>
            <pre class="drawer-error-pre">{{ selectedRunDetail.error }}</pre>
          </section>

          <section class="run-detail-section run-detail-payloads">
            <article>
              <div class="drawer-section-heading">
                <h3>{{ t("operations.toolDetail.input") }}</h3>
              </div>
              <pre v-if="hasPayload(selectedRunDetail.input_payload)">{{ formatPayload(selectedRunDetail.input_payload) }}</pre>
              <p v-else class="drawer-empty">{{ t("operations.toolDetail.noInput") }}</p>
            </article>
            <article>
              <div class="drawer-section-heading">
                <h3>{{ t("operations.toolDetail.result") }}</h3>
                <span>{{ selectedRunDetail.result_summary }}</span>
              </div>
              <pre v-if="hasPayload(selectedRunDetail.result_payload)">{{ formatPayload(selectedRunDetail.result_payload) }}</pre>
              <p v-else class="drawer-empty">{{ t("operations.toolDetail.noResult") }}</p>
            </article>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ t("operations.toolDetail.invocationContext") }}</h3>
            </div>
            <dl v-if="selectedRunDetail.invocation_context.length" class="context-list">
              <div v-for="item in selectedRunDetail.invocation_context" :key="item.label">
                <dt>{{ item.label }}</dt>
                <dd>{{ item.value }}</dd>
              </div>
            </dl>
            <p v-else class="drawer-empty">{{ t("operations.toolDetail.noContext") }}</p>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ detailSectionTitle(selectedRunDetail.assignments.title) }}</h3>
              <span>{{ selectedRunDetail.assignments.total ?? selectedRunDetail.assignments.rows.length }}</span>
            </div>
            <DataTable
              v-if="selectedRunDetail.assignments.rows.length"
              :columns="selectedRunDetail.assignments.columns"
              :rows="selectedRunDetail.assignments.rows"
              section-id="run-assignment-history"
              :page-size="4"
            />
            <p v-else class="drawer-empty">{{ detailEmptyState(selectedRunDetail.assignments.empty_state) }}</p>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ detailSectionTitle(selectedRunDetail.events.title) }}</h3>
              <span>{{ selectedRunDetail.events.total ?? selectedRunDetail.events.rows.length }}</span>
            </div>
            <DataTable
              v-if="selectedRunDetail.events.rows.length"
              :columns="selectedRunDetail.events.columns"
              :rows="selectedRunDetail.events.rows"
              section-id="run-events"
              :page-size="5"
            />
            <p v-else class="drawer-empty">{{ detailEmptyState(selectedRunDetail.events.empty_state) }}</p>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ detailSectionTitle(selectedRunDetail.artifacts.title) }}</h3>
              <span>{{ selectedRunDetail.artifacts.total ?? selectedRunDetail.artifacts.rows.length }}</span>
            </div>
            <DataTable
              v-if="selectedRunDetail.artifacts.rows.length"
              :columns="selectedRunDetail.artifacts.columns"
              :rows="selectedRunDetail.artifacts.rows"
              section-id="run-artifacts"
              :page-size="4"
            />
            <p v-else class="drawer-empty">{{ detailEmptyState(selectedRunDetail.artifacts.empty_state) }}</p>
          </section>
          </template>
          <template v-else>
            <header class="run-detail-header">
              <div>
                <span class="run-detail-kicker">{{ t("operations.toolDetail.title") }}</span>
                <h2>{{ selectedRunId }}</h2>
                <p>{{ runDetailLoading ? t("common.loading") : (runDetailError ?? t("table.noRecords")) }}</p>
              </div>
              <div class="run-detail-actions">
                <button type="button" class="drawer-close" :aria-label="t('operations.toolDetail.close')" @click="closeRunDetail">
                  <X :size="15" />
                </button>
              </div>
            </header>
          </template>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="selectedWorkerDetail" class="run-detail-overlay" @click.self="closeWorkerDetail">
        <aside class="run-detail-drawer worker-detail-drawer" role="dialog" aria-modal="true" :aria-label="t('operations.toolWorkerDetail.ariaLabel')">
          <header class="run-detail-header">
            <div>
              <span class="run-detail-kicker">{{ t("operations.toolWorkerDetail.title") }}</span>
              <h2><StatusDot :tone="selectedWorkerDetail.tone" />{{ workerDetailHeaderTitle(selectedWorkerDetail) }}</h2>
              <p>{{ selectedWorkerDetail.worker_id }} · {{ detailSummaryText(selectedWorkerDetail.status) }}</p>
            </div>
            <div class="run-detail-actions">
              <button type="button" class="drawer-close" :aria-label="t('operations.toolDetail.close')" @click="closeWorkerDetail">
                <X :size="15" />
              </button>
            </div>
          </header>

          <section class="run-detail-summary">
            <dl>
              <div v-for="item in selectedWorkerDetail.summary" :key="item.label" :class="`summary-item summary-item--${item.tone ?? 'neutral'}`">
                <dt>{{ detailSummaryLabel(item.label) }}</dt>
                <dd :title="detailSummaryText(item.value)">{{ detailSummaryText(item.value) }}</dd>
              </div>
            </dl>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ detailSectionTitle(selectedWorkerDetail.capabilities.title) }}</h3>
              <span>{{ selectedWorkerDetail.capabilities.items.length }}</span>
            </div>
            <dl v-if="selectedWorkerDetail.capabilities.items.length" class="context-list">
              <div v-for="item in selectedWorkerDetail.capabilities.items" :key="item.label">
                <dt>{{ detailSummaryLabel(item.label) }}</dt>
                <dd :title="detailSummaryText(item.value)">{{ detailSummaryText(item.value) }}</dd>
              </div>
            </dl>
            <p v-else class="drawer-empty">{{ t("operations.toolWorkerDetail.noCapabilities") }}</p>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ detailSectionTitle(selectedWorkerDetail.runtimes.title) }}</h3>
              <span>{{ selectedWorkerDetail.runtimes.total ?? selectedWorkerDetail.runtimes.rows.length }}</span>
            </div>
            <DataTable
              v-if="selectedWorkerDetail.runtimes.rows.length"
              :columns="selectedWorkerDetail.runtimes.columns"
              :rows="selectedWorkerDetail.runtimes.rows"
              section-id="worker-runtimes"
              :page-size="6"
            />
            <p v-else class="drawer-empty">{{ detailEmptyState(selectedWorkerDetail.runtimes.empty_state) }}</p>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ detailSectionTitle(selectedWorkerDetail.provider_limits.title) }}</h3>
              <span>{{ selectedWorkerDetail.provider_limits.total ?? selectedWorkerDetail.provider_limits.rows.length }}</span>
            </div>
            <DataTable
              v-if="selectedWorkerDetail.provider_limits.rows.length"
              :columns="selectedWorkerDetail.provider_limits.columns"
              :rows="selectedWorkerDetail.provider_limits.rows"
              section-id="worker-provider-limits"
              :page-size="5"
            />
            <p v-else class="drawer-empty">{{ detailEmptyState(selectedWorkerDetail.provider_limits.empty_state) }}</p>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ detailSectionTitle(selectedWorkerDetail.events.title) }}</h3>
              <span>{{ selectedWorkerDetail.events.total ?? selectedWorkerDetail.events.rows.length }}</span>
            </div>
            <DataTable
              v-if="selectedWorkerDetail.events.rows.length"
              :columns="selectedWorkerDetail.events.columns"
              :rows="selectedWorkerDetail.events.rows"
              section-id="worker-events"
              :page-size="5"
            />
            <p v-else class="drawer-empty">{{ detailEmptyState(selectedWorkerDetail.events.empty_state) }}</p>
          </section>

          <section class="run-detail-section">
            <div class="drawer-section-heading">
              <h3>{{ t("operations.toolWorkerDetail.rawPayload") }}</h3>
            </div>
            <pre v-if="hasPayload(selectedWorkerDetail.raw_payload)">{{ formatPayload(selectedWorkerDetail.raw_payload) }}</pre>
            <p v-else class="drawer-empty">{{ t("operations.toolWorkerDetail.noPayload") }}</p>
          </section>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="selectedLifecycleEvent" class="event-detail-overlay" @click.self="closeLifecycleEventDetail">
        <aside class="event-detail-drawer" role="dialog" aria-modal="true" :aria-label="t('table.details')">
          <header class="run-detail-header">
            <div>
              <span class="run-detail-kicker">{{ t("table.event") }}</span>
              <h2><StatusDot :tone="selectedLifecycleEvent.tone" />{{ selectedLifecycleEvent.event }}</h2>
              <p>{{ selectedLifecycleEvent.status }} · {{ selectedLifecycleEvent.level }}</p>
            </div>
            <div class="run-detail-actions">
              <RouterLink v-if="selectedLifecycleEvent.sourceRoute" :to="selectedLifecycleEvent.sourceRoute" class="drawer-link">
                <ExternalLink :size="13" /> {{ t("table.source") }}
              </RouterLink>
              <RouterLink v-if="selectedLifecycleEvent.traceRoute" :to="selectedLifecycleEvent.traceRoute" class="drawer-link">
                <ExternalLink :size="13" /> {{ t("table.trace") }}
              </RouterLink>
              <button type="button" class="drawer-close" :aria-label="t('operations.toolDetail.close')" @click="closeLifecycleEventDetail">
                <X :size="15" />
              </button>
            </div>
          </header>

          <section class="event-detail-body event-detail-body--drawer">
            <dl>
              <div>
                <dt>{{ t("table.time") }}</dt>
                <dd>{{ selectedLifecycleEvent.time }}</dd>
              </div>
              <div>
                <dt>{{ t("text.tool") }}</dt>
                <dd :title="selectedLifecycleEvent.toolFull">{{ selectedLifecycleEvent.tool }}</dd>
              </div>
              <div>
                <dt>{{ t("table.runId") }}</dt>
                <dd :title="selectedLifecycleEvent.runId">{{ selectedLifecycleEvent.runId }}</dd>
              </div>
              <div>
                <dt>{{ t("table.source") }}</dt>
                <dd>
                  <RouterLink v-if="selectedLifecycleEvent.sourceRoute" :to="selectedLifecycleEvent.sourceRoute" :title="selectedLifecycleEvent.source">
                    {{ selectedLifecycleEvent.source }}
                  </RouterLink>
                  <span v-else :title="selectedLifecycleEvent.source">{{ selectedLifecycleEvent.source }}</span>
                </dd>
              </div>
              <div>
                <dt>{{ t("table.workerId") }}</dt>
                <dd :title="selectedLifecycleEvent.worker">{{ selectedLifecycleEvent.worker }}</dd>
              </div>
              <div>
                <dt>{{ t("table.assignment") }}</dt>
                <dd :title="selectedLifecycleEvent.assignment">{{ selectedLifecycleEvent.assignment }}</dd>
              </div>
              <div>
                <dt>{{ t("table.trace") }}</dt>
                <dd>
                  <RouterLink v-if="selectedLifecycleEvent.traceRoute" :to="selectedLifecycleEvent.traceRoute" :title="selectedLifecycleEvent.trace">
                    {{ selectedLifecycleEvent.trace }}
                  </RouterLink>
                  <span v-else :title="selectedLifecycleEvent.trace">{{ selectedLifecycleEvent.trace }}</span>
                </dd>
              </div>
            </dl>
            <div class="event-detail-list">
              <span>{{ t("table.details") }}</span>
              <p v-if="!selectedLifecycleEvent.details.length">-</p>
              <ul v-else>
                <li v-for="(detail, detailIndex) in selectedLifecycleEvent.details" :key="`${selectedLifecycleEvent.id}:${detailIndex}`">
                  {{ detail }}
                </li>
              </ul>
            </div>
          </section>
        </aside>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="selectedArtifact" class="event-detail-overlay" @click.self="closeArtifactDetail">
        <aside class="event-detail-drawer artifact-detail-drawer" role="dialog" aria-modal="true" :aria-label="t('operations.toolArtifactDetail.ariaLabel')">
          <header class="run-detail-header">
            <div>
              <span class="run-detail-kicker">{{ t("operations.toolArtifactDetail.title") }}</span>
              <h2>{{ selectedArtifact.name }}</h2>
              <p>{{ selectedArtifact.kind }} · {{ selectedArtifact.mimeType }}</p>
            </div>
            <div class="run-detail-actions">
              <a
                v-if="selectedArtifact.route"
                :href="artifactAssetUrl(selectedArtifact.route) ?? selectedArtifact.route"
                class="drawer-link"
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink :size="13" /> {{ t("operations.toolArtifactDetail.openPreview") }}
              </a>
              <RouterLink v-if="selectedArtifact.traceRoute" :to="selectedArtifact.traceRoute" class="drawer-link">
                <ExternalLink :size="13" /> {{ t("table.trace") }}
              </RouterLink>
              <button type="button" class="drawer-close" :aria-label="t('operations.toolDetail.close')" @click="closeArtifactDetail">
                <X :size="15" />
              </button>
            </div>
          </header>

          <section class="artifact-detail-preview">
            <img v-if="selectedArtifact.imageSrc" :src="selectedArtifact.imageSrc" :alt="selectedArtifact.name" />
            <span v-else><FileText :size="32" /></span>
          </section>

          <section class="event-detail-body event-detail-body--drawer">
            <dl>
              <div>
                <dt>{{ t("table.name") }}</dt>
                <dd :title="selectedArtifact.name">{{ selectedArtifact.name }}</dd>
              </div>
              <div>
                <dt>{{ t("table.kind") }}</dt>
                <dd>{{ selectedArtifact.kind }}</dd>
              </div>
              <div>
                <dt>{{ t("table.mimeType") }}</dt>
                <dd :title="selectedArtifact.mimeType">{{ selectedArtifact.mimeType }}</dd>
              </div>
              <div>
                <dt>{{ t("common.size") }}</dt>
                <dd>{{ selectedArtifact.size }}</dd>
              </div>
              <div>
                <dt>{{ t("table.dimensions") }}</dt>
                <dd>{{ selectedArtifact.dimensions }}</dd>
              </div>
              <div>
                <dt>{{ t("text.tool") }}</dt>
                <dd :title="selectedArtifact.tool">{{ selectedArtifact.tool }}</dd>
              </div>
              <div>
                <dt>{{ t("table.runId") }}</dt>
                <dd :title="selectedArtifact.runId">{{ selectedArtifact.runId }}</dd>
              </div>
              <div>
                <dt>{{ t("table.time") }}</dt>
                <dd>{{ selectedArtifact.time }}</dd>
              </div>
              <div>
                <dt>{{ t("table.trace") }}</dt>
                <dd>
                  <RouterLink v-if="selectedArtifact.traceRoute" :to="selectedArtifact.traceRoute" :title="selectedArtifact.trace">
                    {{ selectedArtifact.trace }}
                  </RouterLink>
                  <span v-else :title="selectedArtifact.trace">{{ selectedArtifact.trace }}</span>
                </dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.tool-console {
  --tool-main-card-min-height: clamp(330px, calc(100dvh - var(--shell-topbar-height) - 430px), 500px);
  --tool-side-card-min-height: 126px;
  --tool-bottom-card-min-height: 104px;
  height: calc(100dvh - var(--shell-topbar-height));
  min-width: 0;
  padding: 7px 10px 10px;
  overflow: auto;
  scrollbar-gutter: stable;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
}

.tool-header,
.tool-header__ops,
.tool-metrics,
.tool-tabs,
.panel-heading,
.table-tools,
.tool-note {
  display: flex;
  align-items: center;
}

.tool-header {
  display: grid;
  grid-template-columns: minmax(190px, 0.5fr) minmax(320px, 0.72fr) minmax(650px, 1.8fr);
  align-items: end;
  gap: 12px;
  min-height: 44px;
  margin-bottom: 6px;
}

h2,
h3,
p,
dl {
  margin: 0;
}

h2 {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 17px;
  line-height: 1.15;
}

h2 span {
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 650;
}

h3 {
  font-size: 12.5px;
}

.tool-title-block {
  min-width: 0;
}

.tool-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-header__controls {
  display: grid;
  grid-template-columns: minmax(140px, 1.2fr) minmax(70px, 0.55fr) minmax(142px, 1fr);
  gap: 8px;
  min-width: 0;
  margin: 0;
}

.tool-header__controls div {
  min-width: 0;
}

.tool-header__controls dt {
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1;
}

.tool-header__controls dd {
  display: flex;
  align-items: center;
  min-height: 25px;
  margin: 4px 0 0;
  padding: 0 10px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel-soft) 86%, transparent);
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
  color: var(--text-muted);
  font-size: 10.5px;
}

.tool-header__ops :deep(.ui-button--sm) {
  min-height: 28px;
  padding: 0 8px;
  gap: 5px;
  border-radius: var(--radius-1);
  font-size: 10.5px;
}

.tool-header__ops span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tool-header__ops strong {
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
  border-color: color-mix(in srgb, var(--color-warning) 64%, var(--border-subtle)) !important;
  color: var(--color-warning) !important;
}

.tool-alert {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 30px;
  margin-bottom: 8px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 42%, var(--border-subtle));
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 88%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
}

.tool-alert span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 42%, var(--border-subtle));
}

.tool-runtime-bar,
.tool-dashboard-grid,
.tool-dashboard-main,
.tool-split-tables,
.tool-runtime-info,
.tool-runtime-actions,
.tool-donut-body,
.latency-summary,
.provider-health-list li,
.failure-list li,
.latency-bars li {
  display: grid;
}

.tool-runtime-bar {
  grid-template-columns: minmax(190px, 0.72fr) minmax(360px, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 54px;
  margin-bottom: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
}

.tool-runtime-health {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.tool-runtime-health strong {
  color: var(--color-success);
  font-size: 18px;
  line-height: 1;
}

.tool-runtime-health--warning strong {
  color: var(--color-warning);
}

.tool-runtime-health--danger strong {
  color: var(--color-danger);
}

.tool-runtime-health span {
  min-width: 0;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-runtime-info {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  align-items: center;
}

.tool-runtime-info div {
  min-width: 0;
  padding-left: 10px;
  border-left: 1px solid var(--border-subtle);
}

.tool-runtime-info dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.tool-runtime-info dd {
  margin: 3px 0 0;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 780;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-runtime-info__item--warning dd {
  color: var(--color-warning);
}

.tool-runtime-info__item--success dd {
  color: var(--color-success);
}

.tool-runtime-actions {
  grid-auto-flow: column;
  gap: 8px;
  justify-content: end;
}

.tool-metrics {
  display: grid;
  grid-template-columns: repeat(7, minmax(118px, 1fr));
  gap: 7px;
}

.metric,
.tool-runs-panel,
.tool-status-strip > article,
.tool-side-stack > article,
.tool-bottom-grid > article {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.metric {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr) 18px;
  gap: 5px;
  align-items: stretch;
  height: 72px;
  min-height: 0;
  padding: 9px 10px 7px;
  overflow: hidden;
}

.metric-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-blue) 22%, transparent);
  color: var(--color-blue);
}

.metric--success .metric-icon {
  background: color-mix(in srgb, var(--color-success) 20%, transparent);
  color: var(--color-success);
}

.metric--warning .metric-icon {
  background: color-mix(in srgb, var(--color-warning) 22%, transparent);
  color: var(--color-warning);
}

.metric--danger .metric-icon {
  background: color-mix(in srgb, var(--color-danger) 20%, transparent);
  color: var(--color-danger);
}

.metric-copy {
  min-width: 0;
}

.metric-copy em {
  display: block;
  color: var(--color-blue);
  font-size: 10.5px;
  font-weight: 760;
  font-style: normal;
}

.metric--success .metric-copy em {
  color: var(--color-success);
}

.metric--warning .metric-copy em {
  color: var(--color-warning);
}

.metric--danger .metric-copy em {
  color: var(--color-danger);
}

.metric-copy strong {
  display: block;
  margin-top: 3px;
  font-size: 19px;
  line-height: 1;
}

.metric-copy small {
  display: -webkit-box;
  margin-top: 1px;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.12;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.metric-spark {
  display: block;
  align-self: end;
  height: 18px;
  overflow: hidden;
  border-bottom: 1px solid color-mix(in srgb, var(--color-blue) 40%, transparent);
  background:
    linear-gradient(180deg, transparent 0 36%, color-mix(in srgb, var(--color-blue) 10%, transparent) 36% 100%),
    repeating-linear-gradient(90deg, transparent 0 12px, color-mix(in srgb, var(--border-subtle) 40%, transparent) 12px 13px);
}

.metric-spark span {
  display: block;
  height: 100%;
  clip-path: polygon(0 72%, 16% 68%, 28% 62%, 38% 44%, 48% 54%, 58% 30%, 70% 48%, 82% 34%, 100% 42%, 100% 100%, 0 100%);
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-blue) 52%, transparent), transparent 86%);
}

.metric--success .metric-spark {
  border-bottom-color: color-mix(in srgb, var(--color-success) 42%, transparent);
}

.metric--success .metric-spark span {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-success) 52%, transparent), transparent 86%);
}

.metric--warning .metric-spark {
  border-bottom-color: color-mix(in srgb, var(--color-warning) 42%, transparent);
}

.metric--warning .metric-spark span {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-warning) 52%, transparent), transparent 86%);
}

.metric--danger .metric-spark {
  border-bottom-color: color-mix(in srgb, var(--color-danger) 42%, transparent);
}

.metric--danger .metric-spark span {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-danger) 52%, transparent), transparent 86%);
}

.metric--success .metric-copy strong {
  color: var(--color-success);
}

.metric--warning .metric-copy strong {
  color: var(--color-warning);
}

.metric--danger .metric-copy strong {
  color: var(--color-danger);
}

.tool-dashboard-grid {
  grid-template-columns: minmax(0, 1fr) minmax(276px, 304px);
  gap: 8px;
  align-items: stretch;
  margin-top: 7px;
}

.tool-dashboard-main {
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  min-width: 0;
}

.tool-live-grid {
  display: grid;
  grid-template-columns: minmax(420px, 1.32fr) minmax(300px, 0.98fr) minmax(230px, 0.76fr);
  gap: 8px;
  min-width: 0;
  min-height: 0;
}

.tool-dashboard-grid .tool-runs-panel,
.tool-side-stack > article {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.tool-runs-panel--primary {
  min-height: 262px;
}

.tool-runs-panel--secondary {
  min-height: 146px;
}

.tool-workers-table {
  min-height: 164px;
}

.tool-bottom-split {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
  gap: 8px;
  min-height: 0;
  overflow: hidden;
}

.tool-artifacts-panel {
  min-height: 0;
}

.tool-live-card {
  min-height: 0;
}

.tool-records-panel {
  min-height: 0;
}

.panel-heading--records {
  align-items: center;
}

.tool-filter-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel-soft) 88%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 720;
}

.tool-record-toolbar {
  display: grid;
  grid-template-columns: minmax(118px, 0.75fr) minmax(132px, 0.8fr) minmax(118px, 0.75fr) minmax(180px, 1.35fr) minmax(132px, 0.8fr);
  gap: 7px;
  flex: 0 0 auto;
  margin-bottom: 6px;
}

.tool-record-toolbar label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 26px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel-soft) 86%, transparent);
}

.tool-record-toolbar span {
  color: var(--text-muted);
  font-size: 10.5px;
  white-space: nowrap;
}

.tool-record-toolbar select,
.tool-record-toolbar input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
}

.tool-record-toolbar__search {
  grid-template-columns: auto minmax(0, 1fr);
}

.tool-split-tables {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.tool-side-stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
}

.tool-side-stack > article {
  min-width: 0;
  min-height: 112px;
  padding: 8px;
}

.tool-donut-panel {
  min-height: 150px;
}

.tool-donut-body {
  grid-template-columns: 106px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.tool-donut {
  position: relative;
  display: grid;
  place-items: center;
  align-content: center;
  width: 96px;
  height: 96px;
  border-radius: 999px;
  text-align: center;
}

.tool-donut::after {
  content: "";
  position: absolute;
  inset: 18px;
  border-radius: inherit;
  background: color-mix(in srgb, var(--surface-panel) 96%, transparent);
}

.tool-donut strong,
.tool-donut span {
  position: relative;
  z-index: 1;
}

.tool-donut strong {
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1;
}

.tool-donut span {
  color: var(--text-muted);
  font-size: 10px;
}

.tool-donut-body ul,
.provider-health-list,
.failure-list,
.latency-bars {
  display: grid;
  gap: 5px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.tool-donut-body li,
.provider-health-list li,
.failure-list li {
  min-width: 0;
  color: var(--text-secondary);
  font-size: 10.5px;
}

.tool-donut-body li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.tool-donut-body li span,
.provider-health-list li span,
.failure-list li span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-donut-body li em,
.provider-health-list li em,
.failure-list li em {
  color: var(--text-muted);
  font-style: normal;
  white-space: nowrap;
}

.latency-summary {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 5px;
  margin-bottom: 6px;
}

.latency-summary div {
  min-width: 0;
  padding: 5px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.latency-summary dt {
  color: var(--text-muted);
  font-size: 10px;
}

.latency-summary dd {
  margin: 2px 0 0;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 800;
}

.latency-bars li {
  grid-template-columns: minmax(0, 1fr) 42px;
  gap: 8px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 10.5px;
}

.latency-bars li span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.latency-bars li strong {
  color: var(--text-primary);
  font-size: 10.5px;
  text-align: right;
}

.latency-bars li i {
  grid-column: 1 / -1;
  display: block;
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-raised) 80%, transparent);
}

.latency-bars li em {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-blue);
}

.failure-list li,
.provider-health-list li {
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.provider-health-list li {
  grid-template-columns: minmax(0, 1fr) auto 48px;
}

.failure-list strong,
.provider-health-list strong {
  color: var(--text-primary);
  font-size: 10.5px;
  white-space: nowrap;
}

.failure-list strong em {
  color: var(--text-muted);
  font-style: normal;
}

.provider-state {
  padding: 2px 6px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel-soft) 84%, transparent);
}

.provider-state--success {
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.provider-state--warning {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
}

.provider-state--danger {
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
}

.panel-heading--table {
  align-items: flex-start;
}

.panel-heading--table > div:first-child {
  min-width: 0;
}

.table-tools--compact {
  margin-top: 0;
  padding-bottom: 0;
}

.tool-runs-panel--primary :deep(.data-table--tool-runs) {
  --data-table-min-width: 860px;
}

.tool-runs-panel--primary :deep(.data-table--workers) {
  --data-table-min-width: 900px;
}

.tool-live-card :deep(.data-table) {
  --data-table-min-width: 100%;
}

.tool-live-card :deep(th),
.tool-live-card :deep(td) {
  padding-inline: 5px;
  font-size: 10.5px;
}

.tool-live-card :deep(.column-tool) {
  width: 42%;
}

.tool-live-card :deep(.column-source),
.tool-live-card :deep(.column-worker) {
  width: 86px;
}

.tool-live-card :deep(.column-duration),
.tool-live-card :deep(.column-wait-time),
.tool-live-card :deep(.column-priority),
.tool-live-card :deep(.column-progress) {
  width: 58px;
}

.tool-live-card :deep(.column-external-service) {
  width: 88px;
}

.tool-live-card :deep(.column-actions) {
  width: 54px;
}

.tool-records-panel :deep(.data-table--tool-run-records) {
  --data-table-min-width: 100%;
}

.tool-records-panel :deep(th),
.tool-records-panel :deep(td) {
  height: 24px;
  min-height: 24px;
  padding-top: 3px;
  padding-bottom: 3px;
}

.tool-records-panel :deep(.column-time) {
  width: 82px;
}

.tool-records-panel :deep(.column-tool) {
  width: 170px;
}

.tool-records-panel :deep(.column-run-id),
.tool-records-panel :deep(.column-source),
.tool-records-panel :deep(.column-worker) {
  width: 112px;
}

.tool-records-panel :deep(.column-mode),
.tool-records-panel :deep(.column-duration) {
  width: 70px;
}

.tool-records-panel :deep(.column-status) {
  width: 82px;
}

.tool-records-panel :deep(.column-actions) {
  width: 66px;
}

.tool-status-strip {
  display: grid;
  grid-template-columns: minmax(320px, 1.2fr) minmax(220px, 0.66fr) minmax(260px, 0.86fr);
  gap: 6px;
  align-items: start;
  margin-top: 6px;
}

.tool-status-strip > article {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 78px;
  padding: 7px;
}

.risk-status-panel .stat-tile {
  min-height: 46px;
  padding: 6px 7px;
}

.risk-status-panel .stat-tile dd {
  margin-top: 2px;
  font-size: 15px;
}

.stat-grid--status {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.inline-status-panel dl {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.inline-status-panel .panel-empty {
  min-height: 40px;
}

.artifacts-status-panel .artifact-stat-strip {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.artifacts-status-panel .stat-tile {
  min-height: 46px;
  padding: 6px 7px;
}

.artifacts-status-panel .stat-tile dd {
  margin-top: 2px;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-tabs {
  gap: 14px;
  min-height: 29px;
  margin-top: 6px;
  border-bottom: 1px solid var(--border-subtle);
  overflow-x: auto;
  scrollbar-width: thin;
}

.tool-tabs button {
  flex: 0 0 auto;
  display: inline-flex;
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
  white-space: nowrap;
}

.tool-tabs button.active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.tool-tabs button span {
  color: var(--text-muted);
  font-size: 10px;
}

.tool-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(252px, 296px);
  gap: 6px;
  margin-top: 0;
}

.tool-side-stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
}

.tool-runs-panel,
.tool-status-strip > article,
.tool-side-stack > article,
.tool-bottom-grid > article {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 7px;
}

.tool-main-grid > .tool-runs-panel {
  min-height: var(--tool-main-card-min-height);
}

.tool-main-grid .tool-side-stack > article {
  min-height: var(--tool-side-card-min-height);
}

.tool-bottom-grid > article {
  min-height: var(--tool-bottom-card-min-height);
}

.panel-heading {
  flex: 0 0 auto;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.panel-heading a,
.panel-heading span {
  color: var(--color-blue);
  font-size: 11px;
  text-decoration: none;
}

.panel-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  align-items: center;
  white-space: nowrap;
}

.panel-heading h3 span {
  color: var(--text-muted);
  font-weight: 500;
}

.tool-runs-panel > .panel-heading h3 {
  white-space: nowrap;
}

.table-tools {
  gap: 6px;
  flex-wrap: nowrap;
  align-items: flex-start;
  min-width: 0;
  margin-top: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.table-tools label,
.table-tools button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 22px;
  padding: 0 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 10.5px;
}

.table-tools label {
  cursor: default;
}

.table-tools label span {
  color: var(--text-muted);
}

.table-tools select,
.table-tools input {
  min-width: 72px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
}

.table-tools input {
  width: 96px;
}

.table-tools input[type="search"] {
  width: 126px;
}

.run-actions-bar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  margin-bottom: 6px;
  padding: 4px 6px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 34%, var(--border-subtle));
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel-soft) 82%, transparent);
  overflow-x: auto;
  scrollbar-width: thin;
}

.run-actions-bar > span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.tool-runs-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.tool-runs-panel footer.tool-table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.tool-table-footer__copy {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.tool-run-pager {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.tool-run-pager button {
  display: grid;
  place-items: center;
  width: 24px;
  height: 22px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
}

.tool-run-pager button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.tool-runs-panel :deep(.data-table--tool-runs th),
.tool-runs-panel :deep(.data-table--tool-runs td) {
  padding-top: 4px;
  padding-bottom: 4px;
}

.tool-runs-panel :deep(.data-table--tool-runs td) {
  font-size: 11px;
}

.tool-runs-panel :deep(.data-table--tool-lifecycle-events) {
  --data-table-min-width: 760px;
}

.tool-runs-panel :deep(.data-table--tool-lifecycle-events th),
.tool-runs-panel :deep(.data-table--tool-lifecycle-events td) {
  padding-top: 6px;
  padding-bottom: 6px;
}

.tool-runs-panel :deep(.data-table--tool-lifecycle-events .column-time) {
  width: 86px;
}

.tool-runs-panel :deep(.data-table--tool-lifecycle-events .column-event) {
  width: 160px;
}

.tool-runs-panel :deep(.data-table--tool-lifecycle-events .column-status) {
  width: 86px;
}

.tool-runs-panel :deep(.data-table--tool-lifecycle-events .column-tool) {
  width: 142px;
}

.tool-runs-panel :deep(.data-table--tool-lifecycle-events .column-run-id),
.tool-runs-panel :deep(.data-table--tool-lifecycle-events .column-source),
.tool-runs-panel :deep(.data-table--tool-lifecycle-events .column-worker-id) {
  width: 112px;
}

.event-detail-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
  scrollbar-gutter: stable;
}

.event-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 82;
  display: flex;
  justify-content: flex-end;
  background: color-mix(in srgb, #000 22%, transparent);
}

.event-detail-drawer {
  width: min(430px, calc(100vw - 184px));
  height: 100dvh;
  overflow: auto;
  padding: 14px;
  border-left: 1px solid var(--border-subtle);
  background: var(--surface-page);
  box-shadow: -18px 0 40px color-mix(in srgb, #000 24%, transparent);
}

.artifact-detail-drawer {
  width: min(520px, calc(100vw - 184px));
}

.event-detail-drawer .run-detail-header h2,
.worker-detail-drawer .run-detail-header h2 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.event-detail-body--drawer {
  padding-top: 12px;
  overflow: visible;
}

.event-detail-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 30px;
  padding-bottom: 7px;
  border-bottom: 1px solid var(--border-subtle);
}

.event-detail-title span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-detail-title em {
  flex: 0 0 auto;
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
  font-weight: 700;
}

.event-detail-body dl {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}

.event-detail-body dl div {
  min-width: 0;
}

.event-detail-body dt,
.event-detail-list > span {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
}

.event-detail-body dd {
  min-width: 0;
  margin: 2px 0 0;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-detail-body a {
  color: var(--color-blue);
  text-decoration: none;
}

.artifact-detail-preview {
  display: grid;
  place-items: center;
  min-height: 220px;
  max-height: 360px;
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel-soft) 88%, transparent);
  color: var(--text-muted);
}

.artifact-detail-preview img {
  width: 100%;
  height: 100%;
  max-height: 360px;
  object-fit: contain;
}

.event-detail-list {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}

.event-detail-list ul {
  display: grid;
  gap: 5px;
  padding: 0;
  margin: 6px 0 0;
  list-style: none;
}

.event-detail-list li,
.event-detail-list p {
  margin: 0;
  padding: 5px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel-soft) 82%, transparent);
  color: var(--text-secondary);
  font-size: 10.5px;
  line-height: 1.28;
  overflow-wrap: anywhere;
}

.tool-types-panel ul {
  display: grid;
  gap: 7px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.tool-types-panel li {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 48px 44px;
  gap: 8px;
  align-items: center;
  min-height: 20px;
  color: var(--text-secondary);
  font-size: 10.5px;
}

.tool-types-panel li span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.tool-types-panel li strong,
.tool-types-panel li em {
  text-align: right;
}

.tool-types-panel li em {
  color: var(--text-muted);
  font-style: normal;
}

.tool-types-panel li i {
  position: absolute;
  right: 0;
  bottom: -2px;
  height: 2px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--color-blue) 72%, transparent);
}

.auth-panel {
  border-color: color-mix(in srgb, var(--color-danger) 42%, var(--border-subtle));
}

.stat-grid {
  display: grid;
  gap: 6px;
  margin: 0;
}

.stat-grid--compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.stat-grid--wide {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.stat-tile {
  min-width: 0;
  min-height: 68px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.stat-tile dt {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-tile dd {
  margin: 5px 0 2px;
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 800;
  line-height: 1;
}

.stat-tile span {
  display: -webkit-box;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.15;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
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

.stat-tile--info dd {
  color: var(--color-blue);
}

.worker-body {
  display: grid;
  grid-template-columns: 124px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.worker-donut {
  display: grid;
  grid-template-rows: auto auto;
  align-content: center;
  justify-items: center;
  gap: 2px;
  position: relative;
  place-items: center;
  width: 116px;
  height: 116px;
  border-radius: 999px;
  text-align: center;
  background: var(--surface-raised);
}

.worker-donut::before {
  content: "";
  position: absolute;
}

.worker-donut strong,
.worker-donut span {
  z-index: 1;
}

.worker-donut strong {
  color: var(--chart-on-solid);
  font-size: 25px;
  font-weight: 800;
  line-height: 1;
  text-shadow: 0 1px 2px var(--chart-on-solid-shadow);
}

.worker-donut span {
  max-width: 82px;
  color: var(--chart-on-solid-muted);
  font-size: 10.5px;
  line-height: 1.08;
  text-shadow: 0 1px 2px var(--chart-on-solid-shadow);
}

.worker-panel dl,
.inline-risk-panel dl {
  display: grid;
  gap: 5px;
}

.worker-panel dl div,
.inline-risk-panel dl div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 10.5px;
}

.worker-panel dt {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.worker-panel dd,
.inline-risk-panel dd {
  margin: 0;
  font-weight: 800;
}

.worker-panel dd span,
.inline-risk-panel dd span {
  color: var(--text-muted);
  font-weight: 500;
}

.worker-panel small {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: auto;
  padding-top: 6px;
  color: var(--text-muted);
  font-size: 10.5px;
}

.inline-risk-panel p {
  margin-bottom: 10px;
  color: var(--text-muted);
  font-size: 12px;
}

.inline-risk-panel strong {
  display: block;
  margin-top: 16px;
  color: var(--color-blue);
  font-size: 12px;
}

.inline-risk-panel .danger {
  color: var(--color-danger);
}

.tool-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 6px;
  margin-top: 6px;
}

.artifact-preview-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 7px;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  justify-content: start;
  min-width: 0;
}

.artifact-preview-card {
  display: grid;
  grid-template-rows: minmax(78px, 0.92fr) minmax(58px, 0.68fr);
  min-width: 0;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  text-align: left;
  text-decoration: none;
}

.artifact-preview-card:hover,
.artifact-preview-card:focus-visible {
  border-color: color-mix(in srgb, var(--color-blue) 42%, var(--border-subtle));
  outline: none;
}

.artifact-preview-media {
  position: relative;
  display: grid;
  min-width: 0;
  min-height: 0;
  place-items: center;
  overflow: hidden;
  background: color-mix(in srgb, var(--surface-raised) 82%, transparent);
  color: var(--text-muted);
}

.artifact-preview-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.artifact-preview-media em {
  position: absolute;
  top: 6px;
  right: 6px;
  max-width: calc(100% - 12px);
  padding: 2px 6px;
  overflow: hidden;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 82%, transparent);
  color: #fff;
  font-size: 9px;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  text-transform: capitalize;
  white-space: nowrap;
}

.artifact-preview-copy {
  display: grid;
  align-content: start;
  gap: 3px;
  min-width: 0;
  padding: 7px;
}

.artifact-preview-copy strong,
.artifact-preview-copy em,
.artifact-preview-copy small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-preview-copy strong {
  color: var(--text-primary);
  font-size: 11px;
}

.artifact-preview-copy em {
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
}

.artifact-preview-copy small {
  color: var(--text-muted);
  font-size: 10px;
}

.tool-artifacts-panel--wide {
  border-color: color-mix(in srgb, var(--color-accent) 54%, var(--border-subtle));
}

.artifact-stat-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin: 0;
}

.artifact-stat-strip .stat-tile {
  min-height: 56px;
}

.tool-console :deep(.data-table th),
.tool-console :deep(.data-table td) {
  padding-top: 4px;
  padding-bottom: 4px;
  font-size: 11px;
  line-height: 1.2;
}

.tool-console :deep(.data-table__pager) {
  min-height: 28px;
  padding-top: 4px;
}

.panel-empty {
  flex: 1 1 auto;
  display: grid;
  min-height: 44px;
  place-items: center;
  color: var(--text-muted);
  font-size: 11px;
  text-align: center;
}

.panel-empty--compact {
  min-height: 52px;
}

.state-empty {
  flex: 1 1 auto;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 4px;
  min-height: 52px;
  padding: 8px;
  color: var(--text-muted);
  text-align: center;
}

.state-empty--compact {
  min-height: 68px;
}

.state-empty > span {
  display: none;
}

.state-empty strong {
  color: var(--text-secondary);
  font-size: 11px;
}

.state-empty p {
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.25;
}

.tool-note {
  gap: 8px;
  margin-top: 12px;
  color: var(--text-muted);
  font-size: 11px;
}

.run-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  justify-content: flex-end;
  background: color-mix(in srgb, #000 34%, transparent);
}

.run-detail-drawer {
  width: min(760px, calc(100vw - 184px));
  height: 100dvh;
  overflow: auto;
  padding: 14px;
  border-left: 1px solid var(--border-subtle);
  background: var(--surface-page);
  box-shadow: -18px 0 40px color-mix(in srgb, #000 28%, transparent);
}

.run-detail-header {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-page);
}

.run-detail-header h2 {
  margin-top: 2px;
  font-size: 16px;
}

.run-detail-header p,
.run-detail-kicker {
  color: var(--text-muted);
  font-size: 11px;
}

.run-detail-actions {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.drawer-link,
.drawer-close {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
  text-decoration: none;
}

.drawer-close {
  width: 28px;
  justify-content: center;
  padding: 0;
}

.run-detail-summary {
  padding: 12px 0;
}

.run-detail-summary dl {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.summary-item,
.run-detail-section {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.summary-item {
  padding: 8px;
}

.summary-item dt,
.context-list dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.summary-item dd,
.context-list dd {
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 11.5px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-item--success dd {
  color: var(--color-success);
}

.summary-item--warning dd {
  color: var(--color-warning);
}

.summary-item--danger dd {
  color: var(--color-danger);
}

.run-detail-section {
  margin-bottom: 10px;
  padding: 10px;
}

.run-detail-payloads {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  border: 0;
  padding: 0;
  background: transparent;
}

.run-detail-payloads article {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.drawer-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.drawer-section-heading span {
  color: var(--text-muted);
  font-size: 10.5px;
}

.run-detail-section pre,
.run-detail-payloads pre {
  max-height: 220px;
  margin: 0;
  overflow: auto;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
  white-space: pre-wrap;
  word-break: break-word;
}

.context-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.context-list div {
  min-width: 0;
}

.error-facts-list {
  margin-bottom: 8px;
}

.drawer-empty,
.drawer-error {
  display: grid;
  min-height: 48px;
  margin: 0;
  place-items: center;
  color: var(--text-muted);
  font-size: 11px;
}

.drawer-error {
  color: var(--color-danger);
  text-align: center;
}

.drawer-error-pre {
  color: var(--color-danger);
}

.run-detail-drawer :deep(.data-table) {
  max-height: 230px;
}

.motion-spin {
  animation: tool-spin 0.9s linear infinite;
}

@keyframes tool-spin {
  to {
  transform: rotate(360deg);
  }
}

@media (min-width: 1241px) {
  .tool-console {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    overscroll-behavior: contain;
  }

  .tool-header,
  .tool-alert,
  .tool-metrics {
    flex: 0 0 auto;
  }

  .tool-dashboard-grid {
    flex: 1 1 auto;
    grid-template-rows: minmax(0, 1fr);
    align-items: stretch;
    min-height: 0;
    overflow: hidden;
  }

  .tool-dashboard-main {
    grid-template-rows:
      minmax(150px, 0.9fr)
      minmax(236px, 1.42fr)
      minmax(170px, 0.88fr);
    height: 100%;
    min-height: 0;
    overflow: hidden;
  }

  .tool-live-grid {
    min-height: 0;
    overflow: hidden;
  }

  .tool-split-tables,
  .tool-bottom-split,
  .tool-live-grid,
  .tool-side-stack {
    min-height: 0;
    overflow: hidden;
  }

  .tool-side-stack {
    grid-template-rows:
      minmax(0, 1.25fr)
      minmax(0, 1fr)
      minmax(0, 0.8fr)
      minmax(0, 0.9fr);
    height: 100%;
  }

  .tool-runs-panel,
  .tool-side-stack > article {
    min-height: 0;
    overflow: hidden;
  }

  .tool-runs-panel--primary,
  .tool-runs-panel--secondary,
  .tool-live-card,
  .tool-records-panel,
  .tool-workers-table,
  .tool-artifacts-panel,
  .tool-donut-panel {
    min-height: 0;
  }

  .tool-runs-panel :deep(.data-table) {
    overflow: auto;
  }
}

@media (max-width: 1240px) {
  .tool-runtime-bar,
  .tool-dashboard-grid,
  .tool-status-strip,
  .tool-main-grid,
  .tool-bottom-grid,
  .tool-bottom-split,
  .tool-live-grid,
  .tool-record-toolbar,
  .tool-split-tables {
    grid-template-columns: minmax(0, 1fr);
  }

  .tool-header {
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }

  .tool-header__controls {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .tool-runtime-actions {
    justify-content: start;
  }

  .artifact-preview-grid {
    grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  }

  .artifact-stat-strip,
  .stat-grid--status {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .run-detail-drawer {
    width: min(760px, calc(100vw - 24px));
  }

  .run-detail-summary dl,
  .run-detail-payloads,
  .context-list {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .tool-metrics {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: thin;
    scroll-snap-type: x proximity;
  }

  .metric {
    flex: 0 0 168px;
    scroll-snap-align: start;
  }
}

@media (max-width: 760px) {
  .tool-console {
    overflow-x: hidden;
    padding: 10px 14px 14px;
  }

  .tool-header {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    align-items: flex-start;
  }

  .tool-header > div:first-child {
    min-width: 0;
  }

  h2 {
    display: block;
    font-size: 17px;
    line-height: 1.2;
  }

  h2 span {
    display: block;
    margin-top: 3px;
    line-height: 1.3;
  }

  .tool-header__ops {
    justify-content: flex-start;
  }

  .tool-runtime-bar {
    padding: 9px;
  }

  .tool-runtime-info {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .tool-status-strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .tool-status-strip > article {
    flex: 0 0 286px;
  }

  .artifacts-status-panel .artifact-stat-strip {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .table-tools,
  .run-actions-bar {
    overflow-x: auto;
    flex-wrap: nowrap;
    justify-content: flex-start;
    scrollbar-width: thin;
  }

  .table-tools button,
  .run-actions-bar > * {
    flex: 0 0 auto;
  }

  .tool-runs-panel footer {
    flex-direction: column;
    gap: 3px;
  }

  .event-detail-drawer {
    width: min(430px, calc(100vw - 24px));
  }

  .artifact-detail-drawer {
    width: min(520px, calc(100vw - 24px));
  }

  .worker-body {
    grid-template-columns: 112px minmax(0, 1fr);
  }

  .tool-donut-body {
    grid-template-columns: 104px minmax(0, 1fr);
  }

  .tool-donut {
    width: 98px;
    height: 98px;
  }

  .worker-donut {
    width: 104px;
    height: 104px;
  }

  .inline-status-panel dl,
  .stat-grid--wide {
    grid-template-columns: minmax(0, 1fr);
  }

  .stat-grid--status,
  .artifact-stat-strip,
  .artifact-preview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .artifact-preview-card {
    max-width: none;
  }
}
</style>
