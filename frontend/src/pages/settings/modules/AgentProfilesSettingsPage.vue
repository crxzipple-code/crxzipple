<script setup lang="ts">
import {
  Box,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileText,
  Folder,
  Import,
  Link2,
  Maximize2,
  MoreVertical,
  Plus,
  Power,
  RefreshCcw,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
  UserCog,
  X,
} from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";

import {
  createAgentProfile,
  deleteAgentProfile,
  disableAgentProfile,
  enableAgentProfile,
  exportAgentHome,
  getAgentProfile,
  getAgentProfileResolution,
  getAgentHome,
  grantAgentAuthorization,
  listAgentProfiles,
  revokeAgentAuthorization,
  syncAgentHome,
  updateAgentProfile,
  updateAgentHomeFiles,
  type AgentAuthorizationGrantKind,
  type AgentProfileApiPayload,
  type AgentProfileResolutionApiPayload,
  type AgentHomeSnapshotApiPayload,
} from "../ownerApis/agentProfiles";
import {
  listBrowserProfiles,
  type BrowserProfileApiPayload,
} from "../ownerApis/browserProfiles";
import {
  listLlmProfiles,
  type LlmProfileApiPayload,
} from "../ownerApis/llmProfiles";
import {
  listTools,
  type ToolApiPayload,
} from "../ownerApis/toolCatalog";

type JsonRecord = Record<string, unknown>;

const profiles = ref<AgentProfileApiPayload[]>([]);
const llmProfiles = ref<LlmProfileApiPayload[]>([]);
const toolCatalog = ref<ToolApiPayload[]>([]);
const browserProfiles = ref<BrowserProfileApiPayload[]>([]);
const browserDefaultProfile = ref("");
const homeSnapshot = ref<AgentHomeSnapshotApiPayload | null>(null);
const profileResolution = ref<AgentProfileResolutionApiPayload | null>(null);
const selectedProfileId = ref<string | null>(null);
const isLoading = ref(false);
const homeLoading = ref(false);
const resolutionLoading = ref(false);
const loadError = ref<string | null>(null);
const catalogLoadError = ref<string | null>(null);
const homeError = ref<string | null>(null);
const resolutionError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const ownerActionError = ref<string | null>(null);
const ownerActionMessage = ref<string | null>(null);
const ownerActionLoading = ref(false);
const authorizationActionKey = ref<string | null>(null);
const importInput = ref<HTMLInputElement | null>(null);
const toolSearchTerm = ref("");
const editMode = ref<"create" | "update">("update");

const editProfileId = ref("");
const editName = ref("");
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
const editDefaultBrowserProfile = ref("");
const editMemorySpace = ref("");
const editSystemPrompt = ref("");
const editStreamByDefault = ref(false);
const editTimeoutSeconds = ref(120);
const editMaxTurns = ref(99);
const selectedHomeFileName = ref("");
const editHomeFileContent = ref("");

const selectedProfile = computed(() =>
  profiles.value.find((profile) => profile.id === selectedProfileId.value) ?? null,
);

const selectedTags = computed(() =>
  editTags.value.split(",").map((tag) => tag.trim()).filter(Boolean),
);

const filteredToolCatalog = computed(() => {
  const query = toolSearchTerm.value.trim().toLowerCase();
  if (!query) return toolCatalog.value;
  return toolCatalog.value.filter((tool) =>
    [
      tool.id,
      tool.name,
      tool.kind,
      toolAuthorizationTargetLabel(tool),
    ].filter(Boolean).join(" ").toLowerCase().includes(query),
  );
});

const visibleToolCatalog = computed(() => filteredToolCatalog.value);

const selectedHomeFile = computed(() =>
  homeSnapshot.value?.files.find((file) => file.name === selectedHomeFileName.value) ?? null,
);

const homeEditorLineNumbers = computed(() => {
  const lineCount = Math.max(1, editHomeFileContent.value.split(/\r\n|\r|\n/).length);
  return Array.from({ length: Math.min(lineCount, 999) }, (_, index) => index + 1).join("\n");
});

const effectiveAuthorizationGrants = computed(() =>
  profileResolution.value?.authorization_grants ?? [],
);

const enabledAllowAuthorizationGrants = computed(() =>
  effectiveAuthorizationGrants.value.filter(
    (grant) => grant.effect === "allow" && grant.status === "enabled",
  ),
);

const preauthorizedEffectIds = computed(() => {
  const values = new Set<string>();
  for (const grant of enabledAllowAuthorizationGrants.value) {
    for (const effectId of grant.effect_ids) values.add(effectId);
  }
  return values;
});

const preauthorizedToolIds = computed(() => {
  const values = new Set<string>();
  for (const grant of enabledAllowAuthorizationGrants.value) {
    for (const toolId of grant.tool_ids) values.add(toolId);
  }
  return values;
});

const preauthorizedToolCount = computed(() =>
  toolCatalog.value.filter((tool) => isToolPreauthorized(tool)).length,
);

const resolutionIssueCount = computed(() =>
  profileResolution.value?.summary.issues ?? profileResolution.value?.validation.length ?? 0,
);

const blockedAccessGrantCount = computed(() =>
  profileResolution.value?.access_grants.filter((grant) => !grant.ready).length ?? 0,
);

const readyAccessGrantCount = computed(() =>
  profileResolution.value?.access_grants.filter((grant) => grant.ready).length ?? 0,
);

const homePathLabel = computed(() =>
  editHomeDir.value.trim()
    || editWorkdir.value.trim()
    || editWorkspace.value.trim()
    || selectedProfile.value?.runtime_preferences.home_dir
    || selectedProfile.value?.runtime_preferences.workdir
    || selectedProfile.value?.runtime_preferences.workspace
    || "-",
);

const browserProfileOptions = computed(() =>
  browserProfiles.value.map((profile) => ({
    value: profile.name,
    label: `${profile.name}${profile.name === browserDefaultProfile.value ? " · system default" : ""}`,
  })),
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

watch([selectedProfileId, editMode], () => {
  void refreshSelectedProfileReadModels();
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
  homeSnapshot.value = null;
  profileResolution.value = null;
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
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  editProfileId.value = "";
  editName.value = "";
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
  editDefaultBrowserProfile.value = "";
  editMemorySpace.value = "";
  editSystemPrompt.value = "";
  editStreamByDefault.value = false;
  editTimeoutSeconds.value = 120;
  editMaxTurns.value = 99;
  homeSnapshot.value = null;
  profileResolution.value = null;
  selectedHomeFileName.value = "";
  editHomeFileContent.value = "";
}

function resetEditFormFromProfile(profile: AgentProfileApiPayload): void {
  const llmRouting = objectValue(profile.llm_routing_policy) ?? {};
  const runtimePreferences = objectValue(profile.runtime_preferences) ?? {};
  const instructionPolicy = objectValue(profile.instruction_policy) ?? {};
  const executionPolicy = objectValue(profile.execution_policy) ?? {};
  editMode.value = "update";
  editProfileId.value = profile.id;
  editName.value = profile.name;
  editTags.value = tagsForProfile(profile).join(", ");
  editEnabled.value = profile.enabled;
  editDefaultLlmId.value = textValue(llmRouting.default_llm_id, "");
  editFallbackLlmIds.value = fallbackLlmIds(profile).join(", ");
  editImageLlmId.value = textValue(llmRouting.image_llm_id, "");
  editDocumentLlmId.value = textValue(llmRouting.document_llm_id, "");
  editWorkdir.value = textValue(runtimePreferences.workdir, "");
  editWorkspace.value = textValue(runtimePreferences.workspace, "");
  editHomeDir.value = textValue(runtimePreferences.home_dir, "");
  editSandboxMode.value = textValue(runtimePreferences.sandbox_mode, "sandbox");
  editDefaultBrowserProfile.value = defaultBrowserProfileForProfile(profile);
  editMemorySpace.value = memorySpaceForProfile(profile);
  editSystemPrompt.value = textValue(instructionPolicy.system_prompt, "");
  editStreamByDefault.value = instructionPolicy.stream_by_default === true;
  editTimeoutSeconds.value = numericOr(executionPolicy.timeout_seconds, 120);
  editMaxTurns.value = numericOr(executionPolicy.max_turns, 99);
}

async function loadCatalogs(): Promise<void> {
  catalogLoadError.value = null;
  try {
    const [tools, browserCatalog] = await Promise.all([
      listTools().catch(() => [] as ToolApiPayload[]),
      listBrowserProfiles().catch(() => null),
    ]);
    toolCatalog.value = tools;
    browserProfiles.value = browserCatalog?.profiles ?? [];
    browserDefaultProfile.value = browserCatalog?.default_profile ?? "";
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

async function refreshSelectedProfileReadModels(): Promise<void> {
  if (!selectedProfileId.value || editMode.value !== "update") return;
  await Promise.all([
    loadAgentResolution(),
    loadAgentHome(),
  ]);
}

async function toggleToolPreauthorization(tool: ToolApiPayload, event: Event): Promise<void> {
  const profileId = selectedProfileId.value;
  if (!profileId || authorizationActionKey.value) return;
  const checked = (event.target as HTMLInputElement | null)?.checked === true;
  const targets = toolAuthorizationTargets(tool);
  const actionKey = toolAuthorizationActionKey(tool);
  authorizationActionKey.value = actionKey;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  try {
    for (const target of targets) {
      const payload = {
        agent_id: profileId,
        kind: target.kind,
        id: target.id,
        reason: checked
          ? "settings_agent_profiles_grant_preauthorization"
          : "settings_agent_profiles_revoke_preauthorization",
      };
      if (checked) {
        await grantAgentAuthorization(payload);
      } else {
        await revokeAgentAuthorization(payload);
      }
    }
    await loadAgentResolution();
    ownerActionMessage.value = checked
      ? "Agent preauthorization granted."
      : "Agent preauthorization revoked.";
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
    await loadAgentResolution();
  } finally {
    authorizationActionKey.value = null;
  }
}

async function toggleToolPreauthorizationFromButton(tool: ToolApiPayload): Promise<void> {
  const checked = !isToolPreauthorized(tool);
  await toggleToolPreauthorization(tool, { target: { checked } } as unknown as Event);
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
    await refreshSelectedProfileReadModels();
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
    profileResolution.value = null;
    homeSnapshot.value = null;
    await refreshSelectedProfileReadModels();
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
  try {
    const updated = profile.enabled
      ? await disableAgentProfile(profile.id, { reason: "settings_agent_profiles_owner_view" })
      : await enableAgentProfile(profile.id, { reason: "settings_agent_profiles_owner_view" });
    replaceProfile(updated);
    selectedProfileId.value = updated.id;
    resetEditFormFromProfile(updated);
    profileResolution.value = null;
    await refreshSelectedProfileReadModels();
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

function handleAgentSelectorChange(event: Event): void {
  const profileId = (event.target as HTMLSelectElement | null)?.value ?? "";
  if (!profileId || profileId === selectedProfileId.value) return;
  void selectProfile(profileId);
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
  };
  const memorySpace = editMemorySpace.value.trim();
  delete attrs.memory_space;
  delete attrs.memory_space_id;
  delete attrs.tools;
  delete attrs.tool_ids;
  delete attrs.skill_ids;
  delete attrs.skills;
  const defaultBrowserProfile = editDefaultBrowserProfile.value.trim();
  if (defaultBrowserProfile) {
    attrs.default_browser_profile = defaultBrowserProfile;
  } else {
    delete attrs.default_browser_profile;
  }
  return {
    name: editName.value.trim(),
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
      attrs,
    },
    memory: {
      ...(current?.memory ?? {}),
      enabled: current?.memory?.enabled ?? true,
      scope_ref: memorySpace || null,
      access: current?.memory?.access ?? "read_write",
    },
    reason: "settings_agent_profiles_owner_view",
  };
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
  const llmRouting = objectValue(profile.llm_routing_policy) ?? {};
  return Array.isArray(llmRouting.fallback_llm_ids)
    ? llmRouting.fallback_llm_ids.map((item) => textValue(item)).filter(Boolean)
    : [];
}

function memorySpaceForProfile(profile: AgentProfileApiPayload | null): string {
  return textValue(objectValue(profile?.memory)?.scope_ref, "");
}

function defaultBrowserProfileForProfile(profile: AgentProfileApiPayload | null): string {
  return textValue(runtimeAttrs(profile).default_browser_profile, "");
}

function runtimeAttrs(profile: AgentProfileApiPayload | null): JsonRecord {
  return objectValue(objectValue(profile?.runtime_preferences)?.attrs) ?? {};
}

function toolAuthorizationTargets(tool: ToolApiPayload): Array<{ kind: AgentAuthorizationGrantKind; id: string }> {
  const effectIds = tool.required_effect_ids.map((effectId) => effectId.trim()).filter(Boolean);
  if (effectIds.length) {
    return effectIds.map((id) => ({ kind: "effect", id }));
  }
  return [{ kind: "tool", id: tool.id }];
}

function toolAuthorizationTargetLabel(tool: ToolApiPayload): string {
  const targets = toolAuthorizationTargets(tool);
  const effects = targets.filter((target) => target.kind === "effect").map((target) => target.id);
  if (effects.length) return `Effects: ${effects.join(", ")}`;
  return "Exact tool grant";
}

function toolAuthorizationActionKey(tool: ToolApiPayload): string {
  return toolAuthorizationTargets(tool)
    .map((target) => `${target.kind}:${target.id}`)
    .join("|");
}

function isToolPreauthorized(tool: ToolApiPayload): boolean {
  if (preauthorizedToolIds.value.has(tool.id)) return true;
  const effectIds = tool.required_effect_ids.map((effectId) => effectId.trim()).filter(Boolean);
  return effectIds.length > 0 && effectIds.every((effectId) => preauthorizedEffectIds.value.has(effectId));
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
    enabled: source.enabled !== false,
    identity: objectValue(source.identity) ?? {},
    instruction_policy: objectValue(source.instruction_policy) ?? {},
    llm_routing_policy: llmRoutingPolicy,
    execution_policy: objectValue(source.execution_policy) ?? {},
    runtime_preferences: objectValue(source.runtime_preferences) ?? {},
    reason: "settings_agent_profiles_import",
  };
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
    <form class="agent-fullscreen-form" @submit.prevent="submitOwnerForm">
      <header class="agent-command-bar">
        <div class="agent-title-block">
          <span class="agent-avatar">{{ initials(selectedProfile) }}</span>
          <div>
            <h1>Agent Profiles</h1>
            <p>{{ editName || "New Agent" }} · {{ editProfileId || "agent-id" }}</p>
          </div>
        </div>
        <label class="agent-profile-selector">
          <span>Agent</span>
          <select :value="selectedProfileId ?? ''" :disabled="editMode === 'create'" @change="handleAgentSelectorChange">
            <option v-if="editMode === 'create'" value="">New Agent</option>
            <option v-for="profile in profiles" :key="profile.id" :value="profile.id">
              {{ profile.name }} · {{ profile.id }}
            </option>
          </select>
        </label>
        <div class="agent-header-actions" aria-label="Agent profile actions">
          <div class="agent-icon-toolbar">
            <button
              class="agent-icon-action agent-icon-action--accent"
              type="button"
              title="New Agent"
              aria-label="New Agent"
              :disabled="ownerActionLoading"
              @click="beginCreateProfile"
            >
              <Plus :size="16" />
            </button>
            <button
              class="agent-icon-action"
              type="button"
              title="Import"
              aria-label="Import"
              :disabled="ownerActionLoading"
              @click="triggerImportProfile"
            >
              <Import :size="15" />
            </button>
            <button
              class="agent-icon-action"
              type="button"
              title="Refresh"
              aria-label="Refresh"
              :disabled="isLoading"
              @click="loadAgentProfiles"
            >
              <RefreshCcw :size="15" />
            </button>
            <button class="agent-icon-action" type="button" title="More actions" aria-label="More actions">
              <MoreVertical :size="15" />
            </button>
            <span class="agent-icon-divider" aria-hidden="true" />
            <button class="agent-icon-action" type="button" title="Cancel" aria-label="Cancel" @click="closeCreateMode">
              <X :size="16" />
            </button>
            <button
              class="agent-icon-action agent-icon-action--save"
              type="button"
              title="Save Changes"
              aria-label="Save Changes"
              :disabled="!canSubmitOwnerForm"
              @click="submitOwnerForm"
            >
              <Save :size="15" />
            </button>
            <template v-if="editMode === 'update'">
              <span class="agent-icon-divider" aria-hidden="true" />
              <button
                class="agent-icon-action"
                type="button"
                :title="selectedProfile?.enabled ? 'Disable' : 'Enable'"
                :aria-label="selectedProfile?.enabled ? 'Disable' : 'Enable'"
                :disabled="ownerActionLoading"
                @click="toggleSelectedProfile"
              >
                <Power :size="15" />
              </button>
              <button
                class="agent-icon-action agent-icon-action--danger"
                type="button"
                title="Delete"
                aria-label="Delete"
                :disabled="ownerActionLoading"
                @click="deleteSelectedProfile"
              >
                <Trash2 :size="15" />
              </button>
            </template>
            <input
              ref="importInput"
              accept="application/json,.json"
              class="agent-import-input"
              type="file"
              @change="importAgentProfileFile"
            />
          </div>
        </div>
      </header>

      <div class="agent-content-scroll">
        <p v-if="loadError" class="agent-page-error">{{ loadError }}</p>
        <section class="agent-workbench">
          <div class="agent-metric-strip" aria-label="Agent profile summary">
            <article class="agent-metric agent-metric--effective">
              <span class="agent-metric-icon"><CheckCircle2 :size="24" /></span>
              <div>
                <span>Effective</span>
                <strong>{{ titleize(profileResolution?.summary.status, resolutionLoading ? "Loading" : "Not loaded") }}</strong>
                <small>{{ resolutionIssueCount }} issues</small>
              </div>
            </article>
            <article class="agent-metric agent-metric--capabilities">
              <span class="agent-metric-icon"><Box :size="24" /></span>
              <div>
                <span>Tools</span>
                <strong>{{ preauthorizedToolCount }} trusted tools</strong>
                <small>{{ toolCatalog.length }} catalog tools</small>
              </div>
            </article>
            <article class="agent-metric agent-metric--access">
              <span class="agent-metric-icon"><ShieldCheck :size="24" /></span>
              <div>
                <span>Access</span>
                <strong>{{ readyAccessGrantCount }} ready · {{ blockedAccessGrantCount }} blocked</strong>
                <small>{{ effectiveAuthorizationGrants.length }} grants resolved</small>
              </div>
            </article>
            <article class="agent-metric agent-metric--memory">
              <span class="agent-metric-icon"><Database :size="24" /></span>
              <div>
                <span>Memory</span>
                <strong>{{ editMemorySpace || "Default memory" }}</strong>
                <small>{{ selectedProfile?.memory?.enabled === false ? "disabled" : "managed by Memory" }}</small>
              </div>
            </article>
            <article class="agent-metric agent-metric--updated">
              <span class="agent-metric-icon"><Clock3 :size="24" /></span>
              <div>
                <span>Updated</span>
                <strong>{{ formatRelativeTimestamp(selectedProfile?.updated_at || selectedProfile?.created_at) }}</strong>
                <small>{{ selectedProfile?.updated_at || selectedProfile?.created_at ? "" : "-" }}</small>
              </div>
            </article>
            <article class="agent-metric agent-metric--home">
              <span class="agent-metric-icon"><Folder :size="24" /></span>
              <div>
                <span>Home Directory</span>
                <strong>{{ homePathLabel }}</strong>
                <small>{{ homeSnapshot?.home_dir || "not synced" }}</small>
              </div>
            </article>
          </div>

          <div class="agent-workbench-summary">
            {{ preauthorizedToolCount }} trusted tools · {{ effectiveAuthorizationGrants.length }} grants · {{ homeSnapshot?.files.length ?? 0 }} home files
          </div>

          <section class="agent-config-grid" aria-label="Agent profile configuration">
            <article class="agent-panel agent-panel--identity">
              <header class="agent-panel-title">
                <h3><UserCog :size="15" /> Identity & Routing</h3>
                <span>{{ editMode === "create" ? "new profile" : editProfileId }}</span>
              </header>
              <div class="dense-field-grid dense-field-grid--identity">
                <label class="dense-field">
                  <span>Display Name</span>
                  <input v-model="editName" placeholder="Support Agent" />
                </label>
                <label class="dense-field">
                  <span>Profile ID</span>
                  <input v-model="editProfileId" :readonly="editMode === 'update'" placeholder="support-prod" />
                </label>
                <div class="dense-status-field">
                  <span>Status</span>
                  <label class="profile-status-toggle" :class="{ on: editEnabled }">
                    <i />
                    <em>{{ editEnabled ? "Enabled" : "Disabled" }}</em>
                    <span class="mini-switch">
                      <input v-model="editEnabled" type="checkbox" />
                      <b />
                    </span>
                  </label>
                </div>
                <label class="dense-field">
                  <span>Tags</span>
                  <input v-model="editTags" placeholder="support, internal" />
                </label>
                <label class="dense-field">
                  <span>Default LLM</span>
                  <select v-model="editDefaultLlmId">
                    <option v-for="llm in llmProfiles" :key="llm.id" :value="llm.id">
                      {{ llm.model_name }} · {{ llm.provider }}
                    </option>
                    <option v-if="!llmProfiles.length" :value="editDefaultLlmId">{{ editDefaultLlmId || "No LLM profiles loaded" }}</option>
                  </select>
                </label>
                <label class="dense-field">
                  <span>Fallback LLMs</span>
                  <input v-model="editFallbackLlmIds" placeholder="comma,separated,llm.ids" />
                </label>
                <label class="dense-field">
                  <span>Image LLM</span>
                  <input v-model="editImageLlmId" placeholder="optional" />
                </label>
                <label class="dense-field">
                  <span>Document LLM</span>
                  <input v-model="editDocumentLlmId" placeholder="optional" />
                </label>
                <label class="dense-field dense-field--full dense-field--prompt">
                  <span>System Prompt · {{ editSystemPrompt.length }} chars</span>
                  <textarea v-model="editSystemPrompt" rows="7" />
                </label>
              </div>
            </article>

            <article class="agent-panel agent-panel--runtime">
              <header class="agent-panel-title">
                <h3><Settings2 :size="15" /> Runtime & Memory</h3>
                <span>{{ editSandboxMode }}</span>
              </header>
              <div class="dense-field-grid dense-field-grid--runtime">
                <label class="dense-field">
                  <span>Environment</span>
                  <select v-model="editSandboxMode">
                    <option value="sandbox">Sandbox</option>
                    <option value="workspace">Workspace</option>
                    <option value="container">Container</option>
                    <option value="hybrid">Hybrid</option>
                  </select>
                </label>
                <label class="dense-field">
                  <span>Browser Profile</span>
                  <select v-model="editDefaultBrowserProfile">
                    <option value="">System default{{ browserDefaultProfile ? ` · ${browserDefaultProfile}` : "" }}</option>
                    <option v-for="profile in browserProfileOptions" :key="profile.value" :value="profile.value">
                      {{ profile.label }}
                    </option>
                    <option
                      v-if="editDefaultBrowserProfile && !browserProfiles.some((profile) => profile.name === editDefaultBrowserProfile)"
                      :value="editDefaultBrowserProfile"
                    >
                      {{ editDefaultBrowserProfile }} · missing
                    </option>
                  </select>
                </label>
                <label class="dense-field">
                  <span>Timeout</span>
                  <input v-model.number="editTimeoutSeconds" min="1" type="number" />
                </label>
                <label class="dense-field">
                  <span>Max Turns</span>
                  <input v-model.number="editMaxTurns" min="1" type="number" />
                </label>
                <label class="dense-field">
                  <span>Workdir</span>
                  <input v-model="editWorkdir" placeholder="/agents/support" />
                </label>
                <label class="dense-field">
                  <span>Home Directory</span>
                  <input v-model="editHomeDir" />
                </label>
                <label class="dense-field">
                  <span>Workspace</span>
                  <input v-model="editWorkspace" />
                </label>
                <label class="dense-field">
                  <span>Memory Space</span>
                  <input v-model="editMemorySpace" :placeholder="editProfileId || 'agent-id'" />
                </label>
                <label class="dense-checkbox">
                  <input v-model="editStreamByDefault" type="checkbox" />
                  <span>Stream by default</span>
                </label>
              </div>
            </article>

            <article class="agent-panel agent-panel--tools">
              <header class="agent-panel-title">
                <h3><Link2 :size="15" /> Tool Access</h3>
                <span>{{ preauthorizedToolCount }} trusted · {{ effectiveAuthorizationGrants.length }} grants</span>
              </header>
              <label class="tool-search">
                <Search :size="14" />
                <input v-model="toolSearchTerm" aria-label="Search tools" type="search" />
              </label>
              <div class="tool-access-table">
                <div class="tool-access-row tool-access-row--head">
                  <span>Tool</span>
                  <span>Auth Target</span>
                  <span>Trust</span>
                </div>
                <div class="tool-access-body">
                  <article v-for="tool in visibleToolCatalog" :key="tool.id" class="tool-access-row">
                    <div class="tool-main">
                      <strong>{{ tool.name || tool.id }}</strong>
                      <small>{{ tool.id }}</small>
                    </div>
                    <small class="tool-target">{{ toolAuthorizationTargetLabel(tool) }}</small>
                    <button
                      class="tool-trust-button"
                      :class="{ active: isToolPreauthorized(tool) }"
                      :disabled="resolutionLoading || authorizationActionKey === toolAuthorizationActionKey(tool)"
                      type="button"
                      @click="toggleToolPreauthorizationFromButton(tool)"
                    >
                      {{ authorizationActionKey === toolAuthorizationActionKey(tool) ? "Saving" : "Trust" }}
                    </button>
                  </article>
                  <p v-if="!toolCatalog.length" class="grant-empty">No tools returned by the Tool catalog.</p>
                  <p v-else-if="!filteredToolCatalog.length" class="grant-empty">No tools match this search.</p>
                </div>
              </div>
            </article>
          </section>

          <section class="agent-work-grid" aria-label="Agent profile work surfaces">
            <article class="agent-panel agent-panel--home-files">
              <header class="agent-panel-title">
                <h3><Folder :size="15" /> Agent Home</h3>
                <span>{{ homeSnapshot?.files.length ?? 0 }} files</span>
              </header>
              <div class="home-toolbar">
                <div class="home-path">
                  <strong>{{ homeSnapshot?.home_dir || "No home snapshot loaded" }}</strong>
                  <small>{{ homeSnapshot?.workdir || "workdir follows home" }}</small>
                </div>
                <div class="home-actions">
                  <button type="button" :disabled="homeLoading" @click="loadAgentHome"><RefreshCcw :size="13" />Reload</button>
                  <button type="button" :disabled="ownerActionLoading" @click="syncSelectedHome"><RefreshCcw :size="13" />Sync</button>
                  <button type="button" :disabled="ownerActionLoading" @click="exportSelectedHome"><Download :size="13" />Export</button>
                </div>
              </div>
              <div class="home-files-table">
                <div class="home-files-head">
                  <span>Name</span>
                  <span>Type</span>
                  <span>Status</span>
                  <span>Updated</span>
                </div>
                <div class="home-files-body">
                  <button
                    v-for="file in homeSnapshot?.files ?? []"
                    :key="file.name"
                    type="button"
                    class="home-file-row"
                    :class="{ active: selectedHomeFileName === file.name }"
                    @click="selectHomeFile(file.name)"
                  >
                    <span class="home-file-name"><FileText :size="14" />{{ file.name }}</span>
                    <span>{{ file.language || "-" }}</span>
                    <span :class="{ ready: file.exists, blocked: !file.exists }">{{ file.exists ? "exists" : "missing" }}</span>
                    <span>{{ formatRelativeTimestamp(selectedProfile?.updated_at || selectedProfile?.created_at) }}</span>
                  </button>
                  <p v-if="!homeLoading && !(homeSnapshot?.files.length)" class="grant-empty">No agent home files loaded.</p>
                </div>
              </div>
              <p v-if="homeError" class="settings-tone-danger">{{ homeError }}</p>
            </article>

            <article class="agent-panel agent-panel--home-editor">
              <header class="agent-panel-title home-editor-title">
                <div>
                  <h3><FileText :size="15" /> {{ selectedHomeFileName || "Agent Home File" }}</h3>
                  <small>{{ selectedHomeFile?.path || "Select a file from Agent Home" }}</small>
                </div>
                <div class="home-editor-actions">
                  <button type="button" :disabled="!selectedHomeFileName || ownerActionLoading" @click="saveSelectedHomeFile">
                    Save Home File
                  </button>
                  <button type="button" aria-label="Expand editor"><Maximize2 :size="14" /></button>
                </div>
              </header>
              <div class="home-code-editor">
                <pre class="home-line-numbers">{{ homeEditorLineNumbers }}</pre>
                <textarea v-model="editHomeFileContent" :disabled="!selectedHomeFileName" />
              </div>
            </article>
          </section>
        </section>

        <p v-if="detailError" class="settings-tone-danger">{{ detailError }}</p>
        <p v-if="catalogLoadError" class="settings-tone-danger">{{ catalogLoadError }}</p>
        <p v-if="resolutionError" class="settings-tone-danger">{{ resolutionError }}</p>
        <p v-if="ownerActionError" class="settings-tone-danger">{{ ownerActionError }}</p>
        <p v-else-if="ownerActionMessage" class="settings-tone-success">{{ ownerActionMessage }}</p>
      </div>

    </form>
  </main>
</template>

<style scoped>
.agent-profiles-page {
  --agent-green: #118848;
  --agent-accent: #5b8cff;
  --agent-gray: #98a2b3;
  --agent-line: color-mix(in srgb, var(--border-subtle) 54%, transparent);
  --agent-line-strong: color-mix(in srgb, var(--border-subtle) 78%, transparent);
  --agent-canvas: color-mix(in srgb, var(--surface-page) 92%, black 5%);
  --agent-surface: color-mix(in srgb, var(--surface-panel) 82%, transparent);
  --agent-surface-soft: color-mix(in srgb, var(--surface-panel) 58%, transparent);
  --agent-input-bg: color-mix(in srgb, var(--surface-input) 62%, transparent);
  height: calc(100vh - 50px);
  min-height: 0;
  padding: 0;
  overflow: hidden;
  background: var(--agent-canvas);
}

.agent-fullscreen-form {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  height: 100%;
  min-height: 0;
}

.agent-command-bar {
  display: grid;
  grid-template-columns: minmax(250px, 0.9fr) minmax(300px, 460px) auto;
  align-items: center;
  gap: 16px;
  min-height: 52px;
  padding: 4px 24px;
  border-bottom: 0;
  background: transparent;
}

.agent-title-block {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.agent-avatar {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-2);
  border: 1px solid color-mix(in srgb, var(--agent-green) 38%, transparent);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--agent-green) 74%, white 5%), color-mix(in srgb, var(--agent-green) 68%, black 14%));
  color: white;
  font-size: 13px;
  font-weight: 800;
}

.agent-title-block h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 760;
  line-height: 1.1;
}

.agent-title-block p {
  margin: 3px 0 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-header-actions {
  display: flex;
  justify-self: end;
  min-width: max-content;
}

.agent-import-input {
  display: none;
}

.agent-icon-toolbar {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: max-content;
}

.agent-icon-action {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    background 0.16s ease,
    color 0.16s ease,
    opacity 0.16s ease;
}

.agent-icon-action:hover:not(:disabled) {
  border-color: var(--agent-line-strong);
  background: var(--agent-surface-soft);
  color: var(--text-primary);
}

.agent-icon-action:disabled {
  cursor: not-allowed;
  opacity: 0.46;
}

.agent-icon-action--accent {
  border-color: color-mix(in srgb, var(--agent-accent) 54%, var(--agent-line));
  color: color-mix(in srgb, var(--agent-accent) 86%, white 8%);
}

.agent-icon-action--accent:hover:not(:disabled) {
  background: color-mix(in srgb, var(--agent-accent) 12%, transparent);
}

.agent-icon-action--save {
  border-color: color-mix(in srgb, var(--agent-accent) 76%, transparent);
  background: color-mix(in srgb, var(--agent-accent) 82%, black 7%);
  color: #ffffff;
}

.agent-icon-action--save:hover:not(:disabled) {
  background: color-mix(in srgb, var(--agent-accent) 72%, black 14%);
  color: #ffffff;
}

.agent-icon-action--danger {
  border-color: color-mix(in srgb, var(--color-danger) 46%, transparent);
  color: var(--color-danger);
}

.agent-icon-action--danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
}

.agent-icon-divider {
  width: 1px;
  height: 20px;
  margin-inline: 4px;
  background: var(--agent-line);
}

.agent-profile-selector {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 3px;
  min-width: 0;
  justify-self: stretch;
  width: 100%;
}

.agent-profile-selector span {
  color: var(--text-secondary);
  font-size: 9.5px;
  font-weight: 800;
  text-transform: uppercase;
  white-space: nowrap;
}

.agent-profile-selector select {
  width: 100%;
  min-width: 0;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: var(--agent-input-bg);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 800;
}

.agent-content-scroll {
  min-height: 0;
  overflow: auto;
}

.agent-page-error,
.settings-tone-danger,
.settings-tone-success {
  margin: 10px 24px 0;
  font-size: 12px;
  font-weight: 700;
}

.agent-page-error,
.settings-tone-danger {
  color: var(--color-danger);
}

.settings-tone-success {
  color: var(--agent-green);
}

.agent-workbench {
  display: grid;
  grid-template-rows: 76px 20px minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
  box-sizing: border-box;
  height: 100%;
  min-height: 0;
  padding: 10px 24px 12px;
}

.agent-metric-strip {
  display: grid;
  grid-template-columns: 0.78fr 0.88fr 0.88fr 0.86fr 0.72fr 1.28fr;
  gap: 8px;
  min-width: 0;
  min-height: 0;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.agent-metric {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 38%, transparent);
}

.agent-metric-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 999px;
  color: var(--agent-green);
  background: color-mix(in srgb, var(--agent-green) 18%, transparent);
}

.agent-metric--capabilities .agent-metric-icon {
  color: #8b5cf6;
  background: color-mix(in srgb, #8b5cf6 20%, transparent);
}

.agent-metric--memory .agent-metric-icon {
  color: #3b82f6;
  background: color-mix(in srgb, #3b82f6 18%, transparent);
}

.agent-metric--updated .agent-metric-icon {
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--text-secondary) 14%, transparent);
}

.agent-metric div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.agent-metric span:not(.agent-metric-icon) {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 780;
  text-transform: uppercase;
}

.agent-metric strong,
.agent-metric small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-metric strong {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 760;
}

.agent-metric small {
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 620;
}

.agent-workbench-summary {
  display: flex;
  align-items: center;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 650;
}

.agent-config-grid,
.agent-work-grid {
  display: grid;
  gap: 8px;
  min-width: 0;
  min-height: 0;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.agent-config-grid {
  grid-template-columns: minmax(0, 1.12fr) minmax(0, 1fr) minmax(0, 1.28fr);
}

.agent-work-grid {
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1fr);
}

.agent-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  padding: 12px 14px;
  border: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: var(--agent-surface);
  box-shadow: none;
  overflow: hidden;
}

.agent-panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  min-height: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--agent-line);
}

.agent-panel-title h3 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 780;
}

.agent-panel-title span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dense-field-grid {
  display: grid;
  gap: 8px 9px;
  align-content: start;
  min-height: 0;
  overflow: auto;
  padding-top: 8px;
  padding-right: 2px;
  scrollbar-gutter: stable;
}

.dense-field-grid--runtime {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.dense-field-grid--identity {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 0.92fr);
  row-gap: 10px;
}

.agent-panel--identity .dense-field--prompt {
  min-height: 164px;
  margin-top: 6px;
}

.dense-field,
.dense-checkbox {
  min-width: 0;
  color: var(--text-primary);
  font-size: 10.5px;
  font-weight: 650;
}

.dense-status-field {
  display: grid;
  grid-template-rows: auto 28px;
  gap: 3px;
  min-width: 0;
  color: var(--text-primary);
  font-size: 10.5px;
  font-weight: 650;
}

.dense-status-field > span {
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-status-toggle {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--agent-line) 88%, transparent);
  border-radius: var(--radius-2);
  background: var(--agent-input-bg);
  cursor: pointer;
}

.profile-status-toggle i {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--agent-gray);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--agent-gray) 12%, transparent);
}

.profile-status-toggle.on i {
  background: var(--agent-green);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--agent-green) 16%, transparent);
}

.profile-status-toggle em {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 11.5px;
  font-style: normal;
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-switch {
  position: relative;
  width: 32px;
  height: 18px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--text-muted) 28%, transparent);
}

.mini-switch input {
  position: absolute;
  inset: 0;
  opacity: 0;
}

.mini-switch b {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #fff;
  transition: transform 0.16s ease;
}

.profile-status-toggle.on .mini-switch {
  background: var(--agent-green);
}

.profile-status-toggle.on .mini-switch b {
  transform: translateX(14px);
}

.dense-field {
  display: grid;
  grid-template-rows: auto 28px;
  gap: 4px;
}

.dense-field--full {
  grid-column: 1 / -1;
}

.dense-field--span-2 {
  grid-column: span 2;
}

.dense-field span {
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dense-field input,
.dense-field textarea,
.dense-field select {
  width: 100%;
  min-width: 0;
  border: 1px solid color-mix(in srgb, var(--agent-line) 88%, transparent);
  border-radius: var(--radius-2);
  background: var(--agent-input-bg);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 450;
}

.dense-field input:focus,
.dense-field textarea:focus,
.dense-field select:focus,
.home-code-editor textarea:focus {
  border-color: color-mix(in srgb, var(--agent-accent) 62%, var(--agent-line));
  outline: none;
}

.dense-field input,
.dense-field select {
  height: 28px;
  padding: 0 8px;
}

.dense-field textarea {
  height: 42px;
  min-height: 42px;
  padding: 6px 8px;
  line-height: 1.35;
  resize: none;
}

.dense-field--prompt {
  grid-template-rows: auto minmax(146px, 1fr);
}

.dense-field--prompt textarea {
  height: 100%;
  min-height: 146px;
}

.dense-field input[readonly] {
  background: color-mix(in srgb, var(--surface-sidebar) 52%, transparent);
  color: var(--text-muted);
}

.dense-checkbox {
  display: flex;
  align-items: end;
  gap: 7px;
  height: 46px;
  padding-bottom: 5px;
}

.dense-checkbox input {
  width: 14px;
  height: 14px;
}

.tool-main strong,
.tool-main small,
.tool-target,
.home-path strong,
.home-path small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-main strong {
  color: var(--text-primary);
  font-size: 11.5px;
  font-weight: 680;
}

.tool-main small,
.tool-target,
.grant-empty {
  margin: 0;
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 560;
}

.tool-main strong {
  font-size: 11.5px;
  font-weight: 680;
}

.tool-access-table {
  display: grid;
  grid-template-rows: 22px minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}

.agent-panel--tools {
  grid-template-rows: auto 26px minmax(0, 1fr);
}

.tool-search {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin: 6px 0 5px;
  padding: 0 8px;
  border: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: var(--agent-input-bg);
  color: var(--text-muted);
}

.tool-search input {
  width: 100%;
  min-width: 0;
  height: 24px;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11.5px;
  outline: none;
}

.tool-access-body {
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable;
}

.tool-access-row {
  display: grid;
  grid-template-columns: minmax(170px, 1.45fr) minmax(130px, 0.9fr) 58px;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  padding: 3px 0;
  border-top: 1px solid color-mix(in srgb, var(--agent-line) 72%, transparent);
}

.tool-access-row--head {
  min-height: 24px;
  padding: 2px 0;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 760;
  text-transform: uppercase;
}

.tool-trust-button {
  justify-self: end;
  min-height: 24px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--agent-accent) 54%, var(--agent-line));
  border-radius: var(--radius-2);
  background: transparent;
  color: color-mix(in srgb, var(--agent-accent) 86%, white 8%);
  cursor: pointer;
  font-size: 10.5px;
  font-weight: 700;
}

.tool-trust-button.active {
  border-color: color-mix(in srgb, var(--agent-green) 56%, transparent);
  color: var(--agent-green);
}

.tool-trust-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.tool-main {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.agent-panel--home-editor {
  grid-template-rows: auto minmax(0, 1fr);
}

.agent-panel--home-files {
  grid-template-rows: auto auto minmax(0, 1fr);
}

.home-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  min-height: 48px;
  padding: 8px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--agent-line) 72%, transparent);
}

.home-path {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.home-path strong {
  color: var(--text-primary);
  font-size: 11.5px;
  font-weight: 760;
}

.home-path small {
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 600;
}

.home-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(62px, auto));
  gap: 6px;
}

.home-actions button,
.home-editor-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 28px;
  border: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  font-size: 11px;
  font-weight: 760;
}

.home-actions button:hover,
.home-editor-actions button:hover:not(:disabled) {
  border-color: var(--agent-line-strong);
  background: var(--agent-surface-soft);
}

.home-actions button:disabled,
.home-editor-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.home-files-table {
  display: grid;
  grid-template-rows: 28px minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  padding-top: 4px;
}

.home-files-head,
.home-file-row {
  display: grid;
  grid-template-columns: minmax(150px, 1.25fr) minmax(80px, 0.46fr) minmax(80px, 0.46fr) minmax(110px, 0.6fr);
  align-items: center;
  gap: 10px;
  min-height: 0;
}

.home-files-head {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 760;
  text-transform: uppercase;
}

.home-files-body {
  display: grid;
  align-content: start;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable;
}

.home-file-row {
  min-height: 26px;
  padding: 0 8px;
  border: 0;
  border-top: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
  font-size: 11.5px;
}

.home-file-row.active {
  background: color-mix(in srgb, #6d5dfc 18%, transparent);
}

.home-file-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.home-file-row span,
.home-editor-title small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-file-row .ready {
  color: var(--agent-green);
}

.home-file-row .blocked {
  color: var(--color-danger);
}

.home-editor-title {
  align-items: start;
}

.home-editor-title > div:first-child {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.home-editor-title small {
  color: var(--text-secondary);
  font-size: 10.5px;
}

.home-editor-actions {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  min-width: max-content;
}

.home-code-editor {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  margin-top: 8px;
  border: 1px solid var(--agent-line);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-input) 42%, transparent);
  overflow: hidden;
}

.home-line-numbers {
  min-height: 0;
  margin: 0;
  padding: 8px 0;
  border-right: 1px solid var(--agent-line);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  overflow: hidden;
  text-align: center;
  user-select: none;
}

.home-code-editor textarea {
  height: 100%;
  min-height: 0;
  padding: 8px;
  border: 0;
  background: transparent;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.55;
  resize: none;
}

.agent-panel .settings-tone-danger {
  margin: 6px 0 0;
}

@media (max-width: 1180px) {
  .agent-command-bar {
    grid-template-columns: minmax(240px, 1fr) minmax(260px, 360px) auto;
  }

  .agent-header-actions {
    justify-self: end;
  }

  .agent-workbench {
    height: auto;
    grid-template-rows: auto auto auto auto;
  }

  .agent-metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .agent-config-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .agent-work-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .agent-profiles-page {
    height: auto;
    min-height: 0;
    overflow: visible;
  }

  .agent-fullscreen-form {
    min-height: 100vh;
  }

  .agent-command-bar {
    grid-template-columns: minmax(0, 1fr);
  }

  .agent-profile-selector,
  .agent-header-actions {
    grid-column: 1 / -1;
    justify-self: stretch;
  }

  .agent-header-actions {
    justify-content: flex-start;
  }

  .agent-icon-toolbar {
    flex-wrap: wrap;
    justify-content: flex-start;
    min-width: 0;
  }

  .agent-workbench,
  .agent-config-grid,
  .agent-work-grid,
  .agent-metric-strip,
  .dense-field-grid--identity,
  .dense-field-grid--runtime,
  .home-files-head,
  .home-file-row,
  .home-actions {
    grid-template-columns: minmax(0, 1fr);
  }

  .agent-workbench {
    padding-inline: 14px;
  }

  .tool-access-row {
    grid-template-columns: minmax(0, 1fr) 64px;
  }

  .tool-access-row > .tool-target,
  .tool-access-row--head > span:nth-child(2) {
    display: none;
  }

}
</style>
