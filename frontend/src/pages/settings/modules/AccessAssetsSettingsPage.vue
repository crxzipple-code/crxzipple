<script setup lang="ts">
import { ArrowRight, GitBranch, KeyRound, LayoutList, PlayCircle, RefreshCcw, Save, Shield } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  executeAccessAction,
  getAccessAssetDetail,
  getAccessInventory,
  getAccessOverview,
  getAccessSetup,
  listAccessAssets,
  listAccessAudits,
  listAccessConsumers,
  type AccessActionResultPayload,
  type AccessAssetDetailPayload,
  type AccessAssetListPayload,
  type AccessAssetSummaryPayload,
  type AccessAuditPayload,
  type AccessAuditsPayload,
  type AccessConsumersPayload,
  type AccessConsumerBindingPayload,
  type AccessCredentialBindingPayload,
  type AccessInventoryTargetPayload,
  type AccessInventoryPayload,
  type AccessOwnerJsonRecord,
  type AccessOverviewPayload,
  type AccessReadinessPayload,
  type AccessSetupFlowPayload,
} from "../ownerApis/accessAssets";

type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

const { t } = useI18n();
const overview = ref<AccessOverviewPayload | null>(null);
const assetList = ref<AccessAssetListPayload | null>(null);
const consumersPayload = ref<AccessConsumersPayload | null>(null);
const auditsPayload = ref<AccessAuditsPayload | null>(null);
const inventory = ref<AccessInventoryPayload | null>(null);
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
const apiWarnings = ref<string[]>([]);

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

const audits = computed<AccessAuditPayload[]>(() =>
  auditsPayload.value?.audits ?? overview.value?.audits ?? [],
);

const inventoryTargets = computed(() => inventory.value?.targets ?? []);

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

const selectedAsset = computed(() => {
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

const selectedInventoryTarget = computed(() => {
  if (!selectedAsset.value) return inventoryTargets.value[0] ?? null;
  return inventoryTargets.value.find((target) => target.resource_id === selectedAsset.value?.asset_id)
    ?? inventoryTargets.value.find((target) => metadataList(target.metadata, "asset_ids", "assets").includes(selectedAsset.value?.asset_id ?? ""))
    ?? null;
});

const selectedSetupTarget = computed(() =>
  firstMissingRequirement(selectedInventoryTarget.value)
    ?? safeCredentialSourceRef(firstCredentialBinding.value)
    ?? firstReadinessRequirement(selectedReadiness.value)
    ?? selectedAsset.value?.asset_id
    ?? "",
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

const assets = computed(() =>
  assetSummaries.value.map((asset) => ({
    [t("table.name")]: textValue(asset.display_name, asset.asset_id),
    [t("settings.access.table.assetId")]: asset.asset_id,
    [t("table.kind")]: titleize(asset.asset_kind),
    [t("settings.access.table.governanceScope")]: textValue(asset.governance_scope, "-"),
    [t("table.status")]: statusLabel(asset.status),
    [t("table.readiness")]: readinessStatusLabel(asset.readiness),
    [t("table.requiredBy")]: (asset.consumer_modules ?? []).join(" / ") || "-",
    [t("settings.access.table.credentials")]: String(asset.credential_binding_count ?? 0),
    [t("table.source")]: "/ui/access/assets",
  })),
);

const assetColumns = computed(() => [
  t("table.name"),
  t("settings.access.table.assetId"),
  t("table.kind"),
  t("settings.access.table.governanceScope"),
  t("table.status"),
  t("table.readiness"),
  t("table.requiredBy"),
  t("settings.access.table.credentials"),
  t("table.source"),
]);

const consumerRows = computed(() => {
  const counts = new Map<string, number>();
  for (const consumer of consumerBindings.value) {
    const key = titleize(consumer.consumer_module || consumer.consumer_kind || "consumer");
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([type, count]) => ({
    [t("table.type")]: type,
    [t("table.count")]: String(count),
  }));
});

const usageRows = computed(() => [
  { [t("settings.access.table.metric")]: t("settings.access.metric.assets"), [t("table.value")]: String(totalCount(assetList.value?.counts, "total", assetSummaries.value.length)) },
  { [t("settings.access.table.metric")]: t("settings.access.metric.credentialBindings"), [t("table.value")]: String(totalCount(overview.value?.counts, "credential_bindings", credentialBindings.value.length)) },
  { [t("settings.access.table.metric")]: t("settings.access.consumers"), [t("table.value")]: String(consumerBindings.value.length) },
  { [t("settings.access.table.metric")]: t("table.target"), [t("table.value")]: String(inventory.value?.counts?.total ?? inventoryTargets.value.length) },
  { [t("settings.access.table.metric")]: t("settings.access.blockedChecks"), [t("table.value")]: String(inventory.value?.counts?.blocked ?? inventoryTargets.value.filter((target) => !target.ready).length) },
  { [t("settings.access.table.metric")]: t("settings.resource.auditLogs"), [t("table.value")]: String(audits.value.length) },
]);

const credentialBindingRows = computed(() =>
  selectedCredentialBindings.value.map((binding) => ({
    [t("table.binding")]: binding.binding_id,
    [t("table.kind")]: titleize(binding.binding_kind),
    [t("table.source")]: binding.source_ref ?? titleize(binding.source_kind),
    [t("table.status")]: statusLabel(binding.status),
    [t("settings.access.secret.preview")]: binding.masked_preview ?? t("settings.access.secret.serverSideOnly"),
  })),
);

const consumerBindingRows = computed(() =>
  selectedConsumerBindings.value.map((consumer) => ({
    [t("table.consumer")]: textValue(consumer.display_name, consumer.consumer_module ?? consumer.consumer_id ?? "-"),
    [t("table.usageType")]: titleize(consumer.consumer_kind),
    [t("table.status")]: consumer.enabled === false ? t("text.disabled") : statusLabel(consumer.status, t("text.enabled")),
    [t("table.requirements")]: requirementSetSummary(consumer.requirement_sets),
  })),
);

const inventoryRows = computed(() =>
  inventoryTargets.value.slice(0, 8).map((target) => ({
    [t("table.target")]: textValue(target.display_name, target.resource_id),
    [t("table.kind")]: titleize(target.resource_type),
    [t("table.status")]: target.ready ? t("text.ready") : t("text.blocked"),
    [t("table.setup")]: target.setup_available ? t("common.yes") : t("common.no"),
    [t("table.requiredBy")]: metadataList(
      target.metadata,
      "llm_profile_ids",
      "tool_ids",
      "channel_profiles",
      "usage_types",
    ).join(" / ") || "-",
  })),
);

const auditRows = computed(() =>
  audits.value.slice(0, 8).map((audit) => ({
    [t("table.time")]: formatTime(audit.created_at),
    [t("table.action")]: titleize(audit.action_type),
    [t("table.target")]: [audit.target_type, audit.target_id].filter(Boolean).join(":") || "-",
    [t("table.status")]: statusLabel(audit.status),
    [t("table.reason")]: textValue(audit.reason, "-"),
  })),
);

const connectedEndpointRows = computed(() => [
  { [t("table.endpoint")]: "GET /ui/access", [t("table.status")]: endpointStatus(overview.value), [t("table.details")]: "overview, readiness, credentials, setup sessions" },
  { [t("table.endpoint")]: "GET /ui/access/assets", [t("table.status")]: endpointStatus(assetList.value), [t("table.details")]: "asset list read model" },
  { [t("table.endpoint")]: "GET /ui/access/assets/{asset_id}", [t("table.status")]: selectedAssetDetail.value ? t("common.connected") : statusLabel(detailError.value, t("status.unknown")), [t("table.details")]: "selected asset detail" },
  { [t("table.endpoint")]: "GET /ui/access/consumers", [t("table.status")]: endpointStatus(consumersPayload.value), [t("table.details")]: "consumer bindings" },
  { [t("table.endpoint")]: "GET /ui/access/audits", [t("table.status")]: endpointStatus(auditsPayload.value), [t("table.details")]: "access action audit log" },
  { [t("table.endpoint")]: "GET /access/inventory", [t("table.status")]: inventory.value ? t("common.connected") : t("status.unknown"), [t("table.details")]: "runtime readiness inventory" },
  { [t("table.endpoint")]: "GET /access/setup", [t("table.status")]: setupFlow.value ? t("common.connected") : t("status.unknown"), [t("table.details")]: "setup flow preview" },
  { [t("table.endpoint")]: "POST /access/actions", [t("table.status")]: actionResult.value ? t("common.connected") : t("status.unknown"), [t("table.details")]: "begin_setup_session, register_* binding, dry-run" },
]);

const missingWriteRows = computed(() => [
  { [t("table.action")]: "Enable / disable access asset", [t("table.status")]: t("text.unsupported"), [t("table.endpoint")]: "-", [t("table.reason")]: "No Access owner endpoint in http.py or ui_http.py" },
  { [t("table.action")]: "Revoke / unregister credential binding", [t("table.status")]: t("text.unsupported"), [t("table.endpoint")]: "-", [t("table.reason")]: "Dangerous action markers exist, but service returns unsupported" },
  { [t("table.action")]: "Lease / checkout credential", [t("table.status")]: t("text.unsupported"), [t("table.endpoint")]: "-", [t("table.reason")]: "No lease API or read model contract exposed" },
  { [t("table.action")]: "Rotate secret / OAuth token", [t("table.status")]: t("text.unsupported"), [t("table.endpoint")]: "-", [t("table.reason")]: "No rotation workflow endpoint exposed" },
]);

const setupActionRows = computed(() =>
  (setupFlow.value?.actions ?? []).map((action) => ({
    [t("table.action")]: textValue(action.label, titleize(action.kind)),
    [t("table.kind")]: titleize(action.kind),
    [t("table.command")]: action.command?.join(" ") ?? action.path ?? action.url ?? action.env_vars?.join(", ") ?? "-",
  })),
);

const tags = computed(() => {
  const metadata = selectedAsset.value?.metadata;
  const rawTags = metadata?.tags;
  if (Array.isArray(rawTags)) {
    return rawTags.map((item) => String(item)).filter(Boolean).slice(0, 8);
  }
  return selectedAsset.value?.consumer_modules?.slice(0, 8) ?? [];
});

const readinessTone = computed<StatusTone>(() => {
  if (selectedReadiness.value?.ready) return "success";
  if (selectedReadiness.value?.status === "setup_needed") return "warning";
  if (selectedReadiness.value?.status === "unsupported") return "danger";
  if (apiWarnings.value.length || detailError.value) return "warning";
  return selectedAsset.value?.status === "active" ? "info" : "neutral";
});

const pageTone = computed<StatusTone>(() => {
  if (loadError.value) return "danger";
  if (overview.value?.degraded || assetList.value?.degraded || apiWarnings.value.length) return "warning";
  if (overview.value?.ready === false || inventory.value?.ready === false) return "warning";
  return "success";
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
const generatedAt = computed(() =>
  overview.value?.generated_at
  ?? assetList.value?.generated_at
  ?? selectedAsset.value?.updated_at
  ?? selectedAsset.value?.created_at
  ?? null,
);

onMounted(() => {
  void loadAccessAssets();
});

async function loadAccessAssets(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  detailError.value = null;
  setupError.value = null;
  actionError.value = null;
  apiWarnings.value = [];
  selectedAssetDetail.value = null;
  setupFlow.value = null;
  actionResult.value = null;
  try {
    const [overviewResult, assetsResult, consumersResult, auditsResult, inventoryResult] = await Promise.allSettled([
      getAccessOverview(),
      listAccessAssets(),
      listAccessConsumers(),
      listAccessAudits({ limit: 50 }),
      getAccessInventory({ include_ready: true, include_disabled: true }),
    ]);
    overview.value = settledValue(overviewResult, "GET /ui/access");
    assetList.value = settledValue(assetsResult, "GET /ui/access/assets");
    consumersPayload.value = settledValue(consumersResult, "GET /ui/access/consumers");
    auditsPayload.value = settledValue(auditsResult, "GET /ui/access/audits");
    inventory.value = settledValue(inventoryResult, "GET /access/inventory");
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
  setupFlow.value = null;
  actionResult.value = null;
  await loadSelectedAssetDetail();
}

async function prepareSetupFlow(): Promise<void> {
  const target = selectedSetupTarget.value.trim();
  if (!target) return;
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
      resource_kind: selectedInventoryTarget.value?.resource_type ?? "access_requirement",
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

function settledValue<T>(result: PromiseSettledResult<T>, label: string): T | null {
  if (result.status === "fulfilled") return result.value;
  apiWarnings.value.push(`${label}: ${errorMessage(result.reason)}`);
  return null;
}

function endpointStatus(payload: { degraded?: boolean; status?: string } | null): string {
  if (!payload) return t("status.unknown");
  if (payload.degraded) return t("text.degraded");
  return statusLabel(payload.status, t("common.connected"));
}

function readinessStatusLabel(readiness: AccessReadinessPayload | null | undefined): string {
  if (readiness?.ready) return t("text.ready");
  if (readiness) return statusLabel(readiness.status);
  return t("status.unknown");
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
    failed: t("status.failed"),
    ready: t("text.ready"),
    setup_needed: t("text.setupNeeded"),
    succeeded: t("status.success"),
    unsupported: t("text.unsupported"),
    waiting_for_user: t("text.waitingUser"),
  };
  return known[normalized] ?? titleize(normalized, fallback);
}

function firstMissingRequirement(target: AccessInventoryTargetPayload | null | undefined): string | null {
  if (!target) return null;
  for (const set of target.requirement_sets ?? []) {
    for (const check of set.checks ?? []) {
      if (check.ready === false && check.requirement) return check.requirement;
    }
  }
  return null;
}

function firstReadinessRequirement(readiness: AccessReadinessPayload | null | undefined): string | null {
  for (const check of readiness?.checks ?? []) {
    const requirement = textValue(check.requirement, "");
    if (requirement) return requirement;
  }
  return null;
}

function safeCredentialSourceRef(binding: AccessCredentialBindingPayload | null | undefined): string | null {
  const sourceRef = textValue(binding?.source_ref, "");
  if (sourceRef && sourceRef !== "***" && sourceRef !== "literal:***") return sourceRef;
  return null;
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

function totalCount(counts: AccessOwnerJsonRecord | undefined, key: string, fallback: number): number {
  const value = counts?.[key];
  return typeof value === "number" ? value : fallback;
}

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  return Array.from(new Set(values.map((value) => textValue(value, "")).filter(Boolean)));
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
</script>

<template>
  <main class="settings-module access-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>{{ t("settings.resource.accessAssets") }}</h1>
        <p>{{ t("settings.access.pageDescription") }}</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadAccessAssets">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section class="access-tabs-row">
      <div class="access-source-strip">
        <span><Shield :size="14" />Access owner: external credentials and provider authorization assets</span>
        <span><LayoutList :size="14" />GET /ui/access/assets</span>
        <span><KeyRound :size="14" />GET /access/inventory</span>
      </div>
    </section>

    <section class="settings-panel access-list">
      <div v-if="loadError" class="access-empty">{{ loadError }}</div>
      <div v-else-if="isLoading" class="access-empty">{{ t("settings.access.loading") }}</div>
      <DataTable
        v-else
        :columns="assetColumns"
        :rows="assets"
        section-id="access-assets"
      />
      <div v-if="assetSummaries.length" class="access-asset-picker">
        <button
          v-for="asset in assetSummaries"
          :key="asset.asset_id"
          type="button"
          :class="{ active: asset.asset_id === selectedAssetId }"
          @click="selectAsset(asset.asset_id)"
        >
          {{ asset.display_name ?? asset.asset_id }}
        </button>
      </div>
      <footer>{{ t("settings.access.results", { count: assets.length }) }}</footer>
    </section>

    <p v-if="apiWarnings.length && !loadError" class="settings-tone-warning access-api-warning">
      {{ apiWarnings.join(" / ") }}
    </p>

    <section v-if="selectedAsset" class="access-detail-layout">
      <div class="access-main-column">
        <article class="settings-panel access-editor">
          <aside class="access-editor-tabs">
            <button class="active" type="button">{{ t("settings.access.tab.overview") }}</button>
            <button type="button">{{ t("settings.access.tab.credentials") }}</button>
            <button type="button">{{ t("settings.access.tab.readiness") }}</button>
            <button type="button">{{ t("settings.resource.auditLogs") }}</button>
            <button type="button" disabled>{{ t("text.unsupported") }}</button>
          </aside>

          <div class="access-form">
            <header>
              <span class="asset-icon"><Shield :size="20" /></span>
              <div>
                <h2>
                  {{ selectedAsset.display_name ?? selectedAsset.asset_id }}
                  <em><StatusDot :tone="readinessTone" />{{ readinessLabel }}</em>
                  <span>{{ titleize(selectedAsset.asset_kind) }}</span>
                </h2>
                <p>{{ selectedReadiness?.reason ?? "Access owner control-plane record" }}</p>
              </div>
            </header>

            <div class="access-action-row">
              <UiButton size="sm" variant="secondary" :disabled="!selectedSetupTarget || setupLoading" @click="prepareSetupFlow">
                <PlayCircle :size="14" /> GET /access/setup
              </UiButton>
              <UiButton size="sm" variant="primary" :disabled="!selectedSetupTarget || actionLoading" @click="beginSetupSession">
                <PlayCircle :size="14" /> POST /access/actions
              </UiButton>
              <UiButton size="sm" variant="secondary" disabled>Enable</UiButton>
              <UiButton size="sm" variant="danger" disabled>Disable</UiButton>
              <UiButton size="sm" variant="danger" disabled>Revoke</UiButton>
              <UiButton size="sm" variant="secondary" disabled>Lease</UiButton>
            </div>
            <p v-if="setupError" class="settings-tone-danger">{{ setupError }}</p>
            <p v-else-if="actionError" class="settings-tone-danger">{{ actionError }}</p>
            <p v-else-if="actionResult" class="settings-tone-success">{{ actionResultLabel }}</p>

            <section class="asset-info-grid">
              <article>
                <dl class="settings-kv">
                  <div><dt>{{ t("settings.access.table.assetId") }}</dt><dd>{{ selectedAsset.asset_id }}</dd></div>
                  <div><dt>{{ t("settings.access.table.providerService") }}</dt><dd>{{ metadataText(selectedAsset.metadata, "provider", "service", "source") ?? "-" }}</dd></div>
                  <div><dt>{{ t("table.type") }}</dt><dd>{{ titleize(selectedAsset.asset_kind) }}</dd></div>
                  <div><dt>{{ t("settings.access.table.governanceScope") }}</dt><dd class="settings-tone-success">{{ selectedAsset.governance_scope ?? "-" }}</dd></div>
                  <div><dt>{{ t("settings.access.secret.storage") }}</dt><dd>{{ secretStorageLabel }}</dd></div>
                  <div><dt>{{ t("table.source") }}</dt><dd>/ui/access/assets/{{ selectedAsset.asset_id }}</dd></div>
                  <div><dt>{{ t("table.createdAt") }}</dt><dd>{{ formatTime(selectedAsset.created_at) }}</dd></div>
                  <div><dt>{{ t("table.updatedAt") }}</dt><dd>{{ formatTime(selectedAsset.updated_at) }}</dd></div>
                </dl>
              </article>

              <article>
                <h3>{{ t("settings.access.credentialBinding") }}</h3>
                <dl class="settings-kv">
                  <div><dt>{{ t("settings.access.table.bindings") }}</dt><dd>{{ selectedCredentialBindings.length }}</dd></div>
                  <div><dt>{{ t("table.source") }}</dt><dd>{{ firstCredentialBinding?.source_kind ?? "-" }}</dd></div>
                  <div><dt>{{ t("settings.access.secret.preview") }}</dt><dd>{{ credentialPreview }}</dd></div>
                  <div><dt>{{ t("settings.access.secret.policy") }}</dt><dd>{{ formatJsonSummary(selectedAssetDetail?.secret_policy) }}</dd></div>
                </dl>
              </article>

              <article>
                <h3>{{ t("settings.access.readiness") }}</h3>
                <dl class="settings-kv">
                  <div><dt>{{ t("table.status") }}</dt><dd>{{ readinessLabel }}</dd></div>
                  <div><dt>{{ t("settings.access.table.setupAvailable") }}</dt><dd>{{ selectedReadiness?.setup_available ? t("common.yes") : t("common.no") }}</dd></div>
                  <div><dt>{{ t("settings.access.table.checks") }}</dt><dd>{{ selectedReadiness?.checks?.length ?? 0 }}</dd></div>
                  <div><dt>{{ t("table.reason") }}</dt><dd>{{ detailError ?? selectedReadiness?.reason ?? "-" }}</dd></div>
                </dl>
              </article>

              <article>
                <h3>Setup Flow</h3>
                <dl class="settings-kv">
                  <div><dt>{{ t("table.target") }}</dt><dd>{{ selectedSetupTarget || "-" }}</dd></div>
                  <div><dt>{{ t("table.kind") }}</dt><dd>{{ titleize(setupFlow?.kind, setupLoading ? t("common.loading") : "-") }}</dd></div>
                  <div><dt>{{ t("table.details") }}</dt><dd>{{ setupFlowSummary }}</dd></div>
                </dl>
              </article>
            </section>
          </div>
        </article>

        <section class="access-support-grid">
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>{{ t("settings.access.credentialBinding") }}</h3><span>{{ selectedCredentialBindings.length }}</span></div>
            <DataTable :columns="[t('table.binding'), t('table.kind'), t('table.source'), t('table.status'), t('settings.access.secret.preview')]" :rows="credentialBindingRows" section-id="access-credential-bindings" :page-size="4" />
            <p v-if="!credentialBindingRows.length" class="access-panel-empty">{{ t("table.noRecords") }}</p>
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>{{ t("settings.access.consumers") }}</h3></div>
            <DataTable :columns="[t('table.consumer'), t('table.usageType'), t('table.status'), t('table.requirements')]" :rows="consumerBindingRows" section-id="access-consumer-bindings" :page-size="4" />
            <p v-if="!consumerBindingRows.length" class="access-panel-empty">{{ t("settings.access.empty.noConsumers") }}</p>
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>{{ t("table.missingAccess") }}</h3><span>{{ inventory?.counts?.blocked ?? 0 }}</span></div>
            <DataTable :columns="[t('table.target'), t('table.kind'), t('table.status'), t('table.setup'), t('table.requiredBy')]" :rows="inventoryRows" section-id="access-inventory-targets" :page-size="4" />
            <p v-if="!inventoryRows.length" class="access-panel-empty">{{ t("table.noRecords") }}</p>
          </article>
          <article class="settings-panel">
            <div class="settings-panel-heading"><h3>{{ t("settings.resource.auditLogs") }}</h3><span>{{ audits.length }}</span></div>
            <DataTable :columns="[t('table.time'), t('table.action'), t('table.target'), t('table.status'), t('table.reason')]" :rows="auditRows" section-id="access-audits" :page-size="4" />
            <p v-if="!auditRows.length" class="access-panel-empty">{{ t("table.noRecords") }}</p>
          </article>
        </section>
      </div>

      <aside class="access-summary-stack">
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>{{ t("settings.access.consumers") }}</h2><span>/ui/access/consumers</span></div>
          <DataTable :columns="[t('table.type'), t('table.count')]" :rows="consumerRows" section-id="access-consumers" />
          <p>{{ consumerRows.length ? "Consumer rows are owned by Access read models." : t("settings.access.empty.noConsumers") }}</p>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>{{ t("settings.access.configurationSummary") }}</h2><span><StatusDot :tone="pageTone" />{{ statusLabel(overview?.status, t("common.ready")) }}</span></div>
          <DataTable :columns="[t('settings.access.table.metric'), t('table.value')]" :rows="usageRows" section-id="access-usage-summary" />
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Access API Surface</h2></div>
          <DataTable :columns="[t('table.endpoint'), t('table.status'), t('table.details')]" :rows="connectedEndpointRows" section-id="access-api-surface" :page-size="8" />
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Missing Write Operations</h2></div>
          <DataTable :columns="[t('table.action'), t('table.status'), t('table.endpoint'), t('table.reason')]" :rows="missingWriteRows" section-id="access-write-gaps" :page-size="4" />
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>{{ t("settings.access.validationHealth") }}</h2></div>
          <dl class="settings-kv">
            <div><dt>{{ t("settings.access.readiness") }}</dt><dd>{{ readinessLabel }}</dd></div>
            <div><dt>{{ t("settings.access.table.checks") }}</dt><dd>{{ selectedReadiness?.checks?.length ?? 0 }}</dd></div>
            <div><dt>Setup Actions</dt><dd>{{ setupActionRows.length }}</dd></div>
            <div><dt>{{ t("settings.access.secret.policy") }}</dt><dd>{{ formatJsonSummary(selectedAssetDetail?.secret_policy) }}</dd></div>
          </dl>
          <DataTable v-if="setupActionRows.length" :columns="[t('table.action'), t('table.kind'), t('table.command')]" :rows="setupActionRows" section-id="access-setup-actions" :page-size="3" />
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>{{ t("table.tags") }}</h2></div>
          <div class="settings-chip-row">
            <span v-for="tag in tags" :key="tag">{{ tag }}</span>
            <span v-if="!tags.length">{{ t("table.noRecords") }}</span>
          </div>
        </article>
      </aside>
    </section>

    <section v-else class="settings-panel access-empty-state">
      <Shield :size="22" />
      <h2>{{ t("settings.access.empty.noAssetsTitle") }}</h2>
      <p>{{ t("settings.access.empty.noAssetsDescription") }}</p>
    </section>

    <footer class="settings-footer">
      <span><Shield :size="14" />{{ t("settings.access.source.controlPlane") }}</span>
      <span><GitBranch :size="14" />{{ t("settings.access.source.readinessOwnedByAccess") }}</span>
      <span><Save :size="14" />{{ t("settings.access.lastSynced") }}: {{ formatTime(generatedAt) }}</span>
      <a>{{ t("settings.resource.auditLogs") }} <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.access-tabs-row {
  border-bottom: 1px solid var(--border-subtle);
}

.access-tabs-row .settings-tabs {
  margin-bottom: 0;
  border-bottom: 0;
}

.access-source-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.access-source-strip span,
.access-empty-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.access-list {
  padding: 0;
  overflow: hidden;
}

.access-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 9%, transparent);
}

.access-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.access-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-gray) 30%, transparent);
}

.access-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.access-api-warning {
  margin-top: 8px;
  font-size: 12px;
}

.access-asset-picker,
.access-action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.access-asset-picker {
  padding: 8px 12px;
  border-top: 1px solid var(--border-subtle);
}

.access-asset-picker button {
  max-width: 220px;
  min-height: 26px;
  overflow: hidden;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.access-asset-picker button.active {
  border-color: color-mix(in srgb, var(--color-blue) 52%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-blue) 14%, transparent);
  color: var(--text-primary);
}

.access-empty,
.access-empty-state {
  color: var(--text-muted);
  font-size: 12px;
}

.access-empty {
  padding: 22px;
}

.access-empty-state {
  justify-content: center;
  min-height: 210px;
  margin-top: 10px;
  flex-direction: column;
  text-align: center;
}

.access-panel-empty {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 11px;
}

.access-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.access-main-column,
.access-summary-stack {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.access-summary-stack {
  align-content: start;
}

.access-summary-stack p {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 11px;
}

.access-editor {
  display: grid;
  grid-template-columns: 166px minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.access-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.access-editor-tabs button {
  min-height: 31px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--radius-2);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.access-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.access-editor-tabs button:disabled {
  cursor: not-allowed;
  opacity: 0.54;
}

.access-form {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.access-form header,
.access-form h2 {
  display: flex;
  align-items: center;
}

.access-form header {
  gap: 10px;
}

.asset-icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
}

.access-form h2 {
  gap: 9px;
  font-size: 16px;
}

.access-form h2 em,
.access-form h2 span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 20px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-active) 70%, transparent);
  color: var(--text-secondary);
  font-size: 11px;
  font-style: normal;
}

.access-form p {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.access-action-row {
  align-items: center;
}

.asset-info-grid,
.access-support-grid {
  display: grid;
  gap: 10px;
}

.asset-info-grid {
  grid-template-columns: minmax(0, 1.1fr) repeat(3, minmax(170px, 0.7fr));
}

.asset-info-grid article {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 76%, transparent);
}

.asset-info-grid h3 {
  margin-bottom: 9px;
  font-size: 13px;
}

.access-support-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
</style>
