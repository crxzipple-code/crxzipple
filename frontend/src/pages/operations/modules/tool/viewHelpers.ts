import { buildApiUrl } from "@/shared/api/client";
import { formatLocalTime } from "@/shared/i18n/formatters";
import type {
  OperationsTab,
  UiChartSection,
  UiMetricCard,
  UiTableRow,
  UiTableSection,
  UiTone,
} from "@/shared/runtime/types";
import { titleCaseDynamicValue } from "../../mapping";

export interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

export interface ToolLifecycleEventCardView {
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

export interface ToolArtifactPreviewItem {
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

export interface ToolDashboardMetric {
  id: string;
  label: string;
  value: string;
  helper: string;
  tone: UiTone;
  icon: unknown;
  fillPct: number;
}

export interface ToolInfoItem {
  id: string;
  label: string;
  value: string;
  tone?: UiTone;
}

export interface ToolProviderHealthItem {
  id: string;
  name: string;
  state: string;
  latency: string;
  tone: UiTone;
}

export interface ToolFailureSummaryItem {
  id: string;
  label: string;
  count: number;
  pct: number;
  tone: UiTone;
}

export type ToolStatusFilter = "all" | "active" | "running" | "waiting" | "failed" | "long_running" | "succeeded" | "cancelled";
export type ToolTimeFilter = "all" | "24h";
export type ToolModeFilter = "all" | "inline" | "background";
export type ToolStrategyFilter = "all" | "async" | "thread" | "process";
export type ToolEnvironmentFilter = "all" | "local" | "sandbox" | "remote";
export type ToolTernaryFilter = "all" | "yes" | "no";

export const toolRunPageSize = 7;
export const lifecycleEventPageSize = 5;

export const knownToolTabIds = new Set([
  "runs",
  "sources",
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

export const knownToolRunFilters = new Set<ToolStatusFilter>([
  "all",
  "active",
  "running",
  "waiting",
  "failed",
  "long_running",
  "succeeded",
  "cancelled",
]);

export const knownToolModeFilters = new Set<ToolModeFilter>([
  "all",
  "inline",
  "background",
]);

export const knownToolStrategyFilters = new Set<ToolStrategyFilter>([
  "all",
  "async",
  "thread",
  "process",
]);

export const knownToolEnvironmentFilters = new Set<ToolEnvironmentFilter>([
  "all",
  "local",
  "sandbox",
  "remote",
]);

export const knownToolTernaryFilters = new Set<ToolTernaryFilter>([
  "all",
  "yes",
  "no",
]);

export const fallbackTabs: OperationsTab[] = [
  { id: "runs", label: "Tool Runs" },
  { id: "sources", label: "Sources" },
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

export const toolTextKeys: Record<string, string> = {
  "Tool Runtime": "operations.tool.title",
  "Tool Runs": "operations.tool.tab.runs",
  "Sources": "operations.tool.tab.sources",
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
  "Source Health": "operations.tool.section.sourceHealth",
  "Discovery Failures": "operations.tool.section.discoveryFailures",
  "Function Catalog Risks": "operations.tool.section.functionCatalogRisks",
  "Provider Backend Health": "operations.tool.section.providerBackendHealth",
  "CLI Process Health": "operations.tool.section.cliProcessHealth",
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
  "No access or runtime readiness risks detected.": "operations.tool.empty.noRisk",
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
  "No Tool sources are registered.": "operations.tool.empty.noSources",
  "No Tool discovery failures recorded.": "operations.tool.empty.noDiscoveryFailures",
  "No stale, deprecated, disabled, or deleted functions.": "operations.tool.empty.noFunctionRisks",
  "No provider backend sources are registered.": "operations.tool.empty.noProviderBackendSources",
  "No CLI sources are registered.": "operations.tool.empty.noCliSources",
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

export const toolEventTextKeys: Record<string, string> = {
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

export function emptyTable(id: string, title: string): UiTableSection {
  return {
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  };
}

export function chartTotal(section: UiChartSection | null | undefined): number {
  const raw = typeof section?.total === "number" ? section.total : Number(section?.total ?? 0);
  if (Number.isFinite(raw) && raw > 0) return raw;
  return section?.segments?.reduce((sum, segment) => sum + segment.value, 0) ?? 0;
}

export function chartSegments(section: UiChartSection | null | undefined): ChartSegmentView[] {
  const total = chartTotal(section);
  return (section?.segments ?? []).map((segment) => ({
    ...segment,
    pct: total ? Math.round((segment.value / total) * 100) : 0,
  }));
}

export function fallbackMetric(id: string): UiMetricCard {
  return {
    id,
    label: id,
    value: "0",
    delta: "",
    tone: "neutral",
  };
}

export function numberCell(row: UiTableRow, key: string): number {
  const value = Number(cellText(row, key).replace(/[^\d.-]/g, ""));
  return Number.isFinite(value) ? value : 0;
}

export function workerLoadLimit(value: string): number {
  const match = value.match(/\/\s*(\d+)/);
  return match ? Number(match[1]) : 0;
}

export function ratioPct(value: number, total: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
}

export function durationPct(value: number | null | undefined, maxValue: number | null | undefined): number {
  if (value == null || maxValue == null || maxValue <= 0) return 0;
  return ratioPct(value, maxValue);
}

export function durationSecondsFromLabel(value: string): number | null {
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

export function formatDurationSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  if (value >= 3600) return `${Math.floor(value / 3600)}h ${Math.round((value % 3600) / 60)}m`;
  if (value >= 60) return `${Math.floor(value / 60)}m ${value % 60}s`;
  return `${value}s`;
}

export function donutGradient(segments: ChartSegmentView[]): string {
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

export function toneColor(tone: UiTone): string {
  const colors: Record<UiTone, string> = {
    success: "var(--color-success)",
    info: "var(--color-blue)",
    warning: "var(--color-warning)",
    danger: "var(--color-danger)",
    neutral: "var(--color-gray)",
  };
  return colors[tone] ?? colors.neutral;
}

export function cellText(row: UiTableRow, key: string): string {
  const value = row.cells[key];
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return value.text;
  return String(value);
}

export function cellRouteValue(row: UiTableRow, key: string): string | null {
  const value = row.cells[key];
  const route = value && typeof value === "object" ? value.route : value;
  if (typeof route !== "string" || route === "-") return null;
  return route.replace(/^\/ui(?=\/)/, "");
}

export function artifactPreviewItem(row: UiTableRow): ToolArtifactPreviewItem {
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

export function artifactAssetUrl(route: string | null): string | null {
  if (!route) return null;
  if (/^https?:\/\//.test(route)) return route;
  return buildApiUrl(route.startsWith("/") ? route : `/${route}`);
}

export function rowRunId(row: UiTableRow): string {
  const runId = cellText(row, "run_id");
  return runId === "-" ? row.id : runId;
}

export function rowWorkerId(row: UiTableRow): string {
  const workerId = cellText(row, "worker");
  return workerId === "-" ? row.id : workerId;
}

export function linkCell(text: string, route: string | null) {
  return route ? { text, route } : text;
}

export function splitEventDetails(value: string): string[] {
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

export function compactToolLabel(value: string): string {
  return value.replace(/\s+\([^)]+\)$/, "");
}

export function titleLabel(value: string): string {
  return titleCaseDynamicValue(value, value);
}

export function compactEntityId(value: string): string {
  if (!value || value === "-") return "-";
  if (value.length <= 16) return value;
  return `${value.slice(0, 7)}...${value.slice(-5)}`;
}

export function rowStatus(row: UiTableRow): string {
  return String(row.status ?? cellText(row, "status")).trim().toLowerCase().replace(/[\s-]+/g, "_");
}

export function isFailureStatus(status: string): boolean {
  return ["failed", "timed_out", "timeout", "cancelled", "error"].includes(status);
}

export function canCancelToolRun(row: UiTableRow): boolean {
  const actions = cellText(row, "actions").toLowerCase();
  const status = rowStatus(row);
  return actions.includes("cancel") && !["succeeded", "failed", "cancelled", "timed_out"].includes(status);
}

export function canRetryToolRun(row: UiTableRow): boolean {
  return cellText(row, "actions").toLowerCase().includes("retry");
}

export function isUiTableRow(row: unknown): row is UiTableRow {
  return Boolean(row && typeof row === "object" && "cells" in row);
}

export function formatPayload(payload: unknown): string {
  if (payload === null || payload === undefined || payload === "") return "-";
  if (typeof payload === "string") return payload;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

export function hasPayload(payload: unknown): boolean {
  if (payload === null || payload === undefined) return false;
  if (typeof payload === "string") return payload.trim().length > 0;
  if (Array.isArray(payload)) return payload.length > 0;
  if (typeof payload === "object") return Object.keys(payload).length > 0;
  return true;
}

export function isEnumLikeValue(value: string): boolean {
  return /^[a-z][a-z0-9_-]+$/.test(value) || /^[A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+)+$/.test(value);
}
