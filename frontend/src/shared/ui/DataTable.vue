<script setup lang="ts">
import { Copy, ExternalLink, MoreVertical, Pencil } from "lucide-vue-next";
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { formatLocalTime, formatRawKeyLabel, looksLikeRawKey } from "@/shared/i18n/formatters";
import { useI18n } from "@/shared/i18n";
import type { UiTableCellValue, UiTableColumn, UiTableRow } from "@/shared/runtime/types";

type LegacyRow = Record<string, string | number | null>;
type DataColumn = string | UiTableColumn;
type DataRow = LegacyRow | UiTableRow;

const props = defineProps<{
  columns: DataColumn[];
  rows: DataRow[];
  sectionId?: string;
  pageSize?: number;
  clickableRows?: boolean;
  selectedRowId?: string | null;
  allowRawKeys?: boolean;
}>();

const emit = defineEmits<{
  (event: "row-click", row: DataRow): void;
}>();

const { locale, t } = useI18n();
const currentPage = ref(1);

const normalizedColumns = computed(() =>
  props.columns.map((column) =>
    typeof column === "string"
      ? { key: column, label: localizeText(column) }
      : { ...column, label: localizeText(column.label) },
  ),
);

const normalizedPageSize = computed(() => {
  if (!props.pageSize || props.pageSize <= 0) return null;
  return Math.floor(props.pageSize);
});

const totalRows = computed(() => props.rows.length);
const totalPages = computed(() => {
  const size = normalizedPageSize.value;
  return size ? Math.max(1, Math.ceil(totalRows.value / size)) : 1;
});

const displayedRows = computed(() => {
  const size = normalizedPageSize.value;
  if (!size) return props.rows;
  const start = (currentPage.value - 1) * size;
  return props.rows.slice(start, start + size);
});

const pageStart = computed(() => {
  if (!totalRows.value) return 0;
  const size = normalizedPageSize.value ?? totalRows.value;
  return (currentPage.value - 1) * size + 1;
});

const pageEnd = computed(() => {
  const size = normalizedPageSize.value ?? totalRows.value;
  return Math.min(currentPage.value * size, totalRows.value);
});

const showPagination = computed(() => {
  const size = normalizedPageSize.value;
  return Boolean(size && totalRows.value > size);
});

watch(
  () => [props.rows.length, props.pageSize],
  () => {
    currentPage.value = 1;
  },
);

watch(totalPages, (pages) => {
  if (currentPage.value > pages) {
    currentPage.value = pages;
  }
});

function isTableRow(row: DataRow): row is UiTableRow {
  return "cells" in row;
}

function rawCellValue(row: DataRow, key: string): string | number | null | UiTableCellValue | undefined {
  return isTableRow(row) ? row.cells[key] : row[key];
}

function rawCellText(row: DataRow, key: string): string {
  const value = rawCellValue(row, key);
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "object") {
    return (value as UiTableCellValue).text;
  }
  return String(value);
}

function cellText(row: DataRow, key: string): string {
  const text = rawCellText(row, key);
  if (isTimeLikeColumn(key) && isIsoDateTime(text)) {
    return formatLocalTime(text);
  }
  return isUserContentColumn(key) ? text : localizeText(text, key);
}

function actionIconCount(row: DataRow, key: string): number {
  const text = rawCellText(row, key);
  return text.includes("/") ? 5 : 1;
}

function normalizeRoute(value: string | null | undefined): string | null {
  if (!value || value === "-") return null;
  return value.replace(/^\/ui(?=\/)/, "");
}

function hiddenRoute(row: DataRow, key: string): string | null {
  return normalizeRoute(rawCellText(row, key));
}

function primaryRoute(row: DataRow): string | null {
  return hiddenRoute(row, "route");
}

function traceRoute(row: DataRow): string | null {
  return hiddenRoute(row, "trace_route");
}

function cellRoute(row: DataRow, key: string): string | null {
  const value = rawCellValue(row, key);
  if (value && typeof value === "object" && "route" in value) {
    return normalizeRoute(value.route);
  }

  const normalized = normalizeKey(key);
  if (normalized === "trace") {
    return traceRoute(row);
  }
  if (
    normalized === "run-id"
    || normalized === "holder-run-id"
    || normalized === "current-run"
    || normalized === "run-id-entity"
    || normalized === "intake-key"
    || normalized === "example-run-id"
  ) {
    return primaryRoute(row);
  }
  return null;
}

function isBrowserHref(route: string | null): boolean {
  return Boolean(route && (/^https?:\/\//.test(route) || route.startsWith("/artifacts/")));
}

function normalizeKey(key: string) {
  return key.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function isIsoDateTime(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}T/.test(value);
}

function isTimeLikeColumn(key: string) {
  const normalized = normalizeKey(key);
  return normalized === "time"
    || normalized.endsWith("-at")
    || normalized.startsWith("last-")
    || normalized === "received-at"
    || normalized === "enqueued-at"
    || normalized === "started"
    || normalized === "completed"
    || normalized === "last"
    || normalized === "next";
}

function columnClass(key: string) {
  return `column-${normalizeKey(key)}`;
}

function isActionColumn(key: string) {
  return normalizeKey(key) === "actions" || normalizeKey(key) === "action";
}

function isBadgeColumn(key: string) {
  return ["status", "state", "risk-level", "result", "validation", "source"].includes(normalizeKey(key));
}

function badgeTone(value: string) {
  const text = value.toLowerCase();
  if (/(error|failed|fail|high|blocked|danger|revoked|错误|失败|高|阻塞|已撤销)/.test(text)) return "danger";
  if (/(warning|medium|draft|pending|controlled|review|警告|中|草稿|待|受控|审核)/.test(text)) return "warning";
  if (/(healthy|active|available|online|idle|pass|valid|low|allow|built-in|completed|success|健康|活跃|可用|在线|空闲|通过|有效|低|允许|内置|完成|成功)/.test(text)) return "success";
  if (/(custom|info|staging|dev|自定义|信息|预发|开发)/.test(text)) return "info";
  return "neutral";
}

function isChipColumn(key: string) {
  return normalizeKey(key) === "scope";
}

function shouldAllowRawKeys() {
  return props.allowRawKeys === true;
}

function isRawKeyLikeColumn(key: string) {
  const normalized = normalizeKey(key);
  return rawKeyLikeColumns.has(normalized)
    || normalized.endsWith("-event")
    || normalized.endsWith("-events")
    || normalized.endsWith("-topic")
    || normalized.endsWith("-topics")
    || normalized.endsWith("-key");
}

function shouldHumanizeRawKey(value: string, key?: string) {
  return !shouldAllowRawKeys() && (!key || isRawKeyLikeColumn(key)) && looksLikeRawKey(value);
}

function isUserContentColumn(key: string) {
  const normalized = normalizeKey(key);
  if (isRawKeyLikeColumn(key) && !shouldAllowRawKeys()) return false;
  return userContentColumns.has(normalized)
    || normalized.endsWith("-id")
    || normalized.includes("run-id")
    || normalized.includes("model-version");
}

function cellChips(value: string) {
  if (value === "-" || value.includes("/")) return [value];
  const matches = value.match(/Prod Only|Prod|Staging|Dev|All agents/g);
  return matches?.length ? matches : value.split(/,\s*/).filter(Boolean);
}

function goToPreviousPage() {
  currentPage.value = Math.max(1, currentPage.value - 1);
}

function goToNextPage() {
  currentPage.value = Math.min(totalPages.value, currentPage.value + 1);
}

function handleRowClick(event: MouseEvent, row: DataRow) {
  if (!props.clickableRows) return;
  const target = event.target;
  if (target instanceof Element && target.closest("a, button")) return;
  emit("row-click", row);
}

function rowIdentifier(row: DataRow): string | null {
  if (isTableRow(row)) return row.id;
  const value = (row as Record<string, unknown>).__row_id;
  if (typeof value === "string" && value.trim()) return value.trim();
  return null;
}

function localizeText(value: string, columnKey?: string): string {
  const key = textKeys[value];
  if (key) return t(key);

  const unsupportedCredentialBindingSource = value.match(/^unsupported credential binding source '(.+)'\.$/i);
  if (unsupportedCredentialBindingSource) {
    return t("operations.llm.reason.unsupportedCredentialBindingSource", {
      source: unsupportedCredentialBindingSource[1],
    });
  }

  if (shouldHumanizeRawKey(value, columnKey)) return formatRawKeyLabel(value);

  if (locale.value !== "zh-CN") return value;

  const enqueued = value.match(/^Run (.+) enqueued$/);
  if (enqueued) return `运行 ${enqueued[1]} 已入队`;

  const waitingForLane = value.match(/^Run (.+) waiting for lane lock$/);
  if (waitingForLane) return `运行 ${waitingForLane[1]} 正在等待 Lane 锁`;

  const workerLease = value.match(/^Worker (.+) lease expiring soon$/);
  if (workerLease) return `工作器 ${workerLease[1]} 租约即将过期`;

  return value;
}

const textKeys: Record<string, string> = {
  "Component": "table.component",
  "Status": "table.status",
  "Assignment": "table.assignment",
  "Lease": "table.lease",
  "Detail": "table.detail",
  "Details": "table.details",
  "Title": "table.title",
  "Description": "table.description",
  "Name": "table.name",
  "Profile": "table.profile",
  "Driver": "table.driver",
  "Kind": "table.kind",
  "Mode": "table.mode",
  "Strategy": "table.strategy",
  "Environment": "table.environment",
  "Duration": "table.duration",
  "Result": "table.result",
  "Time": "table.time",
  "Change": "table.change",
  "Changed": "table.changed",
  "Updated": "table.updated",
  "Reindexed": "table.reindexed",
  "Chunks": "table.chunks",
  "Owner": "table.owner",
  "Type": "table.type",
  "Severity": "table.severity",
  "Category": "table.category",
  "Issue": "table.issue",
  "Priority": "table.priority",
  "Provider": "table.provider",
  "External Service": "table.externalService",
  "Timeout": "table.timeout",
  "Current Context": "operations.memory.reason.currentContext",
  "current context": "operations.memory.reason.currentContext",
  "keyword": "operations.memory.backend.keyword",
  "vector": "operations.memory.backend.vector",
  "Agent": "common.agent",
  "Backend": "table.backend",
  "Space ID": "table.spaceId",
  "Files": "table.files",
  "Indexed Files": "table.indexedFiles",
  "Retrieval Backend": "table.retrievalBackend",
  "Watcher": "table.watcher",
  "Storage Root": "table.storageRoot",
  "File": "table.file",
  "Preview": "table.preview",
  "Job": "table.job",
  "Progress": "table.progress",
  "Source Files": "operations.memory.tab.files",
  "Index DB": "table.indexDb",
  "Rank": "table.rank",
  "Score": "table.score",
  "Lines": "table.lines",
  "Snippet": "table.snippet",
  "Operation": "table.operation",
  "Latest Updated": "table.latestUpdated",
  "Last Scanned": "table.lastScanned",
  "Next Scan": "table.nextScan",
  "Version": "table.version",
  "Tags": "table.tags",
  "Resources": "table.resources",
  "Required Tools": "table.requiredTools",
  "Suggested Tools": "table.suggestedTools",
  "Effects": "table.effects",
  "Capability Type": "table.capabilityType",
  "Required Item": "table.requiredItem",
  "Impact": "table.impact",
  "Resolved By": "table.resolvedBy",
  "Resolved To": "table.resolvedTo",
  "Purpose": "table.purpose",
  "Available Skills": "table.availableSkills",
  "Ready Skills": "table.readySkills",
  "Missing": "table.missing",
  "Winner": "table.winner",
  "Provider / Model": "table.providerModel",
  "API Family": "table.apiFamily",
  "Credential": "table.credential",
  "Availability": "table.availability",
  "Context": "table.context",
  "Invocation ID": "table.invocationId",
  "Finish Reason": "table.finishReason",
  "Error Code": "table.errorCode",
  "Retryable": "table.retryable",
  "Last Invocation": "table.lastInvocation",
  "Last Failed": "table.lastFailed",
  "Affected Invocations": "table.affectedInvocations",
  "Entity": "table.entity",
  "Percent": "table.percent",
  "Run ID": "table.runId",
  "Parent Run": "table.parentRun",
  "Tool Run ID": "table.toolRunId",
  "Turn ID": "table.turnId",
  "Chain ID": "table.chainId",
  "Step ID": "table.stepId",
  "Step Kind": "table.stepKind",
  "Chain Status": "table.chainStatus",
  "Active Step": "table.activeStep",
  "Last Step": "table.lastStep",
  "Steps": "table.steps",
  "Items": "table.items",
  "Lane Key": "table.laneKey",
  "Enqueued At": "table.enqueuedAt",
  "Agent (Target)": "table.agentTarget",
  "Wait Reason": "table.waitReason",
  "Wait Time": "table.waitTime",
  "Dispatch": "table.dispatchStatus",
  "Wait Count": "table.waitCount",
  "Avg Wait": "table.avgWait",
  "Max Wait": "table.maxWait",
  "Total Wait": "table.totalWait",
  "Sources": "table.sources",
  "Runtime Count": "table.runtimeCount",
  "Providers": "table.providers",
  "Actions": "table.actions",
  "Capability": "table.capability",
  "Capabilities": "table.capabilities",
  "Limit": "table.limit",
  "Capacity": "table.capacity",
  "Waiting": "table.waiting",
  "Available Workers": "table.availableWorkers",
  "State": "table.state",
  "Holder Run ID": "table.holderRunId",
  "Lock Epoch": "table.lockEpoch",
  "Expires At": "table.expiresAt",
  "Renewed At": "table.renewedAt",
  "Reason": "table.reason",
  "Retry Budget": "table.retryBudget",
  "Candidate Workers": "table.candidateWorkers",
  "Blocked By": "table.blockedBy",
  "Next Step": "table.nextStep",
  "Worker": "table.worker",
  "Worker ID": "table.workerId",
  "Interaction ID": "table.interactionId",
  "Instance ID": "table.instanceId",
  "Process ID": "table.processId",
  "Session Key": "table.sessionKey",
  "Display Name": "table.displayName",
  "Service Set": "table.serviceSet",
  "Service Group": "table.serviceGroup",
  "Services": "table.services",
  "Desired": "table.desired",
  "Active Leases": "table.activeLeases",
  "Managed By": "table.managedBy",
  "Transport": "table.transport",
  "Start Policy": "table.startPolicy",
  "Restart Policy": "table.restartPolicy",
  "PID": "table.pid",
  "Exit Code": "table.exitCode",
  "Binding": "table.binding",
  "Command": "table.command",
  "Working Directory": "table.workingDirectory",
  "Ended At": "table.endedAt",
  "Endpoint": "table.endpoint",
  "Runtime Dependency": "table.runtimeDependency",
  "Tools/List": "table.toolsList",
  "CDP Endpoint": "table.cdpEndpoint",
  "Pages": "table.pages",
  "Host Gen": "table.hostGeneration",
  "Active Target": "table.activeTarget",
  "Page Gen": "table.pageGeneration",
  "Snapshot Gen": "table.snapshotGeneration",
  "Ref Gen": "table.refGeneration",
  "Last Action": "table.lastAction",
  "Refs": "table.refs",
  "Frames": "table.frames",
  "Proxy": "table.proxy",
  "Proxy Ready": "table.proxyReady",
  "Egress": "table.egress",
  "Runtime": "table.runtime",
  "Manifest": "table.manifest",
  "Requires": "table.requires",
  "Last Healthcheck At": "table.lastHealthcheckAt",
  "Env Drift": "table.envDrift",
  "Last Error": "table.lastError",
  "Lease ID": "table.leaseId",
  "Acquired At": "table.acquiredAt",
  "Heartbeat At": "table.heartbeatAt",
  "Role": "table.role",
  "Attempt": "table.attempt",
  "Assigned At": "table.assignedAt",
  "Started At": "table.startedAt",
  "Completed At": "table.completedAt",
  "Lease Expires At": "table.leaseExpiresAt",
  "Last Heartbeat": "table.lastHeartbeat",
  "Lease (Expires At)": "table.leaseExpiresAt",
  "Registered At": "table.registeredAt",
  "Current Run": "table.currentRun",
  "Load": "table.loadShort",
  "Load (1m)": "table.load",
  "Worker Load": "table.workerLoad",
  "Runtime Key": "table.runtimeKey",
  "Runtime ID": "table.runtimeId",
  "Concurrency Key": "table.concurrencyKey",
  "Max Concurrency": "table.maxConcurrency",
  "Runs (5m)": "table.runs5m",
  "Source": "table.source",
  "Intake Key": "table.intakeKey",
  "Received At": "table.receivedAt",
  "Target Lane": "table.targetLane",
  "Age": "table.age",
  "Error": "table.error",
  "Draft": "table.draft",
  "Intent": "table.intent",
  "Actor": "table.actor",
  "Validation": "table.validation",
  "Module": "table.module",
  "Trace": "table.trace",
  "Level": "table.level",
  "Event": "table.event",
  "Event Key": "table.rawEventKey",
  "Event ID": "table.eventId",
  "Topic": "table.topic",
  "Cursor": "table.cursor",
  "Contract": "table.contract",
  "Contracts": "table.contracts",
  "Route": "table.route",
  "Routes": "table.routes",
  "Source Topic": "table.sourceTopic",
  "Target Topic": "table.targetTopic",
  "Latest Cursor": "table.latestCursor",
  "Observe Cursor": "table.observeCursor",
  "Live Cursor": "table.liveCursor",
  "Updated At": "table.updatedAt",
  "Seconds Since Update": "table.secondsSinceUpdate",
  "Lag": "table.lag",
  "Kinds": "table.kinds",
  "Definitions": "table.definitions",
  "Surfaces": "table.surfaces",
  "Topic Pattern": "table.topicPattern",
  "Producers": "table.producers",
  "Consumers": "table.consumers",
  "Durability": "table.durability",
  "Live Matches": "table.liveMatches",
  "Observer": "table.observer",
  "Source Events": "table.sourceEvents",
  "Output Definitions": "table.outputDefinitions",
  "Handlers": "table.handlers",
  "Observed Inputs": "table.observedInputs",
  "Source Kinds": "table.sourceKinds",
  "Target Kind": "table.targetKind",
  "Subscription": "table.subscription",
  "Latest Event": "table.latestEvent",
  "Source Event ID": "table.sourceEventId",
  "External Event ID": "table.externalEventId",
  "External Message ID": "table.externalMessageId",
  "External Conversation ID": "table.externalConversationId",
  "External User ID": "table.externalUserId",
  "Agent ID": "table.agentId",
  "Active Session ID": "table.activeSessionId",
  "Pattern": "table.pattern",
  "Direction": "table.direction",
  "Target": "table.target",
  "Last Seen": "table.lastSeen",
  "Run ID / Entity": "table.runEntity",
  "Count": "table.count",
  "Value": "table.value",
  "Field": "table.field",
  "Stream": "table.stream",
  "Bytes": "table.bytes",
  "Next Offset": "table.nextOffset",
  "Runs": "table.runs",
  "Failures": "table.failures",
  "Success Rate": "table.successRate",
  "Avg Duration": "table.avgDuration",
  "Max Duration": "table.maxDuration",
  "Last Run": "table.lastRun",
  "Artifact ID": "table.artifactId",
  "Mime Type": "table.mimeType",
  "Size": "common.size",
  "Dimensions": "table.dimensions",
  "Asset": "table.asset",
  "Requirements": "table.requirements",
  "Requirement": "table.requirement",
  "Usage": "table.usage",
  "Required By": "table.requiredBy",
  "Readiness": "table.readiness",
  "Consumer": "table.consumer",
  "Usage Type": "table.usageType",
  "Usage ID": "table.usageId",
  "Target Type": "table.targetType",
  "Flow Type": "table.flowType",
  "Path": "table.path",
  "Required Access": "table.requiredAccess",
  "Missing Access": "table.missingAccess",
  "Affected (24h)": "table.affected24h",
  "Access Failures": "table.accessFailures",
  "Setup": "table.setup",
  "Action": "table.action",
  "Account ID": "table.accountId",
  "Accounts": "table.accounts",
  "Channel Type": "table.channelType",
  "Connection ID": "table.connectionId",
  "Connections": "table.connections",
  "Conversation ID": "table.conversationId",
  "Heartbeat Age": "table.heartbeatAge",
  "Outbound ID": "table.outboundId",
  "Service Key": "table.serviceKey",
  "Streaming": "table.streaming",
  "Transport Mode": "table.transportMode",
  "Transport Modes": "table.transportModes",
  "Metadata": "table.metadata",
  "No records.": "table.noRecords",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "Config Drift": "text.configDrift",
  "Active": "text.active",
  "Enabled": "operations.channels.status.enabled",
  "Disabled": "operations.channels.status.disabled",
  "Offline": "operations.channels.status.offline",
  "offline": "text.offline",
  "Expired": "text.expired",
  "Released": "text.released",
  "Configured": "text.configured",
  "not configured": "text.notConfigured",
  "not_configured": "text.notConfigured",
  "not required": "text.notRequired",
  "access_binding": "text.accessBinding",
  "Available": "text.available",
  "Installed": "text.installed",
  "Registered": "text.registered",
  "Online": "text.online",
  "online": "text.online",
  "Intake": "operations.channels.direction.intake",
  "Observe": "operations.channels.direction.observe",
  "Live": "operations.channels.direction.live",
  "Broadcast": "operations.channels.direction.broadcast",
  "Control": "operations.channels.direction.control",
  "Other": "operations.channels.direction.other",
  "Topic Contract": "operations.channels.contract.topic",
  "Route Contract": "operations.channels.contract.route",
  "Definition": "operations.channels.contract.definition",
  "Surface": "operations.channels.contract.surface",
  "Observer Runtime": "operations.events.observer.runtime",
  "Missing Heartbeat": "operations.events.observer.missingHeartbeat",
  "Busy": "operations.tool.worker.busy",
  "Idle": "operations.tool.worker.idle",
  "idle": "operations.tool.worker.idle",
  "Stale": "operations.tool.worker.stale",
  "Lease Expired": "operations.tool.worker.leaseExpired",
  "Lease Expiring": "text.leaseExpiring",
  "Queued": "text.queued",
  "Received": "operations.channels.status.received",
  "Submitted": "operations.channels.status.submitted",
  "Running": "status.running",
  "Completed": "text.completed",
  "completed": "status.completed",
  "Rebuilt": "operations.events.observer.rebuilt",
  "rebuilt": "operations.events.observer.rebuilt",
  "Delivered": "operations.channels.status.delivered",
  "Failed": "status.failed",
  "Success": "status.success",
  "Succeeded": "status.success",
  "Cancelled": "status.cancelled",
  "Cancel Requested": "status.cancelRequested",
  "Timed Out": "status.timedOut",
  "Dispatching": "status.dispatching",
  "Created": "status.created",
  "Assigned": "text.assigned",
  "Started": "text.started",
  "background": "text.background",
  "inline": "text.inline",
  "async": "text.async",
  "managed": "text.managed",
  "existing-session": "text.existingSession",
  "local-managed": "text.localManaged",
  "manual_only": "text.manualOnly",
  "least_busy": "text.leastBusy",
  "round_robin": "text.roundRobin",
  "sticky_session": "text.stickySession",
  "none": "text.none",
  "static": "text.static",
  "local": "text.local",
  "remote": "text.remote",
  "provider": "table.provider",
  "credential binding": "text.credentialBinding",
  "ready": "common.ready",
  "attached": "operations.browser.status.attached",
  "fresh": "operations.browser.status.fresh",
  "stale": "operations.browser.status.stale",
  "cooling": "operations.browser.status.cooling",
  "setup_needed": "text.setupNeeded",
  "waiting_user": "text.waitingUser",
  "unsupported": "text.unsupported",
  "expired": "text.expired",
  "Setup Needed": "text.setupNeeded",
  "Declared": "operations.skills.status.declared",
  "Required": "operations.skills.status.required",
  "Required Tool": "operations.skills.requirement.requiredTool",
  "Suggested Tool": "operations.skills.requirement.suggestedTool",
  "Optional Tool": "operations.skills.requirement.optionalTool",
  "Required Effect": "operations.skills.requirement.requiredEffect",
  "Secret": "operations.skills.requirement.secret",
  "Credential File": "operations.skills.requirement.credentialFile",
  "Setup Hint": "operations.skills.requirement.setupHint",
  "Register or enable tool": "operations.skills.next.registerTool",
  "Register or enable missing tools": "operations.skills.next.registerTools",
  "Access setup": "operations.skills.next.accessSetup",
  "Conflict": "operations.skills.status.conflict",
  "Duplicate Skill": "operations.skills.status.duplicateSkill",
  "Inspect": "text.inspect",
  "Waiting User": "text.waitingUser",
  "observed_failure": "text.observedFailure",
  "blocked": "text.blocked",
  "Blocked": "text.blocked",
  "High": "text.high",
  "Medium": "text.medium",
  "Low": "text.low",
  "Info": "text.info",
  "Env": "text.env",
  "File Credential": "text.fileCredential",
  "Inline Credential": "text.inlineCredential",
  "Credential Set": "text.credentialSet",
  "Authorization Requirement": "text.authorizationRequirement",
  "Unknown": "status.unknown",
  "Dirty": "operations.memory.status.dirty",
  "Missing Index": "operations.memory.status.missingIndex",
  "No Context": "operations.memory.status.noContext",
  "File Only": "operations.memory.status.fileOnly",
  "Long Term": "operations.memory.kind.longTerm",
  "Daily": "operations.memory.kind.daily",
  "Archive": "operations.memory.kind.archive",
  "Watching": "operations.memory.status.watching",
  "Not Configured": "operations.memory.status.notConfigured",
  "Hit": "operations.memory.status.hit",
  "Hybrid": "operations.memory.backend.hybrid",
  "hybrid": "operations.memory.backend.hybrid",
  "file-backed": "operations.memory.backend.fileBacked",
  "directory": "operations.memory.source.directory",
  "View": "text.view",
  "Open": "text.open",
  "Open Trace": "text.openTrace",
  "Open / Trace": "text.openSlashTrace",
  "Open / Trace / Cancel": "text.openTraceCancel",
  "Open / Trace / Retry": "text.openTraceRetry",
  "Default tool groups": "text.defaultToolGroups",
  "Image generation": "text.imageGeneration",
  "Browser shared state": "text.browserSharedState",
  "Workspace shared state": "text.workspaceSharedState",
  "Mobile shared state": "text.mobileSharedState",
  "Session shared state": "text.sessionSharedState",
  "Command shared state": "text.commandSharedState",
  "System shared state": "text.systemSharedState",
  "Ready": "text.ready",
  "Stopped": "text.stopped",
  "Starting": "text.starting",
  "Stopping": "text.stopping",
  "Degraded": "text.degraded",
  "failed": "status.failed",
  "stopped": "text.stopped",
  "starting": "text.starting",
  "stopping": "text.stopping",
  "degraded": "text.degraded",
  "released": "text.released",
  "configured": "text.configured",
  "Desired Unmet": "operations.daemon.status.desiredUnmet",
  "Saturated": "text.saturated",
  "No Worker": "text.noWorker",
  "No worker": "text.noWorker",
  "waiting for scheduler": "text.waitingForScheduler",
  "waiting for online worker": "text.waitingForOnlineWorker",
  "waiting for worker slot": "text.waitingForWorkerSlot",
  "waiting for capability capacity": "text.waitingForCapabilityCapacity",
  "assigned to worker": "text.assignedToWorker",
  "running on worker": "text.runningOnWorker",
  "dispatching to worker": "text.dispatchingToWorker",
  "inline execution": "text.inlineExecution",
  "capacity available": "text.capacityAvailable",
  "worker slots full": "text.workerSlotsFull",
  "no online worker": "text.noOnlineWorker",
  "assignment lease expired": "text.assignmentLeaseExpired",
  "error": "text.error",
  "worker_pool": "text.workerPool",
  "worker_capacity": "text.workerCapacity",
  "capability_limit": "text.capabilityLimit",
  "scheduler": "text.scheduler",
  "inline_runtime": "text.inlineRuntime",
  "cancellation": "text.cancellation",
  "inspect error": "text.inspectError",
  "recover expired assignment": "text.recoverExpiredAssignment",
  "wait for worker start": "text.waitForWorkerStart",
  "monitor worker heartbeat": "text.monitorWorkerHeartbeat",
  "start or recover worker": "text.startOrRecoverWorker",
  "wait for capacity": "text.waitForCapacity",
  "scheduler dispatch": "text.schedulerDispatch",
  "wait for assignment": "text.waitForAssignment",
  "finish cancellation": "text.finishCancellation",
  "execute inline": "text.executeInline",
  "monitor": "text.monitor",
  "access readiness service is not connected": "text.accessReadinessDisconnected",
  "access setup is required": "text.accessSetupRequired",
  "access failure observed": "text.accessFailureObserved",
  "access failure observed for unknown tool": "text.accessFailureUnknownTool",
  "Waiting for worker": "text.waitingForWorker",
  "Waiting for lane lock": "text.waitingForLaneLock",
  "Executor busy": "text.executorBusy",
  "Waiting for approval": "text.waitingForApproval",
  "Protect critical section": "text.protectCriticalSection",
  "Limit per-lane concurrency": "text.limitPerLaneConcurrency",
  "Resource isolation": "text.resourceIsolation",
  "Lane Timeout": "text.laneTimeout",
  "Executor Crash": "text.executorCrash",
  "Lane lock timeout after 5m": "text.laneLockTimeout",
  "Worker exited unexpectedly": "text.workerExited",
  "Queued > 5m": "text.queuedOver5m",
  "Running no events > 10m": "text.runningNoEventsOver10m",
  "Lane lock expired": "text.laneLockExpired",
  "Worker lease expired": "text.workerLeaseExpired",
  "Intake Service": "text.intakeService",
  "Scheduler": "text.scheduler",
  "Agent Profiles": "text.agentProfiles",
  "LLM Profiles": "text.llmProfiles",
  "LLM Profile": "text.llmProfile",
  "Tools": "text.tools",
  "Browser profile context": "operations.tool.source.browserProfileContext",
  "Skills": "text.skills",
  "Channels": "text.channels",
  "Events": "text.events",
  "Access Assets": "text.accessAssets",
  "Access Asset": "table.accessAsset",
  "Memory Config": "text.memoryConfig",
  "Runtime Defaults": "text.runtimeDefaults",
  "Tool": "text.tool",
  "tool": "text.tool",
  "Agent Profile": "text.agentProfile",
  "Skill": "text.skill",
  "Channel": "text.channel",
  "channel": "text.channel",
  "llm_profile": "text.llmProfile",
  "credential_binding": "text.credentialBinding",
  "Orchestration": "text.orchestration",
  "Memory": "text.memory",
  "Access": "text.access",
  "System": "text.system",
  "Yes": "common.yes",
  "No": "common.no",
  "Bound": "text.bound",
  "Unbound": "text.unbound",
  "Missing Session": "text.missingSession",
  "Exited": "text.exited",
  "Killed": "text.killed",
  "Input": "text.input",
  "Output": "text.output",
  "Reasoning": "text.reasoning",
  "Unclassified": "text.unclassified",
  "Agent Default": "text.agentDefault",
  "Explicit Override": "text.explicitOverride",
  "Fallback Used": "text.fallbackUsed",
  "No Match / Error": "text.noMatchError",
  "Matched": "operations.events.status.matched",
  "Uncovered": "operations.events.status.uncovered",
  "Definition Only": "operations.events.status.definitionOnly",
  "Topic Contract Only": "operations.events.status.topicContractOnly",
  "Dead Letter": "operations.events.status.deadLetter",
  "At Head": "operations.events.status.atHead",
  "Lagging": "operations.events.metric.lagging",
  "Stuck": "operations.events.status.stuck",
  "active": "text.active",
  "registered": "text.registered",
  "created": "status.created",
  "queued": "status.queued",
  "running": "status.running",
  "waiting": "status.waiting",
  "succeeded": "status.success",
  "cancelled": "status.cancelled",
  "cancel_requested": "status.cancelRequested",
  "dispatching": "status.dispatching",
  "timed_out": "status.timedOut",
  "late_observed": "status.lateObserved",
  "late_ignored": "status.lateIgnored",
  "matched": "operations.events.status.matched",
  "uncovered": "operations.events.status.uncovered",
  "definition_only": "operations.events.status.definitionOnly",
  "topic_contract_only": "operations.events.status.topicContractOnly",
  "dead_letter": "operations.events.status.deadLetter",
  "at_head": "operations.events.status.atHead",
  "lagging": "operations.events.metric.lagging",
  "stuck": "operations.events.status.stuck",
  "observed": "operations.events.status.observed",
  "resolved": "text.resolved",
  "intake": "text.stepKind.intake",
  "llm": "text.stepKind.llm",
  "tool_batch": "text.stepKind.toolBatch",
  "approval": "text.stepKind.approval",
  "tool_resume": "text.stepKind.toolResume",
  "final_response": "text.stepKind.finalResponse",
  "maintenance": "text.stepKind.maintenance",
  "llm_invocation": "text.stepItem.llmInvocation",
  "tool_call": "text.stepItem.toolCall",
  "tool_run": "text.stepItem.toolRun",
  "tool_result": "text.stepItem.toolResult",
  "approval_request": "text.stepItem.approvalRequest",
  "session_message": "text.stepItem.sessionMessage",
  "context_snapshot": "text.stepItem.contextSnapshot",
  "orchestration_run": "text.dispatchOwner.orchestrationRun",
  "orchestration_step": "text.dispatchOwner.orchestrationStep",
  "orchestration_ingress": "text.dispatchOwner.orchestrationIngress",
  "orchestration_continuation": "text.dispatchOwner.orchestrationContinuation",
};

const userContentColumns = new Set([
  "name",
  "display-name",
  "description",
  "detail",
  "details",
  "message",
  "summary",
  "owner",
  "updated-by",
  "created-by",
  "user",
  "actor",
  "resource",
  "asset-id",
  "asset-name",
  "access-asset",
  "provider",
  "version",
  "tags",
  "required",
  "required-item",
  "required-tools",
  "suggested-tools",
  "available-skills",
  "ready-skills",
  "capability",
  "input",
  "missing",
  "resolved",
  "resolved-by",
  "resolved-to",
  "surface",
  "file",
  "path",
  "storage-root",
  "index-db",
  "snippet",
  "trace",
  "provider-service",
  "adapter-type",
  "backend",
  "consumers",
  "tool",
  "source",
  "current-run",
  "worker-id",
  "process-name",
  "node-host",
  "container-instance",
  "event-name",
  "owner-id",
  "topic-pattern",
  "model",
  "model-version",
  "default-llm-profile",
  "fallback-llm-profile",
  "owner-package",
  "required-access",
  "missing-access",
]);

const rawKeyLikeColumns = new Set([
  "event",
  "event-name",
  "event-key",
  "key",
  "metric",
  "metric-key",
  "source",
  "source-event",
  "source-events",
  "source-topic",
  "target-topic",
  "topic",
  "topic-pattern",
  "input-topics",
]);
</script>

<template>
  <div
    class="data-table"
    :class="props.sectionId ? `data-table--${props.sectionId.replace(/_/g, '-')}` : undefined"
  >
    <table>
      <thead>
        <tr>
          <th
            v-for="column in normalizedColumns"
            :key="column.key"
            :class="columnClass(column.key)"
          >
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in displayedRows"
          :key="`${currentPage}:${index}`"
          :class="{
            'is-clickable': props.clickableRows,
            'is-selected': props.selectedRowId && rowIdentifier(row) === props.selectedRowId,
          }"
          @click="handleRowClick($event, row)"
        >
          <td
            v-for="column in normalizedColumns"
            :key="column.key"
            :class="columnClass(column.key)"
            :data-i18n-skip="isUserContentColumn(column.key) ? '' : undefined"
            :title="cellText(row, column.key)"
          >
            <span v-if="isActionColumn(column.key)" class="action-icons">
              <a
                v-if="isBrowserHref(primaryRoute(row))"
                :href="primaryRoute(row) ?? '#'"
                target="_blank"
                rel="noreferrer"
                :aria-label="t('text.open')"
              >
                <ExternalLink :size="12" />
              </a>
              <RouterLink v-else-if="primaryRoute(row)" :to="primaryRoute(row) ?? '/'" :aria-label="t('text.open')">
                <Pencil :size="12" />
              </RouterLink>
              <button v-else type="button" :aria-label="t('common.edit')">
                <Pencil :size="12" />
              </button>
              <template v-if="actionIconCount(row, column.key) > 1">
                <RouterLink v-if="traceRoute(row)" :to="traceRoute(row) ?? '/'" :aria-label="t('text.openTrace')">
                  <Copy :size="12" />
                </RouterLink>
                <button v-else type="button" :aria-label="t('common.clone')">
                  <Copy :size="12" />
                </button>
                <button type="button" :aria-label="t('common.more')">
                  <MoreVertical :size="12" />
                </button>
              </template>
            </span>
            <a
              v-else-if="isBrowserHref(cellRoute(row, column.key))"
              class="cell-link"
              :href="cellRoute(row, column.key) ?? '#'"
              target="_blank"
              rel="noreferrer"
            >
              {{ cellText(row, column.key) }}
            </a>
            <RouterLink
              v-else-if="cellRoute(row, column.key)"
              class="cell-link"
              :to="cellRoute(row, column.key) ?? '/'"
            >
              {{ cellText(row, column.key) }}
            </RouterLink>
            <span
              v-else-if="isBadgeColumn(column.key)"
              :class="['cell-badge', `cell-badge--${badgeTone(cellText(row, column.key))}`]"
            >
              {{ cellText(row, column.key) }}
            </span>
            <span v-else-if="isChipColumn(column.key)" class="cell-chip-row">
              <span v-for="chip in cellChips(cellText(row, column.key))" :key="chip">{{ chip }}</span>
            </span>
            <template v-else>{{ cellText(row, column.key) }}</template>
          </td>
        </tr>
      </tbody>
    </table>
    <footer v-if="showPagination" class="data-table__pager">
      <span>
        {{ t("table.pageSummary", { start: pageStart, end: pageEnd, total: totalRows }) }}
      </span>
      <div>
        <button type="button" :disabled="currentPage <= 1" @click="goToPreviousPage">
          {{ t("common.previous") }}
        </button>
        <button type="button" :disabled="currentPage >= totalPages" @click="goToNextPage">
          {{ t("common.next") }}
        </button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.data-table {
  --data-table-min-width: 100%;

  overflow: auto;
  scrollbar-gutter: stable;
}

.data-table table {
  width: 100%;
  min-width: var(--data-table-min-width);
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}

.data-table thead {
  position: sticky;
  top: 0;
  z-index: 2;
}

.data-table__pager {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-height: 34px;
  padding: 6px 0 0;
  border-top: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-panel) 94%, transparent);
  color: var(--text-muted);
  font-size: 11px;
}

.data-table__pager div {
  display: inline-flex;
  gap: 6px;
}

.data-table__pager button {
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
}

.data-table__pager button:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}

th,
td {
  height: 28px;
  min-height: 28px;
  padding: 4px var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}

tbody tr.is-clickable {
  cursor: pointer;
}

tbody tr.is-clickable:hover td {
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
}

tbody tr.is-selected td {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--text-primary);
}

tbody tr.is-selected td:first-child {
  font-weight: 760;
}

th {
  background: color-mix(in srgb, var(--surface-panel) 96%, var(--surface-page));
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 650;
}

td {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.18;
}

.column-priority {
  width: 46px;
}

.column-run-id,
.column-holder-run-id,
.column-current-run,
.column-run-id-entity,
.column-run-step,
.column-run-turn-step,
.column-run-trace-turn,
.column-source-run-step,
.column-used-in-run-turn,
.column-used-in-run-step,
.column-used-in-runs {
  width: 118px;
}

.column-lane-key,
.column-target-lane {
  width: 98px;
}

.column-request-id,
.column-message-id,
.column-event-id,
.column-event-id-cursor,
.column-asset-id,
.column-owner-id,
.column-worker-id,
.column-node-host,
.column-container-instance,
.column-surface-id {
  width: 132px;
}

.column-enqueued-at,
.column-received-at,
.column-last-heartbeat,
.column-expires-at,
.column-renewed-at,
.column-time,
.column-time-utc-8,
.column-started,
.column-started-at,
.column-completed-at,
.column-created,
.column-created-at,
.column-updated,
.column-updated-at,
.column-last-updated,
.column-last-changed,
.column-last-used,
.column-last-failed,
.column-last-indexed,
.column-last-scanned,
.column-last-modified,
.column-last-consumed,
.column-last-acked,
.column-last-occurred,
.column-last-run,
.column-last-started,
.column-next-scan {
  width: 104px;
}

.column-agent-target {
  width: 98px;
}

.column-duration,
.column-latency,
.column-oldest,
.column-oldest-wait,
.column-expires,
.column-heartbeat,
.column-modified,
.column-next,
.column-last {
  width: 92px;
}

.column-name,
.column-display-name,
.column-asset,
.column-asset-name,
.column-access-asset,
.column-asset-service,
.column-provider,
.column-provider-model,
.column-provider-service,
.column-adapter-type,
.column-model,
.column-model-version,
.column-llm-profile,
.column-default-llm-profile,
.column-fallback-llm-profile,
.column-tool,
.column-skill,
.column-channel,
.column-topic,
.column-surface,
.column-event,
.column-topic-pattern,
.column-subscription,
.column-observer,
.column-consumer,
.column-consumer-observer,
.column-owner,
.column-owner-package,
.column-process,
.column-process-name,
.column-service-set,
.column-dependency,
.column-store,
.column-key,
.column-value,
.column-file,
.column-profile,
.column-bound-agent,
.column-runtime-strategy,
.column-execution-mode,
.column-exec-mode,
.column-capability,
.column-category,
.column-type,
.column-kind,
.column-flow-type {
  width: 128px;
}

.column-agent,
.column-backend,
.column-by,
.column-default,
.column-fallback,
.column-fallback-to,
.column-flow,
.column-instance,
.column-job,
.column-node,
.column-operation,
.column-policy,
.column-port,
.column-processes,
.column-requested,
.column-resolved,
.column-resolved-by,
.column-run,
.column-set,
.column-supervisor,
.column-winner {
  width: 116px;
}

.column-description,
.column-detail,
.column-details,
.column-summary,
.column-message,
.column-change,
.column-issue,
.column-error,
.column-reason,
.column-wait-reason,
.column-result-output,
.column-query-excerpt,
.column-source-event-target,
.column-required-by,
.column-required-by-skill,
.column-required-by-skills,
.column-required-access,
.column-missing-access,
.column-capability-requirements,
.column-access-requirements,
.column-supported-surfaces,
.column-default-skills,
.column-access-grants,
.column-purpose,
.column-scope-hint,
.column-used-by,
.column-consumers,
.column-input-topics {
  width: 178px;
  white-space: nowrap;
}

.column-wait-time,
.column-age,
.column-count,
.column-level,
.column-ttl,
.column-load,
.column-load-1m,
.column-runs-5m,
.column-lock-epoch,
.column-percent,
.column-percent-of-total,
.column-percent-of-queue,
.column-progress,
.column-score,
.column-p95,
.column-size,
.column-models,
.column-partitions,
.column-events,
.column-events-24h,
.column-failures,
.column-failures-24h,
.column-affected,
.column-affected-24h,
.column-affected-runs-24h,
.column-affected-invocations,
.column-hit-count,
.column-top-k,
.column-input,
.column-output,
.column-inbound,
.column-inbound-24h,
.column-outbound,
.column-outbound-24h,
.column-tokens-24h,
.column-invocations-24h,
.column-streaming,
.column-streaming-24h,
.column-errors-24h,
.column-lag,
.column-lag-events,
.column-ack,
.column-ack-rate-24h,
.column-fail,
.column-fail-rate,
.column-success,
.column-success-rate-24h,
.column-failed,
.column-hit,
.column-indexed,
.column-items,
.column-pid,
.column-rank,
.column-resolutions,
.column-restarts,
.column-used {
  width: 70px;
  text-align: right;
}

.column-capacity,
.column-waiting,
.column-available-workers {
  width: 78px;
  text-align: right;
}

.column-streaming {
  text-align: left;
}

.column-action {
  width: 72px;
}

.column-actions {
  width: 90px;
}

.column-source {
  width: 118px;
}

.column-intake-key {
  width: 72px;
}

.column-module,
.column-status,
.column-result,
.column-validation,
.column-risk-level,
.column-impact,
.column-availability,
.column-reachable,
.column-contract,
.column-auth,
.column-mode,
.column-assignment-status,
.column-lease-state,
.column-scope,
.column-environment,
.column-config,
.column-config-status,
.column-direction,
.column-drain,
.column-retention,
.column-rotation,
.column-required,
.column-publication-mode,
.column-compatibility,
.column-read-only,
.column-sensitivity-pii,
.column-holds-worker {
  width: 88px;
}

.column-status {
  width: 96px;
}

.column-provider,
.column-provider-model,
.column-model-version,
.column-tool,
.column-event,
.column-topic-pattern,
.column-source-event-target {
  width: 148px;
}

.data-table--recent-invocations {
  --data-table-min-width: 1260px;
}

.data-table--event-contracts {
  --data-table-min-width: 1240px;
}

.data-table--tool-runs,
.data-table--recent-events,
.data-table--recent-messages,
.data-table--recent-access-events,
.data-table--recent-retrieval-logs,
.data-table--processes,
.data-table--access-targets,
.data-table--access-main-table,
.data-table--access-assets,
.data-table--agent-profiles,
.data-table--llm-profiles,
.data-table--skill-catalog,
.data-table--tool-catalog {
  --data-table-min-width: 1080px;
}

.data-table--tool-runs {
  --data-table-min-width: 1280px;
}

.data-table--run-queue,
.data-table--lane-locks,
.data-table--executor-overview,
.data-table--stuck-runs,
.data-table--missing-access,
.data-table--provider-health,
.data-table--streaming-requests,
.data-table--channel-status,
.data-table--channels-main-table,
.data-table--channels-dead-letters,
.data-table--daemon-main-table,
.data-table--events-main-table,
.data-table--memory-stores,
.data-table--index-jobs,
.data-table--resolved-skills,
.data-table--skills-main-table,
.data-table--resolution-logs,
.data-table--failed-tools,
.data-table--environment-variables {
  --data-table-min-width: 900px;
}

.data-table--provider-blocked,
.data-table--provider-auth-blocked,
.data-table--auth-missing,
.data-table--capability-limits,
.data-table--run-blockers,
.data-table--setup-flows,
.data-table--retrieval-trace,
.data-table--write-flush,
.data-table--source-scan,
.data-table--source-files,
.data-table--topics,
.data-table--subscriptions,
.data-table--observers,
.data-table--dead-letter-queue,
.data-table--channel-events,
.data-table--event-dead-letters,
.data-table--daemon-events-brief,
.data-table--daemon-dependencies-side,
.data-table--daemon-detail-leases,
.data-table--daemon-detail-events,
.data-table--daemon-lease-events,
.data-table--channel-bindings,
.data-table--connection-bindings,
.data-table--channels-detail-connections,
.data-table--channels-detail-accounts,
.data-table--channels-detail-dead-letters,
.data-table--channels-record-related,
.data-table--events-consumer-health,
.data-table--events-dead-letters,
.data-table--events-detail-contracts,
.data-table--events-detail-subscriptions,
.data-table--contracts,
.data-table--fallback-problems,
.data-table--access-fallback,
.data-table--model-availability,
.data-table--access-detail-checks,
.data-table--access-detail-usages,
.data-table--access-detail-setup,
.data-table--access-detail-events,
.data-table--service-sets,
.data-table--dependency-health,
.data-table--environment-secrets,
.data-table--backup-list,
.data-table--memory-config {
  --data-table-min-width: 760px;
}

.data-table--owners-volume,
.data-table--events-owners,
.data-table--consumer-health,
.data-table--mapping-failures,
.data-table--authentication-status,
.data-table--access-usage,
.data-table--auth-status,
.data-table--expiring-soon,
.data-table--tool-queue,
.data-table--long-running,
.data-table--top-used-skills,
.data-table--requirement-footprint,
.data-table--missing-capabilities,
.data-table--access-requirements,
.data-table--capability-requirements,
.data-table--conflicts,
.data-table--profile-usage,
.data-table--channels-profiles,
.data-table--skill-detail-requirements,
.data-table--skill-detail-resources,
.data-table--skill-detail-events,
.data-table--profile-resolution-trace,
.data-table--skill-set-resolution,
.data-table--skill-capabilities,
.data-table--skill-access,
.data-table--tool-access-assets,
.data-table--tool-contract-test,
.data-table--llm-capabilities,
.data-table--access-consumers,
.data-table--access-usage-summary,
.data-table--memory-consumers,
.data-table--memory-lifecycle-health,
.data-table--restore-audit,
.data-table--environment-groups {
  --data-table-min-width: 620px;
}

.data-table--run-queue th,
.data-table--run-queue td {
  padding-inline: 7px;
}

.data-table--run-queue .column-priority {
  width: 52px;
}

.data-table--run-queue .column-run-id {
  width: 92px;
}

.data-table--run-queue .column-lane-key {
  width: 106px;
}

.data-table--run-queue .column-enqueued-at {
  width: 95px;
}

.data-table--run-queue .column-agent-target {
  width: 98px;
}

.data-table--run-queue .column-wait-reason {
  width: 94px;
}

.data-table--run-queue .column-wait-time {
  width: 62px;
}

.data-table--run-queue .column-actions {
  width: 86px;
}

.data-table--tool-runs .column-result,
.data-table--failed-tools .column-error,
.data-table--mapping-failures .column-source {
  width: 180px;
  white-space: nowrap;
}

.data-table--tool-runs .column-source,
.data-table--failed-tools .column-source {
  width: 138px;
}

.data-table--ingress-queue th,
.data-table--ingress-queue td,
.data-table--recent-failures th,
.data-table--recent-failures td,
.data-table--ops-event-log th,
.data-table--ops-event-log td {
  padding-inline: 5px;
  font-size: 10px;
}

.data-table--ingress-queue .column-source {
  width: 58px;
}

.data-table--ingress-queue .column-intake-key {
  width: 74px;
}

.data-table--ingress-queue .column-received-at {
  width: 70px;
}

.data-table--ingress-queue .column-target-lane {
  width: 70px;
}

.data-table--ingress-queue .column-priority {
  width: 54px;
}

.data-table--ingress-queue .column-age {
  width: 38px;
}

.data-table--ingress-queue .column-actions {
  width: 42px;
}

.action-icons {
  display: inline-flex;
  gap: 7px;
  align-items: center;
}

.action-icons button,
.action-icons a {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  text-decoration: none;
}

.action-icons a:hover,
.cell-link:hover {
  color: var(--color-accent);
}

.cell-link {
  overflow: hidden;
  color: var(--color-accent);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-badge,
.cell-chip-row span {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 2px 6px;
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1;
}

.cell-badge--success {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.cell-badge--warning {
  background: color-mix(in srgb, var(--color-warning) 18%, transparent);
  color: var(--color-warning);
}

.cell-badge--danger {
  background: color-mix(in srgb, var(--color-danger) 18%, transparent);
  color: var(--color-danger);
}

.cell-badge--info {
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-accent);
}

.cell-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.cell-chip-row span {
  color: var(--text-muted);
}
</style>
