<script setup lang="ts">
import { AlertTriangle, ArrowRight, Copy, GitBranch, KeyRound, MessageCircle, Plus, Power, RefreshCcw, Save, Trash2 } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import DataTable from "@/shared/ui/DataTable.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { useI18n } from "@/shared/i18n";
import {
  listSettingsResources,
} from "../api";
import {
  deleteChannelProfile,
  getAccessOverviewForChannelSettings,
  getChannelProfile,
  listChannelProfiles,
  setChannelProfileEnabled,
  upsertChannelProfile,
  type AccessCredentialBindingPayload,
  type AccessCredentialRequirementPayload,
  type AccessOverviewPayload,
  type ChannelProfileApiPayload,
  type ChannelProfileWritePayload,
} from "../ownerApis/channelProfiles";

type JsonRecord = Record<string, unknown>;
type TableRow = Record<string, string | number | null>;

interface SettingsResourceSummaryPayload {
  id?: string;
  resource_id?: string;
  title?: string;
  display_name?: string;
  status?: string;
  enabled?: boolean;
  source?: string | null;
  version?: string | number | null;
  updated_at?: string | null;
  metadata?: JsonRecord;
  payload?: JsonRecord;
  effective_config?: JsonRecord;
  resolution?: {
    value?: unknown;
    source?: { kind?: string; name?: string };
    sources?: Array<{ kind?: string; name?: string; version_id?: string | null }>;
    override_trace?: unknown[];
  };
}

interface SettingsResourceDetailPayload extends SettingsResourceSummaryPayload {
  title?: string;
  payload?: JsonRecord;
  versions?: JsonRecord[];
  validation?: { status?: string; checks?: { rows?: JsonRecord[] } };
  audit?: { recent_changes?: { rows?: JsonRecord[]; total?: number } };
}

interface SettingsResourcePagePayload {
  title?: string;
  description?: string;
  status?: string;
  resources?: SettingsResourceSummaryPayload[];
  list?: { total?: number };
  detail?: SettingsResourceDetailPayload | null;
}

interface ChannelCredentialSlotRow {
  kind: "slot" | "empty" | "not_reported";
  accountIndex: number;
  accountId: string;
  slot: string;
  displayName: string;
  provider: string;
  expectedKind: string;
  required: boolean;
  bindingId: string;
  ready: boolean;
  status: string;
  setup: string;
  reason: string;
  requirementId: string;
}

interface CredentialCompatibility {
  compatible: boolean;
  reason: string;
}

const settingsPage = ref<SettingsResourcePagePayload | null>(null);
const selectedDetail = ref<SettingsResourceDetailPayload | null>(null);
const selectedResourceId = ref<string | null>(null);
const isLoading = ref(false);
const detailLoading = ref(false);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const ownerActionError = ref<string | null>(null);
const ownerActionMessage = ref<string | null>(null);
const ownerActionLoading = ref(false);
const editMode = ref<"create" | "update">("update");
const editorText = ref("");
const accessOverview = ref<AccessOverviewPayload | null>(null);
const accessError = ref<string | null>(null);
const { t } = useI18n();

const resources = computed(() => settingsPage.value?.resources ?? []);
const channelColumns = computed(() => [
  { key: "Name", label: t("settings.channelProfiles.table.name") },
  { key: "Channel ID", label: t("settings.channelProfiles.table.channelId") },
  { key: "Type", label: t("settings.channelProfiles.table.type") },
  { key: "Status", label: t("settings.channelProfiles.table.status") },
  { key: "Source", label: t("settings.channelProfiles.table.source") },
  { key: "Version", label: t("settings.channelProfiles.table.version") },
  { key: "Updated At", label: t("settings.channelProfiles.table.updatedAt") },
]);
const keyValueColumns = computed(() => [
  { key: "Key", label: t("settings.channelProfiles.table.key") },
  { key: "Value", label: t("settings.channelProfiles.table.value") },
]);
const resolutionColumns = computed(() => [
  { key: "Layer", label: t("settings.channelProfiles.table.layer") },
  { key: "Source", label: t("settings.channelProfiles.table.source") },
  { key: "Version", label: t("settings.channelProfiles.table.version") },
]);
const selectedResource = computed(() =>
  resources.value.find((resource) => settingsResourceId(resource) === selectedResourceId.value)
  ?? resources.value[0]
  ?? null,
);
const activeDetail = computed(() => selectedDetail.value ?? selectedResource.value);
const selectedConfig = computed(() => activeDetail.value ? resourceConfig(activeDetail.value) : {});
const channelRows = computed<TableRow[]>(() =>
  resources.value.map((resource) => {
    const config = resourceConfig(resource);
    return {
      Name: textValue(resource.display_name, settingsResourceId(resource)),
      "Channel ID": settingsResourceId(resource),
      Type: textValue(config.channel_kind, textValue(config.channel_type, "-")),
      Status: resource.enabled === false ? t("common.disabled") : statusLabel(textValue(resource.status, "ready")),
      Source: sourceLabel(textValue(resource.source, resource.resolution?.source?.name ?? "settings_application")),
      Version: textValue(resource.version, "-"),
      "Updated At": formatTime(resource.updated_at),
    };
  }),
);
const effectiveRows = computed<TableRow[]>(() =>
  Object.entries(selectedConfig.value).slice(0, 14).map(([key, value]) => ({
    Key: key,
    Value: formatValue(value),
  })),
);
const resolutionRows = computed<TableRow[]>(() =>
  (activeDetail.value?.resolution?.sources ?? []).map((source, index) => ({
    Layer: index === 0 ? t("settings.channelProfiles.resolution.primary") : t("settings.channelProfiles.resolution.source"),
    Source: sourceLabel(textValue(source.name, textValue(source.kind, "settings"))),
    Version: textValue(source.version_id, "-"),
  })),
);
const totalResources = computed(() => settingsPage.value?.list?.total ?? resources.value.length);
const selectedChannelType = computed(() => selectedResourceId.value ?? textValue(activeDetail.value?.resource_id));
const canWriteOwnerProfile = computed(() => !ownerActionLoading.value && editorText.value.trim().length > 0);
const ownerFormTitle = computed(() => editMode.value === "create" ? t("settings.channelProfiles.form.createTitle") : t("settings.channelProfiles.form.updateTitle"));
const accessCredentialBindings = computed(() => accessOverview.value?.credential_bindings ?? []);
const accessCredentialRequirements = computed(() => accessOverview.value?.credential_requirements ?? []);
const selectedCredentialRows = computed(() => credentialSlotRowsForConfig(selectedConfig.value, accessCredentialRequirements.value));
const credentialSlotCount = computed(() => selectedCredentialRows.value.filter((row) => row.kind === "slot").length);
const credentialRequirementState = computed(() => {
  const accounts = channelAccountsFromConfig(selectedConfig.value);
  if (!accounts.length) return "no-accounts";
  if (selectedCredentialRows.value.some((row) => row.kind === "not_reported")) return "not-reported";
  if (credentialSlotCount.value === 0) return "empty";
  if (selectedCredentialRows.value.some((row) => row.kind === "slot" && !row.ready)) return "attention";
  return "ready";
});
const credentialRequirementNote = computed(() => {
  if (credentialRequirementState.value === "no-accounts") return t("settings.channelProfiles.credential.noAccounts");
  if (credentialRequirementState.value === "not-reported") return t("settings.channelProfiles.credential.notReported");
  if (credentialRequirementState.value === "empty") return t("settings.channelProfiles.credential.empty");
  if (accessError.value) return t("settings.channelProfiles.credential.accessUnavailable", { error: accessError.value });
  if (credentialRequirementState.value === "attention") return t("settings.channelProfiles.credential.attention");
  return t("settings.channelProfiles.credential.ready");
});

onMounted(() => {
  void loadChannelProfiles();
});

async function loadChannelProfiles(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [profiles, overlay, access] = await Promise.all([
      listChannelProfiles(),
      loadSettingsOverlay(),
      loadAccessOverview(),
    ]);
    accessOverview.value = access;
    const payload = buildChannelProfilePage(profiles, overlay);
    settingsPage.value = payload;
    const first = profiles[0] ?? null;
    selectedResourceId.value = first ? first.channel_type : null;
    selectedDetail.value = first ? channelProfileToDetail(first) : null;
    if (selectedDetail.value) {
      resetEditorFromDetail(selectedDetail.value);
    } else {
      beginCreateProfile();
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    settingsPage.value = null;
    selectedDetail.value = null;
  } finally {
    isLoading.value = false;
  }
}

async function loadAccessOverview(): Promise<AccessOverviewPayload | null> {
  accessError.value = null;
  try {
    return await getAccessOverviewForChannelSettings();
  } catch (error) {
    accessError.value = error instanceof Error ? error.message : String(error);
    return null;
  }
}

async function selectResource(resource: SettingsResourceSummaryPayload): Promise<void> {
  const resourceId = settingsResourceId(resource);
  selectedResourceId.value = resourceId;
  detailLoading.value = true;
  detailError.value = null;
  try {
    selectedDetail.value = channelProfileToDetail(await getChannelProfile(resourceId));
    editMode.value = "update";
    resetEditorFromDetail(selectedDetail.value);
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

function selectChannelRow(row: unknown): void {
  const channelId = textValue(tableCellValue(row, "Channel ID"), "");
  const resource = resources.value.find((item) => settingsResourceId(item) === channelId);
  if (resource) void selectResource(resource);
}

async function handleOwnerActionCompleted(resourceId = selectedResourceId.value): Promise<void> {
  if (!resourceId) {
    await loadChannelProfiles();
    return;
  }
  await loadChannelProfiles();
  selectedResourceId.value = resourceId;
  try {
    selectedDetail.value = channelProfileToDetail(await getChannelProfile(resourceId));
    resetEditorFromDetail(selectedDetail.value);
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  }
}

function beginCreateProfile(): void {
  editMode.value = "create";
  selectedResourceId.value = null;
  selectedDetail.value = null;
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  editorText.value = JSON.stringify(
    {
      channel_type: "webhook",
      enabled: true,
      capabilities: {},
      accounts: [],
      metadata: {},
    },
    null,
    2,
  );
}

function resetEditorFromDetail(detail: SettingsResourceSummaryPayload): void {
  editMode.value = "update";
  editorText.value = JSON.stringify(channelWritePayloadFromConfig(resourceConfig(detail)), null, 2);
}

async function submitOwnerProfile(): Promise<void> {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  if (!canWriteOwnerProfile.value) return;
  ownerActionLoading.value = true;
  try {
    const payload = parseEditorPayload();
    assertCredentialBindingsSaveable(payload);
    const channelType = textValue(payload.channel_type, selectedChannelType.value).trim().toLowerCase();
    if (!channelType) {
      throw new Error(t("settings.channelProfiles.error.channelTypeRequired"));
    }
    const saved = await upsertChannelProfile(channelType, payload);
    ownerActionMessage.value = t("settings.channelProfiles.notice.saved", { channel: saved.channel_type });
    editMode.value = "update";
    await handleOwnerActionCompleted(saved.channel_type);
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function toggleOwnerEnabled(enabled: boolean): Promise<void> {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  const channelType = selectedChannelType.value;
  if (!channelType) return;
  ownerActionLoading.value = true;
  try {
    const profile = await setChannelProfileEnabled(channelType, enabled);
    ownerActionMessage.value = t("settings.channelProfiles.notice.enabledChanged", {
      channel: profile.channel_type,
      status: enabled ? t("common.enabled") : t("common.disabled"),
    });
    await handleOwnerActionCompleted(profile.channel_type);
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

async function removeOwnerProfile(): Promise<void> {
  ownerActionError.value = null;
  ownerActionMessage.value = null;
  const channelType = selectedChannelType.value;
  if (!channelType) return;
  if (!window.confirm(t("settings.channelProfiles.confirm.delete", { channel: channelType }))) return;
  ownerActionLoading.value = true;
  try {
    await deleteChannelProfile(channelType);
    ownerActionMessage.value = t("settings.channelProfiles.notice.deleted", { channel: channelType });
    await loadChannelProfiles();
  } catch (error) {
    ownerActionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ownerActionLoading.value = false;
  }
}

function parseEditorPayload(): ChannelProfileWritePayload {
  let value: unknown;
  try {
    value = JSON.parse(editorText.value);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(t("settings.channelProfiles.error.invalidJson", { detail }));
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(t("settings.channelProfiles.error.payloadObject"));
  }
  return channelWritePayloadFromConfig(value as JsonRecord);
}

function channelWritePayloadFromConfig(config: JsonRecord): ChannelProfileWritePayload {
  return {
    channel_type: optionalText(config.channel_type ?? config.channel_kind),
    enabled: typeof config.enabled === "boolean" ? config.enabled : true,
    capabilities: objectValue(config.capabilities) ?? {},
    accounts: arrayOfRecords(config.accounts),
    metadata: objectValue(config.metadata) ?? {},
  };
}

async function loadSettingsOverlay(): Promise<SettingsResourcePagePayload | null> {
  try {
    return await listSettingsResources("channel-profiles", { limit: 1, offset: 0 }) as SettingsResourcePagePayload;
  } catch {
    return null;
  }
}

function buildChannelProfilePage(
  profiles: ChannelProfileApiPayload[],
  overlay: SettingsResourcePagePayload | null,
): SettingsResourcePagePayload {
  return {
    title: overlay?.title ?? t("settings.channelProfiles.title"),
    description: overlay?.description ?? t("settings.channelProfiles.subtitle"),
    status: overlay?.status ?? (profiles.length ? "ready" : "empty"),
    resources: profiles.map(channelProfileToResource),
    list: { total: profiles.length },
    detail: profiles[0] ? channelProfileToDetail(profiles[0]) : null,
  };
}

function channelProfileToResource(profile: ChannelProfileApiPayload): SettingsResourceSummaryPayload {
  const effectiveConfig = channelProfileConfig(profile);
  return {
    id: profile.channel_type,
    resource_id: profile.channel_type,
    display_name: profile.channel_type,
    status: profile.enabled ? "ready" : "disabled",
    enabled: profile.enabled,
    source: "channels_module_api",
    version: null,
    updated_at: null,
    metadata: {
      owner: "channels",
      account_count: profile.accounts.length,
    },
    payload: effectiveConfig,
    effective_config: effectiveConfig,
    resolution: ownerResolution(t("settings.channelProfiles.source.channelsApi"), effectiveConfig),
  };
}

function channelProfileToDetail(profile: ChannelProfileApiPayload): SettingsResourceDetailPayload {
  return {
    ...channelProfileToResource(profile),
    title: profile.channel_type,
    validation: {
      status: "owner-api",
      checks: {
        rows: [
          { Check: t("settings.channelProfiles.validation.truthSource"), Result: t("settings.channelProfiles.source.channelsApi") },
          { Check: t("settings.channelProfiles.validation.settingsRole"), Result: t("settings.channelProfiles.validation.governanceOverlayOnly") },
        ],
      },
    },
    audit: { recent_changes: { rows: [], total: 0 } },
    versions: [],
  };
}

function channelProfileConfig(profile: ChannelProfileApiPayload): JsonRecord {
  return {
    channel_type: profile.channel_type,
    channel_kind: profile.channel_type,
    enabled: profile.enabled,
    capabilities: profile.capabilities,
    accounts: profile.accounts,
    account_count: profile.accounts.length,
    metadata: profile.metadata,
  };
}

function credentialSlotRowsForConfig(
  config: JsonRecord,
  accessRequirements: AccessCredentialRequirementPayload[],
): ChannelCredentialSlotRow[] {
  const channelType = textValue(config.channel_type ?? config.channel_kind, selectedChannelType.value).toLowerCase();
  return channelAccountsFromConfig(config).flatMap((account, accountIndex) => {
    const accountId = textValue(account.account_id, `account-${accountIndex + 1}`);
    if (!("credential_requirements" in account)) {
      return [emptyCredentialSlotRow("not_reported", accountIndex, accountId)];
    }
    const requirementSet = objectValue(account.credential_requirements);
    const requirements = Array.isArray(requirementSet?.requirements)
      ? requirementSet.requirements.map(objectValue).filter((item): item is JsonRecord => item !== null)
      : [];
    if (!requirements.length) {
      return [emptyCredentialSlotRow("empty", accountIndex, accountId)];
    }
    const localBindings = objectValue(account.credential_bindings) ?? {};
    return requirements.map((requirement) => {
      const slot = objectValue(requirement.slot) ?? {};
      const slotName = textValue(slot.slot, textValue(requirement.requirement_id, "credential"));
      const requirementId = textValue(
        requirement.requirement_id,
        `channels.${channelType}.account:${accountId}.${slotName}`,
      );
      const accessRequirement = findAccessRequirement(accessRequirements, requirementId, channelType, accountId, slotName);
      const bindingId = textValue(
        accessRequirement?.binding_id,
        textValue(slot.binding_id, textValue(localBindings[slotName], "")),
      );
      const required = typeof accessRequirement?.required === "boolean"
        ? accessRequirement.required
        : slot.required !== false;
      const status = textValue(accessRequirement?.status, bindingId ? "bound" : required ? "missing" : "optional");
      const ready = typeof accessRequirement?.ready === "boolean"
        ? accessRequirement.ready
        : Boolean(bindingId) || !required;
      const setupHint = objectValue(accessRequirement?.setup_flow_hint) ?? objectValue(requirement.setup_flow_hint);
      return {
        kind: "slot",
        accountIndex,
        accountId,
        slot: slotName,
        displayName: textValue(accessRequirement?.display_name, textValue(slot.display_name, slotName)),
        provider: textValue(accessRequirement?.provider, textValue(requirement.provider, "-")),
        expectedKind: textValue(accessRequirement?.expected_kind, textValue(slot.expected_kind, "credential")),
        required,
        bindingId,
        ready,
        status,
        setup: formatSetupHint(setupHint),
        reason: textValue(accessRequirement?.reason, ""),
        requirementId,
      };
    });
  });
}

function emptyCredentialSlotRow(
  kind: "empty" | "not_reported",
  accountIndex: number,
  accountId: string,
): ChannelCredentialSlotRow {
  return {
    kind,
    accountIndex,
    accountId,
    slot: "-",
    displayName: kind === "empty"
      ? t("settings.channelProfiles.credential.noRequirement")
      : t("settings.channelProfiles.credential.requirementNotReported"),
    provider: "-",
    expectedKind: "-",
    required: false,
    bindingId: "",
    ready: kind === "empty",
    status: kind === "empty" ? "empty" : "not_reported",
    setup: "-",
    reason: "",
    requirementId: "",
  };
}

function channelAccountsFromConfig(config: JsonRecord): JsonRecord[] {
  return arrayOfRecords(config.accounts);
}

function findAccessRequirement(
  requirements: AccessCredentialRequirementPayload[],
  requirementId: string,
  channelType: string,
  accountId: string,
  slot: string,
): AccessCredentialRequirementPayload | null {
  return requirements.find((requirement) => requirement.requirement_id === requirementId)
    ?? requirements.find((requirement) => (
      requirement.consumer_module === "channels"
      && requirement.consumer_id === `channels.${channelType}.account:${accountId}`
      && requirement.slot === slot
    ))
    ?? null;
}

function updateSlotBinding(row: ChannelCredentialSlotRow, bindingId: string): void {
  if (row.kind !== "slot") return;
  const binding = accessCredentialBindings.value.find((item) => item.binding_id === bindingId);
  if (binding && !credentialBindingCompatibility(binding, row.expectedKind).compatible) return;
  let value: JsonRecord;
  try {
    const parsed = editorText.value.trim() ? JSON.parse(editorText.value) : {};
    value = objectValue(parsed) ?? {};
  } catch {
    value = { ...selectedConfig.value };
  }
  const accounts = arrayOfRecords(value.accounts).map((account) => ({ ...account }));
  const account = accounts[row.accountIndex] ?? { account_id: row.accountId };
  const credentialBindings = { ...(objectValue(account.credential_bindings) ?? {}) };
  if (bindingId) credentialBindings[row.slot] = bindingId;
  else delete credentialBindings[row.slot];
  account.credential_bindings = credentialBindings;
  accounts[row.accountIndex] = account;
  value.accounts = accounts;
  editorText.value = JSON.stringify(channelWritePayloadFromConfig(value), null, 2);
}

function handleSlotBindingChange(row: ChannelCredentialSlotRow, event: Event): void {
  const target = event.target instanceof HTMLSelectElement ? event.target : null;
  updateSlotBinding(row, target?.value ?? "");
}

function assertCredentialBindingsSaveable(payload: ChannelProfileWritePayload): void {
  const config = payload as unknown as JsonRecord;
  const rows = credentialSlotRowsForConfig(config, accessCredentialRequirements.value).filter((row) => row.kind === "slot");
  for (const row of rows) {
    if (row.required && !row.bindingId) {
      throw new Error(t("settings.channelProfiles.error.requiredBinding", {
        account: row.accountId,
        slot: row.slot,
      }));
    }
    if (!row.bindingId) continue;
    const binding = accessCredentialBindings.value.find((item) => item.binding_id === row.bindingId);
    if (!binding) continue;
    const compatibility = credentialBindingCompatibility(binding, row.expectedKind);
    if (!compatibility.compatible) {
      throw new Error(t("settings.channelProfiles.error.incompatibleBinding", {
        account: row.accountId,
        slot: row.slot,
        binding: row.bindingId,
        reason: compatibility.reason,
      }));
    }
  }
}

function credentialOptionsForRow(row: ChannelCredentialSlotRow): AccessCredentialBindingPayload[] {
  if (row.kind !== "slot") return [];
  return [...accessCredentialBindings.value].sort((left, right) => {
    const leftCompatible = credentialBindingCompatibility(left, row.expectedKind).compatible;
    const rightCompatible = credentialBindingCompatibility(right, row.expectedKind).compatible;
    if (leftCompatible !== rightCompatible) return leftCompatible ? -1 : 1;
    return credentialBindingRank(left) - credentialBindingRank(right)
      || left.binding_id.localeCompare(right.binding_id);
  });
}

function credentialBindingCompatibility(
  binding: AccessCredentialBindingPayload,
  expectedKind: string,
): CredentialCompatibility {
  const expected = normalizedCredentialText(expectedKind);
  if (!expected || expected === "credential" || expected === "any") return { compatible: true, reason: "" };
  const bindingKind = normalizedCredentialText(binding.binding_kind);
  const sourceKind = normalizedCredentialText(binding.source_kind);
  const compatibleKinds = credentialKindAliases(expected);
  if (compatibleKinds.has(bindingKind) || compatibleKinds.has(sourceKind)) return { compatible: true, reason: "" };
  if (["credential", "credential_binding", "secret", "token"].includes(bindingKind)) {
    return { compatible: true, reason: "" };
  }
  return {
    compatible: false,
    reason: t("settings.channelProfiles.error.bindingKindMismatch", {
      binding: binding.binding_id,
      actual: credentialBindingTypeLabel(binding),
      expected: credentialKindLabel(expected),
    }),
  };
}

function credentialKindAliases(expectedKind: string): Set<string> {
  const aliases: Record<string, string[]> = {
    api_key: ["api_key", "apikey", "bearer", "bearer_token", "token"],
    bearer_token: ["bearer", "bearer_token", "token", "api_key"],
    app_secret: ["app_secret", "secret"],
    webhook_secret: ["webhook_secret", "secret"],
    basic: ["basic", "basic_auth", "username_password"],
    oauth2_account: ["oauth2_account", "oauth_account", "oauth2", "oauth"],
    openid_connect: ["openid_connect", "oidc", "oauth2_account"],
    certificate: ["certificate", "cert"],
  };
  return new Set([expectedKind, ...(aliases[expectedKind] ?? [])]);
}

function credentialBindingRank(binding: AccessCredentialBindingPayload): number {
  const status = normalizedCredentialText(binding.status) || "active";
  if (["active", "ready", "enabled"].includes(status)) return 0;
  if (["degraded", "warning", "pending"].includes(status)) return 1;
  if (["disabled", "revoked", "blocked", "failed"].includes(status)) return 2;
  return 3;
}

function normalizedCredentialText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function credentialBindingTypeLabel(binding: AccessCredentialBindingPayload): string {
  const kind = textValue(binding.binding_kind, textValue(binding.source_kind, t("settings.channelProfiles.credential.generic")));
  const source = textValue(binding.source_kind, "");
  return source && source !== kind ? `${kind} / ${source}` : kind;
}

function credentialKindLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function formatCredentialBindingLabel(binding: AccessCredentialBindingPayload, expectedKind: string): string {
  const preview = binding.masked_preview ? ` · ${binding.masked_preview}` : "";
  const status = binding.status ? ` · ${statusLabel(binding.status)}` : "";
  const compatibility = credentialBindingCompatibility(binding, expectedKind);
  const suffix = compatibility.compatible ? "" : ` · ${compatibility.reason}`;
  return `${binding.binding_id} · ${credentialBindingTypeLabel(binding)}${preview}${status}${suffix}`;
}

function formatCredentialBindingHelp(row: ChannelCredentialSlotRow): string {
  if (row.kind !== "slot") return credentialRequirementNote.value;
  if (row.bindingId) {
    const binding = accessCredentialBindings.value.find((item) => item.binding_id === row.bindingId);
    if (!binding) return t("settings.channelProfiles.credential.missingInAccess", { binding: row.bindingId });
    const compatibility = credentialBindingCompatibility(binding, row.expectedKind);
    if (!compatibility.compatible) return compatibility.reason;
    return t("settings.channelProfiles.credential.boundHelp", {
      preview: binding.masked_preview ?? t("settings.channelProfiles.credential.secretHeldByAccess"),
      binding: binding.binding_id,
    });
  }
  if (row.required) return t("settings.channelProfiles.credential.requiredMissing");
  return t("settings.channelProfiles.credential.optionalUnbound");
}

function formatSetupHint(value: JsonRecord | null): string {
  if (!value) return "-";
  if (setupProviderMissing(value)) return t("settings.channelProfiles.credential.needsAccessSetupProvider");
  return setupKindLabel(textValue(value.flow_kind ?? value.kind, "-"));
}

function setupProviderMissing(value: JsonRecord): boolean {
  const metadata = objectValue(value.metadata);
  return metadata?.setup_provider_missing === true;
}

function ownerResolution(name: string, value: JsonRecord): SettingsResourceSummaryPayload["resolution"] {
  return {
    value,
    source: { kind: "owner_module", name },
    sources: [{ kind: "owner_module", name, version_id: null }],
    override_trace: [],
  };
}

function resourceConfig(resource: SettingsResourceSummaryPayload): JsonRecord {
  return objectValue(resource.effective_config)
    ?? objectValue(resource.payload)
    ?? objectValue(resource.resolution?.value)
    ?? {};
}

function settingsResourceId(resource: SettingsResourceSummaryPayload): string {
  return textValue(resource.resource_id, textValue(resource.id, "unknown"));
}

function objectValue(value: unknown): JsonRecord | null {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as JsonRecord;
  return null;
}

function arrayOfRecords(value: unknown): JsonRecord[] {
  return Array.isArray(value)
    ? value.map(objectValue).filter((item): item is JsonRecord => item !== null)
    : [];
}

function optionalText(value: unknown): string | null {
  const text = textValue(value, "");
  return text || null;
}

function tableCellValue(row: unknown, key: string): unknown {
  if (!row || typeof row !== "object") return null;
  if ("cells" in row && row.cells && typeof row.cells === "object") {
    return (row.cells as Record<string, unknown>)[key];
  }
  return (row as Record<string, unknown>)[key];
}

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function statusLabel(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const keys: Record<string, string> = {
    active: "common.active",
    disabled: "common.disabled",
    enabled: "common.enabled",
    empty: "settings.channelProfiles.status.empty",
    owner_api: "settings.channelProfiles.status.ownerApi",
    ready: "common.ready",
    unknown: "status.unknown",
  };
  const key = keys[normalized];
  return key ? t(key) : value;
}

function credentialStatusLabel(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const keys: Record<string, string> = {
    bound: "settings.channelProfiles.credential.status.bound",
    disabled: "common.disabled",
    empty: "settings.channelProfiles.credential.status.empty",
    missing: "settings.channelProfiles.credential.status.missing",
    not_reported: "settings.channelProfiles.credential.status.notReported",
    optional: "settings.channelProfiles.credential.status.optional",
    ready: "common.ready",
  };
  const key = keys[normalized];
  return key ? t(key) : value;
}

function sourceLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  const keys: Record<string, string> = {
    "channels module api": "settings.channelProfiles.source.channelsApi",
    channels_module_api: "settings.channelProfiles.source.channelsApi",
    settings: "nav.settings",
    settings_application: "settings.channelProfiles.source.settingsApplication",
  };
  const key = keys[normalized];
  return key ? t(key) : value;
}

function setupKindLabel(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const keys: Record<string, string> = {
    manual: "settings.channelProfiles.credential.setupManual",
    browser_oauth: "settings.channelProfiles.credential.setupBrowserOauth",
    device_code: "settings.channelProfiles.credential.setupDeviceCode",
  };
  const key = keys[normalized];
  return key ? t(key) : value;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatTime(value: unknown): string {
  const raw = textValue(value, "");
  if (!raw) return "-";
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
}
</script>

<template>
  <main class="settings-module channel-settings scroll-area">
    <header class="channel-page-header">
      <div>
        <p>{{ t("nav.settings") }} / <strong>{{ t("settings.channelProfiles.title") }}</strong></p>
        <h1>{{ textValue(activeDetail?.display_name, textValue(activeDetail?.title, t("settings.channelProfiles.title"))) }} <span><i class="channel-status-dot" />{{ statusLabel(textValue(activeDetail?.status, settingsPage?.status ?? "unknown")) }}</span></h1>
        <div class="channel-id">{{ t("settings.channelProfiles.field.id") }}: <code>{{ selectedResourceId ?? "-" }}</code><Copy :size="13" /></div>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="beginCreateProfile">
          <Plus :size="14" /> {{ t("settings.channelProfiles.action.new") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadChannelProfiles">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section v-if="loadError" class="settings-panel">
      <p class="settings-tone-danger">{{ loadError }}</p>
    </section>

    <section class="channel-layout">
      <aside class="settings-panel channel-picker">
        <label><MessageCircle :size="14" /><input disabled :placeholder="t('settings.channelProfiles.searchPlaceholder')" /></label>
        <select disabled><option>{{ t("settings.channelProfiles.ownerProfiles") }}</option></select>
        <div class="channel-list">
          <button
            v-for="resource in resources"
            :key="settingsResourceId(resource)"
            :class="{ active: settingsResourceId(resource) === selectedResourceId }"
            type="button"
            @click="selectResource(resource)"
          >
            <span><MessageCircle :size="18" /></span>
            <strong>{{ textValue(resource.display_name, settingsResourceId(resource)) }}<small>{{ settingsResourceId(resource) }}</small></strong>
            <em>{{ resource.enabled === false ? t("common.disabled") : statusLabel(textValue(resource.status, "ready")) }}</em>
          </button>
        </div>
        <p class="channel-owner-note">{{ t("settings.channelProfiles.ownerNote") }}</p>
      </aside>

      <div class="channel-workspace">
        <section class="settings-panel">
          <div class="settings-panel-heading">
            <h2>{{ t("settings.channelProfiles.title") }}</h2>
            <span>{{ isLoading ? t("common.loading") : `${channelRows.length} / ${totalResources}` }}</span>
          </div>
          <DataTable
            :columns="channelColumns"
            :rows="channelRows"
            section-id="channel-profiles"
            clickable-rows
            @row-click="selectChannelRow"
          />
        </section>

        <section v-if="!isLoading && !resources.length && editMode !== 'create'" class="settings-panel settings-empty-state">
          <MessageCircle :size="24" />
          <h2>{{ t("settings.channelProfiles.empty.title") }}</h2>
          <p>{{ t("settings.channelProfiles.empty.body") }}</p>
        </section>

        <section v-else class="channel-top-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h2>{{ t("settings.channelProfiles.section.effectiveConfig") }}</h2></div>
            <DataTable :columns="keyValueColumns" :rows="effectiveRows" section-id="channel-effective-config" />
            <p v-if="detailLoading">{{ t("settings.channelProfiles.loadingDetail") }}</p>
            <p v-if="detailError" class="settings-tone-danger">{{ detailError }}</p>
          </article>

          <article class="settings-panel channel-credentials">
            <div class="settings-panel-heading">
              <h2><KeyRound :size="15" /> {{ t("settings.channelProfiles.section.credentialSlots") }}</h2>
              <span>{{ accessError ? t("settings.channelProfiles.credential.accessDegraded") : t("settings.channelProfiles.credential.slotCount", { count: credentialSlotCount }) }}</span>
            </div>
            <p :class="['channel-credential-note', credentialRequirementState === 'attention' || credentialRequirementState === 'not-reported' ? 'is-warning' : '']">
              <AlertTriangle v-if="credentialRequirementState === 'attention' || credentialRequirementState === 'not-reported'" :size="13" />
              {{ credentialRequirementNote }}
            </p>
            <div class="channel-slot-list">
              <div
                v-for="row in selectedCredentialRows"
                :key="`${row.accountIndex}:${row.slot}:${row.kind}`"
                :class="['channel-slot-row', `is-${row.kind}`, row.ready ? 'is-ready' : 'is-blocked']"
              >
                <div class="channel-slot-main">
                  <strong>{{ row.displayName }}<small>{{ row.accountId }} / {{ row.slot }}</small></strong>
                  <span>{{ row.provider }} · {{ row.expectedKind }} · {{ row.required ? t("settings.channelProfiles.credential.required") : t("settings.channelProfiles.credential.optional") }}</span>
                </div>
                <div class="channel-slot-state">
                  <em>{{ credentialStatusLabel(row.status) }}</em>
                  <small>{{ t("settings.channelProfiles.credential.setup", { setup: row.setup }) }}</small>
                </div>
                <template v-if="row.kind === 'slot'">
                  <select
                    :value="row.bindingId"
                    :disabled="ownerActionLoading"
                    :aria-invalid="row.required && !row.bindingId"
                    @change="handleSlotBindingChange(row, $event)"
                  >
                    <option value="" :disabled="row.required">{{ t("settings.channelProfiles.credential.noBinding") }}</option>
                    <option
                      v-if="row.bindingId && !accessCredentialBindings.some((binding) => binding.binding_id === row.bindingId)"
                      :value="row.bindingId"
                    >
                      {{ t("settings.channelProfiles.credential.missingInAccess", { binding: row.bindingId }) }}
                    </option>
                    <option
                      v-for="binding in credentialOptionsForRow(row)"
                      :key="binding.binding_id"
                      :value="binding.binding_id"
                      :disabled="!credentialBindingCompatibility(binding, row.expectedKind).compatible"
                    >
                      {{ formatCredentialBindingLabel(binding, row.expectedKind) }}
                    </option>
                  </select>
                  <small :class="['channel-slot-help', row.ready ? '' : 'is-warning']">{{ formatCredentialBindingHelp(row) }}</small>
                </template>
              </div>
            </div>
          </article>

          <aside class="channel-side-stack">
            <article class="settings-panel">
              <div class="settings-panel-heading"><h2>{{ t("settings.channelProfiles.section.resolutionTrace") }}</h2></div>
              <DataTable :columns="resolutionColumns" :rows="resolutionRows" section-id="channel-resolution-trace" />
            </article>
            <article class="settings-panel">
              <div class="settings-panel-heading"><h2>{{ t("settings.channelProfiles.section.summary") }}</h2></div>
              <dl class="settings-kv">
                <div><dt>{{ t("settings.channelProfiles.table.status") }}</dt><dd>{{ statusLabel(textValue(activeDetail?.status, "unknown")) }}</dd></div>
                <div><dt>{{ t("settings.channelProfiles.field.enabled") }}</dt><dd>{{ activeDetail?.enabled === false ? t("common.no") : t("common.yes") }}</dd></div>
                <div><dt>{{ t("settings.channelProfiles.table.source") }}</dt><dd>{{ sourceLabel(textValue(activeDetail?.source, activeDetail?.resolution?.source?.name ?? "-")) }}</dd></div>
                <div><dt>{{ t("settings.channelProfiles.table.version") }}</dt><dd>{{ textValue(activeDetail?.version, "-") }}</dd></div>
                <div><dt>{{ t("settings.channelProfiles.field.overrides") }}</dt><dd>{{ activeDetail?.resolution?.override_trace?.length ?? 0 }}</dd></div>
                <div><dt>{{ t("settings.channelProfiles.field.versions") }}</dt><dd>{{ selectedDetail?.versions?.length ?? 0 }}</dd></div>
              </dl>
            </article>
            <article class="settings-panel channel-owner-editor">
              <div class="settings-panel-heading">
                <h2>{{ ownerFormTitle }}</h2>
                <span>{{ t("settings.channelProfiles.form.ownerApi") }}</span>
              </div>
              <textarea v-model="editorText" spellcheck="false" />
              <div class="settings-header-actions compact-actions">
                <UiButton size="sm" variant="primary" :disabled="!canWriteOwnerProfile" @click="submitOwnerProfile">
                  <Save :size="14" /> {{ t("settings.channelProfiles.action.save") }}
                </UiButton>
                <UiButton size="sm" variant="secondary" :disabled="ownerActionLoading || !selectedChannelType" @click="toggleOwnerEnabled(activeDetail?.enabled === false)">
                  <Power :size="14" /> {{ activeDetail?.enabled === false ? t("settings.channelProfiles.action.enable") : t("settings.channelProfiles.action.disable") }}
                </UiButton>
                <UiButton size="sm" variant="danger" :disabled="ownerActionLoading || !selectedChannelType" @click="removeOwnerProfile">
                  <Trash2 :size="14" /> {{ t("settings.channelProfiles.action.delete") }}
                </UiButton>
              </div>
              <p v-if="ownerActionMessage" class="settings-tone-success">{{ ownerActionMessage }}</p>
              <p v-if="ownerActionError" class="settings-tone-danger">{{ ownerActionError }}</p>
              <p class="channel-owner-note">{{ t("settings.channelProfiles.form.writeHint") }}</p>
            </article>
          </aside>
        </section>
      </div>
    </section>

    <footer class="settings-footer">
      <span><GitBranch :size="14" />{{ t("settings.channelProfiles.footer.governanceOverlay") }}</span>
      <span><MessageCircle :size="14" />{{ t("settings.channelProfiles.footer.truthSource") }}</span>
      <a>{{ t("settings.channelProfiles.footer.auditHistory") }} <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.channel-page-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.channel-page-header p {
  margin: 0 0 6px;
  color: var(--text-muted);
  font-size: 12px;
}

.channel-page-header h1,
.channel-page-header h1 span,
.channel-id {
  display: flex;
  align-items: center;
}

.channel-page-header h1 {
  gap: 10px;
  margin: 0;
  font-size: 20px;
}

.channel-page-header h1 span {
  gap: 6px;
  min-height: 21px;
  padding: 3px 8px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
  font-size: 11px;
}

.channel-id {
  gap: 8px;
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.channel-layout {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
  gap: 12px;
}

.channel-picker {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 10px;
}

.channel-picker label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.channel-picker input,
.channel-picker select {
  width: 100%;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.channel-picker input {
  min-height: 0;
  border: 0;
  outline: 0;
  background: transparent;
}

.channel-picker select {
  padding: 0 8px;
}

.channel-list {
  display: grid;
  gap: 4px;
}

.channel-list button {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 58px;
  padding: 8px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}

.channel-list button.active {
  background: var(--surface-active);
}

.channel-list button > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--color-blue);
  border-radius: var(--radius-2);
  color: var(--color-blue);
}

.channel-list strong {
  display: grid;
  gap: 3px;
  font-size: 12px;
}

.channel-list small {
  color: var(--text-muted);
  font-size: 11px;
}

.channel-list em {
  color: var(--color-success);
  font-size: 10.5px;
  font-style: normal;
}

.channel-owner-note {
  margin: 0;
  padding: 8px 2px 0;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.channel-workspace {
  min-width: 0;
}

.channel-top-grid,
.channel-mid-grid,
.channel-bottom-grid {
  display: grid;
  gap: 10px;
}

.channel-top-grid {
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.25fr) 340px;
}

.channel-side-stack {
  display: grid;
  gap: 10px;
  align-content: start;
  min-width: 0;
}

.channel-owner-editor {
  display: grid;
  gap: 10px;
}

.channel-owner-editor textarea {
  min-height: 190px;
  resize: vertical;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
}

.channel-credentials {
  min-width: 0;
}

.channel-credentials h2 {
  display: flex;
  align-items: center;
  gap: 6px;
}

.channel-credential-note {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  margin: 0 0 10px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.4;
}

.channel-credential-note.is-warning,
.channel-slot-help.is-warning {
  color: var(--color-warning);
}

.channel-slot-list {
  display: grid;
  gap: 8px;
}

.channel-slot-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px;
  gap: 8px;
  align-items: start;
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.channel-slot-row.is-slot {
  grid-template-columns: minmax(0, 1fr) 92px;
}

.channel-slot-row.is-empty,
.channel-slot-row.is-not_reported {
  border-style: dashed;
}

.channel-slot-row.is-blocked {
  border-color: color-mix(in srgb, var(--color-warning) 50%, var(--border-subtle));
}

.channel-slot-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.channel-slot-main strong {
  display: grid;
  gap: 2px;
  min-width: 0;
  font-size: 12px;
}

.channel-slot-main small,
.channel-slot-main span,
.channel-slot-state small,
.channel-slot-help {
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.35;
}

.channel-slot-state {
  display: grid;
  gap: 3px;
  justify-items: end;
  text-align: right;
}

.channel-slot-state em {
  color: var(--color-success);
  font-size: 10.5px;
  font-style: normal;
}

.channel-slot-row.is-blocked .channel-slot-state em {
  color: var(--color-warning);
}

.channel-slot-row select {
  grid-column: 1 / -1;
  width: 100%;
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-base);
  color: var(--text-primary);
  font-size: 11px;
}

.channel-slot-row select[aria-invalid="true"] {
  border-color: var(--color-warning);
}

.channel-slot-help {
  grid-column: 1 / -1;
}

.compact-actions {
  flex-wrap: wrap;
  justify-content: flex-start;
}

.channel-mid-grid {
  grid-template-columns: 1fr 1fr 330px;
  margin-top: 10px;
}

.channel-bottom-grid {
  grid-template-columns: 1fr 1.2fr;
  margin-top: 10px;
}

.settings-form-grid small {
  color: var(--text-muted);
  font-size: 10.5px;
}

.asset-list {
  display: grid;
  gap: 8px;
  margin: 10px 0 20px;
}

.asset-list span {
  display: flex;
  justify-content: space-between;
  min-height: 34px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-size: 11px;
}

.asset-list em {
  color: var(--text-muted);
  font-style: normal;
}

.binding-flow,
.mapping-grid {
  display: grid;
  align-items: center;
  gap: 10px;
}

.binding-flow {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
}

.binding-flow span {
  display: grid;
  gap: 4px;
  min-height: 70px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  font-size: 11px;
}

pre {
  min-height: 70px;
  margin: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10.5px;
  white-space: pre-wrap;
}

.binding-preview button,
.policy-stack button {
  min-height: 30px;
  margin-top: 10px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--color-accent);
  cursor: pointer;
}

.policy-stack {
  display: grid;
  gap: 10px;
}

.policy-stack article + article {
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

.policy-stack h3 {
  margin: 0 0 8px;
  font-size: 13px;
}

.mapping-preview {
  margin-top: 10px;
}

.mapping-grid {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) minmax(0, 1fr) auto minmax(0, 1fr);
}

.mapping-grid h3 {
  margin: 0 0 8px;
  font-size: 12px;
}

.channel-bottom-grid p {
  color: var(--text-muted);
  font-size: 11px;
}

.channel-status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-success);
}
</style>
