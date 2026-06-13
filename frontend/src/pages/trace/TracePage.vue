<script setup lang="ts">
import {
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  Filter,
  GitBranch,
  Search,
  XCircle,
} from "lucide-vue-next";
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import {
  formatDuration,
  formatLocalTime,
  formatNumber,
  formatRawKeyLabel,
  looksLikeRawKey,
} from "@/shared/i18n/formatters";
import { useI18n } from "@/shared/i18n";
import {
  promptPreviewContentText,
  stringifyPromptPreviewJson,
  type RunPromptInputPreview,
} from "@/shared/runtime/promptPreview";
import type {
  TraceEventView,
  TraceLinkedEntity,
  TraceSummaryView,
  WorkbenchLinkedEntityDetail,
} from "@/shared/runtime/types";
import UiBadge from "@/shared/ui/UiBadge.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import UiCard from "@/shared/ui/UiCard.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import XmlSourceViewer from "@/shared/ui/XmlSourceViewer.vue";
import {
  loadTraceContextRenderSnapshotById,
  loadTraceContextRenderSnapshot,
  loadTraceData,
  loadTraceInvocationPromptPreview,
  loadTraceLinkedEntityDetail,
  loadTracePromptPreview,
  type TraceContextRenderSnapshot,
} from "./api";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const loadingTrace = ref(false);
const loadError = ref<string | null>(null);
const traceSummary = ref<TraceSummaryView | null>(null);
const traceEvents = ref<TraceEventView[]>([]);
const graphTraceEvents = ref<TraceEventView[]>([]);
const selectedEventId = ref<string | null>(null);
const activeTraceView = ref<"timeline" | "graph">(traceViewFromQuery(route.query.view));
const contextRenderSnapshot = ref<TraceContextRenderSnapshot | null>(null);
const contextPromptPreview = ref<RunPromptInputPreview | null>(null);
const loadingContextSnapshot = ref(false);
const contextActualRequestTab = ref<ContextActualRequestTabId>("xml");
const selectedEntityDetailKey = ref<string | null>(null);
const selectedEntityDetail = ref<WorkbenchLinkedEntityDetail | null>(null);
const entityDetailLoading = ref(false);
const entityDetailError = ref<string | null>(null);
let contextSnapshotSerial = 0;

type ContextActualRequestTabId = "xml" | "messages" | "tool_schemas" | "options" | "attachments";
type ContextRouteDiagnosticTone = "success" | "warning" | "danger" | "info";
interface ContextRouteGroupRow {
  id: string;
  group: string;
  source: string;
  functions: string;
  defaultSchemas: string;
  visibility: string;
  tone: ContextRouteDiagnosticTone;
}
interface ContextRouteSchemaRow {
  id: string;
  schema: string;
  status: string;
  reason: string;
  priority: string;
  tone: ContextRouteDiagnosticTone;
}
interface ContextBrowserEvidencePathRow {
  id: string;
  path: string;
  status: string;
  schemas: string;
  count: string;
  tone: ContextRouteDiagnosticTone;
}
interface ContextBrowserWarningRow {
  id: string;
  warningType: string;
  code: string;
  latestTool: string;
  summary: string;
  tone: ContextRouteDiagnosticTone;
}

const activeEvents = computed(() => activeTraceView.value === "graph" ? graphTraceEvents.value : traceEvents.value);

const selectedEvent = computed(() => {
  return activeEvents.value.find((event) => event.event_id === selectedEventId.value)
    ?? activeEvents.value[0]
    ?? null;
});

const selectedEventIndex = computed(() => {
  if (!selectedEvent.value) return 0;
  return activeEvents.value.findIndex((event) => event.event_id === selectedEvent.value?.event_id) + 1;
});

const activeTraceId = computed(() => {
  const routeTraceId = typeof route.params.traceId === "string" ? route.params.traceId : null;
  return traceSummary.value?.trace_id ?? routeTraceId ?? "-";
});

const activeStepId = computed(() => {
  const raw = route.query.step_id;
  return typeof raw === "string" && raw.trim() ? raw.trim() : null;
});

const runId = computed(() => {
  return linkedEntity("run_id")?.id ?? selectedEvent.value?.trace.run_id ?? null;
});
const selectedLlmInvocationId = computed(() => {
  const value = selectedEvent.value?.trace.llm_invocation_id;
  return typeof value === "string" && value.trim() ? value.trim() : null;
});

const sessionKey = computed(() => {
  return linkedEntity("session_key")?.id ?? selectedEvent.value?.trace.session_key ?? null;
});

const turnId = computed(() => {
  return linkedEntity("turn_id")?.id ?? selectedEvent.value?.trace.turn_id ?? null;
});

const workbenchRoute = computed(() => {
  return runId.value ? `/workbench/runs/${encodeURIComponent(runId.value)}` : "/workbench";
});

const operationsRoute = computed(() => {
  const lane = laneForFamily(selectedEvent.value?.family);
  const family = lane === "channel" ? "channels" : lane === "observation" ? "events" : lane;
  return `/operations/${family || "orchestration"}`;
});

const statusTotals = computed(() => {
  return activeEvents.value.reduce<Record<string, number>>((totals, event) => {
    totals[event.status] = (totals[event.status] ?? 0) + 1;
    return totals;
  }, {});
});

const familyTotals = computed(() => {
  return activeEvents.value.reduce<Record<string, number>>((totals, event) => {
    const lane = laneForFamily(event.family);
    totals[lane] = (totals[lane] ?? 0) + 1;
    return totals;
  }, {});
});

const displaySummaryStatus = computed(() => activeTraceView.value === "graph" ? "failed" : traceSummary.value?.status);
const displaySummaryDuration = computed(() => activeTraceView.value === "graph" ? 168000 : traceSummary.value?.duration_ms);
const contextSnapshotRows = computed(() => {
  const snapshot = contextRenderSnapshot.value;
  if (!snapshot) return [];
  const requestMetadata = snapshotLlmRequestMetadata(snapshot);
  const metadata = snapshot.metadata;
  const renderedTokens = (
    metadataOptionalNumber(metadata.rendered_prompt_estimated_tokens)
    ?? promptEstimateTokenTotal(snapshot.estimate)
  );
  return [
    { label: t("trace.id.run"), value: shortId(snapshot.run_id, 24) },
    { label: t("workbench.context.revision"), value: String(snapshot.tree_revision) },
    { label: t("workbench.context.runtimeContractVersion"), value: textValue(requestMetadata.runtime_contract_version) },
    { label: t("workbench.context.runtimeContractHash"), value: shortId(textValue(requestMetadata.runtime_contract_hash, ""), 16) },
    { label: t("workbench.context.includedNodes"), value: formatNumber(snapshot.included_node_ids.length) },
    { label: t("workbench.context.mirroredNodes"), value: formatNumber(snapshot.mirrored_node_ids.length) },
    { label: t("workbench.context.includedRefs"), value: formatNumber(snapshot.included_refs.length) },
    { label: t("workbench.context.protocolRefs"), value: formatNumber(snapshot.protocol_required_refs.length) },
    { label: t("workbench.context.collapsedRefs"), value: formatNumber(snapshot.collapsed_refs.length) },
    { label: t("workbench.context.renderedPromptTokens"), value: formatNumber(renderedTokens) },
    { label: t("workbench.context.providerPromptTokens"), value: formatOptionalNumber(metadata.estimated_provider_prompt_tokens) },
    { label: t("workbench.context.directTranscriptTokens"), value: formatOptionalNumber(metadata.direct_transcript_estimated_tokens) },
    { label: t("workbench.context.schemaMirrorTokens"), value: formatOptionalNumber(metadata.mirrored_tool_schema_estimated_tokens) },
    { label: t("workbench.context.schemaMirrorBudget"), value: schemaMirrorBudgetValue(metadata) },
    { label: t("workbench.context.schemaMirrorSkipped"), value: formatOptionalNumber(metadata.tool_schema_mirror_skipped_count) },
    { label: t("table.createdAt"), value: formatLocalTime(snapshot.created_at) },
  ];
});
const contextSnapshotRiskRows = computed<Array<{
  label: string;
  value: string;
  tone: "success" | "warning" | "danger";
  detail: string;
}>>(() => {
  const metadata = contextRenderSnapshot.value?.metadata;
  if (!metadata) return [];
  const warnings = metadataNumber(metadata.session_range_warning_count);
  const blocked = metadataNumber(metadata.session_range_blocked_count);
  const limited = metadataNumber(metadata.session_range_limited_count);
  const budgetStatus = titleize(metadata.session_budget_status, "Ok");
  const budgetTone = blocked > 0 ? "danger" : warnings > 0 || limited > 0 ? "warning" : "success";
  return [
    {
      label: t("workbench.context.sessionBudgetStatus"),
      value: budgetStatus,
      tone: budgetTone,
      detail: t("workbench.context.sessionBudgetHelp"),
    },
    {
      label: t("workbench.context.rangeWarnings"),
      value: formatNumber(warnings),
      tone: warnings > 0 ? "warning" : "success",
      detail: t("workbench.context.rangeWarningsHelp"),
    },
    {
      label: t("workbench.context.rangeBlocked"),
      value: formatNumber(blocked),
      tone: blocked > 0 ? "danger" : "success",
      detail: t("workbench.context.rangeBlockedHelp"),
    },
    {
      label: t("workbench.context.rangeLimited"),
      value: formatNumber(limited),
      tone: limited > 0 ? "warning" : "success",
      detail: t("workbench.context.rangeLimitedHelp"),
    },
  ];
});
const contextRouteDiagnosticRows = computed<Array<{
  label: string;
  value: string;
  tone: ContextRouteDiagnosticTone;
  detail: string;
}>>(() => {
  const snapshot = contextRenderSnapshot.value;
  const preview = contextPromptPreview.value;
  if (!snapshot && !preview) return [];
  const requestMetadata = snapshot ? snapshotLlmRequestMetadata(snapshot) : previewLlmRequestMetadata(preview);
  const metadata = { ...requestMetadata, ...(snapshot?.metadata ?? preview?.context_render_metadata ?? {}) };
  const promptInput = snapshot ? snapshotRunPromptInputMetadata(snapshot) : previewRunPromptInputMetadata(preview);
  const messageCount = (
    metadataOptionalNumber(promptInput.message_count)
    ?? contextActualRequestMessages.value.length
  );
  const schemaCount = (
    metadataOptionalNumber(promptInput.tool_schema_count)
    ?? contextActualRequestToolSchemas.value.length
  );
  const mirroredCount = (
    metadataOptionalNumber(metadata.mirrored_tool_schema_count)
    ?? schemaCount
  );
  const maxMirrorCount = metadataOptionalNumber(metadata.tool_schema_mirror_max_count);
  const skippedCount = metadataNumber(metadata.tool_schema_mirror_skipped_count);
  const budgetStatus = textValue(metadata.tool_schema_mirror_budget_status, "ok");
  const budgetTone: ContextRouteDiagnosticTone = (
    skippedCount > 0 || budgetStatus !== "ok"
      ? "warning"
      : "success"
  );
  const browserGroups = browserGroupRefsValue(metadata.tool_schema_mirror_default_group_refs);
  const skippedSummary = skippedSchemaSummary(metadata, skippedCount);
  const capabilityVisibility = capabilityVisibilityValue(metadata);
  const toolResultCompaction = toolResultTruncationSummary(contextActualRequestMessages.value);
  const browserAffordance = browserInvestigationAffordanceSummary(metadata);
  const browserWarnings = browserInvestigationWarningSummary(metadata);
  const workPlanUpdates = workPlanUpdateSummary(metadata);
  const finalEvidence = finalResponseEvidenceSummary(metadata);
  return [
    {
      label: t("workbench.context.routeProviderShape"),
      value: `${formatNumber(messageCount)} ${t("workbench.context.routeMessagesShort")} · ${formatNumber(schemaCount)} ${t("workbench.context.routeSchemasShort")}`,
      tone: schemaCount > 0 ? "success" : "warning",
      detail: t("workbench.context.routeProviderShapeHelp"),
    },
    {
      label: t("workbench.context.routePlanUpdates"),
      value: workPlanUpdates.value,
      tone: workPlanUpdates.tone,
      detail: workPlanUpdates.detail,
    },
    {
      label: t("workbench.context.routeBrowserGroups"),
      value: browserGroups || t("text.none"),
      tone: browserGroups ? "success" : "warning",
      detail: schemaReasonSummary(metadata),
    },
    {
      label: t("workbench.context.routeBrowserAffordance"),
      value: browserAffordance.value,
      tone: browserAffordance.tone,
      detail: browserAffordance.detail,
    },
    {
      label: t("workbench.context.routeBrowserWarnings"),
      value: browserWarnings.value,
      tone: browserWarnings.tone,
      detail: browserWarnings.detail,
    },
    {
      label: t("workbench.context.routeFinalEvidence"),
      value: finalEvidence.value,
      tone: finalEvidence.tone,
      detail: finalEvidence.detail,
    },
    {
      label: t("workbench.context.routeSchemaMirror"),
      value: `${formatNumber(mirroredCount)}/${maxMirrorCount === null ? "-" : formatNumber(maxMirrorCount)} · ${formatNumber(skippedCount)} ${t("workbench.context.routeSkippedShort")}`,
      tone: budgetTone,
      detail: schemaMirrorBudgetValue(metadata),
    },
    {
      label: t("workbench.context.routeCapabilityVisibility"),
      value: capabilityVisibility,
      tone: metadataNumber(metadata.tool_schema_mirror_available_count) > 0 ? "info" : "warning",
      detail: t("workbench.context.routeCapabilityVisibilityHelp"),
    },
    {
      label: t("workbench.context.routeBudgetSplit"),
      value: routeBudgetSplitValue(metadata),
      tone: metadataNumber(metadata.estimated_provider_prompt_tokens) > 0 ? "info" : "warning",
      detail: t("workbench.context.routeBudgetSplitHelp"),
    },
    {
      label: t("workbench.context.routeSkipped"),
      value: skippedSummary,
      tone: skippedCount > 0 ? "warning" : "success",
      detail: skippedCount > 0 ? skippedSummary : t("workbench.context.routeSkippedNone"),
    },
    {
      label: t("workbench.context.routeToolResultTruncation"),
      value: toolResultCompaction.value,
      tone: toolResultCompaction.compactedCount > 0 ? "info" : "success",
      detail: t("workbench.context.routeToolResultTruncationHelp"),
    },
  ];
});
const contextRouteGroupRows = computed<ContextRouteGroupRow[]>(() => {
  const snapshot = contextRenderSnapshot.value;
  const preview = contextPromptPreview.value;
  if (!snapshot && !preview) return [];
  const requestMetadata = snapshot ? snapshotLlmRequestMetadata(snapshot) : previewLlmRequestMetadata(preview);
  const metadata = { ...requestMetadata, ...(snapshot?.metadata ?? preview?.context_render_metadata ?? {}) };
  const groups = Array.isArray(metadata.tool_schema_mirror_groups)
    ? metadata.tool_schema_mirror_groups.filter(isRecord)
    : [];
  return groups.map((group, index) => {
    const title = textValue(group.title ?? group.group_key ?? group.node_id, "-");
    const groupKey = textValue(group.group_key, "");
    const sourceId = textValue(group.source_id, "");
    const state = textValue(group.state, "-");
    const visibility = textValue(group.visibility, state);
    const defaultGroup = group.default_group === true;
    const defaultSchemaCount = (
      metadataOptionalNumber(group.default_schema_count)
      ?? (Array.isArray(group.default_schema_ids) ? group.default_schema_ids.length : 0)
    );
    return {
      id: textValue(group.node_id, `${sourceId}:${groupKey}:${index}`),
      group: groupKey ? `${title} · ${groupKey}` : title,
      source: sourceId ? shortId(sourceId, 28) : textValue(group.kind, "-"),
      functions: formatOptionalNumber(group.function_count, "0"),
      defaultSchemas: defaultGroup
        ? `${formatNumber(defaultSchemaCount)} · ${t("workbench.context.routeDefaultShort")}`
        : formatNumber(defaultSchemaCount),
      visibility: titleize(visibility, "-"),
      tone: defaultGroup ? "info" : state === "collapsed" ? "warning" : "success",
    };
  });
});
const contextRouteSchemaRows = computed<ContextRouteSchemaRow[]>(() => {
  const snapshot = contextRenderSnapshot.value;
  const preview = contextPromptPreview.value;
  if (!snapshot && !preview) return [];
  const requestMetadata = snapshot ? snapshotLlmRequestMetadata(snapshot) : previewLlmRequestMetadata(preview);
  const metadata = { ...requestMetadata, ...(snapshot?.metadata ?? preview?.context_render_metadata ?? {}) };
  const mirrored = Array.isArray(metadata.tool_schema_mirror_default_mirrored)
    ? metadata.tool_schema_mirror_default_mirrored.filter(isRecord)
    : [];
  const skipped = Array.isArray(metadata.tool_schema_mirror_skipped)
    ? metadata.tool_schema_mirror_skipped.filter(isRecord)
    : [];
  const rows: ContextRouteSchemaRow[] = [];
  for (const item of mirrored) {
    const schema = textValue(item.name ?? item.schema_name ?? item.node_id, "");
    if (!schema) continue;
    rows.push({
      id: `mirrored:${textValue(item.node_id, schema)}`,
      schema,
      status: t("workbench.context.routeMirrored"),
      reason: textValue(item.bootstrap_reason, t("text.none")),
      priority: formatOptionalNumber(item.priority, "-"),
      tone: "success",
    });
  }
  for (const item of skipped) {
    const schema = textValue(item.name ?? item.schema_name ?? item.node_id, "");
    if (!schema) continue;
    rows.push({
      id: `skipped:${textValue(item.node_id, schema)}:${textValue(item.reason, "")}`,
      schema,
      status: t("workbench.context.routeSkippedShort"),
      reason: textValue(item.reason ?? item.bootstrap_reason, t("text.none")),
      priority: formatOptionalNumber(item.priority, "-"),
      tone: "warning",
    });
  }
  return rows.slice(0, 32);
});
const contextBrowserEvidencePathRows = computed<ContextBrowserEvidencePathRow[]>(() => {
  const metadata = contextRouteMetadata();
  const ladder = Array.isArray(metadata.browser_evidence_path_ladder)
    ? metadata.browser_evidence_path_ladder.filter(isRecord)
    : [];
  return ladder.map((item, index) => {
    const path = textValue(item.path, "-");
    const status = textValue(item.status, "-");
    const schemaNames = metadataStringList(item.schemas);
    return {
      id: `${path}:${index}`,
      path: titleize(path, "-"),
      status: titleize(status, "-"),
      schemas: schemaNames.slice(0, 3).join(", ") || "-",
      count: formatOptionalNumber(item.schema_count, "0"),
      tone: status === "present" ? "success" : "warning",
    };
  });
});
const contextBrowserWarningRows = computed<ContextBrowserWarningRow[]>(() => {
  const metadata = contextRouteMetadata();
  const warnings = Array.isArray(metadata.browser_investigation_warnings)
    ? metadata.browser_investigation_warnings.filter(isRecord)
    : [];
  return warnings.map((item, index) => {
    const severity = textValue(item.severity, "warning");
    const warningTypes = metadataStringList(item.warning_types);
    return {
      id: textValue(item.node_id, `${textValue(item.code, "warning")}:${index}`),
      warningType: warningTypes.map((value) => titleize(value, value)).join(", ") || "-",
      code: textValue(item.code, "-"),
      latestTool: textValue(item.latest_tool, "-"),
      summary: textValue(item.summary, "-"),
      tone: severity === "error" || severity === "danger" ? "danger" : "warning",
    };
  });
});
const contextSnapshotDiagnosticRows = computed(() => {
  const snapshot = contextRenderSnapshot.value;
  if (!snapshot) return [];
  const metadata = snapshot.metadata;
  const promptInput = snapshotRunPromptInputMetadata(snapshot);
  const requestMetadata = snapshotLlmRequestMetadata(snapshot);
  return [
    {
      label: t("table.invocationId"),
      value: shortId(textValue(contextPromptPreview.value?.provider_request_options?.invocation_id, ""), 24),
    },
    {
      label: t("workbench.context.requestMetadataSnapshot"),
      value: shortId(textValue(requestMetadata.context_render_snapshot_id, snapshot.id), 24),
    },
    {
      label: t("workbench.context.treeSchemaVersion"),
      value: textValue(requestMetadata.tree_schema_version ?? metadata.tree_schema_version),
    },
    {
      label: t("workbench.context.rootNodes"),
      value: textValue(metadata.root_node_ids),
    },
    {
      label: t("workbench.context.topRenderedNodes"),
      value: topRenderedNodesValue(metadata),
    },
    {
      label: t("workbench.context.requestMetadataHistory"),
      value: titleize(requestMetadata.context_history_delivery, "-"),
    },
    {
      label: t("workbench.context.runtimeContractVersion"),
      value: textValue(requestMetadata.runtime_contract_version),
    },
    {
      label: t("workbench.context.runtimeContractHash"),
      value: shortId(textValue(requestMetadata.runtime_contract_hash, ""), 24),
    },
    {
      label: t("workbench.context.requestMetadataMirroredSchemas"),
      value: formatOptionalNumber(requestMetadata.mirrored_tool_schema_count),
    },
    {
      label: t("workbench.context.requestMetadataMirroredNodes"),
      value: formatOptionalNumber(requestMetadata.mirrored_node_count),
    },
    {
      label: t("workbench.context.historyDelivery"),
      value: titleize(metadata.history_delivery, "-"),
    },
    {
      label: t("workbench.context.directTranscriptMessages"),
      value: formatOptionalNumber(metadata.direct_transcript_message_count),
    },
    {
      label: t("workbench.context.directTranscriptRoles"),
      value: textValue(metadata.direct_transcript_roles),
    },
    {
      label: t("workbench.context.treeSessionMessages"),
      value: formatOptionalNumber(metadata.tree_session_message_count),
    },
    {
      label: t("workbench.context.toolInteractions"),
      value: formatOptionalNumber(metadata.tree_tool_interaction_count),
    },
    {
      label: t("workbench.context.foldedHistory"),
      value: formatOptionalNumber(metadata.folded_history_node_count),
    },
    {
      label: t("workbench.context.sessionTokens"),
      value: formatOptionalNumber(metadata.session_estimated_text_tokens),
    },
    {
      label: t("workbench.context.sessionBudgetStatus"),
      value: titleize(metadata.session_budget_status, "-"),
    },
    {
      label: t("workbench.context.rangeWarnings"),
      value: formatOptionalNumber(metadata.session_range_warning_count),
    },
    {
      label: t("workbench.context.rangeBlocked"),
      value: formatOptionalNumber(metadata.session_range_blocked_count),
    },
    {
      label: t("workbench.context.rangeLimited"),
      value: formatOptionalNumber(metadata.session_range_limited_count),
    },
    {
      label: t("workbench.context.artifactBlocks"),
      value: formatOptionalNumber(metadata.artifact_content_block_count),
    },
    {
      label: t("workbench.context.providerMessages"),
      value: formatOptionalNumber(promptInput.message_count),
    },
    {
      label: t("workbench.context.providerToolSchemas"),
      value: formatOptionalNumber(promptInput.tool_schema_count),
    },
    {
      label: t("workbench.context.llm"),
      value: textValue(promptInput.llm_id),
    },
    {
      label: t("workbench.context.llmCapabilities"),
      value: textValue(promptInput.llm_capabilities, t("text.none")),
    },
    {
      label: t("workbench.context.currentInbound"),
      value: shortId(textValue(metadata.current_inbound_message_id, ""), 24),
    },
    {
      label: t("trace.contextSnapshot.currentInboundNode"),
      value: shortId(textValue(metadata.current_inbound_node_id, ""), 24),
    },
  ];
});
const contextSnapshotPromptCharCount = computed(() => (
  contextActualRequestXmlSource.value.length
));
const contextPreviewPromptBody = computed(() => {
  const messages = contextPromptPreview.value?.messages ?? [];
  for (const message of messages) {
    if (message.metadata?.prompt_block_kind !== "context_workspace") continue;
    const text = promptPreviewContentText(message.content).trim();
    if (text) return text;
  }
  return "";
});
const contextActualRequestXmlSource = computed(() => (
  contextRenderSnapshot.value?.prompt_body ?? contextPreviewPromptBody.value
));
const contextActualRequestProviderAttachments = computed<Record<string, unknown>>(() => (
  firstNonEmptyRecord(
    contextPromptPreview.value?.provider_attachments,
    contextRenderSnapshot.value?.provider_attachments,
  )
));
const contextActualRequestProviderOptions = computed<Record<string, unknown>>(() => (
  contextPromptPreview.value?.provider_request_options ?? {}
));
const contextActualRequestMessages = computed<unknown[]>(() => (
  contextPromptPreview.value?.messages ?? []
));
const contextActualRequestToolSchemas = computed<unknown[]>(() => {
  const previewSchemas = contextPromptPreview.value?.tool_schemas ?? [];
  if (previewSchemas.length > 0) return previewSchemas;
  const attachmentSchemas = contextActualRequestProviderAttachments.value.tool_schemas;
  return Array.isArray(attachmentSchemas) ? attachmentSchemas : [];
});
const contextActualRequestTabs = computed<Array<{ id: ContextActualRequestTabId; label: string; count: string }>>(() => [
  {
    id: "xml",
    label: t("workbench.context.requestTab.xml"),
    count: formatNumber(contextActualRequestXmlSource.value.length),
  },
  {
    id: "messages",
    label: t("workbench.context.requestTab.messages"),
    count: formatNumber(contextActualRequestMessages.value.length),
  },
  {
    id: "tool_schemas",
    label: t("workbench.context.requestTab.toolSchemas"),
    count: formatNumber(contextActualRequestToolSchemas.value.length),
  },
  {
    id: "options",
    label: t("workbench.context.requestTab.options"),
    count: formatNumber(Object.keys(contextActualRequestProviderOptions.value).length),
  },
  {
    id: "attachments",
    label: t("workbench.context.requestTab.attachments"),
    count: formatNumber(Object.keys(contextActualRequestProviderAttachments.value).length),
  },
]);
const contextActualRequestJson = computed(() => {
  if (contextActualRequestTab.value === "messages") {
    return stringifyPromptPreviewJson(contextActualRequestMessages.value);
  }
  if (contextActualRequestTab.value === "tool_schemas") {
    return stringifyPromptPreviewJson(contextActualRequestToolSchemas.value);
  }
  if (contextActualRequestTab.value === "options") {
    return stringifyPromptPreviewJson(contextActualRequestProviderOptions.value);
  }
  return stringifyPromptPreviewJson(contextActualRequestProviderAttachments.value);
});
const contextSnapshotSessionNodeRows = computed(() => {
  const refs = contextRenderSnapshot.value?.metadata.session_message_node_refs;
  if (!Array.isArray(refs)) return [];
  return refs
    .filter(isRecord)
    .map((ref) => ({
      nodeId: textValue(ref.node_id, ""),
      sequence: textValue(ref.sequence_no, "-"),
      sessionId: textValue(ref.session_id, "-"),
    }))
    .filter((ref) => ref.nodeId);
});
const contextSnapshotSessionNodePreviewRows = computed(() => (
  contextSnapshotSessionNodeRows.value.slice(0, 4)
));
const contextSnapshotHiddenSessionNodeCount = computed(() => (
  Math.max(contextSnapshotSessionNodeRows.value.length - contextSnapshotSessionNodePreviewRows.value.length, 0)
));
const contextSnapshotRefRows = computed(() => {
  const snapshot = contextRenderSnapshot.value;
  if (!snapshot) return [];
  const refs = snapshot.protocol_required_refs.length
    ? snapshot.protocol_required_refs
    : snapshot.included_refs;
  return refs
    .filter(isRecord)
    .map((ref, index) => ({
      id: textValue(ref.item_id ?? ref.owner_id ?? ref.node_id, `ref-${index}`),
      kind: titleize(ref.kind ?? ref.owner_kind, "-"),
      sequence: textValue(ref.sequence_no, "-"),
      owner: textValue(ref.owner_module ?? ref.source_module, "-"),
      callId: shortId(textValue(ref.tool_call_id, ""), 24),
    }))
    .filter((row) => row.id)
    .slice(0, 4);
});
const contextSnapshotHiddenRefCount = computed(() => {
  const snapshot = contextRenderSnapshot.value;
  if (!snapshot) return 0;
  const sourceCount = snapshot.protocol_required_refs.length
    ? snapshot.protocol_required_refs.length
    : snapshot.included_refs.length;
  return Math.max(sourceCount - contextSnapshotRefRows.value.length, 0);
});
const graphVisibleEvents = computed(() => graphTraceEvents.value.filter((event) => event.key_event));
const timelineAxisStyle = computed(() => ({
  "--trace-axis-height": `${Math.max(traceEvents.value.length - 1, 0) * 72}px`,
}));

const graphLanes = computed(() => {
  const lanes = [
    { id: "channel", label: t("trace.family.channel"), tone: "info" },
    { id: "orchestration", label: t("trace.family.orchestration"), tone: "neutral" },
    { id: "llm", label: t("trace.family.llm"), tone: "info" },
    { id: "tool", label: t("trace.family.tool"), tone: "warning" },
    { id: "events", label: t("trace.family.events"), tone: "danger" },
    { id: "observation", label: t("trace.family.observation"), tone: "success" },
    { id: "error", label: t("trace.family.error"), tone: "danger" },
  ] as const;
  return lanes.map((lane) => ({
    ...lane,
    count: graphVisibleEvents.value.filter((event) => laneForFamily(event.family) === lane.id).length,
  }));
});

const graphNodes = computed(() => {
  const laneIndex: Record<string, number> = {
    channel: 0,
    orchestration: 1,
    llm: 2,
    tool: 3,
    events: 4,
    observation: 5,
    error: 6,
  };
  const laneCounts = graphVisibleEvents.value.reduce<Record<string, number>>((counts, event) => {
    const lane = laneForFamily(event.family);
    counts[lane] = (counts[lane] ?? 0) + 1;
    return counts;
  }, {});
  const laneOrders: Record<string, number> = {};
  return graphVisibleEvents.value.map((event) => {
    const lane = laneForFamily(event.family);
    const order = laneOrders[lane] ?? 0;
    laneOrders[lane] = order + 1;
    const count = laneCounts[lane] ?? 1;
    const left = count === 1 ? 48 : 8 + order * (54 / Math.max(count - 1, 1));
    const top = 3 + laneIndex[lane] * 13.8;
    return {
      event,
      lane,
      tone: event.status === "failed" ? "danger" : toneForFamily(event.family),
      left,
      top,
      style: {
        left: `${left}%`,
        top: `${top}%`,
      },
    };
  });
});

const graphEdges = computed(() => {
  const nodes = graphNodes.value;
  return nodes.slice(0, -1).map((node, index) => {
    const next = nodes[index + 1];
    const x1 = node.left + 13;
    const y1 = node.top + 5;
    const x2 = next.left + 13;
    const y2 = next.top + 5;
    const deltaX = x2 - x1;
    const deltaY = y2 - y1;
    const length = Math.sqrt(deltaX * deltaX + deltaY * deltaY);

    return {
      id: `${node.event.event_id}-${next.event.event_id}`,
      dashed: index % 3 === 2,
      style: {
        left: `${x1}%`,
        top: `${y1}%`,
        width: `${length}%`,
        transform: `rotate(${Math.atan2(deltaY, deltaX)}rad)`,
      },
    };
  });
});

watch(
  () => [route.params.traceId, route.query.step_id],
  async ([traceIdParam, stepIdParam]) => {
    loadingTrace.value = true;
    loadError.value = null;
    try {
      const traceId = typeof traceIdParam === "string" ? traceIdParam : null;
      const stepId = typeof stepIdParam === "string" ? stepIdParam : null;
      const loaded = await loadTraceData(traceId, stepId);
      traceSummary.value = loaded.summary;
      traceEvents.value = loaded.events;
      graphTraceEvents.value = loaded.graphEvents;
      selectedEventId.value = preferredEventId(activeTraceView.value);
      resetLinkedEntityDetail();
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : String(error);
    } finally {
      loadingTrace.value = false;
    }
  },
  { immediate: true },
);

watch(
  () => route.query.view,
  (view) => {
    activeTraceView.value = traceViewFromQuery(view);
    selectedEventId.value = preferredEventId(activeTraceView.value);
    resetLinkedEntityDetail();
  },
);

watch(selectedEventId, () => {
  resetLinkedEntityDetail();
});

watch(
  () => [runId.value, selectedLlmInvocationId.value],
  ([nextRunId]) => {
    void refreshTraceContextRenderSnapshot(
      typeof nextRunId === "string" ? nextRunId : null,
    );
  },
  { immediate: true },
);

async function refreshTraceContextRenderSnapshot(nextRunId: string | null): Promise<void> {
  const serial = ++contextSnapshotSerial;
  if (!nextRunId) {
    contextRenderSnapshot.value = null;
    contextPromptPreview.value = null;
    loadingContextSnapshot.value = false;
    return;
  }

  loadingContextSnapshot.value = true;
  contextRenderSnapshot.value = null;
  contextPromptPreview.value = null;
  const invocationId = selectedLlmInvocationId.value;
  let preview = invocationId
    ? await loadTraceInvocationPromptPreview(invocationId, nextRunId)
    : await loadTracePromptPreview(nextRunId);
  if (invocationId && !preview) {
    preview = await loadTracePromptPreview(nextRunId);
  }
  const snapshotId = typeof preview?.context_render_snapshot_id === "string"
    ? preview.context_render_snapshot_id.trim()
    : "";
  const snapshot = snapshotId
    ? await loadTraceContextRenderSnapshotById(snapshotId)
    : await loadTraceContextRenderSnapshot(nextRunId);
  if (serial === contextSnapshotSerial) {
    contextRenderSnapshot.value = snapshot;
    contextPromptPreview.value = preview;
    loadingContextSnapshot.value = false;
  }
}

function traceViewFromQuery(view: unknown): "timeline" | "graph" {
  return view === "graph" ? "graph" : "timeline";
}

function setTraceView(view: "timeline" | "graph"): void {
  activeTraceView.value = view;
  void router.replace({
    query: {
      ...route.query,
      view: view === "graph" ? "graph" : undefined,
    },
  });
}

function preferredEventId(view: "timeline" | "graph"): string | null {
  const events = view === "graph" ? graphTraceEvents.value : traceEvents.value;
  const preferredName = view === "graph" ? "Tool Run Failed" : "Tool Run Succeeded";
  return events.find((event) => event.name === preferredName)?.event_id
    ?? events[0]?.event_id
    ?? null;
}

function toneForStatus(status: string | null | undefined): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "success" || status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "waiting" || status === "queued") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

function toneForFamily(family: string | null | undefined): "neutral" | "info" | "success" | "warning" | "danger" {
  if (family === "tool") return "warning";
  if (family === "llm") return "info";
  if (family === "observation") return "success";
  if (family === "events" || family === "error") return "danger";
  return "neutral";
}

function laneForFamily(family: string | null | undefined): string {
  if (family === "channel") return "channel";
  if (family === "llm") return "llm";
  if (family === "tool") return "tool";
  if (family === "events") return "events";
  if (family === "observation") return "observation";
  if (family === "error") return "error";
  return "orchestration";
}

function statusLabel(status: string | null | undefined): string {
  return t(`status.${status || "unknown"}`);
}

function eventDisplayName(event: TraceEventView): string {
  const key = {
    "User Message Received": "userMessageReceived",
    "Run Created": "runCreated",
    "LLM Invocation Started": "llmInvocationStarted",
    "Tool Call Requested": "toolCallRequested",
    "Tool Run Created": "toolRunCreated",
    "Tool Run Succeeded": "toolRunSucceeded",
    "Tool Run Failed": "toolRunFailed",
    "Result Applied to Run Step": "resultApplied",
    "Response Delivered": "responseDelivered",
    "Tool Run Created Event": "createdEvent",
    "Error Event Generated": "errorGenerated",
    "Observation Failed": "observationFailed",
    "Artifact Observation Skipped": "artifactObservationSkipped",
    "Run Marked Failed": "runMarkedFailed",
    "Failure Delivered": "failureDelivered",
  }[event.name];
  if (key) return t(`trace.eventName.${key}`);
  return looksLikeRawKey(event.name) ? formatRawKeyLabel(event.name) : event.name;
}

function shortId(value: string | null | undefined, maxLength = 18): string {
  if (!value) return "-";
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(maxLength - 3, 1))}...`;
}

function textValue(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value.trim() || fallback;
  if (Array.isArray(value)) {
    const items = value.map((item) => textValue(item, "")).filter(Boolean);
    return items.length ? items.join(", ") : fallback;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return fallback;
  }
}

function formatOptionalNumber(value: unknown, fallback = "-"): string {
  if (typeof value === "number" && Number.isFinite(value)) return formatNumber(value);
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return formatNumber(parsed);
  }
  return fallback;
}

function metadataOptionalNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function metadataNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function metadataStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => textValue(item, ""))
      .filter(Boolean);
  }
  const text = textValue(value, "");
  return text ? [text] : [];
}

function promptEstimateTokenTotal(
  estimate: {
    text_tokens?: unknown;
    tool_schema_tokens?: unknown;
    file_tokens?: unknown;
  } | null | undefined,
): number {
  if (!estimate) return 0;
  return metadataNumber(estimate.text_tokens) + metadataNumber(estimate.tool_schema_tokens) + metadataNumber(estimate.file_tokens);
}

function schemaMirrorBudgetValue(metadata: Record<string, unknown>): string {
  const status = titleize(metadata.tool_schema_mirror_budget_status, "Ok");
  const mirrored = formatOptionalNumber(metadata.mirrored_tool_schema_count, "0");
  const maxCount = formatOptionalNumber(metadata.tool_schema_mirror_max_count);
  const tokens = formatOptionalNumber(metadata.mirrored_tool_schema_estimated_tokens, "0");
  const maxTokens = formatOptionalNumber(metadata.tool_schema_mirror_max_estimated_tokens);
  return `${status} · ${mirrored}/${maxCount} · ${tokens}/${maxTokens}`;
}

function browserGroupRefsValue(value: unknown): string {
  if (!Array.isArray(value)) return "";
  const labels = value
    .filter(isRecord)
    .filter((row) => textValue(row.source_id, "").includes("browser"))
    .map((row) => {
      const source = shortId(textValue(row.source_id, ""), 28);
      const group = textValue(row.group_key, "");
      const reason = textValue(row.reason, "");
      return [source, group, reason].filter(Boolean).join(" / ");
    })
    .filter(Boolean);
  return labels.slice(0, 3).join(" · ");
}

function schemaReasonSummary(metadata: Record<string, unknown>): string {
  const reasons = isRecord(metadata.tool_schema_mirror_default_schema_reasons)
    ? metadata.tool_schema_mirror_default_schema_reasons
    : {};
  const mirrored = Array.isArray(metadata.tool_schema_mirror_default_mirrored)
    ? metadata.tool_schema_mirror_default_mirrored.filter(isRecord)
    : [];
  const names = mirrored
    .map((item) => textValue(item.name, ""))
    .filter(Boolean)
    .slice(0, 4);
  if (names.length) {
    return names
      .map((name) => {
        const reason = textValue(reasons[name], "");
        return reason ? `${name} (${reason})` : name;
      })
      .join(" · ");
  }
  return t("workbench.context.routeBrowserGroupsHelp");
}

function browserInvestigationAffordanceSummary(
  metadata: Record<string, unknown>,
): { value: string; tone: ContextRouteDiagnosticTone; detail: string } {
  const status = textValue(metadata.browser_investigation_affordance_status, "");
  const routeBias = textValue(metadata.browser_investigation_route_bias, "");
  const present = metadataStringList(metadata.browser_investigation_present_paths);
  const missing = metadataStringList(metadata.browser_investigation_missing_paths);
  const schemaCount = metadataStringList(metadata.browser_investigation_schema_names).length;
  const tone: ContextRouteDiagnosticTone = status === "ok"
    ? "success"
    : status === "dom_form_only" || status === "missing_browser_tools"
      ? "danger"
      : "warning";
  const value = [status ? titleize(status) : "", routeBias && routeBias !== status ? titleize(routeBias) : ""]
    .filter(Boolean)
    .join(" · ");
  const detail = [
    `${t("workbench.context.routePresentPathsShort")} ${present.length ? present.join(", ") : "-"}`,
    `${t("workbench.context.routeMissingPathsShort")} ${missing.length ? missing.join(", ") : "-"}`,
    `${t("workbench.context.routeSchemasVisibleShort")} ${formatNumber(schemaCount)}`,
  ].join(" · ");
  return {
    value: value || t("text.none"),
    tone,
    detail: value ? detail : t("workbench.context.routeBrowserAffordanceHelp"),
  };
}

function browserInvestigationWarningSummary(
  metadata: Record<string, unknown>,
): { value: string; tone: ContextRouteDiagnosticTone; detail: string } {
  const count = metadataNumber(metadata.browser_investigation_warning_count);
  const terminalFactGap = metadata.browser_evidence_path_no_terminal_fact === true;
  const warningTypes = metadataStringList(metadata.browser_investigation_warning_types);
  const value = count > 0
    ? `${formatNumber(count)} · ${warningTypes.map((item) => titleize(item, item)).slice(0, 3).join(", ")}`
    : terminalFactGap
      ? t("workbench.context.routeEvidencePathNoTerminalFact")
      : t("text.none");
  const detailParts = [
    terminalFactGap ? t("workbench.context.routeEvidencePathNoTerminalFactHelp") : "",
    warningTypes.length ? warningTypes.join(", ") : "",
  ].filter(Boolean);
  return {
    value,
    tone: count > 0 || terminalFactGap ? "warning" : "success",
    detail: detailParts.join(" · ") || t("workbench.context.routeBrowserWarningsHelp"),
  };
}

function workPlanUpdateSummary(
  metadata: Record<string, unknown>,
): { value: string; tone: ContextRouteDiagnosticTone; detail: string } {
  const count = metadataNumber(metadata.work_plan_update_count);
  const phase = textValue(metadata.work_plan_phase, "");
  const status = textValue(metadata.work_plan_status, "");
  const reason = textValue(metadata.work_plan_update_reason, "");
  const tone: ContextRouteDiagnosticTone = count > 6
    ? "warning"
    : count > 0
      ? "info"
      : "success";
  const detail = [
    status ? `${t("workbench.context.routePlanStatusShort")} ${titleize(status)}` : "",
    reason ? `${t("workbench.context.routePlanReasonShort")} ${titleize(reason)}` : "",
    metadata.work_plan_phase_changed === true
      ? t("workbench.context.routePlanPhaseChanged")
      : "",
  ].filter(Boolean).join(" · ");
  return {
    value: phase ? `${formatNumber(count)} · ${phase}` : formatNumber(count),
    tone,
    detail: detail || t("workbench.context.routePlanUpdatesHelp"),
  };
}

function finalResponseEvidenceSummary(
  metadata: Record<string, unknown>,
): { value: string; tone: ContextRouteDiagnosticTone; detail: string } {
  const required = metadata.final_response_requires_evidence_path === true;
  const browserPaths = metadataStringList(metadata.browser_verified_evidence_paths);
  const verifiedPaths = metadataStringList(metadata.verified_evidence_paths);
  const paths = browserPaths.length ? browserPaths : verifiedPaths;
  if (!required) {
    return {
      value: t("workbench.context.routeFinalEvidenceNotRequired"),
      tone: "info",
      detail: t("workbench.context.routeFinalEvidenceHelp"),
    };
  }
  return {
    value: paths.length
      ? `${t("workbench.context.routeFinalEvidenceRequired")} · ${paths.join(", ")}`
      : t("workbench.context.routeFinalEvidenceRequired"),
    tone: paths.length ? "success" : "warning",
    detail: t("workbench.context.routeFinalEvidenceRequiredHelp"),
  };
}

function skippedSchemaSummary(
  metadata: Record<string, unknown>,
  skippedCount: number,
): string {
  if (skippedCount <= 0) return t("workbench.context.routeSkippedNone");
  const byReason = isRecord(metadata.tool_schema_mirror_skipped_by_reason)
    ? metadata.tool_schema_mirror_skipped_by_reason
    : {};
  const reasonLabels = Object.entries(byReason)
    .slice(0, 3)
    .map(([reason, count]) => `${titleize(reason, reason)} ${formatOptionalNumber(count, "0")}`);
  if (reasonLabels.length) return reasonLabels.join(" · ");
  const skipped = Array.isArray(metadata.tool_schema_mirror_skipped)
    ? metadata.tool_schema_mirror_skipped.filter(isRecord)
    : [];
  const skippedNames = skipped
    .map((item) => textValue(item.name ?? item.tool_name ?? item.node_id, ""))
    .filter(Boolean)
    .slice(0, 3);
  if (skippedNames.length) return skippedNames.join(" · ");
  return `${formatNumber(skippedCount)} ${t("workbench.context.routeSkippedShort")}`;
}

function routeBudgetSplitValue(metadata: Record<string, unknown>): string {
  const direct = formatOptionalNumber(metadata.direct_transcript_estimated_tokens, "0");
  const tree = formatOptionalNumber(metadata.rendered_prompt_estimated_tokens, "0");
  const schemas = formatOptionalNumber(metadata.mirrored_tool_schema_estimated_tokens, "0");
  return `${t("workbench.context.routeDirectShort")} ${direct} · ${t("workbench.context.routeTreeShort")} ${tree} · ${t("workbench.context.routeSchemasShort")} ${schemas}`;
}

function capabilityVisibilityValue(metadata: Record<string, unknown>): string {
  const available = formatOptionalNumber(metadata.tool_schema_mirror_available_count, "0");
  const enabled = formatOptionalNumber(metadata.tool_schema_mirror_enabled_candidate_count, "0");
  const defaultMirrored = formatOptionalNumber(metadata.tool_schema_mirror_default_mirrored_count, "0");
  const defaultRequested = formatOptionalNumber(metadata.tool_schema_mirror_default_requested_count, "0");
  const duplicate = formatOptionalNumber(metadata.tool_schema_mirror_duplicate_count, "0");
  return `${t("workbench.context.routeAvailableShort")} ${available} · ${t("workbench.context.routeEnabledShort")} ${enabled} · ${t("workbench.context.routeDefaultShort")} ${defaultMirrored}/${defaultRequested} · ${t("workbench.context.routeDuplicateShort")} ${duplicate}`;
}

function toolResultTruncationSummary(messages: unknown[]): { value: string; compactedCount: number } {
  let compactedCount = 0;
  let omittedChars = 0;
  let omittedCount = 0;
  for (const message of messages) {
    if (!isRecord(message)) continue;
    const role = textValue(message.role, "");
    if (role && role !== "tool") continue;
    const text = promptPreviewContentText(message.content);
    if (!text.includes("omitted_from_provider_transcript")) continue;
    compactedCount += 1;
    omittedChars += sumLineNumbers(text, /omitted_chars:\s*(\d+)/g);
    omittedCount += sumLineNumbers(text, /omitted_count:\s*(\d+)/g);
  }
  if (compactedCount <= 0) {
    return {
      value: t("workbench.context.routeToolResultTruncationNone"),
      compactedCount,
    };
  }
  const parts = [`${formatNumber(compactedCount)} ${t("workbench.context.routeCompactedShort")}`];
  if (omittedChars > 0) {
    parts.push(`${formatNumber(omittedChars)} ${t("workbench.context.routeOmittedCharsShort")}`);
  }
  if (omittedCount > 0) {
    parts.push(`${formatNumber(omittedCount)} ${t("workbench.context.routeSkippedShort")}`);
  }
  return {
    value: parts.join(" · "),
    compactedCount,
  };
}

function sumLineNumbers(text: string, pattern: RegExp): number {
  return Array.from(text.matchAll(pattern))
    .map((match) => Number(match[1]))
    .filter(Number.isFinite)
    .reduce((total, value) => total + value, 0);
}

function topRenderedNodesValue(metadata: Record<string, unknown>): string {
  const rows = Array.isArray(metadata.top_rendered_nodes)
    ? metadata.top_rendered_nodes
    : [];
  const labels = rows
    .filter(isRecord)
    .slice(0, 3)
    .map((row) => {
      const nodeId = shortId(textValue(row.node_id, ""), 24);
      const tokens = formatOptionalNumber(row.text_tokens, "0");
      return `${nodeId} ${tokens}`;
    })
    .filter((value) => value.trim());
  return labels.length ? labels.join(" · ") : "-";
}

function snapshotRunPromptInputMetadata(snapshot: TraceContextRenderSnapshot): Record<string, unknown> {
  const value = snapshot.provider_attachments.prompt_input;
  return isRecord(value) ? value : {};
}

function snapshotRuntimeContractMetadata(snapshot: TraceContextRenderSnapshot): Record<string, unknown> {
  const value = snapshot.metadata.runtime_contract;
  return isRecord(value) ? value : {};
}

function snapshotLlmRequestMetadata(snapshot: TraceContextRenderSnapshot): Record<string, unknown> {
  const contract = snapshotRuntimeContractMetadata(snapshot);
  return {
    prompt_input: snapshot.provider_attachments.prompt_input,
    tree_schema_version: snapshot.metadata.tree_schema_version,
    context_render_snapshot_id: snapshot.id,
    context_history_delivery: snapshot.metadata.history_delivery,
    mirrored_tool_schema_count: snapshot.metadata.mirrored_tool_schema_count,
    mirrored_tool_schema_estimated_tokens: snapshot.metadata.mirrored_tool_schema_estimated_tokens,
    tool_schema_mirror_budget_status: snapshot.metadata.tool_schema_mirror_budget_status,
    tool_schema_mirror_skipped_count: snapshot.metadata.tool_schema_mirror_skipped_count,
    tool_schema_mirror_max_count: snapshot.metadata.tool_schema_mirror_max_count,
    tool_schema_mirror_max_estimated_tokens: snapshot.metadata.tool_schema_mirror_max_estimated_tokens,
    rendered_prompt_estimated_tokens: snapshot.metadata.rendered_prompt_estimated_tokens,
    direct_transcript_estimated_tokens: snapshot.metadata.direct_transcript_estimated_tokens,
    estimated_provider_prompt_tokens: snapshot.metadata.estimated_provider_prompt_tokens,
    duplicate_tool_delivery_risk: snapshot.metadata.duplicate_tool_delivery_risk,
    session_budget_status: snapshot.metadata.session_budget_status,
    mirrored_node_count: snapshot.metadata.mirrored_node_count,
    runtime_contract: contract,
    runtime_contract_version: snapshot.metadata.runtime_contract_version ?? contract.contract_version,
    runtime_contract_hash: snapshot.metadata.runtime_contract_hash ?? contract.content_hash,
  };
}

function previewRunPromptInputMetadata(preview: RunPromptInputPreview | null): Record<string, unknown> {
  const value = preview?.provider_attachments?.prompt_input;
  return isRecord(value) ? value : {};
}

function previewLlmRequestMetadata(preview: RunPromptInputPreview | null): Record<string, unknown> {
  const metadata = preview?.context_render_metadata ?? {};
  const requestMetadata = isRecord(preview?.provider_request_options?.request_metadata)
    ? preview.provider_request_options.request_metadata
    : {};
  const contract = isRecord(metadata.runtime_contract) ? metadata.runtime_contract : {};
  return {
    prompt_input: preview?.provider_attachments?.prompt_input,
    tree_schema_version: metadata.tree_schema_version,
    context_render_snapshot_id: preview?.context_render_snapshot_id,
    context_history_delivery: metadata.history_delivery,
    mirrored_tool_schema_count: metadata.mirrored_tool_schema_count,
    mirrored_node_count: metadata.mirrored_node_count,
    runtime_contract: contract,
    runtime_contract_version: metadata.runtime_contract_version ?? contract.contract_version,
    runtime_contract_hash: metadata.runtime_contract_hash ?? contract.content_hash,
    ...requestMetadata,
  };
}

function contextRouteMetadata(): Record<string, unknown> {
  const snapshot = contextRenderSnapshot.value;
  const preview = contextPromptPreview.value;
  if (!snapshot && !preview) return {};
  const requestMetadata = snapshot ? snapshotLlmRequestMetadata(snapshot) : previewLlmRequestMetadata(preview);
  return {
    ...requestMetadata,
    ...(snapshot?.metadata ?? preview?.context_render_metadata ?? {}),
  };
}

function titleize(value: unknown, fallback = "-"): string {
  const text = textValue(value, fallback);
  if (text === "-") return text;
  return text
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function firstNonEmptyRecord(
  primary: Record<string, unknown> | null | undefined,
  fallback: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  if (primary && Object.keys(primary).length > 0) return primary;
  if (fallback && Object.keys(fallback).length > 0) return fallback;
  return {};
}

function linkedEntity(type: string): TraceLinkedEntity | null {
  return traceSummary.value?.linked_entities.find((entity) => entity.type === type) ?? null;
}

function resetLinkedEntityDetail(): void {
  selectedEntityDetailKey.value = null;
  selectedEntityDetail.value = null;
  entityDetailLoading.value = false;
  entityDetailError.value = null;
}

function linkedEntityDetailKey(entity: TraceLinkedEntity): string {
  return `${entity.type}:${entity.id}`;
}

function linkedEntitySupportsDetail(entity: TraceLinkedEntity): boolean {
  return (
    entity.type === "session_item"
    || entity.type === "session_message"
    || entity.type === "llm_response_item"
    || entity.type === "llm_response_item_id"
  );
}

async function showLinkedEntityDetail(entity: TraceLinkedEntity): Promise<void> {
  if (!linkedEntitySupportsDetail(entity)) return;
  const key = linkedEntityDetailKey(entity);
  if (selectedEntityDetailKey.value === key && selectedEntityDetail.value) return;
  selectedEntityDetailKey.value = key;
  selectedEntityDetail.value = null;
  entityDetailLoading.value = true;
  entityDetailError.value = null;
  try {
    selectedEntityDetail.value = await loadTraceLinkedEntityDetail(entity.type, entity.id);
  } catch (error) {
    entityDetailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    entityDetailLoading.value = false;
  }
}

function linkedEntityDetailSummary(detail: WorkbenchLinkedEntityDetail | null): string {
  if (!detail) return "";
  if (detail.summary.trim()) return detail.summary;
  const content = detail.payload.content_payload;
  if (isRecord(content) && typeof content.text === "string") return content.text;
  return detail.label;
}

function familyLabel(family: string): string {
  return t(`trace.family.${laneForFamily(family)}`);
}

function surfaceIdForEvent(event: TraceEventView): string {
  return {
    channel: "web_chat",
    orchestration: event.name === "Run Created" ? "run_service" : "tool_planner",
    llm: "openai",
    tool: "tool_service",
    events: "events_service",
    observation: "run_state_observer",
    error: "error_router",
  }[laneForFamily(event.family)] ?? event.owner;
}

function eventDuration(event: TraceEventView): string {
  if (event.name === "Tool Run Succeeded") return "11.0s";
  if (event.name === "Tool Run Failed") return "12.4s";
  if (event.name.includes("LLM")) return "2.4s";
  if (event.relative_ms < 1000) return `${event.relative_ms || 120}ms`;
  return formatDuration(event.relative_ms);
}

function formatTraceClock(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  const milliseconds = String(date.getMilliseconds()).padStart(3, "0");
  return `${formatLocalTime(value)}.${milliseconds}`;
}

function formatTraceDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  const datePart = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
  return `${datePart} ${formatTraceClock(value)}`;
}

function timelineEntities(event: TraceEventView): TraceLinkedEntity[] {
  if (event.linked_entities.length > 0) {
    return event.linked_entities;
  }
  const common = {
    event_id: { type: "event_id", id: "evt_01H8XK3Q..." },
    run_id: { type: "run_id", id: runId.value ?? "run_01H8XK3Q..." },
    llm_invocation_id: { type: "llm_invocation_id", id: "llm_91d2b6a1..." },
    tool_run_id: { type: "tool_run_id", id: "tr_e8f3a6c2e1..." },
    step_id: { type: "step_id", id: "step_01H8XK3Q..." },
    observation_id: { type: "observation_id", id: "obs_01H8XK3Q..." },
  } satisfies Record<string, TraceLinkedEntity>;

  if (event.name === "Run Created") return [common.run_id];
  if (event.name === "LLM Invocation Started") return [common.llm_invocation_id];
  if (event.name === "Tool Run Created" || event.name === "Tool Run Succeeded") return [common.tool_run_id];
  if (eventDisplayName(event) === t("trace.eventName.resultApplied")) return [common.step_id, common.observation_id];
  return [common.event_id];
}

function eventDetailValue(key: string, event: TraceEventView): string {
  if (key === "source") return event.name === "Tool Run Failed" ? "tool.result.failed" : "-";
  if (key === "observation") return laneForFamily(event.family) === "observation" ? "obs_01H8XK3Q..." : "-";
  if (key === "caused") return event.name.includes("Tool Run") ? "tr_e8f3a6c2e1..." : "-";
  return "-";
}

function selectOffset(offset: number): void {
  const currentIndex = selectedEventIndex.value - 1;
  const nextEvent = activeEvents.value[currentIndex + offset];
  if (nextEvent) {
    selectedEventId.value = nextEvent.event_id;
  }
}
</script>

<template>
  <div class="trace-page page-grid" :class="`trace-page--${activeTraceView}`">
    <aside class="trace-filters scroll-area">
      <div class="filter-header">
        <h1>{{ t("trace.searchFilter") }}</h1>
        <button type="button">{{ t("common.reset") }}</button>
      </div>
      <div class="filter-tabs">
        <button
          :class="{ active: activeTraceView === 'timeline' }"
          type="button"
          @click="setTraceView('timeline')"
        >
          {{ t("trace.timeline") }}
        </button>
        <button
          :class="{ active: activeTraceView === 'graph' }"
          type="button"
          @click="setTraceView('graph')"
        >
          {{ t("trace.graphBeta") }}
        </button>
      </div>

      <section class="filter-section">
        <h2>{{ t("trace.quickSearch") }}</h2>
        <label class="trace-search">
          <input :placeholder="t('trace.searchPlaceholder')" />
          <Search :size="16" />
        </label>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.commonIds") }}</h2>
        <div class="id-grid">
          <button type="button">{{ t("trace.id.trace") }}</button>
          <button type="button">{{ t("trace.id.run") }}</button>
          <button type="button">{{ t("trace.id.session") }}</button>
          <button type="button">{{ t("trace.id.toolRun") }}</button>
          <button type="button">{{ t("trace.id.llmInvocation") }}</button>
          <button type="button">{{ t("trace.id.event") }}</button>
          <button type="button">{{ t("trace.id.artifact") }}</button>
        </div>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.timeRange") }}</h2>
        <div class="time-range-grid">
          <input value="2026-04-29 14:28:00" />
          <input value="2026-04-29 14:40:00" />
        </div>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.resultStatus") }}</h2>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.success") }}</span>
          <strong>{{ activeTraceView === 'timeline' ? 12 : (statusTotals.success ?? 0) + (statusTotals.completed ?? 0) }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.partial") }}</span>
          <strong>{{ activeTraceView === 'timeline' ? 1 : 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.failed") }}</span>
          <strong>{{ statusTotals.failed ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><input type="checkbox" />{{ t("trace.filter.cancelled") }}</span>
          <strong>0</strong>
        </label>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.running") }}</span>
          <strong>{{ statusTotals.running ?? 0 }}</strong>
        </label>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.eventFamily") }}</h2>
        <label>
          <span class="filter-option-type"><StatusDot tone="info" />{{ t("trace.family.channel") }}</span>
          <strong>{{ familyTotals.channel ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="neutral" />{{ t("trace.family.orchestration") }}</span>
          <strong>{{ familyTotals.orchestration ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="info" />{{ t("trace.family.llm") }}</span>
          <strong>{{ familyTotals.llm ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="warning" />{{ t("trace.family.tool") }}</span>
          <strong>{{ familyTotals.tool ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="danger" />{{ t("trace.family.events") }}</span>
          <strong>{{ familyTotals.events ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="success" />{{ t("trace.family.observation") }}</span>
          <strong>{{ familyTotals.observation ?? 0 }}</strong>
        </label>
        <label v-if="activeTraceView === 'graph'">
          <span class="filter-option-type"><StatusDot tone="danger" />{{ t("trace.family.error") }}</span>
          <strong>{{ familyTotals.error ?? 0 }}</strong>
        </label>
      </section>

      <UiButton variant="primary">
        <Filter :size="16" />
        {{ t("common.searchAction") }}
      </UiButton>
      <div class="filter-footer">
        <span>{{ t("trace.filterFound", { count: activeTraceView === 'timeline' ? 8 : 18, filtered: activeTraceView === 'timeline' ? '8 / 28' : '0 / 18' }) }}</span>
        <label><span>{{ t("trace.onlyKeyEvents") }}</span><input checked type="checkbox" /></label>
      </div>
    </aside>

    <section class="trace-main scroll-area">
      <div v-if="activeTraceView === 'timeline'" class="connection-strip">
        <span>
          <StatusDot :tone="loadError ? 'danger' : loadingTrace ? 'info' : 'success'" />
          {{ loadError ?? (loadingTrace ? t("trace.loading") : t("trace.healthy")) }}
        </span>
        <span>{{ t("common.updatedAt") }} {{ formatLocalTime(traceSummary?.completed_at ?? traceSummary?.started_at) }}</span>
      </div>

      <div class="trace-title-row">
        <div class="trace-title-main">
          <h1>{{ activeTraceView === 'timeline' ? t("trace.timeline") : t("trace.graphTitle") }}</h1>
          <p>
            {{ t("trace.title.prefix") }} /
            <span class="mono">{{ activeTraceId }}</span>
          </p>
          <UiButton size="sm" variant="secondary">
            <Copy :size="15" />
            {{ t("common.copy") }}
          </UiButton>
        </div>
        <div class="trace-actions">
          <RouterLink class="view-workbench" :to="workbenchRoute">
            {{ t("common.viewInWorkbench") }}
          </RouterLink>
          <button class="export-button" type="button">
            {{ t("common.export") }}
            <ChevronDown :size="14" />
          </button>
        </div>
      </div>

      <UiCard v-if="activeTraceView === 'timeline'" class="trace-summary trace-summary--timeline">
        <div>
          <span>{{ t("trace.summary.session") }}</span>
          <strong class="mono">{{ shortId(sessionKey) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.run") }}</span>
          <strong class="mono">{{ shortId(runId) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.turn") }}</span>
          <strong>{{ turnId ?? '-' }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.step") }}</span>
          <strong class="mono">{{ shortId(activeStepId) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.result") }}</span>
          <strong>
            <StatusDot :tone="toneForStatus(displaySummaryStatus)" />
            {{ statusLabel(displaySummaryStatus) }}
          </strong>
        </div>
        <div>
          <span>{{ t("trace.summary.startedAt") }}</span>
          <strong>{{ formatTraceDateTime(traceSummary?.started_at) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.duration") }}</span>
          <strong>{{ formatDuration(displaySummaryDuration) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.eventCount") }}</span>
          <strong>{{ traceEvents.length }} / {{ traceSummary?.event_count ?? 28 }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.filter") }}</span>
          <strong>{{ t("trace.onlyKeyEvents") }}</strong>
        </div>
      </UiCard>

      <UiCard v-else class="trace-summary trace-summary--graph">
        <div>
          <span>{{ t("trace.summary.session") }}</span>
          <strong class="mono">{{ shortId(sessionKey) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.run") }}</span>
          <strong class="mono">{{ shortId(runId) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.turn") }}</span>
          <strong>{{ turnId ?? '-' }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.step") }}</span>
          <strong class="mono">{{ shortId(activeStepId) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.status") }}</span>
          <strong>
            <StatusDot :tone="toneForStatus(displaySummaryStatus)" />
            {{ statusLabel(displaySummaryStatus) }}
          </strong>
        </div>
        <div>
          <span>{{ t("trace.summary.startedAt") }}</span>
          <strong>{{ formatTraceDateTime(traceSummary?.started_at) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.duration") }}</span>
          <strong>{{ formatDuration(displaySummaryDuration) }}</strong>
        </div>
      </UiCard>

      <UiCard v-if="activeTraceView === 'timeline'" class="timeline-table" :style="timelineAxisStyle">
        <header class="timeline-head">
          <span>{{ t("trace.table.timeLocal") }}</span>
          <span>{{ t("trace.table.relative") }}</span>
          <span>{{ t("trace.table.event") }}</span>
          <span>{{ t("trace.table.linkedEntities") }}</span>
        </header>
        <button
          v-for="event in traceEvents"
          :key="event.event_id"
          class="timeline-row"
          :class="{ 'timeline-row--active': event.event_id === selectedEventId }"
          type="button"
          @click="selectedEventId = event.event_id"
        >
          <time>{{ formatTraceClock(event.timestamp) }}</time>
          <span>+{{ formatDuration(event.relative_ms) }}</span>
          <span class="timeline-row__event">
            <i :class="`timeline-row__node timeline-row__node--${toneForFamily(event.family)}`">
              <CheckCircle2 :size="14" />
            </i>
            <span class="timeline-row__copy">
              <strong>{{ eventDisplayName(event) }}</strong>
              <small>
                {{ t("trace.row.owner") }}: {{ event.owner }}
                <span>{{ t("trace.row.surfaceId") }}: {{ surfaceIdForEvent(event) }}</span>
                <span>{{ t("trace.row.family") }}: {{ familyLabel(event.family) }}</span>
              </small>
            </span>
          </span>
          <span class="entity-list">
            <span v-for="entity in timelineEntities(event)" :key="`${event.event_id}-${entity.type}`" class="entity-row">
              <small>{{ entity.type }}</small>
              <code>{{ shortId(entity.id, 16) }}</code>
              <Copy :size="13" />
            </span>
            <ChevronRight :size="15" />
          </span>
        </button>
        <div v-if="traceEvents.length === 0" class="timeline-empty">
          {{ t("trace.noEvents") }}
        </div>
        <footer class="timeline-footer">
          <span><StatusDot tone="info" /> {{ t("trace.family.channel") }}</span>
          <span><StatusDot tone="neutral" /> {{ t("trace.family.orchestration") }}</span>
          <span><StatusDot tone="info" /> {{ t("trace.family.llm") }}</span>
          <span><StatusDot tone="warning" /> {{ t("trace.family.tool") }}</span>
          <span><StatusDot tone="danger" /> {{ t("trace.family.events") }}</span>
          <span><StatusDot tone="success" /> {{ t("trace.family.observation") }}</span>
        </footer>
        <div class="timeline-note">{{ t("trace.keyEventNote") }}</div>
      </UiCard>

      <UiCard v-else class="trace-graph-card">
        <div class="graph-toolbar">
          <label>
            {{ t("trace.graph.layout") }}
            <select>
              <option>{{ t("trace.graph.autoLayout") }}</option>
              <option>{{ t("trace.graph.byTime") }}</option>
            </select>
          </label>
          <label>
            {{ t("trace.graph.group") }}
            <select>
              <option>{{ t("trace.graph.byModule") }}</option>
              <option>{{ t("trace.graph.byOwner") }}</option>
            </select>
          </label>
          <label><input checked type="checkbox" /> {{ t("trace.graph.showEventName") }}</label>
          <label><input checked type="checkbox" /> {{ t("trace.graph.showDuration") }}</label>
          <label><input checked type="checkbox" /> {{ t("trace.graph.showId") }}</label>
          <div class="graph-zoom">
            <button type="button">-</button>
            <span>100%</span>
            <button type="button">+</button>
          </div>
        </div>

        <div class="graph-canvas">
          <div class="graph-lanes">
            <div
              v-for="lane in graphLanes"
              :key="lane.id"
              :class="`graph-lane graph-lane--${lane.tone}`"
            >
              <span>{{ lane.label }}</span>
              <strong>{{ lane.count }}</strong>
            </div>
          </div>

          <div class="graph-stage">
            <i
              v-for="edge in graphEdges"
              :key="edge.id"
              class="graph-edge"
              :class="{ 'graph-edge--dashed': edge.dashed }"
              :style="edge.style"
            />
            <button
              v-for="node in graphNodes"
              :key="node.event.event_id"
              class="graph-node"
              :class="[`graph-node--${node.tone}`, { 'graph-node--active': node.event.event_id === selectedEventId }]"
              :style="node.style"
              type="button"
              @click="selectedEventId = node.event.event_id"
            >
              <span class="graph-node__icon">
                <GitBranch :size="15" />
              </span>
              <strong>{{ eventDisplayName(node.event) }}</strong>
              <small>{{ node.event.owner }} / {{ shortId(node.event.event_id, 13) }}</small>
              <em>{{ formatDuration(node.event.relative_ms) }}</em>
            </button>
          </div>

          <div class="graph-minimap">
            <span v-for="node in graphNodes" :key="`mini-${node.event.event_id}`" />
          </div>
        </div>

        <footer class="graph-legend">
          <span v-for="lane in graphLanes" :key="`legend-${lane.id}`">
            <StatusDot :tone="lane.tone" />
            {{ lane.label }}
          </span>
          <span><i class="edge-sample" /> {{ t("trace.graph.causal") }}</span>
          <span><i class="edge-sample edge-sample--dashed" /> {{ t("trace.graph.influence") }}</span>
        </footer>
      </UiCard>
    </section>

    <aside class="event-inspector scroll-area">
      <h1>{{ activeTraceView === 'graph' ? t("trace.stepInspector") : t("trace.inspector") }}</h1>
      <div class="inspector-nav">
        <button type="button" :disabled="selectedEventIndex <= 1" @click="selectOffset(-1)">
          <ChevronLeft :size="15" /> {{ t("trace.inspector.prev") }}
        </button>
        <span>{{ selectedEventIndex }} / {{ activeEvents.length }}</span>
        <button type="button" :disabled="selectedEventIndex >= activeEvents.length" @click="selectOffset(1)">
          {{ t("trace.inspector.next") }} <ChevronRight :size="15" />
        </button>
      </div>

      <UiCard v-if="selectedEvent" class="event-card">
        <div class="event-card__hero">
          <span class="event-card__icon" :class="`event-card__icon--${toneForStatus(selectedEvent.status)}`">
            <XCircle v-if="toneForStatus(selectedEvent.status) === 'danger'" :size="30" />
            <CheckCircle2 v-else :size="30" />
          </span>
          <div>
            <h2>{{ eventDisplayName(selectedEvent) }}</h2>
            <UiBadge :tone="toneForStatus(selectedEvent.status)">
              {{ statusLabel(selectedEvent.status) }}
            </UiBadge>
            <UiBadge :tone="toneForFamily(selectedEvent.family)">
              {{ familyLabel(selectedEvent.family) }}
            </UiBadge>
            <UiBadge tone="neutral">
              key_event
            </UiBadge>
          </div>
        </div>

        <div class="inspector-tabs">
          <button class="active" type="button">{{ t("trace.tabs.overview") }}</button>
          <button type="button">{{ t("trace.tabs.payload") }}</button>
          <button type="button">{{ t("trace.tabs.logs") }} ({{ selectedEvent.status === 'failed' ? 12 : 3 }})</button>
          <button type="button">{{ t("trace.tabs.events") }} ({{ selectedEvent.status === 'failed' ? 2 : 2 }})</button>
          <button type="button">{{ t("trace.tabs.linked") }} ({{ selectedEvent.status === 'failed' ? 6 : 4 }})</button>
        </div>

        <dl class="event-details">
          <div>
            <dt>{{ t("trace.detail.eventId") }}</dt>
            <dd class="mono">{{ shortId(selectedEvent.event_id, 28) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.eventName") }}</dt>
            <dd>{{ eventDisplayName(selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.eventFamily") }}</dt>
            <dd>{{ familyLabel(selectedEvent.family) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.timestampLocal") }}</dt>
            <dd>{{ formatTraceDateTime(selectedEvent.timestamp) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.duration") }}</dt>
            <dd>{{ eventDuration(selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("common.owner") }}</dt>
            <dd>{{ selectedEvent.owner }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.surfaceId") }}</dt>
            <dd>{{ surfaceIdForEvent(selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.sourceEventId") }}</dt>
            <dd>{{ eventDetailValue('source', selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.observationId") }}</dt>
            <dd>{{ eventDetailValue('observation', selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.causedBy") }}</dt>
            <dd>{{ eventDetailValue('caused', selectedEvent) }}</dd>
          </div>
        </dl>

        <dl v-if="selectedEvent.status === 'failed'" class="event-details event-details--summary">
          <div>
            <dt>{{ t("trace.detail.errorCode") }}</dt>
            <dd>403</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.errorMessage") }}</dt>
            <dd>Forbidden</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.provider") }}</dt>
            <dd>OpenAI</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.model") }}</dt>
            <dd>dall-e-3</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.requestId") }}</dt>
            <dd class="mono">req_01H8XK3Q8B2C7D6E4F8G0H1I2J</dd>
          </div>
        </dl>

        <h3>{{ t("trace.linkedEntities") }}</h3>
        <button
          v-for="entity in timelineEntities(selectedEvent).filter((item) => linkedEntitySupportsDetail(item))"
          :key="`detail:${entity.type}:${entity.id}`"
          class="entity-link"
          type="button"
          :disabled="entityDetailLoading && selectedEntityDetailKey === linkedEntityDetailKey(entity)"
          @click="showLinkedEntityDetail(entity)"
        >
          <span>{{ entity.type }}</span>
          <code>{{ entity.id }}</code>
          <small v-if="entityDetailLoading && selectedEntityDetailKey === linkedEntityDetailKey(entity)">
            {{ t("common.loading") }}
          </small>
          <ExternalLink v-else :size="14" />
        </button>
        <RouterLink
          v-for="entity in timelineEntities(selectedEvent).filter((item) => !linkedEntitySupportsDetail(item))"
          :key="entity.type"
          class="entity-link"
          :to="`/trace/${selectedEvent.trace.trace_id}`"
        >
          <span>{{ entity.type }}</span>
          <code>{{ entity.id }}</code>
          <ExternalLink :size="14" />
        </RouterLink>
        <div v-if="selectedEntityDetail || entityDetailError" class="entity-detail-card">
          <template v-if="selectedEntityDetail">
            <header>
              <span>{{ selectedEntityDetail.owner }}</span>
              <strong>{{ selectedEntityDetail.label }}</strong>
            </header>
            <p>{{ linkedEntityDetailSummary(selectedEntityDetail) }}</p>
            <dl>
              <div>
                <dt>{{ t("table.kind") }}</dt>
                <dd>{{ selectedEntityDetail.type }}</dd>
              </div>
              <div>
                <dt>ID</dt>
                <dd>{{ selectedEntityDetail.id }}</dd>
              </div>
            </dl>
          </template>
          <p v-else>{{ entityDetailError }}</p>
        </div>

        <h3>{{ t("trace.quickActions") }}</h3>
        <div class="quick-actions">
          <RouterLink :to="workbenchRoute">
            <GitBranch :size="16" />
            {{ t("common.viewInWorkbench") }}
          </RouterLink>
          <RouterLink :to="operationsRoute">
            <ExternalLink :size="16" />
            {{ selectedEvent.family === 'tool' ? t("trace.action.openToolOperations") : t("common.openInOperations") }}
          </RouterLink>
          <RouterLink to="/operations/llm">
            <ExternalLink :size="16" />
            {{ t("trace.action.openLlmOperations") }}
          </RouterLink>
          <RouterLink :to="`/trace/${selectedEvent.trace.trace_id}`">
            <ExternalLink :size="16" />
            {{ t("trace.action.viewArtifact") }}
          </RouterLink>
          <button type="button">
            <GitBranch :size="16" />
            {{ t("trace.action.copyCurl") }}
          </button>
        </div>
      </UiCard>
      <UiCard v-else class="event-card event-card--empty">
        {{ t("trace.emptySelection") }}
      </UiCard>

      <UiCard v-if="contextRenderSnapshot || contextPromptPreview || loadingContextSnapshot" class="event-card trace-context-snapshot-card">
        <div class="trace-context-snapshot-head">
          <div>
            <h2>{{ t("trace.contextSnapshot.title") }}</h2>
            <p>{{ t("trace.contextSnapshot.subtitle") }}</p>
          </div>
          <UiBadge :tone="contextRenderSnapshot || contextPromptPreview ? 'success' : 'info'">
            {{ contextRenderSnapshot || contextPromptPreview ? t("workbench.context.historyDelivery") : t("common.loading") }}
          </UiBadge>
        </div>

        <div v-if="loadingContextSnapshot && !contextRenderSnapshot" class="trace-context-snapshot-loading">
          {{ t("trace.contextSnapshot.loading") }}
        </div>

        <template v-if="contextRenderSnapshot || contextPromptPreview">
          <dl v-if="contextSnapshotRows.length" class="trace-context-snapshot-summary">
            <div v-for="row in contextSnapshotRows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd :title="row.value">{{ row.value }}</dd>
            </div>
          </dl>

          <div v-if="contextSnapshotRiskRows.length" class="trace-context-snapshot-risk-strip" :aria-label="t('workbench.context.sessionBudgetStatus')">
            <div
              v-for="row in contextSnapshotRiskRows"
              :key="row.label"
              class="trace-context-snapshot-risk"
              :class="`trace-context-snapshot-risk--${row.tone}`"
              :title="row.detail"
            >
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>

          <div v-if="contextRouteDiagnosticRows.length" class="context-route-diagnostics" :aria-label="t('workbench.context.routeDiagnostics')">
            <div
              v-for="row in contextRouteDiagnosticRows"
              :key="row.label"
              class="context-route-diagnostic"
              :class="`context-route-diagnostic--${row.tone}`"
              :title="row.detail"
            >
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>

          <div v-if="contextBrowserEvidencePathRows.length" class="context-route-schemas" role="table" :aria-label="t('workbench.context.routeEvidencePathLadder')">
            <div class="context-route-schemas__head" role="row">
              <span role="columnheader">{{ t("workbench.context.routeEvidencePath") }}</span>
              <span role="columnheader">{{ t("common.status") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeSchemas") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeFunctions") }}</span>
            </div>
            <div
              v-for="row in contextBrowserEvidencePathRows"
              :key="row.id"
              class="context-route-schemas__row"
              :class="`context-route-schemas__row--${row.tone}`"
              role="row"
            >
              <span role="cell" :title="row.path">{{ row.path }}</span>
              <span role="cell">{{ row.status }}</span>
              <span role="cell" :title="row.schemas">{{ row.schemas }}</span>
              <span role="cell">{{ row.count }}</span>
            </div>
          </div>

          <div v-if="contextBrowserWarningRows.length" class="context-route-schemas" role="table" :aria-label="t('workbench.context.routeBrowserWarnings')">
            <div class="context-route-schemas__head context-route-schemas__head--wide" role="row">
              <span role="columnheader">{{ t("workbench.context.routeWarningType") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeCode") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeLatestTool") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeSummary") }}</span>
            </div>
            <div
              v-for="row in contextBrowserWarningRows"
              :key="row.id"
              class="context-route-schemas__row context-route-schemas__row--wide"
              :class="`context-route-schemas__row--${row.tone}`"
              role="row"
            >
              <span role="cell" :title="row.warningType">{{ row.warningType }}</span>
              <span role="cell" :title="row.code">{{ row.code }}</span>
              <span role="cell" :title="row.latestTool">{{ row.latestTool }}</span>
              <span role="cell" :title="row.summary">{{ row.summary }}</span>
            </div>
          </div>

          <div v-if="contextRouteGroupRows.length" class="context-route-groups" role="table" :aria-label="t('workbench.context.routeGroups')">
            <div class="context-route-groups__head" role="row">
              <span role="columnheader">{{ t("workbench.context.routeGroup") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeSource") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeFunctions") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeDefaultSchemas") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeVisibility") }}</span>
            </div>
            <div
              v-for="row in contextRouteGroupRows"
              :key="row.id"
              class="context-route-groups__row"
              :class="`context-route-groups__row--${row.tone}`"
              role="row"
            >
              <span role="cell" :title="row.group">{{ row.group }}</span>
              <span role="cell" :title="row.source">{{ row.source }}</span>
              <span role="cell">{{ row.functions }}</span>
              <span role="cell">{{ row.defaultSchemas }}</span>
              <span role="cell">{{ row.visibility }}</span>
            </div>
          </div>

          <div v-if="contextRouteSchemaRows.length" class="context-route-schemas" role="table" :aria-label="t('workbench.context.routeSchemas')">
            <div class="context-route-schemas__head" role="row">
              <span role="columnheader">{{ t("workbench.context.routeSchema") }}</span>
              <span role="columnheader">{{ t("common.status") }}</span>
              <span role="columnheader">{{ t("workbench.context.routeReason") }}</span>
              <span role="columnheader">{{ t("workbench.context.routePriority") }}</span>
            </div>
            <div
              v-for="row in contextRouteSchemaRows"
              :key="row.id"
              class="context-route-schemas__row"
              :class="`context-route-schemas__row--${row.tone}`"
              role="row"
            >
              <span role="cell" :title="row.schema">{{ row.schema }}</span>
              <span role="cell">{{ row.status }}</span>
              <span role="cell" :title="row.reason">{{ row.reason }}</span>
              <span role="cell">{{ row.priority }}</span>
            </div>
          </div>

          <div v-if="contextSnapshotDiagnosticRows.length" class="trace-context-snapshot-diagnostics" :aria-label="t('workbench.context.renderDiagnostics')">
            <div
              v-for="row in contextSnapshotDiagnosticRows"
              :key="row.label"
              class="trace-context-snapshot-diagnostic"
            >
              <span>{{ row.label }}</span>
              <strong :title="row.value">{{ row.value }}</strong>
            </div>
          </div>

          <div v-if="contextSnapshotRefRows.length" class="trace-context-snapshot-node-refs">
            <div class="trace-context-snapshot-node-refs__head">
              <span>{{ t("workbench.context.protocolRefs") }}</span>
              <small v-if="contextSnapshotHiddenRefCount > 0">
                {{ t("workbench.context.moreRefs", { count: formatNumber(contextSnapshotHiddenRefCount) }) }}
              </small>
            </div>
            <div
              v-for="row in contextSnapshotRefRows"
              :key="row.id"
              class="trace-context-snapshot-node-ref"
            >
              <span>{{ row.kind }} · #{{ row.sequence }}</span>
              <code :title="`${row.id} · ${row.owner} · ${row.callId}`">{{ shortId(row.id, 34) }}</code>
            </div>
          </div>

          <div v-if="contextSnapshotSessionNodeRows.length" class="trace-context-snapshot-node-refs">
            <div class="trace-context-snapshot-node-refs__head">
              <span>{{ t("trace.contextSnapshot.sessionNodes") }}</span>
              <small>
                {{ t("trace.contextSnapshot.sessionNodeCount", { count: formatNumber(contextSnapshotSessionNodeRows.length) }) }}
              </small>
            </div>
            <div
              v-for="row in contextSnapshotSessionNodePreviewRows"
              :key="row.nodeId"
              class="trace-context-snapshot-node-ref"
            >
              <span>{{ t("trace.contextSnapshot.sequence", { sequence: row.sequence }) }}</span>
              <code :title="`${row.nodeId} · ${row.sessionId}`">{{ shortId(row.nodeId, 34) }}</code>
            </div>
            <small v-if="contextSnapshotHiddenSessionNodeCount > 0" class="trace-context-snapshot-node-refs__more">
              {{ t("trace.contextSnapshot.moreSessionNodes", { count: formatNumber(contextSnapshotHiddenSessionNodeCount) }) }}
            </small>
          </div>

          <div class="context-request-tabs" role="tablist" :aria-label="t('trace.contextSnapshot.title')">
            <button
              v-for="tab in contextActualRequestTabs"
              :key="tab.id"
              type="button"
              role="tab"
              :aria-selected="contextActualRequestTab === tab.id"
              :class="{ active: contextActualRequestTab === tab.id }"
              @click="contextActualRequestTab = tab.id"
            >
              <span>{{ tab.label }}</span>
              <small>{{ tab.count }}</small>
            </button>
          </div>
          <div class="context-request-panel">
            <template v-if="contextActualRequestTab === 'xml'">
              <div class="trace-context-snapshot-preview-head">
                <span>{{ t("workbench.context.promptXml") }}</span>
                <small>{{ t("workbench.context.promptChars", { count: formatNumber(contextSnapshotPromptCharCount) }) }}</small>
              </div>
              <XmlSourceViewer
                v-if="contextActualRequestXmlSource"
                class="trace-context-snapshot-preview"
                :source="contextActualRequestXmlSource"
                max-height="min(42vh, 460px)"
              />
              <p v-else class="trace-context-snapshot-loading context-request-empty">{{ t("workbench.context.requestEmpty") }}</p>
            </template>
            <pre v-else class="context-request-json">{{ contextActualRequestJson }}</pre>
          </div>
        </template>
      </UiCard>
    </aside>
  </div>
</template>

<style scoped>
.trace-page {
  display: grid;
  grid-template-columns: 252px minmax(0, 1fr) minmax(430px, 30vw);
  height: calc(100dvh - var(--shell-topbar-height));
  overflow: hidden;
  background: var(--surface-page);
}

.trace-page--graph {
  grid-template-columns: 270px minmax(0, 1fr) minmax(430px, 30vw);
}

.trace-filters,
.event-inspector {
  padding: var(--space-4);
  background: var(--surface-sidebar);
}

.trace-filters {
  border-right: 1px solid var(--border-subtle);
}

.event-inspector {
  border-left: 1px solid var(--border-subtle);
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: 18px;
  line-height: 1.25;
}

h2,
h3 {
  font-size: 13px;
  line-height: 1.3;
}

.filter-tabs,
.trace-actions,
.trace-title-main,
.connection-strip,
.trace-title-row,
.trace-summary,
.timeline-row,
.timeline-row__event,
.entity-list,
.event-card__hero,
.inspector-nav,
.inspector-nav button,
.entity-link,
.quick-actions a,
.quick-actions button,
.filter-section label {
  display: flex;
  align-items: center;
}

.connection-strip,
.trace-title-row,
.trace-summary,
.timeline-row,
.inspector-nav,
.entity-link {
  justify-content: space-between;
}

.filter-tabs {
  gap: var(--space-2);
  margin: 16px 0 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.filter-tabs button,
.inspector-tabs button,
.inspector-nav button,
.filter-section button,
.id-grid button,
.filter-header button,
.export-button {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filter-header button {
  min-height: 28px;
  border-color: transparent;
  background: transparent;
  color: var(--text-secondary);
}

.filter-tabs button {
  flex: 1;
  height: 32px;
  border-width: 0 0 2px;
  background: transparent;
  font-size: 12px;
}

.filter-tabs .active,
.inspector-tabs .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.filter-section {
  display: grid;
  gap: 9px;
  margin-bottom: 18px;
}

.trace-search {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.trace-search input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
}

.id-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.time-range-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-2);
}

.time-range-grid input {
  min-width: 0;
  min-height: 30px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-size: 12px;
}

.id-grid button {
  min-height: 29px;
  padding: 0 10px;
  font-size: 11px;
}

.filter-section label {
  justify-content: space-between;
  gap: var(--space-2);
  color: var(--text-secondary);
  font-size: 12px;
}

.filter-option-type {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  text-align: left;
}

.filter-option-type input {
  flex: 0 0 auto;
  margin: 0;
}

.filter-section strong {
  color: var(--text-primary);
}

.filter-footer {
  display: grid;
  gap: 10px;
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 11px;
}

.filter-footer label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-primary);
}

.trace-main {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  align-content: stretch;
  gap: 10px;
  min-height: 0;
  padding: var(--space-4);
  overflow: hidden;
}

.trace-page--graph .trace-main {
  grid-template-rows: auto auto minmax(0, 1fr);
  padding-top: 28px;
}

.connection-strip {
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background: var(--surface-success);
  color: var(--text-secondary);
  font-size: 12px;
}

.connection-strip span:first-child {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.trace-title-main {
  flex: 1 1 auto;
  gap: var(--space-3);
  min-width: 0;
}

.trace-title-main h1 {
  white-space: nowrap;
}

.trace-title-row p {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-actions {
  flex: 0 0 auto;
  gap: var(--space-2);
  margin-left: auto;
}

.trace-page--graph .trace-title-row {
  gap: 10px;
}

.trace-page--graph .trace-title-main p {
  max-width: 290px;
}

.trace-page--graph .view-workbench,
.trace-page--graph .export-button {
  padding: 0 10px;
}

.view-workbench,
.export-button {
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  white-space: nowrap;
}

.view-workbench {
  background: var(--surface-active);
  color: var(--color-accent);
  text-decoration: none;
}

.trace-summary {
  display: grid;
  gap: 0;
  min-height: 76px;
  padding: 0;
  overflow: hidden;
}

.trace-summary > div {
  min-width: 0;
  padding: 13px 14px;
  border-left: 1px solid var(--border-subtle);
}

.trace-summary > div:first-child {
  border-left: 0;
}

.trace-summary--timeline {
  grid-template-columns: 1.05fr 1.05fr 0.65fr 0.78fr 1.45fr 0.75fr 0.72fr 1fr;
}

.trace-summary--graph {
  grid-template-columns: 1.1fr 1.05fr 0.8fr 0.9fr 1.45fr 0.9fr;
  min-height: 64px;
}

.trace-summary span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

.trace-summary strong {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin-top: var(--space-1);
  overflow: hidden;
  font-size: 12px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-summary strong.mono {
  display: block;
}

.timeline-table {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.timeline-table::before {
  position: absolute;
  top: 80px;
  left: 210px;
  z-index: 0;
  width: 2px;
  height: var(--trace-axis-height);
  content: "";
  background: linear-gradient(
    180deg,
    var(--color-blue),
    var(--color-violet) 38%,
    var(--color-warning) 62%,
    var(--color-teal)
  );
  opacity: 0.76;
}

.timeline-head,
.timeline-row {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 102px 80px minmax(360px, 1fr) 252px;
  gap: 13px;
  min-height: 72px;
  padding: 0 15px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
}

.timeline-head {
  align-items: center;
  min-height: 44px;
  color: var(--text-muted);
  font-size: 11px;
}

.timeline-row {
  width: 100%;
  flex: 0 0 72px;
  cursor: pointer;
  font-size: 13px;
}

.timeline-empty {
  display: grid;
  min-height: 120px;
  place-items: center;
  color: var(--text-muted);
}

.timeline-row--active {
  background: var(--surface-active);
}

.timeline-row__event {
  position: relative;
  gap: 12px;
  min-width: 0;
}

.timeline-row__copy,
.timeline-row__copy strong,
.timeline-row__copy small {
  display: block;
  min-width: 0;
}

.timeline-row__copy strong,
.timeline-row__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-row__copy strong {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.25;
}

.timeline-row__copy small {
  color: var(--text-muted);
  margin-top: 3px;
  font-size: 11px;
}

.timeline-row__copy small span {
  margin-left: 12px;
}

.timeline-row__node {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 3px solid var(--surface-panel);
  border-radius: 999px;
  background: var(--node-color);
  color: var(--text-on-accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--node-color) 52%, transparent);
}

.timeline-row__node--neutral {
  --node-color: var(--color-violet);
}

.timeline-row__node--info {
  --node-color: var(--color-blue);
}

.timeline-row__node--success {
  --node-color: var(--color-teal);
}

.timeline-row__node--warning {
  --node-color: var(--color-warning);
}

.entity-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 10px;
  justify-content: stretch;
}

.entity-row {
  grid-column: 1;
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.entity-row small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-list > svg {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
}

.timeline-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 18px;
  margin: auto 80px 0;
  min-height: 42px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  color: var(--text-secondary);
  font-size: 11px;
}

.timeline-footer span,
.timeline-note {
  display: flex;
  align-items: center;
  gap: 7px;
}

.timeline-note {
  min-height: 36px;
  padding: 0 80px;
  color: var(--text-muted);
  font-size: 11px;
}

code {
  padding: 2px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
}

.event-inspector h1 {
  margin-bottom: 14px;
}

.inspector-nav {
  min-height: 36px;
  margin-bottom: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  overflow: hidden;
}

.inspector-nav button {
  gap: var(--space-2);
  height: 36px;
  border: 0;
  background: transparent;
}

.inspector-nav button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.event-card {
  display: grid;
  gap: 13px;
  padding: 14px;
}

.event-card--empty {
  min-height: 180px;
  place-items: center;
  color: var(--text-muted);
}

.trace-context-snapshot-card {
  margin-top: 12px;
}

.trace-context-snapshot-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.trace-context-snapshot-head p {
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.35;
}

.trace-context-snapshot-summary,
.trace-context-snapshot-diagnostics {
  display: grid;
  gap: 7px;
  margin: 0;
}

.trace-context-snapshot-summary {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
}

.trace-context-snapshot-summary div,
.trace-context-snapshot-diagnostic {
  min-width: 0;
}

.trace-context-snapshot-summary dt,
.trace-context-snapshot-diagnostic span {
  display: block;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.trace-context-snapshot-summary dd,
.trace-context-snapshot-diagnostic strong {
  display: block;
  min-width: 0;
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-context-snapshot-risk-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
}

.trace-context-snapshot-risk {
  min-width: 0;
  padding: 8px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 72%, transparent);
}

.trace-context-snapshot-risk span {
  display: block;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-context-snapshot-risk strong {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-context-snapshot-risk--success strong {
  color: var(--color-success);
}

.trace-context-snapshot-risk--warning {
  border-color: color-mix(in srgb, var(--color-warning) 44%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-warning) 8%, var(--surface-raised));
}

.trace-context-snapshot-risk--warning strong {
  color: var(--color-warning);
}

.trace-context-snapshot-risk--danger {
  border-color: color-mix(in srgb, var(--color-danger) 48%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-danger) 8%, var(--surface-raised));
}

.trace-context-snapshot-risk--danger strong {
  color: var(--color-danger);
}

.trace-context-snapshot-diagnostics {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.trace-context-snapshot-diagnostic {
  padding: 8px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 72%, transparent);
}

.context-route-diagnostics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
  gap: 6px;
}

.context-route-diagnostic {
  min-width: 0;
  padding: 7px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-inset);
}

.context-route-diagnostic--success {
  border-color: color-mix(in srgb, var(--color-success) 28%, var(--border-subtle));
}

.context-route-diagnostic--warning {
  border-color: color-mix(in srgb, var(--color-warning) 34%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-warning) 6%, var(--surface-inset));
}

.context-route-diagnostic--danger {
  border-color: color-mix(in srgb, var(--color-danger) 36%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-danger) 6%, var(--surface-inset));
}

.context-route-diagnostic--info {
  border-color: color-mix(in srgb, var(--color-accent) 30%, var(--border-subtle));
}

.context-route-diagnostic span {
  display: block;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-route-diagnostic strong {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 650;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-route-groups {
  display: grid;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-inset);
}

.context-route-groups__head,
.context-route-groups__row {
  display: grid;
  grid-template-columns: minmax(140px, 1.45fr) minmax(86px, 0.95fr) minmax(44px, 0.4fr) minmax(76px, 0.75fr) minmax(76px, 0.75fr);
  min-width: 0;
}

.context-route-groups__head {
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 650;
  text-transform: uppercase;
}

.context-route-groups__row {
  color: var(--text-secondary);
  font-size: 11px;
}

.context-route-groups__row + .context-route-groups__row {
  border-top: 1px solid color-mix(in srgb, var(--border-subtle) 72%, transparent);
}

.context-route-groups__row--info {
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
}

.context-route-groups__row--warning {
  background: color-mix(in srgb, var(--color-warning) 6%, transparent);
}

.context-route-groups__row--success {
  background: color-mix(in srgb, var(--color-success) 4%, transparent);
}

.context-route-groups span {
  min-width: 0;
  overflow: hidden;
  padding: 6px 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-route-schemas {
  display: grid;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-inset);
}

.context-route-schemas__head,
.context-route-schemas__row {
  display: grid;
  grid-template-columns: minmax(145px, 1.2fr) minmax(58px, 0.45fr) minmax(110px, 1fr) minmax(42px, 0.35fr);
  min-width: 0;
}

.context-route-schemas__head {
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 650;
  text-transform: uppercase;
}

.context-route-schemas__row {
  color: var(--text-secondary);
  font-size: 11px;
}

.context-route-schemas__row--wide {
  grid-template-columns: minmax(110px, 0.9fr) minmax(96px, 0.85fr) minmax(118px, 0.95fr) minmax(150px, 1.25fr);
}

.context-route-schemas__head--wide {
  grid-template-columns: minmax(110px, 0.9fr) minmax(96px, 0.85fr) minmax(118px, 0.95fr) minmax(150px, 1.25fr);
}

.context-route-schemas__row + .context-route-schemas__row {
  border-top: 1px solid color-mix(in srgb, var(--border-subtle) 72%, transparent);
}

.context-route-schemas__row--success {
  background: color-mix(in srgb, var(--color-success) 4%, transparent);
}

.context-route-schemas__row--warning {
  background: color-mix(in srgb, var(--color-warning) 6%, transparent);
}

.context-route-schemas span {
  min-width: 0;
  overflow: hidden;
  padding: 6px 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-request-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
}

.context-request-tabs button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 72%, transparent);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
}

.context-request-tabs button.active {
  border-color: color-mix(in srgb, var(--color-accent) 58%, transparent);
  background: color-mix(in srgb, var(--color-accent) 12%, var(--surface-raised));
  color: var(--color-accent);
}

.context-request-tabs span,
.context-request-tabs small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-request-tabs small {
  color: var(--text-muted);
  font-size: 10px;
}

.context-request-panel {
  display: grid;
  min-height: 240px;
  min-width: 0;
}

.context-request-json {
  min-height: 240px;
  max-height: min(42vh, 460px);
  margin: 0;
  overflow: auto;
  padding: 10px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-inset);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre;
}

.context-request-empty {
  min-height: 220px;
}

.trace-context-snapshot-node-refs {
  display: grid;
  gap: 6px;
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-panel-soft);
}

.trace-context-snapshot-node-refs__head,
.trace-context-snapshot-node-ref {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.trace-context-snapshot-node-refs__head {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.trace-context-snapshot-node-refs__head small,
.trace-context-snapshot-node-refs__more {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 500;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-context-snapshot-node-ref {
  min-width: 0;
  color: var(--text-muted);
  font-size: 11px;
}

.trace-context-snapshot-node-ref code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.trace-context-snapshot-node-refs__more {
  display: block;
}

.trace-context-snapshot-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.trace-context-snapshot-preview-head small {
  color: var(--text-muted);
}

.trace-context-snapshot-preview {
  min-height: 240px;
}

.trace-context-snapshot-loading {
  display: grid;
  min-height: 96px;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  color: var(--text-muted);
  font-size: 12px;
}

.event-card__hero {
  gap: 12px;
}

.event-card__icon {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  border-radius: 999px;
  background: var(--color-success);
  color: var(--text-on-accent);
}

.event-card__icon--danger {
  background: var(--color-danger);
}

.event-card__icon--warning {
  background: var(--color-warning);
}

.event-card__icon--info {
  background: var(--color-blue);
}

.event-card h2 {
  margin-bottom: 6px;
  font-size: 15px;
  line-height: 1.25;
}

.inspector-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  border-bottom: 1px solid var(--border-subtle);
}

.inspector-tabs button {
  min-height: 32px;
  padding: 0 3px;
  border-width: 0 0 2px;
  background: transparent;
  font-size: 11px;
  line-height: 1.1;
}

.event-details {
  display: grid;
  gap: 8px;
  margin: 0;
  font-size: 12px;
}

.event-details div {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 8px;
}

.event-details--summary {
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

dt {
  color: var(--text-muted);
}

dd {
  min-width: 0;
  margin: 0;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.entity-link {
  gap: var(--space-2);
  min-height: 34px;
  width: 100%;
  border: 0;
  font-size: 12px;
  color: var(--text-secondary);
  text-decoration: none;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  cursor: pointer;
}

.entity-link code {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.entity-link small {
  color: var(--text-muted);
  font-size: 11px;
}

.entity-link:disabled {
  cursor: wait;
  opacity: 0.64;
}

.entity-detail-card {
  display: grid;
  gap: 8px;
  padding: 10px 0 4px;
  border-bottom: 1px solid var(--border-subtle);
}

.entity-detail-card header {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.entity-detail-card header span {
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 750;
  text-transform: uppercase;
}

.entity-detail-card header strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-detail-card p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.entity-detail-card dl {
  display: grid;
  gap: 6px;
  margin: 0;
}

.entity-detail-card dl div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
}

.entity-detail-card dt,
.entity-detail-card dd {
  font-size: 11px;
  line-height: 1.35;
}

.entity-detail-card dt {
  color: var(--text-muted);
}

.entity-detail-card dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.quick-actions a,
.quick-actions button {
  gap: var(--space-2);
  min-height: 43px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-primary);
  cursor: pointer;
  text-decoration: none;
  font-size: 12px;
}

.quick-actions button:last-child {
  grid-column: 1 / span 1;
}

.trace-graph-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 10px;
  overflow: hidden;
}

.graph-toolbar,
.graph-toolbar label,
.graph-zoom,
.graph-legend,
.graph-legend span {
  display: flex;
  align-items: center;
}

.graph-toolbar {
  gap: 16px;
  min-height: 34px;
  color: var(--text-muted);
  font-size: var(--font-size-1);
}

.graph-toolbar label {
  gap: 8px;
}

.graph-toolbar select,
.graph-zoom button {
  min-height: 28px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
}

.graph-toolbar select {
  padding: 0 9px;
}

.graph-zoom {
  gap: 0;
  margin-left: auto;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  overflow: hidden;
}

.graph-zoom button,
.graph-zoom span {
  display: grid;
  place-items: center;
  min-width: 34px;
  height: 28px;
  border-width: 0 1px 0 0;
}

.graph-zoom button:last-child {
  border-right: 0;
}

.graph-canvas {
  position: relative;
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  margin-top: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background:
    radial-gradient(circle, color-mix(in srgb, var(--border-default) 42%, transparent) 1px, transparent 1px) 0 0 / 16px 16px,
    var(--surface-panel-soft);
  overflow: hidden;
}

.graph-lanes {
  display: grid;
  grid-template-rows: repeat(7, minmax(0, 1fr));
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 68%, transparent);
}

.graph-lane {
  display: grid;
  align-content: center;
  gap: 4px;
  min-height: 82px;
  padding: 0 9px;
  border-left: 2px solid var(--lane-color);
  border-bottom: 1px solid var(--border-subtle);
}

.graph-lane span {
  color: var(--text-secondary);
  font-size: var(--font-size-1);
}

.graph-lane strong {
  color: var(--lane-color);
  font-size: var(--font-size-4);
}

.graph-lane--neutral {
  --lane-color: var(--color-violet);
}

.graph-lane--info {
  --lane-color: var(--color-blue);
}

.graph-lane--success {
  --lane-color: var(--color-teal);
}

.graph-lane--warning {
  --lane-color: var(--color-warning);
}

.graph-lane--danger {
  --lane-color: #ff7a1a;
}

.graph-stage {
  position: relative;
  min-width: 0;
}

.graph-edge {
  position: absolute;
  height: 2px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-violet) 72%, transparent);
  transform-origin: left center;
  opacity: 0.8;
}

.graph-edge--dashed {
  background: repeating-linear-gradient(90deg, var(--text-muted) 0 6px, transparent 6px 10px);
  opacity: 0.62;
}

.graph-node {
  position: absolute;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  grid-template-rows: auto auto;
  column-gap: 8px;
  row-gap: 2px;
  width: 188px;
  min-height: 54px;
  padding: 8px 9px;
  border: 1px solid var(--node-color);
  border-radius: var(--radius-2);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--node-color) 18%, transparent), transparent),
    var(--surface-raised);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.graph-node--active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--node-color) 34%, transparent);
}

.graph-node__icon {
  display: grid;
  grid-row: 1 / span 2;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: var(--node-color);
}

.graph-node strong,
.graph-node small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.graph-node strong {
  font-size: var(--font-size-1);
}

.graph-node small {
  color: var(--text-muted);
  font-size: 11px;
}

.graph-node em {
  grid-column: 3;
  grid-row: 1 / span 2;
  align-self: end;
  color: var(--text-muted);
  font-size: 11px;
  font-style: normal;
}

.graph-node--neutral {
  --node-color: var(--color-violet);
}

.graph-node--info {
  --node-color: var(--color-blue);
}

.graph-node--success {
  --node-color: var(--color-teal);
}

.graph-node--warning {
  --node-color: var(--color-warning);
}

.graph-node--danger {
  --node-color: var(--color-danger);
}

.graph-minimap {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: grid;
  align-content: end;
  gap: 3px;
  width: 92px;
  height: 92px;
  padding: 9px;
  border: 1px solid var(--border-default);
  background: color-mix(in srgb, var(--surface-sidebar) 86%, transparent);
}

.graph-minimap span {
  display: block;
  height: 5px;
  margin-left: auto;
  border-radius: 999px;
  background: var(--color-blue);
}

.graph-minimap span:nth-child(2n) {
  width: 42px;
  background: var(--color-violet);
}

.graph-minimap span:nth-child(2n + 1) {
  width: 28px;
}

.graph-legend {
  justify-content: center;
  flex-wrap: wrap;
  gap: 18px;
  min-height: 46px;
  color: var(--text-secondary);
  font-size: var(--font-size-1);
}

.graph-legend span {
  gap: 7px;
}

.edge-sample {
  width: 28px;
  height: 1px;
  background: var(--text-muted);
}

.edge-sample--dashed {
  background: repeating-linear-gradient(90deg, var(--text-muted) 0 5px, transparent 5px 9px);
}

@media (max-width: 1300px) {
  .trace-page {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .event-inspector {
    display: none;
  }
}

@media (max-width: 820px) {
  .trace-page {
    grid-template-columns: minmax(0, 1fr);
    overflow: auto;
  }

  .trace-filters {
    max-height: 360px;
  }

  .trace-main {
    overflow: visible;
  }
}
</style>
