<script setup lang="ts">
import { GitBranch, Info, KeyRound, Pencil, PlayCircle, Power, PowerOff, RefreshCcw, Save, Shield, ShieldOff, X } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  executeAccessAction,
  getAccessAssetDetail,
  getAccessOverview,
  getAccessSetup,
  type AccessActionResultPayload,
  type AccessAssetDetailPayload,
  type AccessAssetListPayload,
  type AccessAssetSummaryPayload,
  type AccessConsumersPayload,
  type AccessConsumerBindingPayload,
  type AccessCredentialBindingActionChanges,
  type AccessCredentialBindingActionIntent,
  type AccessCredentialBindingPayload,
  type AccessCredentialRequirementPayload,
  type AccessCredentialRequirementsPayload,
  type AccessOAuthAccountPayload,
  type AccessOwnerJsonRecord,
  type AccessOverviewPayload,
  type AccessReadinessPayload,
  type AccessSetupSessionPayload,
  type AccessSetupFlowPayload,
} from "../ownerApis/accessAssets";

type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";
type AccessAssetTableRow = Record<string, string | number | null> & {
  __row_id: string;
  __asset_id: string;
};

const { t } = useI18n();
const overview = ref<AccessOverviewPayload | null>(null);
const assetList = ref<AccessAssetListPayload | null>(null);
const consumersPayload = ref<AccessConsumersPayload | null>(null);
const requirementsPayload = ref<AccessCredentialRequirementsPayload | null>(null);
const selectedAssetDetail = ref<AccessAssetDetailPayload | null>(null);
const selectedAssetId = ref<string | null>(null);
const setupFlow = ref<AccessSetupFlowPayload | null>(null);
const actionResult = ref<AccessActionResultPayload | null>(null);
const isLoading = ref(false);
const setupLoading = ref(false);
const actionLoading = ref(false);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const setupError = ref<string | null>(null);
const actionError = ref<string | null>(null);
const oauthActionMessage = ref<string | null>(null);
const apiWarnings = ref<string[]>([]);
const detailOpen = ref(true);
const bindingModalOpen = ref(false);
const revokeModalOpen = ref(false);
type BindingSourceKind = "env" | "file" | "oauth_account" | "app_credential";
type BindingModalMode = "register" | "edit";

const bindingKindsBySource: Record<BindingSourceKind, string[]> = {
  env: ["api_key", "bearer_token", "basic", "app_secret", "webhook_secret", "certificate"],
  file: ["api_key", "bearer_token", "basic", "app_secret", "webhook_secret", "certificate"],
  oauth_account: ["oauth2_account", "openid_connect"],
  app_credential: ["app_secret", "webhook_secret", "certificate"],
};

const bindingModalMode = ref<BindingModalMode>("register");
const bindingModalBinding = ref<AccessCredentialBindingPayload | null>(null);
const bindingSourceKind = ref<BindingSourceKind>("env");
const bindingIdInput = ref("");
const bindingSourceRefInput = ref("");
const bindingAssetIdInput = ref("");
const bindingKindInput = ref("api_key");
const bindingRegisterLoading = ref(false);
const bindingRegisterMessage = ref<string | null>(null);
const bindingRegisterError = ref<string | null>(null);
const bindingActionMessage = ref<string | null>(null);
const revokeBinding = ref<AccessCredentialBindingPayload | null>(null);
const revokeConfirmationInput = ref("");
const assetKindFilter = ref("all");
const assetProviderFilter = ref("all");
const assetStatusFilter = ref("all");
const assetReadinessFilter = ref("all");
const consumerModuleFilter = ref("all");

const readinessByAssetId = computed(() => {
  const values = new Map<string, AccessReadinessPayload>();
  for (const readiness of overview.value?.readiness ?? []) {
    if (readiness.target_kind === "asset" && readiness.target_id) {
      values.set(readiness.target_id, readiness);
    }
  }
  for (const asset of overview.value?.assets?.assets ?? []) {
    if (asset.asset_id && asset.readiness) {
      values.set(asset.asset_id, asset.readiness);
    }
  }
  for (const asset of assetList.value?.assets ?? []) {
    if (asset.asset_id && asset.readiness) {
      values.set(asset.asset_id, asset.readiness);
    }
  }
  return values;
});

const credentialBindings = computed<AccessCredentialBindingPayload[]>(() =>
  overview.value?.credential_bindings ?? [],
);

const consumerBindings = computed<AccessConsumerBindingPayload[]>(() =>
  consumersPayload.value?.consumers ?? overview.value?.consumer_bindings ?? [],
);

const credentialRequirements = computed<AccessCredentialRequirementPayload[]>(() =>
  requirementsPayload.value?.credential_requirements
    ?? overview.value?.credential_requirements
    ?? [],
);

const missingAccessRequirements = computed(() => {
  const source = overview.value?.missing_requirements?.length
    ? overview.value.missing_requirements
    : credentialRequirements.value.filter((requirement) => !requirement.ready || requirement.missing);
  return source;
});

const assetSummaries = computed<AccessAssetSummaryPayload[]>(() => {
  const source = assetList.value?.assets?.length
    ? assetList.value.assets
    : overview.value?.assets?.assets ?? [];
  return source.map((asset) => ({
    ...asset,
    readiness: asset.readiness ?? readinessByAssetId.value.get(asset.asset_id) ?? null,
    credential_binding_count: asset.credential_binding_count
      ?? credentialBindings.value.filter((binding) => binding.asset_id === asset.asset_id).length,
    consumer_modules: uniqueStrings([
      ...(asset.consumer_modules ?? []),
      ...consumerBindings.value
        .filter((binding) => binding.asset_id === asset.asset_id)
        .map((binding) => binding.consumer_module),
    ]),
  }));
});

const filteredAssetSummaries = computed(() =>
  assetSummaries.value.filter((asset) => {
    if (assetKindFilter.value !== "all" && normalizedFilter(asset.asset_kind) !== assetKindFilter.value) return false;
    if (assetProviderFilter.value !== "all" && normalizedFilter(assetProviderText(asset)) !== assetProviderFilter.value) return false;
    if (assetStatusFilter.value !== "all" && normalizedFilter(asset.status) !== assetStatusFilter.value) return false;
    if (assetReadinessFilter.value !== "all") {
      const readiness = asset.readiness;
      const readinessValue = readiness?.ready ? "ready" : normalizedFilter(readiness?.status ?? asset.status);
      if (readinessValue !== assetReadinessFilter.value) return false;
    }
    if (consumerModuleFilter.value !== "all") {
      const modules = (asset.consumer_modules ?? []).map((item) => normalizedFilter(item));
      if (!modules.includes(consumerModuleFilter.value)) return false;
    }
    return true;
  }),
);

const assetKindOptions = computed(() =>
  uniqueStrings(assetSummaries.value.map((asset) => normalizedFilter(asset.asset_kind)).filter((item) => item !== "unknown")).sort(),
);

const assetProviderOptions = computed(() =>
  uniqueStrings(assetSummaries.value.map((asset) => normalizedFilter(assetProviderText(asset))).filter((item) => item !== "unknown")).sort(),
);

const assetStatusOptions = computed(() =>
  uniqueStrings(assetSummaries.value.map((asset) => normalizedFilter(asset.status)).filter((item) => item !== "unknown")).sort(),
);

const assetReadinessOptions = computed(() =>
  uniqueStrings(assetSummaries.value.map((asset) => {
    const readiness = asset.readiness;
    return readiness?.ready ? "ready" : normalizedFilter(readiness?.status ?? asset.status);
  }).filter((item) => item !== "unknown")).sort(),
);

const consumerModuleOptions = computed(() =>
  uniqueStrings(assetSummaries.value.flatMap((asset) => asset.consumer_modules ?? []).map((item) => normalizedFilter(item))).sort(),
);

const selectedAsset = computed(() => {
  if (!detailOpen.value) return null;
  const fallback = assetSummaries.value[0] ?? null;
  const base = assetSummaries.value.find((asset) => asset.asset_id === selectedAssetId.value) ?? fallback;
  if (!base) return null;
  if (selectedAssetDetail.value?.asset_id === base.asset_id) {
    return {
      ...base,
      ...selectedAssetDetail.value,
      readiness: selectedAssetDetail.value.readiness ?? base.readiness,
      consumer_modules: uniqueStrings([
        ...(base.consumer_modules ?? []),
        ...(selectedAssetDetail.value.consumer_modules ?? []),
      ]),
    };
  }
  return base;
});

const selectedReadiness = computed(() =>
  selectedAsset.value?.readiness
    ?? (selectedAsset.value ? readinessByAssetId.value.get(selectedAsset.value.asset_id) ?? null : null),
);

const selectedCredentialBindings = computed(() => {
  if (!selectedAsset.value) return [];
  if (selectedAssetDetail.value?.asset_id === selectedAsset.value.asset_id) {
    return selectedAssetDetail.value.credential_bindings ?? [];
  }
  return credentialBindings.value.filter((binding) => binding.asset_id === selectedAsset.value?.asset_id);
});

const selectedConsumerBindings = computed(() => {
  if (!selectedAsset.value) return [];
  if (selectedAssetDetail.value?.asset_id === selectedAsset.value.asset_id) {
    return selectedAssetDetail.value.consumer_bindings ?? [];
  }
  const modules = new Set(selectedAsset.value.consumer_modules ?? []);
  return consumerBindings.value.filter((binding) =>
    binding.asset_id === selectedAsset.value?.asset_id
    || (binding.consumer_module ? modules.has(binding.consumer_module) : false),
  );
});

const firstCredentialBinding = computed(() => selectedCredentialBindings.value[0] ?? null);

const selectedActionBinding = computed(() => firstCredentialBinding.value);

const selectedActionBindingStatus = computed(() =>
  textValue(selectedActionBinding.value?.status, "active").toLowerCase(),
);

const selectedActionBindingDisabled = computed(() =>
  selectedActionBindingStatus.value === "disabled",
);

const selectedActionBindingRevoked = computed(() =>
  selectedActionBindingStatus.value === "revoked",
);

const revokeTargetBindingId = computed(() => revokeBinding.value?.binding_id ?? "");

const revokeConfirmationMatches = computed(() =>
  Boolean(revokeTargetBindingId.value)
  && revokeConfirmationInput.value.trim() === revokeTargetBindingId.value,
);

const selectedOAuthBinding = computed(() =>
  selectedCredentialBindings.value.find((binding) => isOAuthBinding(binding)) ?? null,
);

const isOAuthAccessSelected = computed(() =>
  Boolean(selectedOAuthBinding.value)
  || normalizedFilter(selectedAsset.value?.governance_scope) === "oauth_account"
  || normalizedFilter(selectedAsset.value?.asset_kind).includes("oauth")
);

const selectedOAuthAccount = computed<AccessOAuthAccountPayload | null>(() => {
  if (!isOAuthAccessSelected.value) return null;
  const bindingId = selectedOAuthBinding.value?.binding_id;
  const providerId = selectedOAuthProviderRef.value;
  const accounts = overview.value?.oauth_accounts ?? [];
  return accounts.find((account) => bindingId && account.credential_binding_id === bindingId)
    ?? accounts.find((account) => providerId && account.provider_id === providerId)
    ?? null;
});

const selectedOAuthProviderRef = computed(() =>
  metadataText(selectedOAuthBinding.value?.metadata, "provider_id", "provider")
  ?? metadataText(selectedAsset.value?.metadata, "provider_id", "provider")
  ?? "",
);

const selectedOAuthProviderId = computed(() =>
  selectedOAuthProviderRef.value
  || selectedOAuthAccount.value?.provider_id
  || "",
);

const selectedOAuthProviderConfig = computed(() => {
  const providerId = normalizedFilter(selectedOAuthProviderId.value);
  if (!providerId) return null;
  return overview.value?.oauth_providers?.find((provider) =>
    normalizedFilter(provider.provider_id) === providerId,
  ) ?? null;
});

const selectedOAuthProviderLabel = computed(() =>
  providerLabel(selectedOAuthProviderId.value || selectedOAuthBinding.value?.binding_id || selectedAsset.value?.asset_id || "OAuth"),
);

const isCodexOAuthSelected = computed(() =>
  normalizedFilter(selectedOAuthProviderId.value) === "openai-codex"
  || normalizedFilter(selectedOAuthBinding.value?.binding_id) === "codex-oauth-default"
  || normalizedFilter(selectedAsset.value?.asset_id) === "codex-oauth-default",
);

const selectedOAuthActionMode = computed<"codex" | "generic" | "setup" | "unsupported">(() => {
  if (!isOAuthAccessSelected.value) return "unsupported";
  if (isCodexOAuthSelected.value) return "codex";
  const provider = selectedOAuthProviderConfig.value;
  const supportsBrowser = Boolean(provider?.authorization_url || provider?.callback_url);
  const supportsDevice = Boolean(provider?.device_code_url);
  if (supportsBrowser || supportsDevice) return "generic";
  return selectedReadiness.value?.setup_available ? "setup" : "unsupported";
});

const selectedOAuthSetupFlowKind = computed(() => {
  const provider = selectedOAuthProviderConfig.value;
  if (provider?.authorization_url || provider?.callback_url) return "browser_oauth";
  if (provider?.device_code_url) return "device_code";
  return "browser_oauth";
});

const selectedOAuthActionLabel = computed(() => {
  if (selectedOAuthActionMode.value === "codex") {
    return actionLoading.value ? t("settings.access.codex.startingLogin") : t("settings.access.codex.login");
  }
  if (selectedOAuthActionMode.value === "generic") return t("settings.access.oauth.startGeneric");
  if (selectedOAuthActionMode.value === "setup") return t("settings.access.oauth.inspectSetup");
  return t("settings.access.oauth.unsupported");
});

const selectedOAuthBindingId = computed(() =>
  selectedOAuthBinding.value?.binding_id
  ?? (isCodexOAuthSelected.value ? "codex-oauth-default" : selectedAsset.value?.asset_id ?? ""),
);

const selectedOAuthAccountId = computed(() =>
  selectedOAuthAccount.value?.account_id
  ?? (isCodexOAuthSelected.value ? "openai-codex:default" : "-"),
);

const selectedOAuthAccountExpired = computed(() => {
  const expiresAt = selectedOAuthAccount.value?.expires_at;
  if (!expiresAt) return false;
  const expiresAtMs = Date.parse(expiresAt);
  return Number.isFinite(expiresAtMs) && expiresAtMs <= Date.now();
});

const selectedOAuthReady = computed(() =>
  selectedOAuthAccount.value?.status === "active" && !selectedOAuthAccountExpired.value,
);

const selectedOAuthTone = computed<StatusTone>(() => {
  if (selectedOAuthReady.value) return "success";
  if (selectedOAuthAccountExpired.value) return "warning";
  return "neutral";
});

const selectedOAuthStatusLabel = computed(() => {
  if (selectedOAuthReady.value) return t("settings.access.oauth.connected");
  if (selectedOAuthAccountExpired.value) return t("settings.access.oauth.expired");
  return t("settings.access.oauth.notConnected");
});

const selectedOAuthHint = computed(() => {
  const provider = selectedOAuthProviderLabel.value;
  if (isCodexOAuthSelected.value) {
    if (selectedOAuthReady.value) return t("settings.access.codex.readyHint");
    if (selectedOAuthAccountExpired.value) return t("settings.access.codex.expiredHint");
    return t("settings.access.codex.missingHint");
  }
  if (selectedOAuthReady.value) return t("settings.access.oauth.readyHint", { provider });
  if (selectedOAuthAccountExpired.value) return t("settings.access.oauth.expiredHint", { provider });
  return t("settings.access.oauth.missingHint", { provider });
});

const selectedOAuthCredentialSource = computed(() =>
  metadataText(selectedOAuthAccount.value?.metadata, "source", "setup_flow")
  ?? selectedOAuthBinding.value?.masked_preview
  ?? "-",
);

const selectedOAuthSetupSessions = computed<AccessSetupSessionPayload[]>(() => {
  if (!isOAuthAccessSelected.value) return [];
  const providerId = normalizedFilter(selectedOAuthProviderId.value);
  const bindingId = normalizedFilter(selectedOAuthBindingId.value);
  const accountId = normalizedFilter(selectedOAuthAccountId.value);
  const matches = (value: unknown, expected: string) =>
    expected !== "unknown" && expected !== "-" && normalizedFilter(value) === expected;
  return (overview.value?.setup_sessions ?? [])
    .filter((session) => {
      const metadata = session.metadata ?? {};
      return matches(session.target_id, providerId)
        || matches(metadataText(metadata, "provider_id"), providerId)
        || matches(metadataText(metadata, "credential_binding_id"), bindingId)
        || matches(metadataText(metadata, "account_id"), accountId);
    })
    .slice(0, 3);
});

const selectedOAuthLatestSetupSession = computed(() =>
  selectedOAuthSetupSessions.value[0] ?? null,
);

const selectedMissingRequirement = computed(() => {
  const selectedBindingIds = new Set(selectedCredentialBindings.value.map((binding) => binding.binding_id));
  if (!selectedAsset.value || selectedBindingIds.size === 0) return missingAccessRequirements.value[0] ?? null;
  return missingAccessRequirements.value.find((requirement) =>
    (requirement.binding_id ? selectedBindingIds.has(requirement.binding_id) : false)
    || metadataList(requirement.metadata, "asset_ids", "assets").includes(selectedAsset.value?.asset_id ?? ""),
  ) ?? missingAccessRequirements.value[0] ?? null;
});

const selectedSetupTarget = computed(() =>
  firstMissingRequirement(selectedMissingRequirement.value)
    ?? safeCredentialSourceRef(firstCredentialBinding.value)
    ?? firstReadinessRequirement(selectedReadiness.value)
    ?? selectedAsset.value?.asset_id
    ?? "",
);

const selectedSetupResourceKind = computed(() =>
  selectedMissingRequirement.value ? "access_requirement" : "credential_binding",
);

const credentialPreview = computed(() => (
  firstCredentialBinding.value?.masked_preview
  ?? safeCredentialSourceRef(firstCredentialBinding.value)
  ?? (firstCredentialBinding.value ? t("settings.access.secret.serverSideOnly") : "-")
));

const secretStorageLabel = computed(() => (
  selectedAsset.value && "storage_key" in selectedAsset.value && selectedAsset.value.storage_key
    ? t("settings.access.secret.serverSideManaged")
    : t("settings.access.secret.bindingMetadataOnly")
));

const assets = computed<AccessAssetTableRow[]>(() =>
  filteredAssetSummaries.value.map((asset) => ({
    __row_id: asset.asset_id,
    __asset_id: asset.asset_id,
    name: textValue(asset.display_name, asset.asset_id),
    asset_id: asset.asset_id,
    kind: titleize(asset.asset_kind),
    governance_scope: textValue(asset.governance_scope, "-"),
    status: statusLabel(asset.status),
    readiness: readinessStatusLabel(asset.readiness),
    required_by: (asset.consumer_modules ?? []).join(" / ") || "-",
    credentials: String(asset.credential_binding_count ?? 0),
  })),
);

const assetColumns = computed(() => [
  { key: "name", label: t("table.name") },
  { key: "asset_id", label: t("settings.access.table.assetId") },
  { key: "kind", label: t("table.kind") },
  { key: "governance_scope", label: t("settings.access.table.governanceScope") },
  { key: "status", label: t("table.status") },
  { key: "readiness", label: t("table.readiness") },
  { key: "required_by", label: t("table.requiredBy") },
  { key: "credentials", label: t("settings.access.table.credentials") },
]);

const requirementBindingRows = computed(() =>
  credentialRequirements.value.map((requirement) => ({
    [t("table.consumer")]: textValue(requirement.display_name, requirement.consumer_id ?? "-"),
    [t("table.module")]: textValue(requirement.consumer_module, "-"),
    [t("table.slot")]: textValue(requirement.slot, "-"),
    [t("table.expectedKind")]: titleize(requirement.expected_kind),
    [t("table.binding")]: requirement.binding_id ?? t("settings.access.requirement.missingBinding"),
    [t("table.readiness")]: requirement.ready ? t("text.ready") : statusLabel(requirement.status, requirement.missing ? t("settings.access.requirement.missingBinding") : t("status.unknown")),
    [t("table.setup")]: requirement.ready ? t("text.ready") : setupHintLabel(requirement),
    [t("table.updatedAt")]: formatTime(requirement.last_checked_at),
  })),
);

const selectedConsumerSummary = computed(() => {
  const consumers = selectedConsumerBindings.value.map((consumer) =>
    textValue(consumer.display_name, consumer.consumer_module ?? consumer.consumer_id ?? ""),
  );
  return uniqueStrings(consumers).join(" / ") || t("settings.access.empty.noConsumers");
});

const selectedConsumerUsageSummary = computed(() =>
  uniqueStrings(selectedConsumerBindings.value.map((consumer) => titleize(consumer.consumer_kind, ""))).join(" / ") || "-",
);

const selectedConsumerStatusSummary = computed(() =>
  uniqueStrings(selectedConsumerBindings.value.map((consumer) =>
    consumer.enabled === false ? t("text.disabled") : statusLabel(consumer.status, t("text.enabled")),
  )).join(" / ") || "-",
);

const selectedConsumerRequirementSummary = computed(() => {
  const summaries = selectedConsumerBindings.value
    .map((consumer) => requirementSetSummary(consumer.requirement_sets))
    .filter((summary) => summary !== "-");
  return uniqueStrings(summaries).join(" / ") || "-";
});

const readinessTone = computed<StatusTone>(() => {
  if (selectedReadiness.value?.ready) return "success";
  if (selectedReadiness.value?.status === "setup_needed") return "warning";
  if (selectedReadiness.value?.status === "unsupported") return "danger";
  if (apiWarnings.value.length || detailError.value) return "warning";
  return selectedAsset.value?.status === "active" ? "info" : "neutral";
});

const readinessLabel = computed(() => readinessStatusLabel(selectedReadiness.value));
const setupFlowSummary = computed(() => {
  if (!setupFlow.value) return "-";
  return [
    setupFlow.value.title,
    setupFlow.value.command?.join(" "),
    setupFlow.value.path,
    setupFlow.value.env_vars?.join(", "),
  ].filter(Boolean).join(" / ");
});
const actionResultLabel = computed(() =>
  actionResult.value
    ? `${statusLabel(actionResult.value.status)}${actionResult.value.audit_ref ? ` (${actionResult.value.audit_ref})` : ""}`
    : "-",
);
const codexActionResultLabel = computed(() => {
  const asset = actionResult.value?.asset;
  if (asset?.resource_kind === "oauth_setup_session") {
    return t("settings.access.codex.loginStarted");
  }
  return actionResultLabel.value;
});
const bindingModalTitle = computed(() =>
  bindingModalMode.value === "edit"
    ? t("settings.access.binding.editTitle")
    : t("settings.access.binding.registerTitle"),
);
const bindingModalSubmitLabel = computed(() =>
  bindingModalMode.value === "edit"
    ? t("settings.access.binding.action.save")
    : t("settings.access.binding.action.register"),
);
const bindingModalSubmittingLabel = computed(() =>
  bindingModalMode.value === "edit"
    ? t("settings.access.binding.action.saving")
    : t("settings.access.binding.action.registering"),
);
const bindingSourceRequired = computed(() => {
  if (bindingModalMode.value === "register") return true;
  if (!bindingModalBinding.value) return false;
  return bindingSourceKind.value !== bindingSourceKindFrom(bindingModalBinding.value.source_kind);
});
const bindingSourceLabel = computed(() => {
  if (bindingSourceKind.value === "app_credential") return t("settings.access.binding.source.appCredentialLabel");
  if (bindingSourceKind.value === "file") return t("settings.access.binding.source.fileLabel");
  if (bindingSourceKind.value === "oauth_account") return t("settings.access.binding.source.oauthLabel");
  return t("settings.access.binding.source.envLabel");
});
const bindingSourcePlaceholder = computed(() => {
  if (bindingSourceKind.value === "app_credential") return t("settings.access.binding.source.appCredentialPlaceholder");
  if (bindingSourceKind.value === "file") return t("settings.access.binding.source.filePlaceholder");
  if (bindingSourceKind.value === "oauth_account") return t("settings.access.binding.source.oauthPlaceholder");
  return t("settings.access.binding.source.envPlaceholder");
});
const bindingIntent = computed<AccessCredentialBindingActionIntent>(() => {
  if (bindingSourceKind.value === "app_credential") return "register_app_credential_binding";
  if (bindingSourceKind.value === "file") return "register_file_binding";
  if (bindingSourceKind.value === "oauth_account") return "register_oauth_account_binding";
  return "register_env_binding";
});
const bindingKindOptions = computed(() => bindingKindsBySource[bindingSourceKind.value]);
const bindingAssetCandidate = computed(() => {
  const assetId = bindingAssetIdInput.value.trim();
  if (!assetId) return null;
  return assetSummaries.value.find((asset) => asset.asset_id === assetId) ?? null;
});
const bindingCompatibilityError = computed(() => {
  const bindingKind = normalizedFilter(bindingKindInput.value || defaultBindingKindForSource(bindingSourceKind.value));
  if (bindingKindOptions.value.includes(bindingKind)) return null;
  return t("settings.access.binding.error.incompatibleKind", {
    kind: bindingKind || "-",
    source: bindingSourceLabel.value,
  });
});
const bindingAssetCompatibilityError = computed(() => {
  const asset = bindingAssetCandidate.value;
  if (!asset) return null;
  const bindingKind = normalizedFilter(bindingKindInput.value || defaultBindingKindForSource(bindingSourceKind.value));
  const sourceKind = bindingSourceKind.value;
  const assetKind = normalizedFilter(asset.asset_kind);
  const governanceScope = normalizedFilter(asset.governance_scope);
  const assetLooksOAuth = governanceScope === "oauth_account" || assetKind.includes("oauth");
  const bindingLooksOAuth = sourceKind === "oauth_account" || bindingKind === "oauth2_account" || bindingKind === "openid_connect";
  if (assetLooksOAuth && !bindingLooksOAuth) {
    return t("settings.access.binding.error.assetKindMismatch", {
      asset: asset.asset_id,
      kind: titleize(bindingKind),
    });
  }
  if (!assetLooksOAuth && bindingLooksOAuth) {
    return t("settings.access.binding.error.assetKindMismatch", {
      asset: asset.asset_id,
      kind: titleize(bindingKind),
    });
  }
  return null;
});
const bindingSubmitError = computed(() => {
  return bindingCompatibilityError.value ?? bindingAssetCompatibilityError.value;
});
const generatedAt = computed(() =>
  overview.value?.generated_at
  ?? assetList.value?.generated_at
  ?? selectedAsset.value?.updated_at
  ?? selectedAsset.value?.created_at
  ?? null,
);

watch(bindingSourceKind, (sourceKind) => {
  if (!bindingKindsBySource[sourceKind].includes(normalizedFilter(bindingKindInput.value))) {
    bindingKindInput.value = defaultBindingKindForSource(sourceKind);
  }
});

onMounted(() => {
  void loadAccessAssets();
});

async function loadAccessAssets(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  detailError.value = null;
  setupError.value = null;
  actionError.value = null;
  oauthActionMessage.value = null;
  bindingActionMessage.value = null;
  apiWarnings.value = [];
  selectedAssetDetail.value = null;
  setupFlow.value = null;
  actionResult.value = null;
  try {
    const [overviewResult] = await Promise.allSettled([
      getAccessOverview(),
    ]);
    overview.value = settledValue(overviewResult, "GET /ui/access");
    assetList.value = overview.value?.assets ?? null;
    consumersPayload.value = {
      consumers: overview.value?.consumer_bindings ?? [],
    };
    requirementsPayload.value = {
      credential_requirements: overview.value?.credential_requirements ?? [],
      requirements_by_consumer: overview.value?.requirements_by_consumer ?? {},
      missing_requirements: overview.value?.missing_requirements ?? [],
      ready_requirements: overview.value?.ready_requirements ?? [],
      oauth_requirements: overview.value?.oauth_requirements ?? [],
    };
    const firstAssetId = assetSummaries.value[0]?.asset_id ?? null;
    if (!selectedAssetId.value || !assetSummaries.value.some((asset) => asset.asset_id === selectedAssetId.value)) {
      selectedAssetId.value = firstAssetId;
    }
    if (!overview.value && !assetList.value) {
      loadError.value = apiWarnings.value.join(" / ") || "Access owner API unavailable.";
    }
    await loadSelectedAssetDetail();
  } finally {
    isLoading.value = false;
  }
}

async function loadSelectedAssetDetail(): Promise<void> {
  const assetId = selectedAssetId.value;
  selectedAssetDetail.value = null;
  detailError.value = null;
  if (!assetId) return;
  try {
    selectedAssetDetail.value = await getAccessAssetDetail(assetId);
  } catch (error) {
    detailError.value = errorMessage(error);
  }
}

async function selectAsset(assetId: string): Promise<void> {
  selectedAssetId.value = assetId;
  detailOpen.value = true;
  setupFlow.value = null;
  actionResult.value = null;
  oauthActionMessage.value = null;
  bindingActionMessage.value = null;
  await loadSelectedAssetDetail();
}

async function selectAssetRow(row: unknown): Promise<void> {
  const value = (row as { __asset_id?: unknown }).__asset_id;
  if (typeof value !== "string" || !value.trim()) return;
  await selectAsset(value.trim());
}

function closeSelectedDetail(): void {
  detailOpen.value = false;
  bindingActionMessage.value = null;
}

async function prepareSetupFlow(): Promise<void> {
  const target = selectedSetupTarget.value.trim();
  if (!target) return;
  await prepareSetupFlowForTarget(target);
}

async function startCodexLogin(): Promise<void> {
  if (!isCodexOAuthSelected.value) return;
  const bindingId = selectedOAuthBindingId.value.trim() || "codex-oauth-default";
  const accountId = selectedOAuthAccountId.value.trim() || "openai-codex:default";
  actionLoading.value = true;
  setupError.value = null;
  actionError.value = null;
  oauthActionMessage.value = null;
  actionResult.value = null;
  try {
    const result = await executeAccessAction({
      action_id: `settings_access_start_codex_login_${Date.now()}`,
      resource_kind: "oauth_login",
      target_id: "openai-codex",
      intent: "begin_codex_oauth_login",
      reason: "Start built-in OpenAI Codex OAuth login from Settings Access Assets.",
      changes: {
        credential_binding_id: bindingId,
        account_id: accountId,
        open_browser: true,
      },
      actor: "settings-ui",
      trace_context: {
        page: "settings.access-assets",
        endpoint: "/access/actions",
        source: "builtin_oauth",
      },
    });
    actionResult.value = result;
    const asset = result.asset ?? {};
    const metadata = (typeof asset.metadata === "object" && asset.metadata !== null)
      ? asset.metadata as AccessOwnerJsonRecord
      : {};
    const authorizeUrl = textValue(asset.authorize_url, "");
    if (authorizeUrl && metadata.browser_opened !== true) {
      window.open(authorizeUrl, "_blank", "noopener,noreferrer");
    }
    oauthActionMessage.value = t("settings.access.codex.loginStarted");
    void pollCodexOAuthAccount(bindingId, accountId);
  } catch (error) {
    actionResult.value = null;
    actionError.value = errorMessage(error);
  } finally {
    actionLoading.value = false;
  }
}

async function pollCodexOAuthAccount(bindingId: string, accountId: string): Promise<void> {
  for (let attempt = 0; attempt < 45; attempt += 1) {
    await sleep(2000);
    await loadAccessAssets();
    const account = overview.value?.oauth_accounts?.find((item) =>
      item.account_id === accountId || item.credential_binding_id === bindingId,
    );
    if (account?.status === "active") {
      selectedAssetId.value = bindingId;
      await loadSelectedAssetDetail();
      oauthActionMessage.value = t("settings.access.codex.imported", {
        account: account.account_id,
      });
      return;
    }
  }
}

async function prepareSetupFlowForTarget(target: string): Promise<void> {
  setupLoading.value = true;
  setupError.value = null;
  actionError.value = null;
  try {
    setupFlow.value = await getAccessSetup(target);
  } catch (error) {
    setupFlow.value = null;
    setupError.value = errorMessage(error);
  } finally {
    setupLoading.value = false;
  }
}

async function beginSetupSession(): Promise<void> {
  const target = selectedSetupTarget.value.trim();
  if (!target) return;
  actionLoading.value = true;
  actionError.value = null;
  try {
    actionResult.value = await executeAccessAction({
      action_id: `settings_access_setup_${Date.now()}`,
      resource_kind: selectedSetupResourceKind.value,
      target_id: target,
      intent: "begin_setup_session",
      reason: "Prepare external access setup from Settings Access Assets.",
      changes: {
        flow_kind: setupFlow.value?.kind ?? "manual",
        expected_binding_kind: firstCredentialBinding.value?.binding_kind,
        secret_capture_policy: {
          mode: "binding_only",
          storage: "server_side",
        },
        validation_state: {
          status: selectedReadiness.value?.status ?? "pending",
        },
      },
      actor: "settings-ui",
      trace_context: {
        page: "settings.access-assets",
        endpoint: "/access/actions",
      },
    });
  } catch (error) {
    actionResult.value = null;
    actionError.value = errorMessage(error);
  } finally {
    actionLoading.value = false;
  }
}

async function startSelectedOAuthFlow(): Promise<void> {
  if (selectedOAuthActionMode.value === "codex") {
    await startCodexLogin();
    return;
  }
  if (selectedOAuthActionMode.value === "generic") {
    await beginProviderOAuthSetup();
    return;
  }
  if (selectedOAuthActionMode.value === "setup") {
    await prepareSetupFlow();
  }
}

async function beginProviderOAuthSetup(): Promise<void> {
  const providerId = selectedOAuthProviderId.value.trim();
  if (!providerId) return;
  actionLoading.value = true;
  setupError.value = null;
  actionError.value = null;
  oauthActionMessage.value = null;
  actionResult.value = null;
  try {
    const result = await executeAccessAction({
      action_id: `settings_access_start_oauth_${providerId}_${Date.now()}`,
      resource_kind: "oauth_provider",
      target_id: providerId,
      intent: "begin_oauth_setup_session",
      reason: `Start ${providerId} OAuth setup from Settings Access Assets.`,
      changes: {
        provider_id: providerId,
        flow_kind: selectedOAuthSetupFlowKind.value,
        credential_binding_id: selectedOAuthBindingId.value || null,
        account_id: selectedOAuthAccountId.value !== "-" ? selectedOAuthAccountId.value : null,
      },
      actor: "settings-ui",
      trace_context: {
        page: "settings.access-assets",
        endpoint: "/access/actions",
        source: "provider_oauth",
      },
    });
    actionResult.value = result;
    const asset = result.asset ?? {};
    const openUrl = textValue(asset.authorize_url, "") || textValue(asset.verification_url, "");
    if (openUrl) {
      window.open(openUrl, "_blank", "noopener,noreferrer");
    }
    oauthActionMessage.value = t("settings.access.oauth.setupStarted", {
      provider: selectedOAuthProviderLabel.value,
    });
    await loadAccessAssets();
  } catch (error) {
    actionResult.value = null;
    actionError.value = errorMessage(error);
  } finally {
    actionLoading.value = false;
  }
}

function openRegisterCredentialBindingModal(): void {
  bindingModalMode.value = "register";
  bindingModalBinding.value = null;
  bindingSourceKind.value = "env";
  bindingIdInput.value = "";
  bindingSourceRefInput.value = "";
  bindingAssetIdInput.value = selectedAsset.value?.asset_id ?? "";
  bindingKindInput.value = defaultBindingKindForSource(bindingSourceKind.value);
  bindingRegisterMessage.value = null;
  bindingRegisterError.value = null;
  bindingModalOpen.value = true;
}

function openEditCredentialBindingModal(binding = selectedActionBinding.value): void {
  if (!binding) return;
  const sourceKind = bindingSourceKindFrom(binding.source_kind);
  bindingModalMode.value = "edit";
  bindingModalBinding.value = binding;
  bindingSourceKind.value = sourceKind;
  bindingIdInput.value = binding.binding_id;
  bindingSourceRefInput.value = binding.source_ref ?? "";
  bindingAssetIdInput.value = binding.asset_id ?? selectedAsset.value?.asset_id ?? "";
  bindingKindInput.value = binding.binding_kind || defaultBindingKindForSource(sourceKind);
  bindingRegisterMessage.value = null;
  bindingRegisterError.value = null;
  bindingModalOpen.value = true;
}

function closeBindingModal(): void {
  bindingModalOpen.value = false;
  bindingModalMode.value = "register";
  bindingModalBinding.value = null;
  bindingSourceKind.value = "env";
  bindingIdInput.value = "";
  bindingSourceRefInput.value = "";
  bindingAssetIdInput.value = "";
  bindingKindInput.value = defaultBindingKindForSource("env");
  bindingRegisterMessage.value = null;
  bindingRegisterError.value = null;
}

async function submitCredentialBinding(): Promise<void> {
  const bindingId = bindingIdInput.value.trim();
  const sourceRef = bindingSourceRefInput.value.trim();
  const assetId = bindingAssetIdInput.value.trim();
  const bindingKind = bindingKindInput.value.trim() || defaultBindingKindForSource(bindingSourceKind.value);
  bindingRegisterMessage.value = null;
  bindingRegisterError.value = null;
  bindingActionMessage.value = null;
  actionError.value = null;
  if (!bindingId) {
    bindingRegisterError.value = t("settings.access.binding.error.bindingRequired");
    return;
  }
  if (bindingSourceRequired.value && !sourceRef) {
    bindingRegisterError.value = t("settings.access.binding.error.sourceRequired", {
      source: bindingSourceLabel.value,
    });
    return;
  }
  if (bindingSubmitError.value) {
    bindingRegisterError.value = bindingSubmitError.value;
    return;
  }
  const changes: AccessCredentialBindingActionChanges = {
    binding_id: bindingId,
    binding_kind: bindingKind,
    source_kind: bindingSourceKind.value,
  };
  const previousSourceRef = textValue(bindingModalBinding.value?.source_ref, "");
  if (sourceRef || previousSourceRef) changes.source_ref = sourceRef || null;
  if (bindingModalMode.value === "edit") {
    changes.asset_id = assetId || null;
  } else {
    changes.status = "active";
    if (assetId) changes.asset_id = assetId;
  }
  bindingRegisterLoading.value = true;
  try {
    const intent = bindingModalMode.value === "edit" ? "update_credential_binding" : bindingIntent.value;
    const result = await executeAccessAction({
      action_id: `settings_access_${bindingModalMode.value}_binding_${Date.now()}`,
      resource_kind: "credential_binding",
      target_id: bindingId,
      intent,
      changes,
      reason: bindingModalMode.value === "edit"
        ? `Update Access credential binding ${bindingId}.`
        : `Register Access credential binding ${bindingId}.`,
      actor: "settings-ui",
      trace_context: {
        page: "settings.access-assets",
        endpoint: "/access/actions",
        source_kind: bindingSourceKind.value,
      },
    });
    if (assetId) selectedAssetId.value = assetId;
    await loadAccessAssets();
    actionResult.value = result;
    bindingActionMessage.value = withAuditRef(
      bindingModalMode.value === "edit"
        ? t("settings.access.binding.updated", { binding: bindingId })
        : t("settings.access.binding.registered", { binding: bindingId }),
      result.audit_ref,
    );
    closeBindingModal();
  } catch (error) {
    bindingRegisterError.value = errorMessage(error);
  } finally {
    bindingRegisterLoading.value = false;
  }
}

async function toggleSelectedCredentialBindingStatus(): Promise<void> {
  const binding = selectedActionBinding.value;
  if (!binding || selectedActionBindingRevoked.value) return;
  const nextIntent: AccessCredentialBindingActionIntent = selectedActionBindingDisabled.value
    ? "enable_credential_binding"
    : "disable_credential_binding";
  const nextVerb = selectedActionBindingDisabled.value ? "Enable" : "Disable";
  await runCredentialBindingStatusAction(
    binding,
    nextIntent,
    `${nextVerb} Access credential binding ${binding.binding_id}.`,
    selectedActionBindingDisabled.value
      ? t("settings.access.binding.enabled", { binding: binding.binding_id })
      : t("settings.access.binding.disabled", { binding: binding.binding_id }),
  );
}

function openRevokeCredentialBindingModal(binding = selectedActionBinding.value): void {
  if (!binding || isRevokedBinding(binding)) return;
  revokeBinding.value = binding;
  revokeConfirmationInput.value = "";
  bindingActionMessage.value = null;
  actionError.value = null;
  revokeModalOpen.value = true;
}

function closeRevokeCredentialBindingModal(): void {
  if (actionLoading.value) return;
  revokeModalOpen.value = false;
  revokeBinding.value = null;
  revokeConfirmationInput.value = "";
}

async function revokeCredentialBinding(): Promise<void> {
  const binding = revokeBinding.value;
  const bindingId = revokeTargetBindingId.value;
  if (!binding || !bindingId) return;
  if (!revokeConfirmationMatches.value) {
    actionError.value = t("settings.access.binding.revokeMismatch");
    return;
  }
  const succeeded = await runCredentialBindingStatusAction(
    binding,
    "revoke_credential_binding",
    `Revoke Access credential binding ${bindingId}.`,
    t("settings.access.binding.revoked", { binding: bindingId }),
    {
      confirmation: revokeConfirmationInput.value.trim(),
      risk_acknowledged: true,
    },
  );
  if (succeeded) closeRevokeCredentialBindingModal();
}

async function runCredentialBindingStatusAction(
  binding: AccessCredentialBindingPayload,
  intent: AccessCredentialBindingActionIntent,
  reason: string,
  successMessage: string,
  risk?: { confirmation?: string; risk_acknowledged?: boolean },
): Promise<boolean> {
  const bindingId = binding.binding_id;
  actionLoading.value = true;
  actionError.value = null;
  bindingActionMessage.value = null;
  try {
    const result = await executeAccessAction({
      action_id: `settings_access_${intent}_${Date.now()}`,
      resource_kind: "credential_binding",
      target_id: bindingId,
      intent,
      changes: {
        binding_id: bindingId,
      },
      reason,
      confirmation: risk?.confirmation,
      risk_acknowledged: risk?.risk_acknowledged,
      actor: "settings-ui",
      trace_context: {
        page: "settings.access-assets",
        endpoint: "/access/actions",
        source_kind: binding.source_kind,
      },
    });
    if (binding.asset_id) selectedAssetId.value = binding.asset_id;
    await loadAccessAssets();
    actionResult.value = result;
    bindingActionMessage.value = withAuditRef(successMessage, result.audit_ref);
    return true;
  } catch (error) {
    actionResult.value = null;
    actionError.value = errorMessage(error);
    return false;
  } finally {
    actionLoading.value = false;
  }
}

function settledValue<T>(result: PromiseSettledResult<T>, label: string): T | null {
  if (result.status === "fulfilled") return result.value;
  apiWarnings.value.push(`${label}: ${errorMessage(result.reason)}`);
  return null;
}

function readinessStatusLabel(readiness: AccessReadinessPayload | null | undefined): string {
  if (readiness?.ready) return t("text.ready");
  if (readiness) return statusLabel(readiness.status);
  return t("status.unknown");
}

function setupSessionTone(session: AccessSetupSessionPayload): StatusTone {
  const status = normalizedFilter(session.status);
  if (status === "completed" || status === "succeeded") return "success";
  if (status === "waiting_for_user") return "warning";
  if (status === "failed" || status === "expired") return "danger";
  return "neutral";
}

function setupSessionStatusLabel(session: AccessSetupSessionPayload): string {
  return statusLabel(session.status, t("status.unknown"));
}

function statusLabel(value: unknown, fallback = "-"): string {
  const normalized = textValue(value, "");
  if (!normalized) return fallback;
  const known: Record<string, string> = {
    active: t("text.active"),
    blocked: t("text.blocked"),
    completed: t("text.completed"),
    configured: t("text.configured"),
    degraded: t("text.degraded"),
    disabled: t("text.disabled"),
    error: t("text.error"),
    expired: t("text.expired"),
    failed: t("status.failed"),
    ready: t("text.ready"),
    revoked: t("settings.access.binding.status.revoked"),
    setup_needed: t("text.setupNeeded"),
    succeeded: t("status.success"),
    unsupported: t("text.unsupported"),
    waiting_for_user: t("text.waitingUser"),
  };
  return known[normalized] ?? titleize(normalized, fallback);
}

function withAuditRef(message: string, auditRef: string | null | undefined): string {
  return auditRef ? `${message} (${auditRef})` : message;
}

function bindingSourceKindFrom(value: unknown): BindingSourceKind {
  const normalized = textValue(value, "").toLowerCase();
  if (normalized === "file") return "file";
  if (normalized === "oauth_account" || normalized === "oauth" || normalized === "oauth2_account") {
    return "oauth_account";
  }
  if (normalized === "app_credential" || normalized === "app" || normalized === "app_secret") {
    return "app_credential";
  }
  return "env";
}

function isRevokedBinding(binding: AccessCredentialBindingPayload): boolean {
  return textValue(binding.status, "").toLowerCase() === "revoked";
}

function firstMissingRequirement(requirement: AccessCredentialRequirementPayload | null | undefined): string | null {
  if (!requirement) return null;
  if (requirement.binding_id) return requirement.binding_id;
  return textValue(requirement.metadata?.requirement, "")
    || textValue(requirement.metadata?.raw, "")
    || textValue(requirement.requirement_id, "");
}

function firstReadinessRequirement(readiness: AccessReadinessPayload | null | undefined): string | null {
  for (const check of readiness?.checks ?? []) {
    const requirement = textValue(check.requirement, "");
    if (requirement) return requirement;
  }
  return null;
}

function safeCredentialSourceRef(binding: AccessCredentialBindingPayload | null | undefined): string | null {
  const bindingId = textValue(binding?.binding_id, "");
  if (bindingId) return bindingId;
  return null;
}

function isOAuthBinding(binding: AccessCredentialBindingPayload): boolean {
  const kind = textValue(binding.binding_kind, "").toLowerCase();
  const sourceKind = textValue(binding.source_kind, "").toLowerCase();
  return sourceKind === "oauth_account"
    || kind === "oauth2_account"
    || kind === "openid_connect";
}

function providerLabel(providerId: string): string {
  const normalized = providerId.trim().toLowerCase();
  const known: Record<string, string> = {
    "openai-codex": "Codex",
    github: "GitHub",
    "github-oauth": "GitHub",
    huggingface: "Hugging Face",
    "hugging-face": "Hugging Face",
    "huggingface-hub": "Hugging Face",
    anthropic: "Claude",
    claude: "Claude",
  };
  return known[normalized] ?? titleize(providerId, "OAuth");
}

function setupHintLabel(requirement: AccessCredentialRequirementPayload): string {
  if (setupProviderMissing(requirement.setup_flow_hint)) {
    return t("settings.access.requirement.setupProviderMissing");
  }
  const flowKind = textValue(requirement.setup_flow_hint?.flow_kind, "");
  if (flowKind) return titleize(flowKind);
  return requirement.missing ? t("settings.access.requirement.missingBinding") : t("settings.access.requirement.notReported");
}

function setupProviderMissing(value: AccessOwnerJsonRecord | null | undefined): boolean {
  const metadata = value?.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return false;
  return (metadata as AccessOwnerJsonRecord).setup_provider_missing === true;
}

function requirementSetSummary(value: string[][] | undefined): string {
  if (!value?.length) return "-";
  return value.map((items) => items.join(" + ")).join(" / ");
}

function metadataList(metadata: AccessOwnerJsonRecord | undefined, ...keys: string[]): string[] {
  const values: string[] = [];
  if (!metadata) return values;
  for (const key of keys) {
    const value = metadata[key];
    if (Array.isArray(value)) {
      values.push(...value.map((item) => textValue(item, "")).filter(Boolean));
    } else {
      const text = textValue(value, "");
      if (text) values.push(text);
    }
  }
  return uniqueStrings(values);
}

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  return Array.from(new Set(values.map((value) => textValue(value, "")).filter(Boolean)));
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
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

function metadataText(metadata: AccessOwnerJsonRecord | undefined, ...keys: string[]): string | null {
  if (!metadata) return null;
  for (const key of keys) {
    const value = textValue(metadata[key], "");
    if (value) return value;
  }
  return null;
}

function formatJsonSummary(value: AccessOwnerJsonRecord | undefined): string {
  if (!value || Object.keys(value).length === 0) return "-";
  return Object.entries(value)
    .slice(0, 3)
    .map(([key, item]) => `${key}: ${Array.isArray(item) ? item.length : textValue(item, "set")}`)
    .join(", ");
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", " UTC");
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function defaultBindingKindForSource(sourceKind: BindingSourceKind): string {
  if (sourceKind === "app_credential") return "app_secret";
  if (sourceKind === "file") return "api_key";
  if (sourceKind === "oauth_account") return "oauth2_account";
  return "api_key";
}

function normalizedFilter(value: unknown): string {
  const normalized = textValue(value, "unknown").trim().toLowerCase().replace(/\s+/g, "_");
  return normalized || "unknown";
}

function assetProviderText(asset: AccessAssetSummaryPayload): string {
  return metadataText(asset.metadata, "provider_id", "provider", "service") ?? "unknown";
}
</script>

<template>
  <main class="settings-module access-settings scroll-area">
    <header class="settings-page-header access-page-header">
      <div>
        <h1>{{ t("settings.resource.accessAssets") }}</h1>
        <p>{{ t("settings.access.pageDescription") }}</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="primary" @click="openRegisterCredentialBindingModal">
          <KeyRound :size="14" /> {{ t("settings.access.binding.registerTitle") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadAccessAssets">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section :class="['access-workbench', { 'access-workbench--no-detail': !selectedAsset }]">
      <div class="access-primary">
        <section class="settings-panel access-list">
          <div class="access-list-toolbar">
            <label>
              <span>{{ t("table.kind") }}</span>
              <select v-model="assetKindFilter">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="kind in assetKindOptions" :key="kind" :value="kind">{{ titleize(kind) }}</option>
              </select>
            </label>
            <label>
              <span>{{ t("settings.access.table.provider") }}</span>
              <select v-model="assetProviderFilter">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="provider in assetProviderOptions" :key="provider" :value="provider">{{ providerLabel(provider) }}</option>
              </select>
            </label>
            <label>
              <span>{{ t("table.status") }}</span>
              <select v-model="assetStatusFilter">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="status in assetStatusOptions" :key="status" :value="status">{{ statusLabel(status) }}</option>
              </select>
            </label>
            <label>
              <span>{{ t("table.readiness") }}</span>
              <select v-model="assetReadinessFilter">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="readiness in assetReadinessOptions" :key="readiness" :value="readiness">{{ statusLabel(readiness) }}</option>
              </select>
            </label>
            <label>
              <span>{{ t("table.module") }}</span>
              <select v-model="consumerModuleFilter">
                <option value="all">{{ t("common.all") }}</option>
                <option v-for="module in consumerModuleOptions" :key="module" :value="module">{{ titleize(module) }}</option>
              </select>
            </label>
          </div>
          <div v-if="loadError" class="access-empty">{{ loadError }}</div>
          <div v-else-if="isLoading" class="access-empty">{{ t("settings.access.loading") }}</div>
          <DataTable
            v-else
            :columns="assetColumns"
            :rows="assets"
            section-id="access-assets"
            :clickable-rows="true"
            :selected-row-id="selectedAssetId"
            @row-click="selectAssetRow"
          />
          <footer class="access-list-footer">
            <span>{{ t("settings.access.results", { count: assets.length }) }}</span>
            <span v-if="apiWarnings.length && !loadError" class="settings-tone-warning">{{ apiWarnings.join(" / ") }}</span>
            <span v-if="requirementBindingRows.length">{{ t("settings.access.bindingsByRequirement") }}: {{ requirementBindingRows.length }}</span>
          </footer>
        </section>
      </div>

      <aside v-if="selectedAsset" class="settings-panel access-detail-drawer">
        <header class="access-detail-header">
          <div>
            <h2>
              {{ selectedAsset.display_name ?? selectedAsset.asset_id }}
              <span>{{ readinessLabel }}</span>
            </h2>
            <p class="access-detail-kind"><KeyRound :size="14" />{{ t("settings.access.credentialBinding") }}</p>
            <p>{{ selectedReadiness?.reason ?? t("settings.access.recordSummary") }}</p>
          </div>
          <button type="button" class="access-icon-button" @click="closeSelectedDetail">
            <X :size="16" />
          </button>
        </header>

        <section class="access-detail-actions access-binding-actions">
          <div>
            <h3>{{ t("settings.access.binding.actionsTitle") }}</h3>
            <p>
              {{ selectedActionBinding?.binding_id ?? t("settings.access.binding.noneSelected") }}
              <span v-if="selectedActionBinding">· {{ statusLabel(selectedActionBinding.status, t("status.unknown")) }}</span>
            </p>
          </div>
          <div>
            <UiButton
              size="sm"
              variant="secondary"
              :disabled="!selectedActionBinding || actionLoading || bindingRegisterLoading || selectedActionBindingRevoked"
              @click="openEditCredentialBindingModal()"
            >
              <Pencil :size="14" />{{ t("settings.access.binding.action.edit") }}
            </UiButton>
            <UiButton
              size="sm"
              variant="secondary"
              :disabled="!selectedActionBinding || actionLoading || selectedActionBindingRevoked"
              @click="toggleSelectedCredentialBindingStatus"
            >
              <Power v-if="selectedActionBindingDisabled" :size="14" />
              <PowerOff v-else :size="14" />
              {{ selectedActionBindingDisabled ? t("settings.access.binding.action.enable") : t("settings.access.binding.action.disable") }}
            </UiButton>
            <UiButton
              size="sm"
              variant="danger"
              :disabled="!selectedActionBinding || actionLoading || selectedActionBindingRevoked"
              @click="openRevokeCredentialBindingModal()"
            >
              <ShieldOff :size="14" />{{ t("settings.access.binding.action.revoke") }}
            </UiButton>
          </div>
        </section>

        <section v-if="isOAuthAccessSelected" class="codex-login-card">
          <div class="codex-login-card__heading">
            <div>
              <h3>{{ isCodexOAuthSelected ? t("settings.access.codex.title") : t("settings.access.oauth.title", { provider: selectedOAuthProviderLabel }) }}</h3>
              <p>{{ selectedOAuthHint }}</p>
            </div>
            <span class="codex-login-card__status">
              <StatusDot :tone="selectedOAuthTone" />{{ selectedOAuthStatusLabel }}
            </span>
          </div>

          <dl class="codex-login-grid">
            <div><dt>{{ t("settings.access.oauth.provider") }}</dt><dd>{{ selectedOAuthProviderLabel }}</dd></div>
            <div><dt>{{ t("settings.access.oauth.account") }}</dt><dd>{{ selectedOAuthAccountId }}</dd></div>
            <div><dt>{{ t("settings.access.oauth.binding") }}</dt><dd>{{ selectedOAuthBindingId || "-" }}</dd></div>
            <div><dt>{{ t("settings.access.oauth.expiresAt") }}</dt><dd>{{ formatTime(selectedOAuthAccount?.expires_at) }}</dd></div>
            <div><dt>{{ t("settings.access.oauth.source") }}</dt><dd>{{ selectedOAuthCredentialSource }}</dd></div>
            <div>
              <dt>{{ t("settings.access.oauth.latestSetup") }}</dt>
              <dd>
                {{ selectedOAuthLatestSetupSession
                  ? `${setupSessionStatusLabel(selectedOAuthLatestSetupSession)} · ${titleize(selectedOAuthLatestSetupSession.flow_kind)}`
                  : "-" }}
              </dd>
            </div>
          </dl>

          <div v-if="selectedOAuthSetupSessions.length" class="oauth-session-strip">
            <span
              v-for="session in selectedOAuthSetupSessions"
              :key="session.session_id"
              class="oauth-session-strip__item"
            >
              <StatusDot :tone="setupSessionTone(session)" />
              {{ setupSessionStatusLabel(session) }}
              <small>{{ titleize(session.flow_kind) }} · {{ formatTime(session.expires_at) }}</small>
            </span>
          </div>

          <div class="codex-login-actions">
            <UiButton
              size="sm"
              :variant="selectedOAuthActionMode === 'codex' || selectedOAuthActionMode === 'generic' ? 'primary' : 'secondary'"
              :disabled="selectedOAuthActionMode === 'unsupported' || actionLoading || setupLoading"
              @click="startSelectedOAuthFlow"
            >
              <PlayCircle :size="14" />{{ selectedOAuthActionLabel }}
            </UiButton>
          </div>
        </section>

        <section v-else class="access-detail-actions">
          <h3>{{ t("operations.access.action.setupAccess") }}</h3>
          <div>
            <UiButton size="sm" variant="primary" :disabled="!selectedSetupTarget || actionLoading" @click="beginSetupSession">
              {{ t("settings.access.action.startSetup") }}
            </UiButton>
            <UiButton size="sm" variant="secondary" :disabled="!selectedSetupTarget || setupLoading" @click="prepareSetupFlow">
              {{ t("operations.access.action.setupAccess") }}
            </UiButton>
          </div>
        </section>

        <p v-if="setupError" class="settings-tone-danger access-detail-status">{{ setupError }}</p>
        <p v-else-if="actionError" class="settings-tone-danger access-detail-status">{{ actionError }}</p>
        <p v-else-if="bindingActionMessage" class="settings-tone-success access-detail-status">{{ bindingActionMessage }}</p>
        <p v-else-if="actionResult" class="settings-tone-success access-detail-status">{{ isCodexOAuthSelected ? codexActionResultLabel : actionResultLabel }}</p>
        <p v-else-if="oauthActionMessage && isOAuthAccessSelected" class="settings-tone-info access-detail-status">{{ oauthActionMessage }}</p>
        <p v-if="setupFlow || setupLoading" class="settings-tone-info access-setup-flow-status">
          {{ titleize(setupFlow?.kind, setupLoading ? t("common.loading") : t("operations.access.tab.setup")) }} · {{ setupFlowSummary }}
        </p>

        <section class="access-detail-section">
          <dl class="access-detail-kv">
            <div><dt>{{ t("settings.access.table.assetId") }}</dt><dd>{{ selectedAsset.asset_id }}</dd></div>
            <div><dt>{{ t("settings.access.table.providerService") }}</dt><dd>{{ metadataText(selectedAsset.metadata, "provider", "service") ?? "-" }}</dd></div>
            <div><dt>{{ t("table.type") }}</dt><dd>{{ titleize(selectedAsset.asset_kind) }}</dd></div>
            <div><dt>{{ t("settings.access.table.governanceScope") }}</dt><dd>{{ selectedAsset.governance_scope ?? "-" }}</dd></div>
            <div><dt>{{ t("settings.access.secret.storage") }}</dt><dd>{{ secretStorageLabel }}</dd></div>
            <div><dt>{{ t("table.createdAt") }}</dt><dd>{{ formatTime(selectedAsset.created_at) }}</dd></div>
            <div><dt>{{ t("table.updatedAt") }}</dt><dd>{{ formatTime(selectedAsset.updated_at) }}</dd></div>
          </dl>
        </section>

        <section class="access-detail-section">
          <h3>{{ t("settings.access.credentialBinding") }}</h3>
          <dl class="access-detail-kv">
            <div><dt>{{ t("settings.access.table.bindings") }}</dt><dd>{{ selectedCredentialBindings.length }}</dd></div>
            <div><dt>{{ t("table.source") }}</dt><dd>{{ firstCredentialBinding?.source_kind ?? "-" }}</dd></div>
            <div><dt>{{ t("settings.access.secret.preview") }}</dt><dd class="access-inline-code">{{ credentialPreview }}</dd></div>
            <div><dt>{{ t("settings.access.secret.policy") }}</dt><dd class="access-inline-code access-inline-code--wrap">{{ formatJsonSummary(selectedAssetDetail?.secret_policy) }}</dd></div>
          </dl>
        </section>

        <section class="access-detail-section">
          <h3>{{ t("settings.access.readiness") }}</h3>
          <dl class="access-detail-kv">
            <div><dt>{{ t("table.status") }}</dt><dd>{{ readinessLabel }}</dd></div>
            <div><dt>{{ t("settings.access.table.setupAvailable") }}</dt><dd>{{ selectedReadiness?.setup_available ? t("common.yes") : t("common.no") }}</dd></div>
            <div><dt>{{ t("settings.access.table.checks") }}</dt><dd>{{ selectedReadiness?.checks?.length ?? 0 }}</dd></div>
            <div><dt>{{ t("table.reason") }}</dt><dd>{{ detailError ?? selectedReadiness?.reason ?? "-" }}</dd></div>
          </dl>
        </section>

        <section class="access-detail-section">
          <h3>{{ t("settings.access.consumers") }}</h3>
          <dl class="access-detail-kv">
            <div><dt>{{ t("table.consumer") }}</dt><dd>{{ selectedConsumerSummary }}</dd></div>
            <div><dt>{{ t("table.usageType") }}</dt><dd>{{ selectedConsumerUsageSummary }}</dd></div>
            <div><dt>{{ t("table.status") }}</dt><dd>{{ selectedConsumerStatusSummary }}</dd></div>
            <div><dt>{{ t("table.requirements") }}</dt><dd>{{ selectedConsumerRequirementSummary }}</dd></div>
          </dl>
        </section>
      </aside>
    </section>

    <Teleport to="body">
      <div v-if="bindingModalOpen" class="access-modal-backdrop" @click.self="!bindingRegisterLoading && closeBindingModal()">
        <article class="settings-panel access-register-panel access-register-modal" role="dialog" aria-modal="true">
          <header class="access-panel-title">
            <div>
              <h2>{{ bindingModalTitle }}</h2>
              <span>/access/actions</span>
            </div>
            <button type="button" class="access-icon-button" :disabled="bindingRegisterLoading" @click="closeBindingModal">
              <X :size="16" />
            </button>
          </header>
          <div class="access-register-form">
            <label>
              <span>{{ t("settings.access.binding.field.bindingId") }} <em>*</em></span>
              <input
                v-model="bindingIdInput"
                :placeholder="t('settings.access.binding.placeholder.bindingId')"
                :disabled="bindingRegisterLoading || bindingModalMode === 'edit'"
              />
            </label>
            <label>
              <span>{{ t("settings.access.binding.field.sourceKind") }} <em>*</em></span>
              <select v-model="bindingSourceKind" :disabled="bindingRegisterLoading">
                <option value="env">{{ t("settings.access.binding.source.env") }}</option>
                <option value="file">{{ t("settings.access.binding.source.file") }}</option>
                <option value="oauth_account">{{ t("settings.access.binding.source.oauth") }}</option>
                <option value="app_credential">{{ t("settings.access.binding.source.appCredential") }}</option>
              </select>
            </label>
            <label>
              <span>{{ t("settings.access.binding.field.bindingKind") }} <em>*</em></span>
              <select v-model="bindingKindInput" :disabled="bindingRegisterLoading">
                <option v-for="kind in bindingKindOptions" :key="kind" :value="kind">
                  {{ titleize(kind) }}
                </option>
              </select>
            </label>
            <label>
              <span>{{ t("settings.access.binding.field.assetId") }}</span>
              <input
                v-model="bindingAssetIdInput"
                :placeholder="t('settings.access.binding.placeholder.assetId')"
                :disabled="bindingRegisterLoading"
              />
            </label>
            <label class="access-register-form__wide">
              <span>{{ bindingSourceLabel }} <em v-if="bindingSourceRequired">*</em></span>
              <input v-model="bindingSourceRefInput" :placeholder="bindingSourcePlaceholder" :disabled="bindingRegisterLoading" />
            </label>
            <div class="access-register-note">
              <Info :size="14" />
              <span>{{ bindingSubmitError ?? t("settings.access.binding.secretNotice") }}</span>
            </div>
            <div class="access-register-actions">
              <UiButton size="sm" variant="ghost" :disabled="bindingRegisterLoading" @click="closeBindingModal">
                {{ t("common.cancel") }}
              </UiButton>
              <UiButton size="sm" variant="primary" :disabled="bindingRegisterLoading || Boolean(bindingSubmitError)" @click="submitCredentialBinding">
                <KeyRound :size="14" /> {{ bindingRegisterLoading ? bindingModalSubmittingLabel : bindingModalSubmitLabel }}
              </UiButton>
            </div>
            <p v-if="bindingRegisterError" class="settings-tone-danger access-register-status">{{ bindingRegisterError }}</p>
            <p v-else-if="bindingRegisterMessage" class="settings-tone-success access-register-status">{{ bindingRegisterMessage }}</p>
          </div>
        </article>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="revokeModalOpen" class="access-modal-backdrop" @click.self="closeRevokeCredentialBindingModal">
        <article class="settings-panel access-register-panel access-register-modal access-revoke-modal" role="dialog" aria-modal="true">
          <header class="access-panel-title">
            <div>
              <h2>{{ t("settings.access.binding.revokeTitle") }}</h2>
              <span>{{ revokeTargetBindingId }}</span>
            </div>
            <button type="button" class="access-icon-button" :disabled="actionLoading" @click="closeRevokeCredentialBindingModal">
              <X :size="16" />
            </button>
          </header>
          <div class="access-register-form">
            <div class="access-register-note access-revoke-note">
              <ShieldOff :size="14" />
              <span>{{ t("settings.access.binding.revokeWarning", { binding: revokeTargetBindingId }) }}</span>
            </div>
            <label class="access-register-form__wide">
              <span>{{ t("settings.access.binding.revokeConfirmLabel") }} <em>*</em></span>
              <input
                v-model="revokeConfirmationInput"
                :placeholder="revokeTargetBindingId"
                :disabled="actionLoading"
              />
            </label>
            <div class="access-register-actions">
              <UiButton size="sm" variant="ghost" :disabled="actionLoading" @click="closeRevokeCredentialBindingModal">
                {{ t("common.cancel") }}
              </UiButton>
              <UiButton
                size="sm"
                variant="danger"
                :disabled="actionLoading || !revokeConfirmationMatches"
                @click="revokeCredentialBinding"
              >
                <ShieldOff :size="14" />{{ actionLoading ? t("settings.access.binding.action.revoking") : t("settings.access.binding.action.revoke") }}
              </UiButton>
            </div>
          </div>
        </article>
      </div>
    </Teleport>

    <footer class="settings-footer">
      <span><Shield :size="14" />{{ t("settings.access.source.controlPlane") }}</span>
      <span><GitBranch :size="14" />{{ t("settings.access.source.readinessOwnedByAccess") }}</span>
      <span><Save :size="14" />{{ t("settings.access.lastSynced") }}: {{ formatTime(generatedAt) }}</span>
    </footer>
  </main>
</template>

<style scoped>
.access-settings {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 10px;
  height: calc(100dvh - var(--shell-topbar-height));
  padding: 12px 14px calc(var(--settings-statusbar-height) + 10px);
  overflow: hidden;
}

.access-workbench {
  display: grid;
  grid-template-columns: minmax(640px, 1fr) clamp(320px, 25vw, 380px);
  gap: 10px;
  align-items: stretch;
  height: 100%;
  min-width: 0;
  min-height: 0;
}

.access-workbench--no-detail {
  grid-template-columns: minmax(0, 1fr);
}

.access-primary {
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

.access-page-header {
  margin: 0;
}

.access-page-header h1 {
  font-size: 18px;
}

.access-page-header p {
  margin-top: 3px;
  font-size: 11.5px;
}

.access-list {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}

.access-list-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  min-height: 42px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.access-list-toolbar label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
}

.access-list-toolbar span {
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 700;
  white-space: nowrap;
}

.access-list-toolbar select {
  max-width: 132px;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.access-list :deep(.data-table--access-assets) {
  --data-table-min-width: 100%;

  height: 100%;
  min-height: 0;
}

.access-list :deep(td:first-child) {
  color: var(--text-primary);
  font-weight: 750;
}

.access-list :deep(.data-table--access-assets .column-name) {
  width: 18%;
}

.access-list :deep(.data-table--access-assets .column-asset-id) {
  width: 28%;
}

.access-list :deep(.data-table--access-assets .column-kind) {
  width: 15%;
}

.access-list :deep(.data-table--access-assets .column-governance-scope) {
  width: 12%;
}

.access-list :deep(.data-table--access-assets .column-status),
.access-list :deep(.data-table--access-assets .column-readiness) {
  width: 86px;
}

.access-list :deep(.data-table--access-assets .column-required-by) {
  width: 12%;
}

.access-list :deep(.data-table--access-assets .column-credentials) {
  width: 72px;
  text-align: right;
}

.access-list-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 30px;
  padding: 8px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.access-list-footer span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.access-empty {
  padding: 22px;
  color: var(--text-muted);
  font-size: 12px;
}

.access-panel-title,
.access-detail-header,
.access-detail-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.access-panel-title {
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.access-panel-title div {
  display: flex;
  align-items: baseline;
  gap: 9px;
  min-width: 0;
}

.access-panel-title h2,
.access-detail-header h2,
.access-detail-section h3 {
  margin: 0;
  color: var(--text-primary);
}

.access-panel-title h2 {
  font-size: 16px;
}

.access-panel-title span {
  color: var(--color-blue);
  font-size: 12px;
}

.access-icon-button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.access-icon-button:hover {
  background: var(--surface-active);
  color: var(--text-primary);
}

.access-register-panel {
  padding: 0;
  overflow: hidden;
}

.access-register-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 18px;
  padding: 14px 16px 16px;
}

.access-register-form label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.access-register-form label span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.access-register-form label em {
  color: var(--color-red);
  font-style: normal;
}

.access-register-form input,
.access-register-form select {
  width: 100%;
  min-width: 0;
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  outline: 0;
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 13px;
}

.access-register-form input:disabled,
.access-register-form select:disabled {
  cursor: not-allowed;
  opacity: 0.66;
}

.access-register-form__wide,
.access-register-note,
.access-register-actions,
.access-register-status {
  grid-column: 1 / -1;
}

.access-register-note {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid color-mix(in srgb, var(--color-blue) 22%, var(--border-subtle));
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-blue) 10%, var(--surface-panel-soft));
  color: var(--text-secondary);
  font-size: 12px;
}

.access-register-note svg {
  flex: 0 0 auto;
  color: var(--color-blue);
}

.access-revoke-note {
  border-color: color-mix(in srgb, var(--color-danger) 42%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-danger) 10%, var(--surface-panel-soft));
}

.access-revoke-note svg {
  color: var(--color-danger);
}

.access-register-actions {
  display: flex;
  justify-content: flex-end;
}

.access-register-status {
  margin: 0;
  font-size: 12px;
}

.access-modal-backdrop {
  position: fixed;
  z-index: 60;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: color-mix(in srgb, var(--color-black, #000) 34%, transparent);
  backdrop-filter: blur(8px);
}

.access-register-modal {
  width: min(760px, calc(100vw - 48px));
  max-height: calc(100vh - 48px);
  box-shadow: 0 18px 52px rgb(0 0 0 / 28%);
}

.access-detail-drawer {
  height: 100%;
  min-height: 0;
  max-height: none;
  padding: 0;
  overflow: auto;
}

.access-detail-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.access-detail-header h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 16px;
  line-height: 1.2;
}

.access-detail-header h2 span {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 3px 8px;
  border-radius: var(--radius-1);
  background: var(--surface-active);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.access-detail-header p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 11.5px;
  line-height: 1.35;
}

.access-detail-kind {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.access-detail-kind svg {
  color: var(--color-blue);
}

.access-detail-actions {
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.access-detail-actions h3 {
  margin: 0;
  font-size: 13px;
}

.access-detail-actions p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 11.5px;
}

.access-detail-actions p span {
  color: var(--text-secondary);
}

.access-detail-actions div,
.codex-login-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.access-binding-actions > div:first-child {
  display: block;
  min-width: 0;
}

.access-binding-actions > div:last-child {
  flex: 0 1 auto;
}

.access-detail-status,
.access-setup-flow-status {
  margin: 8px 14px 0;
  font-size: 12px;
}

.access-setup-flow-status {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.access-detail-section {
  display: grid;
  gap: 8px;
  padding: 11px 14px;
  border-top: 1px solid var(--border-subtle);
}

.access-detail-section:first-of-type {
  border-top: 0;
}

.access-detail-section h3 {
  font-size: 13px;
}

.access-detail-kv {
  display: grid;
  gap: 8px;
  margin: 0;
}

.access-detail-kv div {
  display: grid;
  grid-template-columns: minmax(104px, 0.44fr) minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  min-width: 0;
}

.access-detail-kv dt {
  color: var(--text-secondary);
  font-size: 11.5px;
}

.access-detail-kv dd {
  min-width: 0;
  margin: 0;
  color: var(--text-primary);
  font-size: 11.5px;
  overflow-wrap: anywhere;
}

.access-inline-code {
  display: inline-flex;
  max-width: 100%;
  min-height: 28px;
  align-items: center;
  padding: 4px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.access-inline-code--wrap {
  display: block;
  line-height: 1.35;
  white-space: normal;
}

.codex-login-card {
  display: grid;
  gap: 8px;
  margin: 10px 14px;
  padding: 8px;
  border: 1px solid color-mix(in srgb, var(--color-blue) 34%, var(--border-subtle));
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-blue) 9%, var(--surface-panel-soft));
}

.codex-login-card__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.codex-login-card__heading h3 {
  margin: 0;
  font-size: 13px;
}

.codex-login-card__heading p {
  margin: 3px 0 0;
  color: var(--text-muted);
  font-size: 11px;
}

.codex-login-card__status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  min-height: 24px;
  padding: 3px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.codex-login-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  margin: 0;
}

.codex-login-grid div {
  min-width: 0;
}

.codex-login-grid dt {
  margin-bottom: 3px;
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 700;
}

.codex-login-grid dd {
  overflow: hidden;
  margin: 0;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oauth-session-strip {
  display: grid;
  gap: 4px;
}

.oauth-session-strip__item {
  display: grid;
  grid-template-columns: auto minmax(64px, max-content) minmax(0, 1fr);
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 11px;
}

.oauth-session-strip__item small {
  overflow: hidden;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-footer {
  margin-top: 0;
}

@media (max-width: 1180px) {
  .access-workbench {
    grid-template-columns: minmax(0, 1fr);
  }

  .access-detail-drawer {
    height: auto;
    max-height: none;
  }
}

@media (max-width: 720px) {
  .access-register-form,
  .codex-login-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .access-detail-kv div {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
}
</style>
