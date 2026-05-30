<script setup lang="ts">
import {
  AlertTriangle,
  Bot,
  Box,
  Boxes,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Download,
  ExternalLink,
  FileImage,
  Grid2X2,
  Loader2,
  MessageSquarePlus,
  MoreVertical,
  PanelRightOpen,
  Send,
  ShieldCheck,
  Sparkles,
  StopCircle,
  User,
  Wand2,
  Wrench,
  XCircle,
} from "lucide-vue-next";
import { computed, nextTick, onUnmounted, ref, watch, type Component } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { dataMode } from "@/shared/api/client";
import { formatBytes, formatDuration, formatLocalTime, formatNumber } from "@/shared/i18n/formatters";
import { useI18n } from "@/shared/i18n";
import type {
  TurnStepView,
  UiKeyValueSection,
  UiLinkedEntity,
  UiRuntimeAction,
  WorkbenchHomeReadModel,
  WorkbenchRunView,
  WorkbenchThreadSummary,
} from "@/shared/runtime/types";
import UiBadge from "@/shared/ui/UiBadge.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import UiCard from "@/shared/ui/UiCard.vue";
import MarkdownView from "@/shared/ui/MarkdownView.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import {
  getSkillDraft,
  type SkillDraftApiPayload,
} from "../settings/ownerApis/skillCatalog";
import {
  applyWorkbenchContextAction,
  cancelWorkbenchTurn,
  createWorkbenchTurn,
  listWorkbenchAgents,
  listWorkbenchModels,
  listWorkbenchTools,
  loadWorkbenchContextRenderSnapshot,
  loadWorkbenchContextTree,
  loadWorkbenchData,
  openEventStream,
  resolveWorkbenchApproval,
  uploadWorkbenchArtifact,
  type ApprovalDecision,
  type CreateTurnPayload,
  type EventConsoleRecord,
  type WorkbenchAgentProfile,
  type WorkbenchArtifactUpload,
  type WorkbenchContentBlock,
  type WorkbenchContextNode,
  type WorkbenchContextRenderSnapshot,
  type WorkbenchContextTree,
  type WorkbenchLlmProfile,
  type WorkbenchToolSummary,
} from "./api";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const home = ref<WorkbenchHomeReadModel | null>(null);
const activeThreadId = ref<string | null>(null);
const activeThreadFilterId = ref("all");
const loadingRun = ref(false);
const loadError = ref<string | null>(null);
const run = ref<WorkbenchRunView | null>(null);
const runSteps = ref<TurnStepView[]>([]);
const activeTurnId = ref<string | null>(null);
const turnsRow = ref<HTMLElement | null>(null);
const stepList = ref<HTMLElement | null>(null);
const composerInput = ref<HTMLInputElement | null>(null);
const attachmentInput = ref<HTMLInputElement | null>(null);
const composerContent = ref("");
const composerMode = ref<"continue" | "new">("continue");
const draftSessionKey = ref<string | null>(null);
const selectedAgentId = ref<string | null>(null);
const selectedModelId = ref<string | null>(null);
const agentsLoading = ref(false);
const modelsLoading = ref(false);
const runtimeOptionsLoaded = ref(false);
const runtimeOptionsError = ref<string | null>(null);
const workbenchAgents = ref<WorkbenchAgentProfile[]>([]);
const workbenchModels = ref<WorkbenchLlmProfile[]>([]);
const activeInspectorTab = ref<InspectorTabId>("overview");
const expandedStepIds = ref<Set<string>>(new Set());
const selectedStepId = ref<string | null>(null);
const attachedArtifacts = ref<WorkbenchArtifactUpload[]>([]);
const toolsOpen = ref(false);
const toolsLoading = ref(false);
const toolsLoaded = ref(false);
const toolsError = ref<string | null>(null);
const workbenchTools = ref<WorkbenchToolSummary[]>([]);
const contextTree = ref<WorkbenchContextTree | null>(null);
const contextRenderSnapshot = ref<WorkbenchContextRenderSnapshot | null>(null);
const contextTreeLoading = ref(false);
const contextTreeError = ref<string | null>(null);
const contextActionBusy = ref<string | null>(null);
const contextMemoryLayerFilter = ref<ContextMemoryLayerFilter>("all");
const contextXmlDisplayFoldedNodeIds = ref<Set<string>>(new Set());
const attachmentBusy = ref(false);
const attachmentError = ref<string | null>(null);
const pendingRunId = ref<string | null>(null);
const pendingSessionKey = ref<string | null>(null);
const commandBusy = ref<"send" | "cancel" | null>(null);
const commandError = ref<string | null>(null);
const approvalBusyStepId = ref<string | null>(null);
const approvalBusyDecision = ref<ApprovalDecision | null>(null);
const approvalErrorStepId = ref<string | null>(null);
const approvalError = ref<string | null>(null);
const skillApprovalDrafts = ref<Record<string, SkillApprovalDraftState>>({});
const liveStream = ref<LiveStreamState | null>(null);
const posterPreviewUrl = "/workbench-poster-preview.png";

const stepIcons: Record<TurnStepView["type"], Component> = {
  user_input: User,
  agent_thinking: Sparkles,
  llm: Brain,
  tool_call: Wrench,
  tool_result: Box,
  approval_required: ShieldCheck,
  missing_access: AlertTriangle,
  error: XCircle,
  final_response: CheckCircle2,
};

interface LinkedWorkbenchAsset {
  key: string;
  id: string;
  label: string;
  labelKey?: "workbench.asset.toolRun" | "workbench.asset.llmInvocation" | "workbench.asset.artifact";
  icon: Component;
  route: string;
}

interface LiveStreamState {
  runId: string | null;
  text: string;
  updatedAt: string | null;
}

interface SkillApprovalDraftState {
  loading: boolean;
  error: string | null;
  draft: SkillDraftApiPayload | null;
}

type InspectorTabId = "overview" | "step" | "debug" | "context" | "memory" | "agent";
type ContextMemoryLayerFilter = "all" | "private" | "shared" | "project" | "team" | "system";

const workbenchThreads = computed(() => home.value?.threads ?? []);
const activeThread = computed(() => workbenchThreads.value.find((thread) => thread.id === activeThreadId.value));
const threadFilters = computed(() => home.value?.filters ?? []);
const filteredWorkbenchThreads = computed(() => workbenchThreads.value.filter((thread) => threadMatchesFilter(thread, activeThreadFilterId.value)));
const isNewSessionDraft = computed(() => composerMode.value === "new" && draftSessionKey.value !== null);
const displayedTurns = computed(() => isNewSessionDraft.value ? [] : [...(run.value?.turns ?? [])].reverse());
const activeSteps = computed(() => isNewSessionDraft.value ? [] : runSteps.value.filter((step) => step.turn_id === activeTurnId.value));
const runningStep = computed(() => activeSteps.value.find((step) => step.status === "running"));
const linkedAssets = computed(() => collectLinkedAssets(activeSteps.value, isNewSessionDraft.value ? null : run.value?.trace.trace_id ?? null));
const runInspector = computed(() => isNewSessionDraft.value ? null : run.value?.inspector ?? null);
const backendQuickActions = computed(() => runInspector.value?.quick_actions ?? run.value?.actions ?? []);
const currentTurnSummary = computed(() => runInspector.value?.current_turn_summary ?? null);
const currentTurnToolName = computed(() => {
  const activeToolStep = runningStep.value ?? activeSteps.value.find((step) => step.type === "tool_call" || step.type === "tool_result");
  const label = activeToolStep?.badges[0]?.label;
  return label ? badgeLabel(label) : "-";
});
const connection = computed(() => home.value?.connection ?? null);
const connectionStripText = computed(() => {
  if (loadError.value) return loadError.value;
  const currentConnection = connection.value;
  if (!currentConnection) return `${t("common.connected")} · ${t("workbench.allServicesHealthy")}`;
  return currentConnection.details
    ? `${currentConnection.label} · ${currentConnection.details}`
    : currentConnection.label;
});
const runCoverPreviewUrl = computed(() => (
  run.value?.cover_artifact?.preview_url
  ?? run.value?.cover_artifact?.download_url
  ?? firstArtifactPreviewUrl(activeSteps.value)
  ?? posterPreviewUrl
));
const showRunEta = computed(() => (
  run.value?.status_strip?.eta_ms !== null
  && run.value?.status_strip?.eta_ms !== undefined
));
const composerPlaceholder = computed(() => (
  composerMode.value === "new"
    ? t("workbench.newTaskComposerPlaceholder")
    : t("workbench.composerPlaceholder")
));
const canSubmitComposer = computed(() => (
  (composerContent.value.trim().length > 0 || attachedArtifacts.value.length > 0)
  && commandBusy.value === null
  && !attachmentBusy.value
  && Boolean(selectedAgentId.value || realRunAgentId(run.value))
));
const canCancelRun = computed(() => {
  const status = run.value?.status;
  return !isNewSessionDraft.value && Boolean(run.value) && status !== "completed" && status !== "success" && status !== "failed" && status !== "cancelled";
});
const activeLiveStream = computed(() => {
  const stream = liveStream.value;
  if (!stream || isNewSessionDraft.value) return null;
  const streamRunId = stream.runId;
  if (streamRunId && !liveStreamMatchesCurrentRun(streamRunId)) return null;
  const currentRunStatus = streamRunId && streamRunId !== run.value?.run_id ? null : run.value?.status;
  if (currentRunStatus === "failed" || currentRunStatus === "cancelled") {
    return null;
  }
  if (
    (currentRunStatus === "completed" || currentRunStatus === "success")
    && activeSteps.value.some((step) => step.type === "final_response")
  ) return null;
  return stream.text.trim() ? stream : null;
});
const activeTimelineSteps = computed(() => {
  const steps = activeSteps.value;
  const stream = activeLiveStream.value;
  if (!stream || steps.some((step) => step.type === "final_response")) {
    return steps;
  }
  return [...steps, liveFinalResponseStep(stream)];
});
const selectedStep = computed(() => {
  const steps = activeTimelineSteps.value;
  return steps.find((step) => step.step_id === selectedStepId.value)
    ?? runningStep.value
    ?? steps[0]
    ?? null;
});
const selectedStepEntities = computed(() => selectedStep.value?.linked_entities ?? []);
const selectedStepActions = computed(() => selectedStep.value?.actions ?? []);
const enabledAgents = computed(() => workbenchAgents.value.filter((agent) => agent.enabled));
const enabledModels = computed(() => workbenchModels.value.filter((model) => model.enabled));
const selectedAgent = computed(() => enabledAgents.value.find((agent) => agent.id === selectedAgentId.value) ?? null);
const selectedAgentDefaultModelId = computed(() => selectedAgent.value?.llm_routing_policy.default_llm_id ?? null);
const selectableModels = computed(() => enabledModels.value.filter((model) => model.id !== selectedAgentDefaultModelId.value));
const inspectorTabs = computed<Array<{ id: InspectorTabId; label: string }>>(() => [
  { id: "overview", label: t("workbench.inspect.overview") },
  { id: "step", label: t("workbench.inspect.step") },
  { id: "debug", label: t("workbench.inspect.debug") },
  { id: "context", label: t("workbench.inspect.context") },
  { id: "memory", label: t("workbench.inspect.memory") },
  { id: "agent", label: t("workbench.inspect.agent") },
]);
const stepStats = computed(() => {
  const steps = activeSteps.value;
  return {
    total: steps.length,
    running: steps.filter((step) => step.status === "running").length,
    waiting: steps.filter((step) => step.status === "waiting" || step.status === "queued").length,
    failed: steps.filter((step) => step.status === "failed").length,
    tool: steps.filter((step) => step.type === "tool_call" || step.type === "tool_result" || step.trace.tool_run_id).length,
  };
});
const activeTurnSummary = computed(() => displayedTurns.value.find((turn) => turn.turn_id === activeTurnId.value) ?? null);
const contextSessionKey = computed(() => {
  if (isNewSessionDraft.value) return draftSessionKey.value;
  return run.value?.session_key ?? null;
});
const contextNodeRows = computed(() => flattenContextNodes(contextTree.value?.nodes ?? []));
const filteredContextNodeRows = computed(() => (
  reflowContextNodeRows(filterContextNodeRows(contextNodeRows.value, contextMemoryLayerFilter.value))
));
const contextXmlTree = computed(() => buildContextXmlTree(filteredContextNodeRows.value));
const contextXmlLines = computed(() => (
  buildContextXmlLines(contextXmlTree.value, contextXmlDisplayFoldedNodeIds.value)
    .map((line, index) => ({ ...line, lineNumber: index + 1 }))
));
const contextMemoryLayerOptions = computed<Array<{ id: ContextMemoryLayerFilter; label: string; count: number }>>(() => {
  const rows = contextNodeRows.value;
  const countFor = (layer: ContextMemoryLayerFilter) => (
    layer === "all"
      ? rows.length
      : rows.filter((node) => contextMemoryLayer(node) === layer).length
  );
  return [
    { id: "all", label: t("common.all"), count: countFor("all") },
    { id: "private", label: t("workbench.context.memory.private"), count: countFor("private") },
    { id: "shared", label: t("workbench.context.memory.shared"), count: countFor("shared") },
    { id: "project", label: t("workbench.context.memory.project"), count: countFor("project") },
    { id: "team", label: t("workbench.context.memory.team"), count: countFor("team") },
    { id: "system", label: t("workbench.context.memory.system"), count: countFor("system") },
  ];
});
const contextEstimateRows = computed(() => {
  const estimate = contextTree.value?.estimate;
  if (!estimate) return [];
  return [
    { label: t("workbench.context.textTokens"), value: formatNumber(estimate.text_tokens) },
    { label: t("workbench.context.toolSchemaTokens"), value: formatNumber(estimate.tool_schema_tokens) },
    { label: t("workbench.context.fileTokens"), value: formatNumber(estimate.file_tokens) },
    { label: t("workbench.context.images"), value: formatNumber(estimate.image_count) },
    { label: t("workbench.context.attachments"), value: formatNumber(estimate.provider_attachment_count) },
  ];
});
const contextSnapshotRows = computed(() => {
  const snapshot = contextRenderSnapshot.value;
  if (!snapshot) return [];
  return [
    { label: t("trace.id.run"), value: compactIdentifier(snapshot.run_id) },
    { label: t("workbench.context.revision"), value: String(snapshot.tree_revision) },
    { label: t("workbench.context.includedNodes"), value: formatNumber(snapshot.included_node_ids.length) },
    { label: t("workbench.context.mirroredNodes"), value: formatNumber(snapshot.mirrored_node_ids.length) },
    { label: t("common.tokens"), value: formatNumber(snapshot.estimate.text_tokens + snapshot.estimate.tool_schema_tokens + snapshot.estimate.file_tokens) },
    { label: t("table.createdAt"), value: formatLocalTime(snapshot.created_at) },
  ];
});

const draftRunId = "__workbench_draft__";
let refreshSerial = 0;
let closeRelayStream: (() => void) | null = null;
let refreshTimer: ReturnType<typeof window.setTimeout> | null = null;
let liveScrollFrame: number | null = null;

watch(
  () => [route.params.runId, route.params.sessionKey],
  () => {
    clearLiveFlow();
    toolsOpen.value = false;
    expandedStepIds.value = new Set();
    selectedStepId.value = null;
    void refreshWorkbench();
  },
  { immediate: true },
);

watch(
  () => [activeInspectorTab.value, contextSessionKey.value],
  () => {
    if (activeInspectorTab.value === "context") {
      void refreshContextTree();
    }
  },
);

watch(
  () => [
    contextTree.value?.workspace?.session_key ?? "",
    contextTree.value?.workspace?.active_revision ?? "",
    contextMemoryLayerFilter.value,
  ],
  () => {
    contextXmlDisplayFoldedNodeIds.value = new Set();
  },
);

if (dataMode === "api") {
  closeRelayStream = openEventStream(
    {
      topicPrefix: "event_relay.workbench",
      snapshotLimit: 0,
      timeoutSeconds: 300,
    },
    {
      event: handleRelayEvent,
    },
  );
}

void loadRuntimeOptions();

onUnmounted(() => {
  closeRelayStream?.();
  if (refreshTimer !== null) {
    window.clearTimeout(refreshTimer);
  }
  if (liveScrollFrame !== null) {
    window.cancelAnimationFrame(liveScrollFrame);
  }
});

async function refreshWorkbench() {
  const serial = ++refreshSerial;
  loadingRun.value = true;
  loadError.value = null;
  try {
    const loaded = await loadWorkbenchData({
      runId: routeParam("runId"),
      sessionKey: routeParam("sessionKey"),
    });
    if (serial !== refreshSerial) return;
    home.value = loaded.home;
    run.value = loaded.run ?? createDraftWorkbenchRun();
    runSteps.value = loaded.steps;
    void loadSkillApprovalDrafts(loaded.steps);
    if (!loaded.run) {
      composerMode.value = "new";
      ensureDraftSessionKey();
    }
    syncComposerRuntimeSelection(loaded.run);
    if (loaded.run?.run_id === pendingRunId.value) {
      pendingRunId.value = null;
    }
    if (loaded.run?.session_key === pendingSessionKey.value) {
      pendingSessionKey.value = null;
    }
    if (isNewSessionDraft.value) {
      activeTurnId.value = null;
      activeThreadId.value = null;
    } else {
      activeTurnId.value = loaded.run?.current_turn_id ?? null;
      activeThreadId.value = loaded.home.active_thread_id ?? loaded.run?.session_key ?? null;
    }
    void nextTick(scrollActiveTurnTab);
  } catch (error) {
    if (serial !== refreshSerial) return;
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    if (serial === refreshSerial) {
      loadingRun.value = false;
    }
  }
}

async function refreshContextTree() {
  const sessionKey = contextSessionKey.value;
  if (dataMode !== "api" || !sessionKey || isNewSessionDraft.value) {
    contextTree.value = null;
    contextRenderSnapshot.value = null;
    contextTreeError.value = null;
    return;
  }
  contextTreeLoading.value = true;
  contextTreeError.value = null;
  try {
    const [tree, snapshot] = await Promise.all([
      loadWorkbenchContextTree(sessionKey),
      run.value?.run_id ? loadWorkbenchContextRenderSnapshot(run.value.run_id) : Promise.resolve(null),
    ]);
    contextTree.value = tree;
    contextRenderSnapshot.value = snapshot;
  } catch (error) {
    contextTree.value = null;
    contextRenderSnapshot.value = null;
    contextTreeError.value = commandErrorMessage(error);
  } finally {
    contextTreeLoading.value = false;
  }
}

async function runContextNodeAction(node: WorkbenchContextNode, action: string) {
  const sessionKey = contextSessionKey.value;
  if (!sessionKey || contextActionBusy.value) return;
  contextActionBusy.value = `${node.id}:${action}`;
  contextTreeError.value = null;
  try {
    await applyWorkbenchContextAction(sessionKey, node.id, action, run.value?.run_id ?? null);
    await refreshContextTree();
  } catch (error) {
    contextTreeError.value = commandErrorMessage(error);
  } finally {
    contextActionBusy.value = null;
  }
}

async function loadRuntimeOptions() {
  if (dataMode !== "api" || runtimeOptionsLoaded.value || agentsLoading.value || modelsLoading.value) return;

  agentsLoading.value = true;
  modelsLoading.value = true;
  runtimeOptionsError.value = null;
  try {
    const [agents, models] = await Promise.all([
      listWorkbenchAgents(),
      listWorkbenchModels(),
    ]);
    workbenchAgents.value = agents;
    workbenchModels.value = models;
    runtimeOptionsLoaded.value = true;
    syncComposerRuntimeSelection(run.value);
    if (isDraftRunView(run.value)) {
      run.value = createDraftWorkbenchRun();
    }
  } catch (error) {
    runtimeOptionsError.value = commandErrorMessage(error);
  } finally {
    agentsLoading.value = false;
    modelsLoading.value = false;
  }
}

async function submitComposer() {
  const content = composerContent.value.trim();
  const currentRun = run.value;
  if ((!content && attachedArtifacts.value.length === 0) || commandBusy.value !== null || attachmentBusy.value) return;
  if (!currentRun && composerMode.value !== "new") return;

  commandBusy.value = "send";
  commandError.value = null;
  try {
    const response = await createWorkbenchTurn(buildCreateTurnPayload(buildComposerContent(content), currentRun));
    pendingRunId.value = response.run.id;
    pendingSessionKey.value = response.run.session_key;
    activeTurnId.value = response.run.id;
    activeThreadId.value = response.run.session_key;
    runSteps.value = [];
    liveStream.value = null;
    composerContent.value = "";
    attachedArtifacts.value = [];
    composerMode.value = "continue";
    draftSessionKey.value = null;
    await router.push(`/workbench/runs/${encodeURIComponent(response.run.id)}`);
    await refreshWorkbench();
  } catch (error) {
    commandError.value = commandErrorMessage(error);
  } finally {
    commandBusy.value = null;
  }
}

async function cancelActiveRun() {
  const currentRun = run.value;
  if (!currentRun || !canCancelRun.value || commandBusy.value !== null) return;

  commandBusy.value = "cancel";
  commandError.value = null;
  try {
    await cancelWorkbenchTurn(currentRun.run_id, t("workbench.cancelReason"));
    await refreshWorkbench();
  } catch (error) {
    commandError.value = commandErrorMessage(error);
  } finally {
    commandBusy.value = null;
  }
}

async function resolveApprovalStep(step: TurnStepView, decision: ApprovalDecision) {
  const currentRun = run.value;
  const requestId = approvalRequestId(step);
  const runId = step.run_id || currentRun?.run_id;
  if (!requestId || !runId || approvalBusyStepId.value !== null) return;

  approvalBusyStepId.value = step.step_id;
  approvalBusyDecision.value = decision;
  approvalErrorStepId.value = null;
  approvalError.value = null;
  try {
    const response = await resolveWorkbenchApproval(runId, requestId, decision);
    liveStream.value = null;
    if (response.run.id && response.run.id !== routeParam("runId")) {
      await router.push(`/workbench/runs/${encodeURIComponent(response.run.id)}`);
    }
    await refreshWorkbench();
  } catch (error) {
    approvalErrorStepId.value = step.step_id;
    approvalError.value = commandErrorMessage(error);
  } finally {
    approvalBusyStepId.value = null;
    approvalBusyDecision.value = null;
  }
}

async function loadSkillApprovalDrafts(steps: TurnStepView[]) {
  const draftIds = Array.from(new Set(steps.map(skillApprovalDraftId).filter((id): id is string => Boolean(id))));
  if (!draftIds.length) return;
  for (const draftId of draftIds) {
    const current = skillApprovalDrafts.value[draftId];
    if (current?.loading || current?.draft) continue;
    skillApprovalDrafts.value = {
      ...skillApprovalDrafts.value,
      [draftId]: { loading: true, error: null, draft: null },
    };
    try {
      const draft = await getSkillDraft(draftId);
      skillApprovalDrafts.value = {
        ...skillApprovalDrafts.value,
        [draftId]: { loading: false, error: null, draft },
      };
    } catch (error) {
      skillApprovalDrafts.value = {
        ...skillApprovalDrafts.value,
        [draftId]: {
          loading: false,
          error: commandErrorMessage(error),
          draft: null,
        },
      };
    }
  }
}

function skillApprovalDraftId(step: TurnStepView): string | null {
  if (step.approval?.tool_name !== "skill_draft_apply") return null;
  const direct = normalizeText(step.approval.draft_id);
  if (direct) return direct;
  const fromArgs = normalizeText(step.approval.tool_arguments?.draft_id);
  return fromArgs || null;
}

function skillApprovalDraftState(step: TurnStepView): SkillApprovalDraftState | null {
  const draftId = skillApprovalDraftId(step);
  if (!draftId) return null;
  return skillApprovalDrafts.value[draftId] ?? { loading: true, error: null, draft: null };
}

function normalizeText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function syncComposerRuntimeSelection(currentRun: WorkbenchRunView | null, options: { force?: boolean } = {}) {
  const force = options.force ?? composerMode.value === "continue";
  if (!currentRun || isDraftRunView(currentRun)) {
    selectedAgentId.value = selectedAgentId.value ?? enabledAgents.value[0]?.id ?? null;
    selectedModelId.value = selectedModelId.value ?? selectedAgentDefaultModelId.value ?? enabledModels.value[0]?.id ?? null;
    return;
  }
  if (isNewSessionDraft.value && !force) {
    if (!selectedAgentId.value) {
      selectedAgentId.value = currentRun.agent.id !== "unknown" ? currentRun.agent.id : enabledAgents.value[0]?.id ?? null;
    }
    if (!selectedModelId.value) {
      selectedModelId.value = currentRun.model.id !== "auto" ? currentRun.model.id : selectedAgentDefaultModelId.value;
    }
    return;
  }
  selectedAgentId.value = currentRun.agent.id !== "unknown" ? currentRun.agent.id : enabledAgents.value[0]?.id ?? null;
  selectedModelId.value = currentRun.model.id !== "auto" ? currentRun.model.id : selectedAgentDefaultModelId.value;
}

function handleAgentSelection(event: Event) {
  const value = (event.target as HTMLSelectElement).value || null;
  selectedAgentId.value = value;
  const agentDefaultModel = enabledAgents.value.find((agent) => agent.id === value)?.llm_routing_policy.default_llm_id ?? null;
  selectedModelId.value = agentDefaultModel || (enabledModels.value[0]?.id ?? null);
  if (composerMode.value === "continue" && run.value && value && value !== run.value.agent.id) {
    switchComposerToDraft();
  }
}

function handleModelSelection(event: Event) {
  selectedModelId.value = (event.target as HTMLSelectElement).value || null;
}

function switchComposerToDraft() {
  composerMode.value = "new";
  draftSessionKey.value = createDraftSessionKey();
  pendingRunId.value = null;
  pendingSessionKey.value = null;
  activeThreadId.value = null;
  activeTurnId.value = null;
  toolsOpen.value = false;
  commandError.value = null;
}

function startNewTask() {
  composerMode.value = "new";
  draftSessionKey.value = createDraftSessionKey();
  pendingRunId.value = null;
  pendingSessionKey.value = null;
  composerContent.value = "";
  attachedArtifacts.value = [];
  attachmentError.value = null;
  toolsOpen.value = false;
  commandError.value = null;
  syncComposerRuntimeSelection(run.value, { force: false });
  if (!run.value || isDraftRunView(run.value)) {
    run.value = createDraftWorkbenchRun();
  }
  activeThreadId.value = null;
  activeTurnId.value = null;
  void nextTick(() => composerInput.value?.focus());
}

function discardDraftSession() {
  composerMode.value = "continue";
  draftSessionKey.value = null;
  pendingRunId.value = null;
  pendingSessionKey.value = null;
  commandError.value = null;
  attachmentError.value = null;
  toolsOpen.value = false;
  if (isDraftRunView(run.value) && !home.value?.active_run_id) {
    startNewTask();
    return;
  }
  activeTurnId.value = run.value?.current_turn_id ?? null;
  activeThreadId.value = home.value?.active_thread_id ?? run.value?.session_key ?? null;
  void nextTick(scrollActiveTurnTab);
}

function buildCreateTurnPayload(content: string | WorkbenchContentBlock[], currentRun: WorkbenchRunView | null): CreateTurnPayload {
  const selectedAgent = selectedAgentId.value?.trim() || null;
  const selectedModel = selectedModelId.value?.trim() || null;
  const currentAgentId = currentRun?.agent.id && currentRun.agent.id !== "unknown" ? currentRun.agent.id : null;
  const agentId = composerMode.value === "continue"
    ? currentAgentId ?? selectedAgent ?? undefined
    : selectedAgent ?? currentAgentId ?? undefined;
  const payload: CreateTurnPayload = {
    content,
    source: "ui.workbench",
    queue_policy: "jump_queue",
    priority: 100,
    channel: "crxzipple",
    chat_type: "direct",
    direct_scope: "main",
    main_key: "main",
  };
  if (agentId) {
    payload.agent_id = agentId;
  }
  if (selectedModel && selectedModel !== "auto") {
    payload.llm_id = selectedModel;
  } else if (composerMode.value === "continue" && currentRun?.model.id && currentRun.model.id !== "auto") {
    payload.llm_id = currentRun.model.id;
  }
  if (composerMode.value === "new") {
    payload.main_key = ensureDraftSessionKey();
    return payload;
  }
  if (!currentRun) {
    return payload;
  }
  return {
    ...payload,
    ...sessionRouteFromKey(currentRun.session_key, agentId),
  };
}

function buildComposerContent(text: string): string | WorkbenchContentBlock[] {
  if (!attachedArtifacts.value.length) return text;
  const blocks: WorkbenchContentBlock[] = [];
  if (text) {
    blocks.push({ type: "text", text });
  }
  for (const artifact of attachedArtifacts.value) {
    if (artifact.kind === "image" || artifact.mime_type.startsWith("image/")) {
      blocks.push({
        type: "image_ref",
        artifact_id: artifact.id,
        mime_type: artifact.mime_type,
        name: artifact.name ?? artifact.id,
        width: artifact.width,
        height: artifact.height,
        preview_url: artifact.preview_url,
        original_url: artifact.original_url,
      });
    } else {
      blocks.push({
        type: "file_ref",
        artifact_id: artifact.id,
        mime_type: artifact.mime_type,
        name: artifact.name ?? artifact.id,
        download_url: artifact.download_url,
      });
    }
  }
  return blocks;
}

function createDraftSessionKey() {
  return `workbench-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function ensureDraftSessionKey() {
  if (draftSessionKey.value === null) {
    draftSessionKey.value = createDraftSessionKey();
  }
  return draftSessionKey.value;
}

function createDraftWorkbenchRun(): WorkbenchRunView {
  const sessionKey = ensureDraftSessionKey();
  const agent = selectedAgent.value ?? enabledAgents.value[0] ?? null;
  const agentId = selectedAgentId.value ?? agent?.id ?? "unknown";
  const agentName = agent?.name || agentId;
  const modelId = selectedModelId.value ?? selectedAgentDefaultModelId.value ?? enabledModels.value[0]?.id ?? "auto";
  const model = enabledModels.value.find((item) => item.id === modelId) ?? null;
  return {
    run_id: draftRunId,
    session_key: sessionKey,
    title: t("workbench.newSessionTitle"),
    status: "accepted",
    agent: { id: agentId, name: agentName },
    model: { id: modelId, name: model?.model_name ?? modelId },
    started_at: null,
    completed_at: null,
    duration_ms: null,
    metrics: {
      tool_calls: 0,
      llm_calls: 0,
      tokens: 0,
      estimated_cost_usd: null,
    },
    turns: [],
    current_turn_id: null,
    status_strip: null,
    cover_artifact: null,
    actions: home.value?.actions ?? [],
    inspector: null,
    trace: {
      trace_id: draftRunId,
      session_key: sessionKey,
      run_id: draftRunId,
    },
  };
}

function isDraftRunView(value: WorkbenchRunView | null): boolean {
  return value?.run_id === draftRunId;
}

function realRunAgentId(value: WorkbenchRunView | null): string | null {
  if (!value || isDraftRunView(value) || value.agent.id === "unknown") return null;
  return value.agent.id;
}

function sessionRouteFromKey(sessionKey: string, agentId: string | undefined): Partial<CreateTurnPayload> {
  if (!agentId) return {};
  const prefix = `agent:${agentId}:`;
  if (!sessionKey.startsWith(prefix)) return {};

  const { base, threadId } = splitThreadSuffix(sessionKey.slice(prefix.length));
  const route: Partial<CreateTurnPayload> = {};
  if (threadId) {
    route.thread_id = threadId;
  }

  const parts = base.split(":").filter(Boolean);
  if (parts[0] === "dm" && parts[1]) {
    return { ...route, chat_type: "direct", direct_scope: "per_peer", peer_id: parts.slice(1).join(":") };
  }
  if (parts.length >= 3 && parts[1] === "dm") {
    return { ...route, chat_type: "direct", direct_scope: "per_channel_peer", channel: parts[0], peer_id: parts.slice(2).join(":") };
  }
  if (parts.length >= 4 && parts[2] === "dm") {
    return {
      ...route,
      chat_type: "direct",
      direct_scope: "per_account_channel_peer",
      channel: parts[0],
      account_id: parts[1],
      peer_id: parts.slice(3).join(":"),
    };
  }
  if (parts.length >= 3 && (parts[1] === "channel" || parts[1] === "group")) {
    return {
      ...route,
      chat_type: parts[1],
      channel: parts[0],
      conversation_id: parts.slice(2).join(":"),
    };
  }
  return { ...route, chat_type: "direct", direct_scope: "main", main_key: base || "main" };
}

function splitThreadSuffix(value: string) {
  const marker = ":thread:";
  const index = value.indexOf(marker);
  if (index === -1) return { base: value, threadId: null as string | null };
  return {
    base: value.slice(0, index),
    threadId: value.slice(index + marker.length) || null,
  };
}

function collectLinkedAssets(steps: TurnStepView[], traceId: string | null): LinkedWorkbenchAsset[] {
  const route = traceId ? `/trace/${encodeURIComponent(traceId)}` : "/trace";
  const seen = new Set<string>();
  const assets: LinkedWorkbenchAsset[] = [];

  function add(asset: Omit<LinkedWorkbenchAsset, "key" | "route"> & { route?: string }) {
    const key = `${asset.labelKey ?? asset.label}:${asset.id}`;
    if (seen.has(key)) return;
    seen.add(key);
    assets.push({ ...asset, key, route: asset.route ?? route });
  }

  for (const entity of runInspector.value?.linked_assets ?? []) {
    add(linkedAssetFromEntity(entity, route));
  }
  for (const step of steps) {
    for (const entity of step.linked_entities ?? []) {
      add(linkedAssetFromEntity(entity, route));
    }
    if (step.trace.tool_run_id) {
      add({ id: step.trace.tool_run_id, label: t("workbench.asset.toolRun"), labelKey: "workbench.asset.toolRun", icon: Wrench });
    }
    if (step.trace.llm_invocation_id) {
      add({ id: step.trace.llm_invocation_id, label: t("workbench.asset.llmInvocation"), labelKey: "workbench.asset.llmInvocation", icon: Brain });
    }
    if (step.trace.artifact_id) {
      add({ id: step.trace.artifact_id, label: t("workbench.asset.artifact"), labelKey: "workbench.asset.artifact", icon: FileImage });
    }
    for (const artifact of step.artifacts) {
      add({ id: artifact.artifact_id, label: t("workbench.asset.artifact"), labelKey: "workbench.asset.artifact", icon: FileImage });
    }
  }

  return assets.slice(0, 8);
}

function linkedAssetFromEntity(entity: UiLinkedEntity, fallbackRoute: string): Omit<LinkedWorkbenchAsset, "key"> {
  const labelKey = linkedEntityLabelKey(entity.type);
  return {
    id: entity.id,
    label: entity.label ?? (labelKey ? t(labelKey) : entity.type),
    labelKey,
    icon: linkedEntityIcon(entity.type),
    route: entity.route ?? fallbackRoute,
  };
}

function linkedEntityLabelKey(type: string): LinkedWorkbenchAsset["labelKey"] | undefined {
  if (type === "tool_run") return "workbench.asset.toolRun";
  if (type === "llm_invocation") return "workbench.asset.llmInvocation";
  if (type === "artifact") return "workbench.asset.artifact";
  return undefined;
}

function linkedEntityIcon(type: string): Component {
  if (type === "tool_run") return Wrench;
  if (type === "llm_invocation") return Brain;
  if (type === "artifact") return FileImage;
  if (type.includes("access")) return AlertTriangle;
  return PanelRightOpen;
}

function commandErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

async function toggleToolsMenu() {
  toolsOpen.value = !toolsOpen.value;
  if (toolsOpen.value && !toolsLoaded.value && !toolsLoading.value) {
    await loadWorkbenchToolCatalog();
  }
}

async function loadWorkbenchToolCatalog() {
  toolsLoading.value = true;
  toolsError.value = null;
  try {
    workbenchTools.value = await listWorkbenchTools();
    toolsLoaded.value = true;
  } catch (error) {
    toolsError.value = commandErrorMessage(error);
  } finally {
    toolsLoading.value = false;
  }
}

function insertToolPrompt(tool: WorkbenchToolSummary) {
  const prefix = composerContent.value.trim() ? "\n" : "";
  composerContent.value = `${composerContent.value}${prefix}${t("workbench.composer.useTool", { tool: tool.id })}`;
  toolsOpen.value = false;
  void nextTick(() => composerInput.value?.focus());
}

function openAttachmentPicker() {
  attachmentError.value = null;
  attachmentInput.value?.click();
}

async function handleAttachmentInput(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = "";
  if (!files.length) return;

  attachmentBusy.value = true;
  attachmentError.value = null;
  try {
    const uploads = await Promise.all(files.map((file) => uploadWorkbenchArtifact(file)));
    attachedArtifacts.value = [...attachedArtifacts.value, ...uploads];
  } catch (error) {
    attachmentError.value = commandErrorMessage(error);
  } finally {
    attachmentBusy.value = false;
  }
}

function removeAttachment(artifactId: string) {
  attachedArtifacts.value = attachedArtifacts.value.filter((artifact) => artifact.id !== artifactId);
}

function toggleStepDetails(stepId: string) {
  const next = new Set(expandedStepIds.value);
  if (next.has(stepId)) {
    next.delete(stepId);
  } else {
    next.add(stepId);
  }
  expandedStepIds.value = next;
}

function selectStepForInspector(step: TurnStepView) {
  selectedStepId.value = step.step_id;
  activeInspectorTab.value = "step";
}

function isStepExpanded(stepId: string) {
  return expandedStepIds.value.has(stepId);
}

function stepDetailRows(step: TurnStepView) {
  const rows: Array<{ label: string; value: string }> = [
    { label: t("workbench.details.stepId"), value: step.step_id },
    { label: t("trace.id.run"), value: step.run_id },
    { label: t("trace.id.turn"), value: step.turn_id },
    { label: t("common.status"), value: t(`status.${step.status}`) },
  ];
  if (step.duration_ms !== null) {
    rows.push({ label: t("common.duration"), value: formatDuration(step.duration_ms) });
  }
  if (step.trace.tool_run_id) {
    rows.push({ label: t("trace.id.toolRun"), value: step.trace.tool_run_id });
  }
  if (step.trace.llm_invocation_id) {
    rows.push({ label: t("trace.id.llmInvocation"), value: step.trace.llm_invocation_id });
  }
  if (step.trace.artifact_id) {
    rows.push({ label: t("trace.id.artifact"), value: step.trace.artifact_id });
  }
  if (step.trace.approval_request_id) {
    rows.push({ label: t("workbench.details.approvalRequest"), value: step.trace.approval_request_id });
  }
  return rows;
}

function exportActiveRun() {
  const currentRun = run.value;
  if (!currentRun || isNewSessionDraft.value) return;
  const payload = {
    exported_at: new Date().toISOString(),
    run: currentRun,
    steps: runSteps.value,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${currentRun.run_id}.workbench.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

watch(activeTurnId, () => {
  selectedStepId.value = null;
  void nextTick(scrollActiveTurnTab);
});

watch(activeTimelineSteps, (steps) => {
  if (!steps.length) {
    selectedStepId.value = null;
    return;
  }
  if (!selectedStepId.value || !steps.some((step) => step.step_id === selectedStepId.value)) {
    selectedStepId.value = (runningStep.value ?? steps[0]).step_id;
  }
});

watch(threadFilters, (filters) => {
  if (!filters.some((filter) => filter.id === activeThreadFilterId.value)) {
    activeThreadFilterId.value = "all";
  }
});

watch(
  () => activeLiveStream.value ? `${activeLiveStream.value.runId ?? ""}:${activeLiveStream.value.text.length}` : "",
  () => {
    queueLiveFinalScroll();
  },
  { flush: "post" },
);

function routeParam(name: "runId" | "sessionKey") {
  const value = route.params[name];
  return typeof value === "string" ? value : null;
}

function handleRelayEvent(record: EventConsoleRecord) {
  const payload = record.source_payload;
  if (!payload || !relayPayloadMatches(payload)) return;
  applyLiveRelayPayload(record, payload);
  const refreshDelay = payload.target === "llm_delta" ? 900 : 160;
  scheduleWorkbenchRefresh(refreshDelay);
}

function scheduleWorkbenchRefresh(delayMs: number) {
  if (refreshTimer !== null) {
    window.clearTimeout(refreshTimer);
  }
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    void refreshWorkbench();
  }, delayMs);
}

function relayPayloadMatches(payload: Record<string, unknown>) {
  if (payload.surface !== "workbench") return false;
  const payloadRunId = typeof payload.run_id === "string" ? payload.run_id : null;
  const payloadSessionKey = typeof payload.session_key === "string" ? payload.session_key : null;
  if (!payloadRunId && !payloadSessionKey) return true;
  if (payloadRunId && liveStreamMatchesCurrentRun(payloadRunId)) return true;
  if (payloadSessionKey && liveSessionMatchesCurrentThread(payloadSessionKey)) return true;
  return !run.value;
}

function liveStreamMatchesCurrentRun(runId: string) {
  return [
    run.value?.run_id,
    activeTurnId.value,
    pendingRunId.value,
    routeParam("runId"),
  ].some((candidate) => candidate === runId);
}

function liveSessionMatchesCurrentThread(sessionKey: string) {
  return [
    activeThreadId.value,
    pendingSessionKey.value,
    run.value?.session_key,
    routeParam("sessionKey"),
  ].some((candidate) => candidate === sessionKey);
}

function applyLiveRelayPayload(record: EventConsoleRecord, payload: Record<string, unknown>) {
  const target = typeof payload.target === "string" ? payload.target : "update";
  const reason = typeof payload.reason === "string" ? payload.reason : record.event_name;
  const runId = typeof payload.run_id === "string" ? payload.run_id : null;
  const delta = isRecord(payload.delta) ? payload.delta : null;
  if (target === "llm_delta" && delta) {
    applyLiveTextDelta(runId, delta, record.created_at ?? null);
  }
  if (reason === "orchestration.run.failed" || reason === "orchestration.run.cancelled") {
    liveStream.value = null;
  }
}

function applyLiveTextDelta(runId: string | null, delta: Record<string, unknown>, updatedAt: string | null) {
  const text = typeof delta.text === "string" ? delta.text : "";
  const textDelta = typeof delta.text_delta === "string" ? delta.text_delta : "";
  const previous = liveStream.value?.runId === runId ? liveStream.value.text : "";
  liveStream.value = {
    runId,
    text: text || `${previous}${textDelta}`,
    updatedAt,
  };
}

function liveFinalResponseStep(stream: LiveStreamState): TurnStepView {
  const currentRun = run.value;
  const turnId = activeTurnId.value ?? currentRun?.current_turn_id ?? currentRun?.run_id ?? stream.runId ?? "live";
  const runId = stream.runId ?? currentRun?.run_id ?? turnId;
  const stepId = `${runId}:final_response`;
  return {
    step_id: stepId,
    turn_id: turnId,
    run_id: runId,
    type: "final_response",
    status: "running",
    title: "Final Response",
    summary: stream.text,
    markdown: stream.text,
    started_at: stream.updatedAt ?? currentRun?.started_at ?? null,
    completed_at: null,
    duration_ms: null,
    artifacts: [],
    badges: [{ label: t("workbench.live.receiving"), tone: "info" }],
    details_available: false,
    trace: {
      ...(currentRun?.trace ?? { trace_id: runId }),
      run_id: runId,
      turn_id: turnId,
      step_id: stepId,
    },
  };
}

function clearLiveFlow() {
  liveStream.value = null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toneForStatus(status: string): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "success" || status === "completed" || status === "connected") return "success";
  if (status === "running" || status === "connecting") return "info";
  if (status === "waiting" || status === "queued" || status === "degraded") return "warning";
  if (status === "failed" || status === "offline" || status === "error") return "danger";
  return "neutral";
}

function stepVisualTone(step: TurnStepView) {
  if (step.status === "failed" || step.type === "error") return "danger";
  if (step.status === "waiting" || step.status === "queued" || step.type === "approval_required" || step.type === "missing_access") {
    return "warning";
  }
  if (step.type === "user_input") return "user";
  if (step.type === "llm" || step.type === "agent_thinking") return "llm";
  if (step.type === "tool_call") return "tool-call";
  if (step.type === "tool_result") return "tool-result";
  if (step.type === "final_response") return "final";
  return "neutral";
}

function iconForStep(type: TurnStepView["type"]) {
  return stepIcons[type] ?? Bot;
}

function stepTime(value: string | null) {
  return value ? formatLocalTime(value) : "-";
}

function relativeThreadTime(updatedAt: string) {
  const updatedTime = Date.parse(updatedAt);
  if (Number.isNaN(updatedTime)) return "";
  const deltaMinutes = Math.max(Math.round((Date.now() - updatedTime) / 60000), 0);
  if (deltaMinutes < 60) {
    return t("workbench.relativeMinutesAgo", { count: Math.max(deltaMinutes, 1) });
  }
  return t("workbench.relativeHoursAgo", { count: Math.max(Math.round(deltaMinutes / 60), 1) });
}

function threadAdornment(thread: WorkbenchThreadSummary) {
  if (thread.status === "running" || thread.status === "accepted") return "spinner";
  if (thread.status === "waiting" || thread.status === "queued") return "waiting";
  if (thread.status === "completed" || thread.status === "success") return "check";
  if (thread.status === "failed" || thread.status === "cancelled") return "alert";
  if (thread.starred) return "star";
  return "none";
}

function threadLastAction(thread: WorkbenchThreadSummary) {
  return thread.current_activity;
}

function threadTitle(thread: WorkbenchThreadSummary) {
  return thread.title;
}

function runTitle(currentRun: WorkbenchRunView) {
  return currentRun.title;
}

function stepTitle(step: TurnStepView) {
  if (step.type === "tool_call" || step.type === "tool_result") {
    if (!step.title || step.title === "Tool Call" || step.title === "Tool Execution") {
      return t("workbench.badge.toolCall");
    }
    if (step.title === "Tool Result") return t("workbench.badge.toolResult");
    if (step.title === "Tool Failed") return t("status.failed");
    return step.title;
  }
  const byId = {
    step_user_input: t("workbench.step.userInput.title"),
    step_llm: t("workbench.step.llm.title"),
    step_tool_call: t("workbench.step.imageGeneration.title"),
    step_tool_result: t("workbench.step.imageGenerated.title"),
    step_final: t("workbench.step.final.title"),
  }[step.step_id];
  if (byId) return byId;
  const byType: Partial<Record<TurnStepView["type"], string>> = {
    user_input: t("workbench.step.userInput.title"),
    agent_thinking: t("workbench.step.llm.title"),
    llm: t("workbench.step.llm.title"),
    tool_call: t("workbench.badge.toolCall"),
    tool_result: t("workbench.badge.toolResult"),
    approval_required: t("workbench.step.approval.title"),
    missing_access: t("workbench.step.imageGeneration.title"),
    error: t("status.failed"),
    final_response: t("workbench.step.final.title"),
  };
  return byType[step.type] ?? step.title;
}

function stepSummary(step: TurnStepView) {
  if (step.type === "approval_required") {
    return approvalSummary(step.summary);
  }
  return {
    step_user_input: t("workbench.step.userInput.summary"),
    step_llm: t("workbench.step.llm.summary"),
    step_tool_call: t("workbench.step.imageGeneration.summary"),
    step_tool_result: t("workbench.step.imageGenerated.summary"),
    step_final: t("workbench.step.final.summary"),
  }[step.step_id] ?? step.summary;
}

function badgeLabel(label: string) {
  return {
    "Tool Call": t("workbench.badge.toolCall"),
    "Tool Result": t("workbench.badge.toolResult"),
    Authorization: t("workbench.badge.authorization"),
  }[label] ?? label;
}

function approvalSummary(summary: string) {
  const capabilityMatch = summary.match(/^Approval is required for (.+)\.?$/);
  if (capabilityMatch?.[1]) {
    return t("workbench.step.approval.summaryWithCapability", {
      capability: capabilityMatch[1].replace(/\.$/, ""),
    });
  }
  if (summary === "Approval is required before the run can continue.") {
    return t("workbench.step.approval.summary");
  }
  return summary;
}

function statusStripLabel(label: string | null | undefined) {
  return label === "正在生成图片" ? t("workbench.status.generatingImage") : label;
}

function artifactPreviewUrl(artifact: TurnStepView["artifacts"][number]) {
  return artifact.preview_url ?? artifact.thumbnail_url ?? artifact.download_url ?? posterPreviewUrl;
}

function firstArtifactPreviewUrl(steps: TurnStepView[]) {
  const artifact = steps
    .flatMap((step) => step.artifacts)
    .find((item) => item.preview_url || item.thumbnail_url || item.download_url);
  return artifact ? artifactPreviewUrl(artifact) : null;
}

function artifactResolution(artifact: TurnStepView["artifacts"][number]) {
  if (artifact.width && artifact.height) {
    return `${artifact.width} × ${artifact.height}`;
  }
  return "-";
}

function compactIdentifier(value: string | null | undefined, head = 12, tail = 8) {
  if (!value) return "-";
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function compactInspectorValue(value: string | null | undefined) {
  if (!value) return "-";
  const isMachineValue = /^[a-z0-9:_./-]+$/i.test(value) || /^[a-f0-9]{16,}$/i.test(value);
  return isMachineValue ? compactIdentifier(value) : value;
}

interface WorkbenchContextNodeRow extends WorkbenchContextNode {
  depth: number;
  childCount: number;
  ancestorContinues: boolean[];
  isLastChild: boolean;
}

interface ContextXmlTreeItem {
  node: WorkbenchContextNodeRow;
  children: ContextXmlTreeItem[];
}

type ContextXmlLineKind = "open" | "close" | "summary" | "self" | "folded";

interface ContextXmlLine {
  key: string;
  kind: ContextXmlLineKind;
  node: WorkbenchContextNodeRow;
  depth: number;
  tag: string;
  attributes: Array<{ name: string; value: string }>;
  hasBody: boolean;
  displayFolded: boolean;
  summary: string | null;
}

interface NumberedContextXmlLine extends ContextXmlLine {
  lineNumber: number;
}

function flattenContextNodes(nodes: WorkbenchContextNode[]): WorkbenchContextNodeRow[] {
  return buildContextNodeRows(nodes);
}

function reflowContextNodeRows(rows: WorkbenchContextNodeRow[]): WorkbenchContextNodeRow[] {
  return buildContextNodeRows(rows);
}

function buildContextNodeRows(nodes: WorkbenchContextNode[]): WorkbenchContextNodeRow[] {
  const byParent = new Map<string | null, WorkbenchContextNode[]>();
  const knownIds = new Set(nodes.map((node) => node.id));
  for (const node of nodes) {
    const parentId = node.parent_id && knownIds.has(node.parent_id) ? node.parent_id : null;
    const siblings = byParent.get(parentId) ?? [];
    siblings.push(node);
    byParent.set(parentId, siblings);
  }
  for (const siblings of byParent.values()) {
    siblings.sort((left, right) => (
      left.display_order - right.display_order
      || left.title.localeCompare(right.title)
      || left.id.localeCompare(right.id)
    ));
  }
  const rows: WorkbenchContextNodeRow[] = [];
  const visited = new Set<string>();
  const visit = (parentId: string | null, depth: number, ancestorContinues: boolean[]) => {
    const siblings = byParent.get(parentId) ?? [];
    for (const [index, node] of siblings.entries()) {
      if (visited.has(node.id)) continue;
      visited.add(node.id);
      const childCount = byParent.get(node.id)?.length ?? 0;
      const continues = index < siblings.length - 1;
      rows.push({
        ...node,
        depth,
        childCount,
        ancestorContinues,
        isLastChild: !continues,
      });
      visit(node.id, depth + 1, [...ancestorContinues, continues]);
    }
  };
  visit(null, 0, []);
  return rows;
}

function filterContextNodeRows(rows: WorkbenchContextNodeRow[], filter: ContextMemoryLayerFilter) {
  if (filter === "all") return rows;
  const rowsById = new Map(rows.map((node) => [node.id, node]));
  const matchingMemoryIds = new Set(
    rows
      .filter((node) => contextMemoryLayer(node) === filter)
      .map((node) => node.id),
  );
  const included = new Set<string>(["memory.visible", ...matchingMemoryIds]);
  for (const nodeId of matchingMemoryIds) {
    let parentId = rowsById.get(nodeId)?.parent_id ?? null;
    while (parentId) {
      if (included.has(parentId)) break;
      included.add(parentId);
      parentId = rowsById.get(parentId)?.parent_id ?? null;
    }
  }
  return rows.filter((node) => included.has(node.id));
}

function buildContextXmlTree(rows: WorkbenchContextNodeRow[]): ContextXmlTreeItem[] {
  const items = new Map<string, ContextXmlTreeItem>();
  for (const row of rows) {
    items.set(row.id, { node: row, children: [] });
  }
  const roots: ContextXmlTreeItem[] = [];
  for (const row of rows) {
    const item = items.get(row.id);
    if (!item) continue;
    const parent = row.parent_id ? items.get(row.parent_id) : null;
    if (parent) {
      parent.children.push(item);
    } else {
      roots.push(item);
    }
  }
  return roots;
}

function buildContextXmlLines(
  items: ContextXmlTreeItem[],
  foldedIds: Set<string>,
  depth = 0,
): ContextXmlLine[] {
  const lines: ContextXmlLine[] = [];
  for (const item of items) {
    const node = item.node;
    const renderedChildren = node.state.collapsed ? [] : item.children;
    const tag = contextNodeXmlTag(node);
    const attributes = contextNodeXmlAttributes(node);
    const summary = node.summary?.trim() ? node.summary.trim() : null;
    const hasBody = Boolean(summary) || renderedChildren.length > 0;
    const displayFolded = hasBody && foldedIds.has(node.id);
    const base = { node, depth, tag, attributes, hasBody, displayFolded, summary };
    if (!hasBody) {
      lines.push({ ...base, key: `${node.id}:self`, kind: "self" });
      continue;
    }
    if (displayFolded) {
      lines.push({ ...base, key: `${node.id}:folded`, kind: "folded" });
      continue;
    }
    lines.push({ ...base, key: `${node.id}:open`, kind: "open" });
    if (summary) {
      lines.push({ ...base, key: `${node.id}:summary`, kind: "summary", depth: depth + 1 });
    }
    lines.push(...buildContextXmlLines(renderedChildren, foldedIds, depth + 1));
    lines.push({ ...base, key: `${node.id}:close`, kind: "close" });
  }
  return lines;
}

function contextMemoryLayer(node: WorkbenchContextNode): ContextMemoryLayerFilter | null {
  const value = node.metadata.governance_scope ?? node.metadata.layer_kind ?? node.owner_ref.layer_kind;
  if (
    value === "private"
    || value === "shared"
    || value === "project"
    || value === "team"
    || value === "system"
  ) {
    return value;
  }
  return null;
}

function contextMemoryAccessCode(node: WorkbenchContextNode) {
  if (contextMemoryLayer(node) === null) return null;
  const readable = node.metadata.readable === true || node.owner_ref.readable === true;
  const writable = node.metadata.writable === true || node.owner_ref.writable === true;
  if (readable && writable) return "read_write";
  if (readable) return "read_only";
  if (writable) return "write_only";
  return null;
}

function contextNodeTokenLabel(node: WorkbenchContextNode) {
  const tokens = node.estimate.text_tokens + node.estimate.tool_schema_tokens + node.estimate.file_tokens;
  return formatNumber(tokens);
}

function xmlText(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function xmlAttributeText(value: unknown) {
  return xmlText(value).replace(/"/g, "&quot;");
}

function contextNodeXmlState(node: WorkbenchContextNode) {
  if (node.state.opened) return "opened";
  return node.state.collapsed ? "collapsed" : "expanded";
}

function contextNodeXmlTag(node: WorkbenchContextNode) {
  const tag = (node.kind || node.owner || "node").replace(/[^A-Za-z0-9_.:-]/g, "_");
  return /^[A-Za-z_:]/.test(tag) ? tag : `node_${tag}`;
}

function contextNodeXmlAttributes(node: WorkbenchContextNodeRow) {
  const attrs = [
    { name: "id", value: node.id },
    { name: "label", value: node.title },
    { name: "owner", value: node.owner },
    { name: "state", value: contextNodeXmlState(node) },
  ];
  if (!node.state.prompt_visible) attrs.push({ name: "prompt_visible", value: "false" });
  if (node.state.pinned) attrs.push({ name: "pinned", value: "true" });
  if (node.state.schema_enabled) attrs.push({ name: "schema_enabled", value: "true" });
  const memoryAccess = contextMemoryAccessCode(node);
  if (memoryAccess) attrs.push({ name: "memory_access", value: memoryAccess });
  const actions = contextNodeXmlActions(node);
  if (actions) attrs.push({ name: "actions", value: actions });
  attrs.push({ name: "tokens", value: contextNodeTokenLabel(node) });
  return attrs;
}

function contextNodeXmlActions(node: WorkbenchContextNode) {
  return node.actions.join(" ");
}

function contextNodeActions(node: WorkbenchContextNode) {
  const actions: Array<{ id: string; label: string }> = [];
  if (node.actions.includes(node.state.pinned ? "unpin" : "pin")) {
    actions.push({
      id: node.state.pinned ? "unpin" : "pin",
      label: node.state.pinned ? t("workbench.context.action.unpin") : t("workbench.context.action.pin"),
    });
  }
  if (node.actions.includes(node.state.schema_enabled ? "disable_tool_schema" : "enable_tool_schema")) {
    actions.push({
      id: node.state.schema_enabled ? "disable_tool_schema" : "enable_tool_schema",
      label: node.state.schema_enabled ? t("workbench.context.action.disableSchema") : t("workbench.context.action.enableSchema"),
    });
  }
  return actions;
}

function contextNodeBusinessActions(node: WorkbenchContextNode) {
  const toggleAction = contextNodeToggleAction(node);
  return toggleAction ? [toggleAction, ...contextNodeActions(node)] : contextNodeActions(node);
}

function contextXmlLineActions(line: NumberedContextXmlLine) {
  return line.kind === "summary" || line.kind === "close" ? [] : contextNodeBusinessActions(line.node);
}

function contextXmlLineStyle(line: NumberedContextXmlLine) {
  return { "--xml-depth": String(line.depth) };
}

function contextXmlLineCanFold(line: NumberedContextXmlLine) {
  return line.hasBody && (line.kind === "open" || line.kind === "folded");
}

function contextXmlLineClasses(line: NumberedContextXmlLine) {
  return {
    "context-xml-line-row--hidden": !line.node.state.prompt_visible,
    "context-xml-line-row--summary": line.kind === "summary",
    "context-xml-line-row--close": line.kind === "close",
    "context-xml-line-row--folded": line.kind === "folded",
  };
}

function contextXmlBusinessActionBusyKey(node: WorkbenchContextNode, actionId: string) {
  return actionId === "expand" || actionId === "collapse"
    ? contextNodeToggleBusyKey(node)
    : contextActionBusyKey(node, actionId);
}

function toggleContextXmlDisplayFold(nodeId: string) {
  const next = new Set(contextXmlDisplayFoldedNodeIds.value);
  if (next.has(nodeId)) {
    next.delete(nodeId);
  } else {
    next.add(nodeId);
  }
  contextXmlDisplayFoldedNodeIds.value = next;
}

function runContextXmlBusinessAction(node: WorkbenchContextNode, actionId: string) {
  if (actionId === "expand" || actionId === "collapse") {
    void runContextNodeToggle(node);
    return;
  }
  void runContextNodeAction(node, actionId);
}

function contextNodeToggleAction(node: WorkbenchContextNode) {
  const action = node.state.collapsed ? "expand" : "collapse";
  if (!node.actions.includes(action)) return null;
  return {
    id: action,
    label: node.state.collapsed ? t("workbench.context.action.expand") : t("workbench.context.action.collapse"),
  };
}

function contextNodeToggleBusyKey(node: WorkbenchContextNode) {
  const action = contextNodeToggleAction(node);
  return action ? contextActionBusyKey(node, action.id) : "";
}

function runContextNodeToggle(node: WorkbenchContextNode) {
  const action = contextNodeToggleAction(node);
  if (!action) return;
  void runContextNodeAction(node, action.id);
}

function contextActionBusyKey(node: WorkbenchContextNode, action: string) {
  return `${node.id}:${action}`;
}

function estimatedCostLabel(value: number | null | undefined) {
  return typeof value === "number" ? `$${value.toFixed(3)}` : "-";
}

function inspectorSectionsFor(tab: Exclude<InspectorTabId, "step">): UiKeyValueSection[] {
  const inspector = runInspector.value;
  if (!inspector) return [];
  if (tab === "overview") return inspector.overview ?? [];
  if (tab === "debug") return inspector.debug ?? [];
  if (tab === "context") return [];
  if (tab === "memory") return inspector.memory ?? [];
  return inspector.agent ?? [];
}

function linkedEntityRoute(entity: UiLinkedEntity) {
  return entity.route ?? (entity.trace?.trace_id ? `/trace/${encodeURIComponent(entity.trace.trace_id)}` : null);
}

function linkedEntityLabel(entity: UiLinkedEntity) {
  const labelKey = linkedEntityLabelKey(entity.type);
  return entity.label ?? (labelKey ? t(labelKey) : entity.type);
}

function actionRoute(action: UiRuntimeAction) {
  return action.target?.route ?? null;
}

function actionHref(action: UiRuntimeAction) {
  if (!action.endpoint || action.method !== "GET") return null;
  return action.endpoint;
}

function actionLabel(action: UiRuntimeAction) {
  return action.label;
}

function canRunAction(action: UiRuntimeAction) {
  return action.allowed && commandBusy.value === null;
}

function handleQuickAction(action: UiRuntimeAction) {
  if (!action.allowed) return;
  if (action.id === "cancel_run") {
    void cancelActiveRun();
  }
}

function quickActionIcon(action: UiRuntimeAction): Component {
  if (action.id === "view_trace") return ShieldCheck;
  if (action.id === "open_operations") return PanelRightOpen;
  if (action.id === "cancel_run") return StopCircle;
  if (action.owner === "artifacts") return FileImage;
  if (action.owner === "access") return AlertTriangle;
  return ExternalLink;
}

function statusStripTone(status: string) {
  if (status === "failed") {
    return "status-strip--danger";
  }
  if (status === "waiting" || status === "queued") {
    return "status-strip--warning";
  }
  if (status === "completed" || status === "success") {
    return "status-strip--success";
  }
  return "status-strip--running";
}

function isPendingStatus(status: string) {
  return status === "running" || status === "waiting" || status === "queued";
}

function isLiveFinalStep(step: TurnStepView) {
  return step.type === "final_response" && step.status === "running";
}

function approvalRequestId(step: TurnStepView) {
  return step.trace.approval_request_id ?? null;
}

function canResolveApproval(step: TurnStepView) {
  return step.type === "approval_required" && step.status === "waiting" && approvalRequestId(step) !== null;
}

function isApprovalBusy(step: TurnStepView, decision?: ApprovalDecision) {
  if (approvalBusyStepId.value !== step.step_id) return false;
  return decision === undefined || approvalBusyDecision.value === decision;
}

function isSkillDraftApproval(step: TurnStepView) {
  return step.approval?.tool_name === "skill_draft_apply" && skillApprovalDraftId(step) !== null;
}

function skillApprovalTarget(step: TurnStepView) {
  const draft = skillApprovalDraftState(step)?.draft;
  const target = normalizeText(draft?.target_source_id) ?? normalizeText(draft?.target_scope);
  return target ?? "-";
}

function skillApprovalValidation(step: TurnStepView) {
  const state = skillApprovalDraftState(step);
  const draft = state?.draft;
  if (state?.loading) return t("workbench.approval.skill.loadingDraft");
  if (state?.error) return state.error;
  if (!draft?.validation) return t("workbench.approval.skill.validationNotRun");
  if (draft.validation.errors.length) {
    return t("workbench.approval.skill.validationErrors", { count: String(draft.validation.errors.length) });
  }
  if (draft.validation.warnings.length) {
    return t("workbench.approval.skill.validationWarnings", { count: String(draft.validation.warnings.length) });
  }
  return t("workbench.approval.skill.validationClean");
}

function skillApprovalReadiness(step: TurnStepView) {
  const validation = skillApprovalDraftState(step)?.draft?.validation;
  if (!validation) return "-";
  return titleize(validation.readiness_status, "-");
}

function skillApprovalMissing(step: TurnStepView) {
  const validation = skillApprovalDraftState(step)?.draft?.validation;
  if (!validation) return "-";
  const items = [
    ...validation.missing_tools,
    ...validation.missing_access,
    ...validation.missing_effects,
    ...validation.unsupported_surfaces,
    ...validation.unsupported_platforms,
  ];
  return items.length ? items.join(", ") : t("workbench.approval.skill.none");
}

function skillApprovalDiffSummary(step: TurnStepView) {
  const draft = skillApprovalDraftState(step)?.draft;
  const diff = draft?.diff;
  if (!diff) return t("workbench.approval.skill.diffNotBuilt");
  const summary = textValue(diff.summary, "");
  if (summary) return summary;
  if (diff.file_diffs.length) {
    return t("workbench.approval.skill.fileDiffs", { count: String(diff.file_diffs.length) });
  }
  return t("workbench.approval.skill.diffReady");
}

function skillApprovalRiskItems(step: TurnStepView) {
  const draft = skillApprovalDraftState(step)?.draft;
  if (!draft) return [t("workbench.approval.skill.riskOwnerWrite")];
  const items = [t("workbench.approval.skill.riskOwnerWrite")];
  if (!draft.diff) items.push(t("workbench.approval.skill.riskMissingDiff"));
  if (!draft.validation) items.push(t("workbench.approval.skill.riskMissingValidation"));
  if (draft.validation?.errors.length) items.push(t("workbench.approval.skill.riskValidationErrors"));
  if (draft.target_source_id === "system") items.push(t("workbench.approval.skill.riskReadonlySource"));
  return items;
}

function skillApprovalDraftTitle(step: TurnStepView) {
  const draft = skillApprovalDraftState(step)?.draft;
  return draft?.skill_name ?? skillApprovalDraftId(step) ?? "-";
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

function titleize(value: unknown, fallback = "-"): string {
  const text = textValue(value, fallback);
  if (text === "-") return text;
  return text
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isWaitingStatus(status: string) {
  return status === "waiting" || status === "queued";
}

function filterLabel(id: string, fallback: string) {
  if (id === "all") return t("common.all");
  if (id === "running") return t("status.running");
  if (id === "completed") return t("status.completed");
  if (id === "failed") return t("status.failed");
  return fallback;
}

function threadMatchesFilter(thread: WorkbenchThreadSummary, filterId: string) {
  if (filterId === "all") return true;
  if (filterId === "running") return ["accepted", "queued", "running", "waiting"].includes(thread.status);
  if (filterId === "completed") return ["completed", "success"].includes(thread.status);
  if (filterId === "failed") return ["failed", "cancelled"].includes(thread.status);
  return true;
}

function selectThread(thread: WorkbenchThreadSummary) {
  composerMode.value = "continue";
  draftSessionKey.value = null;
  pendingRunId.value = null;
  pendingSessionKey.value = null;
  commandError.value = null;
  activeThreadId.value = thread.id;
  if (thread.run_id) {
    void router.push(`/workbench/runs/${encodeURIComponent(thread.run_id)}`);
    return;
  }
  void router.push(`/workbench/threads/${encodeURIComponent(thread.session_key)}`);
}

function scrollActiveTurnTab() {
  const container = turnsRow.value;
  const turnId = activeTurnId.value;
  if (!container || !turnId) return;
  const activeButton = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
    (button) => button.dataset.turnId === turnId,
  );
  activeButton?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function queueLiveFinalScroll() {
  if (!activeLiveStream.value) return;
  if (liveScrollFrame !== null) {
    window.cancelAnimationFrame(liveScrollFrame);
  }
  liveScrollFrame = window.requestAnimationFrame(() => {
    liveScrollFrame = null;
    void nextTick(scrollLiveFinalIntoView);
  });
}

function scrollLiveFinalIntoView() {
  const container = stepList.value;
  if (!container || !activeLiveStream.value) return;
  const liveRow = container.querySelector<HTMLElement>(".step-row--live-final");
  if (!liveRow) return;

  const bottomPadding = 12;
  const rowTop = liveRow.offsetTop;
  const rowBottom = liveRow.offsetTop + liveRow.offsetHeight;
  const visibleTop = container.scrollTop;
  const visibleBottom = container.scrollTop + container.clientHeight;
  if (rowTop >= visibleTop && rowBottom <= visibleBottom - bottomPadding) return;

  container.scrollTo({
    top: Math.max(0, rowBottom - container.clientHeight + bottomPadding),
    behavior: "smooth",
  });
}

function handleTurnsWheel(event: WheelEvent) {
  const container = turnsRow.value;
  if (!container || container.scrollWidth <= container.clientWidth) return;
  const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
  if (delta === 0) return;
  const maxScrollLeft = container.scrollWidth - container.clientWidth;
  const nextScrollLeft = Math.max(0, Math.min(maxScrollLeft, container.scrollLeft + delta));
  if (nextScrollLeft === container.scrollLeft) return;
  event.preventDefault();
  container.scrollLeft = nextScrollLeft;
}
</script>

<template>
  <div v-if="run" class="workbench-page page-grid">
    <aside class="threads-panel">
      <div class="panel-header">
        <h1>{{ t("workbench.threads") }}</h1>
        <UiButton
          :variant="composerMode === 'new' ? 'secondary' : 'primary'"
          size="sm"
          @click="startNewTask"
        >
          <MessageSquarePlus :size="16" />
          {{ t("workbench.newTask") }}
        </UiButton>
      </div>

      <div class="thread-filters" :aria-label="t('workbench.threadFilters')">
        <button
          v-for="filter in threadFilters"
          :key="filter.id"
          type="button"
          :class="{ active: filter.id === activeThreadFilterId }"
          :aria-pressed="filter.id === activeThreadFilterId"
          @click="activeThreadFilterId = filter.id"
        >
          {{ filterLabel(filter.id, filter.label) }}
          <strong>{{ filter.count }}</strong>
        </button>
      </div>

      <div class="threads-list scroll-area">
        <button
          v-if="isNewSessionDraft"
          class="thread-card thread-card--active thread-card--draft"
          type="button"
        >
          <span class="thread-card__status">
            <StatusDot tone="info" animated />
            {{ t("workbench.newSessionDraft") }}
          </span>
          <span class="thread-card__adornment">
            <MessageSquarePlus class="motion-breathe" :size="16" />
          </span>
          <strong>{{ t("workbench.newSessionTitle") }}</strong>
          <span class="thread-card__agent">{{ run.agent.name }}</span>
          <small>
            <span class="thread-card__activity">
              <MessageSquarePlus :size="13" />
              <span>{{ draftSessionKey }}</span>
            </span>
          </small>
        </button>

        <button
          v-for="thread in filteredWorkbenchThreads"
          :key="thread.id"
          class="thread-card"
          :class="[
            { 'thread-card--active': thread.id === activeThreadId },
            `thread-card--${thread.status}`,
          ]"
          type="button"
          @click="selectThread(thread)"
        >
          <span class="thread-card__status">
            <StatusDot :tone="toneForStatus(thread.status)" :animated="isPendingStatus(thread.status)" />
            {{ t(`status.${thread.status}`) }}
          </span>
          <span class="thread-card__adornment">
            <Loader2 v-if="threadAdornment(thread) === 'spinner'" class="motion-spin" :size="16" />
            <span v-else-if="threadAdornment(thread) === 'waiting'" class="thread-card__waiting motion-breathe" />
            <CheckCircle2 v-else-if="threadAdornment(thread) === 'check'" :size="16" />
            <AlertTriangle v-else-if="threadAdornment(thread) === 'alert'" :size="16" />
            <Sparkles v-else-if="threadAdornment(thread) === 'star'" class="motion-breathe" :size="16" />
          </span>
          <strong>{{ threadTitle(thread) }}</strong>
          <span class="thread-card__agent">{{ thread.agent }}</span>
          <small>
            <span class="thread-card__activity">
              <Wand2 v-if="thread.status === 'running'" :size="13" />
              <ShieldCheck v-else-if="thread.status === 'waiting'" :size="13" />
              <CheckCircle2 v-else-if="thread.status === 'completed'" :size="13" />
              <XCircle v-else-if="thread.status === 'failed'" :size="13" />
              <span>{{ threadLastAction(thread) }}</span>
            </span>
            <span class="thread-card__time">{{ relativeThreadTime(thread.updated_at) }}</span>
          </small>
        </button>

        <div v-if="!isNewSessionDraft && !filteredWorkbenchThreads.length" class="thread-filter-empty">
          <ShieldCheck :size="16" />
          <span>{{ t("workbench.threadFilterEmpty") }}</span>
        </div>
      </div>

      <div class="threads-footer">
        <button type="button">
          <AlertTriangle :size="15" />
          {{ t("common.helpDocs") }}
        </button>
      </div>
    </aside>

    <section class="workbench-main scroll-area">
      <div class="connection-stack">
        <div class="connection-strip">
          <span>
            <StatusDot :tone="loadError ? 'danger' : toneForStatus(connection?.status ?? 'success')" />
            {{ connectionStripText }}
          </span>
          <span>{{ t("common.updatedAt") }} {{ formatLocalTime(connection?.updated_at ?? run.started_at) }} <ChevronDown :size="13" /></span>
        </div>
      </div>

      <UiCard class="run-card">
        <div class="run-card__media">
          <img :src="runCoverPreviewUrl" alt="" />
        </div>
        <div class="run-card__body">
          <div class="run-card__title">
            <h2>{{ isNewSessionDraft ? t("workbench.newSessionTitle") : activeThread ? threadTitle(activeThread) : runTitle(run) }}</h2>
            <UiBadge :tone="isNewSessionDraft ? 'info' : toneForStatus(run.status)">
              {{ isNewSessionDraft ? t("workbench.newSessionDraft") : t(`status.${run.status}`) }}
              <Loader2 v-if="!isNewSessionDraft && run.status === 'running'" class="motion-spin" :size="12" />
            </UiBadge>
          </div>
          <dl class="run-facts">
            <div>
              <dt>{{ t("common.startedAt") }}</dt>
              <dd>{{ isNewSessionDraft ? "-" : formatLocalTime(run.started_at) }}</dd>
            </div>
            <div>
              <dt>{{ t("common.duration") }}</dt>
              <dd>{{ isNewSessionDraft ? "-" : formatDuration(run.duration_ms) }}</dd>
            </div>
            <div>
              <dt>{{ t("common.toolCalls") }}</dt>
              <dd>{{ isNewSessionDraft ? `0 ${t("common.times")}` : `${run.metrics.tool_calls} ${t("common.times")}` }}</dd>
            </div>
            <div>
              <dt>{{ t("common.agent") }}</dt>
              <dd>{{ run.agent.name }}</dd>
            </div>
            <div>
              <dt>{{ t("common.model") }}</dt>
              <dd>{{ run.model.name }}</dd>
            </div>
          </dl>
        </div>
        <UiButton
          v-if="isNewSessionDraft"
          variant="secondary"
          size="sm"
          @click="discardDraftSession"
        >
          <XCircle :size="16" />
          {{ t("workbench.discardDraft") }}
        </UiButton>
        <UiButton
          v-else
          variant="danger"
          size="sm"
          :disabled="!canCancelRun || commandBusy === 'cancel'"
          @click="cancelActiveRun"
        >
          <Loader2 v-if="commandBusy === 'cancel'" class="motion-spin" :size="16" />
          <StopCircle v-else :size="16" />
          {{ commandBusy === "cancel" ? t("workbench.stoppingRun") : t("workbench.stopRun") }}
        </UiButton>
        <button class="icon-only" type="button" :title="t('common.more')">
          <MoreVertical :size="18" />
        </button>
      </UiCard>

      <div class="timeline-slot">
        <UiCard class="turns-card">
          <div v-if="isNewSessionDraft" class="draft-session-strip">
            <MessageSquarePlus :size="16" />
            <strong>{{ t("workbench.newSessionDraft") }}</strong>
            <span>{{ draftSessionKey }}</span>
          </div>
          <div v-else ref="turnsRow" class="turns-row" @wheel="handleTurnsWheel">
            <strong>{{ t("workbench.turns") }}</strong>
            <button
              v-for="turn in displayedTurns"
              :key="turn.turn_id"
              :data-turn-id="turn.turn_id"
              type="button"
              :class="{ active: turn.turn_id === activeTurnId }"
              @click="activeTurnId = turn.turn_id"
            >
              {{ t("workbench.turnLabel", { ordinal: turn.ordinal }) }}
              <small>{{ t(`status.${turn.status}`) }} · {{ formatDuration(turn.duration_ms) }}</small>
            </button>
          </div>

          <div class="view-tabs">
            <button class="active" type="button">
              <Boxes :size="15" />
              {{ t("workbench.steps") }}
            </button>
            <button type="button">
              <Clock3 :size="15" />
              {{ t("workbench.timeline") }}
            </button>
          </div>

          <div ref="stepList" class="step-list">
            <div v-if="isNewSessionDraft" class="draft-session-empty">
              <MessageSquarePlus :size="24" />
              <strong>{{ t("workbench.newSessionEmptyTitle") }}</strong>
              <p>{{ t("workbench.newSessionEmptyBody") }}</p>
            </div>
            <div v-else class="step-stack">
              <article
                v-for="step in activeTimelineSteps"
                :key="step.step_id"
                class="step-row"
                :class="[
                  `step-row--${stepVisualTone(step)}`,
                  { 'step-row--pending': isPendingStatus(step.status) },
                  { 'step-row--live-final': isLiveFinalStep(step) },
                  { 'step-row--selected': selectedStep?.step_id === step.step_id },
                ]"
                role="button"
                tabindex="0"
                :aria-selected="selectedStep?.step_id === step.step_id"
                @click="selectStepForInspector(step)"
                @keydown.enter.prevent="selectStepForInspector(step)"
                @keydown.space.prevent="selectStepForInspector(step)"
              >
                <time>{{ stepTime(step.started_at) }}</time>
                <div class="step-row__line">
                  <span class="step-row__dot" />
                </div>
                <div class="step-row__content">
                  <span class="step-icon">
                    <component :is="iconForStep(step.type)" :size="20" />
                  </span>
                  <div class="step-row__body">
                    <header>
                      <h3>{{ stepTitle(step) }}</h3>
                      <UiBadge
                        v-for="badge in step.badges"
                        :key="badge.label"
                        :tone="badge.tone"
                      >
                        {{ badgeLabel(badge.label) }}
                      </UiBadge>
                    </header>
                    <MarkdownView v-if="step.markdown" :source="step.markdown" />
                    <p v-else-if="stepSummary(step)">{{ stepSummary(step) }}</p>
                    <div v-if="isSkillDraftApproval(step)" class="skill-approval-card">
                      <header>
                        <span>{{ t("workbench.approval.skill.title") }}</span>
                        <strong>{{ skillApprovalDraftTitle(step) }}</strong>
                      </header>
                      <dl>
                        <div>
                          <dt>{{ t("workbench.approval.skill.draftId") }}</dt>
                          <dd>{{ skillApprovalDraftId(step) }}</dd>
                        </div>
                        <div>
                          <dt>{{ t("workbench.approval.skill.target") }}</dt>
                          <dd>{{ skillApprovalTarget(step) }}</dd>
                        </div>
                        <div>
                          <dt>{{ t("workbench.approval.skill.validation") }}</dt>
                          <dd>{{ skillApprovalValidation(step) }}</dd>
                        </div>
                        <div>
                          <dt>{{ t("workbench.approval.skill.readiness") }}</dt>
                          <dd>{{ skillApprovalReadiness(step) }}</dd>
                        </div>
                        <div>
                          <dt>{{ t("workbench.approval.skill.missing") }}</dt>
                          <dd>{{ skillApprovalMissing(step) }}</dd>
                        </div>
                        <div>
                          <dt>{{ t("workbench.approval.skill.diff") }}</dt>
                          <dd>{{ skillApprovalDiffSummary(step) }}</dd>
                        </div>
                      </dl>
                      <div class="skill-approval-risk">
                        <span>{{ t("workbench.approval.skill.risk") }}</span>
                        <ul>
                          <li v-for="item in skillApprovalRiskItems(step)" :key="item">{{ item }}</li>
                        </ul>
                      </div>
                    </div>
                    <span v-if="isLiveFinalStep(step)" class="live-stream-cursor" aria-hidden="true" />
                    <template v-if="canResolveApproval(step)">
                      <div class="approval-actions">
                        <UiButton
                          class="approval-action-button"
                          size="sm"
                          variant="primary"
                          :disabled="approvalBusyStepId !== null"
                          @click="resolveApprovalStep(step, 'allow_once')"
                        >
                          <Loader2 v-if="isApprovalBusy(step, 'allow_once')" class="motion-spin" :size="14" />
                          <CheckCircle2 v-else :size="14" />
                          {{ t("workbench.approval.allowOnce") }}
                        </UiButton>
                        <UiButton
                          class="approval-action-button"
                          size="sm"
                          variant="secondary"
                          :disabled="approvalBusyStepId !== null"
                          @click="resolveApprovalStep(step, 'allow_for_session')"
                        >
                          <Loader2 v-if="isApprovalBusy(step, 'allow_for_session')" class="motion-spin" :size="14" />
                          <ShieldCheck v-else :size="14" />
                          {{ t("workbench.approval.allowSession") }}
                        </UiButton>
                        <UiButton
                          class="approval-action-button"
                          size="sm"
                          variant="secondary"
                          :disabled="approvalBusyStepId !== null"
                          @click="resolveApprovalStep(step, 'always_for_agent')"
                        >
                          <Loader2 v-if="isApprovalBusy(step, 'always_for_agent')" class="motion-spin" :size="14" />
                          <Sparkles v-else :size="14" />
                          {{ t("workbench.approval.allowAgent") }}
                        </UiButton>
                        <UiButton
                          class="approval-action-button"
                          size="sm"
                          variant="danger"
                          :disabled="approvalBusyStepId !== null"
                          @click="resolveApprovalStep(step, 'deny')"
                        >
                          <Loader2 v-if="isApprovalBusy(step, 'deny')" class="motion-spin" :size="14" />
                          <XCircle v-else :size="14" />
                          {{ t("workbench.approval.deny") }}
                        </UiButton>
                      </div>
                      <small v-if="approvalErrorStepId === step.step_id && approvalError" class="approval-error">
                        {{ approvalError }}
                      </small>
                    </template>
                    <div v-if="step.artifacts.length" class="artifact-strip">
                      <div v-for="artifact in step.artifacts" :key="artifact.artifact_id" class="artifact-thumb">
                        <img :src="artifactPreviewUrl(artifact)" :alt="artifact.name" />
                      </div>
                      <dl class="artifact-meta">
                        <div>
                          <dt>{{ t("common.fileName") }}</dt>
                          <dd>{{ step.artifacts[0].name }}</dd>
                        </div>
                        <div>
                          <dt>{{ t("common.resolution") }}</dt>
                          <dd>{{ artifactResolution(step.artifacts[0]) }}</dd>
                        </div>
                        <div>
                          <dt>{{ t("common.size") }}</dt>
                          <dd>{{ formatBytes(step.artifacts[0].size_bytes ?? 0) }}</dd>
                        </div>
                      </dl>
                    </div>
                    <div v-if="isStepExpanded(step.step_id)" class="step-details-panel">
                      <dl>
                        <div v-for="row in stepDetailRows(step)" :key="`${step.step_id}:${row.label}`">
                          <dt>{{ row.label }}</dt>
                          <dd>{{ row.value }}</dd>
                        </div>
                      </dl>
                      <RouterLink :to="`/trace/${step.trace.trace_id}`">
                        <PanelRightOpen :size="14" />
                        {{ t("common.viewTrace") }}
                      </RouterLink>
                    </div>
                  </div>
                  <div class="step-row__actions">
                    <span :class="`step-row__status step-row__status--${toneForStatus(step.status)}`">
                      <Loader2 v-if="step.status === 'running'" class="motion-spin" :size="16" />
                      <CheckCircle2 v-else-if="step.status === 'success'" :size="16" />
                      <AlertTriangle v-else-if="step.status === 'waiting'" class="motion-breathe" :size="16" />
                      <span v-if="step.status !== 'success'">{{ t(`status.${step.status}`) }}</span>
                    </span>
                    <template v-if="step.artifacts.length">
                      <a
                        class="step-action-button"
                        :href="step.artifacts[0].preview_url ?? step.artifacts[0].download_url ?? '#'"
                        target="_blank"
                        rel="noreferrer"
                      >
                        <PanelRightOpen :size="14" />
                        {{ t("common.viewImage") }}
                      </a>
                      <RouterLink class="step-action-button" :to="`/trace/${step.trace.trace_id}`">
                        <Loader2 :size="14" />
                        {{ t("common.viewTrace") }}
                      </RouterLink>
                    </template>
                    <RouterLink
                      v-else-if="step.type === 'final_response'"
                      class="step-action-button"
                      :to="`/trace/${step.trace.trace_id}`"
                    >
                      {{ t("common.viewDetails") }}
                    </RouterLink>
                    <button
                      v-if="step.details_available"
                      class="step-action-button"
                      type="button"
                      :aria-expanded="isStepExpanded(step.step_id)"
                      @click="toggleStepDetails(step.step_id)"
                    >
                      {{ isStepExpanded(step.step_id) ? t("common.collapseDetails") : t("common.expandDetails") }}
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </UiCard>
      </div>

      <div class="status-strip" :class="isNewSessionDraft ? 'status-strip--warning' : statusStripTone(run.status)">
        <div class="status-strip__main">
          <MessageSquarePlus v-if="isNewSessionDraft" class="motion-breathe" :size="20" />
          <Loader2 v-else-if="run.status === 'running'" class="motion-spin" :size="20" />
          <AlertTriangle v-else-if="isWaitingStatus(run.status)" class="motion-breathe" :size="20" />
          <CheckCircle2 v-else-if="run.status === 'completed' || run.status === 'success'" :size="20" />
          <XCircle v-else-if="run.status === 'failed'" :size="20" />
          <Loader2 v-else class="motion-spin" :size="20" />
          <strong>{{ isNewSessionDraft ? t("workbench.newSessionDraft") : statusStripLabel(run.status_strip?.label) ?? (loadingRun ? t("common.loading") : t("workbench.readyFallback")) }}</strong>
          <span>· {{ isNewSessionDraft ? t("workbench.newSessionStatus") : t("workbench.statusRunning", { duration: formatDuration(run.duration_ms) }) }}</span>
        </div>
        <div class="status-strip__meta">
          <span v-if="isNewSessionDraft">{{ draftSessionKey }}</span>
          <template v-else>
            <span v-if="showRunEta">{{ t("workbench.eta", { duration: formatDuration(run.status_strip?.eta_ms) }) }}</span>
            <span>{{ t("workbench.queueWait", { duration: formatDuration(run.status_strip?.queue_wait_ms) }) }}</span>
          </template>
        </div>
        <RouterLink v-if="!isNewSessionDraft" class="status-strip__action" :to="`/trace/${run.trace.trace_id}`">
          <PanelRightOpen :size="15" />
          {{ t("common.viewTrace") }}
        </RouterLink>
      </div>

      <form class="composer" @submit.prevent="submitComposer">
        <div class="composer__input">
          <input
            ref="attachmentInput"
            class="composer__file-input"
            type="file"
            multiple
            @change="handleAttachmentInput"
          />
          <input
            ref="composerInput"
            v-model="composerContent"
            :placeholder="composerPlaceholder"
            :disabled="commandBusy === 'send'"
          />
          <span v-if="composerMode === 'new'" class="composer__mode">{{ t("workbench.newTaskMode") }}</span>
          <span v-if="commandError" class="composer__error">{{ commandError }}</span>
          <span v-if="attachmentError" class="composer__error">{{ attachmentError }}</span>
          <div v-if="attachedArtifacts.length" class="composer-attachments">
            <button
              v-for="artifact in attachedArtifacts"
              :key="artifact.id"
              type="button"
              class="composer-attachment"
              :title="artifact.name ?? artifact.id"
              @click="removeAttachment(artifact.id)"
            >
              <FileImage :size="14" />
              <span>{{ artifact.name ?? artifact.id }}</span>
              <XCircle :size="13" />
            </button>
          </div>
          <div class="composer-bottom-row">
            <button type="button" :title="t('common.attach')" :disabled="commandBusy === 'send' || attachmentBusy" @click="openAttachmentPicker">
              <Loader2 v-if="attachmentBusy" class="motion-spin" :size="16" />
              <ExternalLink v-else :size="16" />
            </button>
            <div class="composer-tool-anchor">
              <button
                type="button"
                class="tool-menu"
                :disabled="commandBusy === 'send'"
                :aria-expanded="toolsOpen"
                @click="toggleToolsMenu"
              >
                <Grid2X2 :size="16" />
                {{ t("common.tools") }}
                <ChevronDown :size="13" />
              </button>
              <div v-if="toolsOpen" class="composer-tool-menu">
                <div class="composer-tool-menu__header">
                  <strong>{{ t("workbench.tools.available") }}</strong>
                  <button type="button" :aria-label="t('common.more')" @click="toolsOpen = false">
                    <XCircle :size="14" />
                  </button>
                </div>
                <div v-if="toolsLoading" class="composer-tool-menu__state">
                  <Loader2 class="motion-spin" :size="16" />
                  {{ t("common.loading") }}
                </div>
                <div v-else-if="toolsError" class="composer-tool-menu__state composer-tool-menu__state--danger">
                  {{ toolsError }}
                </div>
                <div v-else-if="!workbenchTools.length" class="composer-tool-menu__state">
                  {{ t("workbench.tools.empty") }}
                </div>
                <template v-else>
                  <button
                    v-for="tool in workbenchTools"
                    :key="tool.id"
                    type="button"
                    class="composer-tool-item"
                    @click="insertToolPrompt(tool)"
                  >
                    <Wrench :size="15" />
                    <span>
                      <strong>{{ tool.name || tool.id }}</strong>
                      <small>{{ tool.id }} · {{ tool.kind }}</small>
                    </span>
                    <UiBadge v-if="tool.execution_policy.requires_confirmation" tone="warning">
                      {{ t("workbench.tools.requiresApproval") }}
                    </UiBadge>
                  </button>
                </template>
              </div>
            </div>
            <div class="composer-runtime-row">
              <label>
                <Bot :size="14" />
                <span>{{ t("common.agent") }}</span>
                <select
                  :value="selectedAgentId ?? ''"
                  :disabled="agentsLoading || commandBusy === 'send'"
                  @change="handleAgentSelection"
                >
                  <option v-if="!enabledAgents.length" value="">{{ agentsLoading ? t("common.loading") : t("workbench.runtime.noAgents") }}</option>
                  <option v-for="agent in enabledAgents" :key="agent.id" :value="agent.id">
                    {{ agent.name || agent.id }}
                  </option>
                </select>
              </label>
              <label>
                <Brain :size="14" />
                <span>{{ t("common.model") }}</span>
                <select
                  :value="selectedModelId ?? ''"
                  :disabled="modelsLoading || commandBusy === 'send'"
                  @change="handleModelSelection"
                >
                  <option v-if="!enabledModels.length" value="">{{ modelsLoading ? t("common.loading") : t("workbench.runtime.noModels") }}</option>
                  <option v-if="selectedAgentDefaultModelId" :value="selectedAgentDefaultModelId">
                    {{ t("workbench.runtime.agentDefault", { model: selectedAgentDefaultModelId }) }}
                  </option>
                  <option v-for="model in selectableModels" :key="model.id" :value="model.id">
                    {{ model.id }}
                  </option>
                </select>
              </label>
              <small v-if="runtimeOptionsError">{{ runtimeOptionsError }}</small>
            </div>
          </div>
        </div>
        <div class="composer__actions">
          <UiButton variant="primary" type="submit" :disabled="!canSubmitComposer">
            <Loader2 v-if="commandBusy === 'send'" class="motion-spin" :size="16" />
            <Send v-else :size="16" />
            {{ commandBusy === "send" ? t("workbench.sending") : t("workbench.send") }}
          </UiButton>
        </div>
      </form>
    </section>

    <aside class="inspector-panel scroll-area">
      <div class="inspector-tabs">
        <button
          v-for="tab in inspectorTabs"
          :key="tab.id"
          type="button"
          :class="{ active: activeInspectorTab === tab.id }"
          :aria-selected="activeInspectorTab === tab.id"
          @click="activeInspectorTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <template v-if="activeInspectorTab === 'overview'">
        <UiCard
          v-for="section in inspectorSectionsFor('overview')"
          :key="section.id"
          class="inspector-section"
        >
          <h2>{{ section.title }}</h2>
          <dl>
            <div v-for="item in section.items" :key="`${section.id}:${item.label}`">
              <dt>{{ item.label }}</dt>
              <dd>
                <RouterLink v-if="item.route" :to="item.route" :title="item.value">
                  {{ compactInspectorValue(item.value) }}
                </RouterLink>
                <span v-else :title="item.value">{{ compactInspectorValue(item.value) }}</span>
              </dd>
            </div>
          </dl>
        </UiCard>

        <UiCard v-if="!inspectorSectionsFor('overview').length" class="inspector-section">
          <h2>{{ t("workbench.overview") }}</h2>
          <dl>
            <div>
              <dt>{{ t("common.status") }}</dt>
              <dd>
                <UiBadge :tone="isNewSessionDraft ? 'info' : toneForStatus(run.status)">
                  {{ isNewSessionDraft ? t("workbench.newSessionDraft") : t(`status.${run.status}`) }}
                </UiBadge>
              </dd>
            </div>
            <div>
              <dt>{{ t("common.duration") }}</dt>
              <dd>{{ isNewSessionDraft ? "-" : formatDuration(run.duration_ms) }}</dd>
            </div>
            <div>
              <dt>{{ t("common.startedAt") }}</dt>
              <dd>{{ isNewSessionDraft ? "-" : formatLocalTime(run.started_at) }}</dd>
            </div>
            <div>
              <dt>{{ t("common.toolCalls") }}</dt>
              <dd>{{ isNewSessionDraft ? `0 ${t("common.times")}` : `${run.metrics.tool_calls} ${t("common.times")} · ${t("status.failed")} ${stepStats.failed}` }}</dd>
            </div>
            <div>
              <dt>{{ t("common.llmCalls") }}</dt>
              <dd>{{ isNewSessionDraft ? `0 ${t("common.times")}` : `${run.metrics.llm_calls} ${t("common.times")}` }}</dd>
            </div>
            <div>
              <dt>{{ t("common.tokens") }}</dt>
              <dd>{{ isNewSessionDraft ? "0" : formatNumber(run.metrics.tokens) }}</dd>
            </div>
            <div>
              <dt>{{ t("common.estimatedCost") }}</dt>
              <dd>{{ isNewSessionDraft ? "-" : estimatedCostLabel(run.metrics.estimated_cost_usd) }}</dd>
            </div>
          </dl>
        </UiCard>

        <UiCard class="inspector-section">
          <h2>{{ t("workbench.currentTurn") }}</h2>
          <p>
            {{ currentTurnSummary ?? t("workbench.currentTurnBody", { tool: currentTurnToolName }) }}
          </p>
        </UiCard>

        <UiCard class="inspector-section">
          <h2>{{ t("workbench.linkedAssets") }}</h2>
          <RouterLink
            v-for="asset in linkedAssets"
            :key="asset.key"
            class="asset-link"
            :to="asset.route"
          >
            <component :is="asset.icon" :size="16" />
            <strong>{{ asset.labelKey ? t(asset.labelKey) : asset.label }}</strong>
            <span :title="asset.id">{{ compactIdentifier(asset.id) }}</span>
            <ChevronRight :size="14" />
          </RouterLink>
          <p v-if="!linkedAssets.length" class="asset-empty">{{ t("workbench.asset.empty") }}</p>
        </UiCard>

        <UiCard class="inspector-section quick-actions">
          <h2>{{ t("workbench.quickActions") }}</h2>
          <template v-if="backendQuickActions.length">
            <RouterLink
              v-for="action in backendQuickActions.filter((item) => actionRoute(item))"
              :key="action.id"
              :to="actionRoute(action) ?? '/'"
            >
              <component :is="quickActionIcon(action)" :size="17" />
              <span>
                <strong>{{ actionLabel(action) }}</strong>
                <small :title="action.owner">{{ action.owner }}</small>
              </span>
              <ExternalLink :size="14" />
            </RouterLink>
            <button
              v-for="action in backendQuickActions.filter((item) => !actionRoute(item))"
              :key="action.id"
              type="button"
              :disabled="!canRunAction(action)"
              @click="handleQuickAction(action)"
            >
              <component :is="quickActionIcon(action)" :size="17" />
              <span>
                <strong>{{ actionLabel(action) }}</strong>
                <small :title="action.disabled_reason ?? action.owner">{{ action.disabled_reason ?? action.owner }}</small>
              </span>
              <ExternalLink :size="14" />
            </button>
          </template>
          <RouterLink v-else-if="!isNewSessionDraft" :to="`/trace/${run.trace.trace_id}`">
            <ShieldCheck :size="17" />
            <span>
              <strong>{{ t("workbench.quick.viewTrace") }}</strong>
              <small>{{ t("workbench.quick.traceHelp") }}</small>
            </span>
            <ExternalLink :size="14" />
          </RouterLink>
          <RouterLink v-if="!backendQuickActions.length" to="/operations/orchestration">
            <PanelRightOpen :size="17" />
            <span>
              <strong>{{ t("workbench.quick.viewOperations") }}</strong>
              <small>{{ t("workbench.quick.operationsHelp") }}</small>
            </span>
            <ExternalLink :size="14" />
          </RouterLink>
          <button
            v-if="!backendQuickActions.length"
            type="button"
            :disabled="isNewSessionDraft"
            @click="exportActiveRun"
          >
            <Download :size="17" />
            <span>
              <strong>{{ t("workbench.quick.exportRun") }}</strong>
              <small>{{ t("workbench.quick.exportHelp") }}</small>
            </span>
            <ExternalLink :size="14" />
          </button>
        </UiCard>
      </template>

      <template v-else-if="activeInspectorTab === 'step'">
        <UiCard v-if="selectedStep" class="inspector-section step-inspector-card">
          <h2>{{ t("workbench.stepInspector") }}</h2>
          <div class="step-inspector-card__heading">
            <component :is="iconForStep(selectedStep.type)" :size="18" />
            <strong>{{ stepTitle(selectedStep) }}</strong>
            <UiBadge :tone="toneForStatus(selectedStep.status)">
              {{ t(`status.${selectedStep.status}`) }}
            </UiBadge>
          </div>
          <p>{{ stepSummary(selectedStep) }}</p>
          <dl>
            <div v-for="row in stepDetailRows(selectedStep)" :key="`selected:${row.label}`">
              <dt>{{ row.label }}</dt>
              <dd :title="row.value">{{ compactInspectorValue(row.value) }}</dd>
            </div>
          </dl>
        </UiCard>

        <UiCard v-if="selectedStep?.artifacts.length" class="inspector-section">
          <h2>{{ t("workbench.stepArtifacts") }}</h2>
          <RouterLink
            v-for="artifact in selectedStep.artifacts"
            :key="artifact.artifact_id"
            class="asset-link"
            :to="`/trace/${selectedStep.trace.trace_id}`"
          >
            <FileImage :size="16" />
            <strong>{{ artifact.name }}</strong>
            <span :title="`${artifactResolution(artifact)} · ${formatBytes(artifact.size_bytes ?? 0)}`">
              {{ artifactResolution(artifact) }} · {{ formatBytes(artifact.size_bytes ?? 0) }}
            </span>
            <ChevronRight :size="14" />
          </RouterLink>
        </UiCard>

        <UiCard class="inspector-section">
          <h2>{{ t("workbench.stepLinkedEntities") }}</h2>
          <RouterLink
            v-for="entity in selectedStepEntities.filter((item) => linkedEntityRoute(item))"
            :key="`${entity.type}:${entity.id}`"
            class="asset-link"
            :to="linkedEntityRoute(entity) ?? '/'"
          >
            <component :is="linkedEntityIcon(entity.type)" :size="16" />
            <strong>{{ linkedEntityLabel(entity) }}</strong>
            <span :title="entity.id">{{ compactIdentifier(entity.id) }}</span>
            <ChevronRight :size="14" />
          </RouterLink>
          <div
            v-for="entity in selectedStepEntities.filter((item) => !linkedEntityRoute(item))"
            :key="`${entity.type}:${entity.id}`"
            class="asset-link asset-link--static"
          >
            <component :is="linkedEntityIcon(entity.type)" :size="16" />
            <strong>{{ linkedEntityLabel(entity) }}</strong>
            <span :title="entity.id">{{ compactIdentifier(entity.id) }}</span>
          </div>
          <p v-if="!selectedStepEntities.length" class="asset-empty">{{ t("workbench.asset.empty") }}</p>
        </UiCard>

        <UiCard class="inspector-section quick-actions">
          <h2>{{ t("workbench.stepActions") }}</h2>
          <RouterLink
            v-for="action in selectedStepActions.filter((item) => actionRoute(item))"
            :key="action.id"
            :to="actionRoute(action) ?? '/'"
          >
            <component :is="quickActionIcon(action)" :size="17" />
            <span>
              <strong>{{ actionLabel(action) }}</strong>
              <small :title="action.owner">{{ action.owner }}</small>
            </span>
            <ExternalLink :size="14" />
          </RouterLink>
          <a
            v-for="action in selectedStepActions.filter((item) => !actionRoute(item) && actionHref(item))"
            :key="action.id"
            :href="actionHref(action) ?? '#'"
            target="_blank"
            rel="noreferrer"
          >
            <component :is="quickActionIcon(action)" :size="17" />
            <span>
              <strong>{{ actionLabel(action) }}</strong>
              <small :title="action.owner">{{ action.owner }}</small>
            </span>
            <ExternalLink :size="14" />
          </a>
          <button
            v-for="action in selectedStepActions.filter((item) => !actionRoute(item) && !actionHref(item))"
            :key="action.id"
            type="button"
            :disabled="!canRunAction(action)"
            @click="handleQuickAction(action)"
          >
            <component :is="quickActionIcon(action)" :size="17" />
            <span>
              <strong>{{ actionLabel(action) }}</strong>
              <small :title="action.disabled_reason ?? action.owner">{{ action.disabled_reason ?? action.owner }}</small>
            </span>
            <ExternalLink :size="14" />
          </button>
          <p v-if="!selectedStepActions.length" class="asset-empty">{{ t("workbench.asset.empty") }}</p>
        </UiCard>
      </template>

      <template v-else-if="activeInspectorTab === 'debug'">
        <UiCard
          v-for="section in inspectorSectionsFor('debug')"
          :key="section.id"
          class="inspector-section"
        >
          <h2>{{ section.title }}</h2>
          <dl>
            <div v-for="item in section.items" :key="`${section.id}:${item.label}`">
              <dt>{{ item.label }}</dt>
              <dd>
                <RouterLink v-if="item.route" :to="item.route" :title="item.value">
                  {{ compactInspectorValue(item.value) }}
                </RouterLink>
                <span v-else :title="item.value">{{ compactInspectorValue(item.value) }}</span>
              </dd>
            </div>
          </dl>
        </UiCard>
        <UiCard v-if="!inspectorSectionsFor('debug').length" class="inspector-section">
          <h2>{{ t("workbench.debug.runtime") }}</h2>
          <dl>
            <div>
              <dt>{{ t("trace.id.trace") }}</dt>
              <dd :title="run.trace.trace_id">{{ compactIdentifier(run.trace.trace_id) }}</dd>
            </div>
            <div>
              <dt>{{ t("trace.id.run") }}</dt>
              <dd :title="run.run_id">{{ compactIdentifier(run.run_id) }}</dd>
            </div>
            <div>
              <dt>{{ t("trace.id.session") }}</dt>
              <dd :title="run.session_key">{{ compactIdentifier(run.session_key) }}</dd>
            </div>
            <div>
              <dt>{{ t("trace.id.turn") }}</dt>
              <dd :title="activeTurnId ?? '-'">{{ compactIdentifier(activeTurnId) }}</dd>
            </div>
          </dl>
        </UiCard>
        <UiCard v-if="!inspectorSectionsFor('debug').length" class="inspector-section">
          <h2>{{ t("workbench.debug.steps") }}</h2>
          <dl>
            <div>
              <dt>{{ t("common.total") }}</dt>
              <dd>{{ stepStats.total }}</dd>
            </div>
            <div>
              <dt>{{ t("status.running") }}</dt>
              <dd>{{ stepStats.running }}</dd>
            </div>
            <div>
              <dt>{{ t("status.waiting") }}</dt>
              <dd>{{ stepStats.waiting }}</dd>
            </div>
            <div>
              <dt>{{ t("common.toolCalls") }}</dt>
              <dd>{{ stepStats.tool }}</dd>
            </div>
          </dl>
        </UiCard>
      </template>

      <template v-else-if="activeInspectorTab === 'context'">
        <UiCard class="inspector-section context-tree-card">
          <div class="context-tree-card__heading">
            <h2>{{ t("workbench.context.title") }}</h2>
            <button
              type="button"
              :disabled="contextTreeLoading || !contextSessionKey"
              @click="refreshContextTree"
            >
              <Loader2 v-if="contextTreeLoading" class="motion-spin" :size="14" />
              <span>{{ t("common.refresh") }}</span>
            </button>
          </div>
          <p v-if="contextTreeError" class="context-tree-error">{{ contextTreeError }}</p>
          <dl v-if="contextTree?.workspace" class="context-tree-summary">
            <div>
              <dt>{{ t("trace.id.session") }}</dt>
              <dd :title="contextTree.workspace.session_key">{{ compactIdentifier(contextTree.workspace.session_key) }}</dd>
            </div>
            <div>
              <dt>{{ t("common.agent") }}</dt>
              <dd :title="contextTree.workspace.agent_id">{{ compactIdentifier(contextTree.workspace.agent_id) }}</dd>
            </div>
            <div>
              <dt>{{ t("workbench.context.revision") }}</dt>
              <dd>{{ contextTree.workspace.active_revision }}</dd>
            </div>
            <div>
              <dt>{{ t("table.updated") }}</dt>
              <dd>{{ formatLocalTime(contextTree.workspace.updated_at) }}</dd>
            </div>
          </dl>
          <p v-else-if="!contextTreeLoading && !contextTreeError" class="asset-empty">
            {{ contextSessionKey ? t("workbench.context.empty") : t("workbench.context.noSession") }}
          </p>
        </UiCard>

        <UiCard v-if="contextTree" class="inspector-section context-tree-card">
          <h2>{{ t("workbench.context.estimate") }}</h2>
          <dl>
            <div v-for="row in contextEstimateRows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>
        </UiCard>

        <UiCard v-if="contextRenderSnapshot" class="inspector-section context-tree-card">
          <h2>{{ t("workbench.context.renderSnapshot") }}</h2>
          <dl>
            <div v-for="row in contextSnapshotRows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>
          <pre class="context-snapshot-preview">{{ contextRenderSnapshot.prompt_body.slice(0, 1800) }}</pre>
        </UiCard>

        <UiCard v-if="contextTree" class="inspector-section context-tree-card">
          <div class="context-tree-card__heading context-tree-card__heading--stacked">
            <h2>{{ t("workbench.context.nodes") }}</h2>
            <div class="context-memory-filters" :aria-label="t('workbench.context.memory.filterLabel')">
              <button
                v-for="option in contextMemoryLayerOptions"
                :key="option.id"
                type="button"
                :class="{ active: contextMemoryLayerFilter === option.id }"
                @click="contextMemoryLayerFilter = option.id"
              >
                <span>{{ option.label }}</span>
                <small>{{ option.count }}</small>
              </button>
            </div>
          </div>
          <div v-if="!contextXmlLines.length" class="asset-empty">{{ t("workbench.context.emptyNodes") }}</div>
          <div v-else class="context-xml-viewer" role="tree">
            <div
              v-for="line in contextXmlLines"
              :key="line.key"
              class="context-xml-line-row"
              :class="contextXmlLineClasses(line)"
              :style="contextXmlLineStyle(line)"
              role="treeitem"
              :aria-level="line.depth + 1"
              :aria-expanded="contextXmlLineCanFold(line) ? !line.displayFolded : undefined"
            >
              <span class="context-xml-line-number">{{ line.lineNumber }}</span>
              <span class="context-xml-fold-gutter">
                <button
                  v-if="contextXmlLineCanFold(line)"
                  type="button"
                  class="context-xml-display-toggle"
                  :aria-label="line.displayFolded ? t('workbench.context.action.expand') : t('workbench.context.action.collapse')"
                  @click="toggleContextXmlDisplayFold(line.node.id)"
                >
                  <ChevronRight v-if="line.displayFolded" :size="13" />
                  <ChevronDown v-else :size="13" />
                </button>
              </span>
              <code class="context-xml-source-line" :title="line.node.id">
                <template v-if="line.kind === 'close'">
                  <span class="context-xml-punct">&lt;/</span><span class="context-xml-tag">{{ line.tag }}</span><span class="context-xml-punct">&gt;</span>
                </template>
                <template v-else-if="line.kind === 'summary'">
                  <span class="context-xml-punct">&lt;</span><span class="context-xml-tag">summary</span><span class="context-xml-punct">&gt;</span><span class="context-xml-text">{{ xmlText(line.summary) }}</span><span class="context-xml-punct">&lt;/</span><span class="context-xml-tag">summary</span><span class="context-xml-punct">&gt;</span>
                </template>
                <template v-else>
                  <span class="context-xml-punct">&lt;</span><span class="context-xml-tag">{{ line.tag }}</span>
                  <template
                    v-for="attribute in line.attributes"
                    :key="`${line.key}:attr:${attribute.name}`"
                  >
                    <span class="context-xml-attr"> {{ attribute.name }}</span><span class="context-xml-equals">=</span><span class="context-xml-value">"{{ xmlAttributeText(attribute.value) }}"</span>
                  </template>
                  <template v-if="line.kind === 'self'">
                    <span class="context-xml-punct"> /&gt;</span>
                  </template>
                  <template v-else-if="line.kind === 'folded'">
                    <span class="context-xml-punct">&gt;</span><span class="context-xml-ellipsis">…</span><span class="context-xml-punct">&lt;/</span><span class="context-xml-tag">{{ line.tag }}</span><span class="context-xml-punct">&gt;</span>
                  </template>
                  <template v-else>
                    <span class="context-xml-punct">&gt;</span>
                  </template>
                </template>
              </code>
              <div v-if="contextXmlLineActions(line).length" class="context-xml-actions">
                <button
                  v-for="action in contextXmlLineActions(line)"
                  :key="action.id"
                  type="button"
                  class="context-xml-action"
                  :disabled="contextActionBusy !== null"
                  @click="runContextXmlBusinessAction(line.node, action.id)"
                >
                  <Loader2
                    v-if="contextActionBusy === contextXmlBusinessActionBusyKey(line.node, action.id)"
                    class="motion-spin"
                    :size="11"
                  />
                  <span>{{ action.label }}</span>
                </button>
              </div>
            </div>
          </div>
        </UiCard>
      </template>

      <template v-else-if="activeInspectorTab === 'memory'">
        <UiCard
          v-for="section in inspectorSectionsFor('memory')"
          :key="section.id"
          class="inspector-section"
        >
          <h2>{{ section.title }}</h2>
          <dl>
            <div v-for="item in section.items" :key="`${section.id}:${item.label}`">
              <dt>{{ item.label }}</dt>
              <dd>
                <RouterLink v-if="item.route" :to="item.route" :title="item.value">
                  {{ compactInspectorValue(item.value) }}
                </RouterLink>
                <span v-else :title="item.value">{{ compactInspectorValue(item.value) }}</span>
              </dd>
            </div>
          </dl>
        </UiCard>
        <UiCard v-if="!inspectorSectionsFor('memory').length" class="inspector-section">
          <h2>{{ t("workbench.memory.session") }}</h2>
          <dl>
            <div>
              <dt>{{ t("trace.id.session") }}</dt>
              <dd :title="(isNewSessionDraft ? draftSessionKey : run.session_key) ?? '-'">
                {{ compactIdentifier(isNewSessionDraft ? draftSessionKey : run.session_key) }}
              </dd>
            </div>
            <div>
              <dt>{{ t("workbench.turns") }}</dt>
              <dd>{{ run.turns.length }}</dd>
            </div>
            <div>
              <dt>{{ t("workbench.currentTurn") }}</dt>
              <dd>{{ activeTurnSummary ? t("workbench.turnLabel", { ordinal: activeTurnSummary.ordinal }) : "-" }}</dd>
            </div>
          </dl>
        </UiCard>
        <UiCard v-if="!inspectorSectionsFor('memory').length" class="inspector-section">
          <h2>{{ t("workbench.linkedAssets") }}</h2>
          <p>{{ linkedAssets.length ? t("workbench.memory.assetsFound", { count: linkedAssets.length }) : t("workbench.asset.empty") }}</p>
        </UiCard>
      </template>

      <template v-else>
        <UiCard
          v-for="section in inspectorSectionsFor('agent')"
          :key="section.id"
          class="inspector-section"
        >
          <h2>{{ section.title }}</h2>
          <dl>
            <div v-for="item in section.items" :key="`${section.id}:${item.label}`">
              <dt>{{ item.label }}</dt>
              <dd>
                <RouterLink v-if="item.route" :to="item.route" :title="item.value">
                  {{ compactInspectorValue(item.value) }}
                </RouterLink>
                <span v-else :title="item.value">{{ compactInspectorValue(item.value) }}</span>
              </dd>
            </div>
          </dl>
        </UiCard>
        <UiCard v-if="!inspectorSectionsFor('agent').length" class="inspector-section">
          <h2>{{ t("workbench.inspect.agent") }}</h2>
          <dl>
            <div>
              <dt>{{ t("common.agent") }}</dt>
              <dd>{{ run.agent.name }}</dd>
            </div>
            <div>
              <dt>{{ t("common.model") }}</dt>
              <dd>{{ run.model.name }}</dd>
            </div>
            <div>
              <dt>{{ t("common.status") }}</dt>
              <dd>{{ t(`status.${run.status}`) }}</dd>
            </div>
            <div>
              <dt>{{ t("workbench.agent.source") }}</dt>
              <dd>{{ isNewSessionDraft ? "ui.workbench:new" : "ui.workbench" }}</dd>
            </div>
          </dl>
        </UiCard>
        <UiCard class="inspector-section">
          <h2>{{ t("workbench.tools.available") }}</h2>
          <button type="button" @click="toggleToolsMenu">
            <span>{{ t("workbench.tools.openCatalog") }}</span>
            <ChevronRight :size="14" />
          </button>
        </UiCard>
      </template>
    </aside>
  </div>
  <div v-else class="workbench-empty">
    <Loader2 class="motion-spin" :size="20" />
    <span>{{ loadingRun ? t("workbench.loading") : loadError ?? t("workbench.empty") }}</span>
  </div>
</template>

<style scoped>
.workbench-page {
  display: grid;
  grid-template-columns: 324px minmax(560px, 1fr) 328px;
  height: calc(100dvh - var(--shell-topbar-height));
  overflow: hidden;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-active) 18%, transparent), transparent 34%),
    var(--surface-page);
}

.workbench-page,
.workbench-page * {
  box-sizing: border-box;
}

.workbench-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  height: calc(100dvh - var(--shell-topbar-height));
  color: var(--text-muted);
}

.motion-spin,
.motion-breathe {
  transform-box: fill-box;
  transform-origin: center;
  will-change: transform, opacity;
}

.motion-spin {
  animation: workbench-spin 0.9s linear infinite;
}

.motion-breathe {
  animation: workbench-breathe 1.55s ease-in-out infinite;
}

.threads-panel,
.inspector-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px 14px 12px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 24%, transparent), transparent 54%),
    var(--surface-sidebar);
}

.threads-panel {
  border-right: 1px solid var(--border-subtle);
  overflow: hidden;
}

.inspector-panel {
  gap: var(--space-3);
  border-left: 1px solid var(--border-subtle);
}

.panel-header,
.connection-strip,
.connection-strip span,
.run-card,
.run-card__title,
.turns-row,
.view-tabs,
.step-row header,
.artifact-strip,
.status-strip,
.composer,
.composer__input,
.composer__actions,
.inspector-section > a,
.inspector-section > button,
.inspector-section dl div,
.thread-card__status,
.thread-card small,
.threads-footer button {
  display: flex;
  align-items: center;
}

.panel-header,
.connection-strip,
.run-card,
.run-card__title,
.step-row header,
.status-strip,
.composer,
.inspector-section > a,
.inspector-section > button {
  justify-content: space-between;
}

.panel-header h1 {
  margin: 0;
  font-size: 20px;
  line-height: 1.15;
}

.thread-filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
  gap: var(--space-2);
  margin: 12px 0;
}

.thread-filters button,
.turns-row button,
.view-tabs button,
.inspector-tabs button,
.icon-only {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
}

.thread-filters button {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-width: 0;
  min-height: 34px;
  padding: 0 10px;
  overflow: hidden;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}

.thread-filters strong {
  margin-left: 0;
  color: var(--text-primary);
  font-size: 12px;
}

.thread-filters button.active {
  border-color: var(--color-accent);
  background: var(--surface-active);
  color: var(--color-accent);
}

.thread-filters button.active strong {
  color: var(--color-accent);
}

.threads-list {
  flex: 1 1 auto;
  min-height: 0;
  padding-right: 2px;
}

.thread-filter-empty {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 64px;
  padding: 0 12px;
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-3);
  color: var(--text-muted);
  font-size: 12px;
}

.thread-filter-empty svg {
  flex: 0 0 auto;
  color: var(--color-accent);
}

.thread-card {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 34px) auto auto;
  width: 100%;
  min-width: 0;
  min-height: 120px;
  max-height: 120px;
  gap: 5px;
  margin-bottom: 10px;
  padding: 10px 12px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 28%, transparent), transparent),
    var(--surface-panel);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
}

.thread-card--active {
  border-color: var(--color-accent);
  background: var(--surface-active);
}

.thread-card--failed .thread-card__adornment {
  color: var(--color-danger);
}

.thread-card strong {
  display: -webkit-box;
  min-width: 0;
  padding-right: 24px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.thread-card__agent {
  display: block;
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-card small {
  min-width: 0;
  justify-content: space-between;
  gap: var(--space-2);
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.35;
}

.thread-card__activity {
  display: inline-flex;
  flex: 1 1 auto;
  align-items: center;
  gap: var(--space-1);
  min-width: 0;
  overflow: hidden;
}

.thread-card__activity svg {
  flex: 0 0 auto;
}

.thread-card__activity > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-card__time {
  flex: 0 0 auto;
  margin-left: auto;
  white-space: nowrap;
}

.thread-card__status {
  gap: var(--space-2);
  max-width: calc(100% - 26px);
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-card__adornment {
  position: absolute;
  top: 10px;
  right: 12px;
  color: var(--color-blue);
}

.thread-card__adornment svg {
  display: block;
}

.thread-card__waiting {
  display: block;
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: var(--color-warning);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-warning) 15%, transparent);
}

.thread-card--waiting small svg {
  animation: workbench-breathe 1.55s ease-in-out infinite;
  transform-box: fill-box;
  transform-origin: center;
}

.thread-card--draft {
  border-color: color-mix(in srgb, var(--color-accent) 70%, transparent);
  background: color-mix(in srgb, var(--color-accent) 18%, var(--surface-panel));
}

.threads-footer {
  display: grid;
  flex: 0 0 auto;
  gap: var(--space-2);
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.threads-footer button {
  gap: var(--space-2);
  min-height: 30px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  font-size: 12px;
}

.workbench-main {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto auto;
  gap: 10px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 16px 14px 10px;
}

.workbench-main > * {
  min-width: 0;
  max-width: 100%;
}

.connection-stack {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.connection-strip,
.status-strip {
  min-width: 0;
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  color: var(--text-secondary);
  font-size: 12px;
}

.connection-strip {
  overflow: hidden;
  min-height: 40px;
  background: color-mix(in srgb, var(--color-success) 12%, var(--surface-panel));
}

.connection-strip span {
  min-width: 0;
  gap: var(--space-2);
}

.connection-strip span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.connection-strip span:last-child {
  flex: 0 0 auto;
  white-space: nowrap;
}

.run-card {
  gap: 12px;
  min-width: 0;
  min-height: 132px;
  overflow: hidden;
  padding: 14px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 20%, transparent), transparent),
    var(--surface-panel);
}

.run-card__media {
  flex: 0 0 96px;
  height: 96px;
  overflow: hidden;
  border-radius: var(--radius-2);
  background: var(--surface-raised);
}

.run-card__media img,
.artifact-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.run-card__body {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.run-card__title {
  gap: var(--space-3);
  justify-content: start;
  min-width: 0;
}

.run-card h2 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: 20px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-facts {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 0.75fr) minmax(0, 0.85fr) minmax(0, 1fr) minmax(0, 1.45fr);
  gap: 0;
  min-width: 0;
  margin: 14px 0 0;
}

.run-facts > div {
  min-width: 0;
  overflow: hidden;
  padding: 0 12px;
  border-left: 1px solid var(--border-subtle);
}

.run-facts > div:first-child {
  padding-left: 0;
  border-left: 0;
}

dt {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

dd {
  min-width: 0;
  overflow: hidden;
  margin: 3px 0 0;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.icon-only {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
}

.timeline-slot {
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 18%, transparent), transparent 42%),
    var(--surface-panel);
  box-shadow: var(--shadow-raised);
  scrollbar-gutter: stable;
}

.turns-card {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  padding: 12px 12px 0;
  border: 0;
  border-radius: 0;
  overflow: hidden;
  background: transparent;
  box-shadow: none;
}

.turns-row {
  gap: 10px;
  justify-content: start;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 4px;
  font-size: 13px;
  scrollbar-gutter: auto;
}

.turns-row > strong {
  flex: 0 0 auto;
  margin-right: var(--space-2);
}

.turns-row button {
  display: grid;
  flex: 0 0 auto;
  min-width: 112px;
  min-height: 52px;
  padding: 8px 11px;
  text-align: left;
  font-size: 14px;
}

.turns-row button.active {
  border-color: var(--color-accent);
  background: var(--surface-active);
  color: var(--text-primary);
}

.view-tabs button.active,
.inspector-tabs button.active {
  border-color: transparent transparent var(--color-accent);
  background: transparent;
  color: var(--color-accent);
}

.turns-row small {
  color: var(--text-muted);
  font-size: 12px;
}

.draft-session-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  min-height: 52px;
  padding: 0 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.draft-session-strip strong {
  flex: 0 0 auto;
  color: var(--color-accent);
}

.draft-session-strip span {
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.view-tabs {
  gap: var(--space-2);
  margin: 7px 0 5px;
  border-bottom: 1px solid var(--border-subtle);
}

.view-tabs button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 30px;
  font-size: 14px;
  border-width: 0 0 2px;
  background: transparent;
}

.step-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.step-stack {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.step-row--live-final {
  --step-color: var(--color-accent);
  --step-dot-color: var(--color-accent);
}

.step-row--live-final .step-row__content {
  border-color: color-mix(in srgb, var(--color-accent) 48%, var(--border-subtle));
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-accent) 13%, transparent), transparent 52%),
    var(--surface-panel);
  box-shadow: inset 3px 0 0 var(--color-accent);
  animation: workbench-stream-in 180ms ease-out;
}

.step-row--live-final .step-icon {
  animation: workbench-icon-breathe 1.7s ease-in-out infinite;
}

.live-stream-cursor {
  display: inline-block;
  width: 7px;
  height: 18px;
  margin-top: 8px;
  border-radius: 999px;
  background: var(--color-accent);
  animation: workbench-stream-cursor 900ms steps(2, jump-none) infinite;
}

.draft-session-empty {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  min-height: 100%;
  padding: 24px;
  color: var(--text-secondary);
  text-align: center;
}

.draft-session-empty strong {
  color: var(--text-primary);
  font-size: 16px;
}

.draft-session-empty p {
  max-width: 360px;
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}

.step-row {
  --step-action-width: 112px;
  --step-card-padding-block: 12px;
  --step-card-padding-inline: 14px;
  --step-color: var(--color-gray);
  --step-dot-color: var(--border-strong);
  display: grid;
  grid-template-columns: 72px 28px minmax(0, 1fr);
  cursor: pointer;
}

.step-row:focus-visible .step-row__content {
  outline: 2px solid color-mix(in srgb, var(--color-accent) 70%, transparent);
  outline-offset: 2px;
}

.step-row--selected .step-row__content {
  border-color: color-mix(in srgb, var(--color-accent) 56%, var(--border-subtle));
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--color-accent) 9%, transparent), transparent 58%),
    var(--surface-panel-soft);
  box-shadow: inset 3px 0 0 var(--color-accent);
}

.step-row--selected .step-row__dot {
  background: var(--color-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-accent) 16%, transparent);
}

.step-row--user {
  --step-color: var(--color-violet);
}

.step-row--llm {
  --step-color: var(--color-blue);
}

.step-row--tool-call {
  --step-color: var(--color-violet);
  --step-dot-color: var(--color-violet);
}

.step-row--tool-result {
  --step-color: var(--color-gray);
}

.step-row--final {
  --step-color: var(--color-success);
}

.step-row--warning {
  --step-color: var(--color-warning);
  --step-dot-color: var(--color-warning);
  --step-action-width: 132px;
}

.step-row--danger {
  --step-color: var(--color-danger);
  --step-dot-color: var(--color-danger);
}

.step-row time {
  padding-top: 18px;
  color: var(--text-muted);
  font-size: 12px;
}

.step-row__line {
  position: relative;
  display: flex;
  justify-content: center;
}

.step-row__line::before {
  width: 1px;
  background: var(--border-strong);
  content: "";
}

.step-row__dot {
  position: absolute;
  top: 22px;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--step-dot-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--step-dot-color) 12%, transparent);
}

.step-row--pending .step-row__dot {
  animation: workbench-dot-breathe 1.55s ease-in-out infinite;
}

.step-row--pending .step-icon {
  animation: workbench-icon-breathe 1.7s ease-in-out infinite;
}

.step-row__content {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) minmax(var(--step-action-width), max-content);
  align-items: start;
  gap: 14px;
  min-height: 0;
  padding: var(--step-card-padding-block) var(--step-card-padding-inline);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background: var(--surface-panel-soft);
}

.step-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--step-color) 25%, transparent);
  color: var(--step-color);
}

.step-row h3 {
  margin: 0;
  font-size: 15px;
  line-height: 1.3;
}

.inspector-section h2 {
  margin: 0;
  font-size: 14px;
  line-height: 1.3;
}

.step-row__body {
  min-width: 0;
}

.step-row header {
  justify-content: flex-start;
}

.step-row header,
.step-row__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.step-row__actions {
  display: grid;
  align-content: start;
  justify-items: end;
  justify-self: end;
  gap: 6px;
  min-width: 0;
  width: max-content;
  max-width: var(--step-action-width);
}

.step-row p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.45;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.inspector-section p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.step-inspector-card__heading {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.step-inspector-card__heading strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-row__status {
  display: inline-flex;
  align-items: center;
  justify-content: end;
  gap: var(--space-1);
  min-width: 34px;
  color: var(--text-muted);
  font-size: 12px;
}

.step-row__status--success {
  color: var(--color-success);
}

.step-row__status--info {
  min-height: 28px;
  padding: 0 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-blue) 12%, transparent);
  color: var(--color-blue);
}

.step-row__status--warning {
  color: var(--color-warning);
}

.step-row__status--danger {
  color: var(--color-danger);
}

.artifact-strip {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr);
  align-items: center;
  justify-content: stretch;
  gap: 16px;
  margin-top: 10px;
}

.artifact-thumb {
  width: 128px;
  height: 72px;
  overflow: hidden;
  border-radius: var(--radius-2);
  background: var(--surface-raised);
}

.artifact-meta {
  display: grid;
  gap: 8px;
  margin: 0;
}

.artifact-meta div {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  align-items: center;
  gap: var(--space-3);
}

.artifact-meta dt {
  color: var(--text-muted);
  font-size: 12px;
}

.artifact-meta dd {
  margin: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-details-panel {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 54%, transparent);
}

.step-details-panel dl {
  display: grid;
  gap: 7px;
  margin: 0;
}

.step-details-panel div {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 10px;
}

.step-details-panel dt,
.step-details-panel dd {
  font-size: 11px;
  line-height: 1.35;
}

.step-details-panel dd {
  font-family: var(--font-mono);
  white-space: normal;
  overflow-wrap: anywhere;
}

.step-details-panel a {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 28px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-panel);
  color: var(--color-accent);
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}

.step-action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--step-action-width);
  max-width: 100%;
  min-height: 30px;
  padding: 0 10px;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 64%, transparent);
  color: var(--color-accent);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}

:deep(.step-action-button) {
  border-color: transparent;
  background: color-mix(in srgb, var(--surface-raised) 64%, transparent);
  box-shadow: none;
}

.skill-approval-card {
  display: grid;
  gap: 9px;
  margin-top: 10px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 32%, var(--border-subtle));
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-warning) 7%, var(--surface-raised));
}

.skill-approval-card header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.skill-approval-card header span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 750;
  text-transform: uppercase;
}

.skill-approval-card header strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-approval-card dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin: 0;
}

.skill-approval-card dl div {
  min-width: 0;
}

.skill-approval-card dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.skill-approval-card dd {
  min-width: 0;
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11.5px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-approval-risk {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding-top: 2px;
  border-top: 1px solid var(--border-subtle);
}

.skill-approval-risk span {
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 750;
}

.skill-approval-risk ul {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.skill-approval-risk li {
  max-width: 100%;
  padding: 2px 7px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
  color: var(--color-warning);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.approval-actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  width: 100%;
  max-width: 100%;
  margin-top: 10px;
}

:deep(.approval-action-button) {
  width: 100%;
  min-height: 30px;
  padding-inline: 8px;
  font-size: 12px;
}

.approval-error {
  display: block;
  width: 100%;
  max-width: 100%;
  margin-top: 6px;
  color: var(--color-danger);
  font-size: 11px;
  line-height: 1.35;
  overflow-wrap: anywhere;
  text-align: left;
}

.status-strip a,
.inspector-section a {
  color: var(--color-accent);
  text-decoration: none;
}

.status-strip {
  --strip-color: var(--color-accent);
  min-height: 48px;
  gap: 18px;
  padding: 0 14px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--strip-color) 8%, var(--surface-raised)), color-mix(in srgb, var(--surface-panel) 94%, var(--strip-color))),
    var(--surface-panel);
  font-size: 13px;
  line-height: 1.25;
}

.status-strip__main,
.status-strip__meta,
.status-strip__action {
  display: flex;
  align-items: center;
}

.status-strip__main {
  flex: 1 1 auto;
  min-width: 0;
  gap: var(--space-2);
  overflow: hidden;
}

.status-strip__main svg {
  flex: 0 0 auto;
  color: var(--strip-color);
}

.status-strip__action svg {
  color: var(--color-accent);
}

.status-strip__main strong {
  min-width: 0;
  overflow: hidden;
  color: var(--color-accent);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-strip__main span,
.status-strip__meta {
  color: var(--text-secondary);
}

.status-strip__main span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-strip__meta {
  flex: 0 1 auto;
  gap: 34px;
  margin-left: auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
}

.status-strip__action {
  gap: var(--space-2);
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 82%, transparent);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.status-strip--success {
  --strip-color: var(--color-success);
}

.status-strip--warning {
  --strip-color: var(--color-warning);
}

.status-strip--danger {
  --strip-color: var(--color-danger);
}

@keyframes workbench-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes workbench-breathe {
  0%,
  100% {
    opacity: 0.68;
    transform: scale(0.92);
  }

  50% {
    opacity: 1;
    transform: scale(1.06);
  }
}

@keyframes workbench-icon-breathe {
  0%,
  100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--step-color) 12%, transparent);
  }

  50% {
    box-shadow: 0 0 0 5px color-mix(in srgb, var(--step-color) 12%, transparent);
  }
}

@keyframes workbench-dot-breathe {
  0%,
  100% {
    opacity: 0.72;
    transform: scale(0.86);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--step-dot-color) 10%, transparent);
  }

  50% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 0 7px color-mix(in srgb, var(--step-dot-color) 12%, transparent);
  }
}

@keyframes workbench-stream-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes workbench-stream-cursor {
  0%,
  45% {
    opacity: 1;
  }

  46%,
  100% {
    opacity: 0.18;
  }
}

@media (prefers-reduced-motion: reduce) {
  .motion-spin,
  .motion-breathe,
  .thread-card--waiting small svg,
  .step-row--pending .step-row__dot,
  .step-row--pending .step-icon,
  .step-row--live-final .step-icon,
  .step-row--live-final .step-row__content,
  .live-stream-cursor {
    animation: none;
  }
}

.composer {
  min-height: 116px;
  align-items: end;
  gap: var(--space-3);
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 18%, transparent), transparent),
    var(--surface-panel);
}

.composer__input {
  flex: 1;
  flex-wrap: wrap;
  gap: var(--space-2);
  min-width: 0;
}

.composer__file-input {
  display: none;
}

.composer-bottom-row {
  display: flex;
  flex: 0 1 auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.composer-runtime-row {
  display: flex;
  flex: 0 1 auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.composer-runtime-row label {
  display: inline-grid;
  grid-template-columns: auto auto minmax(104px, 1fr);
  align-items: center;
  gap: 6px;
  min-width: 180px;
  max-width: 280px;
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 12px;
}

.composer-runtime-row label svg {
  color: var(--color-accent);
}

.composer-runtime-row label span {
  color: var(--text-muted);
  white-space: nowrap;
}

.composer-runtime-row select {
  min-width: 0;
  height: 28px;
  overflow: hidden;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  text-overflow: ellipsis;
}

.composer-runtime-row small {
  min-width: 0;
  overflow: hidden;
  color: var(--color-danger);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer input {
  flex: 1 0 100%;
  min-width: 0;
  height: 42px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
}

.composer input:disabled {
  color: var(--text-muted);
}

.composer__mode,
.composer__error {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: var(--radius-2);
  font-size: 12px;
  line-height: 1.2;
}

.composer__mode {
  border: 1px solid color-mix(in srgb, var(--color-accent) 44%, transparent);
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent);
}

.composer__error {
  max-width: 100%;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--color-danger) 42%, transparent);
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer-attachments {
  display: flex;
  flex: 1 0 100%;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.composer-attachment {
  max-width: 220px;
  padding-inline: 8px !important;
}

.composer-attachment span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 30px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
}

.composer button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.composer__input button {
  padding: 0 10px;
  font-size: 12px;
}

.composer-tool-anchor {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.composer-tool-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 6px);
  z-index: 5;
  display: grid;
  gap: 4px;
  width: 340px;
  max-width: min(340px, calc(100vw - 32px));
  max-height: 260px;
  overflow: auto;
  padding: 8px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-3);
  background: var(--surface-panel);
  box-shadow: var(--shadow-panel);
}

.composer-tool-menu__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding-bottom: 3px;
  border-bottom: 1px solid var(--border-subtle);
}

.composer-tool-menu__header strong {
  color: var(--text-primary);
  font-size: 13px;
}

.composer-tool-menu__header button {
  width: 28px;
  justify-content: center;
  padding: 0;
}

.composer-tool-menu__state {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  color: var(--text-secondary);
  font-size: 12px;
}

.composer-tool-menu__state--danger {
  color: var(--color-danger);
}

.composer-tool-item {
  display: grid !important;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  width: 100%;
  min-height: 42px !important;
  padding: 5px 7px !important;
  text-align: left;
}

.composer-tool-item > span {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.composer-tool-item strong,
.composer-tool-item small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer-tool-item strong {
  color: var(--text-primary);
  font-size: 12px;
}

.composer-tool-item small {
  color: var(--text-muted);
  font-size: 10px;
}

.composer__actions {
  align-self: end;
  gap: 1px;
}

.inspector-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  min-height: 52px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 18%, transparent), transparent),
    var(--surface-panel);
}

.inspector-tabs button {
  min-height: 50px;
  border-width: 0 0 2px;
  border-color: transparent;
  border-radius: 0;
  background: transparent;
  font-size: 13px;
}

.inspector-section {
  display: grid;
  gap: 12px;
  padding: 14px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--surface-raised) 16%, transparent), transparent),
    var(--surface-panel);
}

.inspector-section dl {
  display: grid;
  gap: 10px;
  margin: 0;
}

.inspector-section dl div {
  display: grid;
  grid-template-columns: minmax(74px, 0.48fr) minmax(0, 1fr);
  align-items: start;
  justify-content: stretch;
  gap: 10px;
  min-width: 0;
}

.inspector-section dt,
.inspector-section dd {
  min-width: 0;
  font-size: 12px;
  line-height: 1.4;
}

.inspector-section dt {
  overflow: hidden;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspector-section dd {
  margin: 0;
  overflow: hidden;
  color: var(--text-secondary);
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspector-section dd > a,
.inspector-section dd > span {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspector-section dd > a {
  min-height: 0;
  padding: 0;
  border: 0;
  color: var(--color-accent);
}

.inspector-section > a,
.inspector-section > button {
  min-height: 44px;
  min-width: 0;
  gap: var(--space-2);
  justify-content: space-between;
  border-bottom: 1px solid var(--border-subtle);
}

.inspector-section > button {
  border-width: 0 0 1px;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.inspector-section > button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.context-tree-card__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.context-tree-card__heading--stacked {
  align-items: flex-start;
  flex-direction: column;
}

.context-tree-card__heading h2 {
  margin: 0;
}

.context-tree-card__heading button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.context-tree-card__heading button:disabled,
.context-xml-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.context-memory-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.context-memory-filters button {
  min-height: 24px;
  gap: 5px;
  padding: 0 7px;
}

.context-memory-filters button.active {
  border-color: color-mix(in srgb, var(--color-accent) 60%, transparent);
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent);
}

.context-memory-filters small {
  color: var(--text-muted);
  font-size: 10px;
}

.context-tree-error {
  margin: 0;
  padding: 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 42%, transparent);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  color: var(--color-danger);
  font-size: 12px;
}

.context-tree-summary {
  grid-template-columns: 1fr;
}

.context-snapshot-preview {
  max-height: 180px;
  margin: 0;
  overflow: auto;
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-inset);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.context-xml-viewer {
  --xml-indent: 18px;
  display: grid;
  max-height: min(62vh, 680px);
  overflow: auto;
  padding: 6px 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-inset);
  font-family: var(--font-mono);
}

.context-xml-line-row {
  display: grid;
  grid-template-columns: 36px 18px minmax(0, 1fr) auto;
  align-items: center;
  min-height: 21px;
  padding-right: 8px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
}

.context-xml-line-row:hover {
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
}

.context-xml-line-row--hidden {
  opacity: 0.62;
}

.context-xml-line-row--summary {
  color: var(--text-muted);
}

.context-xml-line-number {
  align-self: stretch;
  padding-right: 8px;
  border-right: 1px solid color-mix(in srgb, var(--border-subtle) 72%, transparent);
  color: color-mix(in srgb, var(--text-muted) 72%, transparent);
  line-height: 21px;
  text-align: right;
  user-select: none;
}

.context-xml-fold-gutter {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
}

.context-xml-display-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 0;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.context-xml-display-toggle:hover {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
  color: var(--color-accent);
}

.context-xml-source-line {
  display: block;
  min-width: 0;
  overflow: hidden;
  padding-left: calc(var(--xml-depth) * var(--xml-indent));
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 21px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-xml-punct {
  color: color-mix(in srgb, var(--text-muted) 86%, transparent);
}

.context-xml-tag {
  color: color-mix(in srgb, var(--color-accent) 88%, var(--text-primary));
}

.context-xml-attr {
  color: color-mix(in srgb, var(--color-warning) 78%, var(--text-secondary));
}

.context-xml-equals {
  color: var(--text-muted);
}

.context-xml-value {
  color: color-mix(in srgb, var(--color-success) 78%, var(--text-primary));
}

.context-xml-text {
  color: var(--text-secondary);
}

.context-xml-ellipsis {
  padding: 0 3px;
  color: color-mix(in srgb, var(--text-muted) 76%, transparent);
}

.context-xml-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
  padding-left: 8px;
}

.context-xml-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-height: 20px;
  padding: 0 5px;
  border: 1px solid transparent;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.context-xml-action:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-accent) 42%, transparent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.asset-link {
  display: grid !important;
  grid-template-columns: auto minmax(58px, 0.72fr) minmax(0, 1fr) auto;
  align-items: center;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
}

.asset-link--static {
  min-height: 44px;
  align-items: center;
  justify-content: start;
  border-bottom: 1px solid var(--border-subtle);
}

.asset-link strong {
  min-width: 0;
  overflow: hidden;
  color: var(--color-accent);
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-empty {
  min-height: 34px;
}

.asset-link span {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-actions a,
.quick-actions button {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
}

.quick-actions a > span,
.quick-actions button > span {
  display: grid;
  gap: 2px;
  min-width: 0;
  overflow: hidden;
}

.quick-actions strong,
.quick-actions small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-actions strong {
  color: var(--text-primary);
  font-size: 12px;
}

.quick-actions small {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

@media (max-width: 1280px) {
  .workbench-page {
    grid-template-columns: 280px minmax(0, 1fr);
  }

  .inspector-panel {
    display: none;
  }

  .run-facts {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .workbench-page {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
    overflow: auto;
  }

  .threads-panel {
    max-height: 360px;
  }

  .workbench-main {
    overflow: visible;
  }

  .step-row {
    --step-action-width: 100%;
    grid-template-columns: 54px 20px minmax(0, 1fr);
  }

  .step-row__content {
    grid-template-columns: 30px minmax(0, 1fr);
    gap: 10px;
    padding: 10px 12px;
  }

  .step-icon {
    width: 30px;
    height: 30px;
  }

  .step-row header {
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 6px;
    overflow: hidden;
  }

  .step-row h3 {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .step-row__actions {
    grid-column: 2;
    justify-self: stretch;
    justify-items: stretch;
    width: 100%;
    max-width: none;
  }

  .step-row__status {
    justify-content: flex-start;
  }

  .approval-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .skill-approval-card dl {
    grid-template-columns: minmax(0, 1fr);
  }

  .status-strip {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 6px 8px;
    min-height: 0;
    padding-block: 8px;
  }

  .status-strip__main {
    grid-column: 1;
  }

  .status-strip__meta {
    grid-column: 1;
    gap: 10px;
    margin-left: 0;
    font-size: 11px;
  }

  .status-strip__meta span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .status-strip__action {
    grid-row: 1 / span 2;
    grid-column: 2;
    align-self: center;
    min-width: 0;
  }
}
</style>
