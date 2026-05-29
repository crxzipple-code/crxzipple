<script setup lang="ts">
import {
  Brain,
  CheckCircle2,
  KeyRound,
  Layers,
  Play,
  Plus,
  RefreshCcw,
  Save,
  Search,
  Zap,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import UiButton from "@/shared/ui/UiButton.vue";
import {
  getAccessOverview,
  type AccessCredentialBindingPayload,
} from "../ownerApis/accessAssets";
import {
  createLlmProfile,
  getLlmProfile,
  listLlmProfiles,
  setLlmProfileEnabled,
  testLlmProfile,
  updateLlmProfile,
  type LlmInvocationApiPayload,
  type LlmProfileApiPayload,
  type LlmProfileWritePayload,
} from "../ownerApis/llmProfiles";

const PROVIDER_OPTIONS = ["openai", "openai_codex", "openai_compatible", "anthropic", "google", "ollama"];
const API_FAMILY_OPTIONS = [
  "openai_responses",
  "openai_codex_responses",
  "openai_chat_compatible",
  "anthropic_messages",
  "gemini_generate_content",
  "ollama_native",
];
const MODEL_FAMILY_OPTIONS = ["general", "codex", "reasoning", "vision"];
const REASONING_EFFORT_OPTIONS = ["", "low", "medium", "high"];
type CredentialExpectationKind = "api_key" | "oauth2_account" | "optional_api_key" | "none" | "any";

interface CredentialExpectation {
  kind: CredentialExpectationKind;
  label: string;
  requiresCredential: boolean;
}

const profiles = ref<LlmProfileApiPayload[]>([]);
const selectedProfileId = ref<string | null>(null);
const isCreatingProfile = ref(false);
const isLoading = ref(false);
const detailLoading = ref(false);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const searchTerm = ref("");
const editorError = ref<string | null>(null);
const actionMessage = ref<string | null>(null);
const actionError = ref<string | null>(null);
const isSaving = ref(false);
const isToggling = ref(false);
const isTesting = ref(false);
const testPrompt = ref("Reply with a short readiness check.");
const testError = ref<string | null>(null);
const testResult = ref<LlmInvocationApiPayload | null>(null);
const editProfileId = ref("");
const editProvider = ref("");
const editApiFamily = ref("");
const editModelName = ref("");
const editContextWindowTokens = ref("");
const editModelFamily = ref("general");
const editCapabilities = ref("");
const editBaseUrl = ref("");
const editCredentialBindingId = ref("");
const editTimeoutSeconds = ref("60");
const editMaxConcurrency = ref("");
const editConcurrencyKey = ref("");
const editTemperature = ref("");
const editTopP = ref("");
const editMaxOutputTokens = ref("");
const editReasoningEffort = ref("");
const editEnabled = ref(true);
const credentialBindings = ref<AccessCredentialBindingPayload[]>([]);
const credentialBindingsLoading = ref(false);
const credentialBindingsError = ref<string | null>(null);

const selectedProfile = computed(() =>
  profiles.value.find((profile) => profile.id === selectedProfileId.value) ?? null,
);

const filteredProfiles = computed(() => {
  const query = searchTerm.value.trim().toLowerCase();
  if (!query) return profiles.value;
  return profiles.value.filter((profile) =>
    [
      profile.id,
      profile.provider,
      profile.api_family,
      profile.model_name,
      profile.model_family,
      profile.credential_binding_id,
      profile.source_kind,
      ...profile.capabilities,
    ].filter(Boolean).join(" ").toLowerCase().includes(query),
  );
});

const enabledCount = computed(() => profiles.value.filter((profile) => profile.enabled).length);
const disabledCount = computed(() => Math.max(0, profiles.value.length - enabledCount.value));
const usedCredentialBindingCount = computed(() =>
  new Set(
    profiles.value
      .map((profile) => profile.credential_binding_id)
      .filter((value): value is string => Boolean(value)),
  ).size,
);
const credentialExpectation = computed(() =>
  credentialExpectationFor(editProvider.value, editApiFamily.value),
);
const credentialBindingOptions = computed(() =>
  [...credentialBindings.value].sort((left, right) => {
    const leftCompatibility = credentialBindingCompatibility(left, credentialExpectation.value);
    const rightCompatibility = credentialBindingCompatibility(right, credentialExpectation.value);
    if (leftCompatibility.compatible !== rightCompatibility.compatible) {
      return leftCompatibility.compatible ? -1 : 1;
    }
    const byRank = credentialBindingRank(left) - credentialBindingRank(right);
    if (byRank !== 0) return byRank;
    return left.binding_id.localeCompare(right.binding_id);
  }),
);
const credentialBindingCount = computed(() => credentialBindingOptions.value.length);
const selectedCredentialBinding = computed(() =>
  credentialBindingOptions.value.find((binding) => binding.binding_id === editCredentialBindingId.value) ?? null,
);
const selectedCredentialCompatibility = computed(() =>
  selectedCredentialBinding.value
    ? credentialBindingCompatibility(selectedCredentialBinding.value, credentialExpectation.value)
    : null,
);
const currentCredentialBindingMissing = computed(() =>
  Boolean(editCredentialBindingId.value && !selectedCredentialBinding.value && !credentialBindingsLoading.value),
);
const credentialBindingSelectionError = computed(() => {
  if (credentialBindingsError.value) return credentialBindingsError.value;
  if (currentCredentialBindingMissing.value) return `${editCredentialBindingId.value} is not registered in Access.`;
  if (credentialExpectation.value.requiresCredential && !editCredentialBindingId.value) {
    return `${credentialExpectation.value.label} credential is required.`;
  }
  if (selectedCredentialCompatibility.value && !selectedCredentialCompatibility.value.compatible) {
    return selectedCredentialCompatibility.value.reason;
  }
  return null;
});
const limitedProfilesCount = computed(() =>
  profiles.value.filter((profile) => profile.max_concurrency !== null).length,
);
const unlimitedProfilesCount = computed(() =>
  Math.max(0, profiles.value.length - limitedProfilesCount.value),
);
const isRefreshing = computed(() => isLoading.value || credentialBindingsLoading.value);

const canEditProfile = computed(() => isCreatingProfile.value || Boolean(selectedProfile.value));
const canSaveProfile = computed(() =>
  canEditProfile.value && !credentialBindingSelectionError.value,
);
const canRunProfileProbe = computed(() =>
  canEditProfile.value
  && !credentialBindingSelectionError.value
  && Boolean(editProfileId.value.trim())
  && Boolean(editProvider.value.trim())
  && Boolean(editApiFamily.value.trim())
  && Boolean(editModelName.value.trim()),
);
const selectedTitle = computed(() => {
  if (isCreatingProfile.value) return "New LLM profile";
  const profile = selectedProfile.value;
  if (!profile) return "Select an LLM profile";
  return `${profile.provider} / ${profile.model_name}`;
});
const selectedSubtitle = computed(() => {
  if (isCreatingProfile.value) return "Manual profile · POST /llms";
  const profile = selectedProfile.value;
  if (!profile) return "Profiles are loaded directly from /llms.";
  return `${profile.id} · ${profile.api_family} · ${profile.model_family}`;
});
const probeStatusLabel = computed(() => {
  if (isTesting.value) return "Running";
  if (testResult.value?.status) return testResult.value.status;
  if (testError.value) return "request failed";
  return "idle";
});
const probeResultText = computed(() => {
  if (testResult.value?.error) return testResult.value.error.message;
  return testResult.value?.result?.text ?? "";
});
const probeUsageLabel = computed(() => formatUsage(testResult.value?.result?.usage ?? null));
const probeFinishLabel = computed(() => testResult.value?.result?.finish_reason ?? "-");
const probeRequestLabel = computed(() => testResult.value?.provider_request_id ?? testResult.value?.id ?? "-");
const credentialBindingNote = computed(() => {
  if (credentialBindingsLoading.value) return "Loading credential bindings from Access...";
  if (credentialBindingSelectionError.value) return credentialBindingSelectionError.value;
  if (selectedCredentialBinding.value) {
    return `${formatCredentialBindingMeta(selectedCredentialBinding.value)} · matches ${credentialExpectation.value.label}`;
  }
  if (!credentialBindingOptions.value.length) return "No Access credential bindings found. Create one in Access first.";
  if (credentialExpectation.value.kind === "none") return "This provider normally does not need a credential.";
  return `Select an Access-owned ${credentialExpectation.value.label} binding.`;
});
const credentialBindingNoteTone = computed(() => {
  if (credentialBindingSelectionError.value) return "is-error";
  if (selectedCredentialBinding.value) return "is-success";
  return "is-muted";
});

onMounted(() => {
  void loadAll();
});

async function loadAll(): Promise<void> {
  await Promise.all([loadProfiles(), loadAccessCredentialBindings()]);
}

async function loadProfiles(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  detailError.value = null;
  try {
    const loaded = await listLlmProfiles();
    profiles.value = loaded;
    const selectedStillExists = loaded.some((profile) => profile.id === selectedProfileId.value);
    selectedProfileId.value = selectedStillExists
      ? selectedProfileId.value
      : loaded[0]?.id ?? null;
    syncFormFromProfile();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    profiles.value = [];
    selectedProfileId.value = null;
    syncFormFromProfile(null);
  } finally {
    isLoading.value = false;
  }
}

async function loadAccessCredentialBindings(): Promise<void> {
  credentialBindingsLoading.value = true;
  credentialBindingsError.value = null;
  try {
    const overview = await getAccessOverview();
    credentialBindings.value = overview.credential_bindings ?? [];
  } catch (error) {
    credentialBindingsError.value = error instanceof Error ? error.message : String(error);
    credentialBindings.value = [];
  } finally {
    credentialBindingsLoading.value = false;
  }
}

async function selectProfile(profileId: string): Promise<void> {
  if (!profileId || profileId === selectedProfileId.value) return;
  isCreatingProfile.value = false;
  selectedProfileId.value = profileId;
  detailError.value = null;
  testError.value = null;
  testResult.value = null;
  detailLoading.value = true;
  try {
    const profile = await getLlmProfile(profileId);
    replaceProfile(profile);
    syncFormFromProfile(profile);
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
    syncFormFromProfile();
  } finally {
    detailLoading.value = false;
  }
}

async function saveProfileForm(): Promise<void> {
  if (!canEditProfile.value) return;
  isSaving.value = true;
  editorError.value = null;
  actionError.value = null;
  actionMessage.value = null;
  try {
    const wasCreating = isCreatingProfile.value;
    const payload = buildProfileWritePayload();
    const updated = wasCreating
      ? await createLlmProfile(payload)
      : await updateLlmProfile(payload.id, payload);
    replaceProfile(updated);
    selectedProfileId.value = updated.id;
    isCreatingProfile.value = false;
    syncFormFromProfile(updated);
    actionMessage.value = wasCreating
      ? `Created ${updated.id} through /llms.`
      : `Saved ${updated.id} through /llms/${updated.id}.`;
  } catch (error) {
    editorError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isSaving.value = false;
  }
}

async function toggleSelectedProfile(enabled: boolean): Promise<void> {
  if (!selectedProfileId.value) return;
  isToggling.value = true;
  actionError.value = null;
  actionMessage.value = null;
  try {
    const updated = await setLlmProfileEnabled(selectedProfileId.value, enabled);
    replaceProfile(updated);
    syncFormFromProfile(updated);
    actionMessage.value = `${enabled ? "Enabled" : "Disabled"} ${updated.id}.`;
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
    syncFormFromProfile();
  } finally {
    isToggling.value = false;
  }
}

async function handleEnabledChange(event: Event): Promise<void> {
  const target = event.target instanceof HTMLInputElement ? event.target : null;
  if (!target) return;
  const enabled = target.checked;
  editEnabled.value = enabled;
  if (isCreatingProfile.value) return;
  if (!selectedProfileId.value || !selectedProfile.value) return;
  await toggleSelectedProfile(enabled);
}

async function runProfileProbe(): Promise<void> {
  if (!canRunProfileProbe.value) return;
  isTesting.value = true;
  testError.value = null;
  testResult.value = null;
  try {
    testResult.value = await testLlmProfile({
      profile: buildProfileWritePayload(),
      messages: [{ role: "user", content: testPrompt.value || "Ping" }],
      tool_schemas: [],
      overrides: {},
    });
  } catch (error) {
    testError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isTesting.value = false;
  }
}

function startCreateProfile(): void {
  isCreatingProfile.value = true;
  selectedProfileId.value = null;
  detailError.value = null;
  editorError.value = null;
  actionError.value = null;
  actionMessage.value = null;
  testError.value = null;
  testResult.value = null;
  seedNewProfileForm();
}

function cancelCreateProfile(): void {
  isCreatingProfile.value = false;
  selectedProfileId.value = profiles.value[0]?.id ?? null;
  syncFormFromProfile();
}

function replaceProfile(profile: LlmProfileApiPayload): void {
  const index = profiles.value.findIndex((item) => item.id === profile.id);
  if (index >= 0) {
    profiles.value.splice(index, 1, profile);
  } else {
    profiles.value.unshift(profile);
  }
}

function syncFormFromProfile(profile = selectedProfile.value): void {
  editProfileId.value = profile?.id ?? "";
  editProvider.value = profile?.provider ?? "";
  editApiFamily.value = profile?.api_family ?? "";
  editModelName.value = profile?.model_name ?? "";
  editContextWindowTokens.value = numberText(profile?.context_window_tokens);
  editModelFamily.value = profile?.model_family ?? "general";
  editCapabilities.value = profile?.capabilities.join(", ") ?? "";
  editBaseUrl.value = profile?.base_url ?? "";
  editCredentialBindingId.value = profile?.credential_binding_id ?? "";
  editTimeoutSeconds.value = numberText(profile?.timeout_seconds ?? 60);
  editMaxConcurrency.value = numberText(profile?.max_concurrency);
  editConcurrencyKey.value = profile?.concurrency_key ?? "";
  editTemperature.value = numberText(profile?.default_params.temperature);
  editTopP.value = numberText(profile?.default_params.top_p);
  editMaxOutputTokens.value = numberText(profile?.default_params.max_output_tokens);
  editReasoningEffort.value = profile?.default_params.reasoning_effort ?? "";
  editEnabled.value = profile?.enabled ?? true;
  editorError.value = null;
}

function seedNewProfileForm(): void {
  editProfileId.value = "";
  editProvider.value = "openai";
  editApiFamily.value = "openai_responses";
  editModelName.value = "";
  editContextWindowTokens.value = "";
  editModelFamily.value = "general";
  editCapabilities.value = "tool_calling, structured_output";
  editBaseUrl.value = "";
  editCredentialBindingId.value = firstCompatibleCredentialBindingId() ?? "";
  editTimeoutSeconds.value = "90";
  editMaxConcurrency.value = "";
  editConcurrencyKey.value = "";
  editTemperature.value = "";
  editTopP.value = "";
  editMaxOutputTokens.value = "";
  editReasoningEffort.value = "";
  editEnabled.value = true;
}

function buildProfileWritePayload(): LlmProfileWritePayload {
  if (credentialBindingSelectionError.value) {
    throw new Error(credentialBindingSelectionError.value);
  }
  const selected = selectedProfile.value;
  if (!isCreatingProfile.value && (!selectedProfileId.value || !selected)) {
    throw new Error("Select an LLM profile before saving.");
  }
  const profileId = isCreatingProfile.value
    ? requiredText(editProfileId.value, "profile id")
    : requiredText(selectedProfileId.value ?? "", "profile id");
  return {
    id: profileId,
    provider: requiredText(editProvider.value, "provider"),
    api_family: requiredText(editApiFamily.value, "api family"),
    model_name: requiredText(editModelName.value, "model name"),
    context_window_tokens: nullableNumberText(editContextWindowTokens.value, "context window"),
    model_family: requiredText(editModelFamily.value, "model family"),
    capabilities: commaList(editCapabilities.value),
    default_params: {
      temperature: nullableNumberText(editTemperature.value, "temperature"),
      top_p: nullableNumberText(editTopP.value, "top p"),
      max_output_tokens: nullableNumberText(editMaxOutputTokens.value, "max output tokens"),
      reasoning_effort: nullableText(editReasoningEffort.value),
      extra_body: selected?.default_params.extra_body ?? {},
    },
    base_url: nullableText(editBaseUrl.value),
    credential_binding_id: nullableText(editCredentialBindingId.value),
    timeout_seconds: requiredNumberText(editTimeoutSeconds.value, "timeout seconds"),
    max_concurrency: nullableNumberText(editMaxConcurrency.value, "max concurrency"),
    concurrency_key: nullableText(editConcurrencyKey.value),
    enabled: editEnabled.value,
  };
}

function numberText(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function requiredText(value: string, label: string): string {
  const trimmed = value.trim();
  if (!trimmed) throw new Error(`${label} is required.`);
  return trimmed;
}

function nullableText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function requiredNumberText(value: string, label: string): number {
  const parsed = nullableNumberText(value, label);
  if (parsed === null) throw new Error(`${label} is required.`);
  return parsed;
}

function nullableNumberText(value: string, label: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) throw new Error(`${label} must be a number.`);
  return parsed;
}

function commaList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function formatUsage(usage: Record<string, unknown> | null): string {
  if (!usage) return "-";
  const parts = [
    ["input", usage.input_tokens],
    ["output", usage.output_tokens],
    ["total", usage.total_tokens],
    ["reasoning", usage.reasoning_tokens],
  ]
    .filter(([, value]) => typeof value === "number")
    .map(([label, value]) => `${label}: ${value}`);
  return parts.length ? parts.join(" · ") : "-";
}

function credentialBindingRank(binding: AccessCredentialBindingPayload): number {
  const status = (binding.status ?? "active").toLowerCase();
  if (["active", "ready", "enabled"].includes(status)) return 0;
  if (["degraded", "warning", "pending"].includes(status)) return 1;
  if (["disabled", "revoked", "blocked", "failed"].includes(status)) return 2;
  return 3;
}

function credentialExpectationFor(provider: string, apiFamily: string): CredentialExpectation {
  const normalizedProvider = provider.trim();
  const normalizedFamily = apiFamily.trim();
  if (normalizedProvider === "openai_codex" || normalizedFamily === "openai_codex_responses") {
    return { kind: "oauth2_account", label: "OAuth account", requiresCredential: true };
  }
  if (
    normalizedProvider === "openai"
    || normalizedProvider === "anthropic"
    || normalizedProvider === "google"
    || normalizedFamily === "openai_responses"
    || normalizedFamily === "anthropic_messages"
    || normalizedFamily === "gemini_generate_content"
  ) {
    return { kind: "api_key", label: "API key", requiresCredential: true };
  }
  if (normalizedProvider === "openai_compatible" || normalizedFamily === "openai_chat_compatible") {
    return { kind: "optional_api_key", label: "API key or none", requiresCredential: false };
  }
  if (normalizedProvider === "ollama" || normalizedFamily === "ollama_native") {
    return { kind: "none", label: "No credential", requiresCredential: false };
  }
  return { kind: "any", label: "Access credential", requiresCredential: false };
}

function credentialBindingCompatibility(
  binding: AccessCredentialBindingPayload,
  expectation: CredentialExpectation,
): { compatible: boolean; reason: string } {
  if (expectation.kind === "any") return { compatible: true, reason: "" };
  if (expectation.kind === "none") {
    return {
      compatible: false,
      reason: `${binding.binding_id} is not expected for ${expectation.label} profiles.`,
    };
  }
  if (expectation.kind === "oauth2_account") {
    const compatible = isOAuthAccountBinding(binding);
    return {
      compatible,
      reason: compatible ? "" : `${binding.binding_id} is ${credentialBindingTypeLabel(binding)}, not an OAuth account.`,
    };
  }
  if (expectation.kind === "api_key" || expectation.kind === "optional_api_key") {
    const compatible = isApiKeyBinding(binding);
    return {
      compatible,
      reason: compatible ? "" : `${binding.binding_id} is ${credentialBindingTypeLabel(binding)}, not an API key binding.`,
    };
  }
  return { compatible: true, reason: "" };
}

function isApiKeyBinding(binding: AccessCredentialBindingPayload): boolean {
  if (isOAuthAccountBinding(binding)) return false;
  const kind = normalizedCredentialText(binding.binding_kind);
  return kind === "api_key";
}

function isOAuthAccountBinding(binding: AccessCredentialBindingPayload): boolean {
  return normalizedCredentialText(binding.source_kind) === "oauth_account"
    || normalizedCredentialText(binding.binding_kind) === "oauth2_account"
    || normalizedCredentialText(binding.binding_kind) === "openid_connect";
}

function normalizedCredentialText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function firstCompatibleCredentialBindingId(): string | null {
  return credentialBindingOptions.value.find((binding) =>
    credentialBindingCompatibility(binding, credentialExpectation.value).compatible,
  )?.binding_id ?? null;
}

function credentialBindingTypeLabel(binding: AccessCredentialBindingPayload): string {
  if (isOAuthAccountBinding(binding)) return "OAuth account";
  const source = normalizedCredentialText(binding.source_kind);
  const kind = normalizedCredentialText(binding.binding_kind);
  if (kind === "api_key") {
    if (source === "env") return "API key / env";
    if (source === "file") return "API key / file";
    return "API key";
  }
  return binding.binding_kind ?? binding.source_kind ?? "credential";
}

function formatCredentialBindingLabel(binding: AccessCredentialBindingPayload): string {
  const source = credentialBindingTypeLabel(binding);
  const status = binding.status ? ` · ${binding.status}` : "";
  const compatibility = credentialBindingCompatibility(binding, credentialExpectation.value);
  const suffix = compatibility.compatible ? "" : ` · not for ${credentialExpectation.value.label}`;
  return `${binding.binding_id} · ${source}${status}${suffix}`;
}

function formatCredentialBindingMeta(binding: AccessCredentialBindingPayload): string {
  const source = credentialBindingTypeLabel(binding);
  const preview = binding.masked_preview ?? "secret held by Access";
  return `${source} · ${preview}`;
}

</script>

<template>
  <main class="settings-module llm-settings">
    <header class="settings-page-header llm-header">
      <div>
        <h1>LLM Profiles</h1>
        <p>Profile truth and writes come directly from <code>/llms</code>.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary" :disabled="isSaving" @click="startCreateProfile">
          <Plus :size="14" /> New Model
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="isRefreshing" @click="loadAll">
          <RefreshCcw :size="14" /> {{ isRefreshing ? "Refreshing" : "Refresh" }}
        </UiButton>
      </div>
    </header>

    <section class="llm-summary-grid" aria-label="LLM profile summary">
      <article class="settings-panel llm-summary-card">
        <span><Layers :size="18" /></span>
        <div><small>Profiles</small><strong>{{ profiles.length }}</strong><p>{{ filteredProfiles.length }} visible</p></div>
      </article>
      <article class="settings-panel llm-summary-card">
        <span><CheckCircle2 :size="18" /></span>
        <div><small>Enabled</small><strong>{{ enabledCount }}</strong><p>{{ disabledCount }} disabled</p></div>
      </article>
      <article class="settings-panel llm-summary-card">
        <span><KeyRound :size="18" /></span>
        <div><small>Access Bindings</small><strong>{{ credentialBindingCount }}</strong><p>{{ usedCredentialBindingCount }} used by profiles</p></div>
      </article>
      <article class="settings-panel llm-summary-card">
        <span><Zap :size="18" /></span>
        <div><small>Rate Limits</small><strong>{{ limitedProfilesCount }}</strong><p>{{ unlimitedProfilesCount }} unlimited profiles</p></div>
      </article>
    </section>

    <section class="llm-workspace">
      <article class="settings-panel llm-list-panel">
        <div class="settings-panel-heading">
          <h2>Profiles</h2>
          <span>{{ filteredProfiles.length }} / {{ profiles.length }}</span>
        </div>
        <label class="llm-search">
          <Search :size="14" />
          <input v-model="searchTerm" placeholder="Search profiles" />
        </label>
        <div v-if="isLoading" class="settings-state">Loading LLM profiles from /llms...</div>
        <div v-else-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
        <div v-else-if="!profiles.length" class="settings-state">No LLM profiles returned by /llms.</div>
        <div v-else class="llm-profile-list" role="listbox" aria-label="LLM profiles">
          <button
            v-for="profile in filteredProfiles"
            :key="profile.id"
            type="button"
            :class="['llm-profile-list-item', { 'is-active': !isCreatingProfile && profile.id === selectedProfileId }]"
            :aria-selected="!isCreatingProfile && profile.id === selectedProfileId"
            @click="selectProfile(profile.id)"
          >
            <span class="llm-list-primary">
              <strong>{{ profile.model_name }}</strong>
              <em :class="profile.enabled ? 'is-enabled' : 'is-disabled'">{{ profile.enabled ? "Enabled" : "Disabled" }}</em>
            </span>
            <span class="llm-list-id">{{ profile.id }}</span>
            <span class="llm-list-meta">
              <span>{{ profile.provider }}</span>
              <span>{{ profile.model_family }}</span>
            </span>
          </button>
        </div>
      </article>

      <article class="settings-panel llm-profile-panel">
        <div class="llm-profile-head">
          <div>
            <h2>{{ selectedTitle }}</h2>
            <p>{{ selectedSubtitle }}</p>
          </div>
        </div>

        <div v-if="detailLoading" class="settings-state">Loading selected profile...</div>
        <div v-else-if="detailError" class="settings-state settings-state--error">{{ detailError }}</div>
        <template v-else-if="canEditProfile">
          <section class="llm-editor-block">
            <div class="settings-panel-heading">
              <div>
                <h3>Profile Configuration</h3>
                <span>{{ isCreatingProfile ? "POST /llms" : `PUT /llms/${selectedProfile?.id}` }}</span>
              </div>
              <div class="llm-editor-actions">
                <label class="llm-switch-field">
                  <span>Enabled</span>
                  <input
                    type="checkbox"
                    :checked="editEnabled"
                    :disabled="isSaving || isToggling || !canEditProfile"
                    @change="handleEnabledChange"
                  />
                </label>
                <UiButton
                  v-if="isCreatingProfile"
                  size="sm"
                  variant="secondary"
                  :disabled="isSaving"
                  @click="cancelCreateProfile"
                >
                  Cancel
                </UiButton>
                <UiButton
                  size="sm"
                  variant="primary"
                  :disabled="!canSaveProfile || isSaving || isToggling"
                  @click="saveProfileForm"
                >
                  <Save :size="13" /> {{ isSaving ? "Saving" : isCreatingProfile ? "Create" : "Save" }}
                </UiButton>
              </div>
            </div>
            <div class="llm-field-grid">
              <label class="llm-field">
                <span>Profile ID</span>
                <input v-model="editProfileId" :disabled="!isCreatingProfile || isSaving" placeholder="openai.gpt-5.4-mini" />
              </label>
              <label class="llm-field">
                <span>Provider</span>
                <select v-model="editProvider" :disabled="isSaving">
                  <option v-for="provider in PROVIDER_OPTIONS" :key="provider" :value="provider">{{ provider }}</option>
                </select>
              </label>
              <label class="llm-field">
                <span>API Family</span>
                <select v-model="editApiFamily" :disabled="isSaving">
                  <option v-for="family in API_FAMILY_OPTIONS" :key="family" :value="family">{{ family }}</option>
                </select>
              </label>
              <label class="llm-field">
                <span>Model Name</span>
                <input v-model="editModelName" :disabled="isSaving" />
              </label>
              <label class="llm-field">
                <span>Model Family</span>
                <select v-model="editModelFamily" :disabled="isSaving">
                  <option v-for="family in MODEL_FAMILY_OPTIONS" :key="family" :value="family">{{ family }}</option>
                </select>
              </label>
              <label class="llm-field">
                <span>Context Window</span>
                <input v-model="editContextWindowTokens" inputmode="numeric" :disabled="isSaving" />
              </label>
              <label class="llm-field">
                <span>Timeout Seconds</span>
                <input v-model="editTimeoutSeconds" inputmode="numeric" :disabled="isSaving" />
              </label>
              <label class="llm-field">
                <span>Max Concurrency</span>
                <input v-model="editMaxConcurrency" inputmode="numeric" placeholder="unlimited" :disabled="isSaving" />
              </label>
              <div class="llm-field llm-field--span-2 llm-field--credential">
                <span>Access Binding ID</span>
                <div class="llm-binding-control">
                  <select
                    v-model="editCredentialBindingId"
                    :disabled="isSaving || credentialBindingsLoading"
                    :aria-invalid="Boolean(credentialBindingSelectionError)"
                  >
                    <option value="" :disabled="credentialExpectation.requiresCredential">No credential binding</option>
                    <option
                      v-if="currentCredentialBindingMissing"
                      :value="editCredentialBindingId"
                      disabled
                    >
                      {{ editCredentialBindingId }} · missing in Access
                    </option>
                    <option
                      v-for="binding in credentialBindingOptions"
                      :key="binding.binding_id"
                      :value="binding.binding_id"
                      :disabled="!credentialBindingCompatibility(binding, credentialExpectation).compatible"
                    >
                      {{ formatCredentialBindingLabel(binding) }}
                    </option>
                  </select>
                  <button
                    type="button"
                    class="llm-binding-refresh"
                    :disabled="credentialBindingsLoading || isSaving"
                    aria-label="Refresh Access credential bindings"
                    @click="loadAccessCredentialBindings"
                  >
                    <RefreshCcw :size="13" />
                  </button>
                </div>
                <small :class="['llm-field-note', credentialBindingNoteTone]">{{ credentialBindingNote }}</small>
              </div>
              <label class="llm-field llm-field--span-2">
                <span>Base URL</span>
                <input v-model="editBaseUrl" placeholder="default adapter endpoint" :disabled="isSaving" />
              </label>
              <label class="llm-field llm-field--full">
                <span>Capabilities</span>
                <input v-model="editCapabilities" placeholder="tool_calling, structured_output, reasoning" :disabled="isSaving" />
              </label>
              <label class="llm-field">
                <span>Temperature</span>
                <input v-model="editTemperature" inputmode="decimal" placeholder="provider default" :disabled="isSaving" />
              </label>
              <label class="llm-field">
                <span>Top P</span>
                <input v-model="editTopP" inputmode="decimal" placeholder="provider default" :disabled="isSaving" />
              </label>
              <label class="llm-field">
                <span>Max Output Tokens</span>
                <input v-model="editMaxOutputTokens" inputmode="numeric" placeholder="provider default" :disabled="isSaving" />
              </label>
              <label class="llm-field">
                <span>Reasoning Effort</span>
                <select v-model="editReasoningEffort" :disabled="isSaving">
                  <option v-for="effort in REASONING_EFFORT_OPTIONS" :key="effort || 'default'" :value="effort">
                    {{ effort || "provider default" }}
                  </option>
                </select>
              </label>
              <label class="llm-field llm-field--full">
                <span>Concurrency Key</span>
                <input v-model="editConcurrencyKey" placeholder="shared limiter key" :disabled="isSaving" />
              </label>
            </div>
            <p v-if="editorError" class="llm-inline-error">{{ editorError }}</p>
            <p v-if="actionMessage" class="llm-inline-success">{{ actionMessage }}</p>
            <p v-if="actionError" class="llm-inline-error">{{ actionError }}</p>
          </section>
        </template>
        <div v-else class="settings-state">Select a profile to inspect and edit it.</div>
      </article>

      <aside class="llm-side-stack">
        <article class="settings-panel llm-probe-panel">
          <div class="settings-panel-heading">
            <h2>Direct LLM Test</h2>
            <span>{{ probeStatusLabel }}</span>
          </div>
          <div class="llm-probe-target">
            <strong>{{ editProfileId || selectedProfile?.id || "No profile id" }}</strong>
            <span>POST /llms/test</span>
          </div>
          <textarea v-model="testPrompt" spellcheck="false" />
          <UiButton
            size="sm"
            variant="primary"
            :disabled="!canRunProfileProbe || isTesting || isToggling || isSaving"
            @click="runProfileProbe"
          >
            <Play :size="13" /> {{ isTesting ? "Running" : "Run" }}
          </UiButton>
          <section class="llm-test-output">
            <p v-if="testError" class="llm-inline-error">{{ testError }}</p>
            <div v-else-if="testResult" class="llm-probe-result">
              <div>
                <span>Status</span>
                <strong>{{ testResult.status }}</strong>
              </div>
              <div>
                <span>Finish</span>
                <strong>{{ probeFinishLabel }}</strong>
              </div>
              <div class="llm-probe-result--wide">
                <span>Usage</span>
                <strong>{{ probeUsageLabel }}</strong>
              </div>
              <div class="llm-probe-result--wide">
                <span>Request</span>
                <strong>{{ probeRequestLabel }}</strong>
              </div>
              <p v-if="probeResultText">{{ probeResultText }}</p>
            </div>
            <div v-else class="llm-probe-empty">
              <Play :size="18" />
              <strong>{{ canRunProfileProbe ? "Run a prompt against the current form." : "Complete provider, model, and credential fields before testing." }}</strong>
              <span>Results stay in this panel; profile changes are saved only when you click Save.</span>
            </div>
          </section>
        </article>
      </aside>
    </section>

    <footer class="settings-footer llm-footer">
      <span><Brain :size="14" />Truth source: LLM module API</span>
      <span><Zap :size="14" />Runtime probe: /llms/{{ selectedProfileId ?? ":id" }}/invoke</span>
      <span><KeyRound :size="14" />Credential readiness is owned by Access.</span>
    </footer>
  </main>
</template>

<style scoped>
.llm-settings {
  display: grid;
  grid-template-rows: auto 74px minmax(0, 1fr) auto;
  gap: 10px;
  box-sizing: border-box;
  height: calc(100vh - 50px);
  min-height: 0;
  padding: 12px 16px;
  overflow: hidden;
}

.llm-header {
  margin: 0;
}

.llm-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  min-height: 0;
}

.llm-summary-card {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px;
}

.llm-summary-card > span {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
  color: var(--color-accent);
}

.llm-summary-card div,
.llm-profile-head div {
  min-width: 0;
}

.llm-summary-card small,
.llm-summary-card p,
.llm-profile-head p,
.llm-muted {
  color: var(--text-muted);
  font-size: 11px;
}

.llm-summary-card p,
.llm-profile-head p {
  overflow: hidden;
  margin: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-summary-card strong {
  display: block;
  overflow: hidden;
  margin: 2px 0;
  color: var(--text-primary);
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-editor-block p,
.llm-probe-panel p {
  margin: 0;
}

.llm-workspace {
  display: grid;
  grid-template-columns: minmax(300px, 0.68fr) minmax(620px, 1.34fr) minmax(320px, 0.72fr);
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

.llm-list-panel,
.llm-profile-panel,
.llm-side-stack {
  min-width: 0;
  min-height: 0;
}

.llm-list-panel,
.llm-profile-panel,
.llm-probe-panel {
  overflow: hidden;
}

.llm-list-panel {
  display: grid;
  grid-template-rows: auto 34px minmax(0, 1fr);
  gap: 8px;
}

.llm-search {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.llm-search input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
}

.llm-profile-list {
  display: grid;
  align-content: start;
  gap: 6px;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.llm-profile-list-item {
  display: grid;
  gap: 4px;
  width: 100%;
  min-width: 0;
  padding: 8px 9px;
  border: 1px solid transparent;
  border-radius: var(--radius-2);
  outline: 0;
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
}

.llm-profile-list-item:hover,
.llm-profile-list-item.is-active {
  border-color: color-mix(in srgb, var(--color-accent) 48%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.llm-list-primary,
.llm-list-meta {
  display: flex;
  align-items: center;
  min-width: 0;
}

.llm-list-primary {
  justify-content: space-between;
  gap: 8px;
}

.llm-list-primary strong,
.llm-list-id,
.llm-list-meta span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-list-primary strong {
  min-width: 0;
  color: var(--text-primary);
  font-size: 12px;
}

.llm-list-primary em {
  flex: 0 0 auto;
  font-size: 10px;
  font-style: normal;
  font-weight: 780;
}

.llm-list-primary em.is-enabled {
  color: var(--color-success);
}

.llm-list-primary em.is-disabled {
  color: var(--color-danger);
}

.llm-list-id {
  color: var(--text-muted);
  font-size: 11px;
}

.llm-list-meta {
  gap: 6px;
  color: var(--text-muted);
  font-size: 10.5px;
}

.llm-list-meta span {
  min-width: 0;
  padding-right: 6px;
  border-right: 1px solid var(--border-subtle);
}

.llm-list-meta span:last-child {
  border-right: 0;
}

.llm-profile-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
}

.llm-profile-head,
.llm-footer {
  display: flex;
  align-items: center;
}

.llm-profile-head {
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.llm-profile-head h2 {
  overflow: hidden;
  margin: 0 0 2px;
  color: var(--text-primary);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-editor-block {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 0;
  overflow: hidden;
}

.llm-editor-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.llm-field-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  align-content: start;
  align-items: start;
  gap: 8px;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}

.llm-field {
  display: grid;
  grid-template-rows: auto 30px;
  align-self: start;
  gap: 4px;
  min-width: 0;
}

.llm-field--credential {
  grid-template-rows: auto 30px auto;
}

.llm-field--span-2 {
  grid-column: span 2;
}

.llm-field--full {
  grid-column: 1 / -1;
}

.llm-field span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-field input,
.llm-field select {
  width: 100%;
  min-width: 0;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  outline: 0;
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.llm-field input:disabled,
.llm-field select:disabled {
  cursor: not-allowed;
  opacity: 0.68;
}

.llm-binding-control {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 30px;
  gap: 6px;
  min-width: 0;
}

.llm-binding-refresh {
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

.llm-binding-refresh:hover {
  border-color: color-mix(in srgb, var(--color-accent) 46%, var(--border-subtle));
  color: var(--color-accent);
}

.llm-binding-refresh:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.llm-field-note {
  overflow: hidden;
  min-width: 0;
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-field-note.is-error {
  color: var(--color-danger);
}

.llm-field-note.is-success {
  color: var(--color-success);
}

.llm-switch-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.llm-switch-field input {
  position: relative;
  appearance: none;
  width: 34px;
  height: 18px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--surface-input);
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.llm-switch-field input::after {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: var(--text-muted);
  content: "";
  transition: transform 0.16s ease, background 0.16s ease;
}

.llm-switch-field input:checked {
  border-color: color-mix(in srgb, var(--color-success) 70%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 28%, var(--surface-input));
}

.llm-switch-field input:checked::after {
  transform: translateX(16px);
  background: var(--color-success);
}

.llm-switch-field input:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.llm-side-stack {
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  gap: 10px;
}

.llm-side-stack .settings-panel {
  padding: 10px 12px;
}

.llm-probe-panel {
  display: grid;
  grid-template-rows: auto auto minmax(150px, 0.36fr) auto minmax(0, 1fr);
  align-content: stretch;
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.llm-probe-target {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 2px;
  min-width: 0;
  padding: 7px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-raised) 74%, transparent);
}

.llm-probe-target strong,
.llm-probe-target span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-probe-target strong {
  color: var(--text-primary);
  font-size: 12px;
}

.llm-probe-target span {
  color: var(--text-muted);
  font-size: 11px;
}

.llm-probe-panel textarea {
  width: 100%;
  min-height: 0;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  outline: 0;
  resize: none;
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.4;
}

.llm-test-output {
  min-height: 0;
  overflow: hidden;
}

.llm-probe-result {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  min-height: 0;
  overflow: auto;
}

.llm-probe-result div,
.llm-probe-result p {
  min-width: 0;
  margin: 0;
  padding: 7px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.llm-probe-result--wide,
.llm-probe-result p {
  grid-column: 1 / -1;
}

.llm-probe-result span {
  display: block;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
}

.llm-probe-result strong,
.llm-probe-result p {
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.llm-probe-empty {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  min-height: 0;
  height: 100%;
  padding: 14px;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-2);
  color: var(--text-muted);
  text-align: center;
}

.llm-probe-empty strong {
  color: var(--text-secondary);
  font-size: 12px;
}

.llm-probe-empty span {
  max-width: 260px;
  font-size: 11px;
  line-height: 1.35;
}

.llm-inline-success {
  color: var(--color-success);
}

.llm-inline-error {
  color: var(--color-danger);
}

.llm-footer {
  flex-wrap: wrap;
  gap: 16px;
  min-height: 28px;
  color: var(--text-muted);
  font-size: 11px;
}

.llm-footer span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

@media (max-width: 1280px) {
  .llm-settings {
    height: auto;
    min-height: calc(100vh - 50px);
    overflow: visible;
  }

  .llm-workspace {
    grid-template-columns: minmax(0, 1fr);
  }

  .llm-list-panel,
  .llm-profile-panel,
  .llm-side-stack {
    min-height: 420px;
  }
}

@media (max-width: 760px) {
  .llm-settings {
    padding: 10px;
  }

  .llm-summary-grid,
  .llm-field-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
