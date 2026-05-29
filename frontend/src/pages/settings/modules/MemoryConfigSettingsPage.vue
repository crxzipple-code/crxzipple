<script setup lang="ts">
import {
  Ban,
  Database,
  Download,
  FileText,
  Layers,
  Plus,
  RefreshCcw,
  RotateCw,
  Save,
  Search,
  Send,
  Shield,
  Trash2,
} from "lucide-vue-next";
import { computed, onMounted, reactive, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  deleteMemoryPolicy,
  deleteMemorySpace,
  disableMemoryPolicy,
  disableMemorySpace,
  exportMemorySpace,
  getMemoryAccessSupport,
  listMemoryPolicies,
  listMemorySpaces,
  recallMemoryRuntime,
  rememberMemoryRuntime,
  rebuildMemorySpaceIndex,
  updateMemoryRuntimeDefaults,
  type MemoryAccessSupportPayload,
  type MemoryCredentialBindingOption,
  type MemoryRuntimeRecallPayload,
  type MemoryRuntimeRememberPayload,
  upsertMemoryPolicy,
  upsertMemorySpace,
  type MemoryOwnerJsonRecord,
  type MemoryPolicyApiPayload,
  type MemorySpaceApiPayload,
} from "../ownerApis/memory";
import {
  listAgentProfiles,
  type AgentProfileApiPayload,
} from "../ownerApis/agentProfiles";

type OwnerMode = "space" | "policy";
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";
type TableRow = Record<string, string | number | null>;

const { t } = useI18n();
const DEFAULT_RECALL_METADATA_KEYS = [
  "default_recall",
  "default_recall_enabled",
  "include_in_default_recall",
  "common_recall",
];
const SHARED_WRITE_METADATA_KEYS = [
  "default_write",
  "default_write_enabled",
  "allow_remember",
  "shared_write_enabled",
];
const DEFAULT_RECALL_METADATA_KEY = "default_recall_enabled";
const SHARED_WRITE_METADATA_KEY = "shared_write_enabled";

const spaces = ref<MemorySpaceApiPayload[]>([]);
const policies = ref<MemoryPolicyApiPayload[]>([]);
const agents = ref<AgentProfileApiPayload[]>([]);
const accessSupport = ref<MemoryAccessSupportPayload | null>(null);
const selectedMode = ref<OwnerMode>("space");
const selectedSpaceRef = ref<string | null>(null);
const selectedPolicyId = ref<string | null>(null);
const includeDisabled = ref(true);
const loading = ref(false);
const actionBusy = ref<"space" | "policy" | "delete" | "disable" | "rebuild" | "export" | null>(null);
const runtimeBusy = ref(false);
const memoryTestBusy = ref<"recall" | "remember" | null>(null);
const loadError = ref<string | null>(null);
const runtimeError = ref<string | null>(null);
const memoryTestError = ref<string | null>(null);
const notice = ref<string | null>(null);

const spaceForm = reactive({
  scope_ref: "",
  owner_kind: "agent",
  owner_id: "",
  engine_id: "file_markdown",
  retrieval_backend: "hybrid",
  storage_root: "",
  status: "active",
  metadata: "{}",
  default_recall_enabled: false,
  shared_write_enabled: false,
});

const policyForm = reactive({
  policy_id: "",
  target_kind: "global",
  target_id: "",
  recall_enabled: true,
  remember_enabled: true,
  max_recall_items: 6,
  retention: "engine_default",
  status: "active",
  metadata: "{}",
});

const runtimeForm = reactive({
  retrieval_backend: "keyword",
  vector_provider: "local",
  vector_credential_binding_id: "",
  vector_model: "",
  vector_base_url: "",
  vector_timeout_seconds: 30,
  watch_interval_seconds: 300,
});

const memoryTestForm = reactive({
  agent_id: "",
  scope_ref: "",
  query: "",
  max_items: 6,
  content: "",
  title: "",
  intent: "freeform",
  retention: "engine_default",
});

const memoryRecallResult = ref<MemoryRuntimeRecallPayload | null>(null);
const memoryRememberResult = ref<MemoryRuntimeRememberPayload | null>(null);

const selectedSpace = computed(() =>
  spaces.value.find((space) => space.scope_ref === selectedSpaceRef.value) ?? null,
);
const selectedPolicy = computed(() =>
  policies.value.find((policy) => policy.policy_id === selectedPolicyId.value) ?? null,
);
const agentOptions = computed(() =>
  [...agents.value]
    .sort((left, right) => left.id.localeCompare(right.id))
    .map((agent) => ({
      id: agent.id,
      label: `${agent.name || agent.id} · ${agent.id}`,
    })),
);
const spaceOptions = computed(() =>
  [...spaces.value]
    .sort((left, right) => left.scope_ref.localeCompare(right.scope_ref))
    .map((space) => ({
      id: space.scope_ref,
      label: `${space.scope_ref} · ${space.owner_kind}:${space.owner_id}`,
    })),
);
const policyTargetOptions = computed(() => {
  const options = policyForm.target_kind === "agent"
    ? agentOptions.value
    : policyForm.target_kind === "space"
      ? spaceOptions.value
      : [];
  const current = policyForm.target_id.trim();
  if (!current || options.some((option) => option.id === current)) return options;
  return [{ id: current, label: current }, ...options];
});
const activeSpaces = computed(() => spaces.value.filter((space) => space.status === "active").length);
const disabledSpaces = computed(() => spaces.value.filter((space) => space.status !== "active").length);
const activePolicies = computed(() => policies.value.filter((policy) => policy.status === "active").length);
const defaultEngine = computed(() => spaces.value[0]?.engine_id ?? "file_markdown");
const defaultBackend = computed(() => accessSupport.value?.runtime_defaults.retrieval_backend ?? spaces.value[0]?.retrieval_backend ?? "keyword");
const credentialRequirement = computed(() => accessSupport.value?.credential_requirement ?? null);
const credentialOptions = computed(() => accessSupport.value?.credential_bindings ?? []);
const credentialStatus = computed(() => {
  const requirement = credentialRequirement.value;
  if (runtimeForm.vector_provider !== "openai_compatible") return t("settings.memory.credential.local");
  if (!runtimeForm.vector_credential_binding_id) return t("settings.memory.credential.missing");
  if (!requirement) return t("settings.memory.credential.untracked");
  return requirement.ready ? t("settings.memory.credential.ready") : t("settings.memory.credential.blocked");
});
const memoryTestScopeSummary = computed(() => {
  const scope = memoryRecallResult.value?.scope ?? memoryRememberResult.value?.scope;
  if (!scope) return t("settings.memory.test.noScope");
  return `${scope.scope_ref} · ${scope.engine_id} · ${scope.retrieval_backend}`;
});
const memoryTestLayerSummary = computed(() => {
  const layers = memoryRecallResult.value?.searched_layers ?? [];
  if (!layers.length) return t("settings.memory.test.noLayers");
  return layers
    .map((layer) => `${layer.scope_ref}:${layer.layer_kind}:${layer.access}`)
    .join(" · ");
});
const effectivePolicyPreview = computed(() => {
  const targetScope = memoryTestForm.scope_ref.trim();
  const targetAgent = memoryTestForm.agent_id.trim();
  const active = policies.value
    .filter((policy) => policy.status === "active")
    .filter((policy) => {
      if (policy.target_kind === "global") return true;
      if (policy.target_kind === "space") return Boolean(targetScope) && policy.target_id === targetScope;
      if (policy.target_kind === "agent") return Boolean(targetAgent) && policy.target_id === targetAgent;
      return false;
    })
    .sort((left, right) => policyPriority(left) - policyPriority(right));
  return active[active.length - 1] ?? null;
});

const spaceColumns = computed(() => [
  { key: "Scope", label: t("settings.memory.table.scope") },
  { key: "Owner", label: t("settings.memory.table.owner") },
  { key: "Engine", label: t("settings.memory.table.engine") },
  { key: "Backend", label: t("settings.memory.table.backend") },
  { key: "Default Recall", label: t("settings.memory.table.defaultRecall") },
  { key: "Shared Write", label: t("settings.memory.table.sharedWrite") },
  { key: "Status", label: t("settings.memory.table.status") },
  { key: "Storage", label: t("settings.memory.table.storage") },
  { key: "Updated", label: t("settings.memory.table.updated") },
]);
const policyColumns = computed(() => [
  { key: "Policy", label: t("settings.memory.table.policy") },
  { key: "Target", label: t("settings.memory.table.target") },
  { key: "Recall", label: t("settings.memory.table.recall") },
  { key: "Remember", label: t("settings.memory.table.remember") },
  { key: "Max Items", label: t("settings.memory.table.maxItems") },
  { key: "Retention", label: t("settings.memory.table.retention") },
  { key: "Status", label: t("settings.memory.table.status") },
]);

const spaceRows = computed<TableRow[]>(() =>
  spaces.value.map((space) => ({
    __row_id: space.scope_ref,
    Scope: space.scope_ref,
    Owner: `${space.owner_kind}:${space.owner_id}`,
    Engine: space.engine_id,
    Backend: space.retrieval_backend,
    "Default Recall": yesNo(spaceGateEnabled(space, DEFAULT_RECALL_METADATA_KEYS)),
    "Shared Write": yesNo(spaceGateEnabled(space, SHARED_WRITE_METADATA_KEYS)),
    Status: statusLabel(space.status),
    Storage: space.storage_root,
    Updated: space.updated_at,
  })),
);
const policyRows = computed<TableRow[]>(() =>
  policies.value.map((policy) => ({
    __row_id: policy.policy_id,
    Policy: policy.policy_id,
    Target: policy.target_id ? `${policy.target_kind}:${policy.target_id}` : policy.target_kind,
    Recall: yesNo(policy.recall_enabled),
    Remember: yesNo(policy.remember_enabled),
    "Max Items": policy.max_recall_items,
    Retention: titleize(policy.retention),
    Status: statusLabel(policy.status),
  })),
);

onMounted(() => {
  void refreshMemoryGovernance();
});

async function refreshMemoryGovernance(): Promise<void> {
  loading.value = true;
  loadError.value = null;
  runtimeError.value = null;
  try {
    const [loadedSpaces, loadedPolicies, loadedAgents] = await Promise.all([
      listMemorySpaces(includeDisabled.value),
      listMemoryPolicies(includeDisabled.value),
      listAgentProfiles(),
    ]);
    spaces.value = loadedSpaces;
    policies.value = loadedPolicies;
    agents.value = loadedAgents;
    if (selectedSpaceRef.value && !loadedSpaces.some((space) => space.scope_ref === selectedSpaceRef.value)) {
      selectedSpaceRef.value = null;
    }
    if (selectedPolicyId.value && !loadedPolicies.some((policy) => policy.policy_id === selectedPolicyId.value)) {
      selectedPolicyId.value = null;
    }
    if (!selectedSpaceRef.value && loadedSpaces.length) {
      selectSpace(loadedSpaces[0]);
    } else if (selectedSpace.value) {
      setSpaceForm(selectedSpace.value);
    }
    if (!selectedPolicyId.value && loadedPolicies.length) {
      selectPolicy(loadedPolicies[0]);
    } else if (selectedPolicy.value) {
      setPolicyForm(selectedPolicy.value);
    }
    await refreshMemoryAccessSupport();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function refreshMemoryAccessSupport(): Promise<void> {
  try {
    const support = await getMemoryAccessSupport();
    accessSupport.value = support;
    setRuntimeForm(support);
  } catch (error) {
    runtimeError.value = error instanceof Error ? error.message : String(error);
  }
}

function selectSpaceRow(row: unknown): void {
  const scopeRef = rowValue(row, "__row_id") ?? rowValue(row, "Scope");
  const space = spaces.value.find((item) => item.scope_ref === scopeRef);
  if (!space) return;
  selectedMode.value = "space";
  selectSpace(space);
}

function selectPolicyRow(row: unknown): void {
  const policyId = rowValue(row, "__row_id") ?? rowValue(row, "Policy");
  const policy = policies.value.find((item) => item.policy_id === policyId);
  if (!policy) return;
  selectedMode.value = "policy";
  selectPolicy(policy);
}

function selectSpace(space: MemorySpaceApiPayload): void {
  selectedSpaceRef.value = space.scope_ref;
  setSpaceForm(space);
  setMemoryTestTargetFromSpace(space);
}

function selectPolicy(policy: MemoryPolicyApiPayload): void {
  selectedPolicyId.value = policy.policy_id;
  setPolicyForm(policy);
}

function newSpace(): void {
  selectedMode.value = "space";
  selectedSpaceRef.value = null;
  const agentId = firstAgentId();
  Object.assign(spaceForm, {
    scope_ref: agentId,
    owner_kind: "agent",
    owner_id: agentId,
    engine_id: "file_markdown",
    retrieval_backend: "hybrid",
    storage_root: "",
    status: "active",
    metadata: "{}",
    default_recall_enabled: false,
    shared_write_enabled: false,
  });
}

function newPolicy(): void {
  selectedMode.value = "policy";
  selectedPolicyId.value = null;
  Object.assign(policyForm, {
    policy_id: buildPolicyId("global", ""),
    target_kind: "global",
    target_id: "",
    recall_enabled: true,
    remember_enabled: true,
    max_recall_items: 6,
    retention: "engine_default",
    status: "active",
    metadata: "{}",
  });
}

function onSpaceOwnerKindChange(): void {
  if (spaceForm.owner_kind === "agent") {
    const nextAgent = spaceForm.owner_id.trim() || firstAgentId();
    spaceForm.owner_id = nextAgent;
    spaceForm.scope_ref = nextAgent;
    spaceForm.default_recall_enabled = false;
    spaceForm.shared_write_enabled = false;
    return;
  }
  if (!spaceForm.owner_id.trim()) {
    spaceForm.owner_id = spaceForm.scope_ref.trim() || spaceForm.owner_kind;
  }
  if (!spaceForm.scope_ref.trim() || agentOptions.value.some((agent) => agent.id === spaceForm.scope_ref)) {
    spaceForm.scope_ref = buildScopeRef(spaceForm.owner_kind, spaceForm.owner_id);
  }
}

function onSpaceOwnerIdChange(): void {
  if (spaceForm.owner_kind === "agent") {
    spaceForm.scope_ref = spaceForm.owner_id;
    return;
  }
  if (!selectedSpaceRef.value || !spaceForm.scope_ref.trim()) {
    spaceForm.scope_ref = buildScopeRef(spaceForm.owner_kind, spaceForm.owner_id);
  }
}

function onPolicyTargetKindChange(): void {
  if (policyForm.target_kind === "global") {
    policyForm.target_id = "";
  } else if (policyForm.target_kind === "agent") {
    policyForm.target_id = policyForm.target_id.trim() || firstAgentId();
  } else if (policyForm.target_kind === "space") {
    policyForm.target_id = policyForm.target_id.trim() || selectedSpaceRef.value || spaceOptions.value[0]?.id || "";
  }
  syncPolicyId(true);
}

function onPolicyTargetIdChange(): void {
  syncPolicyId(true);
}

function syncPolicyId(force = false): void {
  if (!force && policyForm.policy_id.trim() && !isGeneratedPolicyId(policyForm.policy_id)) return;
  policyForm.policy_id = buildPolicyId(policyForm.target_kind, policyForm.target_id);
}

async function saveSpace(): Promise<void> {
  const scopeRef = spaceForm.scope_ref.trim();
  if (!scopeRef) {
    loadError.value = t("settings.memory.error.scopeRequired");
    return;
  }
  actionBusy.value = "space";
  loadError.value = null;
  try {
    const saved = await upsertMemorySpace(scopeRef, {
      owner_kind: spaceForm.owner_kind,
      owner_id: spaceForm.owner_id.trim() || scopeRef,
      engine_id: spaceForm.engine_id.trim() || "file_markdown",
      retrieval_backend: spaceForm.retrieval_backend.trim() || "file",
      storage_root: optionalText(spaceForm.storage_root),
      status: spaceForm.status,
      metadata: spaceMetadataFromForm(),
    });
    notice.value = t("settings.memory.notice.spaceSaved", { id: saved.scope_ref });
    selectedSpaceRef.value = saved.scope_ref;
    await refreshMemoryGovernance();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

async function savePolicy(): Promise<void> {
  syncPolicyId();
  const policyId = policyForm.policy_id.trim();
  if (!policyId) {
    loadError.value = t("settings.memory.error.policyRequired");
    return;
  }
  actionBusy.value = "policy";
  loadError.value = null;
  try {
    const saved = await upsertMemoryPolicy(policyId, {
      target_kind: policyForm.target_kind,
      target_id: optionalText(policyForm.target_id),
      recall_enabled: policyForm.recall_enabled,
      remember_enabled: policyForm.remember_enabled,
      max_recall_items: Math.max(1, Number(policyForm.max_recall_items || 1)),
      retention: policyForm.retention,
      status: policyForm.status,
      metadata: parseMetadata(policyForm.metadata),
    });
    notice.value = t("settings.memory.notice.policySaved", { id: saved.policy_id });
    selectedPolicyId.value = saved.policy_id;
    await refreshMemoryGovernance();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

async function saveRuntimeDefaults(): Promise<void> {
  runtimeBusy.value = true;
  runtimeError.value = null;
  loadError.value = null;
  try {
    const saved = await updateMemoryRuntimeDefaults({
      retrieval_backend: runtimeForm.retrieval_backend,
      vector_provider: runtimeForm.vector_provider,
      vector_credential_binding_id: runtimeForm.vector_provider === "openai_compatible"
        ? optionalText(runtimeForm.vector_credential_binding_id)
        : null,
      vector_model: optionalText(runtimeForm.vector_model),
      vector_base_url: optionalText(runtimeForm.vector_base_url),
      vector_timeout_seconds: Math.max(1, Number(runtimeForm.vector_timeout_seconds || 30)),
      watch_interval_seconds: Math.max(0, Number(runtimeForm.watch_interval_seconds || 0)),
    });
    setRuntimeForm({
      runtime_defaults: saved,
      credential_bindings: credentialOptions.value,
      credential_requirement: credentialRequirement.value,
    });
    notice.value = t("settings.memory.notice.runtimeSaved");
    await refreshMemoryAccessSupport();
  } catch (error) {
    runtimeError.value = error instanceof Error ? error.message : String(error);
  } finally {
    runtimeBusy.value = false;
  }
}

async function rebuildSelectedSpace(): Promise<void> {
  const scopeRef = spaceForm.scope_ref.trim();
  if (!scopeRef) return;
  actionBusy.value = "rebuild";
  loadError.value = null;
  try {
    const result = await rebuildMemorySpaceIndex(scopeRef);
    notice.value = t("settings.memory.notice.spaceRebuilt", {
      id: result.scope_ref,
      count: result.indexed_file_count ?? result.file_count ?? 0,
    });
    await refreshMemoryGovernance();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

async function exportSelectedSpace(): Promise<void> {
  const scopeRef = spaceForm.scope_ref.trim();
  if (!scopeRef) return;
  actionBusy.value = "export";
  loadError.value = null;
  try {
    const result = await exportMemorySpace(scopeRef);
    notice.value = t("settings.memory.notice.spaceExported", {
      id: result.scope_ref,
      count: result.files?.length ?? 0,
    });
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

async function runMemoryRecallTest(): Promise<void> {
  const query = memoryTestForm.query.trim();
  if (!query) {
    memoryTestError.value = t("settings.memory.test.errorQueryRequired");
    return;
  }
  memoryTestBusy.value = "recall";
  memoryTestError.value = null;
  try {
    memoryRecallResult.value = await recallMemoryRuntime({
      agent_id: optionalText(memoryTestForm.agent_id),
      scope_ref: optionalText(memoryTestForm.scope_ref),
      query,
      max_items: Math.max(1, Number(memoryTestForm.max_items || 1)),
      intent: optionalText(memoryTestForm.intent),
    });
    notice.value = t("settings.memory.test.noticeRecall", {
      count: memoryRecallResult.value.items.length,
    });
  } catch (error) {
    memoryTestError.value = error instanceof Error ? error.message : String(error);
  } finally {
    memoryTestBusy.value = null;
  }
}

async function runMemoryRememberTest(): Promise<void> {
  const content = memoryTestForm.content.trim();
  if (!content) {
    memoryTestError.value = t("settings.memory.test.errorContentRequired");
    return;
  }
  memoryTestBusy.value = "remember";
  memoryTestError.value = null;
  try {
    memoryRememberResult.value = await rememberMemoryRuntime({
      agent_id: optionalText(memoryTestForm.agent_id),
      scope_ref: optionalText(memoryTestForm.scope_ref),
      content,
      title: optionalText(memoryTestForm.title),
      intent: memoryTestForm.intent,
      retention: memoryTestForm.retention,
    });
    notice.value = t("settings.memory.test.noticeRemember", {
      path: memoryRememberResult.value.write_result?.path ?? memoryRememberResult.value.status,
    });
  } catch (error) {
    memoryTestError.value = error instanceof Error ? error.message : String(error);
  } finally {
    memoryTestBusy.value = null;
  }
}

async function disableSelected(): Promise<void> {
  actionBusy.value = "disable";
  loadError.value = null;
  try {
    if (selectedMode.value === "space" && spaceForm.scope_ref.trim()) {
      const disabled = await disableMemorySpace(spaceForm.scope_ref.trim());
      notice.value = t("settings.memory.notice.spaceDisabled", { id: disabled.scope_ref });
    } else if (selectedMode.value === "policy" && policyForm.policy_id.trim()) {
      const disabled = await disableMemoryPolicy(policyForm.policy_id.trim());
      notice.value = t("settings.memory.notice.policyDisabled", { id: disabled.policy_id });
    }
    await refreshMemoryGovernance();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

async function deleteSelected(): Promise<void> {
  if (typeof window === "undefined") return;
  const id = selectedMode.value === "space" ? spaceForm.scope_ref.trim() : policyForm.policy_id.trim();
  if (!id) return;
  const messageKey = selectedMode.value === "space"
    ? "settings.memory.confirm.deleteSpace"
    : "settings.memory.confirm.deletePolicy";
  if (!window.confirm(t(messageKey, { id }))) return;
  actionBusy.value = "delete";
  loadError.value = null;
  try {
    if (selectedMode.value === "space") {
      await deleteMemorySpace(id);
      selectedSpaceRef.value = null;
      notice.value = t("settings.memory.notice.spaceDeleted", { id });
      newSpace();
    } else {
      await deleteMemoryPolicy(id);
      selectedPolicyId.value = null;
      notice.value = t("settings.memory.notice.policyDeleted", { id });
      newPolicy();
    }
    await refreshMemoryGovernance();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

function setSpaceForm(space: MemorySpaceApiPayload): void {
  Object.assign(spaceForm, {
    scope_ref: space.scope_ref,
    owner_kind: space.owner_kind,
    owner_id: space.owner_id,
    engine_id: space.engine_id,
    retrieval_backend: space.retrieval_backend,
    storage_root: space.storage_root,
    status: space.status,
    metadata: JSON.stringify(stripManagedSpaceGateMetadata(space.metadata ?? {}), null, 2),
    default_recall_enabled: spaceGateEnabled(space, DEFAULT_RECALL_METADATA_KEYS),
    shared_write_enabled: spaceGateEnabled(space, SHARED_WRITE_METADATA_KEYS),
  });
}

function setMemoryTestTargetFromSpace(space: MemorySpaceApiPayload): void {
  memoryTestForm.scope_ref = space.scope_ref;
  if (space.owner_kind === "agent") {
    memoryTestForm.agent_id = space.owner_id;
  }
  if (!memoryTestForm.query.trim()) {
    memoryTestForm.query = space.owner_id || space.scope_ref;
  }
}

function setPolicyForm(policy: MemoryPolicyApiPayload): void {
  Object.assign(policyForm, {
    policy_id: policy.policy_id,
    target_kind: policy.target_kind,
    target_id: policy.target_id ?? "",
    recall_enabled: policy.recall_enabled,
    remember_enabled: policy.remember_enabled,
    max_recall_items: policy.max_recall_items,
    retention: policy.retention,
    status: policy.status,
    metadata: JSON.stringify(policy.metadata ?? {}, null, 2),
  });
}

function setRuntimeForm(support: MemoryAccessSupportPayload): void {
  const defaults = support.runtime_defaults;
  Object.assign(runtimeForm, {
    retrieval_backend: defaults.retrieval_backend ?? "keyword",
    vector_provider: defaults.vector_provider ?? "local",
    vector_credential_binding_id: defaults.vector_credential_binding_id ?? "",
    vector_model: defaults.vector_model ?? "",
    vector_base_url: defaults.vector_base_url ?? "",
    vector_timeout_seconds: defaults.vector_timeout_seconds ?? 30,
    watch_interval_seconds: defaults.watch_interval_seconds ?? 300,
  });
}

function parseMetadata(value: string): MemoryOwnerJsonRecord {
  const normalized = value.trim();
  if (!normalized) return {};
  const parsed = JSON.parse(normalized) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(t("settings.memory.error.metadataObject"));
  }
  return parsed as MemoryOwnerJsonRecord;
}

function spaceMetadataFromForm(): MemoryOwnerJsonRecord {
  const metadata = stripManagedSpaceGateMetadata(parseMetadata(spaceForm.metadata));
  if (spaceForm.owner_kind !== "agent" && spaceForm.default_recall_enabled) {
    metadata[DEFAULT_RECALL_METADATA_KEY] = true;
  }
  if (spaceForm.owner_kind !== "agent" && spaceForm.shared_write_enabled) {
    metadata[SHARED_WRITE_METADATA_KEY] = true;
  }
  return metadata;
}

function stripManagedSpaceGateMetadata(
  metadata: MemoryOwnerJsonRecord,
): MemoryOwnerJsonRecord {
  const next: MemoryOwnerJsonRecord = { ...metadata };
  for (const key of [...DEFAULT_RECALL_METADATA_KEYS, ...SHARED_WRITE_METADATA_KEYS]) {
    delete next[key];
  }
  return next;
}

function spaceGateEnabled(
  space: Pick<MemorySpaceApiPayload, "owner_kind" | "metadata">,
  keys: string[],
): boolean {
  if (space.owner_kind === "agent") return false;
  return metadataFlag(space.metadata ?? {}, keys);
}

function metadataFlag(metadata: MemoryOwnerJsonRecord, keys: string[]): boolean {
  return keys.some((key) => {
    const value = metadata[key];
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") {
      return ["1", "true", "yes", "on", "enabled"].includes(value.trim().toLowerCase());
    }
    return false;
  });
}

function rowValue(row: unknown, key: string): string | null {
  if (!row || typeof row !== "object" || Array.isArray(row)) return null;
  const value = (row as Record<string, unknown>)[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function optionalText(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function firstAgentId(): string {
  return agentOptions.value[0]?.id ?? "";
}

function buildScopeRef(ownerKind: string, ownerId: string): string {
  const slug = slugId(ownerId || ownerKind);
  if (ownerKind === "agent") return slug;
  if (ownerKind === "shared") return slug || "shared";
  return `${ownerKind}-${slug || "default"}`;
}

function buildPolicyId(targetKind: string, targetId: string | null | undefined): string {
  if (targetKind === "global") return "memory-global-default";
  return `memory-${targetKind}-${slugId(targetId || "default")}-policy`;
}

function isGeneratedPolicyId(value: string): boolean {
  return /^memory-(global-default|(space|agent)-[a-z0-9_.-]+-policy)$/.test(value.trim());
}

function slugId(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function policyPriority(policy: MemoryPolicyApiPayload): number {
  if (policy.target_kind === "global") return 0;
  if (policy.target_kind === "space") return 1;
  if (policy.target_kind === "agent") return 2;
  return -1;
}

function yesNo(value: boolean): string {
  return value ? t("common.yes") : t("common.no");
}

function titleize(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusLabel(value: string): string {
  if (value === "active") return t("settings.memory.status.active");
  if (value === "disabled") return t("settings.memory.status.disabled");
  return titleize(value);
}

function credentialOptionLabel(option: MemoryCredentialBindingOption): string {
  if (!option.masked_preview) return option.label;
  return `${option.label} - ${option.masked_preview}`;
}

function toneForStatus(value: string): StatusTone {
  const normalized = value.toLowerCase();
  if (normalized === "active" || normalized === "ready") return "success";
  if (normalized === "disabled") return "warning";
  if (normalized === "error" || normalized === "failed") return "danger";
  return normalized ? "info" : "neutral";
}
</script>

<template>
  <main class="settings-module memory-governance scroll-area">
    <header class="settings-page-header memory-header">
      <div>
        <h1>{{ t("settings.memory.title") }}</h1>
        <p>{{ t("settings.memory.subtitle") }}</p>
      </div>
      <div class="settings-header-actions">
        <label class="include-disabled">
          <input v-model="includeDisabled" type="checkbox" @change="refreshMemoryGovernance" />
          <span>{{ t("settings.memory.includeDisabled") }}</span>
        </label>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshMemoryGovernance">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="14" />
          {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section class="memory-summary-grid">
      <article class="settings-panel memory-summary-card">
        <Database :size="18" />
        <div>
          <small>{{ t("settings.memory.summary.spaces") }}</small>
          <strong>{{ spaces.length }}</strong>
          <p>{{ activeSpaces }} {{ t("settings.memory.summary.active") }} / {{ disabledSpaces }} {{ t("settings.memory.summary.disabled") }}</p>
        </div>
      </article>
      <article class="settings-panel memory-summary-card">
        <Shield :size="18" />
        <div>
          <small>{{ t("settings.memory.summary.policies") }}</small>
          <strong>{{ policies.length }}</strong>
          <p>{{ activePolicies }} {{ t("settings.memory.summary.active") }}</p>
        </div>
      </article>
      <article class="settings-panel memory-summary-card">
        <Layers :size="18" />
        <div>
          <small>{{ t("settings.memory.summary.engine") }}</small>
          <strong>{{ defaultEngine }}</strong>
          <p>{{ t("settings.memory.summary.firstSpace") }}</p>
        </div>
      </article>
      <article class="settings-panel memory-summary-card">
        <FileText :size="18" />
        <div>
          <small>{{ t("settings.memory.summary.backend") }}</small>
          <strong>{{ defaultBackend }}</strong>
          <p>{{ t("settings.memory.summary.ownerApi") }}</p>
        </div>
      </article>
    </section>

    <div v-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
    <div v-if="notice" class="settings-state settings-state--success">{{ notice }}</div>

    <section class="memory-layout">
      <div class="memory-tables">
        <article class="settings-panel memory-table-panel memory-spaces-panel">
          <div class="panel-heading">
            <div>
              <h2>{{ t("settings.memory.spaces.title") }}</h2>
              <p>{{ t("settings.memory.spaces.subtitle") }}</p>
            </div>
            <UiButton size="sm" variant="secondary" @click="newSpace">
              <Plus :size="13" />{{ t("settings.memory.action.newSpace") }}
            </UiButton>
          </div>
          <DataTable
            v-if="spaceRows.length"
            :columns="spaceColumns"
            :rows="spaceRows"
            section-id="memory-spaces"
            :page-size="8"
            clickable-rows
            :selected-row-id="selectedSpaceRef"
            @row-click="selectSpaceRow"
          />
          <div v-else-if="loading" class="settings-state settings-state--compact">{{ t("settings.memory.loading.spaces") }}</div>
          <div v-else class="settings-state settings-state--compact">{{ t("settings.memory.empty.spaces") }}</div>
        </article>

        <article class="settings-panel memory-table-panel memory-policies-panel">
          <div class="panel-heading">
            <div>
              <h2>{{ t("settings.memory.policies.title") }}</h2>
              <p>{{ t("settings.memory.policies.subtitle") }}</p>
            </div>
            <UiButton size="sm" variant="secondary" @click="newPolicy">
              <Plus :size="13" />{{ t("settings.memory.action.newPolicy") }}
            </UiButton>
          </div>
          <DataTable
            v-if="policyRows.length"
            :columns="policyColumns"
            :rows="policyRows"
            section-id="memory-policies"
            :page-size="6"
            clickable-rows
            :selected-row-id="selectedPolicyId"
            @row-click="selectPolicyRow"
          />
          <div v-else-if="loading" class="settings-state settings-state--compact">{{ t("settings.memory.loading.policies") }}</div>
          <div v-else class="settings-state settings-state--compact">{{ t("settings.memory.empty.policies") }}</div>
        </article>

        <article class="settings-panel memory-test-panel">
          <div class="panel-heading panel-heading--compact">
            <div>
              <h2>{{ t("settings.memory.test.title") }}</h2>
              <p>{{ t("settings.memory.test.subtitle") }}</p>
            </div>
            <span class="memory-test-scope">{{ memoryTestScopeSummary }}</span>
          </div>
          <div class="memory-test-body">
            <div class="memory-test-controls">
              <div class="field-row">
                <label>
                  <span>{{ t("settings.memory.test.agentId") }}</span>
                  <select v-model="memoryTestForm.agent_id">
                    <option value="">{{ t("settings.memory.placeholder.selectAgentOptional") }}</option>
                    <option v-for="agent in agentOptions" :key="agent.id" :value="agent.id">
                      {{ agent.label }}
                    </option>
                  </select>
                </label>
                <label>
                  <span>{{ t("settings.memory.test.scopeRef") }}</span>
                  <select v-model="memoryTestForm.scope_ref">
                    <option value="">{{ t("settings.memory.placeholder.autoPrivateScope") }}</option>
                    <option v-for="space in spaceOptions" :key="space.id" :value="space.id">
                      {{ space.label }}
                    </option>
                  </select>
                </label>
              </div>
              <div class="field-row">
                <label>
                  <span>{{ t("settings.memory.test.query") }}</span>
                  <input v-model.trim="memoryTestForm.query" :placeholder="t('settings.memory.test.queryPlaceholder')" />
                </label>
                <label>
                  <span>{{ t("settings.memory.field.maxRecallItems") }}</span>
                  <input v-model.number="memoryTestForm.max_items" min="1" max="100" type="number" />
                </label>
              </div>
              <label>
                <span>{{ t("settings.memory.test.content") }}</span>
                <textarea v-model="memoryTestForm.content" :placeholder="t('settings.memory.test.contentPlaceholder')" />
              </label>
              <div class="field-row">
                <label>
                  <span>{{ t("settings.memory.test.titleField") }}</span>
                  <input v-model.trim="memoryTestForm.title" :placeholder="t('settings.memory.test.titlePlaceholder')" />
                </label>
                <label>
                  <span>{{ t("settings.memory.field.retention") }}</span>
                  <select v-model="memoryTestForm.retention">
                    <option value="engine_default">engine_default</option>
                    <option value="durable">durable</option>
                    <option value="session">session</option>
                    <option value="temporary">temporary</option>
                  </select>
                </label>
              </div>
              <div class="memory-test-actions">
                <UiButton type="button" size="sm" variant="secondary" :disabled="memoryTestBusy !== null" @click="runMemoryRecallTest">
                  <Search :size="13" />{{ t("settings.memory.test.recall") }}
                </UiButton>
                <UiButton type="button" size="sm" variant="primary" :disabled="memoryTestBusy !== null" @click="runMemoryRememberTest">
                  <Send :size="13" />{{ t("settings.memory.test.remember") }}
                </UiButton>
                <span v-if="effectivePolicyPreview" class="memory-policy-preview">
                  {{ t("settings.memory.test.policyPreview", { id: effectivePolicyPreview.policy_id }) }}
                </span>
              </div>
            </div>
            <div class="memory-test-output">
              <p v-if="memoryTestError" class="runtime-hint runtime-hint--error">{{ memoryTestError }}</p>
              <p v-else-if="memoryRememberResult?.write_result" class="runtime-hint">
                {{ t("settings.memory.test.lastWrite", {
                  path: memoryRememberResult.write_result.path,
                  line: memoryRememberResult.write_result.line_start,
                }) }}
              </p>
              <p v-if="memoryRecallResult?.searched_layers?.length" class="runtime-hint">
                {{ t("settings.memory.test.searchedLayers", { layers: memoryTestLayerSummary }) }}
              </p>
              <div v-if="memoryRecallResult?.items.length" class="memory-recall-list">
                <article
                  v-for="item in memoryRecallResult.items"
                  :key="`${item.source_scope_ref ?? memoryRecallResult.scope.scope_ref}:${item.citation}`"
                  class="memory-recall-item"
                >
                  <header>
                    <strong>{{ item.source_scope_ref ?? memoryRecallResult.scope.scope_ref }} · {{ item.path }}</strong>
                    <span>{{ item.citation }}</span>
                  </header>
                  <small v-if="item.source_layer_kind" class="memory-recall-source">
                    {{ t("settings.memory.test.sourceLayer", {
                      layer: item.source_layer_kind,
                      owner: item.source_owner_kind ?? "-",
                    }) }}
                  </small>
                  <p>{{ item.text }}</p>
                </article>
              </div>
              <div v-else class="settings-state settings-state--compact memory-test-empty">
                {{ t("settings.memory.test.empty") }}
              </div>
            </div>
          </div>
        </article>
      </div>

      <aside class="memory-side">
        <article class="settings-panel memory-runtime-panel">
          <div class="panel-heading panel-heading--compact">
            <div>
              <h2>{{ t("settings.memory.runtime.title") }}</h2>
              <p>
                <StatusDot :tone="credentialRequirement?.ready ? 'success' : runtimeForm.vector_provider === 'openai_compatible' ? 'warning' : 'info'" />
                {{ credentialStatus }}
              </p>
            </div>
            <UiButton size="sm" variant="secondary" :disabled="runtimeBusy" @click="saveRuntimeDefaults">
              <Save :size="13" />{{ t("settings.memory.action.saveRuntime") }}
            </UiButton>
          </div>
          <form class="runtime-form" @submit.prevent="saveRuntimeDefaults">
            <div class="field-row">
              <label>
                <span>{{ t("settings.memory.field.backend") }}</span>
                <select v-model="runtimeForm.retrieval_backend">
                  <option value="keyword">keyword</option>
                  <option value="hybrid">hybrid</option>
                  <option value="vector">vector</option>
                </select>
              </label>
              <label>
                <span>{{ t("settings.memory.field.vectorProvider") }}</span>
                <select v-model="runtimeForm.vector_provider">
                  <option value="local">local</option>
                  <option value="openai_compatible">openai_compatible</option>
                </select>
              </label>
            </div>
            <label>
              <span>{{ t("settings.memory.field.accessBinding") }}</span>
              <select
                v-model="runtimeForm.vector_credential_binding_id"
                :disabled="runtimeForm.vector_provider !== 'openai_compatible'"
              >
                <option value="">{{ t("settings.memory.credential.none") }}</option>
                <option
                  v-for="option in credentialOptions"
                  :key="option.binding_id"
                  :value="option.binding_id"
                >
                  {{ credentialOptionLabel(option) }}
                </option>
              </select>
            </label>
            <div class="field-row">
              <label>
                <span>{{ t("settings.memory.field.vectorModel") }}</span>
                <input v-model.trim="runtimeForm.vector_model" :placeholder="t('settings.memory.placeholder.vectorModel')" />
              </label>
              <label>
                <span>{{ t("settings.memory.field.vectorTimeout") }}</span>
                <input v-model.number="runtimeForm.vector_timeout_seconds" min="1" type="number" />
              </label>
            </div>
            <p v-if="credentialRequirement?.reason" class="runtime-hint">{{ credentialRequirement.reason }}</p>
            <p v-else-if="runtimeError" class="runtime-hint runtime-hint--error">{{ runtimeError }}</p>
          </form>
        </article>

        <article class="settings-panel memory-editor-panel">
        <div class="editor-switch">
          <button type="button" :class="{ active: selectedMode === 'space' }" @click="selectedMode = 'space'">
            {{ t("settings.memory.mode.space") }}
          </button>
          <button type="button" :class="{ active: selectedMode === 'policy' }" @click="selectedMode = 'policy'">
            {{ t("settings.memory.mode.policy") }}
          </button>
        </div>

        <form v-if="selectedMode === 'space'" class="owner-form" @submit.prevent="saveSpace">
          <header>
            <div>
              <h2>{{ selectedSpace ? t("settings.memory.editor.spaceEdit") : t("settings.memory.editor.spaceNew") }}</h2>
              <p><StatusDot :tone="toneForStatus(spaceForm.status)" />{{ statusLabel(spaceForm.status) }}</p>
            </div>
          </header>
          <label>
            <span>{{ t("settings.memory.field.scopeRef") }}</span>
            <input v-model.trim="spaceForm.scope_ref" required readonly :placeholder="t('settings.memory.placeholder.autoScopeRef')" />
          </label>
          <div class="field-row">
            <label>
              <span>{{ t("settings.memory.field.ownerKind") }}</span>
              <select v-model="spaceForm.owner_kind" @change="onSpaceOwnerKindChange">
                <option value="agent">agent</option>
                <option value="shared">shared</option>
                <option value="project">project</option>
                <option value="team">team</option>
                <option value="system">system</option>
              </select>
            </label>
            <label>
              <span>{{ t("settings.memory.field.ownerId") }}</span>
              <select
                v-if="spaceForm.owner_kind === 'agent'"
                v-model="spaceForm.owner_id"
                required
                @change="onSpaceOwnerIdChange"
              >
                <option value="">{{ t("settings.memory.placeholder.selectAgent") }}</option>
                <option v-for="agent in agentOptions" :key="agent.id" :value="agent.id">
                  {{ agent.label }}
                </option>
              </select>
              <input
                v-else
                v-model.trim="spaceForm.owner_id"
                required
                :placeholder="t('settings.memory.placeholder.ownerId')"
                @change="onSpaceOwnerIdChange"
              />
            </label>
          </div>
          <div class="field-row">
            <label>
              <span>{{ t("settings.memory.field.engine") }}</span>
              <select v-model="spaceForm.engine_id">
                <option value="file_markdown">file_markdown</option>
              </select>
            </label>
            <label>
              <span>{{ t("settings.memory.field.backend") }}</span>
              <select v-model="spaceForm.retrieval_backend">
                <option value="keyword">keyword</option>
                <option value="hybrid">hybrid</option>
                <option value="vector">vector</option>
              </select>
            </label>
          </div>
          <label>
            <span>{{ t("settings.memory.field.storageRoot") }}</span>
            <input v-model.trim="spaceForm.storage_root" :placeholder="t('settings.memory.placeholder.autoStorage')" />
          </label>
          <label>
            <span>{{ t("settings.memory.field.status") }}</span>
            <select v-model="spaceForm.status">
              <option value="active">{{ t("settings.memory.status.active") }}</option>
              <option value="disabled">{{ t("settings.memory.status.disabled") }}</option>
            </select>
          </label>
          <div class="toggle-grid">
            <label :class="{ 'toggle-muted': spaceForm.owner_kind === 'agent' }">
              <input
                v-model="spaceForm.default_recall_enabled"
                type="checkbox"
                :disabled="spaceForm.owner_kind === 'agent'"
              />
              <span>{{ t("settings.memory.field.defaultRecallLayer") }}</span>
            </label>
            <label :class="{ 'toggle-muted': spaceForm.owner_kind === 'agent' }">
              <input
                v-model="spaceForm.shared_write_enabled"
                type="checkbox"
                :disabled="spaceForm.owner_kind === 'agent'"
              />
              <span>{{ t("settings.memory.field.sharedWriteLayer") }}</span>
            </label>
          </div>
          <div class="editor-actions">
            <UiButton type="submit" size="sm" variant="primary" :disabled="actionBusy !== null">
              <Save :size="13" />{{ t("settings.memory.action.saveSpace") }}
            </UiButton>
            <UiButton type="button" size="sm" variant="secondary" :disabled="!spaceForm.scope_ref || actionBusy !== null" @click="rebuildSelectedSpace">
              <RotateCw :size="13" />{{ t("settings.memory.action.rebuild") }}
            </UiButton>
            <UiButton type="button" size="sm" variant="secondary" :disabled="!spaceForm.scope_ref || actionBusy !== null" @click="exportSelectedSpace">
              <Download :size="13" />{{ t("settings.memory.action.export") }}
            </UiButton>
            <UiButton type="button" size="sm" variant="secondary" :disabled="!spaceForm.scope_ref || actionBusy !== null" @click="disableSelected">
              <Ban :size="13" />{{ t("settings.memory.action.disable") }}
            </UiButton>
            <UiButton type="button" size="sm" variant="danger" :disabled="!spaceForm.scope_ref || actionBusy !== null" @click="deleteSelected">
              <Trash2 :size="13" />{{ t("settings.memory.action.delete") }}
            </UiButton>
          </div>
        </form>

        <form v-else class="owner-form" @submit.prevent="savePolicy">
          <header>
            <div>
              <h2>{{ selectedPolicy ? t("settings.memory.editor.policyEdit") : t("settings.memory.editor.policyNew") }}</h2>
              <p><StatusDot :tone="toneForStatus(policyForm.status)" />{{ statusLabel(policyForm.status) }}</p>
            </div>
          </header>
          <label>
            <span>{{ t("settings.memory.field.policyId") }}</span>
            <input v-model.trim="policyForm.policy_id" required readonly :placeholder="t('settings.memory.placeholder.autoPolicyId')" />
          </label>
          <div class="field-row">
            <label>
              <span>{{ t("settings.memory.field.targetKind") }}</span>
              <select v-model="policyForm.target_kind" @change="onPolicyTargetKindChange">
                <option value="global">global</option>
                <option value="space">space</option>
                <option value="agent">agent</option>
              </select>
            </label>
            <label>
              <span>{{ t("settings.memory.field.targetId") }}</span>
              <select
                v-model="policyForm.target_id"
                :disabled="policyForm.target_kind === 'global'"
                @change="onPolicyTargetIdChange"
              >
                <option value="">
                  {{ policyForm.target_kind === "global"
                    ? t("settings.memory.placeholder.globalPolicyTarget")
                    : t("settings.memory.placeholder.selectTarget") }}
                </option>
                <option v-for="option in policyTargetOptions" :key="option.id" :value="option.id">
                  {{ option.label }}
                </option>
              </select>
            </label>
          </div>
          <div class="toggle-grid">
            <label>
              <input v-model="policyForm.recall_enabled" type="checkbox" />
              <span>{{ t("settings.memory.field.recallEnabled") }}</span>
            </label>
            <label>
              <input v-model="policyForm.remember_enabled" type="checkbox" />
              <span>{{ t("settings.memory.field.rememberEnabled") }}</span>
            </label>
          </div>
          <div class="field-row">
            <label>
              <span>{{ t("settings.memory.field.maxRecallItems") }}</span>
              <input v-model.number="policyForm.max_recall_items" min="1" max="100" type="number" required />
            </label>
            <label>
              <span>{{ t("settings.memory.field.retention") }}</span>
              <select v-model="policyForm.retention">
                <option value="engine_default">engine_default</option>
                <option value="durable">durable</option>
                <option value="session">session</option>
                <option value="temporary">temporary</option>
              </select>
            </label>
          </div>
          <label>
            <span>{{ t("settings.memory.field.status") }}</span>
            <select v-model="policyForm.status">
              <option value="active">{{ t("settings.memory.status.active") }}</option>
              <option value="disabled">{{ t("settings.memory.status.disabled") }}</option>
            </select>
          </label>
          <div class="editor-actions">
            <UiButton type="submit" size="sm" variant="primary" :disabled="actionBusy !== null">
              <Save :size="13" />{{ t("settings.memory.action.savePolicy") }}
            </UiButton>
            <UiButton type="button" size="sm" variant="secondary" :disabled="!policyForm.policy_id || actionBusy !== null" @click="disableSelected">
              <Ban :size="13" />{{ t("settings.memory.action.disable") }}
            </UiButton>
            <UiButton type="button" size="sm" variant="danger" :disabled="!policyForm.policy_id || actionBusy !== null" @click="deleteSelected">
              <Trash2 :size="13" />{{ t("settings.memory.action.delete") }}
            </UiButton>
          </div>
        </form>
        </article>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.memory-governance {
  height: 100%;
  min-height: calc(100dvh - var(--shell-topbar-height));
  overflow: auto;
}

.memory-header {
  align-items: center;
}

.include-disabled {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}

.memory-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}

.memory-summary-card {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 72px;
  padding: 10px;
}

.memory-summary-card > svg {
  display: block;
  color: var(--color-accent);
}

.memory-summary-card small,
.memory-summary-card p,
.panel-heading p,
.owner-form p {
  color: var(--text-muted);
  font-size: 11px;
}

.memory-summary-card strong {
  display: block;
  overflow: hidden;
  margin: 2px 0;
  color: var(--text-primary);
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-layout {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-auto-flow: dense;
  gap: 8px;
  align-items: stretch;
}

.memory-tables {
  display: contents;
}

.memory-side {
  display: contents;
}

.memory-table-panel,
.memory-editor-panel,
.memory-runtime-panel,
.memory-test-panel {
  min-width: 0;
  overflow: hidden;
  padding: 0;
}

.memory-table-panel {
  min-height: 286px;
}

.memory-runtime-panel {
  grid-column: 8 / -1;
  grid-row: 2;
  min-height: 286px;
}

.memory-editor-panel {
  grid-column: 8 / -1;
  grid-row: 1;
  min-height: 286px;
}

.memory-test-panel {
  grid-column: 1 / -1;
  grid-row: 3;
  min-height: 300px;
}

.memory-spaces-panel {
  grid-column: 1 / 8;
  grid-row: 1;
}

.memory-policies-panel {
  grid-column: 1 / 8;
  grid-row: 2;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 54px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-heading h2,
.owner-form h2 {
  margin: 0;
  font-size: 15px;
}

.panel-heading--compact {
  min-height: 48px;
}

.memory-table-panel :deep(th),
.memory-table-panel :deep(td) {
  padding-block: 5px;
  font-size: 11px;
}

.editor-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  padding: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.editor-switch button {
  height: 30px;
  border: 1px solid transparent;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}

.editor-switch button.active {
  border-color: var(--border-accent);
  background: var(--surface-active);
  color: var(--text-primary);
}

.owner-form,
.runtime-form,
.memory-test-controls {
  display: grid;
  gap: 8px;
  padding: 12px;
}

.owner-form {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
}

.owner-form > header,
.owner-form > label:not(.metadata-field),
.owner-form > .field-row,
.owner-form > .toggle-grid,
.owner-form > .editor-actions {
  min-width: 0;
}

.owner-form > header,
.owner-form > label,
.owner-form > .field-row,
.owner-form > .toggle-grid,
.owner-form > .editor-actions {
  grid-column: span 2;
}

.owner-form > .field-row,
.owner-form > .toggle-grid {
  grid-column: span 2;
}

.owner-form header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.owner-form p {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 3px;
}

.owner-form label,
.runtime-form label,
.memory-test-controls label {
  display: grid;
  gap: 4px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 11px;
}

.owner-form input,
.owner-form select,
.owner-form textarea,
.runtime-form input,
.runtime-form select,
.memory-test-controls input,
.memory-test-controls select,
.memory-test-controls textarea {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font: inherit;
}

.owner-form input,
.owner-form select,
.runtime-form input,
.runtime-form select,
.memory-test-controls input,
.memory-test-controls select {
  height: 30px;
  padding: 0 8px;
}

.owner-form textarea,
.memory-test-controls textarea {
  min-height: 96px;
  resize: vertical;
  padding: 8px;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.toggle-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.toggle-grid label {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
}

.toggle-grid input {
  width: auto;
  height: auto;
}

.toggle-grid label.toggle-muted {
  opacity: 0.45;
}

.editor-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  justify-content: flex-end;
  padding-top: 2px;
}

.runtime-hint {
  margin: 0;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.runtime-hint--error {
  color: var(--color-danger);
}

.memory-test-scope {
  max-width: 260px;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-test-body {
  display: grid;
  grid-template-columns: minmax(0, 0.75fr) minmax(360px, 1.25fr);
  min-height: 244px;
}

.memory-test-controls {
  border-right: 1px solid var(--border-subtle);
}

.memory-test-controls textarea {
  min-height: 70px;
}

.memory-test-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
}

.memory-policy-preview {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-test-output {
  display: grid;
  align-content: start;
  gap: 8px;
  min-width: 0;
  min-height: 0;
  padding: 12px;
}

.memory-recall-list {
  display: grid;
  gap: 8px;
  max-height: 244px;
  overflow: auto;
  scrollbar-gutter: stable;
}

.memory-recall-item {
  display: grid;
  gap: 5px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.memory-recall-item header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.memory-recall-item strong,
.memory-recall-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-recall-item strong {
  color: var(--text-primary);
  font-size: 12px;
}

.memory-recall-item span,
.memory-recall-source,
.memory-recall-item p {
  color: var(--text-secondary);
  font-size: 11px;
}

.memory-recall-source {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-recall-item p {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  line-height: 1.45;
}

.memory-test-empty {
  min-height: 186px;
}

.settings-state {
  display: grid;
  place-items: center;
  min-height: 42px;
  margin-bottom: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  color: var(--text-muted);
  font-size: 12px;
}

.settings-state--compact {
  min-height: 108px;
  margin: 0;
  border: 0;
}

.settings-state--error {
  color: var(--color-danger);
}

.settings-state--success {
  color: var(--color-success);
}

@media (max-width: 1100px) {
  .memory-summary-grid,
  .memory-layout,
  .memory-test-body {
    grid-template-columns: 1fr;
  }

  .memory-spaces-panel,
  .memory-policies-panel,
  .memory-runtime-panel,
  .memory-editor-panel,
  .memory-test-panel {
    grid-column: 1 / -1;
    grid-row: auto;
  }

  .memory-test-controls {
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }
}
</style>
