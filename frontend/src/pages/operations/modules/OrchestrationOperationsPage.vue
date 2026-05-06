<script setup lang="ts">
import { Activity, Archive, CircleX, ExternalLink, HeartPulse, Inbox, Network, RefreshCcw, ShieldCheck, UserRoundCheck, Users, X } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { formatLocalTime, formatRawKeyLabel } from "@/shared/i18n/formatters";
import { useI18n } from "@/shared/i18n";
import type {
  OperationsOrchestrationReadModel,
  OperationsTab,
  UiChartSection,
  UiKeyValueSection,
  UiMetricCard,
  UiRuntimeAction,
  UiTableCellValue,
  UiTableColumn,
  UiTableRow,
  UiTableSection,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  cancelOrchestrationRun,
  loadOrchestrationOperations,
  resumeOrchestrationRun,
} from "../api";

type SegmentTone = "neutral" | "info" | "success" | "warning" | "danger";
type DetailSectionId = "run_queue" | "ingress_queue" | "lane_locks" | "executor_overview" | "recent_failures" | "ops_event_log";
type SelectedDetail = {
  sectionId: DetailSectionId;
  title: string;
  row: UiTableRow;
};

const toneColors: Record<SegmentTone, string> = {
  neutral: "var(--color-gray)",
  info: "var(--color-blue)",
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  danger: "var(--color-danger)",
};

const metricIcons: Record<string, unknown> = {
  health: HeartPulse,
  ingress: Inbox,
  ingress_rate: Inbox,
  active: Activity,
  run_queue: Archive,
  backpressure: Users,
  approval_waiting: UserRoundCheck,
  failed: CircleX,
  latency: HeartPulse,
  observed_facts: Network,
  executor_capacity: Network,
};

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const emptyMetricDeltas: Record<string, string> = {
  ingress: "ingress requests",
  ingress_rate: "requests/sec",
  active: "0 waiting",
  run_queue: "0 waiting",
  backpressure: "Waiting runs",
  approval_waiting: "Monitoring only",
  failed: "0 retained",
  latency: "avg runtime",
  observed_facts: "0 runs / 0 executors",
};
const fallbackTabs: OperationsTab[] = [
  { id: "overview", label: "Overview" },
  { id: "runs", label: "Runs", count: 0 },
  { id: "lane_locks", label: "Lane Locks", count: 0 },
  { id: "executors", label: "Executors", count: 0 },
  { id: "failures", label: "Failures", count: 0 },
  { id: "events", label: "Events", count: 0 },
];
const page = ref<OperationsOrchestrationReadModel>(emptyOrchestrationPage());
const loading = ref(false);
const loadError = ref<string | null>(null);
const actionBusy = ref<string | null>(null);
const actionNotice = ref<string | null>(null);
const refreshTimer = ref<number | null>(null);
const selectedDetail = ref<SelectedDetail | null>(null);

const activeTab = computed(() => {
  const tab = typeof route.query.tab === "string" ? route.query.tab : page.value.active_tab;
  return page.value.tabs.some((item) => item.id === tab) ? tab : page.value.active_tab;
});

const lastUpdatedLabel = computed(() => {
  return page.value.updated_at ? formatLocalTime(page.value.updated_at) : "-";
});

const roleLabel = computed(() => {
  const role = page.value.role;
  if (role.can_operate && role.label.toLowerCase() === "admin") {
    return t("common.roleAdminOperable");
  }
  return role.can_operate ? `${role.label} · ${t("common.available")}` : role.label;
});

const metricsById = computed(() => new Map(page.value.metrics.map((metric) => [metric.id, metric])));

const runtimeHealthTone = computed<SegmentTone>(() => {
  if (page.value.health === "healthy") return "success";
  if (page.value.health === "warning") return "warning";
  if (page.value.health === "error") return "danger";
  return "neutral";
});

const runtimeHealthLabel = computed(() => {
  if (page.value.health === "healthy") return t("operations.health.healthy");
  if (page.value.health === "warning") return t("operations.health.warning");
  if (page.value.health === "error") return t("operations.health.error");
  return page.value.health || "-";
});

const runtimeHealthSummary = computed(() => metricDelta("health", metricCard("health")?.delta ?? ""));

const runtimeModeLabel = computed(() => t("operations.orchestration.dashboard.productionEnvironment"));

const eventLoopMode = computed(() => {
  const eventLoop = page.value.scheduler_status.items.find((item) => item.label === "Event Loop");
  return eventLoop ? schedulerItemValue(eventLoop.value) : "-";
});

const concurrencyLimitLabel = computed(() => {
  const globalLimit = page.value.policy_limits.items.find((item) => item.label === "Global Run Concurrency");
  if (globalLimit) return policyItemValue(globalLimit.value);
  const workerCapacity = page.value.policy_limits.items.find((item) => item.label === "Worker Capacity (Online / Total)");
  return workerCapacity ? policyItemValue(workerCapacity.value).split("/")[0]?.trim() || "-" : "-";
});

const queuePolicyLabel = computed(() => {
  const firstRun = page.value.run_queue.rows[0] ?? page.value.ingress_queue.rows[0];
  const policy = firstRun ? rowCellText(firstRun, "policy") : "-";
  if (policy && policy !== "-") return policyText(policy);
  return t("operations.orchestration.policy.fifo");
});

const queueAgeP95Label = computed(() => {
  const item = page.value.scheduler_status.items.find((entry) => entry.label === "Queue Age (p95)");
  return item ? schedulerItemValue(item.value) : "-";
});

const dashboardMetrics = computed(() => [
  {
    id: "ingress",
    icon: Inbox,
    label: t("operations.orchestration.dashboard.ingress"),
    value: metricCard("ingress_rate")?.value ?? "0/s",
    suffix: t("operations.orchestration.dashboard.requestsPerSecond"),
    tone: metricCard("ingress_rate")?.tone ?? metricCard("ingress")?.tone ?? "neutral",
  },
  {
    id: "running",
    icon: Activity,
    label: t("operations.orchestration.dashboard.running"),
    value: metricCard("active")?.value ?? "0",
    suffix: t("operations.orchestration.dashboard.tasks"),
    tone: metricCard("active")?.tone ?? "info",
  },
  {
    id: "queued",
    icon: Archive,
    label: t("operations.orchestration.dashboard.queued"),
    value: metricCard("run_queue")?.value ?? "0",
    suffix: t("operations.orchestration.dashboard.tasks"),
    tone: metricCard("run_queue")?.tone ?? "success",
  },
  {
    id: "blocked",
    icon: UserRoundCheck,
    label: t("operations.orchestration.dashboard.blocked"),
    value: metricCard("backpressure")?.value ?? "0",
    suffix: t("operations.orchestration.dashboard.tasks"),
    tone: metricCard("backpressure")?.tone ?? "success",
  },
  {
    id: "failed",
    icon: CircleX,
    label: t("operations.orchestration.dashboard.failed"),
    value: metricCard("failed")?.value ?? "0",
    suffix: "24h",
    tone: metricCard("failed")?.tone ?? "neutral",
  },
  {
    id: "latency",
    icon: HeartPulse,
    label: t("operations.orchestration.dashboard.latency"),
    value: metricCard("latency")?.value ?? queueAgeP95Label.value,
    suffix: t("operations.orchestration.dashboard.avgRuntime"),
    tone: metricCard("latency")?.tone ?? (page.value.run_queue.rows.length ? "warning" : "info"),
  },
]);

const runningTasksTable = computed<UiTableSection>(() => {
  const rows: UiTableRow[] = [];
  for (const row of page.value.lane_locks.rows) {
    rows.push({
      id: row.id,
      cells: {
        ...row.cells,
        source_section: "lane_locks",
        run_id: rawCellText(row, "holder_run_id"),
        type: rawCellText(row, "type"),
        worker_id: rawCellText(row, "worker_id"),
        duration: rawCellText(row, "duration"),
        status: row.status ?? rawCellText(row, "stage"),
        progress: rawCellText(row, "progress"),
        actions: rawCellText(row, "actions") !== "-" ? rawCellText(row, "actions") : "Open / Trace",
        route: rawCellText(row, "route"),
        trace_route: rawCellText(row, "trace_route"),
      },
      status: row.status,
      tone: row.tone ?? "info",
    });
  }
  const knownRunIds = new Set(rows.map((row) => rawCellText(row, "run_id")));
  for (const row of page.value.executor_overview.rows) {
    const runId = rawCellText(row, "current_run");
    if (!runId || runId === "-" || knownRunIds.has(runId)) continue;
    rows.push({
      id: `${row.id}:${runId}`,
      cells: {
        ...row.cells,
        source_section: "executor_overview",
        run_id: runId,
        type: "executor",
        worker_id: rawCellText(row, "worker_id"),
        duration: "-",
        status: rawCellText(row, "status"),
        progress: rawCellText(row, "load"),
        actions: "Open",
        route: rawCellText(row, "route"),
      },
      status: rawCellText(row, "status"),
      tone: row.tone ?? "info",
    });
  }
  return {
    id: "running_tasks",
    title: "Running Tasks",
    columns: [
      { key: "run_id", label: "Run ID" },
      { key: "type", label: "Type" },
      { key: "worker_id", label: "Worker ID" },
      { key: "duration", label: "Duration" },
      { key: "status", label: "Status" },
      { key: "progress", label: "Progress" },
      { key: "actions", label: "Actions" },
    ],
    rows,
    total: rows.length,
    empty_state: "No active orchestration runs.",
  };
});

const waitingQueueTable = computed<UiTableSection>(() => {
  const rows: UiTableRow[] = [
    ...page.value.run_queue.rows.map((row) => ({
      id: row.id,
      cells: {
        ...row.cells,
        source_section: "run_queue",
        run_id: rawCellText(row, "run_id"),
        type: rawCellText(row, "agent_target"),
        priority: rawCellText(row, "priority"),
        received_at: rawCellText(row, "enqueued_at"),
        wait_time: rawCellText(row, "wait_time"),
        status: row.status ?? "queued",
        actions: "Open / Trace",
        route: rawCellText(row, "route"),
        trace_route: rawCellText(row, "trace_route"),
      },
      status: row.status,
      tone: row.tone ?? "warning",
    })),
    ...page.value.ingress_queue.rows.map((row) => ({
      id: row.id,
      cells: {
        ...row.cells,
        source_section: "ingress_queue",
        run_id: rawCellText(row, "run_id") !== "-" ? rawCellText(row, "run_id") : rawCellText(row, "intake_key"),
        type: rawCellText(row, "source"),
        priority: rawCellText(row, "priority"),
        received_at: rawCellText(row, "received_at"),
        wait_time: rawCellText(row, "age"),
        status: rawCellText(row, "status") !== "-" ? rawCellText(row, "status") : row.status ?? "accepted",
        actions: "Open",
        route: rawCellText(row, "route"),
        trace_route: rawCellText(row, "trace_route"),
      },
      status: row.status,
      tone: row.tone ?? "warning",
    })),
  ];
  return {
    id: "waiting_queue",
    title: "Waiting Queue",
    columns: [
      { key: "run_id", label: "Run ID" },
      { key: "type", label: "Type" },
      { key: "priority", label: "Priority" },
      { key: "received_at", label: "Received At" },
      { key: "wait_time", label: "Wait Time" },
      { key: "status", label: "Status" },
      { key: "actions", label: "Actions" },
    ],
    rows,
    total: rows.length,
    empty_state: "Run queue is empty.",
  };
});

const overviewMainTable = computed<UiTableSection>(() => {
  const queuedCount = sectionCount(page.value.run_queue);
  const runningCount = metricNumber("active");
  const waitingCount = waitingCountFromDelta(metricCard("active")?.delta);
  const backpressureCount = Number(page.value.backpressure.total ?? 0);
  const failureCount = sectionCount(page.value.recent_failures);
  const eventCount = sectionCount(page.value.ops_event_log);
  const executorCount = sectionCount(page.value.executor_overview);
  const ingressCount = sectionCount(page.value.ingress_queue);

  const rows: UiTableRow[] = [
    overviewRow({
      id: "scheduler",
      component: sectionTitle(page.value.scheduler_status.id, page.value.scheduler_status.title),
      status: schedulerOverviewStatus(),
      count: page.value.scheduler_status.items.length,
      detail: schedulerOverviewDetail(),
      tone: schedulerOverviewTone(),
    }),
    overviewRow({
      id: "ingress",
      component: sectionTitle(page.value.ingress_queue.id, page.value.ingress_queue.title),
      status: ingressCount > 0 ? t("status.queued") : t("text.ready"),
      count: ingressCount,
      detail: metricDelta("ingress", metricCard("ingress")?.delta ?? ""),
      tone: ingressCount > 0 ? "warning" : "success",
    }),
    overviewRow({
      id: "runs",
      component: t("operations.orchestration.overview.runs"),
      status: runningCount > 0 ? t("status.running") : queuedCount > 0 || waitingCount > 0 ? t("status.waiting") : t("text.ready"),
      count: queuedCount + runningCount + waitingCount,
      detail: t("operations.orchestration.overview.runsDetail", {
        queued: queuedCount,
        running: runningCount,
        waiting: waitingCount,
      }),
      tone: queuedCount > 0 || waitingCount > 0 ? "warning" : runningCount > 0 ? "info" : "success",
    }),
    overviewRow({
      id: "backpressure",
      component: sectionTitle(page.value.backpressure.id, page.value.backpressure.title),
      status: backpressureCount > 0 ? t("operations.health.warning") : t("operations.health.healthy"),
      count: backpressureCount,
      detail: backpressureOverviewDetail(),
      tone: backpressureCount > 0 ? "warning" : "success",
    }),
    overviewRow({
      id: "executors",
      component: sectionTitle(page.value.executor_overview.id, page.value.executor_overview.title),
      status: executorCount > 0 ? t("text.online") : t("text.offline"),
      count: executorCount,
      detail: executorOverviewDetail(),
      tone: executorCount > 0 ? "success" : "warning",
    }),
    overviewRow({
      id: "failures",
      component: sectionTitle(page.value.recent_failures.id, page.value.recent_failures.title),
      status: failureCount > 0 ? t("operations.health.warning") : t("operations.health.healthy"),
      count: failureCount,
      detail: metricDelta("failed", metricCard("failed")?.delta ?? ""),
      tone: failureCount > 0 ? "danger" : "success",
    }),
    overviewRow({
      id: "events",
      component: sectionTitle(page.value.ops_event_log.id, page.value.ops_event_log.title),
      status: eventCount > 0 ? t("operations.events.status.observed") : t("operations.orchestration.value.noEvents"),
      count: eventCount,
      detail: t("operations.orchestration.overview.eventsDetail", { count: eventCount }),
      tone: eventCount > 0 ? "info" : "neutral",
    }),
  ];

  return {
    id: "runtime_overview",
    title: "Runtime Overview",
    columns: [
      { key: "component", label: "Component" },
      { key: "status", label: "Status" },
      { key: "count", label: "Count" },
      { key: "detail", label: "Detail" },
    ],
    rows,
    total: rows.length,
    empty_state: "No runtime overview records.",
  };
});

const mainTable = computed<UiTableSection>(() => {
  switch (activeTab.value) {
    case "overview":
      return overviewMainTable.value;
    case "lane_locks":
      return page.value.lane_locks;
    case "executors":
      return page.value.executor_overview;
    case "failures":
      return page.value.recent_failures;
    case "events":
      return page.value.ops_event_log;
    case "runs":
    default:
      return page.value.run_queue;
  }
});

const displayedMainTable = computed(() => displayTableSection(mainTable.value));
const mainClickableRows = computed(() => tableHasDetailRows(mainTable.value));

const mainPageSize = computed(() => {
  if (activeTab.value === "executors" || activeTab.value === "events") return 8;
  if (activeTab.value === "failures") return 6;
  return 8;
});

const displayedRunningTasksTable = computed(() => displayTableSection(runningTasksTable.value));
const displayedWaitingQueueTable = computed(() => displayTableSection(waitingQueueTable.value));
const workerPreviewRows = computed(() => page.value.executor_overview.rows.slice(0, 3).map((row) => {
  const load = rowCellText(row, "load");
  return {
    row,
    id: rowCellText(row, "worker_id") || row.id,
    status: rowCellText(row, "status"),
    tone: rowTone(row),
    load,
    loadPercent: percentFromText(load),
    running: rowCellText(row, "running"),
    capacity: rowCellText(row, "capacity"),
    currentRun: rowCellText(row, "current_run"),
    capabilities: capabilityChips(rowCellText(row, "capabilities")),
  };
}));
const laneLockPreviewRows = computed(() => page.value.lane_locks.rows.slice(0, 2).map((row) => ({
  row,
  key: rowCellText(row, "lane_key"),
  holder: rowCellText(row, "holder_run_id"),
  ttl: rowCellText(row, "ttl"),
  heldFor: firstPresentCell(row, ["duration", "held_for"]),
  tone: rowTone(row),
})));
const failurePreviewRows = computed(() => page.value.recent_failures.rows.slice(0, 2).map((row) => ({
  row,
  time: rowCellText(row, "time"),
  runId: rowCellText(row, "run_id"),
  error: rowCellText(row, "error"),
  status: rowCellText(row, "status"),
  tone: rowTone(row),
})));
const eventPreviewRows = computed(() => page.value.ops_event_log.rows.slice(0, 4).map((row) => ({
  row,
  time: rowCellText(row, "time"),
  title: rowCellText(row, "event"),
  level: rowCellText(row, "level"),
  entity: rowCellText(row, "run_id_entity"),
  source: rowCellText(row, "source"),
  tone: rowTone(row),
})));
const stuckPreviewRows = computed(() => page.value.stuck_runs.rows.slice(0, 2).map((row) => {
  const title = firstPresentCell(row, ["run_id", "run", "id"]) || row.id;
  const meta = [
    firstPresentCell(row, ["wait_reason", "reason"]),
    firstPresentCell(row, ["lane_key", "lane"]),
    firstPresentCell(row, ["age", "wait_time", "duration"]),
  ].filter((item) => item && item !== "-").join(" · ");
  return {
    id: row.id,
    title,
    meta,
    status: firstPresentCell(row, ["status", "action", "stage"]) || "-",
    tone: row.tone ?? "warning",
  };
}));
const stuckPreviewOverflow = computed(() => Math.max(0, page.value.stuck_runs.rows.length - stuckPreviewRows.value.length));

const selectedDetailHeadline = computed(() => {
  const detail = selectedDetail.value;
  if (!detail) return "";
  if (detail.sectionId === "run_queue") return firstPresentCell(detail.row, ["run_id", "intake_key"]);
  if (detail.sectionId === "ingress_queue") return firstPresentCell(detail.row, ["run_id", "intake_key"]);
  if (detail.sectionId === "lane_locks") return firstPresentCell(detail.row, ["holder_run_id", "lane_key"]);
  if (detail.sectionId === "executor_overview") return firstPresentCell(detail.row, ["current_run", "worker_id"]);
  if (detail.sectionId === "recent_failures") {
    return firstPresentCell(detail.row, ["error", "run_id"]);
  }
  return firstPresentCell(detail.row, ["event", "run_id_entity"]);
});

const selectedDetailSubtitle = computed(() => {
  const detail = selectedDetail.value;
  if (!detail) return "";
  if (detail.sectionId === "run_queue") {
    return [rowCellText(detail.row, "wait_reason"), rowCellText(detail.row, "lane_key")].filter((item) => item && item !== "-").join(" · ");
  }
  if (detail.sectionId === "ingress_queue") {
    return [rowCellText(detail.row, "source"), rowCellText(detail.row, "status"), rowCellText(detail.row, "age")].filter((item) => item && item !== "-").join(" · ");
  }
  if (detail.sectionId === "lane_locks") {
    return [rowCellText(detail.row, "lane_key"), rowCellText(detail.row, "reason")].filter((item) => item && item !== "-").join(" · ");
  }
  if (detail.sectionId === "executor_overview") {
    return [rowCellText(detail.row, "worker_id"), rowCellText(detail.row, "status")].filter((item) => item && item !== "-").join(" · ");
  }
  if (detail.sectionId === "recent_failures") {
    return [rowCellText(detail.row, "module"), rowCellText(detail.row, "run_id")].filter((item) => item && item !== "-").join(" · ");
  }
  return [rowCellText(detail.row, "level"), rowCellText(detail.row, "source")].filter((item) => item && item !== "-").join(" · ");
});

const selectedDetailFields = computed(() => {
  const detail = selectedDetail.value;
  if (!detail) return [];
  const keys = {
    run_queue: ["run_id", "priority", "lane_key", "enqueued_at", "agent_target", "wait_reason", "wait_time", "policy", "stage", "trace"],
    ingress_queue: ["run_id", "intake_key", "source", "status", "target_lane", "priority", "received_at", "age", "session_key", "summary", "trace"],
    lane_locks: ["lane_key", "holder_run_id", "type", "worker_id", "duration", "status", "progress", "lock_epoch", "ttl", "expires_at", "renewed_at", "reason", "held_for", "stage", "trace", "actions"],
    executor_overview: ["worker_id", "status", "last_heartbeat", "lease_expires_at", "current_run", "load", "running", "capacity", "available_slots", "capabilities", "runs_5m", "actions"],
    recent_failures: ["time", "run_id", "error", "status", "module", "trace", "actions"],
    ops_event_log: ["time", "level", "event", "summary", "run_id_entity", "source", "trace", "event_key"],
  }[detail.sectionId];

  return keys
    .map((key) => ({
      key,
      label: detailFieldLabel(key),
      value: rowCellText(detail.row, key),
      route: detailFieldRoute(detail.row, key),
    }))
    .filter((item) => item.value && item.value !== "-");
});

const selectedDetailText = computed(() => {
  const row = selectedDetail.value?.row;
  if (!row) return "-";
  return [rowCellText(row, "details"), rowCellText(row, "payload"), rowCellText(row, "raw_payload")]
    .find((item) => item && item !== "-") ?? "-";
});

const selectedDetailTone = computed<SegmentTone>(() => {
  const tone = selectedDetail.value?.row.tone;
  return tone === "info" || tone === "success" || tone === "warning" || tone === "danger" ? tone : "neutral";
});

const selectedDetailRoute = computed(() => {
  const row = selectedDetail.value?.row;
  return row ? normalizeRoute(rowCellText(row, "route")) : null;
});

const selectedTraceRoute = computed(() => {
  const row = selectedDetail.value?.row;
  return row ? normalizeRoute(rowCellText(row, "trace_route")) : null;
});

const selectedRunId = computed(() => {
  const row = selectedDetail.value?.row;
  return row ? rowRunId(row) : null;
});

const selectedRunActions = computed(() => {
  const runId = selectedRunId.value;
  if (!runId) return [];
  const terminal = isSelectedRunTerminal();
  return page.value.actions.filter((action) => (
    (action.id === "cancel_run" && !terminal)
    || (action.id === "requeue" && terminal)
  ));
});

function segmentTotal() {
  return page.value.backpressure.segments?.reduce((total, segment) => total + segment.value, 0) ?? Number(page.value.backpressure.total ?? 0);
}

function segmentPercent(value: number) {
  const total = segmentTotal();
  return total === 0 ? 0 : Math.round((value / total) * 100);
}

function donutBackground() {
  let cursor = 0;
  const total = segmentTotal();
  if (total === 0 || !page.value.backpressure.segments?.length) {
    return "var(--surface-raised)";
  }

  const stops = page.value.backpressure.segments.map((segment) => {
    const start = cursor;
    const end = cursor + (segment.value / total) * 100;
    cursor = end;
    const color = toneColors[segment.tone ?? "neutral"];
    return `${color} ${start}% ${end}%`;
  });

  return `conic-gradient(${stops.join(", ")})`;
}

function metricDelta(id: string, fallback: string): string {
  if (fallback) return translatedMetricDelta(id, fallback);
  const key = `operations.orchestration.delta.${id}`;
  const value = t(key);
  return value === key ? fallback : value;
}

function metricValue(id: string, value: string): string {
  if (id === "health") {
    const normalized = value.toLowerCase();
    if (normalized === "healthy") return t("operations.health.healthy");
    if (normalized === "warning") return t("operations.health.warning");
    if (normalized === "error") return t("operations.health.error");
  }
  return value;
}

function tabLabel(id: string, fallback: string): string {
  const key = `operations.orchestration.tab.${id}`;
  const value = t(key);
  return value === key ? fallback : value;
}

function sectionTitle(id: string, fallback: string): string {
  const key = `operations.orchestration.section.${id}`;
  const value = t(key);
  return value === key ? fallback : value;
}

function emptyState(section: UiTableSection): string {
  return section.empty_state ? tableText(section.empty_state) : t("table.noRecords");
}

function tableCountLabel(section: UiTableSection, suffix: "total" | "items" = "items"): string {
  if (section.total != null && section.total !== section.rows.length) {
    return t("operations.loadedTotalSuffix", {
      loaded: section.rows.length,
      total: section.total,
    });
  }
  const count = section.total ?? section.rows.length;
  return t(suffix === "total" ? "operations.totalSuffix" : "operations.itemsSuffix", { count });
}

function sectionCount(section: UiTableSection): number {
  return section.total ?? section.rows.length;
}

function metricCard(id: string): UiMetricCard | undefined {
  return metricsById.value.get(id);
}

function metricNumber(id: string): number {
  const value = Number(metricCard(id)?.value ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function waitingCountFromDelta(delta: string | null | undefined): number {
  const match = (delta ?? "").match(/^(\d+) waiting$/);
  return match ? Number(match[1]) : 0;
}

function overviewRow(input: {
  id: string;
  component: string;
  status: string;
  count: number;
  detail: string;
  tone: SegmentTone;
}): UiTableRow {
  return {
    id: input.id,
    cells: {
      component: input.component,
      status: input.status,
      count: input.count,
      detail: input.detail || "-",
    },
    status: input.status,
    tone: input.tone,
  };
}

function schedulerOverviewStatus(): string {
  const eventLoop = page.value.scheduler_status.items.find((item) => item.label === "Event Loop");
  return eventLoop ? schedulerItemValue(eventLoop.value) : t("operations.orchestration.value.noEvents");
}

function schedulerOverviewTone(): SegmentTone {
  const eventLoop = page.value.scheduler_status.items.find((item) => item.label === "Event Loop");
  if (!eventLoop) return "neutral";
  if (eventLoop.tone === "success" || eventLoop.tone === "warning" || eventLoop.tone === "danger" || eventLoop.tone === "info") {
    return eventLoop.tone;
  }
  const value = eventLoop.value.toLowerCase();
  if (value.includes("stale") || value.includes("error")) return "warning";
  if (value.includes("alive") || value.includes("observed")) return "success";
  return "neutral";
}

function schedulerOverviewDetail(): string {
  const items = page.value.scheduler_status.items.filter((item) => item.label !== "Event Loop").slice(0, 2);
  if (!items.length) return t("operations.orchestration.overview.noSchedulerSignals");
  return items.map((item) => `${schedulerItemLabel(item.label)}: ${schedulerItemValue(item.value)}`).join(" / ");
}

function backpressureOverviewDetail(): string {
  const segments = page.value.backpressure.segments ?? [];
  if (!segments.length) return t("operations.orchestration.overview.noBackpressure");
  return segments
    .map((segment) => `${backpressureLabel(segment.id, segment.label)} ${segment.value}`)
    .join(" / ");
}

function executorOverviewDetail(): string {
  const workerCapacity = page.value.policy_limits.items.find((item) => item.label === "Worker Capacity (Online / Total)");
  if (workerCapacity) return `${policyItemLabel(workerCapacity.label)}: ${policyItemValue(workerCapacity.value)}`;
  return t("operations.orchestration.overview.executorsDetail", { count: sectionCount(page.value.executor_overview) });
}

function displayTableSection(section: UiTableSection): UiTableSection {
  if (!isDetailSectionId(section.id)) return section;
  return {
    ...section,
    columns: section.columns.filter((column) => !isDrawerOnlyColumn(column)),
  };
}

function isDrawerOnlyColumn(column: UiTableColumn): boolean {
  return ["details", "payload", "raw-payload", "raw-payload-json"].includes(normalizeKey(column.key));
}

function normalizeKey(key: string): string {
  return key.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function isDetailSectionId(id: string): id is DetailSectionId {
  return [
    "run_queue",
    "ingress_queue",
    "lane_locks",
    "executor_overview",
    "recent_failures",
    "ops_event_log",
  ].includes(id);
}

function isTableRow(row: unknown): row is UiTableRow {
  return Boolean(row && typeof row === "object" && "cells" in row && "id" in row);
}

function rawCellValue(row: UiTableRow, key: string): string | number | null | UiTableCellValue | undefined {
  return row.cells[key];
}

function rawCellText(row: UiTableRow, key: string): string {
  const value = rawCellValue(row, key);
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return value.text;
  return String(value);
}

function detailSectionForRow(section: UiTableSection, row: UiTableRow): DetailSectionId | null {
  if (isDetailSectionId(section.id)) return section.id;
  const sourceSection = rawCellText(row, "source_section");
  return isDetailSectionId(sourceSection) ? sourceSection : null;
}

function tableHasDetailRows(section: UiTableSection): boolean {
  if (isDetailSectionId(section.id)) return true;
  return section.rows.some((row) => isDetailSectionId(rawCellText(row, "source_section")));
}

function rowCellText(row: UiTableRow, key: string): string {
  const text = rawCellText(row, key);
  if (isTimeKey(key) && isIsoDateTime(text)) return formatLocalTime(text);
  if (text === "Orchestration") return t("operations.module.orchestration");
  if (isRawDisplayKey(key)) return formatRawKeyLabel(text);
  return text;
}

function firstPresentCell(row: UiTableRow, keys: string[]): string {
  for (const key of keys) {
    const text = rowCellText(row, key);
    if (text && text !== "-") return text;
  }
  return "";
}

function rowTone(row: UiTableRow): SegmentTone {
  const tone = row.tone;
  if (tone === "info" || tone === "success" || tone === "warning" || tone === "danger") {
    return tone;
  }
  const status = String(row.status ?? rawCellText(row, "status")).toLowerCase();
  if (/(failed|error|offline|expired)/.test(status)) return "danger";
  if (/(warning|waiting|queued|draining|blocked)/.test(status)) return "warning";
  if (/(online|healthy|completed|success)/.test(status)) return "success";
  if (/(running|processing|observed)/.test(status)) return "info";
  return "neutral";
}

function percentFromText(value: string): number {
  const match = value.match(/(\d+(?:\.\d+)?)%/);
  if (!match) return 0;
  return Math.max(0, Math.min(100, Math.round(Number(match[1]))));
}

function capabilityChips(value: string): string[] {
  if (!value || value === "-") return [];
  return value
    .split(/[,/]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 3);
}

function isTimeKey(key: string): boolean {
  const normalized = normalizeKey(key);
  return normalized === "time" || normalized.endsWith("-at") || normalized.startsWith("last-");
}

function isRawDisplayKey(key: string): boolean {
  const normalized = normalizeKey(key);
  return ["event", "source", "topic", "event-key"].includes(normalized);
}

function detailFieldLabel(key: string): string {
  return {
    time: t("table.time"),
    run_id: t("table.runId"),
    intake_key: t("table.intakeKey"),
    target_lane: t("table.targetLane"),
    received_at: t("table.receivedAt"),
    age: t("table.age"),
    status: t("table.status"),
    type: t("table.type"),
    worker_id: t("table.workerId"),
    duration: t("table.duration"),
    progress: t("table.progress"),
    actions: t("table.actions"),
    current_run: t("table.currentRun"),
    running: t("status.running"),
    capacity: t("table.capacity"),
    available_slots: t("text.available"),
    capabilities: t("table.capabilities"),
    runs_5m: t("table.runs5m"),
    lock_epoch: t("table.lockEpoch"),
    ttl: "TTL",
    expires_at: t("table.expiresAt"),
    renewed_at: t("table.renewedAt"),
    held_for: t("table.duration"),
    stage: t("table.stage"),
    priority: t("table.priority"),
    session_key: t("table.sessionKey"),
    summary: t("table.summary"),
    error: t("table.error"),
    module: t("table.module"),
    trace: t("table.trace"),
    level: t("table.level"),
    event: t("table.event"),
    event_key: t("table.rawEventKey"),
    run_id_entity: t("table.runEntity"),
    source: t("table.source"),
  }[key] ?? key;
}

function detailFieldRoute(row: UiTableRow, key: string): string | null {
  const value = rawCellValue(row, key);
  if (value && typeof value === "object" && "route" in value) {
    return normalizeRoute(value.route);
  }
  const normalized = normalizeKey(key);
  if (normalized === "trace") return normalizeRoute(rawCellText(row, "trace_route"));
  if (normalized === "run-id" || normalized === "run-id-entity") return normalizeRoute(rawCellText(row, "route"));
  return null;
}

function normalizeRoute(value: string | null | undefined): string | null {
  if (!value || value === "-") return null;
  return value.replace(/^\/ui(?=\/)/, "");
}

function normalizeActionRunId(value: string | null | undefined): string | null {
  const normalized = value?.trim() ?? "";
  if (!normalized || normalized === "-") return null;
  return normalized;
}

function rowRunId(row: UiTableRow): string | null {
  return normalizeActionRunId(rawCellText(row, "run_id"))
    ?? normalizeActionRunId(rawCellText(row, "intake_key"))
    ?? normalizeActionRunId(rawCellText(row, "holder_run_id"))
    ?? normalizeActionRunId(rawCellText(row, "current_run"))
    ?? normalizeActionRunId(rawCellText(row, "run_id_entity"));
}

function selectedRunStatus(): string {
  const row = selectedDetail.value?.row;
  if (!row) return "";
  return String(row.status ?? rowCellText(row, "status")).toLowerCase();
}

function isSelectedRunTerminal(): boolean {
  return ["completed", "failed", "cancelled", "canceled", "success"].includes(selectedRunStatus());
}

function selectedRunActionLabel(action: UiRuntimeAction): string {
  if (action.id === "cancel_run") return t("operations.orchestration.action.cancelRun");
  if (action.id === "requeue") return t("operations.orchestration.action.requeue");
  return action.label;
}

function selectedRunActionIcon(action: UiRuntimeAction) {
  return action.id === "cancel_run" ? CircleX : RefreshCcw;
}

function selectedRunActionVariant(action: UiRuntimeAction): "secondary" | "danger" {
  return action.risk === "dangerous" ? "danger" : "secondary";
}

function canRunSelectedRunAction(action: UiRuntimeAction): boolean {
  return Boolean(selectedRunId.value) && action.allowed && !loading.value && actionBusy.value === null;
}

async function runSelectedRunAction(action: UiRuntimeAction) {
  const runId = selectedRunId.value;
  if (!runId || !canRunSelectedRunAction(action)) return;
  const label = selectedRunActionLabel(action);
  if (action.requires_confirmation && !window.confirm(t("operations.orchestration.action.confirm", { action: label, runId }))) {
    return;
  }
  const reason = window.prompt(t("operations.orchestration.action.reasonPrompt", { action: label, runId }));
  if (reason === null) return;

  actionBusy.value = action.id;
  actionNotice.value = null;
  loadError.value = null;
  try {
    const result = action.id === "cancel_run"
      ? await cancelOrchestrationRun(runId, reason.trim() || null)
      : await resumeOrchestrationRun(runId, reason.trim() || null);
    actionNotice.value = t("operations.orchestration.action.notice", {
      action: label,
      runId,
      status: String(result.status ?? "-"),
    });
    await refreshPage();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

function tableText(value: string): string {
  if (value === "No records.") return t("table.noRecords");
  if (value === "No orchestration events observed yet.") return t("operations.orchestration.empty.noEvents");
  if (value === "No stuck runs detected.") return t("operations.orchestration.empty.noStuckRuns");
  if (value === "Run queue is empty.") return t("operations.orchestration.empty.runQueue");
  if (value === "Ingress queue is empty.") return t("operations.orchestration.empty.ingressQueue");
  if (value === "No runtime overview records.") return t("operations.orchestration.empty.runtimeOverview");
  if (value === "No active orchestration runs.") return t("operations.orchestration.empty.noActiveRuns");
  if (value === "No active lane locks.") return t("operations.orchestration.empty.noLaneLocks");
  if (value === "No executor leases registered.") return t("operations.orchestration.empty.noExecutors");
  if (value === "No failed runs retained.") return t("operations.orchestration.empty.noFailures");
  return value;
}

function schedulerItemLabel(label: string): string {
  return {
    "Event Loop": t("operations.orchestration.scheduler.eventLoop"),
    "Last Tick": t("operations.orchestration.scheduler.lastTick"),
    "Tick Lag": t("operations.orchestration.scheduler.tickLag"),
    "Dispatch Latency": t("operations.orchestration.scheduler.dispatchLatency"),
    "Queue Age (p95)": t("operations.orchestration.scheduler.queueAge"),
    "Throughput (5m)": t("operations.orchestration.scheduler.throughput"),
    "Schedule Success Rate (5m)": t("operations.orchestration.scheduler.scheduleSuccessRate"),
    "Scheduler Signals": t("operations.orchestration.scheduler.schedulerSignals"),
    "Observed Cursor": t("operations.orchestration.scheduler.observedCursor"),
    "Observed Entities": t("operations.orchestration.scheduler.observedEntities"),
  }[label] ?? label;
}

function schedulerItemValue(value: string): string {
  if (value === "Alive") return t("operations.orchestration.value.alive");
  if (value === "Observed") return t("operations.orchestration.value.observed");
  if (value === "No events") return t("operations.orchestration.value.noEvents");
  if (value === "Stale") return t("operations.orchestration.value.stale");
  const schedulerSignals = value.match(/^(\d+) queued \/ (\d+) processing$/);
  if (schedulerSignals) {
    return t("operations.orchestration.value.schedulerSignals", {
      queued: schedulerSignals[1],
      processing: schedulerSignals[2],
    });
  }
  const observedEntities = value.match(/^(\d+) runs \/ (\d+) ingress \/ (\d+) signals \/ (\d+) executors$/);
  if (observedEntities) {
    return t("operations.orchestration.value.observedEntities", {
      runs: observedEntities[1],
      ingress: observedEntities[2],
      signals: observedEntities[3],
      executors: observedEntities[4],
    });
  }
  if (isIsoDateTime(value)) return formatLocalTime(value);
  return value;
}

function backpressureLabel(id: string, fallback: string): string {
  const key = `operations.orchestration.backpressure.${id}`;
  const value = t(key);
  return value === key ? fallback : value;
}

function policyItemLabel(label: string): string {
  return {
    "Per-lane Concurrency": t("operations.orchestration.policy.perLaneConcurrency"),
    "Global Run Concurrency": t("operations.orchestration.policy.globalRunConcurrency"),
    "Worker Capacity (Online / Total)": t("operations.orchestration.policy.workerCapacity"),
    "Approval Timeout": t("operations.orchestration.policy.approvalTimeout"),
    "Lease Timeout": t("operations.orchestration.policy.leaseTimeout"),
    "Lane Lock TTL": t("operations.orchestration.policy.laneLockTtl"),
    "Queue Retention": t("operations.orchestration.policy.queueRetention"),
    "Heartbeat Interval": t("operations.orchestration.policy.heartbeatInterval"),
  }[label] ?? label;
}

function policyItemValue(value: string): string {
  if (value === "not configured") return t("text.notConfigured");
  return value;
}

function policyText(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[_-]+/g, " ");
  if (normalized === "fifo" || normalized.includes("first in first out")) {
    return t("operations.orchestration.policy.fifo");
  }
  if (normalized === "priority" || normalized.includes("priority")) {
    return t("operations.orchestration.policy.priority");
  }
  return value;
}

function isIsoDateTime(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}T/.test(value);
}

function translatedMetricDelta(id: string, fallback: string): string {
  if (fallback === "All systems operational") return t("operations.orchestration.delta.health");
  if (fallback === "Operator attention recommended") return t("operations.orchestration.delta.attentionRecommended");
  if (fallback === "Operator action required") return t("operations.orchestration.delta.actionRequired");
  if (fallback === "Loading runtime state") return t("operations.orchestration.delta.loading");
  if (fallback === "ingress requests") return t("operations.orchestration.delta.ingressRequests");
  if (fallback === "requests/sec") return t("operations.orchestration.dashboard.requestsPerSecond");
  if (fallback === "accepted runs") return t("operations.orchestration.delta.acceptedRuns");
  if (fallback === "avg runtime") return t("operations.orchestration.dashboard.avgRuntime");
  if (fallback === "Waiting runs") return t("operations.orchestration.delta.backpressure");
  if (fallback === "Monitoring only") return t("operations.orchestration.delta.approval_waiting");
  if (fallback === "runtime facts unavailable") {
    return t("operations.orchestration.delta.observed_facts_unavailable");
  }
  const waiting = fallback.match(/^(\d+) waiting$/);
  if (waiting) return t("operations.orchestration.delta.waitingCount", { count: waiting[1] });
  const retained = fallback.match(/^(\d+) retained$/);
  if (retained) return t("operations.orchestration.delta.retainedCount", { count: retained[1] });
  const retainedCancelled = fallback.match(/^(\d+) retained \/ (\d+) cancelled$/);
  if (retainedCancelled) {
    return t("operations.orchestration.delta.retainedCancelled", {
      retained: retainedCancelled[1],
      cancelled: retainedCancelled[2],
    });
  }
  const observedFacts = fallback.match(/^(\d+) runs \/ (\d+) executors$/);
  if (observedFacts) {
    return t("operations.orchestration.delta.observed_facts", {
      runs: observedFacts[1],
      executors: observedFacts[2],
    });
  }
  if (fallback === emptyMetricDeltas[id]) return fallback;
  return fallback;
}

function emptyOrchestrationPage(): OperationsOrchestrationReadModel {
  return {
    module: "orchestration",
    title: "Orchestration",
    subtitle: "调度器、运行队列、Lane Lock、Executor、故障与操作事件的统一控制台。",
    health: "unknown",
    updated_at: new Date().toISOString(),
    auto_refresh: true,
    role: {
      label: "Admin",
      can_operate: true,
      scope: "orchestration",
    },
    metrics: emptyMetrics(),
    tabs: fallbackTabs,
    active_tab: "overview",
    actions: [],
    scheduler_status: emptyKeyValueSection("scheduler_status", "Scheduler Status"),
    backpressure: emptyChartSection("backpressure", "Backpressure", "donut"),
    stuck_runs: emptyTableSection("stuck_runs", "Stuck Runs"),
    policy_limits: emptyKeyValueSection("policy_limits", "Policy & Limits"),
    run_queue: emptyTableSection("run_queue", "Run Queue"),
    lane_locks: emptyTableSection("lane_locks", "Lane Locks"),
    executor_overview: emptyTableSection("executor_overview", "Executor Overview"),
    ingress_queue: emptyTableSection("ingress_queue", "Ingress Queue"),
    recent_failures: emptyTableSection("recent_failures", "Recent Failures"),
    ops_event_log: emptyTableSection("ops_event_log", "Ops Event Log"),
  };
}

function emptyMetrics(): UiMetricCard[] {
  return [
    { id: "health", label: "Overall Health", value: "Loading", delta: "Loading runtime state", tone: "neutral" },
    { id: "ingress", label: "Ingress Queue", value: "0", delta: emptyMetricDeltas.ingress, tone: "neutral" },
    { id: "ingress_rate", label: "Ingress Rate", value: "0/s", delta: emptyMetricDeltas.ingress_rate, tone: "neutral" },
    { id: "active", label: "Active Runs", value: "0", delta: emptyMetricDeltas.active, tone: "success" },
    { id: "run_queue", label: "Run Queue", value: "0", delta: emptyMetricDeltas.run_queue, tone: "success" },
    { id: "backpressure", label: "Backpressure", value: "0", delta: emptyMetricDeltas.backpressure, tone: "success" },
    { id: "approval_waiting", label: "Approval Waiting", value: "0", delta: emptyMetricDeltas.approval_waiting, tone: "success" },
    { id: "failed", label: "Recent Failed", value: "0", delta: emptyMetricDeltas.failed, tone: "success" },
    { id: "latency", label: "Average Latency", value: "0s", delta: emptyMetricDeltas.latency, tone: "neutral" },
    { id: "observed_facts", label: "Observed Facts", value: "0", delta: emptyMetricDeltas.observed_facts, tone: "neutral" },
  ];
}

function emptyKeyValueSection(id: string, title: string): UiKeyValueSection {
  return {
    id,
    title,
    items: [],
  };
}

function emptyChartSection(id: string, title: string, kind: UiChartSection["kind"]): UiChartSection {
  return {
    id,
    title,
    kind,
    total: 0,
    segments: [],
  };
}

function emptyTableSection(id: string, title: string): UiTableSection {
  return {
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  };
}

async function refreshPage() {
  loading.value = true;
  try {
    const loaded = await loadOrchestrationOperations();
    page.value = loaded.page;
    loadError.value = null;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

function selectTab(tabId: string) {
  selectedDetail.value = null;
  void router.replace({
    query: {
      ...route.query,
      tab: tabId === "overview" ? undefined : tabId,
    },
  });
}

function toggleAutoRefresh() {
  page.value = {
    ...page.value,
    auto_refresh: !page.value.auto_refresh,
  };
}

function openTableRow(section: UiTableSection, row: unknown) {
  if (!isTableRow(row)) return;
  const sectionId = detailSectionForRow(section, row);
  if (!sectionId) return;
  selectedDetail.value = {
    sectionId,
    title: sectionTitle(sectionId, section.title),
    row,
  };
}

function openMainTableRow(row: unknown) {
  openTableRow(mainTable.value, row);
}

function closeDetail() {
  selectedDetail.value = null;
}

watch(activeTab, () => {
  selectedDetail.value = null;
});

onMounted(() => {
  void refreshPage();
  refreshTimer.value = window.setInterval(() => {
    if (page.value.auto_refresh) void refreshPage();
  }, 5000);
});

onUnmounted(() => {
  if (refreshTimer.value !== null) {
    window.clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
});
</script>

<template>
  <main class="operations-module-console orchestration-console orchestra-page scroll-area">
    <section class="orchestra-status-bar">
      <div class="orchestra-health" :class="`orchestra-health--${runtimeHealthTone}`">
        <StatusDot :tone="runtimeHealthTone" />
        <div>
          <strong>{{ runtimeHealthLabel }}</strong>
          <small>{{ runtimeHealthSummary }}</small>
        </div>
      </div>

      <div class="orchestra-control-group">
        <div class="orchestra-control">
          <span>{{ t("operations.orchestration.dashboard.runtimeMode") }}</span>
          <select class="orchestra-select" :value="runtimeModeLabel" disabled>
            <option>{{ runtimeModeLabel }}</option>
          </select>
        </div>
        <div class="orchestra-control orchestra-control--switch">
          <span>{{ t("operations.orchestration.dashboard.autoSchedule") }}</span>
          <button
            class="orchestra-switch"
            :class="{ 'is-on': page.auto_refresh }"
            type="button"
            :aria-pressed="page.auto_refresh"
            @click="toggleAutoRefresh"
          >
            <i />
          </button>
        </div>
        <div class="orchestra-control">
          <span>{{ t("operations.orchestration.dashboard.concurrencyLimit") }}</span>
          <span class="orchestra-number-field">
            <strong>{{ concurrencyLimitLabel }}</strong>
          </span>
        </div>
        <div class="orchestra-control orchestra-control--wide">
          <span>{{ t("operations.orchestration.dashboard.queuePolicy") }}</span>
          <select class="orchestra-select" :value="queuePolicyLabel" disabled>
            <option>{{ queuePolicyLabel }}</option>
          </select>
        </div>
      </div>

      <div class="orchestra-actions">
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" disabled>
          <Activity :size="13" /> {{ t("operations.orchestration.dashboard.pauseScheduling") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" disabled>
          <Archive :size="13" /> {{ t("operations.orchestration.dashboard.drainMode") }}
        </UiButton>
        <UiButton size="sm" variant="danger" disabled>
          <CircleX :size="13" /> {{ t("operations.orchestration.dashboard.emergencyStop") }}
        </UiButton>
        <span class="orchestra-last-updated">
          {{ t("common.lastUpdated") }}:
          <strong>{{ lastUpdatedLabel }}</strong>
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="12" />
        </span>
      </div>
    </section>

    <div v-if="loadError" class="orchestration-alert orchestration-alert--danger">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>
    <div v-if="actionNotice" class="orchestration-alert orchestration-alert--success">
      <StatusDot tone="success" />
      <span>{{ actionNotice }}</span>
    </div>

    <section class="orchestra-metric-strip">
      <article
        v-for="metric in dashboardMetrics"
        :key="metric.id"
        class="orchestra-metric"
        :class="`orchestra-metric--${metric.tone}`"
      >
        <span class="orchestra-metric__icon"><component :is="metric.icon" :size="22" /></span>
        <span class="orchestra-metric__copy">
          <em>{{ metric.label }}</em>
          <strong>{{ metric.value }}</strong>
          <small>{{ metric.suffix }}</small>
        </span>
      </article>
    </section>

    <nav class="orchestra-tabs" :aria-label="t('operations.module.orchestration')">
      <button
        v-for="tab in page.tabs"
        :key="tab.id"
        :class="{ active: tab.id === activeTab }"
        type="button"
        @click="selectTab(tab.id)"
      >
        {{ tabLabel(tab.id, tab.label) }}
        <span v-if="tab.count">{{ tab.count }}</span>
      </button>
    </nav>

    <section v-if="activeTab === 'overview'" class="orchestra-dashboard">
      <div class="orchestra-main-column">
        <article class="orchestra-panel orchestra-panel--running">
          <header class="orchestra-panel__heading">
            <h3>{{ t("operations.orchestration.dashboard.runningTasks") }}</h3>
            <button type="button" @click="selectTab('runs')">{{ t("common.viewAll") }} <ExternalLink :size="12" /></button>
          </header>
          <DataTable
            v-if="runningTasksTable.rows.length"
            :columns="displayedRunningTasksTable.columns"
            :rows="displayedRunningTasksTable.rows"
            :section-id="displayedRunningTasksTable.id"
            :page-size="4"
            :clickable-rows="tableHasDetailRows(runningTasksTable)"
            @row-click="(row) => openTableRow(runningTasksTable, row)"
          />
          <p v-else class="panel-empty">{{ emptyState(runningTasksTable) }}</p>
        </article>

        <article class="orchestra-panel orchestra-panel--queue">
          <header class="orchestra-panel__heading">
            <h3>{{ t("operations.orchestration.dashboard.waitingQueue") }} <span>({{ waitingQueueTable.total }})</span></h3>
            <button type="button" @click="selectTab('runs')">{{ t("common.viewAll") }} <ExternalLink :size="12" /></button>
          </header>
          <DataTable
            v-if="waitingQueueTable.rows.length"
            :columns="displayedWaitingQueueTable.columns"
            :rows="displayedWaitingQueueTable.rows"
            :section-id="displayedWaitingQueueTable.id"
            :page-size="4"
            :clickable-rows="tableHasDetailRows(waitingQueueTable)"
            @row-click="(row) => openTableRow(waitingQueueTable, row)"
          />
          <p v-else class="panel-empty">{{ emptyState(waitingQueueTable) }}</p>
        </article>

        <article class="orchestra-panel orchestra-panel--events">
          <header class="orchestra-panel__heading">
            <h3>{{ t("operations.orchestration.dashboard.systemEvents") }}</h3>
            <button type="button" @click="selectTab('events')">{{ t("common.viewAll") }} <ExternalLink :size="12" /></button>
          </header>
          <div v-if="eventPreviewRows.length" class="orchestra-event-list">
            <button
              v-for="event in eventPreviewRows"
              :key="event.row.id"
              class="orchestra-event-row"
              type="button"
              @click="openTableRow(page.ops_event_log, event.row)"
            >
              <StatusDot :tone="event.tone" />
              <span class="orchestra-event-row__time">{{ event.time }}</span>
              <span class="orchestra-event-row__copy">
                <strong :title="event.title">{{ event.title }}</strong>
                <small :title="[event.entity, event.source].filter((item) => item && item !== '-').join(' · ')">
                  {{ [event.entity, event.source].filter((item) => item && item !== "-").join(" · ") || event.level }}
                </small>
              </span>
              <em :class="`orchestra-badge orchestra-badge--${event.tone}`">{{ event.level }}</em>
            </button>
          </div>
          <p v-else class="panel-empty">{{ emptyState(page.ops_event_log) }}</p>
        </article>
      </div>

      <aside class="orchestra-side-column">
        <article class="orchestra-panel orchestra-panel--workers">
          <header class="orchestra-panel__heading">
            <h3>{{ t("operations.orchestration.dashboard.workers") }} <span>({{ page.executor_overview.total ?? page.executor_overview.rows.length }})</span></h3>
            <button type="button" @click="selectTab('executors')">{{ t("common.viewAll") }} <ExternalLink :size="12" /></button>
          </header>
          <div v-if="workerPreviewRows.length" class="orchestra-worker-list">
            <button
              v-for="worker in workerPreviewRows"
              :key="worker.row.id"
              class="orchestra-worker-row"
              type="button"
              @click="openTableRow(page.executor_overview, worker.row)"
            >
              <span class="orchestra-worker-row__main">
                <strong :title="worker.id">{{ worker.id }}</strong>
                <small>
                  <StatusDot :tone="worker.tone" />
                  {{ worker.status }}
                </small>
              </span>
              <span class="orchestra-worker-row__meter">
                <i><b :style="{ width: `${worker.loadPercent}%` }" /></i>
                <em>{{ worker.load }}</em>
              </span>
              <span class="orchestra-worker-row__meta">
                <small>{{ t("status.running") }} {{ worker.running }}/{{ worker.capacity }}</small>
                <small :title="worker.currentRun">{{ t("table.currentRun") }} {{ worker.currentRun }}</small>
              </span>
              <span class="orchestra-chip-row">
                <em v-for="chip in worker.capabilities" :key="chip">{{ chip }}</em>
              </span>
            </button>
          </div>
          <p v-else class="panel-empty compact-empty">{{ emptyState(page.executor_overview) }}</p>
        </article>

        <article class="orchestra-panel orchestra-panel--locks">
          <header class="orchestra-panel__heading">
            <h3>{{ t("operations.orchestration.dashboard.laneLocks") }} <span>({{ page.lane_locks.total ?? page.lane_locks.rows.length }})</span></h3>
            <button type="button" @click="selectTab('lane_locks')">{{ t("common.viewAll") }} <ExternalLink :size="12" /></button>
          </header>
          <div v-if="laneLockPreviewRows.length" class="orchestra-mini-table orchestra-mini-table--locks">
            <button
              v-for="lock in laneLockPreviewRows"
              :key="lock.row.id"
              class="orchestra-mini-row"
              type="button"
              @click="openTableRow(page.lane_locks, lock.row)"
            >
              <span :title="lock.key">{{ lock.key }}</span>
              <span :title="lock.holder">{{ lock.holder }}</span>
              <span>{{ lock.heldFor }}</span>
              <em>{{ lock.ttl }}</em>
            </button>
          </div>
          <p v-else class="panel-empty compact-empty">{{ emptyState(page.lane_locks) }}</p>
        </article>

        <article class="orchestra-panel orchestra-panel--failures">
          <header class="orchestra-panel__heading">
            <h3>{{ t("operations.orchestration.dashboard.recentFailures") }}</h3>
            <button type="button" @click="selectTab('failures')">{{ t("common.viewAll") }} <ExternalLink :size="12" /></button>
          </header>
          <div v-if="failurePreviewRows.length" class="orchestra-mini-table orchestra-mini-table--failures">
            <button
              v-for="failure in failurePreviewRows"
              :key="failure.row.id"
              class="orchestra-mini-row"
              type="button"
              @click="openTableRow(page.recent_failures, failure.row)"
            >
              <span>{{ failure.time }}</span>
              <span :title="failure.runId">{{ failure.runId }}</span>
              <span :title="failure.error">{{ failure.error }}</span>
              <em :class="`orchestra-badge orchestra-badge--${failure.tone}`">{{ failure.status }}</em>
            </button>
          </div>
          <p v-else class="panel-empty compact-empty">{{ emptyState(page.recent_failures) }}</p>
        </article>

        <article class="orchestra-panel orchestra-panel--quick">
          <header class="orchestra-panel__heading">
            <h3>{{ t("operations.orchestration.dashboard.quickActions") }}</h3>
          </header>
          <div class="orchestra-quick-grid">
            <button type="button" @click="selectTab('runs')">
              <Archive :size="16" />
              <span>{{ t("operations.orchestration.dashboard.inspectQueue") }}</span>
              <small>{{ t("operations.orchestration.dashboard.inspectQueueHint") }}</small>
            </button>
            <button type="button" @click="selectTab('failures')">
              <RefreshCcw :size="16" />
              <span>{{ t("operations.orchestration.dashboard.retryFailures") }}</span>
              <small>{{ t("operations.orchestration.dashboard.retryFailuresHint") }}</small>
            </button>
            <button type="button" @click="selectTab('events')">
              <Activity :size="16" />
              <span>{{ t("operations.orchestration.dashboard.exportLogs") }}</span>
              <small>{{ t("operations.orchestration.dashboard.exportLogsHint") }}</small>
            </button>
            <button type="button" disabled>
              <Network :size="16" />
              <span>{{ t("operations.orchestration.dashboard.adjustConcurrency") }}</span>
              <small>{{ t("operations.orchestration.dashboard.adjustConcurrencyHint") }}</small>
            </button>
            <button type="button" disabled>
              <ShieldCheck :size="16" />
              <span>{{ t("operations.orchestration.dashboard.forceReleaseLocks") }}</span>
              <small>{{ t("operations.orchestration.dashboard.forceReleaseLocksHint") }}</small>
            </button>
            <button type="button" @click="selectTab('executors')">
              <Users :size="16" />
              <span>{{ t("operations.orchestration.dashboard.diagnose") }}</span>
              <small>{{ t("operations.orchestration.dashboard.diagnoseHint") }}</small>
            </button>
          </div>
        </article>
      </aside>
    </section>

    <section v-else class="orchestra-focus-grid">
      <article class="orchestra-panel orchestra-panel--focus-table">
        <header class="orchestra-panel__heading">
          <h3>{{ sectionTitle(mainTable.id, mainTable.title) }}</h3>
          <span>{{ tableCountLabel(mainTable, "total") }}</span>
        </header>
        <DataTable
          v-if="mainTable.rows.length"
          :columns="displayedMainTable.columns"
          :rows="displayedMainTable.rows"
          :section-id="displayedMainTable.id"
          :page-size="mainPageSize"
          :clickable-rows="mainClickableRows"
          @row-click="openMainTableRow"
        />
        <p v-else class="panel-empty">{{ emptyState(mainTable) }}</p>
      </article>
    </section>

    <Teleport to="body">
      <div v-if="selectedDetail" class="orchestration-detail-overlay" @click.self="closeDetail">
        <aside class="orchestration-detail-drawer" role="dialog" aria-modal="true" :aria-label="t('table.details')">
          <header>
            <div>
              <span>{{ selectedDetail.title }}</span>
              <h3><StatusDot :tone="selectedDetailTone" />{{ selectedDetailHeadline }}</h3>
              <p>{{ selectedDetailSubtitle }}</p>
            </div>
            <div class="drawer-actions">
              <RouterLink v-if="selectedDetailRoute" :to="selectedDetailRoute" class="drawer-link">
                <ExternalLink :size="13" /> {{ t("text.open") }}
              </RouterLink>
              <RouterLink v-if="selectedTraceRoute" :to="selectedTraceRoute" class="drawer-link">
                <ExternalLink :size="13" /> {{ t("text.openTrace") }}
              </RouterLink>
              <button
                v-for="action in selectedRunActions"
                :key="action.id"
                class="drawer-command"
                :class="`drawer-command--${selectedRunActionVariant(action)}`"
                type="button"
                :disabled="!canRunSelectedRunAction(action)"
                @click="runSelectedRunAction(action)"
              >
                <component :is="selectedRunActionIcon(action)" :class="{ 'motion-spin': actionBusy === action.id }" :size="13" />
                {{ selectedRunActionLabel(action) }}
              </button>
              <button type="button" :aria-label="t('common.collapseDetails')" @click="closeDetail">
                <X :size="15" />
              </button>
            </div>
          </header>

          <section class="drawer-section">
            <dl class="drawer-kv">
              <div v-for="field in selectedDetailFields" :key="field.key">
                <dt>{{ field.label }}</dt>
                <dd>
                  <RouterLink v-if="field.route" :to="field.route" :title="field.value">{{ field.value }}</RouterLink>
                  <span v-else :title="field.value">{{ field.value }}</span>
                </dd>
              </div>
            </dl>
          </section>

          <section class="drawer-section drawer-section--raw">
            <h4>{{ t("table.details") }}</h4>
            <pre>{{ selectedDetailText }}</pre>
          </section>
        </aside>
      </div>
    </Teleport>
  </main>
</template>

<style scoped>
.orchestration-console {
  height: calc(100dvh - var(--shell-topbar-height));
  min-width: 0;
  padding: 8px 12px 12px;
  overflow: auto;
  scrollbar-gutter: stable;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 220px);
}

.orchestration-header,
.orchestration-header__actions,
.orchestration-metrics,
.orchestration-tabs,
.panel-heading,
.pressure-panel li,
.orchestration-footnote {
  display: flex;
  align-items: center;
}

.orchestration-header {
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
  font-size: 13px;
}

.orchestration-header p:not(.eyebrow) {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestration-header__actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 10.5px;
}

.orchestration-header__actions span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.orchestration-header__actions strong {
  color: var(--text-primary);
}

.auto-toggle i {
  width: 24px;
  height: 14px;
  border-radius: 999px;
  background: var(--color-success);
  box-shadow: inset 10px 0 0 color-mix(in srgb, #ffffff 92%, transparent);
}

.auto-toggle--off i {
  background: var(--text-muted);
  box-shadow: inset -10px 0 0 color-mix(in srgb, #ffffff 86%, transparent);
}

.role-badge {
  border-color: color-mix(in srgb, var(--color-warning) 64%, var(--border-subtle)) !important;
  color: var(--color-warning) !important;
}

.divider {
  width: 1px;
  height: 18px;
  background: var(--border-default);
}

.orchestration-alert {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 88%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
}

.orchestration-alert span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestration-alert small {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.orchestration-alert--danger {
  border-color: color-mix(in srgb, var(--color-danger) 42%, var(--border-subtle));
}

.orchestration-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 34%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 8%, var(--surface-panel));
}

.orchestration-metrics {
  display: grid;
  grid-template-columns: repeat(8, minmax(96px, 1fr));
  gap: 6px;
  margin-bottom: 6px;
}

.orchestration-metric,
.orchestration-overview > article,
.orchestration-main-grid > article,
.orchestration-side-stack > article {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 88%, transparent);
}

.orchestration-metric {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 6px;
  align-items: center;
  height: 76px;
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
  background: color-mix(in srgb, var(--color-blue) 22%, transparent);
  color: var(--color-blue);
}

.orchestration-metric--success .metric-icon {
  background: color-mix(in srgb, var(--color-success) 20%, transparent);
  color: var(--color-success);
}

.orchestration-metric--warning .metric-icon {
  background: color-mix(in srgb, var(--color-warning) 22%, transparent);
  color: var(--color-warning);
}

.orchestration-metric--danger .metric-icon {
  background: color-mix(in srgb, var(--color-danger) 20%, transparent);
  color: var(--color-danger);
}

.metric-copy {
  min-width: 0;
}

.metric-copy em {
  display: block;
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
}

.metric-copy strong {
  display: block;
  margin-top: 3px;
  color: var(--text-primary);
  font-size: 17px;
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
  -webkit-line-clamp: 2;
}

.orchestration-metric--success .metric-copy strong {
  color: var(--color-success);
}

.orchestration-metric--warning .metric-copy strong {
  color: var(--color-warning);
}

.orchestration-metric--danger .metric-copy strong {
  color: var(--color-danger);
}

.orchestration-tabs {
  gap: 14px;
  min-height: 29px;
  margin-top: 6px;
  border-bottom: 1px solid var(--border-subtle);
  overflow-x: auto;
  scrollbar-width: thin;
}

.orchestration-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
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

.orchestration-tabs button.active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.orchestration-tabs span,
.panel-heading span {
  color: var(--text-muted);
  font-size: 11px;
}

.orchestration-overview {
  display: grid;
  grid-template-columns: minmax(210px, 0.9fr) minmax(240px, 1fr) minmax(230px, 1.1fr) minmax(210px, 0.9fr);
  gap: 6px;
  align-items: start;
  margin-top: 6px;
}

.orchestration-overview > article,
.orchestration-main-grid > article,
.orchestration-side-stack > article {
  min-width: 0;
  padding: 8px;
}

.orchestration-overview > article {
  min-height: 112px;
  overflow: visible;
}

.scheduler-panel dl,
.policy-panel dl {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  max-height: none;
  overflow: visible;
}

.scheduler-panel dl div,
.policy-panel dl div {
  display: grid;
  gap: 1px;
  min-width: 0;
  padding: 4px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.scheduler-panel dt,
.policy-panel dt {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scheduler-panel dd,
.policy-panel dd {
  overflow: visible;
  white-space: nowrap;
}

.scheduler-panel dt,
.policy-panel dt {
  font-size: 9px;
}

.scheduler-panel dd,
.policy-panel dd {
  font-size: 11px;
}

.overview-more {
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1;
  text-align: right;
}

.stuck-preview-list {
  display: grid;
  gap: 6px;
  margin-top: 6px;
}

.stuck-preview-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 6px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.stuck-preview-row span {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.stuck-preview-row strong,
.stuck-preview-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stuck-preview-row strong {
  color: var(--text-secondary);
  font-size: 11.5px;
}

.stuck-preview-row small {
  color: var(--text-muted);
  font-size: 10px;
}

.stuck-preview-status {
  max-width: 78px;
  padding: 2px 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stuck-preview-status--warning {
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
  color: var(--color-warning);
}

.stuck-preview-status--danger {
  background: color-mix(in srgb, var(--color-danger) 14%, transparent);
  color: var(--color-danger);
}

.stuck-preview-status--success {
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
  color: var(--color-success);
}

.stuck-preview-more {
  margin: 0;
  color: var(--text-muted);
  font-size: 10px;
  text-align: right;
}

dl {
  display: grid;
  gap: 5px;
  margin-top: 6px;
}

dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 11px;
}

dt {
  color: var(--text-muted);
}

dd {
  color: var(--text-secondary);
  font-weight: 700;
}

.value--success {
  color: var(--color-success);
}

.value--warning {
  color: var(--color-warning);
}

.pressure-panel {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 9px;
}

.pressure-donut {
  display: grid;
  place-items: center;
  width: 78px;
  height: 78px;
  border-radius: 999px;
}

.pressure-donut > div {
  display: grid;
  grid-template-rows: auto auto;
  align-content: center;
  justify-items: center;
  gap: 2px;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 999px;
  background: var(--surface-panel);
  text-align: center;
}

.pressure-donut strong {
  font-size: 15px;
  font-weight: 800;
  line-height: 1;
}

.pressure-donut span {
  max-width: 44px;
  color: var(--text-muted);
  font-size: 9px;
  line-height: 1.08;
}

.pressure-panel ul {
  display: grid;
  gap: 5px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.pressure-panel li {
  justify-content: space-between;
  gap: 8px;
  color: var(--text-muted);
  font-size: 11px;
}

.pressure-panel li span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.pressure-panel li strong {
  margin-left: auto;
  color: var(--text-secondary);
}

.pressure-panel li em {
  width: 34px;
  color: var(--text-muted);
  font-style: normal;
  text-align: right;
}

.orchestration-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 2.25fr) minmax(290px, 0.72fr);
  gap: 6px;
  margin-top: 6px;
}

.orchestration-table-panel {
  display: flex;
  flex-direction: column;
  min-height: clamp(320px, calc(100dvh - var(--shell-topbar-height) - 430px), 500px);
}

.orchestration-table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
  max-height: 100%;
}

.orchestration-side-stack {
  display: grid;
  gap: 6px;
  align-content: start;
  min-width: 0;
}

.panel-heading {
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 5px;
}

.panel-empty {
  flex: 1 1 auto;
  display: grid;
  min-height: 54px;
  place-items: center;
  color: var(--text-muted);
  font-size: 11px;
}

.compact-empty {
  min-height: 44px;
}

.orchestration-footnote {
  display: none;
}

.orchestration-detail-overlay {
  position: fixed;
  inset: var(--shell-topbar-height, 50px) 0 0;
  z-index: 40;
}

.orchestration-detail-drawer {
  position: absolute;
  top: 16px;
  right: 20px;
  bottom: 20px;
  display: grid;
  align-content: start;
  gap: 12px;
  width: min(480px, calc(100vw - 36px));
  overflow: auto;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 96%, var(--surface-page));
  box-shadow: var(--shadow-floating);
}

.orchestration-detail-drawer header,
.drawer-actions,
.drawer-link,
.drawer-kv div {
  display: flex;
  align-items: center;
}

.orchestration-detail-drawer header {
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.orchestration-detail-drawer header > div:first-child {
  min-width: 0;
}

.orchestration-detail-drawer header span,
.orchestration-detail-drawer h4 {
  color: var(--text-muted);
  font-size: 11px;
}

.orchestration-detail-drawer header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 15px;
}

.orchestration-detail-drawer header p {
  margin-top: 5px;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-actions {
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.drawer-link,
.drawer-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-decoration: none;
}

.drawer-actions button {
  width: 30px;
  padding: 0;
}

.drawer-actions button.drawer-command {
  width: auto;
  gap: 6px;
  padding: 0 9px;
}

.drawer-actions button.drawer-command--danger {
  border-color: color-mix(in srgb, var(--color-danger) 48%, var(--border-subtle));
  color: var(--color-danger);
}

.drawer-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.drawer-section {
  min-width: 0;
}

.drawer-kv {
  display: grid;
  gap: 8px;
  margin-top: 0;
}

.drawer-kv div {
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.drawer-kv dt {
  flex: 0 0 112px;
  font-size: 11px;
}

.drawer-kv dd {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-size: 11px;
  text-align: right;
}

.drawer-kv a {
  color: var(--color-accent);
  text-decoration: none;
}

.drawer-section--raw {
  display: grid;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.drawer-section--raw pre {
  min-height: 116px;
  max-height: 44vh;
  margin: 0;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.motion-spin {
  animation: orchestration-spin 0.9s linear infinite;
}

@keyframes orchestration-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1280px) {
  .orchestration-metrics {
    grid-template-columns: repeat(4, minmax(132px, 1fr));
  }

  .orchestration-overview,
  .orchestration-main-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .orchestration-side-stack {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .orchestration-console {
    height: calc(100dvh - var(--shell-topbar-height));
    padding: 12px;
  }

  .orchestration-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .orchestration-header__actions {
    justify-content: flex-start;
  }

  .orchestration-metrics {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: thin;
  }

  .orchestration-metric {
    flex: 0 0 152px;
  }

  .orchestration-overview {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .orchestration-overview > article {
    flex: 0 0 276px;
  }

  .orchestration-tabs {
    overflow-x: auto;
  }

  .orchestration-side-stack {
    grid-template-columns: minmax(0, 1fr);
  }

  .pressure-panel {
    grid-template-columns: minmax(0, 1fr);
  }

  .pressure-donut {
    margin-inline: auto;
  }

  .orchestration-detail-drawer {
    top: 12px;
    right: 12px;
    bottom: 12px;
    width: calc(100vw - 24px);
  }
}

.orchestra-page {
  --orch-gap: 8px;
  --orch-panel-bg: color-mix(in srgb, var(--surface-panel) 92%, transparent);
  --orch-panel-border: 1px solid color-mix(in srgb, var(--border-subtle) 88%, var(--color-blue) 12%);

  height: calc(100dvh - var(--shell-topbar-height));
  padding: 10px 12px 12px;
  overflow: auto;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-page-gradient-start) 86%, #07111e), var(--surface-page) 260px);
}

.orchestra-status-bar,
.orchestra-control-group,
.orchestra-actions,
.orchestra-metric,
.orchestra-tabs,
.orchestra-panel__heading,
.orchestra-panel__heading button,
.orchestra-last-updated,
.orchestra-quick-grid button {
  display: flex;
  align-items: center;
}

.orchestra-status-bar {
  flex-wrap: wrap;
  gap: 10px 14px;
  min-height: 72px;
  margin-bottom: var(--orch-gap);
  padding: 10px 12px;
  border: var(--orch-panel-border);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.orchestra-health {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  flex: 0 0 156px;
  min-width: 0;
}

.orchestra-health strong {
  display: block;
  color: var(--text-primary);
  font-size: 18px;
  line-height: 1.05;
}

.orchestra-health small,
.orchestra-control span,
.orchestra-last-updated {
  color: var(--text-muted);
  font-size: 11px;
}

.orchestra-health--success strong {
  color: var(--color-success);
}

.orchestra-health--warning strong {
  color: var(--color-warning);
}

.orchestra-health--danger strong {
  color: var(--color-danger);
}

.orchestra-control-group {
  flex: 1 1 520px;
  gap: 0;
  min-width: 360px;
}

.orchestra-control {
  display: grid;
  gap: 5px;
  min-width: 104px;
  padding: 0 18px;
  border-left: 1px solid var(--border-subtle);
}

.orchestra-control:first-child {
  border-left: 0;
}

.orchestra-control--wide {
  min-width: 156px;
}

.orchestra-control--switch {
  min-width: 118px;
}

.orchestra-control strong {
  max-width: 178px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestra-select,
.orchestra-number-field {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-raised) 88%, transparent);
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 800;
}

.orchestra-select {
  max-width: 148px;
  appearance: none;
}

.orchestra-select:disabled {
  opacity: 1;
}

.orchestra-number-field {
  width: 54px;
  justify-content: space-between;
}

.orchestra-switch {
  position: relative;
  width: 34px;
  height: 18px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--color-success) 48%, var(--border-subtle));
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-success) 28%, transparent);
  cursor: pointer;
}

.orchestra-switch i {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: var(--text-primary);
  transition: transform 0.16s ease;
}

.orchestra-switch.is-on i {
  transform: translateX(16px);
}

.orchestra-actions {
  justify-content: flex-end;
  gap: 8px;
  flex: 0 1 auto;
  margin-left: auto;
}

.orchestra-last-updated {
  gap: 5px;
  min-width: 0;
  white-space: nowrap;
}

.orchestra-last-updated strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
}

.orchestra-metric-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(128px, 1fr));
  gap: var(--orch-gap);
  margin-bottom: var(--orch-gap);
}

.orchestra-metric {
  min-height: 80px;
  gap: 11px;
  padding: 12px;
  border: var(--orch-panel-border);
  border-radius: var(--radius-2);
  background: var(--orch-panel-bg);
  overflow: hidden;
}

.orchestra-metric__icon {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
}

.orchestra-metric--success .orchestra-metric__icon {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.orchestra-metric--warning .orchestra-metric__icon {
  background: color-mix(in srgb, var(--color-warning) 22%, transparent);
  color: var(--color-warning);
}

.orchestra-metric--danger .orchestra-metric__icon {
  background: color-mix(in srgb, var(--color-danger) 20%, transparent);
  color: var(--color-danger);
}

.orchestra-metric__copy {
  min-width: 0;
}

.orchestra-metric__copy em,
.orchestra-metric__copy small {
  display: block;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestra-metric__copy strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 21px;
  font-weight: 850;
  line-height: 1;
}

.orchestra-metric__copy small {
  margin-top: 4px;
  font-family: var(--font-mono);
}

.orchestra-tabs {
  gap: 18px;
  min-height: 31px;
  margin-bottom: var(--orch-gap);
  border-bottom: 1px solid var(--border-subtle);
  overflow-x: auto;
  scrollbar-width: thin;
}

.orchestra-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 31px;
  padding: 0 1px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 750;
  white-space: nowrap;
}

.orchestra-tabs button.active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.orchestra-tabs span {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 18px;
  text-align: center;
}

.orchestra-dashboard,
.orchestra-focus-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.58fr) minmax(350px, 0.92fr);
  gap: var(--orch-gap);
  height: calc(100dvh - var(--shell-topbar-height) - 264px);
  min-height: 520px;
}

.orchestra-main-column,
.orchestra-side-column {
  display: grid;
  gap: var(--orch-gap);
  min-height: 0;
}

.orchestra-main-column {
  grid-template-rows: minmax(140px, 0.72fr) minmax(150px, 0.8fr) minmax(200px, 1fr);
}

.orchestra-side-column {
  grid-template-rows: minmax(176px, 0.98fr) minmax(104px, 0.6fr) minmax(116px, 0.66fr) minmax(164px, 0.94fr);
}

.orchestra-focus-grid {
  grid-template-columns: minmax(0, 1fr);
}

.orchestra-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  padding: 10px 10px 8px;
  border: var(--orch-panel-border);
  border-radius: var(--radius-2);
  background: var(--orch-panel-bg);
}

.orchestra-panel__heading {
  justify-content: space-between;
  gap: 10px;
  min-height: 24px;
  margin-bottom: 6px;
}

.orchestra-panel__heading h3 {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestra-panel__heading h3 span,
.orchestra-panel__heading > span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 650;
}

.orchestra-panel__heading button {
  flex: 0 0 auto;
  gap: 5px;
  min-height: 24px;
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--color-accent);
  cursor: pointer;
  font-size: 11px;
  font-weight: 750;
}

.orchestra-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.orchestra-panel :deep(th),
.orchestra-panel :deep(td) {
  height: 27px;
  min-height: 27px;
  padding: 3px 7px;
  font-size: 10.5px;
}

.orchestra-panel :deep(.data-table__pager) {
  min-height: 30px;
  padding-top: 5px;
}

.orchestra-panel--workers :deep(.column-current-run),
.orchestra-panel--failures :deep(.column-error),
.orchestra-panel--events :deep(.column-event) {
  width: 150px;
}

.orchestra-panel--queue :deep(.column-actions),
.orchestra-panel--running :deep(.column-actions) {
  width: 74px;
}

.orchestra-panel--focus-table {
  min-height: 0;
}

.orchestra-panel .panel-empty {
  flex: 1 1 auto;
  min-height: 0;
  place-items: center;
  color: var(--text-muted);
  font-size: 11px;
}

.orchestra-worker-list,
.orchestra-event-list,
.orchestra-mini-table {
  display: grid;
  gap: 6px;
  flex: 1 1 auto;
  min-height: 0;
}

.orchestra-worker-row,
.orchestra-event-row,
.orchestra-mini-row {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
}

.orchestra-worker-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 82px;
  gap: 5px 8px;
  min-height: 38px;
  padding: 6px 7px;
}

.orchestra-worker-row__main,
.orchestra-worker-row__meter,
.orchestra-worker-row__meta,
.orchestra-worker-row__main small,
.orchestra-event-row__copy,
.orchestra-chip-row {
  min-width: 0;
}

.orchestra-worker-row__main {
  display: grid;
  gap: 2px;
}

.orchestra-worker-row__main strong,
.orchestra-worker-row__main small,
.orchestra-worker-row__meta small,
.orchestra-event-row__copy strong,
.orchestra-event-row__copy small,
.orchestra-mini-row span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestra-worker-row__main strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
}

.orchestra-worker-row__main small {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font-size: 10px;
}

.orchestra-worker-row__meter {
  display: grid;
  align-content: center;
  gap: 3px;
}

.orchestra-worker-row__meter i {
  display: block;
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-raised);
}

.orchestra-worker-row__meter b {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-success);
}

.orchestra-worker-row__meter em {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-style: normal;
  text-align: right;
}

.orchestra-worker-row__meta {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
  gap: 6px;
  grid-column: 1 / -1;
}

.orchestra-worker-row__meta small {
  color: var(--text-muted);
  font-size: 9.5px;
}

.orchestra-chip-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  grid-column: 1 / -1;
  overflow: hidden;
}

.orchestra-chip-row em {
  max-width: 92px;
  padding: 1px 5px;
  overflow: hidden;
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 9px;
  font-style: normal;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestra-event-row {
  display: grid;
  grid-template-columns: auto 58px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 5px 7px;
}

.orchestra-event-row__time {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}

.orchestra-event-row__copy {
  display: grid;
  gap: 2px;
}

.orchestra-event-row__copy strong {
  color: var(--text-primary);
  font-size: 11px;
}

.orchestra-event-row__copy small {
  color: var(--text-muted);
  font-size: 9.5px;
}

.orchestra-mini-table--locks,
.orchestra-mini-table--failures {
  grid-auto-rows: minmax(31px, 1fr);
}

.orchestra-mini-row {
  display: grid;
  align-items: center;
  gap: 7px;
  min-height: 31px;
  padding: 4px 7px;
}

.orchestra-mini-table--locks .orchestra-mini-row {
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) 52px 58px;
}

.orchestra-mini-table--failures .orchestra-mini-row {
  grid-template-columns: 58px minmax(0, 0.85fr) minmax(0, 1fr) auto;
}

.orchestra-mini-row span {
  min-width: 0;
  color: var(--text-secondary);
  font-size: 10.5px;
}

.orchestra-mini-row em,
.orchestra-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  max-width: 84px;
  min-height: 19px;
  padding: 0 6px;
  overflow: hidden;
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 9.5px;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestra-badge--success {
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
}

.orchestra-badge--info {
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
}

.orchestra-badge--warning {
  background: color-mix(in srgb, var(--color-warning) 18%, transparent);
  color: var(--color-warning);
}

.orchestra-badge--danger {
  background: color-mix(in srgb, var(--color-danger) 16%, transparent);
  color: var(--color-danger);
}

.orchestra-quick-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  gap: 6px;
  flex: 1 1 auto;
  min-height: 0;
}

.orchestra-quick-grid button {
  align-items: flex-start;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  min-height: 0;
  padding: 5px 7px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
}

.orchestra-quick-grid button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.orchestra-quick-grid svg {
  color: var(--color-accent);
}

.orchestra-quick-grid span,
.orchestra-quick-grid small {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestra-quick-grid span {
  color: var(--text-primary);
  font-size: 10.5px;
  font-weight: 800;
  line-height: 1.1;
}

.orchestra-quick-grid small {
  color: var(--text-muted);
  font-size: 9px;
  line-height: 1.1;
}

@media (max-width: 1360px) {
  .orchestra-status-bar {
    align-items: stretch;
  }

  .orchestra-actions {
    width: 100%;
    justify-content: flex-start;
    margin-left: 0;
  }

  .orchestra-metric-strip {
    grid-template-columns: repeat(3, minmax(150px, 1fr));
  }

  .orchestra-dashboard,
  .orchestra-focus-grid {
    height: auto;
    min-height: 0;
    grid-template-columns: minmax(0, 1fr);
  }

  .orchestra-main-column,
  .orchestra-side-column {
    grid-template-rows: none;
  }

  .orchestra-side-column {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .orchestra-page {
    padding: 10px;
  }

  .orchestra-status-bar {
    min-height: 0;
    padding: 10px;
  }

  .orchestra-control-group {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    min-width: 0;
    width: 100%;
  }

  .orchestra-control {
    padding: 8px 10px;
    border-left: 0;
    border-top: 1px solid var(--border-subtle);
  }

  .orchestra-actions {
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .orchestra-metric-strip {
    display: flex;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .orchestra-metric {
    flex: 0 0 156px;
  }

  .orchestra-side-column,
  .orchestra-quick-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
