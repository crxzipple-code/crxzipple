<script setup lang="ts">
import {
  Box,
  Import,
  MoreVertical,
  Plus,
  Power,
  RefreshCcw,
  Save,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";

import UiButton from "@/shared/ui/UiButton.vue";
import {
  createAgentProfile,
  deleteAgentProfile,
  disableAgentProfile,
  enableAgentProfile,
  exportAgentHome,
  getAgentProfile,
  getAgentProfileResolution,
  getAgentHome,
  listAgentProfiles,
  listAgentProfileEvents,
  syncAgentHome,
  updateAgentProfile,
  updateAgentHomeFiles,
  type AgentOwnerJsonRecord,
  type AgentAuthorizationGrantApiPayload,
  type AgentProfileApiPayload,
  type AgentProfileResolutionApiPayload,
  type AgentHomeSnapshotApiPayload,
  type EventRecordApiPayload,
} from "../ownerApis/agentProfiles";
import {
  listLlmProfiles,
  type LlmProfileApiPayload,
} from "../ownerApis/llmProfiles";
import {
  listSkills,
  type SkillApiPayload,
} from "../ownerApis/skillCatalog";
import {
  listTools,
  type ToolApiPayload,
} from "../ownerApis/toolCatalog";

type JsonRecord = Record<string, unknown>;
type AgentTab = "general" | "llm" | "runtime" | "memory" | "tools" | "resolution" | "history" | "advanced";

const profiles = ref<AgentProfileApiPayload[]>([]);
const llmProfiles = ref<LlmProfileApiPayload[]>([]);
const toolCatalog = ref<ToolApiPayload[]>([]);
const skillCatalog = ref<SkillApiPayload[]>([]);
const homeSnapshot = ref<AgentHomeSnapshotApiPayload | null>(null);
const profileResolution = ref<AgentProfileResolutionApiPayload | null>(null);
const historyRecords = ref<EventRecordApiPayload[]>([]);
const selectedProfileId = ref<string | null>(null);
const isLoading = ref(false);
const homeLoading = ref(false);
const resolutionLoading = ref(false);
const historyLoading = ref(false);
const loadError = ref<string | null>(null);
const catalogLoadError = ref<string | null>(null);
const homeError = ref<string | null>(null);
const resolutionError = ref<string | null>(null);
const historyError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const ownerActionError = ref<string | null>(null);
const ownerActionMessage = ref<string | null>(null);
const ownerActionLoading = ref(false);
const importInput = ref<HTMLInputElement | null>(null);
const openRowMenuId = ref<string | null>(null);
const searchTerm = ref("");
const statusFilter = ref("all");
const runtimeFilter = ref("all");
const strategyFilter = ref("all");
const tagFilter = ref("all");
const currentPage = ref(1);
const pageSize = ref(10);
const editMode = ref<"create" | "update">("update");
const activeTab = ref<AgentTab>("general");

const editProfileId = ref("");
const editName = ref("");
const editDescription = ref("");
const editTags = ref("");
const editEnabled = ref(true);
const editDefaultLlmId = ref("");
const editFallbackLlmIds = ref("");
const editImageLlmId = ref("");
const editDocumentLlmId = ref("");
const editWorkdir = ref("");
const editWorkspace = ref("");
const editHomeDir = ref("");
const editSandboxMode = ref("sandbox");
const editMemoryBackend = ref("");
const editSystemPrompt = ref("");
const editStreamByDefault = ref(false);
const editTimeoutSeconds = ref(120);
const editMaxTurns = ref(99);
const editToolIds = ref<string[]>([]);
const editSkillIds = ref<string[]>([]);
const selectedHomeFileName = ref("");
const editHomeFileContent = ref("");

const llmById = computed(() => {
  const values = new Map<string, LlmProfileApiPayload>();
  for (const item of llmProfiles.value) values.set(item.id, item);
  return values;
});

const selectedProfile = computed(() =>
  profiles.value.find((profile) => profile.id === selectedProfileId.value) ?? null,
);

const filteredProfiles = computed(() => {
  const query = searchTerm.value.trim().toLowerCase();
  return profiles.value.filter((profile) => {
    if (query) {
      const haystack = [
        profile.id,
        profile.name,
        profile.description,
        profile.llm_routing_policy.default_llm_id,
        ...fallbackLlmIds(profile),
        ...tagsForProfile(profile),
      ].join(" ").toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (statusFilter.value !== "all" && profileStatus(profile) !== statusFilter.value) return false;
    if (runtimeFilter.value !== "all" && runtimeMode(profile) !== runtimeFilter.value) return false;
    if (strategyFilter.value !== "all" && routingStrategy(profile) !== strategyFilter.value) return false;
    if (tagFilter.value !== "all" && !tagsForProfile(profile).includes(tagFilter.value)) return false;
    return true;
  });
});

const totalPages = computed(() =>
  Math.max(1, Math.ceil(filteredProfiles.value.length / pageSize.value)),
);

const pagedProfiles = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredProfiles.value.slice(start, start + pageSize.value);
});

const visibleRangeLabel = computed(() => {
  if (!filteredProfiles.value.length) return "0-0 / 0";
  const start = (currentPage.value - 1) * pageSize.value + 1;
  const end = Math.min(filteredProfiles.value.length, start + pageSize.value - 1);
  return `${start}-${end} / ${filteredProfiles.value.length}`;
});

const statusOptions = computed(() => [
  { value: "all", label: "All", count: profiles.value.length },
  { value: "enabled", label: "Enabled", count: profiles.value.filter((profile) => profile.enabled).length },
  { value: "disabled", label: "Disabled", count: profiles.value.filter((profile) => !profile.enabled).length },
  { value: "draft", label: "Draft", count: profiles.value.filter((profile) => profileStatus(profile) === "draft").length },
]);

const runtimeOptions = computed(() => optionCounts(profiles.value.map(runtimeMode), [
  "sandbox",
  "container",
  "hybrid",
  "workspace",
]));

const strategyOptions = computed(() => optionCounts(profiles.value.map(routingStrategy), [
  "fixed",
  "auto-routing",
  "fallback",
  "image/document",
]));

const tagOptions = computed(() => {
  const counts = new Map<string, number>();
  for (const profile of profiles.value) {
    for (const tag of tagsForProfile(profile)) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 8)
    .map(([label, count]) => ({ value: label, label, count }));
});

const selectedTags = computed(() =>
  editTags.value.split(",").map((tag) => tag.trim()).filter(Boolean),
);

const selectedToolIds = computed(() => {
  return editToolIds.value;
});

const selectedSkillIds = computed(() => {
  return editSkillIds.value;
});

const selectedHomeFile = computed(() =>
  homeSnapshot.value?.files.find((file) => file.name === selectedHomeFileName.value) ?? null,
);

const effectiveAuthorizationGrants = computed(() =>
  profileResolution.value?.authorization_grants ?? [],
);

const canSubmitOwnerForm = computed(() =>
  editProfileId.value.trim().length > 0
    && editName.value.trim().length > 0
    && editDefaultLlmId.value.trim().length > 0
    && !ownerActionLoading.value,
);

onMounted(() => {
  void loadAgentProfiles();
});

watch(selectedProfile, (profile) => {
  if (!profile || editMode.value === "create") return;
  resetEditFormFromProfile(profile);
});

watch([activeTab, selectedProfileId], () => {
  if (activeTab.value === "advanced" && selectedProfileId.value && editMode.value === "update") {
    void loadAgentHome();
  }
  if (
    (activeTab.value === "tools" || activeTab.value === "resolution")
    && selectedProfileId.value
    && editMode.value === "update"
  ) {
    void loadAgentResolution();
  }
  if (activeTab.value === "history" && selectedProfileId.value && editMode.value === "update") {
    void loadAgentHistory();
  }
});

watch([searchTerm, statusFilter, runtimeFilter, strategyFilter, tagFilter, pageSize], () => {
  currentPage.value = 1;
});

watch(filteredProfiles, () => {
  if (currentPage.value > totalPages.value) currentPage.value = totalPages.value;
});

async function loadAgentProfiles(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  const currentId = selectedProfileId.value;
  try {
    const [profileList, llmList] = await Promise.all([
      listAgentProfiles(),
      listLlmProfiles().catch(() => [] as LlmProfileApiPayload[]),
      loadCatalogs(),
    ]);
    profiles.value = profileList;
    llmProfiles.value = llmList;
    const nextId = currentId && profileList.some((profile) => profile.id === currentId)
      ? currentId
      : profileList[0]?.id ?? null;
    selectedProfileId.value = nextId;
    if (nextId) {
      editMode.value = "update";
      const detail = await getAgentProfile(nextId);
      replaceProfile(detail);
      resetEditFormFromProfile(detail);
    } else {
      beginCreateProfile();
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isLoading.value = false;
  }
}

async function selectProfile(profileId: string): Promise<void> {
  openRowMenuId.value = null;
  homeSnapshot.value = null;
  profileResolution.value = null;
  historyRecords.value = [];
  selectedHomeFileName.value = "";
  editHomeFileContent.value = "";
  selectedProfileId.value = profileId;
  editMode.value = "update";
  detailError.value = null;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  try {
    const detail = await getAgentProfile(profileId);
    replaceProfile(detail);
    resetEditFormFromProfile(detail);
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  }
}

function beginCreateProfile(): void {
  editMode.value = "create";
  selectedProfileId.value = null;
  activeTab.value = "general";
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  editProfileId.value = "";
  editName.value = "";
  editDescription.value = "";
  editTags.value = "";
  editEnabled.value = true;
  editDefaultLlmId.value = llmProfiles.value[0]?.id ?? "";
  editFallbackLlmIds.value = "";
  editImageLlmId.value = "";
  editDocumentLlmId.value = "";
  editWorkdir.value = "";
  editWorkspace.value = "";
  editHomeDir.value = "";
  editSandboxMode.value = "sandbox";
  editMemoryBackend.value = "";
  editSystemPrompt.value = "";
  editStreamByDefault.value = false;
  editTimeoutSeconds.value = 120;
  editMaxTurns.value = 99;
  editToolIds.value = [];
  editSkillIds.value = [];
  homeSnapshot.value = null;
  profileResolution.value = null;
  historyRecords.value = [];
  selectedHomeFileName.value = "";
  editHomeFileContent.value = "";
}

function resetEditFormFromProfile(profile: AgentProfileApiPayload): void {
  editMode.value = "update";
  editProfileId.value = profile.id;
  editName.value = profile.name;
  editDescription.value = profile.description ?? "";
  editTags.value = tagsForProfile(profile).join(", ");
  editEnabled.value = profile.enabled;
  editDefaultLlmId.value = profile.llm_routing_policy.default_llm_id ?? "";
  editFallbackLlmIds.value = fallbackLlmIds(profile).join(", ");
  editImageLlmId.value = profile.llm_routing_policy.image_llm_id ?? "";
  editDocumentLlmId.value = profile.llm_routing_policy.document_llm_id ?? "";
  editWorkdir.value = profile.runtime_preferences.workdir ?? "";
  editWorkspace.value = profile.runtime_preferences.workspace ?? "";
  editHomeDir.value = profile.runtime_preferences.home_dir ?? "";
  editSandboxMode.value = profile.runtime_preferences.sandbox_mode ?? "sandbox";
  editMemoryBackend.value = profile.runtime_preferences.memory_retrieval_backend ?? "";
  editSystemPrompt.value = profile.instruction_policy.system_prompt ?? "";
  editStreamByDefault.value = profile.instruction_policy.stream_by_default === true;
  editTimeoutSeconds.value = numericOr(profile.execution_policy.timeout_seconds, 120);
  editMaxTurns.value = numericOr(profile.execution_policy.max_turns, 99);
  editToolIds.value = stringArrayFromAttrs(profile, "tool_ids", "tools");
  editSkillIds.value = stringArrayFromAttrs(profile, "skill_ids", "skills");
}

async function loadCatalogs(): Promise<void> {
  catalogLoadError.value = null;
  try {
    const [tools, skills] = await Promise.all([
      listTools().catch(() => [] as ToolApiPayload[]),
      listSkills().catch(() => [] as SkillApiPayload[]),
    ]);
    toolCatalog.value = tools;
    skillCatalog.value = skills;
  } catch (error) {
    catalogLoadError.value = error instanceof Error ? error.message : String(error);
  }
}

async function loadAgentHome(): Promise<void> {
  const profileId = selectedProfileId.value;
  if (!profileId || homeLoading.value) return;
  homeLoading.value = true;
  homeError.value = null;
  try {
    const snapshot = await getAgentHome(profileId);
    homeSnapshot.value = snapshot;
    const preferred = snapshot.files.find((file) => file.name === selectedHomeFileName.value)
      ?? snapshot.files.find((file) => file.name === "AGENT.md")
      ?? snapshot.files[0]
      ?? null;
    if (preferred) {
      selectHomeFile(preferred.name);
    } else {
      selectedHomeFileName.value = "";
      editHomeFileContent.value = "";
    }
  } catch (error) {
    homeError.value = error instanceof Error ? error.message : String(error);
  } finally {
    homeLoading.value = false;
  }
}

async function loadAgentResolution(): Promise<void> {
  const profileId = selectedProfileId.value;
  if (!profileId || resolutionLoading.value) return;
  resolutionLoading.value = true;
  resolutionError.value = null;
  try {
    profileResolution.value = await getAgentProfileResolution(profileId);
  } catch (error) {
    resolutionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    resolutionLoading.value = false;
  }
}

async function loadAgentHistory(): Promise<void> {
  const profileId = selectedProfileId.value;
  if (!profileId || historyLoading.value) return;
  historyLoading.value = true;
  historyError.value = null;
  try {
    const payload = await listAgentProfileEvents(profileId, 25);
    historyRecords.value = payload.records;
  } catch (error) {
    historyError.value = error instanceof Error ? error.message : String(error);
  } finally {
    historyLoading.value = false;
  }
}

function selectHomeFile(fileName: string): void {
  const file = homeSnapshot.value?.files.find((item) => item.name === fileName) ?? null;
  selectedHomeFileName.value = fileName;
  editHomeFileContent.value = file?.content ?? "";
}

async function saveSelectedHomeFile(): Promise<void> {
  const profileId = selectedProfileId.value;
  const fileName = selectedHomeFileName.value;
  if (!profileId || !fileName || ownerActionLoading.value) return;
  ownerActionLoading.value = true;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  try {
    const snapshot = await updateAgentHomeFiles(profileId, [
      { name: fileName, content: editHomeFileContent.value },
    ]);
    homeSnapshot.value = snapshot;
    selectHomeFile(fileName);
    ownerActionMessage.value = "Agent home file saved.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function syncSelectedHome(): Promise<void> {
  const profileId = selectedProfileId.value;
  if (!profileId || ownerActionLoading.value) return;
  ownerActionLoading.value = true;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  try {
    const result = await syncAgentHome(profileId);
    replaceProfile(result.profile);
    resetEditFormFromProfile(result.profile);
    await loadAgentHome();
    ownerActionMessage.value = "Agent profile synced from home.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function exportSelectedHome(): Promise<void> {
  const profileId = selectedProfileId.value;
  if (!profileId || ownerActionLoading.value) return;
  ownerActionLoading.value = true;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  try {
    const result = await exportAgentHome(profileId);
    replaceProfile(result.profile);
    resetEditFormFromProfile(result.profile);
    await loadAgentHome();
    ownerActionMessage.value = "Agent profile exported to home.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function submitOwnerForm(): Promise<void> {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  if (!canSubmitOwnerForm.value) {
    ownerActionError.value = "Profile ID, display name and default LLM are required.";
    return;
  }
  ownerActionLoading.value = true;
  try {
    const payload = buildOwnerWritePayload();
    const profile = editMode.value === "create"
      ? await createAgentProfile({
          ...payload,
          id: editProfileId.value.trim(),
          name: editName.value.trim(),
          llm_routing_policy: payload.llm_routing_policy ?? { default_llm_id: editDefaultLlmId.value.trim() },
        })
      : await updateAgentProfile(editProfileId.value.trim(), payload);
    replaceProfile(profile);
    selectedProfileId.value = profile.id;
    editMode.value = "update";
    resetEditFormFromProfile(profile);
    profileResolution.value = null;
    if (activeTab.value === "tools" || activeTab.value === "resolution") await loadAgentResolution();
    ownerActionMessage.value = "Agent profile saved.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

function triggerImportProfile(): void {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  importInput.value?.click();
}

async function importAgentProfileFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || ownerActionLoading.value) return;

  ownerActionLoading.value = true;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  try {
    const payload = normalizeImportedProfile(JSON.parse(await file.text()));
    const exists = profiles.value.some((profile) => profile.id === payload.id);
    const profile = exists
      ? await updateAgentProfile(payload.id, payload)
      : await createAgentProfile(payload);
    replaceProfile(profile);
    selectedProfileId.value = profile.id;
    editMode.value = "update";
    resetEditFormFromProfile(profile);
    ownerActionMessage.value = exists ? "Agent profile imported and updated." : "Agent profile imported.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function toggleSelectedProfile(): Promise<void> {
  const profile = selectedProfile.value;
  if (!profile || ownerActionLoading.value) return;
  await toggleProfile(profile);
}

async function toggleProfile(profile: AgentProfileApiPayload): Promise<void> {
  if (ownerActionLoading.value) return;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  ownerActionLoading.value = true;
  openRowMenuId.value = null;
  try {
    const updated = profile.enabled
      ? await disableAgentProfile(profile.id, { reason: "settings_agent_profiles_owner_view" })
      : await enableAgentProfile(profile.id, { reason: "settings_agent_profiles_owner_view" });
    replaceProfile(updated);
    selectedProfileId.value = updated.id;
    resetEditFormFromProfile(updated);
    profileResolution.value = null;
    if (activeTab.value === "tools" || activeTab.value === "resolution") await loadAgentResolution();
    ownerActionMessage.value = updated.enabled ? "Agent profile enabled." : "Agent profile disabled.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function deleteSelectedProfile(): Promise<void> {
  const profile = selectedProfile.value;
  if (!profile || ownerActionLoading.value) return;
  await deleteProfile(profile);
}

async function deleteProfile(profile: AgentProfileApiPayload): Promise<void> {
  if (ownerActionLoading.value) return;
  if (!window.confirm(`Delete agent profile '${profile.id}'?`)) return;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  ownerActionLoading.value = true;
  openRowMenuId.value = null;
  try {
    await deleteAgentProfile(profile.id, { reason: "settings_agent_profiles_owner_view" });
    profiles.value = profiles.value.filter((item) => item.id !== profile.id);
    if (selectedProfileId.value === profile.id) {
      selectedProfileId.value = profiles.value[0]?.id ?? null;
    }
    const nextProfile = profiles.value.find((item) => item.id === selectedProfileId.value) ?? null;
    if (nextProfile) {
      resetEditFormFromProfile(nextProfile);
    } else {
      beginCreateProfile();
    }
    ownerActionMessage.value = "Agent profile deleted.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

function duplicateProfile(profile: AgentProfileApiPayload): void {
  openRowMenuId.value = null;
  selectedProfileId.value = null;
  resetEditFormFromProfile(profile);
  editMode.value = "create";
  activeTab.value = "general";
  editProfileId.value = `${profile.id}-copy`;
  editName.value = `${profile.name} Copy`;
  editEnabled.value = false;
  homeSnapshot.value = null;
  profileResolution.value = null;
  historyRecords.value = [];
  selectedHomeFileName.value = "";
  editHomeFileContent.value = "";
  ownerActionError.value = null;
  ownerActionMessage.value = "Review the duplicated profile, then save it as a new Agent.";
}

function toggleRowMenu(profileId: string): void {
  openRowMenuId.value = openRowMenuId.value === profileId ? null : profileId;
}

function setActiveTab(tab: AgentTab): void {
  activeTab.value = tab;
  openRowMenuId.value = null;
}

function closeCreateMode(): void {
  if (profiles.value[0]) {
    selectedProfileId.value = profiles.value[0].id;
    editMode.value = "update";
    resetEditFormFromProfile(profiles.value[0]);
    return;
  }
  beginCreateProfile();
}

function clearFilters(): void {
  searchTerm.value = "";
  statusFilter.value = "all";
  runtimeFilter.value = "all";
  strategyFilter.value = "all";
  tagFilter.value = "all";
}

function goToPage(page: number): void {
  currentPage.value = Math.min(Math.max(1, page), totalPages.value);
}

function replaceProfile(profile: AgentProfileApiPayload): void {
  const index = profiles.value.findIndex((item) => item.id === profile.id);
  if (index >= 0) {
    profiles.value.splice(index, 1, profile);
  } else {
    profiles.value.unshift(profile);
  }
}

function buildOwnerWritePayload() {
  const current = selectedProfile.value;
  const runtime = current?.runtime_preferences;
  const attrs: JsonRecord = {
    ...(runtime?.attrs ?? {}),
    tags: selectedTags.value,
    tool_ids: editToolIds.value,
    skill_ids: editSkillIds.value,
  };
  delete attrs.tools;
  delete attrs.skills;
  return {
    name: editName.value.trim(),
    description: editDescription.value.trim(),
    enabled: editEnabled.value,
    identity: {
      ...(current?.identity ?? {}),
      display_name: editName.value.trim(),
    },
    instruction_policy: {
      ...(current?.instruction_policy ?? {}),
      system_prompt: editSystemPrompt.value,
      stream_by_default: editStreamByDefault.value,
    },
    llm_routing_policy: {
      ...(current?.llm_routing_policy ?? {}),
      default_llm_id: editDefaultLlmId.value.trim(),
      fallback_llm_ids: editFallbackLlmIds.value.split(",").map((item) => item.trim()).filter(Boolean),
      image_llm_id: editImageLlmId.value.trim() || null,
      document_llm_id: editDocumentLlmId.value.trim() || null,
    },
    execution_policy: {
      ...(current?.execution_policy ?? {}),
      timeout_seconds: numericOr(editTimeoutSeconds.value, 120),
      max_turns: numericOr(editMaxTurns.value, 99),
    },
    runtime_preferences: {
      ...(runtime ?? {}),
      home_dir: editHomeDir.value.trim() || null,
      workdir: editWorkdir.value.trim() || null,
      workspace: editWorkspace.value.trim() || null,
      sandbox_mode: editSandboxMode.value.trim() || null,
      memory_retrieval_backend: editMemoryBackend.value.trim() || null,
      attrs,
    },
    reason: "settings_agent_profiles_owner_view",
  };
}

function profileStatus(profile: AgentProfileApiPayload): string {
  const attrs = runtimeAttrs(profile);
  const lifecycle = textValue(attrs.status ?? attrs.lifecycle_status, "");
  if (lifecycle === "draft") return "draft";
  return profile.enabled ? "enabled" : "disabled";
}

function runtimeMode(profile: AgentProfileApiPayload): string {
  const raw = textValue(profile.runtime_preferences.sandbox_mode, "");
  if (raw.includes("container")) return "container";
  if (raw.includes("hybrid")) return "hybrid";
  if (raw.includes("workspace")) return "workspace";
  return raw || "sandbox";
}

function runtimeLocation(profile: AgentProfileApiPayload): string {
  return profile.runtime_preferences.workdir
    ?? profile.runtime_preferences.workspace
    ?? profile.runtime_preferences.home_dir
    ?? "-";
}

function routingStrategy(profile: AgentProfileApiPayload): string {
  if (profile.llm_routing_policy.image_llm_id || profile.llm_routing_policy.document_llm_id) return "image/document";
  if (fallbackLlmIds(profile).length) return "fallback";
  const attrs = runtimeAttrs(profile);
  const strategy = textValue(attrs.llm_strategy ?? attrs.routing_strategy, "");
  if (strategy) return strategy;
  return "fixed";
}

function tagsForProfile(profile: AgentProfileApiPayload): string[] {
  const attrs = runtimeAttrs(profile);
  const raw = attrs.tags;
  if (Array.isArray(raw)) {
    return raw.map((item) => textValue(item)).filter(Boolean).slice(0, 6);
  }
  const fallback = textValue(attrs.tag, "");
  return fallback ? [fallback] : [];
}

function fallbackLlmIds(profile: AgentProfileApiPayload): string[] {
  return Array.isArray(profile.llm_routing_policy.fallback_llm_ids)
    ? profile.llm_routing_policy.fallback_llm_ids
    : [];
}

function memoryState(profile: AgentProfileApiPayload): string {
  const attrs = runtimeAttrs(profile);
  if (attrs.memory_enabled === false) return "off";
  if (profile.runtime_preferences.memory_retrieval_backend) return "on";
  return attrs.memory_enabled === true ? "on" : "off";
}

function toolCount(profile: AgentProfileApiPayload): number {
  const attrs = runtimeAttrs(profile);
  const raw = attrs.tool_ids ?? attrs.tools;
  return Array.isArray(raw) ? raw.length : 0;
}

function runtimeAttrs(profile: AgentProfileApiPayload | null): JsonRecord {
  return objectValue(profile?.runtime_preferences.attrs) ?? {};
}

function stringArrayFromAttrs(
  profile: AgentProfileApiPayload | null,
  primaryKey: string,
  fallbackKey: string,
): string[] {
  const attrs = runtimeAttrs(profile);
  const values = attrs[primaryKey] ?? attrs[fallbackKey] ?? [];
  if (!Array.isArray(values)) return [];
  return values.map((item) => textValue(item)).filter(Boolean);
}

function authorizationGrantKey(grant: AgentAuthorizationGrantApiPayload): string {
  return [
    grant.policy_id,
    grant.action,
    grant.effect_ids.join(","),
    grant.tool_ids.join(","),
  ].join(":");
}

function authorizationGrantTarget(grant: AgentAuthorizationGrantApiPayload): string {
  const groups: string[] = [];
  if (grant.effect_ids.length) groups.push(`Effects: ${grant.effect_ids.join(", ")}`);
  if (grant.tool_ids.length) groups.push(`Tools: ${grant.tool_ids.join(", ")}`);
  return groups.join(" · ") || grant.action;
}

function normalizeImportedProfile(value: unknown) {
  const root = objectValue(value);
  const source = objectValue(root?.profile) ?? root;
  if (!source) throw new Error("Imported file must contain an agent profile JSON object.");
  const id = textValue(source.id, "");
  const name = textValue(source.name, "");
  const llmRoutingPolicy = objectValue(source.llm_routing_policy);
  if (!id || !name || !llmRoutingPolicy || !textValue(llmRoutingPolicy.default_llm_id, "")) {
    throw new Error("Imported profile requires id, name and llm_routing_policy.default_llm_id.");
  }
  return {
    id,
    name,
    description: textValue(source.description, ""),
    enabled: source.enabled !== false,
    identity: objectValue(source.identity) ?? {},
    instruction_policy: objectValue(source.instruction_policy) ?? {},
    llm_routing_policy: llmRoutingPolicy,
    execution_policy: objectValue(source.execution_policy) ?? {},
    runtime_preferences: objectValue(source.runtime_preferences) ?? {},
    reason: "settings_agent_profiles_import",
  };
}

function llmLabel(llmId: string | null | undefined): string {
  const id = textValue(llmId, "");
  if (!id) return "Disabled";
  const profile = llmById.value.get(id);
  return profile?.model_name ?? id;
}

function llmProvider(llmId: string | null | undefined): string {
  const id = textValue(llmId, "");
  if (!id) return "-";
  return llmById.value.get(id)?.provider ?? providerFromId(id);
}

function providerFromId(value: string): string {
  const [provider] = value.split(".");
  return provider || "-";
}

function optionCounts(values: string[], preferred: string[]) {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  const known = preferred.map((value) => ({
    value,
    label: titleize(value),
    count: counts.get(value) ?? 0,
  }));
  const extra = Array.from(counts.entries())
    .filter(([value]) => !preferred.includes(value))
    .map(([value, count]) => ({ value, label: titleize(value), count }));
  return [
    { value: "all", label: "All", count: profiles.value.length },
    ...known,
    ...extra,
  ];
}

function objectValue(value: unknown): JsonRecord | null {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as JsonRecord;
  return null;
}

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function numericOr(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function titleize(value: unknown, fallback = "-"): string {
  const raw = textValue(value, "");
  if (!raw) return fallback;
  return raw
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function initials(profile: AgentProfileApiPayload | null): string {
  const name = profile?.name ?? editName.value;
  return textValue(name, "A").slice(0, 1).toUpperCase();
}

function shortPath(value: string): string {
  if (!value || value === "-") return "-";
  if (value.length <= 30) return value;
  return `...${value.slice(-27)}`;
}

function eventPayload(record: EventRecordApiPayload): AgentOwnerJsonRecord {
  return objectValue(record.source_payload) ?? {};
}

function eventActionLabel(record: EventRecordApiPayload): string {
  const name = textValue(record.source_event_name || record.event_name, "agent.profile.event");
  return titleize(name.replace(/^agent\.profile\./, ""));
}

function eventReason(record: EventRecordApiPayload): string {
  return textValue(eventPayload(record).reason, "-");
}

function eventActor(record: EventRecordApiPayload): string {
  return textValue(eventPayload(record).actor, "system");
}

function formatRelativeTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "-";
  const diffSeconds = Math.round((Date.now() - timestamp) / 1000);
  const absSeconds = Math.abs(diffSeconds);
  if (absSeconds < 45) return "just now";
  const minute = 60;
  const hour = minute * 60;
  const day = hour * 24;
  if (absSeconds < hour) {
    const amount = Math.max(1, Math.round(absSeconds / minute));
    return diffSeconds >= 0 ? `${amount}m ago` : `in ${amount}m`;
  }
  if (absSeconds < day) {
    const amount = Math.max(1, Math.round(absSeconds / hour));
    return diffSeconds >= 0 ? `${amount}h ago` : `in ${amount}h`;
  }
  if (absSeconds < day * 30) {
    const amount = Math.max(1, Math.round(absSeconds / day));
    return diffSeconds >= 0 ? `${amount}d ago` : `in ${amount}d`;
  }
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(timestamp));
}
</script>

<template>
  <main class="settings-module agent-profiles-page">
    <header class="agent-page-header">
      <div>
        <h1>Agent Profiles</h1>
        <p>Manage runtime agent identities, routing and execution behavior.</p>
      </div>
      <div class="agent-page-actions">
        <UiButton size="sm" variant="primary" :disabled="ownerActionLoading" @click="beginCreateProfile">
          <Plus :size="15" /> New Agent
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="ownerActionLoading" @click="triggerImportProfile">
          <Import :size="14" /> Import
        </UiButton>
        <input
          ref="importInput"
          accept="application/json,.json"
          class="agent-import-input"
          type="file"
          @change="importAgentProfileFile"
        />
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadAgentProfiles">
          <RefreshCcw :size="14" /> Refresh
        </UiButton>
        <button class="icon-button" type="button" aria-label="More actions"><MoreVertical :size="16" /></button>
      </div>
    </header>

    <p v-if="loadError" class="agent-page-error">{{ loadError }}</p>

    <section class="agent-workbench">
      <section class="agent-list-panel">
        <div class="agent-table-toolbar">
          <div class="agent-list-count">{{ filteredProfiles.length }} agents</div>
          <label class="agent-search">
            <Search :size="15" />
            <input v-model="searchTerm" placeholder="Search agents..." />
            <kbd>⌘K</kbd>
          </label>
          <select v-model="statusFilter">
            <option v-for="option in statusOptions" :key="option.value" :value="option.value">
              {{ option.label }} · {{ option.count }}
            </option>
          </select>
          <select v-model="runtimeFilter">
            <option v-for="option in runtimeOptions" :key="option.value" :value="option.value">
              {{ option.label }} · {{ option.count }}
            </option>
          </select>
          <select v-model="strategyFilter">
            <option v-for="option in strategyOptions" :key="option.value" :value="option.value">
              {{ option.label }} · {{ option.count }}
            </option>
          </select>
          <select v-model="tagFilter" :disabled="!tagOptions.length">
            <option value="all">All tags</option>
            <option v-for="option in tagOptions" :key="option.value" :value="option.value">
              {{ option.label }} · {{ option.count }}
            </option>
          </select>
          <button class="clear-filters" type="button" @click="clearFilters">
            <X :size="14" /> Clear
          </button>
        </div>
        <div class="agent-table">
          <div class="agent-table-head">
            <span>Agent</span>
            <span>Default LLM</span>
            <span>Fallback</span>
            <span>Runtime</span>
            <span>Preferences</span>
            <span>Status</span>
            <span>Updated</span>
            <span><SlidersHorizontal :size="14" /></span>
          </div>

          <div
            v-for="profile in pagedProfiles"
            :key="profile.id"
            class="agent-row"
            :class="{ active: profile.id === selectedProfileId }"
            role="button"
            tabindex="0"
            @click="selectProfile(profile.id)"
            @keydown.enter.prevent="selectProfile(profile.id)"
            @keydown.space.prevent="selectProfile(profile.id)"
          >
            <span class="agent-cell agent-identity-cell">
              <span class="agent-avatar">{{ initials(profile) }}</span>
              <strong>
                <span class="truncate">{{ profile.name }}</span>
                <small>{{ profile.id }}</small>
                <span v-if="tagsForProfile(profile).length" class="row-tags">
                  <em v-for="tag in tagsForProfile(profile).slice(0, 2)" :key="tag">{{ tag }}</em>
                </span>
              </strong>
            </span>
            <span class="agent-cell llm-cell">
              <span class="llm-badge">{{ llmLabel(profile.llm_routing_policy.default_llm_id).slice(0, 2).toUpperCase() }}</span>
              <strong><span class="truncate">{{ llmLabel(profile.llm_routing_policy.default_llm_id) }}</span><small>{{ llmProvider(profile.llm_routing_policy.default_llm_id) }}</small></strong>
            </span>
            <span class="agent-cell llm-cell muted">
              <span v-if="fallbackLlmIds(profile).length" class="llm-badge secondary">AI</span>
              <strong>
                <span class="truncate">{{ fallbackLlmIds(profile).length ? llmLabel(fallbackLlmIds(profile)[0]) : "Disabled" }}</span>
                <small>{{ fallbackLlmIds(profile).length ? llmProvider(fallbackLlmIds(profile)[0]) : "-" }}</small>
              </strong>
            </span>
            <span class="agent-cell runtime-cell">
              <Box :size="16" />
              <strong><span class="truncate">{{ runtimeMode(profile) }}</span><small>{{ shortPath(runtimeLocation(profile)) }}</small></strong>
            </span>
            <span class="agent-cell preference-cell">
              <small :class="{ on: profile.instruction_policy.stream_by_default }">streaming</small>
              <small :class="{ on: memoryState(profile) === 'on', off: memoryState(profile) === 'off' }">memory: {{ memoryState(profile) }}</small>
              <small>tools: {{ toolCount(profile) }}</small>
            </span>
            <span class="agent-cell status-cell">
              <i :class="`status-dot status-dot--${profileStatus(profile)}`" />
              {{ titleize(profileStatus(profile)) }}
            </span>
            <span class="agent-cell updated-cell" :title="profile.updated_at || profile.created_at || ''">
              {{ formatRelativeTimestamp(profile.updated_at || profile.created_at) }}
            </span>
            <span class="agent-cell row-menu">
              <button
                class="row-menu-button"
                type="button"
                aria-label="Agent row actions"
                @click.stop="toggleRowMenu(profile.id)"
              >
                <MoreVertical :size="15" />
              </button>
              <span v-if="openRowMenuId === profile.id" class="row-action-menu">
                <button type="button" @click.stop="selectProfile(profile.id); activeTab = 'general'; openRowMenuId = null">Edit</button>
                <button type="button" @click.stop="duplicateProfile(profile)">Duplicate</button>
                <button type="button" @click.stop="toggleProfile(profile)">{{ profile.enabled ? "Disable" : "Enable" }}</button>
                <button class="danger" type="button" @click.stop="deleteProfile(profile)">Delete</button>
              </span>
            </span>
          </div>

          <div v-if="!isLoading && !filteredProfiles.length" class="agent-empty">
            No agents match the current filters.
          </div>
        </div>

        <footer class="agent-pagination">
          <span>{{ visibleRangeLabel }}</span>
          <label>
            Rows
            <select v-model.number="pageSize">
              <option :value="10">10</option>
              <option :value="25">25</option>
              <option :value="50">50</option>
            </select>
          </label>
          <nav>
            <button type="button" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">‹</button>
            <button type="button" class="active">{{ currentPage }}</button>
            <button type="button" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">›</button>
          </nav>
        </footer>
      </section>

      <aside class="agent-drawer">
        <button class="drawer-close" type="button" aria-label="Close editor" @click="closeCreateMode">
          <X :size="17" />
        </button>

        <header class="drawer-profile-header">
          <span class="drawer-avatar">{{ initials(selectedProfile) }}</span>
          <div>
            <h2>{{ editName || "New Agent" }}</h2>
            <p>{{ editProfileId || "agent-id" }}</p>
          </div>
          <label class="switch" :class="{ on: editEnabled }">
            <input v-model="editEnabled" type="checkbox" />
            <span />
          </label>
          <em>{{ editEnabled ? "Enabled" : "Disabled" }}</em>
        </header>

        <nav class="drawer-tabs">
          <button type="button" :class="{ active: activeTab === 'general' }" @click="setActiveTab('general')">General</button>
          <button type="button" :class="{ active: activeTab === 'llm' }" @click="setActiveTab('llm')">LLM</button>
          <button type="button" :class="{ active: activeTab === 'runtime' }" @click="setActiveTab('runtime')">Runtime</button>
          <button type="button" :class="{ active: activeTab === 'memory' }" @click="setActiveTab('memory')">Memory</button>
          <button type="button" :class="{ active: activeTab === 'tools' }" @click="setActiveTab('tools')">Tools</button>
          <button type="button" :class="{ active: activeTab === 'resolution' }" @click="setActiveTab('resolution')">Resolve</button>
          <button type="button" :class="{ active: activeTab === 'history' }" @click="setActiveTab('history')">History</button>
          <button type="button" :class="{ active: activeTab === 'advanced' }" @click="setActiveTab('advanced')">Home</button>
        </nav>

        <form class="agent-drawer-form" @submit.prevent="submitOwnerForm">
          <section v-if="activeTab === 'general'" class="drawer-section">
            <h3>Basic Information</h3>
            <label>
              <span>Display Name</span>
              <input v-model="editName" placeholder="Support Agent" />
            </label>
            <label>
              <span>Profile ID</span>
              <input v-model="editProfileId" :readonly="editMode === 'update'" placeholder="support-prod" />
            </label>
            <label>
              <span>Description</span>
              <textarea v-model="editDescription" rows="4" />
            </label>
            <label>
              <span>Tags</span>
              <input v-model="editTags" placeholder="support, internal" />
            </label>
            <h3>Runtime Identity</h3>
            <label>
              <span>Environment</span>
              <select v-model="editSandboxMode">
                <option value="sandbox">Sandbox</option>
                <option value="workspace">Workspace</option>
                <option value="container">Container</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </label>
            <label>
              <span>Workspace / Workdir</span>
              <input v-model="editWorkdir" placeholder="/agents/support" />
            </label>
            <fieldset class="visibility-fieldset">
              <legend>Visibility</legend>
              <label><input checked type="radio" name="agent-visibility" /> Internal <small>Only visible to team members</small></label>
              <label><input disabled type="radio" name="agent-visibility" /> Shared <small>Requires backend field</small></label>
              <label><input disabled type="radio" name="agent-visibility" /> System Default <small>Requires backend field</small></label>
            </fieldset>
          </section>

          <section v-else-if="activeTab === 'llm'" class="drawer-section">
            <h3>Routing</h3>
            <label>
              <span>Default LLM</span>
              <select v-model="editDefaultLlmId">
                <option v-for="llm in llmProfiles" :key="llm.id" :value="llm.id">
                  {{ llm.model_name }} · {{ llm.provider }}
                </option>
                <option v-if="!llmProfiles.length" :value="editDefaultLlmId">{{ editDefaultLlmId || "No LLM profiles loaded" }}</option>
              </select>
            </label>
            <label>
              <span>Fallback LLMs</span>
              <input v-model="editFallbackLlmIds" placeholder="comma,separated,llm.ids" />
            </label>
            <label>
              <span>Image LLM</span>
              <input v-model="editImageLlmId" placeholder="optional" />
            </label>
            <label>
              <span>Document LLM</span>
              <input v-model="editDocumentLlmId" placeholder="optional" />
            </label>
          </section>

          <section v-else-if="activeTab === 'runtime'" class="drawer-section">
            <h3>Execution</h3>
            <label>
              <span>Timeout Seconds</span>
              <input v-model.number="editTimeoutSeconds" min="1" type="number" />
            </label>
            <label>
              <span>Max Turns</span>
              <input v-model.number="editMaxTurns" min="1" type="number" />
            </label>
            <label>
              <span>Home Directory</span>
              <input v-model="editHomeDir" />
            </label>
            <label>
              <span>Workspace</span>
              <input v-model="editWorkspace" />
            </label>
          </section>

          <section v-else-if="activeTab === 'memory'" class="drawer-section">
            <h3>Memory</h3>
            <label>
              <span>Retrieval Backend</span>
              <input v-model="editMemoryBackend" placeholder="keyword / vector / hybrid" />
            </label>
            <label class="checkbox-field">
              <input v-model="editStreamByDefault" type="checkbox" />
              <span>Stream by default</span>
            </label>
            <label>
              <span>System Prompt</span>
              <textarea v-model="editSystemPrompt" rows="7" />
            </label>
          </section>

          <section v-else-if="activeTab === 'tools'" class="drawer-section">
            <h3>Tool Authorization</h3>
            <div class="grant-summary">
              <span>{{ selectedToolIds.length }} tools</span>
              <span>{{ selectedSkillIds.length }} skills</span>
              <span>{{ effectiveAuthorizationGrants.length }} auth grants</span>
            </div>
            <div class="grant-picker">
              <h4>Authorization Grants</h4>
              <article
                v-for="grant in effectiveAuthorizationGrants"
                :key="authorizationGrantKey(grant)"
                class="resolution-row"
              >
                <strong>{{ authorizationGrantTarget(grant) }}</strong>
                <small>{{ grant.policy_id }}</small>
                <em :class="{ ready: grant.status === 'enabled', blocked: grant.effect === 'deny' }">
                  {{ titleize(grant.effect) }} · {{ titleize(grant.status) }}
                </em>
              </article>
              <p v-if="resolutionLoading" class="grant-empty">Loading authorization grants...</p>
              <p v-else-if="!effectiveAuthorizationGrants.length" class="grant-empty">No agent authorization policies matched.</p>
            </div>
            <div class="grant-picker">
              <h4>Tools</h4>
              <label v-for="tool in toolCatalog" :key="tool.id" class="grant-row">
                <input v-model="editToolIds" :value="tool.id" type="checkbox" />
                <strong>{{ tool.name || tool.id }}</strong>
                <small>{{ tool.id }}</small>
              </label>
              <p v-if="!toolCatalog.length" class="grant-empty">No tools returned by the Tool catalog.</p>
            </div>
            <div class="grant-picker">
              <h4>Skills</h4>
              <label v-for="skill in skillCatalog" :key="skill.name" class="grant-row">
                <input v-model="editSkillIds" :value="skill.name" type="checkbox" />
                <strong>{{ skill.name }}</strong>
                <small>{{ skill.source }}</small>
              </label>
              <p v-if="!skillCatalog.length" class="grant-empty">No skills returned by the Skill catalog.</p>
            </div>
          </section>

          <section v-else-if="activeTab === 'resolution'" class="drawer-section">
            <h3>Effective Resolution</h3>
            <div class="history-actions">
              <button type="button" :disabled="resolutionLoading" @click="loadAgentResolution">
                Reload Resolution
              </button>
              <span>{{ profileResolution ? formatRelativeTimestamp(profileResolution.profile_updated_at) : "not loaded" }}</span>
            </div>
            <div v-if="profileResolution" class="resolution-summary">
              <span><strong>{{ titleize(profileResolution.summary.status) }}</strong><small>Status</small></span>
              <span><strong>{{ profileResolution.summary.llm_routes }}</strong><small>LLM routes</small></span>
              <span><strong>{{ profileResolution.summary.tools }}</strong><small>Tools</small></span>
              <span><strong>{{ profileResolution.summary.skills }}</strong><small>Skills</small></span>
              <span><strong>{{ profileResolution.summary.access_grants }}</strong><small>Access</small></span>
              <span><strong>{{ profileResolution.summary.authorization_grants }}</strong><small>Authz</small></span>
              <span><strong>{{ profileResolution.summary.issues }}</strong><small>Issues</small></span>
            </div>

            <div v-if="profileResolution" class="resolution-block">
              <h4>LLM Routes</h4>
              <article v-for="route in profileResolution.llm_routes" :key="`${route.slot}:${route.llm_id}`" class="resolution-row">
                <strong>{{ titleize(route.slot) }} · {{ route.model_name || route.llm_id }}</strong>
                <small>{{ route.provider || "-" }} · {{ route.resolved ? (route.enabled ? "enabled" : "disabled") : "missing" }}</small>
                <em v-if="route.credential_binding">{{ route.credential_binding }}</em>
              </article>
              <p v-if="!profileResolution.llm_routes.length" class="grant-empty">No LLM routes resolved.</p>
            </div>

            <div v-if="profileResolution" class="resolution-block">
              <h4>Tools</h4>
              <article v-for="tool in profileResolution.tools" :key="tool.tool_id" class="resolution-row">
                <strong>{{ tool.name || tool.tool_id }}</strong>
                <small>{{ tool.kind || "-" }} · {{ tool.resolved ? (tool.enabled ? "enabled" : "disabled") : "missing" }}</small>
                <em>{{ tool.access_requirements.length + tool.access_requirement_sets.flat().length }} access requirements</em>
              </article>
              <p v-if="!profileResolution.tools.length" class="grant-empty">No tools selected in this profile.</p>
            </div>

            <div v-if="profileResolution" class="resolution-block">
              <h4>Skills</h4>
              <article v-for="skill in profileResolution.skills" :key="skill.skill_id" class="resolution-row">
                <strong>{{ skill.name || skill.skill_id }}</strong>
                <small>{{ skill.source || "-" }} · {{ skill.resolved ? "resolved" : "missing" }}</small>
                <em>{{ skill.required_tools.length }} required tools</em>
              </article>
              <p v-if="!profileResolution.skills.length" class="grant-empty">No skills selected in this profile.</p>
            </div>

            <div v-if="profileResolution" class="resolution-block">
              <h4>Access Grants</h4>
              <article v-for="grant in profileResolution.access_grants" :key="`${grant.source_type}:${grant.source_id}:${grant.requirement}`" class="resolution-row">
                <strong>{{ grant.requirement }}</strong>
                <small>{{ grant.source_type }} · {{ grant.source_id }}</small>
                <em :class="{ ready: grant.ready, blocked: !grant.ready }">{{ titleize(grant.status) }}</em>
              </article>
              <p v-if="!profileResolution.access_grants.length" class="grant-empty">No declared access grants.</p>
            </div>

            <div v-if="profileResolution" class="resolution-block">
              <h4>Authorization Grants</h4>
              <article
                v-for="grant in profileResolution.authorization_grants"
                :key="authorizationGrantKey(grant)"
                class="resolution-row"
              >
                <strong>{{ authorizationGrantTarget(grant) }}</strong>
                <small>{{ grant.policy_id }} · {{ grant.source_kind || "policy" }}</small>
                <em :class="{ ready: grant.status === 'enabled', blocked: grant.effect === 'deny' }">
                  {{ titleize(grant.effect) }} · {{ titleize(grant.status) }}
                </em>
              </article>
              <p v-if="!profileResolution.authorization_grants.length" class="grant-empty">No agent authorization policies matched.</p>
            </div>

            <div v-if="profileResolution" class="resolution-block">
              <h4>Validation</h4>
              <article v-for="issue in profileResolution.validation" :key="`${issue.code}:${issue.ref}`" class="resolution-row">
                <strong>{{ issue.code }}</strong>
                <small>{{ issue.message }}</small>
                <em :class="{ blocked: issue.severity === 'error' }">{{ titleize(issue.severity) }}</em>
              </article>
              <p v-if="!profileResolution.validation.length" class="grant-empty">No validation issues.</p>
            </div>

            <div v-if="profileResolution" class="resolution-block">
              <h4>Trace</h4>
              <article v-for="record in profileResolution.trace" :key="`${record.source}:${record.detail}`" class="resolution-row">
                <strong>{{ record.source }}</strong>
                <small>{{ record.detail }}</small>
                <em>{{ titleize(record.status) }}</em>
              </article>
            </div>
            <p v-else-if="!resolutionLoading" class="grant-empty">Resolution preview has not been loaded.</p>
            <p v-if="resolutionError" class="settings-tone-danger">{{ resolutionError }}</p>
          </section>

          <section v-else-if="activeTab === 'history'" class="drawer-section">
            <h3>Lifecycle History</h3>
            <div class="history-actions">
              <button type="button" :disabled="historyLoading" @click="loadAgentHistory">Reload History</button>
              <span>{{ historyRecords.length }} events</span>
            </div>
            <div v-if="historyRecords.length" class="history-list">
              <article v-for="record in historyRecords" :key="record.event_id" class="history-row">
                <header>
                  <strong>{{ eventActionLabel(record) }}</strong>
                  <time :title="record.source_created_at || record.created_at">
                    {{ formatRelativeTimestamp(record.source_created_at || record.created_at) }}
                  </time>
                </header>
                <dl>
                  <div><dt>Reason</dt><dd>{{ eventReason(record) }}</dd></div>
                  <div><dt>Actor</dt><dd>{{ eventActor(record) }}</dd></div>
                  <div><dt>Cursor</dt><dd>{{ record.cursor }}</dd></div>
                </dl>
              </article>
            </div>
            <p v-else-if="!historyLoading" class="grant-empty">No agent lifecycle events retained for this profile.</p>
            <p v-if="historyError" class="settings-tone-danger">{{ historyError }}</p>
          </section>

          <section v-else class="drawer-section">
            <h3>Agent Home</h3>
            <div class="home-meta">
              <span>{{ homeSnapshot?.home_dir || "No home snapshot loaded" }}</span>
              <small>{{ homeSnapshot?.workdir || "workdir follows home" }}</small>
            </div>
            <div class="home-actions">
              <button type="button" :disabled="homeLoading" @click="loadAgentHome">Reload</button>
              <button type="button" :disabled="ownerActionLoading" @click="syncSelectedHome">Sync from Home</button>
              <button type="button" :disabled="ownerActionLoading" @click="exportSelectedHome">Export to Home</button>
            </div>
            <div class="home-files-panel">
              <nav class="home-file-list">
                <button
                  v-for="file in homeSnapshot?.files ?? []"
                  :key="file.name"
                  type="button"
                  :class="{ active: selectedHomeFileName === file.name }"
                  @click="selectHomeFile(file.name)"
                >
                  <strong>{{ file.name }}</strong>
                  <small>{{ file.language }} · {{ file.exists ? "exists" : "missing" }}</small>
                </button>
                <p v-if="!homeLoading && !(homeSnapshot?.files.length)" class="grant-empty">No agent home files loaded.</p>
              </nav>
              <label class="home-editor">
                <span>{{ selectedHomeFile?.path || selectedHomeFileName || "Select a home file" }}</span>
                <textarea v-model="editHomeFileContent" :disabled="!selectedHomeFileName" rows="10" />
              </label>
              <button class="home-save-button" type="button" :disabled="!selectedHomeFileName || ownerActionLoading" @click="saveSelectedHomeFile">
                Save Home File
              </button>
            </div>
            <p v-if="homeError" class="settings-tone-danger">{{ homeError }}</p>
            <details class="profile-json-details">
              <summary>Profile JSON</summary>
              <pre>{{ JSON.stringify(selectedProfile ?? buildOwnerWritePayload(), null, 2) }}</pre>
            </details>
          </section>

          <p v-if="detailError" class="settings-tone-danger">{{ detailError }}</p>
          <p v-if="catalogLoadError" class="settings-tone-danger">{{ catalogLoadError }}</p>
          <p v-if="ownerActionError" class="settings-tone-danger">{{ ownerActionError }}</p>
          <p v-else-if="ownerActionMessage" class="settings-tone-success">{{ ownerActionMessage }}</p>
        </form>

        <footer class="drawer-footer">
          <UiButton size="sm" variant="secondary" type="button" @click="closeCreateMode">Cancel</UiButton>
          <UiButton size="sm" variant="primary" type="button" :disabled="!canSubmitOwnerForm" @click="submitOwnerForm">
            <Save :size="14" /> Save Changes
          </UiButton>
          <UiButton
            v-if="editMode === 'update'"
            size="sm"
            variant="secondary"
            type="button"
            :disabled="ownerActionLoading"
            @click="toggleSelectedProfile"
          >
            <Power :size="14" /> {{ selectedProfile?.enabled ? "Disable" : "Enable" }}
          </UiButton>
          <UiButton
            v-if="editMode === 'update'"
            size="sm"
            variant="danger"
            type="button"
            :disabled="ownerActionLoading"
            @click="deleteSelectedProfile"
          >
            <Trash2 :size="14" /> Delete
          </UiButton>
        </footer>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.agent-profiles-page {
  --agent-green: #118848;
  --agent-orange: #f08a18;
  --agent-gray: #98a2b3;
  height: calc(100vh - 92px);
  min-height: 680px;
  padding: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 26% 6%, color-mix(in srgb, var(--color-success) 9%, transparent), transparent 28%),
    var(--surface-page);
}

.agent-page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 82px;
  padding: 18px 24px 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-panel) 84%, transparent);
}

.agent-page-header h1 {
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
}

.agent-page-header p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.agent-page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-import-input {
  display: none;
}

.icon-button {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
}

.agent-page-error {
  margin: 8px 24px 0;
  color: var(--color-danger);
  font-size: 12px;
}

.agent-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  height: calc(100% - 82px);
  min-height: 0;
}

.agent-list-panel,
.agent-drawer {
  min-height: 0;
  overflow: auto;
}

.agent-search {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.agent-search input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
}

.agent-search kbd {
  color: var(--text-muted);
  font: 11px var(--font-mono);
}

.clear-filters {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}

.dot,
.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--agent-gray);
}

.dot--enabled,
.status-dot--enabled {
  background: var(--agent-green);
}

.dot--disabled,
.status-dot--disabled {
  background: var(--agent-orange);
}

.dot--draft,
.status-dot--draft {
  background: var(--agent-gray);
}

.dot--all {
  background: color-mix(in srgb, var(--text-muted) 28%, transparent);
}

.tag-chip,
.row-tags em {
  display: inline-grid;
  place-items: center;
  min-height: 20px;
  padding: 0 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-raised) 88%, transparent);
  color: var(--text-secondary);
  font-size: 11px;
  font-style: normal;
}

.agent-list-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  padding: 18px 12px 0;
}

.agent-table-toolbar {
  display: grid;
  grid-template-columns: auto minmax(180px, 1fr) repeat(4, minmax(112px, 136px)) auto;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.agent-list-count {
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.agent-table-toolbar select {
  width: 100%;
  min-width: 0;
  height: 34px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.agent-table {
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
}

.agent-table-head,
.agent-row {
  display: grid;
  grid-template-columns: minmax(144px, 1.35fr) minmax(108px, 0.95fr) minmax(76px, 0.75fr) minmax(98px, 0.85fr) minmax(88px, 0.78fr) 74px 64px 22px;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.agent-table-head {
  position: sticky;
  top: 0;
  z-index: 2;
  min-height: 40px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-panel) 96%, transparent);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.agent-row {
  width: 100%;
  min-height: 102px;
  padding: 10px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.agent-row:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--color-primary) 72%, transparent);
  outline-offset: -2px;
}

.agent-row.active {
  background: color-mix(in srgb, var(--color-success) 8%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--color-success) 58%, transparent);
}

.agent-cell {
  min-width: 0;
}

.agent-identity-cell,
.llm-cell,
.runtime-cell,
.status-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-avatar,
.drawer-avatar,
.llm-badge {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  border-radius: var(--radius-2);
  color: white;
  font-weight: 800;
}

.agent-avatar {
  width: 34px;
  height: 34px;
  background: linear-gradient(135deg, var(--agent-green), color-mix(in srgb, var(--agent-green) 48%, #0b5));
}

.agent-identity-cell strong,
.llm-cell strong,
.runtime-cell strong {
  display: grid;
  gap: 5px;
  min-width: 0;
  font-size: 12px;
}

.truncate {
  display: block;
  overflow: hidden;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-identity-cell small,
.llm-cell small,
.runtime-cell small {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-tags {
  display: flex;
  gap: 5px;
}

.llm-badge {
  width: 24px;
  height: 24px;
  background: color-mix(in srgb, var(--color-success) 72%, var(--surface-raised));
  font-size: 10px;
}

.llm-badge.secondary {
  background: color-mix(in srgb, var(--color-warning) 62%, var(--surface-raised));
}

.runtime-cell svg {
  color: var(--text-primary);
}

.preference-cell {
  display: grid;
  gap: 5px;
  color: var(--text-secondary);
  font-size: 11px;
}

.preference-cell small {
  position: relative;
  padding-left: 10px;
}

.preference-cell small::before {
  content: "";
  position: absolute;
  top: 5px;
  left: 0;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: var(--agent-gray);
}

.preference-cell .on::before {
  background: var(--agent-green);
}

.preference-cell .off::before {
  background: var(--color-danger);
}

.status-cell {
  font-size: 12px;
  font-weight: 700;
}

.status-cell {
  gap: 6px;
}

.updated-cell,
.row-menu {
  color: var(--text-secondary);
  font-size: 12px;
}

.updated-cell {
  white-space: nowrap;
}

.row-menu {
  position: relative;
  display: grid;
  place-items: center;
}

.row-menu-button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.row-menu-button:hover {
  background: var(--surface-raised);
  color: var(--text-primary);
}

.row-action-menu {
  position: absolute;
  top: 30px;
  right: 0;
  z-index: 5;
  display: grid;
  width: 128px;
  padding: 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-panel);
  box-shadow: var(--shadow-popover);
}

.row-action-menu button {
  height: 28px;
  border: 0;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.row-action-menu button:hover {
  background: var(--surface-raised);
}

.row-action-menu .danger {
  color: var(--color-danger);
}

.agent-empty {
  display: grid;
  place-items: center;
  min-height: 220px;
  color: var(--text-muted);
  font-size: 12px;
}

.agent-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 48px;
  padding: 0 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.agent-pagination label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.agent-pagination select {
  height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-primary);
  font-size: 12px;
}

.agent-pagination button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 34px;
  height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-primary);
}

.agent-pagination nav {
  display: flex;
  gap: 6px;
}

.agent-pagination .active {
  border-color: var(--agent-green);
  color: var(--agent-green);
}

.agent-drawer {
  position: relative;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  border-left: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-panel) 96%, transparent);
}

.drawer-close {
  position: absolute;
  top: 26px;
  right: 22px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}

.drawer-profile-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  min-height: 108px;
  padding: 26px 26px 18px;
}

.drawer-avatar {
  width: 46px;
  height: 46px;
  background: var(--agent-green);
  font-size: 20px;
}

.drawer-profile-header h2 {
  margin: 0;
  overflow: hidden;
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-profile-header p,
.drawer-profile-header em {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  font-style: normal;
}

.switch {
  position: relative;
  width: 40px;
  height: 22px;
}

.switch input {
  position: absolute;
  inset: 0;
  opacity: 0;
}

.switch span {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text-muted) 28%, transparent);
  cursor: pointer;
}

.switch span::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  border-radius: 999px;
  background: white;
  transition: transform 0.16s ease;
}

.switch.on span {
  background: var(--agent-green);
}

.switch.on span::after {
  transform: translateX(18px);
}

.drawer-tabs {
  display: flex;
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-subtle);
  overflow-x: auto;
}

.drawer-tabs button {
  flex: 0 0 auto;
  height: 42px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 10.5px;
}

.drawer-tabs .active {
  border-color: var(--agent-green);
  color: var(--agent-green);
}

.agent-drawer-form {
  min-height: 0;
  overflow: auto;
}

.drawer-section {
  display: grid;
  gap: 16px;
  padding: 24px 24px 92px;
}

.drawer-section h3 {
  margin: 0;
  font-size: 13px;
}

.drawer-section label {
  display: grid;
  gap: 7px;
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
}

.drawer-section input,
.drawer-section textarea,
.drawer-section select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 500;
}

.drawer-section input,
.drawer-section select {
  height: 34px;
  padding: 0 10px;
}

.drawer-section textarea {
  min-height: 72px;
  padding: 10px;
  resize: vertical;
}

.drawer-section input[readonly] {
  background: color-mix(in srgb, var(--surface-sidebar) 70%, transparent);
  color: var(--text-muted);
}

.checkbox-field {
  display: flex !important;
  flex-direction: row;
  align-items: center;
  gap: 8px !important;
}

.checkbox-field input,
.visibility-fieldset input {
  width: 14px;
  height: 14px;
}

.visibility-fieldset {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  border: 0;
}

.visibility-fieldset legend {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 800;
}

.visibility-fieldset label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  column-gap: 8px;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
}

.visibility-fieldset small {
  grid-column: 2;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 500;
}

.grant-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.grant-summary span {
  display: grid;
  place-items: center;
  min-height: 34px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 800;
  overflow: hidden;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.grant-picker {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.grant-picker h4 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.grant-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 3px 8px;
  align-items: center;
  min-height: 34px;
  color: var(--text-primary);
  font-size: 12px;
}

.grant-row input {
  grid-row: span 2;
}

.grant-row strong,
.grant-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.grant-row small,
.grant-empty {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.resolution-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.resolution-summary span {
  display: grid;
  gap: 3px;
  min-height: 48px;
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.resolution-summary strong {
  color: var(--text-primary);
  font-size: 14px;
}

.resolution-summary small {
  color: var(--text-secondary);
  font-size: 10px;
}

.resolution-block {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-input) 84%, transparent);
}

.resolution-block h4 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.resolution-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 10px;
  align-items: center;
  min-height: 32px;
}

.resolution-row strong,
.resolution-row small {
  overflow: hidden;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resolution-row strong {
  color: var(--text-primary);
  font-size: 12px;
}

.resolution-row small {
  grid-column: 1;
  color: var(--text-secondary);
  font-size: 11px;
}

.resolution-row em {
  grid-column: 2;
  grid-row: 1 / span 2;
  justify-self: end;
  max-width: 128px;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resolution-row em.ready {
  color: var(--agent-green);
}

.resolution-row em.blocked {
  color: var(--color-danger);
}

.history-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.history-actions button {
  min-height: 32px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}

.history-actions span {
  color: var(--text-secondary);
  font-size: 12px;
}

.history-list {
  display: grid;
  gap: 10px;
}

.history-row {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.history-row header,
.history-row dl div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-row header strong {
  color: var(--text-primary);
  font-size: 13px;
}

.history-row time,
.history-row dt {
  color: var(--text-secondary);
  font-size: 11px;
}

.history-row dl {
  display: grid;
  gap: 6px;
  margin: 0;
}

.history-row dd {
  overflow: hidden;
  max-width: 180px;
  margin: 0;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-meta {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.home-meta span,
.home-meta small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-meta span {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 800;
}

.home-meta small {
  color: var(--text-secondary);
  font-size: 11px;
}

.home-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.home-actions button:last-child {
  grid-column: span 2;
}

.home-actions button,
.home-save-button {
  min-height: 32px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}

.home-actions button:disabled,
.home-save-button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.home-files-panel {
  display: grid;
  gap: 10px;
}

.home-file-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.home-file-list button {
  display: grid;
  gap: 3px;
  min-height: 42px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.home-file-list button.active {
  border-color: color-mix(in srgb, var(--agent-green) 64%, transparent);
  background: color-mix(in srgb, var(--agent-green) 10%, var(--surface-input));
}

.home-file-list strong,
.home-file-list small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-file-list small {
  color: var(--text-secondary);
  font-size: 11px;
}

.home-editor textarea {
  min-height: 220px;
  font-family: var(--font-mono);
  line-height: 1.45;
}

.home-editor span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-json-details summary {
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 800;
}

.drawer-section pre {
  max-height: 420px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
}

.drawer-footer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-panel) 98%, transparent);
}

.drawer-footer .ui-button--secondary:nth-last-child(-n + 2),
.drawer-footer .ui-button--danger {
  grid-column: span 1;
}

@media (max-width: 1280px) {
  .agent-workbench {
    grid-template-columns: minmax(0, 1fr) 360px;
  }

  .agent-table-toolbar {
    grid-template-columns: auto minmax(160px, 1fr) repeat(2, minmax(112px, 1fr)) auto;
  }

  .agent-table-toolbar select:nth-of-type(n + 3) {
    display: none;
  }
}

@media (max-width: 980px) {
  .agent-profiles-page {
    height: auto;
    min-height: 0;
    overflow: visible;
  }

  .agent-workbench {
    display: block;
    height: auto;
  }

  .agent-list-panel,
  .agent-drawer {
    overflow: visible;
  }
}
</style>
