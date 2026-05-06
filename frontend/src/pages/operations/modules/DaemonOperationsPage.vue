<script setup lang="ts">
import {
  Activity,
  CircleGauge,
  Database,
  GitBranch,
  HeartPulse,
  KeyRound,
  Network,
  RefreshCcw,
  Search,
  ServerCog,
  ShieldAlert,
  Terminal,
  X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime } from "@/shared/i18n/formatters";
import type {
  OperationsDaemonInstanceDetail,
  OperationsDaemonLeaseDetail,
  OperationsDaemonProcessDetail,
  OperationsDaemonReadModel,
  OperationsTab,
  UiChartSection,
  UiKeyValueItem,
  UiLinkedEntity,
  UiMetricCard,
  UiRuntimeAction,
  UiTableRow,
  UiTableSection,
  UiTone,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  loadDaemonOperations,
  runDaemonServiceAction,
  type DaemonServiceActionKind,
} from "../api";

interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

type DataTableRow = UiTableRow | Record<string, unknown>;
type SelectedDetail = { type: "instance" | "lease" | "process"; id: string } | null;

const { t } = useI18n();
const metricIconById: Record<string, unknown> = {
  health: HeartPulse,
  service_sets: Database,
  services: ServerCog,
  instances: CircleGauge,
  processes: CircleGauge,
  leases: KeyRound,
  env_drift: ShieldAlert,
  events: Activity,
};
const fallbackTabs: OperationsTab[] = [
  { id: "instances", label: "Instances" },
  { id: "processes", label: "Process Sessions" },
  { id: "services", label: "Services" },
  { id: "service_sets", label: "Service Sets" },
  { id: "leases", label: "Leases" },
  { id: "dependencies", label: "Dependencies" },
  { id: "events", label: "Daemon Events" },
];
const knownTabIds = new Set(fallbackTabs.map((tab) => tab.id));
const selectableTabs = new Set(["instances", "leases", "processes", "services"]);
const daemonServiceActionById: Record<string, DaemonServiceActionKind> = {
  ensure_service: "ensure",
  healthcheck_service: "healthcheck",
  reconcile_service: "reconcile",
  stop_service: "stop",
};
const actionIconById: Record<string, unknown> = {
  ensure_service: ServerCog,
  healthcheck_service: HeartPulse,
  reconcile_service: RefreshCcw,
  stop_service: ShieldAlert,
};
const daemonTextKeys: Record<string, string> = {
  "Daemons": "operations.daemon.title",
  "观察 daemon service set、服务规格、进程实例、租约与运行事件的运维视图。": "operations.daemon.subtitle",
  "观察守护进程服务集、服务规格、进程实例、租约与运行事件的运维视图。": "operations.daemon.subtitle",
  "Daemon operator": "operations.daemon.role.operator",
  "Overall Health": "operations.daemon.metric.health",
  "Service Sets": "operations.daemon.metric.serviceSets",
  "Services": "operations.daemon.metric.services",
  "Instances": "operations.daemon.metric.instances",
  "Process Sessions": "operations.daemon.metric.processSessions",
  "Processes": "operations.daemon.metric.instances",
  "Leases": "operations.daemon.metric.leases",
  "Env Drift": "operations.daemon.metric.envDrift",
  "Daemon Events": "operations.daemon.metric.events",
  "configured daemon sets": "operations.daemon.delta.configuredSets",
  "instances with runtime env drift": "operations.daemon.delta.envDrift",
  "observed operations events": "operations.daemon.delta.observedEvents",
  "No process sessions observed.": "operations.daemon.empty.noProcesses",
  "No process output observed.": "operations.daemon.empty.noProcessOutput",
  "Daemon runtime state is queryable": "operations.daemon.delta.queryable",
  "Operator attention recommended": "operations.daemon.delta.attentionRecommended",
  "Operator action required": "operations.daemon.delta.actionRequired",
  "Process Health": "operations.daemon.section.processHealth",
  "State Changes / Drift": "operations.daemon.section.stateChanges",
  "Lease Health": "operations.daemon.section.leaseHealth",
  "Lease / Drain Indicators": "operations.daemon.section.leaseDrain",
  "Dependency Health": "operations.daemon.section.dependencyHealth",
  "Ensure Service": "operations.daemon.action.ensureService",
  "Healthcheck Service": "operations.daemon.action.healthcheckService",
  "Reconcile Service": "operations.daemon.action.reconcileService",
  "Stop Service": "operations.daemon.action.stopService",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "Error": "text.error",
  "healthy": "text.healthy",
  "warning": "text.warning",
  "error": "text.error",
  "Ready": "text.ready",
  "ready": "text.ready",
  "Failed": "status.failed",
  "failed": "status.failed",
  "Stopped": "text.stopped",
  "stopped": "text.stopped",
  "Starting": "text.starting",
  "starting": "text.starting",
  "Stopping": "text.stopping",
  "stopping": "text.stopping",
  "Degraded": "text.degraded",
  "degraded": "text.degraded",
  "Active": "text.active",
  "active": "text.active",
  "Running": "text.running",
  "running": "text.running",
  "Exited": "text.exited",
  "exited": "text.exited",
  "Killed": "text.killed",
  "killed": "text.killed",
  "Missing": "table.missing",
  "missing": "table.missing",
  "Bound": "text.bound",
  "Unbound": "text.unbound",
  "Missing Session": "text.missingSession",
  "Released": "text.released",
  "released": "text.released",
  "Expired": "text.expired",
  "expired": "text.expired",
  "Configured": "text.configured",
  "configured": "text.configured",
  "Desired Unmet": "operations.daemon.status.desiredUnmet",
  "Instance ID": "table.instanceId",
  "Process ID": "table.processId",
  "Session Key": "table.sessionKey",
  "Service Key": "table.serviceKey",
  "Status": "table.status",
  "PID": "table.pid",
  "Exit Code": "table.exitCode",
  "Binding": "table.binding",
  "Command": "table.command",
  "Working Directory": "table.workingDirectory",
  "Ended At": "table.endedAt",
  "Worker ID": "table.workerId",
  "Endpoint": "table.endpoint",
  "Started At": "table.startedAt",
  "Last Healthcheck At": "table.lastHealthcheckAt",
  "Drift Detected": "operations.daemon.kv.driftDetected",
  "Env Fingerprint": "operations.daemon.kv.envFingerprint",
  "Expected Fingerprint": "operations.daemon.kv.expectedFingerprint",
  "Actual Fingerprint": "operations.daemon.kv.actualFingerprint",
  "Env Keys": "operations.daemon.kv.envKeys",
  "Last Error": "table.lastError",
  "Display Name": "table.displayName",
  "Service Group": "table.serviceGroup",
  "Role": "table.role",
  "Managed By": "table.managedBy",
  "Transport": "table.transport",
  "Replica Mode": "operations.daemon.kv.replicaMode",
  "Desired": "table.desired",
  "Start Policy": "table.startPolicy",
  "Restart Policy": "table.restartPolicy",
  "Healthcheck Policy": "operations.daemon.kv.healthcheckPolicy",
  "Match Policy": "operations.daemon.kv.matchPolicy",
  "CLI Args": "operations.daemon.kv.cliArgs",
  "Lease ID": "table.leaseId",
  "Active Leases": "table.activeLeases",
  "Leased Services": "operations.daemon.kv.leasedServices",
  "Ready Leased Services": "operations.daemon.kv.readyLeasedServices",
  "Unmatched Leases": "operations.daemon.kv.unmatchedLeases",
  "Released History": "operations.daemon.kv.releasedHistory",
  "Orphaned Processes": "operations.daemon.kv.orphanedProcesses",
  "Owner Kind": "operations.daemon.kv.ownerKind",
  "Owner ID": "operations.daemon.kv.ownerId",
  "Acquired At": "table.acquiredAt",
  "Heartbeat At": "table.heartbeatAt",
  "Expires At": "table.expiresAt",
  "Environment": "table.environment",
  "Service": "operations.daemon.metric.services",
  "Metadata": "table.metadata",
  "Output": "text.output",
  "Stream": "table.stream",
  "Bytes": "table.bytes",
  "Preview": "table.preview",
  "Next Offset": "table.nextOffset",
  "Yes": "common.yes",
  "No": "common.no",
  "No records.": "table.noRecords",
};

const page = ref<OperationsDaemonReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedDetail = ref<SelectedDetail>(null);
const queryInput = ref("");
const submittedSearch = ref("");
const statusFilter = ref("all");
const serviceKeyFilter = ref("all");
const serviceGroupFilter = ref("all");
const refreshTimer = ref<number | null>(null);
const selectedServiceKey = ref<string | null>(null);
const actionBusy = ref<string | null>(null);
const actionNotice = ref<string | null>(null);

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const daemonActions = computed(() => {
  const actions = page.value?.quick_actions?.length ? page.value.quick_actions : page.value?.actions ?? [];
  return actions.filter((action) => action.id in daemonServiceActionById);
});
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "instances";
  return knownTabIds.has(candidate) ? candidate : "instances";
});
const mainTable = computed(() => {
  if (activeTab.value === "processes") return page.value?.processes ?? emptyTable("processes", "Process Sessions");
  if (activeTab.value === "services") return page.value?.services ?? emptyTable("services", "Services");
  if (activeTab.value === "service_sets") return page.value?.service_sets ?? emptyTable("service_sets", "Service Sets");
  if (activeTab.value === "leases") return page.value?.leases ?? emptyTable("leases", "Leases");
  if (activeTab.value === "dependencies") return page.value?.dependency_health ?? emptyTable("dependency_health", "Dependency Health");
  if (activeTab.value === "events") return page.value?.daemon_events ?? emptyTable("daemon_events", "Daemon Events");
  return page.value?.instances ?? emptyTable("instances", "Instances");
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
const serviceKeyOptions = computed(() => {
  const values = new Set<string>();
  for (const row of page.value?.services.rows ?? []) {
    const key = cellValueText(row.cells.service_key);
    if (key && key !== "-") values.add(key);
  }
  for (const row of page.value?.instances.rows ?? []) {
    const key = cellValueText(row.cells.service_key);
    if (key && key !== "-") values.add(key);
  }
  for (const row of page.value?.processes.rows ?? []) {
    const key = cellValueText(row.cells.service_key);
    if (key && key !== "-") values.add(key);
  }
  for (const row of page.value?.leases.rows ?? []) {
    const key = cellValueText(row.cells.service_key);
    if (key && key !== "-") values.add(key);
  }
  return [...values].sort();
});
const serviceGroupOptions = computed(() => {
  const values = new Set<string>();
  for (const row of page.value?.services.rows ?? []) {
    const group = cellValueText(row.cells.service_group);
    if (group && group !== "-") values.add(group);
  }
  for (const row of page.value?.dependency_health.rows ?? []) {
    const group = cellValueText(row.cells.service_group);
    if (group && group !== "-") values.add(group);
  }
  return [...values].sort();
});
const processHealth = computed(() => page.value?.process_health ?? emptyChart("process_health", "Process Health", "donut"));
const leaseHealth = computed(() => page.value?.lease_health ?? emptyChart("lease_health", "Lease Health", "donut"));
const stateSummary = computed(() => page.value?.restart_summary ?? emptyChart("restart_summary", "State Changes / Drift", "bar"));
const drainOverview = computed(() => page.value?.drain_overview ?? emptyKeyValue("drain_overview", "Lease / Drain Indicators"));
const dependencyTable = computed(() => page.value?.dependency_health ?? emptyTable("dependency_health", "Dependency Health"));
const eventsTable = computed(() => page.value?.daemon_events ?? emptyTable("daemon_events", "Daemon Events"));
const processSegments = computed(() => chartSegments(processHealth.value));
const leaseSegments = computed(() => chartSegments(leaseHealth.value));
const stateSegments = computed(() => chartSegments(stateSummary.value));
const selectedInstanceDetail = computed<OperationsDaemonInstanceDetail | null>(() => {
  if (selectedDetail.value?.type !== "instance") return null;
  return (page.value?.instance_details ?? []).find((item) => item.instance_id === selectedDetail.value?.id) ?? null;
});
const selectedLeaseDetail = computed<OperationsDaemonLeaseDetail | null>(() => {
  if (selectedDetail.value?.type !== "lease") return null;
  return (page.value?.lease_details ?? []).find((item) => item.lease_id === selectedDetail.value?.id) ?? null;
});
const selectedProcessDetail = computed<OperationsDaemonProcessDetail | null>(() => {
  if (selectedDetail.value?.type !== "process") return null;
  return (page.value?.process_details ?? []).find((item) => item.process_id === selectedDetail.value?.id) ?? null;
});
const selectedActionServiceKey = computed(() => (
  normalizeServiceKey(serviceKeyFilter.value)
  ?? selectedServiceKey.value
  ?? detailServiceKey(selectedInstanceDetail.value)
  ?? detailServiceKey(selectedLeaseDetail.value)
  ?? detailServiceKey(selectedProcessDetail.value)
));
const drawerOpen = computed(() => Boolean(selectedInstanceDetail.value || selectedLeaseDetail.value || selectedProcessDetail.value));

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
  selectedDetail.value = null;
}

function selectRow(row: DataTableRow) {
  if (!selectableTabs.has(activeTab.value)) return;
  const serviceKey = resolveServiceKey(row);
  if (serviceKey) selectedServiceKey.value = serviceKey;
  if (activeTab.value === "services") {
    selectedDetail.value = null;
    return;
  }
  const id = rowId(row);
  if (!id) return;
  if (activeTab.value === "leases") {
    selectedDetail.value = { type: "lease", id };
    return;
  }
  if (activeTab.value === "processes") {
    selectedDetail.value = { type: "process", id };
    return;
  }
  selectedDetail.value = { type: "instance", id };
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

function resolveServiceKey(row: DataTableRow): string | null {
  if (isUiTableRow(row)) {
    return normalizeServiceKey(row.cells.service_key)
      ?? normalizeServiceKey(row.cells.key)
      ?? (activeTab.value === "services" ? normalizeServiceKey(row.id) : null);
  }
  return normalizeServiceKey(row.service_key)
    ?? normalizeServiceKey(row.key)
    ?? (activeTab.value === "services" ? normalizeServiceKey(rowId(row)) : null);
}

function normalizeServiceKey(value: unknown): string | null {
  const normalized = typeof value === "object" && value !== null && "text" in value
    ? String((value as { text: string }).text).trim()
    : String(value ?? "").trim();
  if (!normalized || normalized === "-" || normalized.toLowerCase() === "all") return null;
  return normalized;
}

function detailServiceKey(
  detail: OperationsDaemonInstanceDetail | OperationsDaemonLeaseDetail | OperationsDaemonProcessDetail | null,
): string | null {
  const serviceItem = detail?.summary.find((item) => item.label === "Service Key");
  return normalizeServiceKey(serviceItem?.value);
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
    label: daemonText(segment.label),
    value: Number(segment.value || 0),
    tone: segment.tone,
    pct: total > 0 ? Math.round((Number(segment.value || 0) / total) * 100) : 0,
  }));
}

function metricIcon(metric: UiMetricCard, index: number) {
  return metricIconById[metric.id] ?? [HeartPulse, ServerCog, CircleGauge, KeyRound, ShieldAlert, Activity, Network][index % 7];
}

function metricLabel(metric: UiMetricCard) {
  return daemonText(metric.label);
}

function metricDelta(metric: UiMetricCard) {
  return daemonText(metric.delta ?? "");
}

function tabLabel(tab: OperationsTab) {
  return daemonText(tab.label);
}

function sectionTitle(section: UiTableSection | UiChartSection | { title: string }) {
  return daemonText(section.title);
}

function emptyState(section: UiTableSection) {
  return daemonText(section.empty_state ?? "No records.");
}

function actionLabel(action: UiRuntimeAction) {
  return daemonText(action.label);
}

function actionVariant(action: UiRuntimeAction): "secondary" | "danger" {
  return action.risk === "dangerous" ? "danger" : "secondary";
}

function actionIcon(action: UiRuntimeAction) {
  return actionIconById[action.id] ?? ServerCog;
}

function detailItems(items: UiKeyValueItem[]) {
  return items.map((item) => ({
    ...item,
    label: daemonText(item.label),
    value: daemonText(item.value),
  }));
}

function linkedRoute(link: UiLinkedEntity): string {
  return link.route || "/operations";
}

function detailPayload(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function daemonText(value: string | null | undefined): string {
  if (!value) return "";
  const desiredUnmet = value.match(/^(\d+) desired unmet$/);
  if (desiredUnmet) {
    return t("operations.daemon.delta.desiredUnmetCount", { count: desiredUnmet[1] });
  }
  const processState = value.match(/^(\d+) ready \/ (\d+) non-ready$/);
  if (processState) {
    return t("operations.daemon.delta.processState", { ready: processState[1], nonReady: processState[2] });
  }
  const leaseState = value.match(/^(\d+) active \/ (\d+) expired$/);
  if (leaseState) {
    return t("operations.daemon.delta.leaseState", { active: leaseState[1], expired: leaseState[2] });
  }
  const processSessionState = value.match(/^(\d+) running \/ (\d+) finished$/);
  if (processSessionState) {
    return t("operations.daemon.delta.processSessionState", { running: processSessionState[1], finished: processSessionState[2] });
  }
  const processMissingState = value.match(/^(\d+) running \/ (\d+) missing$/);
  if (processMissingState) {
    return t("operations.daemon.delta.processMissingState", { running: processMissingState[1], missing: processMissingState[2] });
  }
  const key = daemonTextKeys[value];
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

function emptyKeyValue(id: string, title: string) {
  return {
    id,
    title,
    items: [],
  };
}

function submitSearch() {
  submittedSearch.value = queryInput.value.trim();
  selectedDetail.value = null;
  selectedServiceKey.value = normalizeServiceKey(serviceKeyFilter.value) ?? selectedServiceKey.value;
  void refreshPage();
}

function resetSearch() {
  queryInput.value = "";
  submittedSearch.value = "";
  statusFilter.value = "all";
  serviceKeyFilter.value = "all";
  serviceGroupFilter.value = "all";
  selectedDetail.value = null;
  selectedServiceKey.value = null;
  void refreshPage();
}

function canRunDaemonAction(action: UiRuntimeAction) {
  return action.allowed && !loading.value && actionBusy.value === null;
}

function resolveActionServiceKey(): string | null {
  const current = selectedActionServiceKey.value;
  if (current) return current;
  if (typeof window === "undefined") return null;
  const value = window.prompt(t("operations.daemon.action.serviceKeyPrompt"));
  const serviceKey = normalizeServiceKey(value);
  if (serviceKey) {
    selectedServiceKey.value = serviceKey;
    return serviceKey;
  }
  return null;
}

async function runDaemonAction(action: UiRuntimeAction) {
  if (!canRunDaemonAction(action)) return;
  const actionKind = daemonServiceActionById[action.id];
  if (!actionKind) {
    loadError.value = t("operations.daemon.action.unsupportedAction");
    return;
  }
  const serviceKey = resolveActionServiceKey();
  if (!serviceKey) return;
  const label = actionLabel(action);
  let confirmation: string | null = null;
  let riskAcknowledged = false;
  if (action.requires_confirmation) {
    confirmation = t("operations.daemon.action.confirm", {
      action: label,
      serviceKey,
    });
    const confirmed = window.confirm(confirmation);
    if (!confirmed) return;
    riskAcknowledged = confirmed;
  }
  const promptReason = action.reason_required
    ? window.prompt(t("operations.daemon.action.reasonPrompt", {
      action: label,
      serviceKey,
    }))?.trim()
    : null;
  if (action.reason_required && !promptReason) return;
  const reason = promptReason
    ?? `Operations daemon action ${actionKind} for ${serviceKey}`;

  actionBusy.value = action.id;
  actionNotice.value = null;
  loadError.value = null;
  try {
    const result = await runDaemonServiceAction(
      serviceKey,
      actionKind,
      reason,
      confirmation
        ? {
          confirmation,
          risk_acknowledged: riskAcknowledged,
          metadata: {
            confirmation_prompt: confirmation,
          },
        }
        : {},
    );
    selectedServiceKey.value = serviceKey;
    actionNotice.value = t("operations.daemon.action.notice", {
      action: label,
      serviceKey,
      count: result.length,
    });
    await refreshPage();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadDaemonOperations({
      status: statusFilter.value,
      service_key: serviceKeyFilter.value,
      service_group: serviceGroupFilter.value,
      search: submittedSearch.value,
      limit: 80,
    });
    page.value = loaded.page;
    loadError.value = null;
    if (selectedDetail.value?.type === "instance" && !loaded.page.instance_details.some((item) => item.instance_id === selectedDetail.value?.id)) {
      selectedDetail.value = null;
    }
    if (selectedDetail.value?.type === "lease" && !loaded.page.lease_details.some((item) => item.lease_id === selectedDetail.value?.id)) {
      selectedDetail.value = null;
    }
    if (selectedDetail.value?.type === "process" && !loaded.page.process_details.some((item) => item.process_id === selectedDetail.value?.id)) {
      selectedDetail.value = null;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
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
  <main class="operations-module-console daemon-console scroll-area" :class="{ 'has-drawer': drawerOpen }">
    <header class="daemon-header">
      <div>
        <h2>{{ daemonText(page?.title ?? "Daemons") }} <span>{{ page?.health ? daemonText(page.health) : "-" }}</span></h2>
        <p>{{ daemonText(page?.subtitle ?? "观察守护进程服务集、服务规格、进程实例、租约与运行事件的运维视图。") }}</p>
      </div>
      <div class="daemon-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton class="role-badge" size="sm" variant="secondary">
          <ShieldAlert :size="13" /> {{ t("operations.currentRoleLabel") }}: {{ daemonText(page?.role.label ?? "Daemon operator") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="daemon-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>
    <div v-if="actionNotice" class="daemon-alert daemon-alert--success">
      <StatusDot tone="success" />
      <span>{{ actionNotice }}</span>
    </div>

    <section v-if="daemonActions.length" class="daemon-action-strip">
      <div class="daemon-action-target">
        <span>{{ t("operations.daemon.action.targetService") }}</span>
        <strong>{{ selectedActionServiceKey ?? t("operations.daemon.action.noServiceSelected") }}</strong>
      </div>
      <UiButton
        v-for="action in daemonActions"
        :key="action.id"
        size="sm"
        :variant="actionVariant(action)"
        :disabled="!canRunDaemonAction(action)"
        :title="action.endpoint ?? ''"
        @click="runDaemonAction(action)"
      >
        <component :is="actionIcon(action)" :class="{ 'motion-spin': actionBusy === action.id }" :size="13" />
        {{ actionLabel(action) }}
      </UiButton>
    </section>

    <section class="daemon-metrics">
      <template v-if="displayMetrics.length">
        <article v-for="(metric, index) in displayMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
          <span class="metric-icon"><component :is="metricIcon(metric, index)" :size="22" /></span>
          <span class="metric-copy">
            <em>{{ metricLabel(metric) }}</em>
            <strong>{{ daemonText(metric.value) }}</strong>
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

    <section class="daemon-status-strip">
      <article class="health-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(processHealth) }}</h3>
        </div>
        <div v-if="processSegments.length" class="chart-card-body">
          <div class="donut-visual">
            <strong>{{ processHealth.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl class="segment-list">
            <div v-for="segment in processSegments.slice(0, 6)" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }} <span>{{ segment.pct }}%</span></dd>
            </div>
          </dl>
        </div>
        <p v-if="!processSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="drain-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(drainOverview) }}</h3>
        </div>
        <dl class="kv-grid">
          <div v-for="item in detailItems(drainOverview.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
        <p v-if="!detailItems(drainOverview.items).length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="events-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(eventsTable) }}</h3>
          <a href="/operations/daemon?tab=events" @click.prevent="selectTab('events')">{{ t("common.viewAll") }}</a>
        </div>
        <DataTable v-if="eventsTable.rows.length" :columns="eventsTable.columns" :rows="eventsTable.rows" section-id="daemon-events-brief" :page-size="3" />
        <p v-if="!eventsTable.rows.length" class="panel-empty">{{ emptyState(eventsTable) }}</p>
      </article>
    </section>

    <nav class="daemon-tabs">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: tab.id === activeTab }" type="button" @click="selectTab(tab.id)">
        {{ tabLabel(tab) }}<span v-if="tab.count != null">{{ tab.count }}</span>
      </button>
    </nav>

    <section class="daemon-main-grid">
      <article class="daemon-table-panel">
        <div class="panel-heading panel-heading--table">
          <h3>{{ sectionTitle(mainTable) }} <span>{{ mainTable.total ?? mainTable.rows.length }}</span></h3>
          <form class="table-controls" @submit.prevent="submitSearch">
            <label class="table-search">
              <Search :size="13" />
              <input v-model.trim="queryInput" type="search" :placeholder="t('operations.daemon.searchPlaceholder')" />
            </label>
            <label class="status-filter">
              <span>{{ t("table.status") }}</span>
              <select v-model="statusFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option value="ready">{{ t("text.ready") }}</option>
                <option value="running">{{ t("text.running") }}</option>
                <option value="active">{{ t("text.active") }}</option>
                <option value="degraded">{{ t("text.degraded") }}</option>
                <option value="starting">{{ t("text.starting") }}</option>
                <option value="stopping">{{ t("text.stopping") }}</option>
                <option value="stopped">{{ t("text.stopped") }}</option>
                <option value="failed">{{ t("status.failed") }}</option>
                <option value="exited">{{ t("text.exited") }}</option>
                <option value="killed">{{ t("text.killed") }}</option>
                <option value="expired">{{ t("text.expired") }}</option>
              </select>
            </label>
            <label class="status-filter">
              <span>{{ t("table.serviceKey") }}</span>
              <select v-model="serviceKeyFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="serviceKey in serviceKeyOptions" :key="serviceKey" :value="serviceKey">
                  {{ serviceKey }}
                </option>
              </select>
            </label>
            <label class="status-filter">
              <span>{{ t("table.serviceGroup") }}</span>
              <select v-model="serviceGroupFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="serviceGroup in serviceGroupOptions" :key="serviceGroup" :value="serviceGroup">
                  {{ serviceGroup }}
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
          section-id="daemon-main-table"
          :page-size="12"
          :clickable-rows="selectableTabs.has(activeTab)"
          @row-click="selectRow"
        />
        <p v-else class="table-empty">{{ emptyState(mainTable) }}</p>
      </article>

      <aside class="daemon-side-panel">
        <article class="lease-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(leaseHealth) }}</h3>
            <a href="/operations/daemon?tab=leases" @click.prevent="selectTab('leases')">{{ t("common.viewAll") }}</a>
          </div>
          <div v-if="leaseSegments.length" class="side-donut">
            <strong>{{ leaseHealth.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl v-if="leaseSegments.length" class="segment-list compact">
            <div v-for="segment in leaseSegments" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }}</dd>
            </div>
          </dl>
          <p v-if="!leaseSegments.length" class="panel-empty compact-empty">{{ t("table.noRecords") }}</p>
        </article>

        <article class="state-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(stateSummary) }}</h3>
          </div>
          <dl class="bar-list">
            <div v-for="segment in stateSegments" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
            </div>
          </dl>
          <p v-if="!stateSegments.length" class="panel-empty compact-empty">{{ t("table.noRecords") }}</p>
        </article>

        <article class="dependency-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(dependencyTable) }}</h3>
            <a href="/operations/daemon?tab=dependencies" @click.prevent="selectTab('dependencies')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable v-if="dependencyTable.rows.length" :columns="dependencyTable.columns" :rows="dependencyTable.rows" section-id="daemon-dependencies-side" :page-size="2" />
          <p v-if="!dependencyTable.rows.length" class="panel-empty compact-empty">{{ emptyState(dependencyTable) }}</p>
        </article>

        <article class="links-panel">
          <h3>{{ t("operations.linksToOperations") }}</h3>
          <RouterLink v-for="link in page?.links_to_operations ?? []" :key="link.id" :to="linkedRoute(link)">
            <Terminal :size="15" />
            <span>{{ link.label ?? link.id }}</span>
          </RouterLink>
          <p v-if="!(page?.links_to_operations ?? []).length" class="panel-empty compact-empty">{{ t("table.noRecords") }}</p>
        </article>
      </aside>
    </section>

    <aside v-if="selectedInstanceDetail" class="daemon-drawer">
      <header>
        <div>
          <span>{{ t("operations.daemon.drawer.instance") }}</span>
          <h3>{{ selectedInstanceDetail.title }}</h3>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedDetail = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.daemon.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedInstanceDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedInstanceDetail.environment) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedInstanceDetail.environment.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedInstanceDetail.service) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedInstanceDetail.service.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedInstanceDetail.leases) }}</h4>
        <DataTable :columns="selectedInstanceDetail.leases.columns" :rows="selectedInstanceDetail.leases.rows" section-id="daemon-detail-leases" :page-size="5" />
        <p v-if="!selectedInstanceDetail.leases.rows.length" class="panel-empty compact-empty">{{ emptyState(selectedInstanceDetail.leases) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedInstanceDetail.events) }}</h4>
        <DataTable :columns="selectedInstanceDetail.events.columns" :rows="selectedInstanceDetail.events.rows" section-id="daemon-detail-events" :page-size="5" />
        <p v-if="!selectedInstanceDetail.events.rows.length" class="panel-empty compact-empty">{{ emptyState(selectedInstanceDetail.events) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.daemon.drawer.raw") }}</h4>
        <pre>{{ detailPayload(selectedInstanceDetail.raw_payload) }}</pre>
      </section>
    </aside>

    <aside v-else-if="selectedLeaseDetail" class="daemon-drawer">
      <header>
        <div>
          <span>{{ t("operations.daemon.drawer.lease") }}</span>
          <h3>{{ selectedLeaseDetail.title }}</h3>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedDetail = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.daemon.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedLeaseDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedLeaseDetail.metadata) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedLeaseDetail.metadata.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedLeaseDetail.events) }}</h4>
        <DataTable :columns="selectedLeaseDetail.events.columns" :rows="selectedLeaseDetail.events.rows" section-id="daemon-lease-events" :page-size="5" />
        <p v-if="!selectedLeaseDetail.events.rows.length" class="panel-empty compact-empty">{{ emptyState(selectedLeaseDetail.events) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.daemon.drawer.raw") }}</h4>
        <pre>{{ detailPayload(selectedLeaseDetail.raw_payload) }}</pre>
      </section>
    </aside>

    <aside v-else-if="selectedProcessDetail" class="daemon-drawer">
      <header>
        <div>
          <span>{{ t("operations.daemon.drawer.process") }}</span>
          <h3>{{ selectedProcessDetail.title }}</h3>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedDetail = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.daemon.drawer.summary") }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedProcessDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedProcessDetail.metadata) }}</h4>
        <dl class="detail-grid">
          <div v-for="item in detailItems(selectedProcessDetail.metadata.items)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ sectionTitle(selectedProcessDetail.output) }}</h4>
        <DataTable :columns="selectedProcessDetail.output.columns" :rows="selectedProcessDetail.output.rows" section-id="daemon-process-output" :page-size="5" />
        <p v-if="!selectedProcessDetail.output.rows.length" class="panel-empty compact-empty">{{ emptyState(selectedProcessDetail.output) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.daemon.drawer.raw") }}</h4>
        <pre>{{ detailPayload(selectedProcessDetail.raw_payload) }}</pre>
      </section>
    </aside>
  </main>
</template>

<style scoped>
.daemon-console {
  height: 100%;
  overflow: auto;
  padding: 8px 12px 12px;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
  scrollbar-gutter: stable;
}

.daemon-header,
.daemon-header__ops,
.daemon-metrics,
.daemon-tabs,
.panel-heading,
.chart-card-body,
.daemon-alert,
.daemon-action-strip,
.daemon-action-target,
.auto-toggle,
.table-controls,
.table-search,
.links-panel a {
  display: flex;
  align-items: center;
}

.daemon-header {
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

.daemon-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.daemon-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.daemon-header__ops strong {
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

.daemon-alert {
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

.daemon-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 34%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 9%, var(--surface-panel));
}

.daemon-action-strip {
  flex-wrap: wrap;
  gap: 6px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 4px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.daemon-action-target {
  min-width: min(260px, 100%);
  gap: 8px;
  min-height: 30px;
  padding: 0 10px;
  border-right: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.daemon-action-target strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.daemon-metrics {
  display: grid;
  grid-template-columns: repeat(8, minmax(96px, 1fr));
  gap: 6px;
}

.metric,
.daemon-status-strip > article,
.daemon-table-panel,
.daemon-side-panel > article {
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

.daemon-status-strip {
  display: grid;
  grid-template-columns: minmax(220px, 0.64fr) minmax(340px, 1.06fr) minmax(360px, 1.22fr);
  gap: 6px;
  align-items: start;
  margin-top: 6px;
}

.daemon-status-strip > article,
.daemon-side-panel > article,
.daemon-table-panel {
  min-width: 0;
  padding: 8px;
}

.daemon-status-strip > article {
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
  text-decoration: none;
}

.panel-heading h3 span {
  color: var(--text-muted);
}

.chart-card-body {
  gap: 9px;
  min-height: 76px;
}

.donut-visual,
.side-donut {
  display: grid;
  place-items: center;
  align-content: center;
  border: 10px solid color-mix(in srgb, var(--color-blue) 46%, var(--border-subtle));
  border-radius: 50%;
}

.donut-visual {
  flex: 0 0 76px;
  width: 76px;
  height: 76px;
}

.side-donut {
  width: 76px;
  height: 76px;
  margin: 0 auto 8px;
}

.donut-visual strong,
.side-donut strong {
  font-size: 20px;
  line-height: 1;
}

.donut-visual span,
.side-donut span {
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

.segment-list.compact dd {
  display: block;
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

.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(86px, 1fr));
  gap: 6px;
}

.kv-grid div {
  min-width: 0;
  min-height: 40px;
  padding: 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.kv-grid dt {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kv-grid dd {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 800;
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
  min-height: 64px;
}

.daemon-tabs {
  gap: 8px;
  min-height: 29px;
  margin-top: 6px;
  padding: 0;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  border-radius: 0;
  overflow-x: auto;
}

.daemon-tabs button {
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

.daemon-tabs button.active {
  background: var(--surface-panel-soft);
  color: var(--text-primary);
}

.daemon-tabs span {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 99px;
  background: color-mix(in srgb, var(--color-blue) 16%, transparent);
  color: var(--color-blue);
  font-size: 10px;
  text-align: center;
}

.daemon-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 6px;
  margin-top: 6px;
  align-items: start;
}

.daemon-table-panel {
  display: flex;
  flex-direction: column;
  min-height: clamp(330px, calc(100dvh - var(--shell-topbar-height) - 440px), 500px);
}

.daemon-table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.panel-heading--table {
  align-items: flex-start;
  margin-bottom: 10px;
}

.panel-heading--table h3 {
  flex: 0 0 auto;
}

.table-controls {
  flex: 1;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
  min-width: 0;
}

.table-search {
  gap: 7px;
  width: min(280px, 28vw);
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
}

.status-filter span {
  flex: 0 0 auto;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 600;
}

.status-filter select {
  max-width: 126px;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
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

.daemon-side-panel {
  display: grid;
  gap: 6px;
}

.lease-panel,
.state-panel,
.dependency-panel,
.links-panel {
  min-height: 118px;
  overflow: visible;
}

.links-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  align-content: start;
}

.links-panel h3,
.links-panel .panel-empty {
  grid-column: 1 / -1;
}

.links-panel a {
  gap: 6px;
  min-height: 26px;
  padding: 0 7px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  font-size: 11px;
  text-decoration: none;
}

.links-panel a span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.daemon-drawer {
  position: fixed;
  top: calc(var(--shell-topbar-height, 50px) + 16px);
  right: 20px;
  bottom: 20px;
  z-index: 30;
  width: min(460px, calc(100vw - 36px));
  overflow: auto;
  padding: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 96%, var(--surface-page));
  box-shadow: var(--shadow-floating);
}

.daemon-drawer > header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.daemon-drawer > header span {
  color: var(--text-muted);
  font-size: 11px;
  text-transform: uppercase;
}

.daemon-drawer > header h3 {
  margin-top: 3px;
  word-break: break-word;
}

.daemon-drawer > header button {
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

.motion-spin {
  animation: daemon-spin 0.95s linear infinite;
}

@keyframes daemon-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1280px) {
  .daemon-metrics {
    grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  }

  .daemon-status-strip,
  .daemon-main-grid {
    grid-template-columns: 1fr;
  }

  .daemon-side-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .daemon-drawer {
    top: 70px;
    right: 12px;
    bottom: 12px;
    width: min(420px, calc(100vw - 24px));
  }
}

@media (max-width: 760px) {
  .daemon-console {
    padding: 8px 10px 10px;
  }

  .daemon-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .daemon-header__ops {
    justify-content: flex-start;
  }

  .daemon-metrics,
  .daemon-status-strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .metric {
    flex: 0 0 150px;
  }

  .daemon-status-strip > article {
    flex: 0 0 286px;
  }

  .daemon-side-panel {
    grid-template-columns: 1fr;
  }

  .kv-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .daemon-drawer {
    width: min(420px, calc(100vw - 24px));
  }

  .panel-heading--table {
    align-items: stretch;
    flex-direction: column;
  }

  .table-controls {
    justify-content: flex-start;
  }

  .table-search {
    width: 100%;
  }

  .status-filter {
    flex: 1 1 150px;
  }

  .daemon-action-target {
    flex: 1 1 100%;
    border-right: 0;
  }
}
</style>
