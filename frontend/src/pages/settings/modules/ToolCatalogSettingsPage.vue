<script setup lang="ts">
import {
  Copy,
  GitBranch,
  Package,
  Play,
  Plus,
  RefreshCcw,
  Shield,
  Wrench,
  X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { useI18n } from "@/shared/i18n";
import type { UiTableColumn } from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  bindToolCredentialRequirement,
  createToolSource,
  deleteToolSource,
  disableToolFunction,
  disableToolSource,
  enableToolFunction,
  executeToolRun,
  getToolAccessCredentialContext,
  listToolFunctions,
  listToolProviderBackends,
  listToolSourceDiscoveryRuns,
  listToolSources,
  listToolRuns,
  listTools,
  openToolCliOutputStream,
  refreshToolSource,
  restoreToolSource,
  updateToolFunctionPolicy,
  updateToolSource,
  type BindToolCredentialRequirementRequest,
  type ToolAccessCredentialBindingPayload,
  type ToolAccessCredentialRequirementPayload,
  type ToolApiPayload,
  type ToolCredentialRequirementApiPayload,
  type ToolCredentialRequirementSetApiPayload,
  type ToolEventConsoleRecord,
  type ToolFunctionApiPayload,
  type ToolProviderBackendApiPayload,
  type ToolRunApiPayload,
  type ToolSourceApiPayload,
  type ToolSourceDiscoveryRunApiPayload,
  type ToolSourceWriteApiRequest,
} from "../ownerApis/toolCatalog";

type TableRow = Record<string, string | number | null>;
type TableColumn = string | UiTableColumn;
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";
type CatalogView = "functions" | "sources" | "backends" | "runs";

const { t } = useI18n();

interface ToolCredentialSlotView {
  key: string;
  requirementSetId: string;
  requirement: ToolCredentialRequirementApiPayload;
  accessRequirement: ToolAccessCredentialRequirementPayload | null;
}

interface CredentialBindingCompatibility {
  compatible: boolean;
  reason: string;
}

type SourceEditorMode = "create" | "edit";
type SourceEditorKindInput = "openapi" | "mcp" | "cli";

interface SourceEditorState {
  mode: SourceEditorMode;
  sourceId: string;
  kind: SourceEditorKindInput;
  displayName: string;
  description: string;
  providerName: string;
  specLocation: string;
  baseUrl: string;
  commandText: string;
  allowedSubcommands: string;
  deniedFlags: string;
  workingDirectory: string;
  allowedRoots: string;
  outputLimitBytes: string;
  timeoutSeconds: string;
  maxConcurrency: string;
  defaultEffectIds: string;
  runtimeRequirements: string;
}

interface FunctionPolicyDraft {
  trustLevel: string;
  approvalMode: string;
  requiresApproval: "" | "true" | "false";
  credentialBindingOverrides: string;
  requiredEffectOverrides: string;
}

interface CliConsoleLine {
  id: string;
  stream: string;
  text: string;
  status: string | null;
  exitCode: number | null;
  createdAt: string | null;
}

const tools = ref<ToolApiPayload[]>([]);
const toolFunctions = ref<ToolFunctionApiPayload[]>([]);
const providerBackends = ref<ToolProviderBackendApiPayload[]>([]);
const sources = ref<ToolSourceApiPayload[]>([]);
const selectedSourceId = ref<string | null>(null);
const selectedSourceHistory = ref<ToolSourceDiscoveryRunApiPayload[]>([]);
const selectedToolId = ref<string | null>(null);
const selectedRuns = ref<ToolRunApiPayload[]>([]);
const accessCredentialBindings = ref<ToolAccessCredentialBindingPayload[]>([]);
const accessCredentialRequirements = ref<ToolAccessCredentialRequirementPayload[]>([]);
const isLoading = ref(false);
const runsLoading = ref(false);
const sourceHistoryLoading = ref(false);
const accessContextLoading = ref(false);
const savingCredentialSlotKey = ref<string | null>(null);
const toolActionId = ref<string | null>(null);
const sourceActionId = ref<string | null>(null);
const loadError = ref<string | null>(null);
const runsError = ref<string | null>(null);
const sourceHistoryError = ref<string | null>(null);
const accessContextError = ref<string | null>(null);
const actionMessage = ref<string | null>(null);
const actionError = ref<string | null>(null);
const activeCatalogView = ref<CatalogView>("functions");
const searchQuery = ref("");
const functionSourceFilter = ref("all");
const functionStatusFilter = ref("all");
const runtimeKindFilter = ref("all");
const functionEnabledFilter = ref("all");
const credentialFilter = ref("all");
const credentialBindingDrafts = ref<Record<string, string>>({});
const sourceEditorOpen = ref(false);
const sourceEditorSaving = ref(false);
const sourceEditorError = ref<string | null>(null);
const sourceEditor = ref<SourceEditorState>(emptySourceEditor());
const testRunArguments = ref<Record<string, string>>({});
const testRunMode = ref("inline");
const testRunStrategy = ref("async");
const testRunEnvironment = ref("local");
const testRunSubmitting = ref(false);
const testRunError = ref<string | null>(null);
const lastTestRun = ref<ToolRunApiPayload | null>(null);
const cliConsoleProcessId = ref<string | null>(null);
const cliConsoleLines = ref<CliConsoleLine[]>([]);
const cliConsoleStatus = ref<string | null>(null);
const cliConsoleError = ref<string | null>(null);
const stopCliConsoleStream = ref<(() => void) | null>(null);
const functionPolicyDraft = ref<FunctionPolicyDraft>(emptyFunctionPolicyDraft());
const functionPolicySaving = ref(false);
const functionPolicyError = ref<string | null>(null);

const sourceCount = computed(() => sources.value.length);
const activeSourceCount = computed(() => sources.value.filter((source) => normalizedText(source.status) === "active").length);
const sourceIssueCount = computed(() =>
  sources.value.filter((source) => ["error", "disabled", "deleted"].includes(normalizedText(source.status))).length,
);
const activeBackendCount = computed(() =>
  providerBackends.value.filter((backend) => backend.enabled && normalizedText(backend.status) === "active").length,
);
const backendIssueCount = computed(() =>
  providerBackends.value.filter((backend) =>
    !backend.enabled
    || ["error", "disabled", "deleted"].includes(normalizedText(backend.status))
    || !providerBackendReady(backend),
  ).length,
);
const disabledCount = computed(() => toolFunctions.value.filter((tool) => !tool.enabled).length);

const toolById = computed(() => {
  const lookup = new Map<string, ToolApiPayload>();
  for (const tool of tools.value) {
    lookup.set(tool.id, tool);
  }
  return lookup;
});

const sourceById = computed(() => {
  const lookup = new Map<string, ToolSourceApiPayload>();
  for (const source of sources.value) {
    lookup.set(source.source_id, source);
  }
  return lookup;
});

const selectedTool = computed(() =>
  tools.value.find((tool) => tool.id === selectedToolId.value) ?? null,
);
const functionById = computed(() => {
  const lookup = new Map<string, ToolFunctionApiPayload>();
  for (const item of toolFunctions.value) {
    lookup.set(item.function_id, item);
  }
  return lookup;
});
const selectedFunction = computed(() =>
  selectedToolId.value ? functionById.value.get(selectedToolId.value) ?? null : null,
);
const selectedOwnerTool = computed<ToolApiPayload | null>(() =>
  selectedFunction.value
    ? toolContractFromFunction(selectedFunction.value)
    : selectedTool.value,
);
const selectedSource = computed(() =>
  sources.value.find((source) => source.source_id === selectedSourceId.value) ?? null,
);
const selectedSourceWritable = computed(() =>
  selectedSource.value ? isWritableSource(selectedSource.value) : false,
);
const selectedFunctionSource = computed(() =>
  selectedFunction.value
    ? sources.value.find((source) => source.source_id === selectedFunction.value?.source_id) ?? null
    : null,
);
const selectedFunctionSourceWritable = computed(() =>
  selectedFunctionSource.value ? isWritableSource(selectedFunctionSource.value) : false,
);
const sourceEditorTitle = computed(() =>
  sourceEditor.value.mode === "create"
    ? t("settings.toolCatalog.sourceEditor.newTitle")
    : t("settings.toolCatalog.sourceEditor.editTitle"),
);
const selectedTitle = computed(() =>
  selectedOwnerTool.value?.name
  ?? selectedFunction.value?.name
  ?? selectedOwnerTool.value?.id
  ?? selectedFunction.value?.function_id
  ?? t("settings.toolCatalog.noToolSelected"),
);
const selectedStatusTone = computed<StatusTone>(() => {
  if (selectedFunction.value && normalizedText(selectedFunction.value.status) !== "active") {
    return toneForStatus(selectedFunction.value.status);
  }
  return selectedOwnerTool.value?.enabled === false ? "danger" : "success";
});
const selectedFunctionManaged = computed(() => selectedFunction.value !== null);
const selectedCredentialSlots = computed<ToolCredentialSlotView[]>(() => {
  if (!selectedOwnerTool.value) return [];
  return flattenCredentialSlots(selectedOwnerTool.value.credential_requirements ?? []).map((slot) => ({
    ...slot,
    accessRequirement: accessRequirementForSlot(slot.requirement),
  }));
});
const selectedCredentialSlotRows = computed<TableRow[]>(() =>
  selectedCredentialSlots.value.map((slot) => {
    const requirement = slot.requirement;
    const bindingId = currentCredentialBindingId(slot);
    const binding = bindingId ? credentialBindingById(bindingId) : null;
    return {
      Slot: textValue(requirement.slot.display_name ?? requirement.slot.slot),
      Provider: textValue(requirement.provider),
      Kind: titleize(requirement.slot.expected_kind),
      Transport: titleize(requirement.transport),
      Required: yesNo(requirement.slot.required),
      Binding: bindingId ? maskedBindingLabel(bindingId, binding) : "-",
      Readiness: credentialSlotReadinessLabel(slot),
      Setup: credentialSlotSetupLabel(slot),
    };
  }),
);
const accessCredentialBindingCount = computed(() => accessCredentialBindings.value.length);
const requiredCredentialSlotCount = computed(() =>
  selectedCredentialSlots.value.filter((slot) => slot.requirement.slot.required).length,
);
const readyCredentialSlotCount = computed(() =>
  selectedCredentialSlots.value.filter((slot) => credentialSlotReady(slot)).length,
);
const selectedToolParameters = computed(() => selectedOwnerTool.value?.parameters ?? []);
const supportedModes = computed(() =>
  nonEmptyStrings(selectedOwnerTool.value?.execution_support.supported_modes, ["inline"]),
);
const supportedStrategies = computed(() =>
  nonEmptyStrings(selectedOwnerTool.value?.execution_support.supported_strategies, ["async"]),
);
const supportedEnvironments = computed(() =>
  nonEmptyStrings(selectedOwnerTool.value?.execution_support.supported_environments, ["local"]),
);
const selectedRuntimeRunnable = computed(() =>
  Boolean(
    selectedTool.value
    && selectedOwnerTool.value?.enabled
    && (!selectedFunction.value || normalizedText(selectedFunction.value.status) === "active")
    && (!selectedFunctionSource.value || normalizedText(selectedFunctionSource.value.status) === "active"),
  ),
);
const canSubmitTestRun = computed(() =>
  selectedRuntimeRunnable.value && !testRunSubmitting.value,
);
const lastTestRunTone = computed<StatusTone>(() => toneForStatus(lastTestRun.value?.status));
const cliConsoleText = computed(() =>
  cliConsoleLines.value
    .map((line) => {
      if (line.stream === "status") {
        const suffix = line.exitCode === null ? "" : ` · exit ${line.exitCode}`;
        return `[status] ${line.status ?? "unknown"}${suffix}`;
      }
      return `[${line.stream}] ${line.text}`;
    })
    .join("\n")
    .trim(),
);

const sourceOptions = computed(() =>
  sources.value
    .map((source) => ({
      id: source.source_id,
      label: source.display_name || source.source_id,
    }))
    .sort((left, right) => left.label.localeCompare(right.label)),
);

const functionStatusOptions = computed(() =>
  uniqueStrings(toolFunctions.value.map((item) => normalizedText(item.status)).filter(Boolean)),
);

const runtimeKindOptions = computed(() =>
  uniqueStrings(toolFunctions.value.map((item) => normalizedText(item.runtime_kind)).filter(Boolean)),
);

const filteredFunctions = computed(() => {
  const query = normalizedText(searchQuery.value);
  return toolFunctions.value.filter((item) => {
    const tool = toolContractFromFunction(item);
    const source = sourceById.value.get(item.source_id) ?? null;
    if (functionSourceFilter.value !== "all" && item.source_id !== functionSourceFilter.value) return false;
    if (functionStatusFilter.value !== "all" && normalizedText(item.status) !== functionStatusFilter.value) return false;
    if (runtimeKindFilter.value !== "all" && normalizedText(item.runtime_kind) !== runtimeKindFilter.value) return false;
    if (functionEnabledFilter.value === "enabled" && !item.enabled) return false;
    if (functionEnabledFilter.value === "disabled" && item.enabled) return false;
    if (!credentialFilterMatches(tool, credentialFilter.value)) return false;
    if (!query) return true;
    const haystack = [
      item.function_id,
      item.name,
      item.description,
      item.source_id,
      source?.display_name,
      tool?.kind,
      tool?.runtime_key,
    ].map((value) => textValue(value, "").toLowerCase()).join(" ");
    return haystack.includes(query);
  });
});

const functionRows = computed<TableRow[]>(() =>
  filteredFunctions.value.map((item) => {
    const tool = toolById.value.get(item.function_id) ?? null;
    const source = sourceById.value.get(item.source_id) ?? null;
    return {
      __row_id: item.function_id,
      Name: textValue(item.name, item.function_id),
      "Function ID": item.function_id,
      Source: textValue(source?.display_name, item.source_id),
      Runtime: titleize(item.runtime_kind),
      Enabled: yesNo(item.enabled),
      Status: titleize(item.status),
      Credentials: credentialReadinessLabel(tool),
      Updated: textValue(item.updated_at ?? item.last_seen_at),
      Action: "Open",
    };
  }),
);

const backendRows = computed<TableRow[]>(() => {
  return providerBackends.value.map((backend) => ({
    __row_id: backend.backend_id,
    Backend: textValue(backend.display_name, backend.backend_id),
    "Backend ID": backend.backend_id,
    Capability: titleize(backend.capability),
    Source: textValue(sourceById.value.get(backend.source_id)?.display_name, backend.source_id),
    Credential: providerBackendCredentialLabel(backend),
    Readiness: providerBackendReadinessLabel(backend),
    Runtime: providerBackendRuntimeLabel(backend),
    Status: backend.enabled ? titleize(backend.status) : t("text.disabled"),
    Updated: textValue(backend.updated_at),
    Action: "Open",
  }));
});

const catalogColumns = computed<TableColumn[]>(() => {
  if (activeCatalogView.value === "sources") {
    return [
      column("Source", "table.source"),
      column("Source ID", "settings.toolCatalog.table.sourceId"),
      column("Kind", "table.kind"),
      column("Status", "table.status"),
      column("Revision", "settings.toolCatalog.table.revision"),
      column("Discovery", "settings.toolCatalog.table.discovery"),
      column("Last Discovery", "settings.toolCatalog.table.lastDiscovery"),
      column("Action", "table.action"),
    ];
  }
  if (activeCatalogView.value === "backends") {
    return [
      column("Backend", "table.backend"),
      column("Backend ID", "settings.toolCatalog.table.backendId"),
      column("Capability", "settings.toolCatalog.table.capability"),
      column("Source", "table.source"),
      column("Credential", "settings.toolCatalog.metric.credentials"),
      column("Readiness", "table.readiness"),
      column("Runtime", "settings.toolCatalog.table.runtime"),
      column("Status", "table.status"),
      column("Updated", "settings.toolCatalog.table.updated"),
      column("Action", "table.action"),
    ];
  }
  if (activeCatalogView.value === "runs") {
    return [
      column("Run ID", "table.runId"),
      column("Tool ID", "settings.toolCatalog.table.toolId"),
      column("Catalog", "settings.toolCatalog.table.catalogVersion"),
      column("Status", "table.status"),
      column("Mode", "table.mode"),
      column("Strategy", "table.strategy"),
      column("Environment", "table.environment"),
      column("Attempts", "settings.toolCatalog.table.attempts"),
      column("Created At", "table.createdAt"),
      column("Action", "table.action"),
    ];
  }
  return [
    column("Name", "table.name"),
    column("Function ID", "settings.toolCatalog.table.functionId"),
    column("Source", "table.source"),
    column("Runtime", "settings.toolCatalog.table.runtime"),
    column("Enabled", "settings.toolCatalog.table.enabled"),
    column("Status", "table.status"),
    column("Credentials", "settings.toolCatalog.metric.credentials"),
    column("Updated", "settings.toolCatalog.table.updated"),
    column("Action", "table.action"),
  ];
});

const catalogRows = computed<TableRow[]>(() => {
  if (activeCatalogView.value === "sources") return sourceRows.value;
  if (activeCatalogView.value === "backends") return backendRows.value;
  if (activeCatalogView.value === "runs") return runRows.value;
  return functionRows.value;
});

const sourceHistoryColumns = computed<TableColumn[]>(() => [
  column("Time", "table.time"),
  column("Status", "table.status"),
  column("Functions", "settings.toolCatalog.metric.functions"),
  column("Providers", "table.providers"),
  column("Revision", "settings.toolCatalog.table.revision"),
  column("Error", "table.error"),
]);

const drawerRunColumns = computed<TableColumn[]>(() => [
  column("Run ID", "table.runId"),
  column("Status", "table.status"),
  column("Catalog", "settings.toolCatalog.table.catalogVersion"),
  column("Mode", "table.mode"),
  column("Strategy", "table.strategy"),
  column("Attempts", "settings.toolCatalog.table.attempts"),
  column("Created At", "table.createdAt"),
]);

const catalogSelectedRowId = computed(() => {
  if (activeCatalogView.value === "sources") return selectedSourceId.value;
  if (activeCatalogView.value === "runs") return lastTestRun.value?.id ?? null;
  if (activeCatalogView.value === "functions") return selectedFunction.value?.function_id ?? selectedToolId.value;
  return null;
});

const catalogEmptyMessage = computed(() => {
  if (isLoading.value) return t("settings.toolCatalog.state.loadingCatalog");
  if (loadError.value) return loadError.value;
  if (activeCatalogView.value === "sources") return t("settings.toolCatalog.state.noSources");
  if (activeCatalogView.value === "backends") return t("settings.toolCatalog.state.noBackends");
  if (activeCatalogView.value === "runs") return t("settings.toolCatalog.state.noRuns");
  return t("settings.toolCatalog.state.noFunctions");
});

const activeFunctionCount = computed(() =>
  toolFunctions.value.filter((item) => item.enabled && normalizedText(item.status) === "active").length,
);

const credentialIssueCount = computed(() =>
  toolFunctions.value.filter((item) =>
    credentialFilterMatches(toolContractFromFunction(item), "missing")
    || credentialFilterMatches(toolContractFromFunction(item), "partial"),
  ).length,
);

const sourceDiscoveryIssueCount = computed(() =>
  sources.value.filter((source) =>
    ["failed", "error"].includes(normalizedText(source.last_discovery_status))
    || ["error", "disabled", "deleted"].includes(normalizedText(source.status)),
  ).length,
);

const selectedFunctionSchemaText = computed(() =>
  formatPayload(selectedFunction.value?.input_schema ?? selectedTool.value?.parameters ?? {}),
);

const selectedSourceConfigText = computed(() =>
  formatPayload(selectedSource.value?.config ?? {}),
);

const drawerMode = computed<CatalogView>(() =>
  activeCatalogView.value === "sources" || !selectedTool.value ? activeCatalogView.value : "functions",
);

const runRows = computed<TableRow[]>(() =>
  [...selectedRuns.value]
    .sort((left, right) => timestampValue(right.created_at) - timestampValue(left.created_at))
    .slice(0, 8)
    .map((run) => ({
      __row_id: run.id,
      "Run ID": run.id,
      "Tool ID": run.tool_id,
      Catalog: runCatalogVersionLabel(run),
      Status: titleize(run.status),
      Mode: titleize(run.target.mode),
      Strategy: titleize(run.target.strategy),
      Environment: titleize(run.target.environment),
      Attempts: `${run.attempt_count}/${run.max_attempts}`,
      "Created At": textValue(run.created_at),
      "Completed At": textValue(run.completed_at),
      Action: "Open",
    })),
);

const sourceRows = computed<TableRow[]>(() =>
  sources.value.map((source) => ({
    __row_id: source.source_id,
    Source: textValue(source.display_name, source.source_id),
    "Source ID": source.source_id,
    Kind: titleize(source.kind),
    Status: titleize(source.status),
    Revision: source.revision,
    Discovery: titleize(source.last_discovery_status, "Never"),
    "Last Discovery": textValue(source.last_discovered_at),
    Action: "Open",
  })),
);

const selectedSourceHistoryRows = computed<TableRow[]>(() =>
  selectedSourceHistory.value.map((run) => ({
    Time: textValue(run.discovered_at),
    Status: titleize(run.status),
    Functions: run.function_count,
    Providers: run.provider_backend_count,
    Revision: run.source_revision,
    Error: textValue(run.error_message),
  })),
);

onMounted(() => {
  void loadToolCatalog();
});

onUnmounted(() => {
  closeCliConsoleStream();
});

watch([selectedToolId, accessCredentialRequirements], () => {
  syncCredentialBindingDrafts();
});

watch(selectedFunction, () => {
  syncFunctionPolicyDraft();
}, { immediate: true });

watch(selectedToolId, () => {
  resetToolRunDraft();
});

async function loadToolCatalog(
  preferredToolId = selectedToolId.value,
  preferredSourceId = selectedSourceId.value,
): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [ownerTools, ownerFunctions, ownerProviderBackends, ownerSources] = await Promise.all([
      listTools(),
      listToolFunctions(),
      listToolProviderBackends(),
      listToolSources(),
    ]);
    tools.value = ownerTools;
    toolFunctions.value = ownerFunctions;
    providerBackends.value = ownerProviderBackends;
    sources.value = ownerSources;

    const nextToolId =
      preferredToolId && ownerTools.some((tool) => tool.id === preferredToolId)
        ? preferredToolId
        : ownerTools[0]?.id ?? null;
    const nextSourceId =
      preferredSourceId && ownerSources.some((source) => source.source_id === preferredSourceId)
        ? preferredSourceId
        : ownerSources[0]?.source_id ?? null;
    selectedToolId.value = nextToolId;
    selectedSourceId.value = nextSourceId;
    await Promise.all([
      loadAccessCredentialContext(),
      loadRunsForTool(nextToolId),
      loadSourceHistory(nextSourceId),
    ]);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    tools.value = [];
    toolFunctions.value = [];
    providerBackends.value = [];
    sources.value = [];
    selectedToolId.value = null;
    selectedSourceId.value = null;
    selectedRuns.value = [];
    selectedSourceHistory.value = [];
  } finally {
    isLoading.value = false;
  }
}

async function loadRunsForTool(toolId: string | null): Promise<void> {
  selectedRuns.value = [];
  runsError.value = null;
  if (!toolId) return;
  runsLoading.value = true;
  try {
    selectedRuns.value = await listToolRuns(toolId);
  } catch (error) {
    runsError.value = error instanceof Error ? error.message : String(error);
  } finally {
    runsLoading.value = false;
  }
}

async function loadSourceHistory(sourceId: string | null): Promise<void> {
  selectedSourceHistory.value = [];
  sourceHistoryError.value = null;
  if (!sourceId) return;
  sourceHistoryLoading.value = true;
  try {
    selectedSourceHistory.value = await listToolSourceDiscoveryRuns(sourceId, 12);
  } catch (error) {
    sourceHistoryError.value = error instanceof Error ? error.message : String(error);
  } finally {
    sourceHistoryLoading.value = false;
  }
}

async function loadAccessCredentialContext(): Promise<void> {
  accessContextLoading.value = true;
  accessContextError.value = null;
  try {
    const context = await getToolAccessCredentialContext();
    accessCredentialBindings.value = context.credential_bindings ?? [];
    accessCredentialRequirements.value = context.credential_requirements ?? [];
  } catch (error) {
    accessCredentialBindings.value = [];
    accessCredentialRequirements.value = [];
    accessContextError.value = error instanceof Error ? error.message : String(error);
  } finally {
    accessContextLoading.value = false;
    syncCredentialBindingDrafts();
  }
}

function selectToolResource(row: unknown): void {
  const toolId = rowValue(row, "ID");
  if (toolId && toolId !== selectedToolId.value) {
    selectedToolId.value = toolId;
    void loadRunsForTool(toolId);
  }
}

function selectSourceResource(row: unknown): void {
  const sourceId = rowValue(row, "Source ID");
  if (sourceId && sourceId !== selectedSourceId.value) {
    selectedSourceId.value = sourceId;
    void loadSourceHistory(sourceId);
  }
}

function selectFunctionResource(row: unknown): void {
  const functionId = rowValue(row, "Function ID") ?? rowValue(row, "ID");
  if (!functionId) return;
  const toolFunction = functionById.value.get(functionId) ?? null;
  selectedToolId.value = functionId;
  if (toolFunction?.source_id) {
    selectedSourceId.value = toolFunction.source_id;
    void loadSourceHistory(toolFunction.source_id);
  }
  void loadRunsForTool(functionId);
}

function selectRunResource(row: unknown): void {
  const toolId = rowValue(row, "Tool ID");
  if (toolId && toolId !== selectedToolId.value) {
    selectedToolId.value = toolId;
    void loadRunsForTool(toolId);
  }
}

function selectCatalogRow(row: unknown): void {
  if (activeCatalogView.value === "sources") {
    selectSourceResource(row);
    return;
  }
  if (activeCatalogView.value === "runs") {
    selectRunResource(row);
    return;
  }
  if (activeCatalogView.value === "functions") {
    selectFunctionResource(row);
  }
}

function refreshSelectedRuns(): void {
  void loadRunsForTool(selectedToolId.value);
}

function focusTestRunPanel(): void {
  document.getElementById("tool-test-run-panel")?.scrollIntoView({
    behavior: "smooth",
    block: "center",
  });
}

async function toggleSelectedToolFunction(): Promise<void> {
  const toolFunction = selectedFunction.value;
  if (!toolFunction) return;
  const nextEnabled = !toolFunction.enabled;
  toolActionId.value = `${toolFunction.function_id}:${nextEnabled ? "enable" : "disable"}`;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const result = nextEnabled
      ? await enableToolFunction(toolFunction.function_id)
      : await disableToolFunction(toolFunction.function_id);
    actionMessage.value = t("settings.toolCatalog.notice.functionToggled", {
      name: result.name || result.function_id,
      status: result.enabled ? t("settings.toolCatalog.status.enabled") : t("settings.toolCatalog.status.disabled"),
    });
    await loadToolCatalog(toolFunction.function_id, selectedSourceId.value);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    toolActionId.value = null;
  }
}

async function refreshSelectedSource(): Promise<void> {
  const sourceId = selectedSourceId.value;
  if (!sourceId) return;
  sourceActionId.value = `${sourceId}:refresh`;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const result = await refreshToolSource(sourceId);
    const count = result.discovery?.function_count ?? 0;
    actionMessage.value = result.skipped
      ? t("settings.toolCatalog.notice.sourceRefreshSkipped", { source: sourceId, status: result.source.status })
      : t("settings.toolCatalog.notice.sourceRefreshed", { source: sourceId, count });
    await loadToolCatalog(selectedToolId.value, sourceId);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    sourceActionId.value = null;
  }
}

async function toggleSelectedSource(): Promise<void> {
  const source = selectedSource.value;
  if (!source) return;
  const sourceId = source.source_id;
  const canRestore = ["disabled", "deleted"].includes(normalizedText(source.status));
  sourceActionId.value = `${sourceId}:${canRestore ? "restore" : "disable"}`;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const result = canRestore
      ? await restoreToolSource(sourceId)
      : await disableToolSource(sourceId);
    actionMessage.value = t("settings.toolCatalog.notice.sourceStatusChanged", {
      source: result.display_name || result.source_id,
      status: result.status,
    });
    await loadToolCatalog(selectedToolId.value, sourceId);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    sourceActionId.value = null;
  }
}

async function deleteSelectedSource(): Promise<void> {
  const source = selectedSource.value;
  if (!source) return;
  const sourceId = source.source_id;
  if (!window.confirm(t("settings.toolCatalog.confirm.deleteSource", { source: sourceId }))) {
    return;
  }
  sourceActionId.value = `${sourceId}:delete`;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const result = await deleteToolSource(sourceId);
    actionMessage.value = t("settings.toolCatalog.notice.sourceStatusChanged", {
      source: result.display_name || result.source_id,
      status: result.status,
    });
    await loadToolCatalog(selectedToolId.value, null);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    sourceActionId.value = null;
  }
}

function openSourceEditor(
  mode: SourceEditorMode,
  source: ToolSourceApiPayload | null = selectedSource.value,
): void {
  actionError.value = null;
  sourceEditorError.value = null;
  if (mode === "edit") {
    if (!source) {
      actionError.value = t("settings.toolCatalog.error.selectSourceBeforeEdit");
      return;
    }
    if (!isWritableSource(source)) {
      actionError.value = t("settings.toolCatalog.error.sourceNotWritable");
      return;
    }
    selectedSourceId.value = source.source_id;
    sourceEditor.value = editorStateFromSource(source);
  } else {
    sourceEditor.value = emptySourceEditor();
  }
  sourceEditorOpen.value = true;
}

function openSelectedFunctionSourceEditor(): void {
  const source = selectedFunctionSource.value;
  if (!source) {
    actionError.value = t("settings.toolCatalog.error.functionSourceNotFound");
    return;
  }
  openSourceEditor("edit", source);
}

function closeSourceEditor(): void {
  if (sourceEditorSaving.value) return;
  sourceEditorOpen.value = false;
  sourceEditorError.value = null;
}

async function saveSourceEditor(): Promise<void> {
  sourceEditorSaving.value = true;
  sourceEditorError.value = null;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const payload = buildSourceEditorPayload(sourceEditor.value);
    const result = sourceEditor.value.mode === "create"
      ? await createToolSource(payload)
      : await updateToolSource(payload.source_id, payload);
    actionMessage.value = t("settings.toolCatalog.notice.sourceSaved", {
      source: result.display_name || result.source_id,
    });
    sourceEditorOpen.value = false;
    await loadToolCatalog(selectedToolId.value, result.source_id);
  } catch (error) {
    sourceEditorError.value = error instanceof Error ? error.message : String(error);
  } finally {
    sourceEditorSaving.value = false;
  }
}

async function saveCredentialSlot(slot: ToolCredentialSlotView): Promise<void> {
  const selectedBindingId = (credentialBindingDrafts.value[slot.key] ?? "").trim();
  const compatibility = credentialBindingCompatibilityForSlot(slot.requirement, selectedBindingId);
  actionMessage.value = null;
  actionError.value = null;
  if (!selectedOwnerTool.value || !selectedBindingId) {
    actionError.value = t("settings.toolCatalog.error.selectCredentialBeforeSave");
    return;
  }
  if (!compatibility.compatible) {
    actionError.value = compatibility.reason;
    return;
  }
  savingCredentialSlotKey.value = slot.key;
  try {
    const payload = credentialBindingActionPayload(selectedOwnerTool.value.id, slot, selectedBindingId);
    const result = await bindToolCredentialRequirement(payload);
    actionMessage.value = t("settings.toolCatalog.notice.credentialBound", {
      slot: slot.requirement.slot.slot,
      binding: selectedBindingId,
      audit: result.audit_ref ? ` (${result.audit_ref})` : "",
    });
    await loadAccessCredentialContext();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    savingCredentialSlotKey.value = null;
  }
}

async function submitToolTestRun(): Promise<void> {
  const tool = selectedTool.value;
  if (!tool) return;
  testRunSubmitting.value = true;
  testRunError.value = null;
  closeCliConsoleStream();
  cliConsoleProcessId.value = null;
  cliConsoleLines.value = [];
  cliConsoleStatus.value = null;
  cliConsoleError.value = null;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const run = await executeToolRun(tool.id, {
      arguments: buildTestRunArguments(tool.parameters),
      mode: testRunMode.value,
      strategy: testRunStrategy.value,
      environment: testRunEnvironment.value,
    });
    lastTestRun.value = run;
    attachCliConsoleFromRun(run);
    actionMessage.value = t("settings.toolCatalog.notice.runSubmitted", { run: run.id, status: run.status });
    await loadRunsForTool(tool.id);
  } catch (error) {
    testRunError.value = error instanceof Error ? error.message : String(error);
  } finally {
    testRunSubmitting.value = false;
  }
}

function attachCliConsoleFromRun(run: ToolRunApiPayload): void {
  const outputPayload = normalizedRecord(run.output_payload);
  const processId = stringFromUnknown(outputPayload.process_id);
  if (!processId) return;
  cliConsoleProcessId.value = processId;
  appendCliOutputLine({
    stream: "stdout",
    text: stringFromUnknown(outputPayload.stdout),
    status: stringFromUnknown(outputPayload.status),
    exitCode: numberFromUnknown(outputPayload.exit_code),
    createdAt: run.created_at,
    idHint: `${run.id}:stdout:${outputPayload.next_stdout_offset ?? 0}`,
  });
  appendCliOutputLine({
    stream: "stderr",
    text: stringFromUnknown(outputPayload.stderr),
    status: stringFromUnknown(outputPayload.status),
    exitCode: numberFromUnknown(outputPayload.exit_code),
    createdAt: run.created_at,
    idHint: `${run.id}:stderr:${outputPayload.next_stderr_offset ?? 0}`,
  });
  cliConsoleStatus.value = stringFromUnknown(outputPayload.status) || run.status;
  stopCliConsoleStream.value = openToolCliOutputStream(processId, {
    snapshot: (snapshot) => {
      for (const record of snapshot.records ?? []) appendCliEventRecord(record);
    },
    event: appendCliEventRecord,
    error: () => {
      cliConsoleError.value = t("settings.toolCatalog.error.cliConsoleStream");
    },
  });
}

function appendCliEventRecord(record: ToolEventConsoleRecord): void {
  const payload = normalizedRecord(record.source_payload);
  const processId = stringFromUnknown(payload.process_id);
  if (cliConsoleProcessId.value && processId && processId !== cliConsoleProcessId.value) return;
  const stream = stringFromUnknown(payload.stream) || "stdout";
  const status = stringFromUnknown(payload.status);
  const exitCode = numberFromUnknown(payload.exit_code);
  cliConsoleStatus.value = status || cliConsoleStatus.value;
  appendCliOutputLine({
    stream,
    text: stringFromUnknown(payload.text),
    status,
    exitCode,
    createdAt: record.created_at ?? null,
    idHint: `${record.event_id}:${stream}:${payload.offset ?? ""}:${payload.next_offset ?? ""}`,
  });
  if (stream === "status" || status !== "running") {
    closeCliConsoleStream();
  }
}

function appendCliOutputLine(input: {
  stream: string;
  text: string;
  status: string | null;
  exitCode: number | null;
  createdAt: string | null;
  idHint: string;
}): void {
  if (!input.text && input.stream !== "status") return;
  if (cliConsoleLines.value.some((line) => line.id === input.idHint)) return;
  cliConsoleLines.value = [
    ...cliConsoleLines.value,
    {
      id: input.idHint,
      stream: input.stream,
      text: input.text,
      status: input.status,
      exitCode: input.exitCode,
      createdAt: input.createdAt,
    },
  ].slice(-120);
}

function closeCliConsoleStream(): void {
  stopCliConsoleStream.value?.();
  stopCliConsoleStream.value = null;
}

async function saveFunctionPolicy(): Promise<void> {
  const toolFunction = selectedFunction.value;
  if (!toolFunction) return;
  functionPolicySaving.value = true;
  functionPolicyError.value = null;
  actionMessage.value = null;
  actionError.value = null;
  try {
    const result = await updateToolFunctionPolicy(
      toolFunction.function_id,
      buildFunctionPolicyPayload(toolFunction),
    );
    actionMessage.value = t("settings.toolCatalog.notice.policySaved", {
      name: result.name || result.function_id,
    });
    await loadToolCatalog(selectedToolId.value, selectedSourceId.value);
  } catch (error) {
    functionPolicyError.value = error instanceof Error ? error.message : String(error);
  } finally {
    functionPolicySaving.value = false;
  }
}

function toolContractFromFunction(toolFunction: ToolFunctionApiPayload): ToolApiPayload {
  return {
    id: toolFunction.function_id,
    name: toolFunction.name,
    description: toolFunction.description,
    kind: toolFunction.kind || "function",
    parameters: toolFunction.parameters ?? [],
    tags: toolFunction.tags ?? [],
    required_effect_ids: toolFunction.required_effect_ids ?? [],
    access_requirements: flattenRequirementSets(toolFunction.access_requirement_sets ?? []),
    access_requirement_sets: toolFunction.access_requirement_sets ?? [],
    runtime_requirement_sets: toolFunction.runtime_requirement_sets ?? [],
    context_requirements: toolFunction.context_requirements ?? [],
    credential_requirements: toolFunction.credential_requirements ?? [],
    execution_policy: toolFunction.execution_policy ?? {
      timeout_seconds: 30,
      requires_confirmation: false,
      mutates_state: false,
    },
    execution_support: toolFunction.execution_support ?? {
      supported_modes: ["inline"],
      supported_strategies: ["async"],
      supported_environments: ["local"],
    },
    definition_origin: toolFunction.definition_origin || "local_discovery",
    runtime_key: toolFunction.runtime_key,
    enabled: toolFunction.enabled,
  };
}

function flattenRequirementSets(value: string[][]): string[] {
  return [...new Set(value.flatMap((item) => item))].filter(Boolean);
}

function flattenCredentialSlots(
  sets: ToolCredentialRequirementSetApiPayload[],
): ToolCredentialSlotView[] {
  return sets.flatMap((requirementSet) =>
    requirementSet.requirements.map((requirement) => ({
      key: credentialSlotKey(requirement),
      requirementSetId: requirementSet.requirement_set_id,
      requirement,
      accessRequirement: null,
    })),
  );
}

function credentialSlotKey(requirement: ToolCredentialRequirementApiPayload): string {
  return [
    requirement.consumer.consumer_id,
    requirement.slot.slot,
    requirement.requirement_id,
  ].filter(Boolean).join("::");
}

function accessRequirementForSlot(
  requirement: ToolCredentialRequirementApiPayload,
): ToolAccessCredentialRequirementPayload | null {
  const consumerId = requirement.consumer.consumer_id;
  const slot = requirement.slot.slot;
  return accessCredentialRequirements.value.find((item) =>
    item.consumer_module === "tool"
    && item.consumer_id === consumerId
    && item.slot === slot,
  ) ?? null;
}

function syncCredentialBindingDrafts(): void {
  const next: Record<string, string> = {};
  for (const slot of selectedCredentialSlots.value) {
    const existingDraft = credentialBindingDrafts.value[slot.key];
    next[slot.key] = existingDraft
      ?? currentCredentialBindingId(slot)
      ?? "";
  }
  credentialBindingDrafts.value = next;
}

function currentCredentialBindingId(slot: ToolCredentialSlotView): string | null {
  return slot.accessRequirement?.binding_id
    ?? slot.requirement.slot.binding_id
    ?? null;
}

function credentialBindingById(bindingId: string): ToolAccessCredentialBindingPayload | null {
  return accessCredentialBindings.value.find((binding) => binding.binding_id === bindingId) ?? null;
}

function credentialBindingOptionsForSlot(
  requirement: ToolCredentialRequirementApiPayload,
): ToolAccessCredentialBindingPayload[] {
  return accessCredentialBindings.value
    .filter((binding) => credentialBindingCompatibilityForRequirement(binding, requirement).compatible)
    .sort((left, right) => {
    const byStatus = credentialBindingStatusRank(left) - credentialBindingStatusRank(right);
    if (byStatus !== 0) return byStatus;
    return left.binding_id.localeCompare(right.binding_id);
  });
}

function credentialBindingCompatibilityForSlot(
  requirement: ToolCredentialRequirementApiPayload,
  bindingId: string,
): CredentialBindingCompatibility {
  const binding = credentialBindingById(bindingId);
  if (!binding) {
    return {
      compatible: false,
      reason: t("settings.toolCatalog.error.bindingNotRegistered", { binding: bindingId }),
    };
  }
  return credentialBindingCompatibilityForRequirement(binding, requirement);
}

function credentialBindingCompatibilityForRequirement(
  binding: ToolAccessCredentialBindingPayload,
  requirement: ToolCredentialRequirementApiPayload,
): CredentialBindingCompatibility {
  const bindingStatus = normalizedCredentialText(binding.status);
  if (bindingStatus && !["active", "ready", "valid"].includes(bindingStatus)) {
    return {
      compatible: false,
      reason: t("settings.toolCatalog.error.bindingNotActive", {
        binding: binding.binding_id,
        status: titleize(bindingStatus),
      }),
    };
  }
  const expectedKind = normalizedCredentialText(requirement.slot.expected_kind);
  const bindingKind = normalizedCredentialText(binding.binding_kind);
  if (expectedKind && bindingKind !== expectedKind) {
    return {
      compatible: false,
      reason: t("settings.toolCatalog.error.bindingKindMismatch", {
        binding: binding.binding_id,
        actual: credentialBindingTypeLabel(binding),
        expected: titleize(expectedKind),
      }),
    };
  }
  const requiredProvider = normalizedCredentialText(requirement.provider);
  const bindingProvider = credentialBindingProvider(binding);
  if (requiredProvider && bindingProvider && bindingProvider !== requiredProvider) {
    return {
      compatible: false,
      reason: t("settings.toolCatalog.error.bindingProviderMismatch", {
        binding: binding.binding_id,
        actual: bindingProvider,
        expected: requiredProvider,
      }),
    };
  }
  return { compatible: true, reason: "" };
}

function credentialBindingStatusRank(binding: ToolAccessCredentialBindingPayload): number {
  const status = normalizedCredentialText(binding.status);
  if (["active", "ready", "valid"].includes(status)) return 0;
  if (["pending", "warning", "degraded"].includes(status)) return 1;
  if (["disabled", "revoked", "blocked", "failed"].includes(status)) return 2;
  return 3;
}

function credentialBindingActionPayload(
  toolId: string,
  slot: ToolCredentialSlotView,
  credentialBindingId: string,
): BindToolCredentialRequirementRequest {
  const requirement = slot.requirement;
  return {
    tool_id: toolId,
    consumer_id: requirement.consumer.consumer_id,
    slot: requirement.slot.slot,
    display_name: requirement.slot.display_name,
    provider: requirement.provider,
    expected_kind: requirement.slot.expected_kind,
    credential_binding_id: credentialBindingId,
    requirement_sets: [[requirementReference(requirement)]],
  };
}

function requirementReference(requirement: ToolCredentialRequirementApiPayload): string {
  const provider = requirement.provider?.trim();
  const expectedKind = requirement.slot.expected_kind.trim();
  const slot = requirement.slot.slot.trim();
  const suffix = slot ? `(${slot})` : "";
  return provider ? `${provider}:${expectedKind}${suffix}` : `${expectedKind}${suffix}`;
}

function credentialSlotReady(slot: ToolCredentialSlotView): boolean {
  if (slot.accessRequirement?.ready !== undefined) return slot.accessRequirement.ready;
  const bindingId = currentCredentialBindingId(slot);
  if (!bindingId) return !slot.requirement.slot.required;
  const binding = credentialBindingById(bindingId);
  return Boolean(binding && credentialBindingCompatibilityForRequirement(binding, slot.requirement).compatible);
}

function credentialSlotReadinessLabel(slot: ToolCredentialSlotView): string {
  if (slot.accessRequirement?.status) return titleize(slot.accessRequirement.status);
  const bindingId = currentCredentialBindingId(slot);
  if (!bindingId) return slot.requirement.slot.required
    ? t("settings.toolCatalog.credential.missingBinding")
    : t("settings.toolCatalog.common.optional");
  const binding = credentialBindingById(bindingId);
  if (!binding) return t("settings.toolCatalog.credential.bindingMissingInAccess");
  const compatibility = credentialBindingCompatibilityForRequirement(binding, slot.requirement);
  return compatibility.compatible
    ? titleize(binding.status, t("text.configured"))
    : t("settings.toolCatalog.credential.kindMismatch");
}

function credentialSlotSetupLabel(slot: ToolCredentialSlotView): string {
  const flowKind = setupFlowKind(slot);
  if (credentialSlotReady(slot)) return t("settings.toolCatalog.credential.ready");
  if (setupProviderMissing(slot.accessRequirement?.setup_flow_hint ?? slot.requirement.setup_flow_hint)) {
    return t("settings.toolCatalog.credential.needsAccessSetupProvider");
  }
  if (flowKind && flowKind !== "none" && flowKind !== "unknown") return titleize(flowKind);
  return t("settings.toolCatalog.credential.needsAccessSetupProvider");
}

function credentialReadinessLabel(tool: ToolApiPayload | null): string {
  const summary = credentialReadinessSummary(tool);
  if (summary.total === 0) return t("settings.toolCatalog.credential.noSlots");
  if (summary.ready === summary.total) {
    return t("settings.toolCatalog.credential.readyCount", { ready: summary.ready, total: summary.total });
  }
  if (summary.ready === 0) return t("settings.toolCatalog.credential.missingCount", { total: summary.total });
  return t("settings.toolCatalog.credential.partialCount", { ready: summary.ready, total: summary.total });
}

function credentialFilterMatches(tool: ToolApiPayload | null, filter: string): boolean {
  if (filter === "all") return true;
  const summary = credentialReadinessSummary(tool);
  if (filter === "none") return summary.total === 0;
  if (filter === "ready") return summary.total > 0 && summary.ready === summary.total;
  if (filter === "missing") return summary.total > 0 && summary.ready === 0;
  if (filter === "partial") return summary.ready > 0 && summary.ready < summary.total;
  return true;
}

function credentialReadinessSummary(tool: ToolApiPayload | null): { ready: number; total: number } {
  if (!tool) return { ready: 0, total: 0 };
  const slots = flattenCredentialSlots(tool.credential_requirements ?? []);
  if (!slots.length) return { ready: 0, total: 0 };
  const slotsWithAccess = slots.map((slot) => ({
    ...slot,
    accessRequirement: accessRequirementForSlot(slot.requirement),
  }));
  return {
    total: slotsWithAccess.length,
    ready: slotsWithAccess.filter((slot) => credentialSlotReady(slot)).length,
  };
}

function providerBackendCredentialLabel(backend: ToolProviderBackendApiPayload): string {
  const bindings = providerBackendCredentialBindings(backend);
  return bindings.length ? bindings.join(", ") : "-";
}

function providerBackendCredentialBindings(backend: ToolProviderBackendApiPayload): string[] {
  const values: string[] = [];
  for (const requirementSet of backend.credential_requirements) {
    const requirements = Array.isArray(requirementSet.requirements) ? requirementSet.requirements : [];
    for (const requirement of requirements) {
      const slot = normalizedRecord(normalizedRecord(requirement).slot);
      const bindingId = stringFromUnknown(slot.binding_id);
      if (bindingId) values.push(bindingId);
    }
  }
  return [...new Set(values)];
}

function providerBackendRuntimeLabel(backend: ToolProviderBackendApiPayload): string {
  const runtimeKind = stringFromUnknown(backend.runtime_ref.runtime_kind);
  const ref = stringFromUnknown(backend.runtime_ref.ref);
  if (runtimeKind && ref) return `${runtimeKind}:${ref}`;
  return runtimeKind || ref || "-";
}

function providerBackendReady(backend: ToolProviderBackendApiPayload): boolean {
  return normalizedRecord(backend.readiness).ready === true;
}

function providerBackendReadinessLabel(backend: ToolProviderBackendApiPayload): string {
  const readiness = normalizedRecord(backend.readiness);
  if (readiness.ready === true) return t("text.ready");
  const status = stringFromUnknown(readiness.status);
  if (!status) return t("status.unknown");
  const checks = Array.isArray(readiness.checks) ? readiness.checks : [];
  if (!checks.length) return titleize(status);
  const ready = checks.filter((check) => normalizedRecord(check).ready === true).length;
  return `${titleize(status)} (${ready}/${checks.length})`;
}

function runCatalogVersionLabel(run: ToolRunApiPayload): string {
  const functionId = run.function_id || run.tool_id;
  const functionRevision = run.function_revision ? `r${run.function_revision}` : "r?";
  const sourceRevision = run.source_revision ? `s${run.source_revision}` : "s?";
  const schema = run.schema_hash ? run.schema_hash.slice(0, 8) : "no-schema";
  return `${functionId}@${functionRevision}/${sourceRevision}/${schema}`;
}

function setupFlowKind(slot: ToolCredentialSlotView): string | null {
  return slot.accessRequirement?.setup_flow_hint?.flow_kind
    ?? slot.requirement.setup_flow_hint?.flow_kind
    ?? null;
}

function setupProviderMissing(value: { metadata?: unknown } | null | undefined): boolean {
  const metadata = isRecord(value?.metadata) ? value.metadata : null;
  return metadata?.setup_provider_missing === true;
}

function emptySourceEditor(): SourceEditorState {
  return {
    mode: "create",
    sourceId: "configured.openapi.custom",
    kind: "openapi",
    displayName: t("settings.toolCatalog.sourceEditor.defaultDisplayName"),
    description: "",
    providerName: "custom",
    specLocation: "",
    baseUrl: "",
    commandText: "",
    allowedSubcommands: "",
    deniedFlags: "",
    workingDirectory: "",
    allowedRoots: "",
    outputLimitBytes: "",
    timeoutSeconds: "",
    maxConcurrency: "",
    defaultEffectIds: "",
    runtimeRequirements: "",
  };
}

function emptyFunctionPolicyDraft(): FunctionPolicyDraft {
  return {
    trustLevel: "",
    approvalMode: "",
    requiresApproval: "",
    credentialBindingOverrides: "",
    requiredEffectOverrides: "",
  };
}

function syncFunctionPolicyDraft(): void {
  const toolFunction = selectedFunction.value;
  functionPolicyError.value = null;
  if (!toolFunction) {
    functionPolicyDraft.value = emptyFunctionPolicyDraft();
    return;
  }
  functionPolicyDraft.value = {
    trustLevel: stringValue(
      toolFunction.trust_policy.level ?? toolFunction.trust_policy.trust,
    ),
    approvalMode: stringValue(toolFunction.approval_policy.mode),
    requiresApproval: booleanDraftValue(toolFunction.approval_policy.requires_approval),
    credentialBindingOverrides: formatCredentialBindingOverrides(
      toolFunction.credential_binding_overrides,
    ),
    requiredEffectOverrides: (toolFunction.required_effect_overrides ?? []).join(", "),
  };
}

function buildFunctionPolicyPayload(toolFunction: ToolFunctionApiPayload) {
  const trustPolicy: Record<string, unknown> = { ...toolFunction.trust_policy };
  setOptionalPolicyText(trustPolicy, "level", functionPolicyDraft.value.trustLevel);
  if ("trust" in trustPolicy && !("level" in trustPolicy)) {
    setOptionalPolicyText(trustPolicy, "trust", functionPolicyDraft.value.trustLevel);
  }

  const approvalPolicy: Record<string, unknown> = { ...toolFunction.approval_policy };
  setOptionalPolicyText(approvalPolicy, "mode", functionPolicyDraft.value.approvalMode);
  if (functionPolicyDraft.value.requiresApproval) {
    approvalPolicy.requires_approval = functionPolicyDraft.value.requiresApproval === "true";
  } else {
    delete approvalPolicy.requires_approval;
  }

  const effectOverrides = parseCsvList(functionPolicyDraft.value.requiredEffectOverrides);
  return {
    trust_policy: trustPolicy,
    approval_policy: approvalPolicy,
    credential_binding_overrides: parseCredentialBindingOverrides(
      functionPolicyDraft.value.credentialBindingOverrides,
    ),
    required_effect_overrides: effectOverrides.length ? effectOverrides : null,
  };
}

function setOptionalPolicyText(
  target: Record<string, unknown>,
  key: string,
  value: string,
): void {
  const text = value.trim();
  if (text) target[key] = text;
  else delete target[key];
}

function booleanDraftValue(value: unknown): "" | "true" | "false" {
  if (value === true) return "true";
  if (value === false) return "false";
  return "";
}

function formatCredentialBindingOverrides(value: Record<string, string>): string {
  return Object.entries(value)
    .map(([key, bindingId]) => `${key}=${bindingId}`)
    .join(", ");
}

function parseCredentialBindingOverrides(value: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const rawItem of value.split(",")) {
    const item = rawItem.trim();
    if (!item) continue;
    const separator = item.indexOf("=");
    if (separator <= 0 || separator === item.length - 1) {
      throw new Error(t("settings.toolCatalog.error.credentialOverrideFormat"));
    }
    const key = item.slice(0, separator).trim();
    const bindingId = item.slice(separator + 1).trim();
    if (!key || !bindingId) {
      throw new Error(t("settings.toolCatalog.error.credentialOverrideFormat"));
    }
    result[key] = bindingId;
  }
  return result;
}

function resetToolRunDraft(): void {
  closeCliConsoleStream();
  const next: Record<string, string> = {};
  for (const parameter of selectedToolParameters.value) {
    next[parameter.name] = "";
  }
  testRunArguments.value = next;
  testRunMode.value = supportedModes.value[0] ?? "inline";
  testRunStrategy.value = supportedStrategies.value[0] ?? "async";
  testRunEnvironment.value = supportedEnvironments.value[0] ?? "local";
  testRunError.value = null;
  lastTestRun.value = null;
  cliConsoleProcessId.value = null;
  cliConsoleLines.value = [];
  cliConsoleStatus.value = null;
  cliConsoleError.value = null;
}

function buildTestRunArguments(parameters: ToolApiPayload["parameters"]): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const parameter of parameters) {
    const rawValue = testRunArguments.value[parameter.name] ?? "";
    if (!rawValue.trim()) {
      if (parameter.required) {
        throw new Error(t("settings.toolCatalog.error.parameterRequired", { parameter: parameter.name }));
      }
      continue;
    }
    payload[parameter.name] = parseToolArgumentValue(parameter.data_type, rawValue);
  }
  return payload;
}

function parseToolArgumentValue(dataType: string, rawValue: string): unknown {
  const value = rawValue.trim();
  const kind = normalizedText(dataType);
  if (kind === "boolean" || kind === "bool") return value === "true";
  if (kind === "integer" || kind === "int") {
    const parsed = Number(value);
    if (!Number.isInteger(parsed)) throw new Error(t("settings.toolCatalog.error.notInteger", { value }));
    return parsed;
  }
  if (kind === "number" || kind === "float") {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) throw new Error(t("settings.toolCatalog.error.notNumber", { value }));
    return parsed;
  }
  if (kind === "array" || kind === "object") {
    try {
      return JSON.parse(value) as unknown;
    } catch (error) {
      throw new Error(t("settings.toolCatalog.error.invalidJson", {
        type: dataType,
        reason: error instanceof Error ? error.message : String(error),
      }));
    }
  }
  return rawValue;
}

function parameterInputKind(dataType: string): "text" | "number" | "boolean" | "json" {
  const kind = normalizedText(dataType);
  if (kind === "boolean" || kind === "bool") return "boolean";
  if (["integer", "int", "number", "float"].includes(kind)) return "number";
  if (kind === "array" || kind === "object") return "json";
  return "text";
}

function nonEmptyStrings(value: string[] | undefined, fallback: string[]): string[] {
  const items = (value ?? []).map((item) => item.trim()).filter(Boolean);
  return items.length ? items : fallback;
}

function formatPayload(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function editorStateFromSource(source: ToolSourceApiPayload): SourceEditorState {
  const provider = sourceProviderConfig(source);
  const command = stringListValue(provider.command).join("\n");
  return {
    mode: "edit",
    sourceId: source.source_id,
    kind: source.kind === "mcp" || source.kind === "cli" ? source.kind : "openapi",
    displayName: source.display_name || source.source_id,
    description: source.description ?? "",
    providerName: stringValue(provider.name, source.source_id),
    specLocation: stringValue(provider.spec_location),
    baseUrl: stringValue(provider.base_url),
    commandText: command,
    allowedSubcommands: stringListValue(provider.allowed_subcommands).join(", "),
    deniedFlags: stringListValue(provider.denied_flags).join(", "),
    workingDirectory: stringValue(provider.working_directory),
    allowedRoots: stringListValue(provider.allowed_roots).join(", "),
    outputLimitBytes: stringValue(provider.output_limit_bytes),
    timeoutSeconds: stringValue(provider.timeout_seconds),
    maxConcurrency: stringValue(provider.max_concurrency),
    defaultEffectIds: stringListValue(provider.default_effect_ids).join(", "),
    runtimeRequirements: source.runtime_requirements.join(", "),
  };
}

function buildSourceEditorPayload(state: SourceEditorState): ToolSourceWriteApiRequest {
  const sourceId = state.sourceId.trim();
  const providerName = state.providerName.trim();
  if (!sourceId) throw new Error(t("settings.toolCatalog.error.sourceIdRequired"));
  if (!providerName) throw new Error(t("settings.toolCatalog.error.providerNameRequired"));

  const config: Record<string, unknown> = sourceEditorExistingConfig(state);
  const provider: Record<string, unknown> = {
    ...sourceEditorExistingProvider(state),
    name: providerName,
  };
  config.source = "configured_tool_provider";
  config.package_kind = state.kind;

  if (state.kind === "openapi") {
    const specLocation = state.specLocation.trim();
    if (!specLocation) throw new Error(t("settings.toolCatalog.error.openapiSpecRequired"));
    provider.spec_location = specLocation;
    if (state.baseUrl.trim()) provider.base_url = state.baseUrl.trim();
    else delete provider.base_url;
    delete provider.command;
    delete provider.executable;
    delete provider.allowed_subcommands;
    delete provider.denied_flags;
    delete provider.working_directory;
    delete provider.allowed_roots;
    delete provider.output_limit_bytes;
  } else if (state.kind === "mcp") {
    const command = parseLineList(state.commandText);
    if (!command.length) throw new Error(t("settings.toolCatalog.error.mcpCommandRequired"));
    provider.command = command;
    delete provider.spec_location;
    delete provider.base_url;
    delete provider.executable;
    delete provider.allowed_subcommands;
    delete provider.denied_flags;
    delete provider.working_directory;
    delete provider.allowed_roots;
    delete provider.output_limit_bytes;
  } else {
    const command = parseLineList(state.commandText);
    const allowedSubcommands = parseCsvList(state.allowedSubcommands);
    if (!command.length) throw new Error(t("settings.toolCatalog.error.cliCommandRequired"));
    if (!allowedSubcommands.length) throw new Error(t("settings.toolCatalog.error.cliSubcommandsRequired"));
    provider.command = command;
    provider.allowed_subcommands = allowedSubcommands;
    const deniedFlags = parseCsvList(state.deniedFlags);
    if (deniedFlags.length) provider.denied_flags = deniedFlags;
    else delete provider.denied_flags;
    if (state.workingDirectory.trim()) provider.working_directory = state.workingDirectory.trim();
    else delete provider.working_directory;
    const allowedRoots = parseCsvList(state.allowedRoots);
    if (allowedRoots.length) provider.allowed_roots = allowedRoots;
    else delete provider.allowed_roots;
    const outputLimitBytes = parseOptionalPositiveInteger(
      state.outputLimitBytes,
      t("settings.toolCatalog.sourceEditor.outputLimitBytes"),
    );
    if (outputLimitBytes !== undefined) provider.output_limit_bytes = outputLimitBytes;
    else delete provider.output_limit_bytes;
    delete provider.spec_location;
    delete provider.base_url;
    delete provider.executable;
  }

  const timeoutSeconds = parseOptionalPositiveInteger(
    state.timeoutSeconds,
    t("settings.toolCatalog.sourceEditor.timeoutSeconds"),
  );
  const maxConcurrency = parseOptionalPositiveInteger(
    state.maxConcurrency,
    t("table.maxConcurrency"),
  );
  if (timeoutSeconds !== undefined) provider.timeout_seconds = timeoutSeconds;
  else delete provider.timeout_seconds;
  if (maxConcurrency !== undefined) provider.max_concurrency = maxConcurrency;
  else delete provider.max_concurrency;

  const defaultEffectIds = parseCsvList(state.defaultEffectIds);
  if (defaultEffectIds.length) provider.default_effect_ids = defaultEffectIds;
  else delete provider.default_effect_ids;

  config.provider = provider;
  const existingSource = state.mode === "edit" ? selectedSourceForEditor(state.sourceId) : null;
  return {
    source_id: sourceId,
    kind: state.kind,
    display_name: state.displayName.trim() || sourceId,
    description: state.description.trim(),
    config,
    credential_requirements: existingSource?.credential_requirements ?? [],
    runtime_requirements: parseCsvList(state.runtimeRequirements),
    status: "active",
  };
}

function sourceEditorExistingConfig(state: SourceEditorState): Record<string, unknown> {
  const source = state.mode === "edit" ? selectedSourceForEditor(state.sourceId) : null;
  return source ? { ...source.config } : {};
}

function sourceEditorExistingProvider(state: SourceEditorState): Record<string, unknown> {
  const source = state.mode === "edit" ? selectedSourceForEditor(state.sourceId) : null;
  return source ? { ...sourceProviderConfig(source) } : {};
}

function selectedSourceForEditor(sourceId: string): ToolSourceApiPayload | null {
  return sources.value.find((source) => source.source_id === sourceId) ?? null;
}

function sourceProviderConfig(source: ToolSourceApiPayload): Record<string, unknown> {
  const provider = source.config.provider;
  return isRecord(provider) ? provider : {};
}

function isWritableSource(source: ToolSourceApiPayload): boolean {
  return (
    (source.kind === "openapi" || source.kind === "mcp" || source.kind === "cli")
    && source.config.source === "configured_tool_provider"
    && source.config.package_kind === source.kind
  );
}

function parseCsvList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseLineList(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseOptionalPositiveInteger(value: string, label: string): number | undefined {
  const text = value.trim();
  if (!text) return undefined;
  const parsed = Number(text);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(t("settings.toolCatalog.error.positiveInteger", { label }));
  }
  return parsed;
}

function stringListValue(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string | number => typeof item === "string" || typeof item === "number")
    .map((item) => String(item));
}

function stringValue(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function slotStatusTone(slot: ToolCredentialSlotView): StatusTone {
  if (credentialSlotReady(slot)) return "success";
  if (!currentCredentialBindingId(slot) && slot.requirement.slot.required) return "danger";
  const bindingId = credentialBindingDrafts.value[slot.key]?.trim();
  if (bindingId && !credentialBindingCompatibilityForSlot(slot.requirement, bindingId).compatible) return "danger";
  return "warning";
}

function maskedBindingLabel(bindingId: string, binding: ToolAccessCredentialBindingPayload | null): string {
  if (!binding) return `${bindingId} · missing`;
  const preview = binding.masked_preview ? ` · ${binding.masked_preview}` : "";
  return `${binding.binding_id}${preview}`;
}

function credentialBindingOptionLabel(
  binding: ToolAccessCredentialBindingPayload,
  requirement: ToolCredentialRequirementApiPayload,
): string {
  const compatibility = credentialBindingCompatibilityForRequirement(binding, requirement);
  const status = binding.status ? ` · ${binding.status}` : "";
  const preview = binding.masked_preview ? ` · ${binding.masked_preview}` : "";
  const suffix = compatibility.compatible ? "" : ` · incompatible`;
  return `${binding.binding_id} · ${credentialBindingTypeLabel(binding)}${status}${preview}${suffix}`;
}

function credentialBindingTypeLabel(binding: ToolAccessCredentialBindingPayload): string {
  return binding.binding_kind ?? binding.source_kind ?? "credential";
}

function credentialBindingProvider(binding: ToolAccessCredentialBindingPayload): string {
  const metadata = isRecord(binding.metadata) ? binding.metadata : {};
  return normalizedCredentialText(
    stringValue(metadata.provider_id)
    || stringValue(metadata.provider)
    || stringValue(metadata.service)
    || stringValue(metadata.owner_provider),
  );
}

function normalizedText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function normalizedCredentialText(value: string | null | undefined): string {
  return normalizedText(value);
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right));
}

function rowValue(row: unknown, key: string): string | null {
  const value = tableCellValue(row, key);
  return typeof value === "string" && value.trim() ? value : null;
}

function tableCellValue(row: unknown, key: string): unknown {
  if (!isRecord(row)) return null;
  const cells = row.cells;
  if (isRecord(cells)) return cells[key];
  return row[key];
}

function textValue(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return yesNo(value);
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
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

function column(key: string, labelKey: string): UiTableColumn {
  return { key, label: t(labelKey) };
}

function yesNo(value: unknown): string {
  if (value === true) return t("settings.toolCatalog.common.yes");
  if (value === false) return t("settings.toolCatalog.common.no");
  return textValue(value);
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

function toneForStatus(value: unknown): StatusTone {
  const text = textValue(value, "").toLowerCase();
  if (/(failed|invalid|error|disabled|blocked|missing)/.test(text)) return "danger";
  if (/(warning|draft|pending|unknown|overlay)/.test(text)) return "warning";
  if (/(active|ready|valid|success|published|enabled|wired)/.test(text)) return "success";
  if (text) return "info";
  return "neutral";
}

function timestampValue(value: string | null): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function normalizedRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function stringFromUnknown(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function numberFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
</script>

<template>
  <main class="settings-module tool-settings">
    <header class="tool-page-header">
      <div class="tool-title-block">
        <h1>{{ t("settings.toolCatalog.title") }}</h1>
        <p>{{ t("settings.toolCatalog.subtitle") }}</p>
      </div>
      <div class="tool-header-actions">
        <UiButton size="sm" variant="primary" @click="openSourceEditor('create')">
          <Plus :size="14" /> {{ t("settings.toolCatalog.action.newSource") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="!selectedSourceId || Boolean(sourceActionId)" @click="refreshSelectedSource">
          <RefreshCcw :size="14" /> {{ t("settings.toolCatalog.action.refreshSource") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadToolCatalog()">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section class="tool-notice-line" :class="{ empty: !actionMessage && !actionError }">
      <p v-if="actionError" class="settings-state--error">{{ actionError }}</p>
      <p v-else>{{ actionMessage || " " }}</p>
    </section>

    <section class="tool-metric-strip">
      <article class="tool-metric">
        <span><Wrench :size="15" />{{ t("settings.toolCatalog.metric.functions") }}</span>
        <strong>{{ toolFunctions.length }}</strong>
        <em>{{ t("settings.toolCatalog.metric.functionsHint", { active: activeFunctionCount, disabled: disabledCount }) }}</em>
      </article>
      <article class="tool-metric">
        <span><Package :size="15" />{{ t("settings.toolCatalog.metric.sources") }}</span>
        <strong>{{ sourceCount }}</strong>
        <em>{{ t("settings.toolCatalog.metric.sourcesHint", { active: activeSourceCount, issues: sourceDiscoveryIssueCount }) }}</em>
      </article>
      <article class="tool-metric">
        <span><GitBranch :size="15" />{{ t("settings.toolCatalog.metric.backends") }}</span>
        <strong>{{ providerBackends.length }}</strong>
        <em>{{ t("settings.toolCatalog.metric.backendsHint", { active: activeBackendCount, issues: backendIssueCount }) }}</em>
      </article>
      <article class="tool-metric">
        <span><Shield :size="15" />{{ t("settings.toolCatalog.metric.credentials") }}</span>
        <strong>{{ accessCredentialBindingCount }}</strong>
        <em>{{ t("settings.toolCatalog.metric.credentialsHint", { issues: credentialIssueCount }) }}</em>
      </article>
      <article class="tool-metric">
        <span><Play :size="15" />{{ t("settings.toolCatalog.metric.recentRuns") }}</span>
        <strong>{{ selectedRuns.length }}</strong>
        <em>{{ selectedToolId ? `/tools/${selectedToolId}/runs` : t("settings.toolCatalog.metric.selectFunction") }}</em>
      </article>
    </section>

    <section class="tool-workspace">
      <section class="settings-panel tool-catalog-panel">
        <div class="tool-catalog-toolbar">
          <nav class="tool-view-tabs">
            <button :class="{ active: activeCatalogView === 'functions' }" type="button" @click="activeCatalogView = 'functions'">
              {{ t("settings.toolCatalog.view.functions") }} <span>{{ functionRows.length }}</span>
            </button>
            <button :class="{ active: activeCatalogView === 'sources' }" type="button" @click="activeCatalogView = 'sources'">
              {{ t("settings.toolCatalog.view.sources") }} <span>{{ sourceRows.length }}</span>
            </button>
            <button :class="{ active: activeCatalogView === 'backends' }" type="button" @click="activeCatalogView = 'backends'">
              {{ t("settings.toolCatalog.view.backends") }} <span>{{ backendRows.length }}</span>
            </button>
            <button :class="{ active: activeCatalogView === 'runs' }" type="button" @click="activeCatalogView = 'runs'">
              {{ t("settings.toolCatalog.view.runs") }} <span>{{ runRows.length }}</span>
            </button>
          </nav>
          <div class="tool-search">
            <input v-model.trim="searchQuery" :disabled="activeCatalogView !== 'functions'" :placeholder="t('settings.toolCatalog.searchPlaceholder')" />
          </div>
        </div>

        <div v-if="activeCatalogView === 'functions'" class="tool-filter-bar">
          <label>
            <span>{{ t("table.source") }}</span>
            <select v-model="functionSourceFilter">
              <option value="all">{{ t("settings.toolCatalog.filter.allSources") }}</option>
              <option v-for="source in sourceOptions" :key="source.id" :value="source.id">{{ source.label }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("table.status") }}</span>
            <select v-model="functionStatusFilter">
              <option value="all">{{ t("settings.toolCatalog.filter.allStatus") }}</option>
              <option v-for="status in functionStatusOptions" :key="status" :value="status">{{ titleize(status) }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.toolCatalog.table.runtime") }}</span>
            <select v-model="runtimeKindFilter">
              <option value="all">{{ t("settings.toolCatalog.filter.allRuntime") }}</option>
              <option v-for="kind in runtimeKindOptions" :key="kind" :value="kind">{{ titleize(kind) }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.toolCatalog.table.enabled") }}</span>
            <select v-model="functionEnabledFilter">
              <option value="all">{{ t("common.all") }}</option>
              <option value="enabled">{{ t("settings.toolCatalog.status.enabled") }}</option>
              <option value="disabled">{{ t("settings.toolCatalog.status.disabled") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.toolCatalog.table.credential") }}</span>
            <select v-model="credentialFilter">
              <option value="all">{{ t("common.all") }}</option>
              <option value="ready">{{ t("settings.toolCatalog.credential.ready") }}</option>
              <option value="missing">{{ t("settings.toolCatalog.credential.missing") }}</option>
              <option value="partial">{{ t("settings.toolCatalog.credential.partial") }}</option>
              <option value="none">{{ t("settings.toolCatalog.credential.noSlots") }}</option>
            </select>
          </label>
        </div>

        <div class="tool-table-shell">
          <DataTable
            :columns="catalogColumns"
            :rows="catalogRows"
            :page-size="activeCatalogView === 'functions' ? 20 : 12"
            :section-id="activeCatalogView === 'runs' ? 'tool-runs' : 'tool-catalog'"
            :selected-row-id="catalogSelectedRowId"
            clickable-rows
            allow-raw-keys
            @row-click="selectCatalogRow"
          />
          <div v-if="!catalogRows.length" class="tool-table-empty" :class="{ error: Boolean(loadError) }">
            {{ catalogEmptyMessage }}
          </div>
        </div>
      </section>

      <aside class="settings-panel tool-detail-drawer">
        <template v-if="drawerMode === 'sources'">
          <header class="drawer-header">
            <span class="drawer-icon"><Package :size="17" /></span>
            <div>
              <h2>{{ selectedSource?.display_name ?? t("settings.toolCatalog.source.detailTitle") }}</h2>
              <p>{{ selectedSource?.source_id ?? t("settings.toolCatalog.source.selectHint") }}</p>
            </div>
            <StatusDot :tone="toneForStatus(selectedSource?.status)" />
          </header>

          <div class="drawer-action-row">
            <button type="button" :disabled="!selectedSourceWritable || Boolean(sourceActionId)" @click="openSourceEditor('edit')">
              <Copy :size="13" /> {{ t("common.edit") }}
            </button>
            <button type="button" :disabled="!selectedSource || Boolean(sourceActionId)" @click="refreshSelectedSource">
              <RefreshCcw :size="13" /> {{ t("common.refresh") }}
            </button>
            <button type="button" :disabled="!selectedSource || Boolean(sourceActionId)" @click="toggleSelectedSource">
              {{ selectedSource && ["disabled", "deleted"].includes(normalizedText(selectedSource.status)) ? t("settings.toolCatalog.action.restore") : t("settings.toolCatalog.action.disable") }}
            </button>
            <button type="button" class="danger" :disabled="!selectedSource || normalizedText(selectedSource.status) === 'deleted' || Boolean(sourceActionId)" @click="deleteSelectedSource">
              {{ t("settings.toolCatalog.action.delete") }}
            </button>
          </div>

          <section class="drawer-section">
            <h3>{{ t("settings.toolCatalog.source.overview") }}</h3>
            <dl class="drawer-kv">
              <div><dt>{{ t("table.kind") }}</dt><dd>{{ titleize(selectedSource?.kind) }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.revision") }}</dt><dd>{{ textValue(selectedSource?.revision) }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.configHash") }}</dt><dd>{{ textValue(selectedSource?.config_hash) }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.lastDiscovery") }}</dt><dd>{{ textValue(selectedSource?.last_discovered_at) }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.discoveryStatus") }}</dt><dd>{{ titleize(selectedSource?.last_discovery_status, t("settings.toolCatalog.state.never")) }}</dd></div>
            </dl>
          </section>

          <section class="drawer-section">
            <div class="drawer-section-heading">
              <h3>{{ t("settings.toolCatalog.source.discoveryHistory") }}</h3>
              <button type="button" :disabled="!selectedSourceId || sourceHistoryLoading" @click="loadSourceHistory(selectedSourceId)">
                <RefreshCcw :size="13" />
              </button>
            </div>
            <div v-if="sourceHistoryLoading" class="drawer-empty">{{ t("settings.toolCatalog.state.loadingDiscoveryHistory") }}</div>
            <div v-else-if="sourceHistoryError" class="drawer-empty error">{{ sourceHistoryError }}</div>
            <DataTable
              v-else-if="selectedSourceHistoryRows.length"
              :columns="sourceHistoryColumns"
              :rows="selectedSourceHistoryRows"
              section-id="tool-source-history"
              allow-raw-keys
              :page-size="4"
            />
            <div v-else class="drawer-empty">{{ t("settings.toolCatalog.state.noDiscoveryRuns") }}</div>
          </section>

          <section class="drawer-section">
            <h3>{{ t("settings.toolCatalog.source.config") }}</h3>
            <pre>{{ selectedSourceConfigText }}</pre>
          </section>
        </template>

        <template v-else-if="selectedOwnerTool">
          <header class="drawer-header">
            <span class="drawer-icon"><Wrench :size="17" /></span>
            <div>
              <h2>{{ selectedTitle }}</h2>
              <p>{{ selectedFunction?.function_id ?? selectedOwnerTool.id }}</p>
            </div>
            <StatusDot :tone="selectedStatusTone" />
          </header>

          <div class="drawer-action-row">
            <button type="button" :disabled="!selectedFunctionManaged || Boolean(toolActionId)" @click="toggleSelectedToolFunction">
              {{ (selectedFunction?.enabled ?? selectedOwnerTool.enabled) ? t("settings.toolCatalog.action.disable") : t("settings.toolCatalog.action.enable") }}
            </button>
            <button type="button" :disabled="!selectedFunctionSourceWritable || Boolean(sourceActionId)" @click="openSelectedFunctionSourceEditor">
              <Copy :size="13" /> {{ t("table.source") }}
            </button>
            <button type="button" :disabled="!selectedRuntimeRunnable" @click="submitToolTestRun">
              <Play :size="13" /> {{ t("settings.toolCatalog.action.run") }}
            </button>
            <button type="button" :disabled="!selectedToolId || runsLoading" @click="refreshSelectedRuns">
              <RefreshCcw :size="13" />
            </button>
          </div>

          <section class="drawer-section">
            <h3>{{ t("settings.toolCatalog.section.runtimeContract") }}</h3>
            <dl class="drawer-kv">
              <div><dt>{{ t("table.kind") }}</dt><dd>{{ titleize(selectedOwnerTool.kind) }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.runtime") }}</dt><dd>{{ textValue(selectedOwnerTool.runtime_key) }}</dd></div>
              <div><dt>{{ t("table.source") }}</dt><dd>{{ selectedFunctionSource?.display_name ?? selectedFunction?.source_id ?? "-" }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.modes") }}</dt><dd>{{ textValue(selectedOwnerTool.execution_support.supported_modes) }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.strategies") }}</dt><dd>{{ textValue(selectedOwnerTool.execution_support.supported_strategies) }}</dd></div>
              <div><dt>{{ t("table.timeout") }}</dt><dd>{{ selectedOwnerTool.execution_policy.timeout_seconds }}s</dd></div>
              <div><dt>{{ t("table.effects") }}</dt><dd>{{ textValue(selectedOwnerTool.required_effect_ids) }}</dd></div>
              <div><dt>{{ t("settings.toolCatalog.table.mutates") }}</dt><dd>{{ yesNo(selectedOwnerTool.execution_policy.mutates_state) }}</dd></div>
            </dl>
          </section>

          <section class="drawer-section">
            <div class="drawer-section-heading">
              <h3><Shield :size="14" />{{ t("settings.toolCatalog.section.functionPolicy") }}</h3>
              <span>{{ selectedFunction ? `r${selectedFunction.revision}` : t("settings.toolCatalog.state.readOnly") }}</span>
            </div>
            <div v-if="!selectedFunction" class="drawer-empty">
              {{ t("settings.toolCatalog.state.policyCatalogOnly") }}
            </div>
            <form v-else class="tool-policy-form" @submit.prevent="saveFunctionPolicy">
              <label>
                <span>{{ t("settings.toolCatalog.policy.trust") }}</span>
                <input v-model.trim="functionPolicyDraft.trustLevel" :placeholder="t('settings.toolCatalog.policy.trustedPlaceholder')" />
              </label>
              <label>
                <span>{{ t("settings.toolCatalog.policy.approval") }}</span>
                <select v-model="functionPolicyDraft.approvalMode">
                  <option value="">{{ t("settings.toolCatalog.policy.inherited") }}</option>
                  <option value="auto">{{ t("settings.toolCatalog.policy.auto") }}</option>
                  <option value="manual">{{ t("settings.toolCatalog.policy.manual") }}</option>
                  <option value="always">{{ t("settings.toolCatalog.policy.always") }}</option>
                  <option value="never">{{ t("settings.toolCatalog.policy.never") }}</option>
                </select>
              </label>
              <label>
                <span>{{ t("settings.toolCatalog.policy.requiresApproval") }}</span>
                <select v-model="functionPolicyDraft.requiresApproval">
                  <option value="">{{ t("settings.toolCatalog.policy.inherited") }}</option>
                  <option value="true">{{ t("settings.toolCatalog.common.yes") }}</option>
                  <option value="false">{{ t("settings.toolCatalog.common.no") }}</option>
                </select>
              </label>
              <label>
                <span>{{ t("table.effects") }}</span>
                <input v-model.trim="functionPolicyDraft.requiredEffectOverrides" :placeholder="t('settings.toolCatalog.policy.effectsPlaceholder')" />
              </label>
              <label class="wide">
                <span>{{ t("settings.toolCatalog.policy.credentialOverrides") }}</span>
                <input v-model.trim="functionPolicyDraft.credentialBindingOverrides" :placeholder="t('settings.toolCatalog.policy.credentialOverridesPlaceholder')" />
              </label>
              <p v-if="functionPolicyError" class="settings-state--error tool-policy-error">{{ functionPolicyError }}</p>
              <footer>
                <span>PUT /tools/functions/{{ selectedFunction.function_id }}/policy</span>
                <button type="submit" :disabled="functionPolicySaving">
                  {{ functionPolicySaving ? t("settings.toolCatalog.state.saving") : t("settings.toolCatalog.action.savePolicy") }}
                </button>
              </footer>
            </form>
          </section>

          <section class="drawer-section">
            <div class="drawer-section-heading">
              <h3>{{ t("settings.toolCatalog.section.credentialSlots") }}</h3>
              <span>{{ t("settings.toolCatalog.credential.readyFraction", { ready: readyCredentialSlotCount, total: selectedCredentialSlots.length }) }}</span>
            </div>
            <div v-if="accessContextError" class="drawer-empty error">{{ accessContextError }}</div>
            <div v-else-if="!selectedCredentialSlots.length" class="drawer-empty">{{ t("settings.toolCatalog.state.noCredentialSlots") }}</div>
            <div v-else class="tool-slot-list">
              <section v-for="slot in selectedCredentialSlots" :key="slot.key" class="tool-slot-card">
                <header>
                  <div>
                    <strong>{{ textValue(slot.requirement.slot.display_name ?? slot.requirement.slot.slot) }}</strong>
                    <small>{{ slot.requirement.slot.slot }} · {{ titleize(slot.requirement.slot.expected_kind) }}</small>
                  </div>
                  <span><StatusDot :tone="slotStatusTone(slot)" />{{ credentialSlotReadinessLabel(slot) }}</span>
                </header>
                <div class="tool-slot-bind-row">
                  <select
                    v-model="credentialBindingDrafts[slot.key]"
                    :disabled="accessContextLoading || savingCredentialSlotKey === slot.key"
                  >
                    <option value="" :disabled="slot.requirement.slot.required">{{ t("settings.toolCatalog.credential.noBinding") }}</option>
                    <option
                      v-if="currentCredentialBindingId(slot) && !credentialBindingById(currentCredentialBindingId(slot) ?? '')"
                      :value="currentCredentialBindingId(slot) ?? ''"
                      disabled
                    >
                      {{ t("settings.toolCatalog.credential.missingInAccess", { binding: currentCredentialBindingId(slot) ?? "" }) }}
                    </option>
                    <option
                      v-for="binding in credentialBindingOptionsForSlot(slot.requirement)"
                      :key="binding.binding_id"
                      :value="binding.binding_id"
                      :disabled="!credentialBindingCompatibilityForRequirement(binding, slot.requirement).compatible"
                    >
                      {{ credentialBindingOptionLabel(binding, slot.requirement) }}
                    </option>
                  </select>
                  <button
                    type="button"
                    :disabled="
                      accessContextLoading
                      || savingCredentialSlotKey === slot.key
                      || !credentialBindingDrafts[slot.key]
                      || !credentialBindingCompatibilityForSlot(slot.requirement, credentialBindingDrafts[slot.key] ?? '').compatible
                    "
                    @click="saveCredentialSlot(slot)"
                  >
                    {{ t("settings.toolCatalog.action.bind") }}
                  </button>
                </div>
                <p
                  v-if="credentialBindingDrafts[slot.key] && !credentialBindingCompatibilityForSlot(slot.requirement, credentialBindingDrafts[slot.key] ?? '').compatible"
                  class="tool-slot-warning"
                >
                  {{ credentialBindingCompatibilityForSlot(slot.requirement, credentialBindingDrafts[slot.key] ?? '').reason }}
                </p>
              </section>
            </div>
          </section>

          <section class="drawer-section" id="tool-test-run-panel">
            <div class="drawer-section-heading">
              <h3><Play :size="14" />{{ t("settings.toolCatalog.section.contractTest") }}</h3>
              <span>{{ selectedOwnerTool.id }}</span>
            </div>
            <form class="test-run-form" @submit.prevent="submitToolTestRun">
              <div class="test-run-selects">
                <label>
                  <span>{{ t("table.mode") }}</span>
                  <select v-model="testRunMode">
                    <option v-for="mode in supportedModes" :key="mode" :value="mode">{{ titleize(mode) }}</option>
                  </select>
                </label>
                <label>
                  <span>{{ t("table.strategy") }}</span>
                  <select v-model="testRunStrategy">
                    <option v-for="strategy in supportedStrategies" :key="strategy" :value="strategy">{{ titleize(strategy) }}</option>
                  </select>
                </label>
                <label>
                  <span>{{ t("table.environment") }}</span>
                  <select v-model="testRunEnvironment">
                    <option v-for="environment in supportedEnvironments" :key="environment" :value="environment">{{ titleize(environment) }}</option>
                  </select>
                </label>
              </div>
              <div v-if="selectedToolParameters.length" class="test-run-arguments">
                <label v-for="parameter in selectedToolParameters" :key="parameter.name" class="test-run-field">
                  <span>
                    {{ parameter.name }}
                    <em>{{ parameter.data_type }}{{ parameter.required ? ` · ${t("settings.toolCatalog.common.required")}` : "" }}</em>
                  </span>
                  <select v-if="parameterInputKind(parameter.data_type) === 'boolean'" v-model="testRunArguments[parameter.name]" :required="parameter.required">
                    <option value="">{{ t("settings.toolCatalog.common.unset") }}</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                  <textarea v-else-if="parameterInputKind(parameter.data_type) === 'json'" v-model="testRunArguments[parameter.name]" :required="parameter.required" rows="3" />
                  <input
                    v-else
                    v-model="testRunArguments[parameter.name]"
                    :type="parameterInputKind(parameter.data_type) === 'number' ? 'number' : 'text'"
                    :required="parameter.required"
                  />
                </label>
              </div>
              <div v-else class="drawer-empty">{{ t("settings.toolCatalog.state.noInputParameters") }}</div>
              <p v-if="testRunError" class="settings-state--error test-run-error">{{ testRunError }}</p>
              <footer class="test-run-actions">
                <span v-if="!selectedOwnerTool.enabled">{{ t("settings.toolCatalog.state.selectedToolDisabled") }}</span>
                <span v-else-if="!selectedRuntimeRunnable">{{ t("settings.toolCatalog.state.runtimeUnavailable") }}</span>
                <button type="submit" :disabled="!canSubmitTestRun">
                  {{ testRunSubmitting ? t("settings.toolCatalog.state.running") : t("settings.toolCatalog.action.runTool") }}
                </button>
              </footer>
            </form>
            <section
              v-if="cliConsoleProcessId || cliConsoleLines.length || cliConsoleError"
              class="cli-console"
            >
              <header>
                <strong>{{ t("settings.toolCatalog.section.cliConsole") }}</strong>
                <span>{{ t("settings.toolCatalog.state.cliProcess", { process: cliConsoleProcessId ?? "-" }) }}</span>
              </header>
              <p v-if="cliConsoleError" class="settings-state--error test-run-error">{{ cliConsoleError }}</p>
              <pre v-if="cliConsoleText">{{ cliConsoleText }}</pre>
              <div v-else class="drawer-empty">{{ t("settings.toolCatalog.state.waitingForCliOutput") }}</div>
            </section>
            <section v-if="lastTestRun" class="test-run-result">
              <header>
                <strong>{{ lastTestRun.id }}</strong>
                <span><StatusDot :tone="lastTestRunTone" />{{ titleize(lastTestRun.status) }}</span>
              </header>
              <pre v-if="lastTestRun.error">{{ formatPayload(lastTestRun.error) }}</pre>
              <pre v-else-if="lastTestRun.result">{{ formatPayload(lastTestRun.result) }}</pre>
              <pre v-else>{{ formatPayload(lastTestRun.output_payload) }}</pre>
            </section>
          </section>

          <section class="drawer-section">
            <div class="drawer-section-heading">
              <h3>{{ t("settings.toolCatalog.section.recentRuns") }}</h3>
              <button type="button" :disabled="!selectedToolId || runsLoading" @click="refreshSelectedRuns">
                <RefreshCcw :size="13" />
              </button>
            </div>
            <div v-if="runsLoading" class="drawer-empty">{{ t("settings.toolCatalog.state.loadingRuns", { tool: selectedToolId ?? "" }) }}</div>
            <div v-else-if="runsError" class="drawer-empty error">{{ runsError }}</div>
            <DataTable
              v-else-if="runRows.length"
              :columns="drawerRunColumns"
              :rows="runRows"
              section-id="tool-runs"
              allow-raw-keys
              :page-size="4"
            />
            <div v-else class="drawer-empty">{{ t("settings.toolCatalog.state.noRuns") }}</div>
          </section>

          <section class="drawer-section">
            <h3>{{ t("settings.toolCatalog.section.inputSchema") }}</h3>
            <pre>{{ selectedFunctionSchemaText }}</pre>
          </section>
        </template>

        <div v-else class="drawer-empty drawer-empty--tall">
          {{ t("settings.toolCatalog.state.selectFunctionOrSource") }}
        </div>
      </aside>
    </section>

    <Teleport to="body">
      <section v-if="sourceEditorOpen" class="source-editor-backdrop" @click.self="closeSourceEditor">
        <form class="source-editor-drawer" @submit.prevent="saveSourceEditor">
          <header class="source-editor-header">
            <div>
              <h2>{{ sourceEditorTitle }}</h2>
              <p>{{ t("settings.toolCatalog.sourceEditor.subtitle") }}</p>
            </div>
            <button type="button" :aria-label="t('settings.toolCatalog.sourceEditor.close')" @click="closeSourceEditor">
              <X :size="16" />
            </button>
          </header>

          <p v-if="sourceEditorError" class="source-editor-error">{{ sourceEditorError }}</p>

          <section class="source-editor-section">
            <h3>{{ t("table.source") }}</h3>
            <div class="source-editor-grid">
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.table.sourceId") }}</span>
                <input v-model.trim="sourceEditor.sourceId" :disabled="sourceEditor.mode === 'edit'" required />
              </label>
              <label class="source-editor-field">
                <span>{{ t("table.kind") }}</span>
                <select v-model="sourceEditor.kind" :disabled="sourceEditor.mode === 'edit'">
                  <option value="openapi">OpenAPI</option>
                  <option value="mcp">MCP</option>
                  <option value="cli">CLI</option>
                </select>
              </label>
              <label class="source-editor-field">
                <span>{{ t("table.displayName") }}</span>
                <input v-model.trim="sourceEditor.displayName" required />
              </label>
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.providerName") }}</span>
                <input v-model.trim="sourceEditor.providerName" required />
              </label>
            </div>
          </section>

          <section class="source-editor-section">
            <h3>{{ sourceEditor.kind === "openapi" ? t("settings.toolCatalog.sourceEditor.openapiProvider") : sourceEditor.kind === "mcp" ? t("settings.toolCatalog.sourceEditor.mcpProvider") : t("settings.toolCatalog.sourceEditor.cliProvider") }}</h3>
            <div v-if="sourceEditor.kind === 'openapi'" class="source-editor-grid single">
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.specLocation") }}</span>
                <input v-model.trim="sourceEditor.specLocation" placeholder="https://example.com/openapi.json" required />
              </label>
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.baseUrl") }}</span>
                <input v-model.trim="sourceEditor.baseUrl" :placeholder="t('settings.toolCatalog.common.optional')" />
              </label>
            </div>
            <label v-else-if="sourceEditor.kind === 'mcp'" class="source-editor-field">
              <span>{{ t("settings.toolCatalog.sourceEditor.commandArgv") }}</span>
              <textarea v-model="sourceEditor.commandText" rows="5" placeholder="python&#10;-m&#10;server" required />
            </label>
            <div v-else class="source-editor-grid">
              <label class="source-editor-field wide">
                <span>{{ t("settings.toolCatalog.sourceEditor.commandArgv") }}</span>
                <textarea v-model="sourceEditor.commandText" rows="4" placeholder="python" required />
              </label>
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.allowedSubcommands") }}</span>
                <input v-model.trim="sourceEditor.allowedSubcommands" :placeholder="t('settings.toolCatalog.common.commaSeparated')" required />
              </label>
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.deniedFlags") }}</span>
                <input v-model.trim="sourceEditor.deniedFlags" :placeholder="t('settings.toolCatalog.common.commaSeparated')" />
              </label>
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.workingDirectory") }}</span>
                <input v-model.trim="sourceEditor.workingDirectory" :placeholder="t('settings.toolCatalog.common.optional')" />
              </label>
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.allowedRoots") }}</span>
                <input v-model.trim="sourceEditor.allowedRoots" :placeholder="t('settings.toolCatalog.common.commaSeparated')" />
              </label>
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.outputLimitBytes") }}</span>
                <input v-model.trim="sourceEditor.outputLimitBytes" inputmode="numeric" :placeholder="t('settings.toolCatalog.common.optional')" />
              </label>
            </div>
          </section>

          <section class="source-editor-section">
            <h3>{{ t("settings.toolCatalog.sourceEditor.runtimePolicy") }}</h3>
            <div class="source-editor-grid">
              <label class="source-editor-field">
                <span>{{ t("settings.toolCatalog.sourceEditor.timeoutSeconds") }}</span>
                <input v-model.trim="sourceEditor.timeoutSeconds" inputmode="numeric" :placeholder="t('settings.toolCatalog.common.optional')" />
              </label>
              <label class="source-editor-field">
                <span>{{ t("table.maxConcurrency") }}</span>
                <input v-model.trim="sourceEditor.maxConcurrency" inputmode="numeric" :placeholder="t('settings.toolCatalog.common.optional')" />
              </label>
              <label class="source-editor-field wide">
                <span>{{ t("settings.toolCatalog.sourceEditor.defaultEffectIds") }}</span>
                <input v-model.trim="sourceEditor.defaultEffectIds" :placeholder="t('settings.toolCatalog.common.commaSeparated')" />
              </label>
              <label class="source-editor-field wide">
                <span>{{ t("settings.toolCatalog.sourceEditor.runtimeRequirements") }}</span>
                <input v-model.trim="sourceEditor.runtimeRequirements" :placeholder="t('settings.toolCatalog.common.commaSeparated')" />
              </label>
            </div>
          </section>

          <footer class="source-editor-actions">
            <button type="button" :disabled="sourceEditorSaving" @click="closeSourceEditor">{{ t("common.cancel") }}</button>
            <button type="submit" :disabled="sourceEditorSaving">
              {{ sourceEditorSaving ? t("settings.toolCatalog.state.saving") : t("settings.toolCatalog.action.saveSource") }}
            </button>
          </footer>
        </form>
      </section>
    </Teleport>
  </main>
</template>

<style scoped>
.tool-settings {
  display: grid;
  grid-template-rows: auto 24px 76px minmax(0, 1fr);
  gap: 10px;
  height: calc(100dvh - var(--shell-topbar-height));
  overflow: hidden;
  padding: 12px 16px 14px;
}

.tool-page-header,
.tool-header-actions,
.tool-catalog-toolbar,
.tool-view-tabs,
.drawer-header,
.drawer-action-row,
.drawer-section-heading,
.tool-slot-card header,
.tool-slot-card header > span,
.cli-console header,
.test-run-result header,
.test-run-result header span {
  display: flex;
  align-items: center;
}

.tool-page-header {
  justify-content: space-between;
  gap: 14px;
  min-height: 38px;
}

.tool-title-block h1 {
  font-size: 20px;
  line-height: 1.1;
}

.tool-title-block p {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.tool-header-actions {
  justify-content: flex-end;
  gap: 8px;
}

.tool-notice-line {
  display: grid;
  align-items: center;
  min-height: 24px;
  padding: 0 2px;
  color: var(--text-secondary);
  font-size: 12px;
}

.tool-notice-line.empty {
  visibility: hidden;
}

.tool-notice-line p {
  margin: 0;
}

.tool-metric-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  min-height: 0;
}

.tool-metric {
  display: grid;
  align-content: center;
  gap: 5px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 88%, transparent);
}

.tool-metric span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 11px;
}

.tool-metric strong {
  color: var(--text-primary);
  font-size: 22px;
  line-height: 1;
}

.tool-metric em {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-workspace {
  display: grid;
  grid-template-columns: minmax(720px, 1fr) minmax(430px, 480px);
  gap: 10px;
  min-height: 0;
}

.tool-catalog-panel,
.tool-detail-drawer {
  min-height: 0;
  overflow: hidden;
}

.tool-catalog-panel {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 9px;
  padding: 10px 12px;
}

.tool-catalog-toolbar {
  justify-content: space-between;
  gap: 12px;
}

.tool-view-tabs {
  gap: 4px;
  min-width: 0;
}

.tool-view-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.tool-view-tabs button span {
  color: var(--text-muted);
  font-size: 10.5px;
}

.tool-view-tabs button.active {
  border-color: color-mix(in srgb, var(--color-accent) 58%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--text-primary);
}

.tool-search {
  width: min(320px, 30vw);
}

.tool-search input,
.tool-filter-bar select,
.tool-policy-form input,
.tool-policy-form select,
.tool-slot-bind-row select,
.test-run-selects select,
.test-run-field input,
.test-run-field select,
.test-run-field textarea {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font: inherit;
  font-size: 11px;
}

.tool-search input,
.tool-filter-bar select,
.tool-policy-form input,
.tool-policy-form select,
.tool-slot-bind-row select,
.test-run-selects select,
.test-run-field input,
.test-run-field select {
  height: 30px;
  padding: 0 8px;
}

.tool-search input:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.tool-filter-bar {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  min-height: 45px;
}

.tool-filter-bar label,
.tool-policy-form label,
.test-run-selects label,
.test-run-field {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.tool-filter-bar span,
.tool-policy-form label span,
.test-run-selects span,
.test-run-field > span {
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 650;
}

.tool-table-shell {
  position: relative;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
}

.tool-table-shell :deep(.data-table) {
  height: 100%;
}

.tool-table-shell :deep(th),
.tool-table-shell :deep(td),
.tool-detail-drawer :deep(th),
.tool-detail-drawer :deep(td) {
  padding-block: 5px;
  font-size: 10.5px;
}

.tool-table-shell :deep(tbody tr.is-selected),
.tool-table-shell :deep(tbody tr:hover) {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

.tool-table-empty,
.drawer-empty {
  display: grid;
  place-items: center;
  min-height: 72px;
  padding: 14px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

.tool-table-empty {
  position: absolute;
  inset: 38px 0 0;
  background: color-mix(in srgb, var(--surface-panel) 72%, transparent);
}

.tool-table-empty.error,
.drawer-empty.error,
.settings-state--error {
  color: var(--color-danger);
}

.tool-detail-drawer {
  display: grid;
  align-content: start;
  gap: 8px;
  padding: 12px;
  overflow: auto;
  scrollbar-gutter: stable;
}

.drawer-header {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 42px;
}

.drawer-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
  color: var(--color-accent);
}

.drawer-header h2 {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-header p {
  margin-top: 3px;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-action-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
}

.drawer-action-row button,
.drawer-section-heading button,
.tool-slot-bind-row button,
.tool-policy-form footer button,
.test-run-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 11px;
  font-weight: 750;
}

.drawer-action-row button:not(:disabled),
.tool-policy-form footer button:not(:disabled),
.test-run-actions button:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-accent) 55%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--color-accent);
}

.drawer-action-row button.danger {
  border-color: color-mix(in srgb, var(--color-danger) 42%, var(--border-subtle));
  color: var(--color-danger);
}

.drawer-action-row button:disabled,
.drawer-section-heading button:disabled,
.tool-slot-bind-row button:disabled,
.tool-policy-form footer button:disabled,
.test-run-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.drawer-section {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}

.drawer-section h3,
.drawer-section-heading h3 {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-primary);
  font-size: 12px;
}

.drawer-section-heading {
  justify-content: space-between;
  gap: 10px;
}

.drawer-section-heading span {
  color: var(--text-muted);
  font-size: 10.5px;
}

.drawer-kv {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px 12px;
}

.drawer-kv div {
  min-width: 0;
}

.drawer-kv dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.drawer-kv dd {
  margin: 2px 0 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-section pre,
.cli-console pre,
.test-run-result pre {
  max-height: 180px;
  overflow: auto;
  margin: 0;
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-sidebar) 70%, transparent);
  color: var(--text-secondary);
  font-size: 10.5px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.tool-policy-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  min-width: 0;
}

.tool-policy-form label.wide,
.tool-policy-form footer,
.tool-policy-error {
  grid-column: 1 / -1;
}

.tool-policy-error,
.test-run-error,
.tool-slot-warning {
  margin: 0;
  font-size: 11px;
}

.tool-policy-form footer,
.test-run-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 118px;
  gap: 8px;
  align-items: center;
}

.tool-policy-form footer span,
.test-run-actions span {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-slot-list {
  display: grid;
  gap: 8px;
}

.tool-slot-card {
  display: grid;
  gap: 7px;
  padding: 8px 0 0;
  border-top: 1px dashed var(--border-subtle);
}

.tool-slot-card:first-child {
  padding-top: 0;
  border-top: 0;
}

.tool-slot-card header {
  justify-content: space-between;
  gap: 10px;
}

.tool-slot-card header div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.tool-slot-card strong {
  color: var(--text-primary);
  font-size: 12px;
}

.tool-slot-card small,
.tool-slot-warning {
  color: var(--text-muted);
  font-size: 10.5px;
}

.tool-slot-card header > span {
  gap: 5px;
  color: var(--text-secondary);
  font-size: 11px;
}

.tool-slot-bind-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 66px;
  gap: 7px;
}

.tool-slot-warning {
  color: var(--color-warning);
}

.test-run-form {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.test-run-selects {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
}

.test-run-field > span {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.test-run-field em {
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 500;
}

.test-run-field textarea {
  resize: vertical;
  min-height: 70px;
  padding: 7px 8px;
  line-height: 1.45;
}

.test-run-arguments {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.test-run-result {
  display: grid;
  gap: 8px;
}

.cli-console {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.cli-console header {
  justify-content: space-between;
  gap: 10px;
}

.cli-console header strong {
  color: var(--text-primary);
  font-size: 12px;
}

.cli-console header span {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cli-console pre {
  max-height: 220px;
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
}

.test-run-result header {
  justify-content: space-between;
  gap: 10px;
}

.test-run-result header strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.test-run-result header span {
  gap: 5px;
  color: var(--text-secondary);
  font-size: 11px;
}

.drawer-empty--tall {
  min-height: 300px;
}

.source-editor-backdrop {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  justify-content: flex-end;
  background: color-mix(in srgb, var(--surface-bg) 42%, transparent);
  backdrop-filter: blur(7px);
}

.source-editor-drawer {
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  gap: 14px;
  width: min(560px, calc(100vw - 28px));
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 18px;
  border: 0;
  border-left: 1px solid var(--border-default);
  background: var(--surface-raised);
  color: var(--text-primary);
  box-shadow: -24px 0 56px color-mix(in srgb, #000 30%, transparent);
}

.source-editor-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.source-editor-header h2,
.source-editor-header p {
  margin: 0;
}

.source-editor-header h2 {
  font-size: 18px;
}

.source-editor-header p {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.source-editor-header button {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  cursor: pointer;
}

.source-editor-error {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 40%, transparent);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  color: var(--color-danger);
  font-size: 12px;
}

.source-editor-section {
  display: grid;
  gap: 10px;
  align-content: start;
}

.source-editor-section h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  letter-spacing: 0;
}

.source-editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.source-editor-grid.single {
  grid-template-columns: 1fr;
}

.source-editor-field {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.source-editor-field.wide {
  grid-column: 1 / -1;
}

.source-editor-field span {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 650;
}

.source-editor-field input,
.source-editor-field select,
.source-editor-field textarea {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font: inherit;
  font-size: 12px;
}

.source-editor-field input,
.source-editor-field select {
  height: 34px;
  padding: 0 10px;
}

.source-editor-field textarea {
  resize: vertical;
  min-height: 112px;
  padding: 9px 10px;
  line-height: 1.45;
}

.source-editor-field input:disabled,
.source-editor-field select:disabled {
  opacity: 0.68;
}

.source-editor-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.source-editor-actions button {
  min-height: 36px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 750;
}

.source-editor-actions button[type="submit"] {
  border-color: var(--color-accent);
  background: var(--color-accent);
  color: var(--text-on-accent);
}

.source-editor-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

@media (max-width: 720px) {
  .tool-settings {
    height: auto;
    min-height: calc(100dvh - var(--shell-topbar-height));
    overflow: auto;
  }

  .tool-page-header,
  .tool-catalog-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .tool-header-actions {
    justify-content: flex-start;
  }

  .tool-metric-strip,
  .tool-filter-bar,
  .tool-workspace,
  .drawer-kv,
  .tool-policy-form,
  .test-run-selects,
  .test-run-arguments {
    grid-template-columns: 1fr;
  }

  .tool-search {
    width: 100%;
  }

  .source-editor-drawer {
    width: 100vw;
  }

  .source-editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
