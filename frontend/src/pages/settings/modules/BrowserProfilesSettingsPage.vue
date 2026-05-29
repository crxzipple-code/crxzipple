<script setup lang="ts">
import {
  Activity,
  CheckCircle2,
  Folder,
  Pencil,
  Play,
  Plus,
  Power,
  RefreshCcw,
  RotateCcw,
  Save,
  Shield,
  Square,
  Star,
  Trash2,
  Wifi,
  X,
} from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";

import { hasI18nMessage, useI18n } from "../../../shared/i18n";
import { getAccessOverview, type AccessCredentialBindingPayload } from "../ownerApis/accessAssets";
import {
  controlBrowserProfile,
  createBrowserProfile,
  createBrowserProfilePool,
  deleteBrowserProfilePool,
  deleteBrowserProfile,
  drainBrowserProfilePool,
  listBrowserProfileAllocations,
  listBrowserProfilePools,
  listBrowserProfiles,
  releaseBrowserProfileAllocation,
  setBrowserProfileEnabled,
  setBrowserProfilePoolEnabled,
  setDefaultBrowserProfile,
  testBrowserProfileCdp,
  testBrowserProfileEgress,
  updateBrowserProfilePool,
  updateBrowserProfile,
  type BrowserProfileApiPayload,
  type BrowserProfileAllocationApiPayload,
  type BrowserProfileMutationPayload,
  type BrowserProfilePoolApiPayload,
  type BrowserProfilePoolMutationPayload,
  type BrowserProfilePoolsApiPayload,
  type BrowserProfileTestPayload,
  type BrowserProfilesApiPayload,
} from "../ownerApis/browserProfiles";

type ModalMode = "create" | "edit";
type PoolModalMode = "create" | "edit";

interface BrowserProfileFormState {
  name: string;
  driver: string;
  enabled: boolean;
  cdpUrl: string;
  cdpPort: string;
  userDataDir: string;
  profileDirectory: string;
  attachOnly: boolean;
  autostart: boolean;
  proxyMode: string;
  proxyServer: string;
  proxyBindingId: string;
  proxyCredentialKind: string;
  proxyBypassList: string;
  closeTargetsOnRelease: boolean;
  closeTargetsOnExpire: boolean;
  setAsDefault: boolean;
}

interface BrowserProfilePoolFormState {
  poolId: string;
  displayName: string;
  enabled: boolean;
  profileNames: string[];
  targetHosts: string;
  selectionStrategy: string;
  maxConcurrencyPerProfile: string;
  maxConcurrencyTotal: string;
  allocationTtlSeconds: string;
  cooldownSeconds: string;
  failureCooldownSeconds: string;
  allowAttachOnly: boolean;
  closeTargetsOnRelease: boolean;
  closeTargetsOnExpire: boolean;
}

const DEFAULT_EGRESS_URL = "https://api.ipify.org?format=json";

const { t } = useI18n();
const catalog = ref<BrowserProfilesApiPayload | null>(null);
const poolCatalog = ref<BrowserProfilePoolsApiPayload | null>(null);
const activeAllocations = ref<BrowserProfileAllocationApiPayload[]>([]);
const accessBindings = ref<AccessCredentialBindingPayload[]>([]);
const selectedProfileName = ref<string | null>(null);
const selectedPoolId = ref<string | null>(null);
const isLoading = ref(false);
const accessLoading = ref(false);
const actionProfileName = ref<string | null>(null);
const poolActionId = ref<string | null>(null);
const errorMessage = ref<string | null>(null);
const actionMessage = ref<string | null>(null);
const cdpResult = ref<string | null>(null);
const egressResult = ref<string | null>(null);
const egressUrl = ref(DEFAULT_EGRESS_URL);
const modalMode = ref<ModalMode | null>(null);
const poolModalMode = ref<PoolModalMode | null>(null);
const isSaving = ref(false);
const isPoolSaving = ref(false);
const form = ref(defaultForm());
const poolForm = ref(defaultPoolForm());

const profiles = computed(() => catalog.value?.profiles ?? []);
const pools = computed(() => poolCatalog.value?.pools ?? []);
const defaultProfileName = computed(() => catalog.value?.default_profile ?? "");
const selectedProfile = computed(() =>
  profiles.value.find((profile) => profile.name === selectedProfileName.value)
  ?? profiles.value.find((profile) => profile.name === defaultProfileName.value)
  ?? profiles.value[0]
  ?? null,
);

const managedCount = computed(() =>
  profiles.value.filter((profile) => !profile.attach_only && profile.driver !== "existing-session").length,
);
const enabledCount = computed(() => profiles.value.filter((profile) => profile.enabled !== false).length);
const readyCount = computed(() => profiles.value.filter((profile) => profile.diagnostics?.ready).length);
const proxyCount = computed(() => profiles.value.filter((profile) => profile.proxy?.mode && profile.proxy.mode !== "none").length);
const activePoolCount = computed(() => pools.value.filter((pool) => pool.enabled).length);
const readyPoolCount = computed(() => pools.value.filter((pool) => pool.ready).length);
const activeAllocationCount = computed(() => activeAllocations.value.length);
const selectedIsDefault = computed(() => selectedProfile.value?.name === defaultProfileName.value);
const selectedCanRun = computed(() => Boolean(selectedProfile.value && selectedProfile.value.enabled !== false));
const selectedPool = computed(() =>
  pools.value.find((pool) => pool.pool_id === selectedPoolId.value)
  ?? pools.value[0]
  ?? null,
);
const selectedPoolActiveAllocations = computed(() => {
  const pool = selectedPool.value;
  if (!pool) return [];
  return activeAllocations.value.filter(
    (allocation) => allocation.pool_id === pool.pool_id && allocation.status === "active",
  );
});
const proxyBindingOptions = computed(() =>
  [...accessBindings.value]
    .filter((binding) => isProxyCredentialBinding(binding))
    .filter((binding) => credentialBindingKind(binding) === form.value.proxyCredentialKind)
    .sort((left, right) => credentialBindingRank(left) - credentialBindingRank(right) || left.binding_id.localeCompare(right.binding_id)),
);

onMounted(() => {
  void loadAll();
});

watch(selectedProfile, () => {
  cdpResult.value = null;
  egressResult.value = null;
});

watch(() => form.value.proxyCredentialKind, () => {
  if (
    form.value.proxyBindingId
    && !proxyBindingOptions.value.some((binding) => binding.binding_id === form.value.proxyBindingId)
  ) {
    form.value.proxyBindingId = "";
  }
});

async function loadAll(): Promise<void> {
  await Promise.all([loadProfiles(), loadPools(), loadActiveAllocations(), loadAccessBindings()]);
}

async function loadProfiles(): Promise<void> {
  isLoading.value = true;
  errorMessage.value = null;
  try {
    const payload = await listBrowserProfiles();
    applyCatalog(payload);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    isLoading.value = false;
  }
}

async function loadAccessBindings(): Promise<void> {
  accessLoading.value = true;
  try {
    const overview = await getAccessOverview();
    accessBindings.value = overview.credential_bindings ?? [];
  } catch {
    accessBindings.value = [];
  } finally {
    accessLoading.value = false;
  }
}

async function loadPools(): Promise<void> {
  try {
    const payload = await listBrowserProfilePools();
    applyPoolCatalog(payload);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  }
}

async function loadActiveAllocations(): Promise<void> {
  try {
    const payload = await listBrowserProfileAllocations({ activeOnly: true });
    activeAllocations.value = payload.allocations ?? [];
  } catch {
    activeAllocations.value = [];
  }
}

function applyCatalog(payload: BrowserProfilesApiPayload): void {
  catalog.value = payload;
  selectedProfileName.value = selectedProfileName.value
    && payload.profiles.some((profile) => profile.name === selectedProfileName.value)
    ? selectedProfileName.value
    : payload.default_profile || payload.profiles[0]?.name || null;
}

function applyPoolCatalog(payload: BrowserProfilePoolsApiPayload): void {
  poolCatalog.value = payload;
  selectedPoolId.value = selectedPoolId.value
    && payload.pools.some((pool) => pool.pool_id === selectedPoolId.value)
    ? selectedPoolId.value
    : payload.pools[0]?.pool_id || null;
}

function openCreateModal(): void {
  clearNotices();
  modalMode.value = "create";
  form.value = defaultForm();
}

function openEditModal(profile: BrowserProfileApiPayload): void {
  clearNotices();
  modalMode.value = "edit";
  form.value = formFromProfile(profile);
}

function closeModal(): void {
  if (isSaving.value) return;
  modalMode.value = null;
  form.value = defaultForm();
}

function openCreatePoolModal(): void {
  clearNotices();
  poolModalMode.value = "create";
  poolForm.value = defaultPoolForm();
}

function openEditPoolModal(pool: BrowserProfilePoolApiPayload): void {
  clearNotices();
  poolModalMode.value = "edit";
  poolForm.value = poolFormFromPool(pool);
}

function closePoolModal(): void {
  if (isPoolSaving.value) return;
  poolModalMode.value = null;
  poolForm.value = defaultPoolForm();
}

async function saveProfile(): Promise<void> {
  if (!modalMode.value || isSaving.value) return;
  isSaving.value = true;
  clearNotices();
  try {
    const payload = mutationPayloadFromForm(form.value);
    const nextCatalog = modalMode.value === "create"
      ? await createBrowserProfile({ ...payload, name: form.value.name.trim() })
      : await updateBrowserProfile(form.value.name.trim(), payload);
    applyCatalog(nextCatalog);
    selectedProfileName.value = form.value.name.trim().toLowerCase();
    actionMessage.value = t(
      modalMode.value === "create"
        ? "settings.browserProfiles.notice.created"
        : "settings.browserProfiles.notice.updated",
      { profile: form.value.name.trim() },
    );
    modalMode.value = null;
    form.value = defaultForm();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    isSaving.value = false;
  }
}

async function savePool(): Promise<void> {
  if (!poolModalMode.value || isPoolSaving.value) return;
  isPoolSaving.value = true;
  clearNotices();
  try {
    const payload = poolMutationPayloadFromForm(poolForm.value);
    const poolId = poolForm.value.poolId.trim().toLowerCase();
    const nextCatalog = poolModalMode.value === "create"
      ? await createBrowserProfilePool({ ...payload, pool_id: poolId })
      : await updateBrowserProfilePool(poolId, payload);
    applyPoolCatalog(nextCatalog);
    selectedPoolId.value = poolId;
    actionMessage.value = t(
      poolModalMode.value === "create"
        ? "settings.browserProfiles.pool.notice.created"
        : "settings.browserProfiles.pool.notice.updated",
      { pool: poolId },
    );
    poolModalMode.value = null;
    poolForm.value = defaultPoolForm();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    isPoolSaving.value = false;
  }
}

async function makeDefault(profile: BrowserProfileApiPayload): Promise<void> {
  if (actionProfileName.value || profile.name === defaultProfileName.value) return;
  await runProfileCatalogAction(profile.name, async () => {
    const payload = await setDefaultBrowserProfile(profile.name);
    applyCatalog(payload);
    selectedProfileName.value = profile.name;
    actionMessage.value = t("settings.browserProfiles.notice.defaultChanged", { profile: profile.name });
  });
}

async function toggleProfile(profile: BrowserProfileApiPayload): Promise<void> {
  const nextEnabled = profile.enabled === false;
  await runProfileCatalogAction(profile.name, async () => {
    const payload = await setBrowserProfileEnabled(profile.name, nextEnabled);
    applyCatalog(payload);
    actionMessage.value = t("settings.browserProfiles.notice.enabledChanged", {
      profile: profile.name,
      status: nextEnabled ? t("common.enabled") : t("common.disabled"),
    });
  });
}

async function deleteSelectedProfile(): Promise<void> {
  const profile = selectedProfile.value;
  if (!profile) return;
  await runProfileCatalogAction(profile.name, async () => {
    const payload = await deleteBrowserProfile(profile.name);
    applyCatalog(payload);
    actionMessage.value = t("settings.browserProfiles.notice.deleted", { profile: profile.name });
  });
}

async function togglePool(pool: BrowserProfilePoolApiPayload): Promise<void> {
  const nextEnabled = !pool.enabled;
  await runPoolCatalogAction(pool.pool_id, async () => {
    const payload = await setBrowserProfilePoolEnabled(pool.pool_id, nextEnabled);
    applyPoolCatalog(payload);
    actionMessage.value = t("settings.browserProfiles.pool.notice.enabledChanged", {
      pool: pool.pool_id,
      status: nextEnabled ? t("common.enabled") : t("common.disabled"),
    });
  });
}

async function deleteSelectedPool(): Promise<void> {
  const pool = selectedPool.value;
  if (!pool) return;
  await runPoolCatalogAction(pool.pool_id, async () => {
    const payload = await deleteBrowserProfilePool(pool.pool_id);
    applyPoolCatalog(payload);
    actionMessage.value = t("settings.browserProfiles.pool.notice.deleted", { pool: pool.pool_id });
  });
}

async function drainSelectedPool(): Promise<void> {
  const pool = selectedPool.value;
  if (!pool) return;
  await runPoolCatalogAction(pool.pool_id, async () => {
    const payload = await drainBrowserProfilePool(pool.pool_id);
    actionMessage.value = t("settings.browserProfiles.pool.notice.drained", {
      pool: pool.pool_id,
      count: payload.released,
    });
    await loadPools();
    await loadActiveAllocations();
  });
}

async function releaseAllocation(allocation: BrowserProfileAllocationApiPayload): Promise<void> {
  await runPoolCatalogAction(allocation.pool_id, async () => {
    await releaseBrowserProfileAllocation(allocation.allocation_id);
    actionMessage.value = t("settings.browserProfiles.pool.notice.released", {
      allocation: allocation.allocation_id,
    });
    await loadPools();
    await loadActiveAllocations();
  });
}

async function controlSelectedProfile(action: "start" | "stop" | "restart"): Promise<void> {
  const profile = selectedProfile.value;
  if (!profile) return;
  await runProfileControlAction(profile.name, async () => {
    const payload = await controlBrowserProfile(profile.name, action);
    actionMessage.value = payload.message || t(`settings.browserProfiles.notice.${action}`, { profile: profile.name });
    await loadProfiles();
  });
}

async function runCdpTest(): Promise<void> {
  const profile = selectedProfile.value;
  if (!profile) return;
  await runProfileControlAction(profile.name, async () => {
    const payload = await testBrowserProfileCdp(profile.name);
    cdpResult.value = diagnosticsSummaryText(payload.profile) || t("settings.browserProfiles.test.noResult");
    await loadProfiles();
  });
}

async function runEgressTest(): Promise<void> {
  const profile = selectedProfile.value;
  if (!profile) return;
  await runProfileControlAction(profile.name, async () => {
    const payload = await testBrowserProfileEgress(profile.name, egressUrl.value.trim() || undefined);
    egressResult.value = summarizeEgressResult(payload);
    await loadProfiles();
  });
}

async function runProfileCatalogAction(profileName: string, action: () => Promise<void>): Promise<void> {
  if (actionProfileName.value) return;
  actionProfileName.value = profileName;
  clearNotices();
  try {
    await action();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionProfileName.value = null;
  }
}

async function runProfileControlAction(profileName: string, action: () => Promise<void>): Promise<void> {
  if (actionProfileName.value) return;
  actionProfileName.value = profileName;
  clearNotices({ keepTests: true });
  try {
    await action();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionProfileName.value = null;
  }
}

async function runPoolCatalogAction(poolId: string, action: () => Promise<void>): Promise<void> {
  if (poolActionId.value) return;
  poolActionId.value = poolId;
  clearNotices();
  try {
    await action();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    poolActionId.value = null;
  }
}

function clearNotices(options: { keepTests?: boolean } = {}): void {
  errorMessage.value = null;
  actionMessage.value = null;
  if (!options.keepTests) {
    cdpResult.value = null;
    egressResult.value = null;
  }
}

function defaultForm(): BrowserProfileFormState {
  return {
    name: "",
    driver: "managed",
    enabled: true,
    cdpUrl: "",
    cdpPort: "",
    userDataDir: "",
    profileDirectory: "",
    attachOnly: false,
    autostart: true,
    proxyMode: "none",
    proxyServer: "",
    proxyBindingId: "",
    proxyCredentialKind: "basic",
    proxyBypassList: "",
    closeTargetsOnRelease: true,
    closeTargetsOnExpire: true,
    setAsDefault: false,
  };
}

function defaultPoolForm(): BrowserProfilePoolFormState {
  return {
    poolId: "",
    displayName: "",
    enabled: true,
    profileNames: [],
    targetHosts: "",
    selectionStrategy: "least_busy",
    maxConcurrencyPerProfile: "1",
    maxConcurrencyTotal: "",
    allocationTtlSeconds: "900",
    cooldownSeconds: "0",
    failureCooldownSeconds: "300",
    allowAttachOnly: false,
    closeTargetsOnRelease: true,
    closeTargetsOnExpire: true,
  };
}

function formFromProfile(profile: BrowserProfileApiPayload): BrowserProfileFormState {
  return {
    name: profile.name,
    driver: profile.driver || "managed",
    enabled: profile.enabled !== false,
    cdpUrl: profile.configured_cdp_url || "",
    cdpPort: profile.configured_cdp_port ? String(profile.configured_cdp_port) : "",
    userDataDir: profile.user_data_dir || "",
    profileDirectory: profile.profile_directory || "",
    attachOnly: Boolean(profile.attach_only),
    autostart: profile.autostart !== false,
    proxyMode: profile.proxy?.mode || "none",
    proxyServer: profile.proxy?.server || "",
    proxyBindingId: profile.proxy?.binding_id || "",
    proxyCredentialKind: profile.proxy?.credential_kind || "basic",
    proxyBypassList: (profile.proxy?.bypass_list ?? []).join(", "),
    closeTargetsOnRelease: profile.close_targets_on_release !== false,
    closeTargetsOnExpire: profile.close_targets_on_expire !== false,
    setAsDefault: profile.name === defaultProfileName.value,
  };
}

function mutationPayloadFromForm(value: BrowserProfileFormState): BrowserProfileMutationPayload {
  const proxyMode = value.proxyMode || "none";
  return {
    driver: value.driver,
    enabled: value.enabled,
    cdp_url: nullableText(value.cdpUrl),
    cdp_port: nullableNumber(value.cdpPort),
    user_data_dir: nullableText(value.userDataDir),
    profile_directory: nullableText(value.profileDirectory),
    attach_only: value.attachOnly || value.driver === "existing-session",
    autostart: value.driver === "existing-session" ? false : value.autostart,
    proxy_mode: proxyMode,
    proxy_server: proxyMode === "none" ? null : nullableText(value.proxyServer),
    proxy_binding_id: proxyMode === "access_binding" ? nullableText(value.proxyBindingId) : null,
    proxy_credential_kind: value.proxyCredentialKind,
    proxy_bypass_list: commaList(value.proxyBypassList),
    close_targets_on_release: value.closeTargetsOnRelease,
    close_targets_on_expire: value.closeTargetsOnExpire,
    set_as_default: value.setAsDefault,
  };
}

function poolFormFromPool(pool: BrowserProfilePoolApiPayload): BrowserProfilePoolFormState {
  return {
    poolId: pool.pool_id,
    displayName: pool.display_name || "",
    enabled: pool.enabled,
    profileNames: [...pool.profile_names],
    targetHosts: pool.target_hosts.join(", "),
    selectionStrategy: pool.selection_strategy || "least_busy",
    maxConcurrencyPerProfile: String(pool.max_concurrency_per_profile || 1),
    maxConcurrencyTotal: pool.max_concurrency_total ? String(pool.max_concurrency_total) : "",
    allocationTtlSeconds: String(pool.allocation_ttl_seconds || 900),
    cooldownSeconds: String(pool.cooldown_seconds ?? 0),
    failureCooldownSeconds: String(pool.failure_cooldown_seconds ?? 300),
    allowAttachOnly: Boolean(pool.allow_attach_only),
    closeTargetsOnRelease: pool.close_targets_on_release !== false,
    closeTargetsOnExpire: pool.close_targets_on_expire !== false,
  };
}

function poolMutationPayloadFromForm(value: BrowserProfilePoolFormState): BrowserProfilePoolMutationPayload {
  return {
    display_name: nullableText(value.displayName),
    enabled: value.enabled,
    profile_names: value.profileNames,
    target_hosts: commaList(value.targetHosts),
    selection_strategy: value.selectionStrategy,
    max_concurrency_per_profile: nullableNumber(value.maxConcurrencyPerProfile) || 1,
    max_concurrency_total: nullableNumber(value.maxConcurrencyTotal),
    allocation_ttl_seconds: nullableNumber(value.allocationTtlSeconds) || 900,
    cooldown_seconds: nullableNumber(value.cooldownSeconds) ?? 0,
    failure_cooldown_seconds: nullableNumber(value.failureCooldownSeconds) ?? 300,
    allow_attach_only: value.allowAttachOnly,
    close_targets_on_release: value.closeTargetsOnRelease,
    close_targets_on_expire: value.closeTargetsOnExpire,
  };
}

function togglePoolProfile(profileName: string): void {
  const names = new Set(poolForm.value.profileNames);
  if (names.has(profileName)) {
    names.delete(profileName);
  } else {
    names.add(profileName);
  }
  poolForm.value = {
    ...poolForm.value,
    profileNames: [...names],
  };
}

function poolProfileChecked(profileName: string): boolean {
  return poolForm.value.profileNames.includes(profileName);
}

function nullableText(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function nullableNumber(value: string): number | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const parsed = Number.parseInt(normalized, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function commaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function profileStatus(profile: BrowserProfileApiPayload): string {
  if (profile.enabled === false) return t("common.disabled");
  return diagnosticStatusLabel(profile);
}

function profileStatusTone(profile: BrowserProfileApiPayload): string {
  const status = (profile.diagnostics?.status || "").toLowerCase();
  if (profile.enabled === false) return "warning";
  if (profile.diagnostics?.ready || status === "ready") return "success";
  if (["error", "degraded", "failed"].includes(status)) return "danger";
  return "warning";
}

function profileMode(profile: BrowserProfileApiPayload): string {
  if (profile.attach_only || profile.driver === "existing-session") return t("settings.browserProfiles.mode.attachOnly");
  if (profile.driver === "managed") return t("settings.browserProfiles.mode.managed");
  return profile.driver || t("settings.browserProfiles.mode.custom");
}

function endpointLabel(profile: BrowserProfileApiPayload): string {
  return profile.resolved_cdp_url || profile.configured_cdp_url || (
    profile.resolved_cdp_port || profile.configured_cdp_port
      ? `:${profile.resolved_cdp_port || profile.configured_cdp_port}`
      : "-"
  );
}

function tableEndpointLabel(profile: BrowserProfileApiPayload): string {
  const port = profile.resolved_cdp_port || profile.configured_cdp_port;
  if (port) return `:${port}`;
  const endpoint = profile.resolved_cdp_url || profile.configured_cdp_url || "";
  return endpoint ? endpoint.replace(/^https?:\/\//, "") : "-";
}

function storageLabel(profile: BrowserProfileApiPayload): string {
  return profile.user_data_dir || profile.profile_directory || t("settings.browserProfiles.empty.noStoragePath");
}

function proxyLabel(profile: BrowserProfileApiPayload): string {
  const mode = profile.proxy?.mode || "none";
  if (mode === "none") return t("settings.browserProfiles.proxy.none");
  if (mode === "access_binding") return profile.proxy?.binding_id || t("settings.browserProfiles.proxy.bindingMissing");
  return profile.proxy?.server || t("settings.browserProfiles.proxy.serverMissing");
}

function runtimeLabel(profile: BrowserProfileApiPayload): string {
  const status = profile.runtime?.attachment_status;
  if (!status) return "idle";
  return profile.runtime?.running_pid ? `${status} · pid ${profile.runtime.running_pid}` : status;
}

function runtimeStatusLabel(profile: BrowserProfileApiPayload): string {
  return profile.runtime?.attachment_status || "idle";
}

function egressLabel(profile: BrowserProfileApiPayload): string {
  const runtime = profile.runtime;
  if (!runtime) return "-";
  const status = runtime.proxy_egress_status || stringFromRecord(runtime.proxy_egress, "status");
  const ip = runtime.proxy_egress_ip || stringFromRecord(runtime.proxy_egress, "ip");
  if (!status && !ip) return "-";
  return [status, ip].filter(Boolean).join(" · ");
}

function stringFromRecord(record: Record<string, unknown> | undefined, key: string): string {
  const value = record?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function poolStatus(pool: BrowserProfilePoolApiPayload): string {
  if (!pool.enabled) return t("common.disabled");
  if (pool.ready) return t("settings.browserProfiles.pool.status.ready");
  if (pool.missing_profiles.length) return t("settings.browserProfiles.pool.status.missing");
  if (!pool.eligible_profile_count) return t("settings.browserProfiles.pool.status.noEligible");
  return t("status.unknown");
}

function poolStatusTone(pool: BrowserProfilePoolApiPayload): string {
  if (!pool.enabled) return "warning";
  if (pool.ready) return "success";
  if (pool.missing_profiles.length) return "danger";
  return "warning";
}

function poolConcurrencyLabel(pool: BrowserProfilePoolApiPayload): string {
  const total = pool.max_concurrency_total ? String(pool.max_concurrency_total) : "-";
  return `${pool.max_concurrency_per_profile} / ${total}`;
}

function poolProfilesLabel(pool: BrowserProfilePoolApiPayload): string {
  return pool.profile_names.length ? pool.profile_names.join(", ") : "-";
}

function poolHostsLabel(pool: BrowserProfilePoolApiPayload): string {
  return pool.target_hosts.length ? pool.target_hosts.join(", ") : "-";
}

function selectionStrategyLabel(value: string | undefined): string {
  const normalized = (value || "").trim().toLowerCase();
  if (normalized === "least_busy") return t("text.leastBusy");
  if (normalized === "round_robin") return t("text.roundRobin");
  if (normalized === "sticky_session") return t("text.stickySession");
  if (normalized === "manual_only") return t("text.manualOnly");
  return value || "-";
}

function activeAllocationLabelForProfile(profileName: string): string {
  const count = activeAllocations.value.filter(
    (allocation) => allocation.profile_name === profileName && allocation.status === "active",
  ).length;
  return count ? String(count) : "-";
}

function activeAllocationLabelForPool(poolId: string): string {
  const count = activeAllocations.value.filter(
    (allocation) => allocation.pool_id === poolId && allocation.status === "active",
  ).length;
  return count ? String(count) : "-";
}

function summarizeEgressResult(payload: BrowserProfileTestPayload): string {
  if (payload.status === "not_required") return t("settings.browserProfiles.test.egressNotRequired");
  const result = payload.result;
  if (result && typeof result === "object") {
    const record = result as Record<string, unknown>;
    const status = String(record.status ?? "unknown");
    const ip = typeof record.ip === "string" ? record.ip : "";
    const reason = typeof record.reason === "string" ? record.reason : "";
    return [status, ip, reason].filter(Boolean).join(" · ");
  }
  return String(payload.status ?? payload.reason ?? t("settings.browserProfiles.test.noResult"));
}

function diagnosticStatusLabel(profile: BrowserProfileApiPayload): string {
  const code = diagnosticCode(profile);
  const key = `settings.browserProfiles.diagnostics.status.${code}`;
  if (hasI18nMessage(key)) return t(key);
  return profile.diagnostics?.status || t("status.unknown");
}

function diagnosticsSummaryText(profile: BrowserProfileApiPayload | undefined): string {
  if (!profile?.diagnostics) return t("settings.browserProfiles.empty.noDiagnostics");
  const code = diagnosticCode(profile);
  const messageKey = `settings.browserProfiles.diagnostics.message.${code}`;
  if (hasI18nMessage(messageKey)) {
    return t(messageKey, {
      fields: (profile.diagnostics.restart_fields ?? []).join(", ") || "-",
    });
  }
  const probeStatus = normalizeDiagnosticCode(profile.diagnostics.probe?.status);
  if (probeStatus) {
    const probeMessageKey = `settings.browserProfiles.diagnostics.message.${probeStatus}`;
    if (hasI18nMessage(probeMessageKey)) return t(probeMessageKey);
  }
  return t("settings.browserProfiles.diagnostics.message.generic", {
    status: diagnosticStatusLabel(profile),
  });
}

function diagnosticCode(profile: BrowserProfileApiPayload): string {
  const summaryCode = normalizeDiagnosticCode(profile.diagnostics?.summary?.code);
  if (summaryCode) return summaryCode;
  const probeStatus = normalizeDiagnosticCode(profile.diagnostics?.probe?.status);
  if (probeStatus === "cdp-profile-mismatch") return "profile-mismatch";
  return normalizeDiagnosticCode(profile.diagnostics?.status) || "unknown";
}

function normalizeDiagnosticCode(value: string | undefined): string {
  return (value || "").trim().toLowerCase().replace(/_/g, "-");
}

function isProxyCredentialBinding(binding: AccessCredentialBindingPayload): boolean {
  const kind = credentialBindingKind(binding);
  const source = normalizedCredentialText(binding.source_kind);
  return ["basic", "bearer_token"].includes(kind) || ["basic", "bearer_token"].includes(source);
}

function credentialBindingKind(binding: AccessCredentialBindingPayload): string {
  const kind = normalizedCredentialText(binding.binding_kind);
  if (kind === "bearer") return "bearer_token";
  if (kind) return kind;
  const source = normalizedCredentialText(binding.source_kind);
  return source === "bearer" ? "bearer_token" : source;
}

function credentialBindingRank(binding: AccessCredentialBindingPayload): number {
  const status = normalizedCredentialText(binding.status) || "active";
  if (["active", "ready", "enabled"].includes(status)) return 0;
  if (["disabled", "revoked", "blocked", "failed"].includes(status)) return 2;
  return 1;
}

function credentialBindingLabel(binding: AccessCredentialBindingPayload): string {
  const kind = binding.binding_kind || binding.source_kind || "credential";
  const status = binding.status ? ` · ${binding.status}` : "";
  const preview = binding.masked_preview ? ` · ${binding.masked_preview}` : "";
  return `${binding.binding_id} · ${kind}${preview}${status}`;
}

function normalizedCredentialText(value: string | null | undefined): string {
  return (value || "").trim().toLowerCase();
}
</script>

<template>
  <main class="browser-settings settings-module">
    <header class="browser-settings-head settings-page-header">
      <div>
        <h1>{{ t("settings.resource.browserProfiles") }}</h1>
        <p>{{ t("settings.browserProfiles.subtitle") }}</p>
      </div>
      <div class="browser-head-actions">
        <button type="button" class="browser-settings-button browser-settings-button--primary" @click="openCreateModal">
          <Plus :size="15" />
          {{ t("settings.browserProfiles.action.new") }}
        </button>
        <button type="button" :disabled="isLoading" class="browser-settings-button" @click="loadAll">
          <RefreshCcw :size="15" />
          {{ t("common.refresh") }}
        </button>
      </div>
    </header>

    <section class="browser-stat-strip" :aria-label="t('settings.browserProfiles.summary.aria')">
      <article>
        <Star :size="19" />
        <span>{{ t("settings.browserProfiles.summary.default") }}</span>
        <strong>{{ defaultProfileName || "-" }}</strong>
      </article>
      <article>
        <Folder :size="19" />
        <span>{{ t("settings.browserProfiles.summary.managed") }}</span>
        <strong>{{ managedCount }} / {{ profiles.length }}</strong>
      </article>
      <article>
        <CheckCircle2 :size="19" />
        <span>{{ t("settings.browserProfiles.summary.ready") }}</span>
        <strong>{{ readyCount }} / {{ enabledCount }}</strong>
      </article>
      <article>
        <Shield :size="19" />
        <span>{{ t("settings.browserProfiles.summary.proxy") }}</span>
        <strong>{{ proxyCount }}</strong>
      </article>
      <article>
        <Activity :size="19" />
        <span>{{ t("settings.browserProfiles.summary.activeAllocations") }}</span>
        <strong>{{ activeAllocationCount }}</strong>
      </article>
    </section>

    <p v-if="errorMessage" class="browser-settings-alert">{{ errorMessage }}</p>
    <p v-else-if="actionMessage" class="browser-settings-message">{{ actionMessage }}</p>

    <section class="browser-settings-workspace">
      <div class="browser-profile-table">
        <div class="browser-profile-row browser-profile-row--head">
          <span>{{ t("settings.browserProfiles.table.name") }}</span>
          <span>{{ t("settings.browserProfiles.table.mode") }}</span>
          <span>{{ t("common.status") }}</span>
          <span>{{ t("settings.browserProfiles.table.endpoint") }}</span>
          <span>{{ t("settings.browserProfiles.table.proxy") }}</span>
          <span>{{ t("settings.browserProfiles.table.egress") }}</span>
          <span>{{ t("settings.browserProfiles.table.runtime") }}</span>
          <span>{{ t("settings.browserProfiles.table.allocations") }}</span>
          <span>{{ t("common.actions") }}</span>
        </div>
        <div
          v-for="profile in profiles"
          :key="profile.name"
          role="button"
          tabindex="0"
          class="browser-profile-row"
          :class="{ selected: selectedProfile?.name === profile.name }"
          @click="selectedProfileName = profile.name"
          @keydown.enter.prevent="selectedProfileName = profile.name"
          @keydown.space.prevent="selectedProfileName = profile.name"
        >
          <strong>
            {{ profile.name }}
            <Star v-if="profile.name === defaultProfileName" :size="13" />
          </strong>
          <span>{{ profileMode(profile) }}</span>
          <span class="browser-status" :class="`browser-status--${profileStatusTone(profile)}`">
            {{ profileStatus(profile) }}
          </span>
          <span>{{ tableEndpointLabel(profile) }}</span>
          <span>{{ proxyLabel(profile) }}</span>
          <span>{{ egressLabel(profile) }}</span>
          <span>{{ runtimeStatusLabel(profile) }}</span>
          <span>{{ activeAllocationLabelForProfile(profile.name) }}</span>
          <span class="browser-row-actions">
            <button
              type="button"
              :disabled="profile.name === defaultProfileName || actionProfileName === profile.name"
              :title="t('settings.browserProfiles.action.default')"
              @click.stop="makeDefault(profile)"
            >
              <Star :size="13" />
            </button>
            <button
              type="button"
              :disabled="actionProfileName === profile.name"
              :title="profile.enabled === false ? t('settings.browserProfiles.action.enable') : t('settings.browserProfiles.action.disable')"
              @click.stop="toggleProfile(profile)"
            >
              <Power :size="13" />
            </button>
          </span>
        </div>
        <div v-if="!profiles.length" class="browser-settings-empty">
          {{ isLoading ? t("settings.browserProfiles.state.loading") : t("settings.browserProfiles.empty.noProfiles") }}
        </div>
      </div>

      <aside class="browser-profile-detail">
        <template v-if="selectedProfile">
          <div class="browser-detail-head">
            <div>
              <h2>{{ selectedProfile.name }}</h2>
              <p>{{ diagnosticsSummaryText(selectedProfile) }}</p>
            </div>
            <span class="browser-status" :class="`browser-status--${profileStatusTone(selectedProfile)}`">
              {{ profileStatus(selectedProfile) }}
            </span>
          </div>

          <div class="browser-detail-actions">
            <button type="button" :disabled="!selectedCanRun || actionProfileName === selectedProfile.name" @click="controlSelectedProfile('start')">
              <Play :size="14" />{{ t("settings.browserProfiles.action.start") }}
            </button>
            <button type="button" :disabled="actionProfileName === selectedProfile.name" @click="controlSelectedProfile('stop')">
              <Square :size="14" />{{ t("settings.browserProfiles.action.stop") }}
            </button>
            <button type="button" :disabled="!selectedCanRun || actionProfileName === selectedProfile.name" @click="controlSelectedProfile('restart')">
              <RotateCcw :size="14" />{{ t("settings.browserProfiles.action.restart") }}
            </button>
            <button type="button" :disabled="actionProfileName === selectedProfile.name" @click="openEditModal(selectedProfile)">
              <Pencil :size="14" />{{ t("common.edit") }}
            </button>
          </div>

          <dl class="browser-detail-grid">
            <div><dt>{{ t("settings.browserProfiles.detail.driver") }}</dt><dd>{{ selectedProfile.driver }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.userDataDir") }}</dt><dd>{{ selectedProfile.user_data_dir || "-" }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.profileDirectory") }}</dt><dd>{{ selectedProfile.profile_directory || "-" }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.endpoint") }}</dt><dd>{{ endpointLabel(selectedProfile) }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.proxy") }}</dt><dd>{{ proxyLabel(selectedProfile) }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.egress") }}</dt><dd>{{ egressLabel(selectedProfile) }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.runtime") }}</dt><dd>{{ runtimeLabel(selectedProfile) }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.autostart") }}</dt><dd>{{ selectedProfile.autostart === false ? t("common.no") : t("common.yes") }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.closeOnRelease") }}</dt><dd>{{ selectedProfile.close_targets_on_release === false ? t("common.no") : t("common.yes") }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.closeOnExpire") }}</dt><dd>{{ selectedProfile.close_targets_on_expire === false ? t("common.no") : t("common.yes") }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.detail.storage") }}</dt><dd>{{ storageLabel(selectedProfile) }}</dd></div>
          </dl>

          <section class="browser-test-panel">
            <div>
              <h3>{{ t("settings.browserProfiles.test.title") }}</h3>
              <p>{{ accessLoading ? t("settings.browserProfiles.test.loadingBindings") : t("settings.browserProfiles.test.subtitle") }}</p>
            </div>
            <div class="browser-test-actions">
              <button type="button" :disabled="actionProfileName === selectedProfile.name" @click="runCdpTest">
                <Activity :size="14" />{{ t("settings.browserProfiles.action.testCdp") }}
              </button>
              <label>
                <Wifi :size="14" />
                <input v-model="egressUrl" :placeholder="DEFAULT_EGRESS_URL" />
              </label>
              <button type="button" :disabled="actionProfileName === selectedProfile.name" @click="runEgressTest">
                {{ t("settings.browserProfiles.action.testEgress") }}
              </button>
            </div>
            <p v-if="cdpResult">{{ cdpResult }}</p>
            <p v-if="egressResult">{{ egressResult }}</p>
          </section>

          <section class="browser-danger-zone">
            <div>
              <h3>{{ t("settings.browserProfiles.danger.title") }}</h3>
              <p>{{ selectedIsDefault ? t("settings.browserProfiles.danger.defaultHint") : t("settings.browserProfiles.danger.deleteHint") }}</p>
            </div>
            <button type="button" :disabled="selectedIsDefault || actionProfileName === selectedProfile.name" @click="deleteSelectedProfile">
              <Trash2 :size="14" />{{ t("common.delete") }}
            </button>
          </section>
        </template>
        <template v-else>
          <h2>{{ t("settings.browserProfiles.empty.noSelectionTitle") }}</h2>
          <p>{{ t("settings.browserProfiles.empty.noSelectionBody") }}</p>
        </template>
      </aside>

      <section class="browser-pool-section" :class="{ 'browser-pool-section--wide': !selectedPool }">
        <header>
          <div>
            <h2>{{ t("settings.browserProfiles.pool.title") }}</h2>
            <p>{{ t("settings.browserProfiles.pool.subtitle", { ready: readyPoolCount, active: activePoolCount }) }}</p>
          </div>
          <button type="button" class="browser-settings-button browser-settings-button--primary" @click="openCreatePoolModal">
            <Plus :size="15" />
            {{ t("settings.browserProfiles.pool.action.new") }}
          </button>
        </header>

        <div class="browser-pool-table">
          <div class="browser-pool-row browser-pool-row--head">
            <span>{{ t("settings.browserProfiles.pool.table.pool") }}</span>
            <span>{{ t("settings.browserProfiles.pool.table.profiles") }}</span>
            <span>{{ t("settings.browserProfiles.pool.table.hosts") }}</span>
            <span>{{ t("settings.browserProfiles.pool.table.strategy") }}</span>
            <span>{{ t("settings.browserProfiles.pool.table.concurrency") }}</span>
            <span>{{ t("settings.browserProfiles.pool.table.activeAllocations") }}</span>
            <span>{{ t("common.status") }}</span>
            <span>{{ t("common.actions") }}</span>
          </div>
          <div
            v-for="pool in pools"
            :key="pool.pool_id"
            role="button"
            tabindex="0"
            class="browser-pool-row"
            :class="{ selected: selectedPool?.pool_id === pool.pool_id }"
            @click="selectedPoolId = pool.pool_id"
            @keydown.enter.prevent="selectedPoolId = pool.pool_id"
            @keydown.space.prevent="selectedPoolId = pool.pool_id"
          >
            <strong>{{ pool.display_name || pool.pool_id }}</strong>
            <span>{{ poolProfilesLabel(pool) }}</span>
            <span>{{ poolHostsLabel(pool) }}</span>
            <span>{{ selectionStrategyLabel(pool.selection_strategy) }}</span>
            <span>{{ poolConcurrencyLabel(pool) }}</span>
            <span>{{ activeAllocationLabelForPool(pool.pool_id) }}</span>
            <span class="browser-status" :class="`browser-status--${poolStatusTone(pool)}`">
              {{ poolStatus(pool) }}
            </span>
            <span class="browser-row-actions">
              <button
                type="button"
                :disabled="poolActionId === pool.pool_id"
                :title="t('common.edit')"
                @click.stop="openEditPoolModal(pool)"
              >
                <Pencil :size="13" />
              </button>
              <button
                type="button"
                :disabled="poolActionId === pool.pool_id"
                :title="pool.enabled ? t('settings.browserProfiles.action.disable') : t('settings.browserProfiles.action.enable')"
                @click.stop="togglePool(pool)"
              >
                <Power :size="13" />
              </button>
            </span>
          </div>
          <div v-if="!pools.length" class="browser-settings-empty">
            {{ t("settings.browserProfiles.pool.empty") }}
          </div>
        </div>

        <aside v-if="selectedPool" class="browser-pool-detail">
          <div class="browser-pool-detail-head">
            <strong>{{ selectedPool.display_name || selectedPool.pool_id }}</strong>
            <span class="browser-status" :class="`browser-status--${poolStatusTone(selectedPool)}`">
              {{ poolStatus(selectedPool) }}
            </span>
          </div>
          <dl>
            <div><dt>{{ t("settings.browserProfiles.pool.detail.profiles") }}</dt><dd>{{ poolProfilesLabel(selectedPool) }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.detail.eligible") }}</dt><dd>{{ selectedPool.eligible_profile_count }} / {{ selectedPool.profile_count }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.table.strategy") }}</dt><dd>{{ selectionStrategyLabel(selectedPool.selection_strategy) }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.table.concurrency") }}</dt><dd>{{ poolConcurrencyLabel(selectedPool) }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.detail.ttl") }}</dt><dd>{{ selectedPool.allocation_ttl_seconds }}s</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.detail.cooldown") }}</dt><dd>{{ selectedPool.cooldown_seconds }}s / {{ selectedPool.failure_cooldown_seconds }}s</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.detail.attachOnly") }}</dt><dd>{{ selectedPool.allow_attach_only ? t("common.yes") : t("common.no") }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.detail.closeTargets") }}</dt><dd>{{ selectedPool.close_targets_on_release ? t("common.yes") : t("common.no") }} / {{ selectedPool.close_targets_on_expire ? t("common.yes") : t("common.no") }}</dd></div>
            <div><dt>{{ t("settings.browserProfiles.pool.detail.missing") }}</dt><dd>{{ selectedPool.missing_profiles.join(", ") || "-" }}</dd></div>
          </dl>
          <section v-if="selectedPoolActiveAllocations.length" class="browser-allocation-list">
            <h3>{{ t("settings.browserProfiles.pool.detail.activeAllocations") }}</h3>
            <div>
              <article
                v-for="allocation in selectedPoolActiveAllocations"
                :key="allocation.allocation_id"
              >
                <span>
                  <strong>{{ allocation.profile_name }}</strong>
                  <small>{{ allocation.target_host || allocation.consumer_id }}</small>
                </span>
                <button
                  type="button"
                  :disabled="poolActionId === allocation.pool_id"
                  :title="t('settings.browserProfiles.pool.action.release')"
                  @click="releaseAllocation(allocation)"
                >
                  <X :size="13" />
                </button>
              </article>
            </div>
          </section>
          <div class="browser-pool-detail-actions">
            <button type="button" :disabled="poolActionId === selectedPool.pool_id" @click="drainSelectedPool">
              <RotateCcw :size="14" />{{ t("settings.browserProfiles.pool.action.drain") }}
            </button>
            <button type="button" :disabled="poolActionId === selectedPool.pool_id" @click="deleteSelectedPool">
              <Trash2 :size="14" />{{ t("common.delete") }}
            </button>
          </div>
        </aside>
      </section>
    </section>

    <div v-if="modalMode" class="browser-modal-backdrop" @click.self="closeModal">
      <section class="browser-modal">
        <header>
          <div>
            <h2>{{ modalMode === "create" ? t("settings.browserProfiles.modal.createTitle") : t("settings.browserProfiles.modal.editTitle") }}</h2>
            <p>{{ t("settings.browserProfiles.modal.subtitle") }}</p>
          </div>
          <button type="button" :disabled="isSaving" @click="closeModal">
            <X :size="16" />
          </button>
        </header>

        <div class="browser-form-grid">
          <label>
            <span>{{ t("settings.browserProfiles.field.name") }}</span>
            <input v-model="form.name" :disabled="modalMode === 'edit' || isSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.driver") }}</span>
            <select v-model="form.driver" :disabled="isSaving">
              <option value="managed">{{ t("settings.browserProfiles.mode.managed") }}</option>
              <option value="existing-session">{{ t("settings.browserProfiles.mode.attachOnly") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.enabled") }}</span>
            <select v-model="form.enabled" :disabled="isSaving">
              <option :value="true">{{ t("common.enabled") }}</option>
              <option :value="false">{{ t("common.disabled") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.autostart") }}</span>
            <select v-model="form.autostart" :disabled="isSaving || form.driver === 'existing-session'">
              <option :value="true">{{ t("common.yes") }}</option>
              <option :value="false">{{ t("common.no") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.cdpUrl") }}</span>
            <input v-model="form.cdpUrl" :placeholder="t('settings.browserProfiles.placeholder.cdpUrl')" :disabled="isSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.cdpPort") }}</span>
            <input v-model="form.cdpPort" inputmode="numeric" placeholder="9222" :disabled="isSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.userDataDir") }}</span>
            <input v-model="form.userDataDir" :placeholder="t('settings.browserProfiles.placeholder.userDataDir')" :disabled="isSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.profileDirectory") }}</span>
            <input v-model="form.profileDirectory" placeholder="Profile 1" :disabled="isSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.proxyMode") }}</span>
            <select v-model="form.proxyMode" :disabled="isSaving">
              <option value="none">{{ t("settings.browserProfiles.proxy.none") }}</option>
              <option value="static">{{ t("settings.browserProfiles.proxy.static") }}</option>
              <option value="access_binding">{{ t("settings.browserProfiles.proxy.accessBinding") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.proxyServer") }}</span>
            <input v-model="form.proxyServer" placeholder="http://proxy.example:8080" :disabled="isSaving || form.proxyMode === 'none'" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.proxyCredentialKind") }}</span>
            <select v-model="form.proxyCredentialKind" :disabled="isSaving || form.proxyMode !== 'access_binding'">
              <option value="basic">{{ t("settings.browserProfiles.proxyCredential.basic") }}</option>
              <option value="bearer_token">{{ t("settings.browserProfiles.proxyCredential.bearerToken") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.proxyBinding") }}</span>
            <select v-model="form.proxyBindingId" :disabled="isSaving || form.proxyMode !== 'access_binding'">
              <option value="">{{ t("settings.browserProfiles.proxy.noBinding") }}</option>
              <option
                v-for="binding in proxyBindingOptions"
                :key="binding.binding_id"
                :value="binding.binding_id"
              >
                {{ credentialBindingLabel(binding) }}
              </option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.proxyBypass") }}</span>
            <input v-model="form.proxyBypassList" placeholder="localhost, 127.0.0.1" :disabled="isSaving || form.proxyMode === 'none'" />
          </label>
          <label class="browser-form-check">
            <input v-model="form.attachOnly" type="checkbox" :disabled="isSaving || form.driver === 'existing-session'" />
            <span>{{ t("settings.browserProfiles.field.attachOnly") }}</span>
          </label>
          <label class="browser-form-check">
            <input v-model="form.closeTargetsOnRelease" type="checkbox" :disabled="isSaving" />
            <span>{{ t("settings.browserProfiles.field.closeTargetsOnRelease") }}</span>
          </label>
          <label class="browser-form-check">
            <input v-model="form.closeTargetsOnExpire" type="checkbox" :disabled="isSaving" />
            <span>{{ t("settings.browserProfiles.field.closeTargetsOnExpire") }}</span>
          </label>
          <label class="browser-form-check">
            <input v-model="form.setAsDefault" type="checkbox" :disabled="isSaving" />
            <span>{{ t("settings.browserProfiles.field.setDefault") }}</span>
          </label>
        </div>

        <footer>
          <button type="button" :disabled="isSaving" @click="closeModal">
            {{ t("common.cancel") }}
          </button>
          <button type="button" class="browser-settings-button--primary" :disabled="isSaving || !form.name.trim()" @click="saveProfile">
            <Save :size="14" />{{ t("common.save") }}
          </button>
        </footer>
      </section>
    </div>

    <div v-if="poolModalMode" class="browser-modal-backdrop" @click.self="closePoolModal">
      <section class="browser-modal browser-modal--pool">
        <header>
          <div>
            <h2>{{ poolModalMode === "create" ? t("settings.browserProfiles.pool.modal.createTitle") : t("settings.browserProfiles.pool.modal.editTitle") }}</h2>
            <p>{{ t("settings.browserProfiles.pool.modal.subtitle") }}</p>
          </div>
          <button type="button" :disabled="isPoolSaving" @click="closePoolModal">
            <X :size="16" />
          </button>
        </header>

        <div class="browser-form-grid browser-form-grid--pool">
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.poolId") }}</span>
            <input v-model="poolForm.poolId" :disabled="poolModalMode === 'edit' || isPoolSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.displayName") }}</span>
            <input v-model="poolForm.displayName" :disabled="isPoolSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.field.enabled") }}</span>
            <select v-model="poolForm.enabled" :disabled="isPoolSaving">
              <option :value="true">{{ t("common.enabled") }}</option>
              <option :value="false">{{ t("common.disabled") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.strategy") }}</span>
            <select v-model="poolForm.selectionStrategy" :disabled="isPoolSaving">
              <option value="least_busy">{{ t("text.leastBusy") }}</option>
              <option value="round_robin">{{ t("text.roundRobin") }}</option>
              <option value="sticky_session">{{ t("text.stickySession") }}</option>
              <option value="manual_only">{{ t("text.manualOnly") }}</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.targetHosts") }}</span>
            <input v-model="poolForm.targetHosts" placeholder="ctrip.com, example.com" :disabled="isPoolSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.maxPerProfile") }}</span>
            <input v-model="poolForm.maxConcurrencyPerProfile" inputmode="numeric" :disabled="isPoolSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.maxTotal") }}</span>
            <input v-model="poolForm.maxConcurrencyTotal" inputmode="numeric" :placeholder="t('settings.browserProfiles.pool.placeholder.unlimited')" :disabled="isPoolSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.ttl") }}</span>
            <input v-model="poolForm.allocationTtlSeconds" inputmode="numeric" :disabled="isPoolSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.cooldown") }}</span>
            <input v-model="poolForm.cooldownSeconds" inputmode="numeric" :disabled="isPoolSaving" />
          </label>
          <label>
            <span>{{ t("settings.browserProfiles.pool.field.failureCooldown") }}</span>
            <input v-model="poolForm.failureCooldownSeconds" inputmode="numeric" :disabled="isPoolSaving" />
          </label>
          <label class="browser-form-check">
            <input v-model="poolForm.allowAttachOnly" type="checkbox" :disabled="isPoolSaving" />
            <span>{{ t("settings.browserProfiles.pool.field.allowAttachOnly") }}</span>
          </label>
          <label class="browser-form-check">
            <input v-model="poolForm.closeTargetsOnRelease" type="checkbox" :disabled="isPoolSaving" />
            <span>{{ t("settings.browserProfiles.pool.field.closeTargetsOnRelease") }}</span>
          </label>
          <label class="browser-form-check">
            <input v-model="poolForm.closeTargetsOnExpire" type="checkbox" :disabled="isPoolSaving" />
            <span>{{ t("settings.browserProfiles.pool.field.closeTargetsOnExpire") }}</span>
          </label>
        </div>

        <section class="browser-pool-picker">
          <h3>{{ t("settings.browserProfiles.pool.field.profiles") }}</h3>
          <div>
            <label v-for="profile in profiles" :key="profile.name">
              <input
                type="checkbox"
                :checked="poolProfileChecked(profile.name)"
                :disabled="isPoolSaving"
                @change="togglePoolProfile(profile.name)"
              />
              <span>{{ profile.name }}</span>
              <em>{{ profileMode(profile) }}</em>
            </label>
          </div>
        </section>

        <footer>
          <button type="button" :disabled="isPoolSaving" @click="closePoolModal">
            {{ t("common.cancel") }}
          </button>
          <button type="button" class="browser-settings-button--primary" :disabled="isPoolSaving || !poolForm.poolId.trim() || !poolForm.profileNames.length" @click="savePool">
            <Save :size="14" />{{ t("common.save") }}
          </button>
        </footer>
      </section>
    </div>
  </main>
</template>

<style scoped>
.browser-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: calc(100dvh - var(--shell-topbar-height));
  min-height: 0;
  padding: 12px 14px;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
}

.browser-settings-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
}

.browser-settings-head h1 {
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
}

.browser-settings-head p {
  margin: 3px 0 0;
  font-size: 12px;
}

.browser-settings-head p,
.browser-profile-detail p,
.browser-test-panel p,
.browser-danger-zone p,
.browser-modal p {
  color: var(--text-muted);
}

.browser-head-actions,
.browser-detail-actions,
.browser-test-actions,
.browser-row-actions,
.browser-modal footer {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.browser-head-actions {
  flex-wrap: nowrap;
}

.browser-settings-button,
.browser-profile-row button,
.browser-pool-row button,
.browser-detail-actions button,
.browser-test-actions button,
.browser-danger-zone button,
.browser-pool-detail button,
.browser-modal button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--surface-panel);
  color: var(--text-primary);
  font-size: 11px;
  line-height: 1;
  padding: 7px 10px;
}

.browser-settings-button--primary {
  border-color: color-mix(in srgb, var(--accent) 58%, var(--border-subtle));
  background: color-mix(in srgb, var(--accent) 22%, var(--surface-panel));
}

.browser-stat-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  flex: 0 0 auto;
  gap: 8px;
}

.browser-stat-strip article,
.browser-profile-table,
.browser-profile-detail,
.browser-pool-section,
.browser-modal {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-panel);
}

.browser-stat-strip article {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 50px;
  padding: 8px 10px;
}

.browser-stat-strip span,
.browser-profile-row--head,
.browser-profile-detail dt,
.browser-form-grid span {
  color: var(--text-muted);
  font-size: 10.5px;
}

.browser-stat-strip span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-stat-strip strong {
  color: var(--text-primary);
  font-size: 18px;
  line-height: 1.05;
}

.browser-settings-alert,
.browser-settings-message {
  margin: 0;
  border-radius: 7px;
  padding: 8px 10px;
}

.browser-settings-alert {
  background: color-mix(in srgb, var(--danger) 14%, transparent);
  color: var(--danger);
}

.browser-settings-message {
  background: color-mix(in srgb, var(--success) 14%, transparent);
  color: var(--success);
}

.browser-settings-workspace {
  flex: 1 1 auto;
  display: grid;
  grid-template-areas:
    "profiles detail"
    "pools detail";
  grid-template-columns: minmax(0, 1fr) minmax(400px, 0.44fr);
  grid-template-rows: minmax(250px, 0.88fr) minmax(260px, 0.74fr);
  gap: 10px;
  align-items: stretch;
  min-height: 0;
}

.browser-profile-table {
  grid-area: profiles;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

.browser-profile-row {
  display: grid;
  grid-template-columns: minmax(124px, 1.25fr) 68px 84px minmax(84px, 0.85fr) 72px 48px 64px;
  width: 100%;
  gap: 6px;
  align-items: center;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-primary);
  font-size: 11.5px;
  padding: 7px 9px;
  text-align: left;
}

.browser-profile-row--head,
.browser-pool-row--head {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface-panel);
}

.browser-profile-row > :nth-child(5),
.browser-profile-row > :nth-child(6) {
  display: none;
}

.browser-profile-row.selected {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.browser-profile-row[role="button"],
.browser-pool-row[role="button"] {
  cursor: pointer;
}

.browser-profile-row[role="button"]:focus-visible,
.browser-pool-row[role="button"]:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 72%, transparent);
  outline-offset: -2px;
}

.browser-profile-row strong,
.browser-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.browser-profile-row strong {
  font-size: 12px;
  font-weight: 650;
}

.browser-profile-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-pool-section {
  grid-area: pools;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  align-items: stretch;
  height: 100%;
  min-height: 0;
  margin: 0;
  padding: 10px;
  overflow: hidden;
}

.browser-pool-section--wide {
  grid-template-columns: 1fr;
}

.browser-pool-section > header {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.browser-pool-section h2,
.browser-pool-section p,
.browser-pool-detail dl {
  margin: 0;
}

.browser-pool-section h2,
.browser-detail-head h2 {
  color: var(--text-primary);
  font-size: 16px;
  line-height: 1.2;
}

.browser-pool-section p,
.browser-pool-detail dt,
.browser-pool-picker em {
  color: var(--text-muted);
}

.browser-pool-table {
  min-height: 0;
  overflow: auto;
}

.browser-pool-row {
  display: grid;
  grid-template-columns: minmax(118px, 1fr) minmax(96px, 0.9fr) minmax(90px, 0.8fr) 64px 50px 72px 66px;
  width: 100%;
  gap: 6px;
  align-items: center;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-primary);
  font-size: 11.5px;
  padding: 6px 0;
  text-align: left;
}

.browser-pool-row > :nth-child(4) {
  display: none;
}

.browser-pool-row.selected {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.browser-pool-row--head {
  color: var(--text-muted);
  font-size: 10.5px;
}

.browser-pool-row span,
.browser-pool-row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-pool-row strong {
  font-size: 12px;
  font-weight: 650;
}

.browser-pool-detail {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  border-top: 1px solid var(--border-subtle);
  padding-top: 8px;
  overflow: hidden;
}

.browser-pool-detail-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.browser-pool-detail-head strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
  font-size: 12.5px;
  font-weight: 650;
}

.browser-pool-detail dl {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px 10px;
}

.browser-pool-detail dl div:last-child {
  grid-column: auto;
}

.browser-pool-detail dd {
  min-width: 0;
  margin: 3px 0 0;
  color: var(--text-primary);
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-allocation-list {
  display: grid;
  gap: 6px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 7px;
}

.browser-allocation-list h3,
.browser-allocation-list p {
  margin: 0;
}

.browser-allocation-list h3 {
  color: var(--text-primary);
  font-size: 12px;
}

.browser-allocation-list p {
  color: var(--text-muted);
  font-size: 12px;
}

.browser-allocation-list article {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  padding: 6px 8px;
}

.browser-allocation-list span {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.browser-allocation-list strong,
.browser-allocation-list small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-allocation-list small {
  color: var(--text-muted);
}

.browser-allocation-list button {
  width: 28px;
  height: 28px;
  padding: 0;
}

.browser-pool-detail-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.browser-pool-detail-actions button {
  justify-self: end;
}

.browser-pool-detail-actions button:last-child {
  justify-self: end;
  border-color: color-mix(in srgb, var(--danger) 55%, var(--border-subtle));
  color: var(--danger);
}

.browser-row-actions {
  justify-content: flex-end;
  flex-wrap: nowrap;
}

.browser-row-actions button {
  width: 28px;
  height: 28px;
  padding: 0;
}

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.browser-status::before {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--warning);
  content: "";
}

.browser-status--success::before {
  background: var(--success);
}

.browser-status--danger::before {
  background: var(--danger);
}

.browser-profile-detail {
  grid-area: detail;
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
  padding: 10px;
  overflow: auto;
}

.browser-detail-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}

.browser-detail-head h2,
.browser-modal h2 {
  margin: 0;
}

.browser-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px 10px;
  margin: 0;
}

.browser-detail-grid div {
  min-width: 0;
}

.browser-detail-grid dd {
  min-width: 0;
  margin: 2px 0 0;
  color: var(--text-primary);
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-test-panel,
.browser-danger-zone {
  border-top: 1px solid var(--border-subtle);
  padding-top: 7px;
}

.browser-test-panel h3,
.browser-danger-zone h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 12px;
}

.browser-test-actions label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 142px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  padding: 5px 7px;
}

.browser-test-actions input,
.browser-form-grid input,
.browser-form-grid select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--surface-base);
  color: var(--text-primary);
  padding: 8px 9px;
}

.browser-test-actions label input {
  border: 0;
  padding: 0;
  background: transparent;
}

.browser-danger-zone {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.browser-danger-zone button {
  border-color: color-mix(in srgb, var(--danger) 55%, var(--border-subtle));
  color: var(--danger);
}

.browser-settings-empty {
  padding: 18px;
  color: var(--text-muted);
  text-align: center;
}

.browser-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.48);
}

.browser-modal {
  width: min(960px, 100%);
  max-height: calc(100dvh - 48px);
  overflow: auto;
  padding: 16px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.35);
}

.browser-modal header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  margin-bottom: 14px;
}

.browser-modal header button {
  width: 32px;
  height: 32px;
  padding: 0;
}

.browser-form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.browser-form-grid--pool {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.browser-form-grid label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.browser-form-check {
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  align-content: center;
}

.browser-form-check input {
  width: auto;
}

.browser-modal footer {
  justify-content: flex-end;
  margin-top: 16px;
}

.browser-pool-picker {
  display: grid;
  gap: 10px;
  margin-top: 14px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
}

.browser-pool-picker h3 {
  margin: 0;
  font-size: 14px;
}

.browser-pool-picker > div {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.browser-pool-picker label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  padding: 8px 10px;
}

.browser-pool-picker span,
.browser-pool-picker em {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1420px) {
  .browser-settings-workspace {
    grid-template-columns: minmax(0, 1fr) minmax(360px, 0.48fr);
  }

  .browser-pool-section {
    grid-template-columns: 1fr;
  }

  .browser-pool-row {
    grid-template-columns: minmax(112px, 1fr) minmax(96px, 0.9fr) minmax(82px, 0.8fr) 64px 50px 72px 66px;
    padding: 7px 9px;
  }
}

@media (max-width: 1180px) {
  .browser-settings {
    height: auto;
    min-height: calc(100dvh - var(--shell-topbar-height));
    overflow: visible;
  }

  .browser-stat-strip,
  .browser-settings-workspace,
  .browser-pool-section {
    grid-template-columns: 1fr;
  }

  .browser-settings-workspace {
    grid-template-areas:
      "profiles"
      "detail"
      "pools";
    grid-template-rows: auto auto auto;
  }

  .browser-pool-detail dl {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .browser-profile-row {
    grid-template-columns: minmax(120px, 1fr) 100px 110px 72px;
  }

  .browser-profile-row span:nth-child(4),
  .browser-profile-row span:nth-child(5),
  .browser-profile-row span:nth-child(6),
  .browser-profile-row span:nth-child(7),
  .browser-profile-row span:nth-child(8),
  .browser-profile-row--head span:nth-child(4),
  .browser-profile-row--head span:nth-child(5),
  .browser-profile-row--head span:nth-child(6),
  .browser-profile-row--head span:nth-child(7),
  .browser-profile-row--head span:nth-child(8) {
    display: none;
  }

  .browser-form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .browser-pool-row {
    grid-template-columns: minmax(120px, 1fr) minmax(150px, 1fr) 100px 72px;
  }

  .browser-pool-row span:nth-child(3),
  .browser-pool-row span:nth-child(5),
  .browser-pool-row span:nth-child(6),
  .browser-pool-row--head span:nth-child(3),
  .browser-pool-row--head span:nth-child(5),
  .browser-pool-row--head span:nth-child(6) {
    display: none;
  }
}

@media (max-width: 720px) {
  .browser-settings-head,
  .browser-detail-grid,
  .browser-form-grid {
    grid-template-columns: 1fr;
  }

  .browser-profile-row {
    grid-template-columns: minmax(0, 1fr) 92px 80px 64px;
  }

  .browser-pool-row,
  .browser-pool-picker > div,
  .browser-pool-detail dl {
    grid-template-columns: 1fr;
  }

  .browser-profile-row span:nth-child(4),
  .browser-profile-row--head span:nth-child(4) {
    display: none;
  }
}
</style>
