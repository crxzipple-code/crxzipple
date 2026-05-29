<script setup lang="ts">
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  GitBranch,
  RefreshCcw,
  RotateCcw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Timer,
  Wrench,
  Zap,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import type {
  SettingsActionResponse,
  SettingsDetailReadModel,
  SettingsPayload,
  SettingsResourceDetailReadModel,
  SettingsResolutionSource,
  SettingsRuntimeDefaultsApplyRequirement,
  SettingsRuntimeDefaultsReadModel,
  UiTone,
} from "@/shared/runtime/types";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { getSettingsResource, listSettingsResources, runSettingsAction } from "../api";

type RuntimeGroupId = "orchestration" | "tool_worker";
type OrchestrationNumberKey =
  | "run_lease_seconds"
  | "run_heartbeat_seconds"
  | "executor_max_concurrent_assignments"
  | "auto_compaction_reserve_tokens"
  | "auto_compaction_soft_threshold_tokens";
type ToolWorkerNumberKey =
  | "run_max_attempts"
  | "run_lease_seconds"
  | "run_heartbeat_seconds"
  | "max_in_flight"
  | "default_run_concurrency"
  | "image_run_concurrency"
  | "shared_state_run_concurrency"
  | "remote_default_max_concurrency";

interface RuntimeDefaultsPayload {
  config_id: string;
  enabled: boolean;
  orchestration: {
    run_lease_seconds: number;
    run_heartbeat_seconds: number;
    executor_max_concurrent_assignments: number;
    auto_compaction_enabled: boolean;
    auto_compaction_reserve_tokens: number;
    auto_compaction_soft_threshold_tokens: number;
  };
  tool_worker: {
    run_max_attempts: number;
    run_lease_seconds: number;
    run_heartbeat_seconds: number;
    max_in_flight: number;
    default_run_concurrency: number;
    image_run_concurrency: number;
    shared_state_run_concurrency: number;
    remote_default_max_concurrency: number;
  };
  metadata: {
    schema_version: number;
    [key: string]: unknown;
  };
}

interface RuntimeDetail extends SettingsResourceDetailReadModel {
  runtime_defaults?: SettingsRuntimeDefaultsReadModel;
}

interface NumberFieldSpec {
  id: string;
  group: RuntimeGroupId;
  key: OrchestrationNumberKey | ToolWorkerNumberKey;
  labelKey: string;
  helpKey: string;
  unitKey: string;
  min: number;
  step: number;
  applyKey: string;
}

const DEFAULT_PAYLOAD: RuntimeDefaultsPayload = {
  config_id: "defaults",
  enabled: true,
  orchestration: {
    run_lease_seconds: 30,
    run_heartbeat_seconds: 5,
    executor_max_concurrent_assignments: 4,
    auto_compaction_enabled: true,
    auto_compaction_reserve_tokens: 20_000,
    auto_compaction_soft_threshold_tokens: 4_000,
  },
  tool_worker: {
    run_max_attempts: 3,
    run_lease_seconds: 30,
    run_heartbeat_seconds: 5,
    max_in_flight: 4,
    default_run_concurrency: 4,
    image_run_concurrency: 4,
    shared_state_run_concurrency: 1,
    remote_default_max_concurrency: 16,
  },
  metadata: {
    schema_version: 1,
  },
};

const orchestrationFields: NumberFieldSpec[] = [
  {
    id: "orchestration.run_lease_seconds",
    group: "orchestration",
    key: "run_lease_seconds",
    labelKey: "settings.runtimeDefaults.field.orchestrationLease",
    helpKey: "settings.runtimeDefaults.help.orchestrationLease",
    unitKey: "settings.runtimeDefaults.unit.seconds",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.orchestrationRestart",
  },
  {
    id: "orchestration.run_heartbeat_seconds",
    group: "orchestration",
    key: "run_heartbeat_seconds",
    labelKey: "settings.runtimeDefaults.field.orchestrationHeartbeat",
    helpKey: "settings.runtimeDefaults.help.orchestrationHeartbeat",
    unitKey: "settings.runtimeDefaults.unit.seconds",
    min: 0.1,
    step: 0.5,
    applyKey: "settings.runtimeDefaults.apply.orchestrationRestart",
  },
  {
    id: "orchestration.executor_max_concurrent_assignments",
    group: "orchestration",
    key: "executor_max_concurrent_assignments",
    labelKey: "settings.runtimeDefaults.field.executorConcurrency",
    helpKey: "settings.runtimeDefaults.help.executorConcurrency",
    unitKey: "settings.runtimeDefaults.unit.assignments",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.executorRestart",
  },
];

const compactionFields: NumberFieldSpec[] = [
  {
    id: "orchestration.auto_compaction_reserve_tokens",
    group: "orchestration",
    key: "auto_compaction_reserve_tokens",
    labelKey: "settings.runtimeDefaults.field.compactionReserve",
    helpKey: "settings.runtimeDefaults.help.compactionReserve",
    unitKey: "settings.runtimeDefaults.unit.tokens",
    min: 1,
    step: 1000,
    applyKey: "settings.runtimeDefaults.apply.orchestrationRestart",
  },
  {
    id: "orchestration.auto_compaction_soft_threshold_tokens",
    group: "orchestration",
    key: "auto_compaction_soft_threshold_tokens",
    labelKey: "settings.runtimeDefaults.field.compactionThreshold",
    helpKey: "settings.runtimeDefaults.help.compactionThreshold",
    unitKey: "settings.runtimeDefaults.unit.tokens",
    min: 1,
    step: 1000,
    applyKey: "settings.runtimeDefaults.apply.orchestrationRestart",
  },
];

const toolWorkerFields: NumberFieldSpec[] = [
  {
    id: "tool_worker.run_max_attempts",
    group: "tool_worker",
    key: "run_max_attempts",
    labelKey: "settings.runtimeDefaults.field.toolAttempts",
    helpKey: "settings.runtimeDefaults.help.toolAttempts",
    unitKey: "settings.runtimeDefaults.unit.attempts",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.toolWorkerRestart",
  },
  {
    id: "tool_worker.run_lease_seconds",
    group: "tool_worker",
    key: "run_lease_seconds",
    labelKey: "settings.runtimeDefaults.field.toolLease",
    helpKey: "settings.runtimeDefaults.help.toolLease",
    unitKey: "settings.runtimeDefaults.unit.seconds",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.toolWorkerRestart",
  },
  {
    id: "tool_worker.run_heartbeat_seconds",
    group: "tool_worker",
    key: "run_heartbeat_seconds",
    labelKey: "settings.runtimeDefaults.field.toolHeartbeat",
    helpKey: "settings.runtimeDefaults.help.toolHeartbeat",
    unitKey: "settings.runtimeDefaults.unit.seconds",
    min: 0.1,
    step: 0.5,
    applyKey: "settings.runtimeDefaults.apply.toolWorkerRestart",
  },
  {
    id: "tool_worker.max_in_flight",
    group: "tool_worker",
    key: "max_in_flight",
    labelKey: "settings.runtimeDefaults.field.toolInFlight",
    helpKey: "settings.runtimeDefaults.help.toolInFlight",
    unitKey: "settings.runtimeDefaults.unit.runs",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.toolWorkerRestart",
  },
  {
    id: "tool_worker.default_run_concurrency",
    group: "tool_worker",
    key: "default_run_concurrency",
    labelKey: "settings.runtimeDefaults.field.toolDefaultConcurrency",
    helpKey: "settings.runtimeDefaults.help.toolDefaultConcurrency",
    unitKey: "settings.runtimeDefaults.unit.runs",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.toolRuntimeRestart",
  },
  {
    id: "tool_worker.image_run_concurrency",
    group: "tool_worker",
    key: "image_run_concurrency",
    labelKey: "settings.runtimeDefaults.field.toolImageConcurrency",
    helpKey: "settings.runtimeDefaults.help.toolImageConcurrency",
    unitKey: "settings.runtimeDefaults.unit.runs",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.toolRuntimeRestart",
  },
  {
    id: "tool_worker.shared_state_run_concurrency",
    group: "tool_worker",
    key: "shared_state_run_concurrency",
    labelKey: "settings.runtimeDefaults.field.toolSharedConcurrency",
    helpKey: "settings.runtimeDefaults.help.toolSharedConcurrency",
    unitKey: "settings.runtimeDefaults.unit.runs",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.toolRuntimeRestart",
  },
  {
    id: "tool_worker.remote_default_max_concurrency",
    group: "tool_worker",
    key: "remote_default_max_concurrency",
    labelKey: "settings.runtimeDefaults.field.remoteConcurrency",
    helpKey: "settings.runtimeDefaults.help.remoteConcurrency",
    unitKey: "settings.runtimeDefaults.unit.calls",
    min: 1,
    step: 1,
    applyKey: "settings.runtimeDefaults.apply.toolRuntimeRestart",
  },
];

const allNumberFields = [...orchestrationFields, ...compactionFields, ...toolWorkerFields];

const { t } = useI18n();
const detail = ref<RuntimeDetail | null>(null);
const form = ref<RuntimeDefaultsPayload>(clonePayload(DEFAULT_PAYLOAD));
const initialPayload = ref<RuntimeDefaultsPayload>(clonePayload(DEFAULT_PAYLOAD));
const selectedResourceId = ref("defaults");
const saveReason = ref("");
const isLoading = ref(false);
const isSaving = ref(false);
const isValidating = ref(false);
const loadError = ref<string | null>(null);
const actionError = ref<string | null>(null);
const actionNotice = ref<string | null>(null);
const lastAction = ref<SettingsActionResponse | null>(null);

const runtimeReadModel = computed(() => detail.value?.runtime_defaults ?? null);
const validationErrors = computed(() => validatePayload(form.value));
const isDirty = computed(() =>
  JSON.stringify(actionPayload(form.value)) !== JSON.stringify(actionPayload(initialPayload.value)),
);
const canSave = computed(
  () => Boolean(detail.value)
    && isDirty.value
    && validationErrors.value.length === 0
    && saveReason.value.trim().length > 0
    && !isSaving.value,
);
const validationTone = computed<UiTone>(() => {
  if (validationErrors.value.length > 0) return "danger";
  const status = String(detail.value?.validation?.status ?? runtimeReadModel.value?.validation?.status ?? "");
  if (status === "invalid") return "danger";
  if (status === "unknown" || !status) return "warning";
  return "success";
});
const sourceLabel = computed(() => shortenSource(detail.value?.source ?? runtimeReadModel.value?.source ?? "-"));
const versionLabel = computed(() => textValue(detail.value?.version ?? runtimeReadModel.value?.version));
const schemaLabel = computed(() => runtimeReadModel.value?.schema ?? "runtime-defaults.v1");
const resolvedAtLabel = computed(() => textValue(runtimeReadModel.value?.resolved_at ?? detail.value?.resolution?.resolved_at));
const sourceRows = computed(() => detail.value?.resolution?.sources ?? []);
const auditRows = computed(() => detail.value?.audit?.recent_changes?.rows?.slice(0, 5) ?? []);
const versionRows = computed(() => (detail.value?.versions ?? []).slice(-5).reverse());
const applyRequirements = computed<SettingsRuntimeDefaultsApplyRequirement[]>(() =>
  runtimeReadModel.value?.apply_requirements?.length
    ? runtimeReadModel.value.apply_requirements
    : [
        {
          id: "restart_required",
          mode: "restart_required",
          owner: "runtime",
          applies_after: t("settings.runtimeDefaults.apply.restartRequired"),
        },
      ],
);
const summaryFields = computed(() => [
  {
    icon: ShieldCheck,
    label: t("settings.runtimeDefaults.summary.status"),
    value: detail.value?.enabled === false ? t("common.disabled") : t("common.enabled"),
    note: detail.value?.resource_id ?? selectedResourceId.value,
    tone: detail.value?.enabled === false ? "warning" : "success",
  },
  {
    icon: GitBranch,
    label: t("settings.runtimeDefaults.summary.source"),
    value: sourceLabel.value,
    note: t("settings.runtimeDefaults.summary.version", { version: versionLabel.value }),
    tone: "info",
  },
  {
    icon: Timer,
    label: t("settings.runtimeDefaults.summary.lease"),
    value: `${form.value.orchestration.run_lease_seconds}s / ${form.value.tool_worker.run_lease_seconds}s`,
    note: t("settings.runtimeDefaults.summary.orchestrationTool"),
    tone: "neutral",
  },
  {
    icon: Wrench,
    label: t("settings.runtimeDefaults.summary.toolConcurrency"),
    value: String(form.value.tool_worker.max_in_flight),
    note: t("settings.runtimeDefaults.summary.inFlight"),
    tone: "neutral",
  },
  {
    icon: Clock3,
    label: t("settings.runtimeDefaults.summary.apply"),
    value: t("settings.runtimeDefaults.apply.restartRequiredShort"),
    note: resolvedAtLabel.value,
    tone: "warning",
  },
]);

onMounted(() => {
  void loadRuntimeDefaults();
});

async function loadRuntimeDefaults(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  actionError.value = null;
  try {
    const loaded = await loadRuntimeDetail(selectedResourceId.value);
    detail.value = loaded;
    selectedResourceId.value = loaded.resource_id;
    resetFormFromDetail(loaded);
  } catch (error) {
    try {
      const page = await listSettingsResources("runtime-defaults", { limit: 1, offset: 0 });
      const first = page.resources[0]?.resource_id;
      if (!first) throw error;
      const loaded = await loadRuntimeDetail(first);
      detail.value = loaded;
      selectedResourceId.value = loaded.resource_id;
      resetFormFromDetail(loaded);
    } catch (fallbackError) {
      loadError.value = fallbackError instanceof Error ? fallbackError.message : String(fallbackError);
      detail.value = null;
    }
  } finally {
    isLoading.value = false;
  }
}

async function validateRuntimeDefaults(): Promise<void> {
  if (!detail.value) return;
  isValidating.value = true;
  actionError.value = null;
  actionNotice.value = null;
  try {
    lastAction.value = await runSettingsAction(
      "runtime-defaults",
      detail.value.resource_id,
      "validate",
      {},
      null,
      {
        actor: "settings-ui",
        risk: "low",
        metadata: { source: "runtime_defaults_settings_page" },
      },
    );
    actionNotice.value = t("settings.runtimeDefaults.notice.validated");
    await loadRuntimeDefaults();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isValidating.value = false;
  }
}

async function saveRuntimeDefaults(): Promise<void> {
  actionError.value = null;
  actionNotice.value = null;
  if (!detail.value) {
    actionError.value = t("settings.runtimeDefaults.error.noResource");
    return;
  }
  if (validationErrors.value.length > 0) {
    actionError.value = validationErrors.value.join(" ");
    return;
  }
  if (!saveReason.value.trim()) {
    actionError.value = t("settings.runtimeDefaults.error.reasonRequired");
    return;
  }
  isSaving.value = true;
  try {
    lastAction.value = await runSettingsAction(
      "runtime-defaults",
      detail.value.resource_id,
      "update",
      actionPayload(form.value),
      saveReason.value.trim(),
      {
        actor: "settings-ui",
        risk: "medium",
        metadata: {
          source: "runtime_defaults_settings_page",
          schema: "runtime-defaults.v1",
          apply: "restart_required",
        },
      },
    );
    actionNotice.value = t("settings.runtimeDefaults.notice.saved");
    saveReason.value = "";
    await loadRuntimeDefaults();
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isSaving.value = false;
  }
}

function resetForm(): void {
  form.value = clonePayload(initialPayload.value);
  actionError.value = null;
  actionNotice.value = null;
}

function resetFormFromDetail(nextDetail: RuntimeDetail): void {
  const payload = normalizeRuntimeDefaultsPayload(
    nextDetail.runtime_defaults?.effective_payload ?? nextDetail.effective_config,
  );
  form.value = clonePayload(payload);
  initialPayload.value = clonePayload(payload);
}

async function loadRuntimeDetail(resourceId: string): Promise<RuntimeDetail> {
  const loaded = await getSettingsResource("runtime-defaults", resourceId);
  if (!isSettingsDetail(loaded)) {
    throw new Error(t("settings.runtimeDefaults.error.invalidDetail"));
  }
  return loaded as RuntimeDetail;
}

function numberFieldValue(field: NumberFieldSpec): number {
  const group = form.value[field.group] as Record<string, number | boolean>;
  const value = group[field.key];
  return typeof value === "number" ? value : Number(value) || 0;
}

function updateNumberField(field: NumberFieldSpec, event: Event): void {
  const input = event.target as HTMLInputElement;
  const parsed = Number(input.value);
  const group = form.value[field.group] as Record<string, number | boolean>;
  group[field.key] = Number.isFinite(parsed) ? parsed : 0;
}

function fieldDefault(field: NumberFieldSpec): string {
  return textValue(getPath(DEFAULT_PAYLOAD, `${field.group}.${field.key}`));
}

function fieldMeta(field: NumberFieldSpec): string {
  return t("settings.runtimeDefaults.field.meta", {
    min: field.min,
    default: fieldDefault(field),
    source: sourceLabel.value,
  });
}

function actionPayload(payload: RuntimeDefaultsPayload): SettingsPayload {
  return {
    config_id: payload.config_id,
    enabled: payload.enabled,
    orchestration: {
      run_lease_seconds: normalizeNumber(payload.orchestration.run_lease_seconds),
      run_heartbeat_seconds: normalizeNumber(payload.orchestration.run_heartbeat_seconds),
      executor_max_concurrent_assignments: normalizeNumber(payload.orchestration.executor_max_concurrent_assignments),
      auto_compaction_enabled: Boolean(payload.orchestration.auto_compaction_enabled),
      auto_compaction_reserve_tokens: normalizeNumber(payload.orchestration.auto_compaction_reserve_tokens),
      auto_compaction_soft_threshold_tokens: normalizeNumber(payload.orchestration.auto_compaction_soft_threshold_tokens),
    },
    tool_worker: {
      run_max_attempts: normalizeNumber(payload.tool_worker.run_max_attempts),
      run_lease_seconds: normalizeNumber(payload.tool_worker.run_lease_seconds),
      run_heartbeat_seconds: normalizeNumber(payload.tool_worker.run_heartbeat_seconds),
      max_in_flight: normalizeNumber(payload.tool_worker.max_in_flight),
      default_run_concurrency: normalizeNumber(payload.tool_worker.default_run_concurrency),
      image_run_concurrency: normalizeNumber(payload.tool_worker.image_run_concurrency),
      shared_state_run_concurrency: normalizeNumber(payload.tool_worker.shared_state_run_concurrency),
      remote_default_max_concurrency: normalizeNumber(payload.tool_worker.remote_default_max_concurrency),
    },
    metadata: {
      ...payload.metadata,
      schema_version: normalizeNumber(payload.metadata.schema_version || 1),
    },
  };
}

function normalizeRuntimeDefaultsPayload(value: unknown): RuntimeDefaultsPayload {
  const record = isRecord(value) ? value : {};
  const orchestration = isRecord(record.orchestration) ? record.orchestration : {};
  const toolWorker = isRecord(record.tool_worker) ? record.tool_worker : {};
  const metadata = isRecord(record.metadata) ? record.metadata : {};
  return {
    config_id: textValue(record.config_id ?? record.id, DEFAULT_PAYLOAD.config_id),
    enabled: typeof record.enabled === "boolean" ? record.enabled : DEFAULT_PAYLOAD.enabled,
    orchestration: {
      run_lease_seconds: numberValue(orchestration.run_lease_seconds, DEFAULT_PAYLOAD.orchestration.run_lease_seconds),
      run_heartbeat_seconds: numberValue(orchestration.run_heartbeat_seconds, DEFAULT_PAYLOAD.orchestration.run_heartbeat_seconds),
      executor_max_concurrent_assignments: numberValue(orchestration.executor_max_concurrent_assignments, DEFAULT_PAYLOAD.orchestration.executor_max_concurrent_assignments),
      auto_compaction_enabled: typeof orchestration.auto_compaction_enabled === "boolean" ? orchestration.auto_compaction_enabled : DEFAULT_PAYLOAD.orchestration.auto_compaction_enabled,
      auto_compaction_reserve_tokens: numberValue(orchestration.auto_compaction_reserve_tokens, DEFAULT_PAYLOAD.orchestration.auto_compaction_reserve_tokens),
      auto_compaction_soft_threshold_tokens: numberValue(orchestration.auto_compaction_soft_threshold_tokens, DEFAULT_PAYLOAD.orchestration.auto_compaction_soft_threshold_tokens),
    },
    tool_worker: {
      run_max_attempts: numberValue(toolWorker.run_max_attempts, DEFAULT_PAYLOAD.tool_worker.run_max_attempts),
      run_lease_seconds: numberValue(toolWorker.run_lease_seconds, DEFAULT_PAYLOAD.tool_worker.run_lease_seconds),
      run_heartbeat_seconds: numberValue(toolWorker.run_heartbeat_seconds, DEFAULT_PAYLOAD.tool_worker.run_heartbeat_seconds),
      max_in_flight: numberValue(toolWorker.max_in_flight, DEFAULT_PAYLOAD.tool_worker.max_in_flight),
      default_run_concurrency: numberValue(toolWorker.default_run_concurrency, DEFAULT_PAYLOAD.tool_worker.default_run_concurrency),
      image_run_concurrency: numberValue(toolWorker.image_run_concurrency, DEFAULT_PAYLOAD.tool_worker.image_run_concurrency),
      shared_state_run_concurrency: numberValue(toolWorker.shared_state_run_concurrency, DEFAULT_PAYLOAD.tool_worker.shared_state_run_concurrency),
      remote_default_max_concurrency: numberValue(toolWorker.remote_default_max_concurrency, DEFAULT_PAYLOAD.tool_worker.remote_default_max_concurrency),
    },
    metadata: {
      ...metadata,
      schema_version: numberValue(metadata.schema_version, DEFAULT_PAYLOAD.metadata.schema_version),
    },
  };
}

function validatePayload(payload: RuntimeDefaultsPayload): string[] {
  const errors: string[] = [];
  for (const field of allNumberFields) {
    const value = numberFieldValueFromPayload(payload, field);
    if (!Number.isFinite(value) || value < field.min) {
      errors.push(t("settings.runtimeDefaults.error.positive", { field: t(field.labelKey) }));
    }
  }
  if (!payload.config_id.trim()) {
    errors.push(t("settings.runtimeDefaults.error.configId"));
  }
  return errors;
}

function numberFieldValueFromPayload(payload: RuntimeDefaultsPayload, field: NumberFieldSpec): number {
  const group = payload[field.group] as Record<string, number | boolean>;
  const value = group[field.key];
  return typeof value === "number" ? value : Number(value);
}

function getPath(payload: RuntimeDefaultsPayload, path: string): unknown {
  return path.split(".").reduce<unknown>((current, part) => {
    if (!isRecord(current)) return null;
    return current[part];
  }, payload);
}

function sourceName(source: SettingsResolutionSource): string {
  return shortenSource(source.name || source.source_id || "-");
}

function auditValue(row: unknown, key: string): string {
  return isRecord(row) ? textValue(row[key]) : "-";
}

function versionValue(row: unknown, key: string): string {
  if (!isRecord(row)) return "-";
  return key === "source" ? shortenSource(row[key]) : textValue(row[key]);
}

function normalizeNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function textValue(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function shortenSource(value: unknown): string {
  const text = textValue(value);
  if (text.startsWith("bootstrap:")) return "bootstrap";
  if (text.length > 28) return `${text.slice(0, 25)}...`;
  return text;
}

function clonePayload(payload: RuntimeDefaultsPayload): RuntimeDefaultsPayload {
  return JSON.parse(JSON.stringify(payload)) as RuntimeDefaultsPayload;
}

function isSettingsDetail(value: SettingsDetailReadModel): value is SettingsResourceDetailReadModel {
  return isRecord(value) && value.kind === "runtime-defaults" && typeof value.resource_id === "string";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
</script>

<template>
  <main class="settings-module runtime-settings scroll-area">
    <header class="runtime-command">
      <div class="runtime-title">
        <h1>{{ t("settings.runtimeDefaults.title") }}</h1>
        <p>{{ t("settings.runtimeDefaults.subtitle") }}</p>
      </div>
      <div class="runtime-command-controls">
        <span class="runtime-schema-pill">{{ schemaLabel }}</span>
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadRuntimeDefaults">
          <RefreshCcw :size="14" />{{ t("common.refresh") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="!detail || isValidating" @click="validateRuntimeDefaults">
          <CheckCircle2 :size="14" />{{ isValidating ? t("settings.runtimeDefaults.action.validating") : t("settings.runtimeDefaults.action.validate") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="!isDirty" @click="resetForm">
          <RotateCcw :size="14" />{{ t("common.reset") }}
        </UiButton>
        <UiButton size="sm" variant="primary" :disabled="!canSave" @click="saveRuntimeDefaults">
          <Save :size="14" />{{ isSaving ? t("settings.runtimeDefaults.action.saving") : t("settings.runtimeDefaults.action.save") }}
        </UiButton>
      </div>
    </header>

    <section class="runtime-summary-strip" :aria-label="t('settings.runtimeDefaults.summary.aria')">
      <article
        v-for="item in summaryFields"
        :key="item.label"
        class="settings-panel runtime-summary-card"
        :class="`runtime-summary-card--${item.tone}`"
      >
        <span class="summary-icon"><component :is="item.icon" :size="18" /></span>
        <div>
          <small>{{ item.label }}</small>
          <strong>{{ item.value }}</strong>
          <p>{{ item.note }}</p>
        </div>
      </article>
    </section>

    <section v-if="loadError" class="settings-panel runtime-notice runtime-notice--danger">
      <AlertTriangle :size="16" />{{ loadError }}
    </section>
    <section v-else-if="actionError || actionNotice" class="settings-panel runtime-notice" :class="{ 'runtime-notice--danger': actionError }">
      <AlertTriangle v-if="actionError" :size="16" />
      <CheckCircle2 v-else :size="16" />
      {{ actionError ?? actionNotice }}
    </section>

    <section class="runtime-workspace" :class="{ 'runtime-workspace--loading': isLoading }">
      <div class="runtime-main-column">
        <section class="runtime-form-grid">
          <article class="settings-panel runtime-section runtime-section--identity">
            <div class="runtime-section-heading">
              <h2><SlidersHorizontal :size="15" />{{ t("settings.runtimeDefaults.group.general") }}</h2>
              <span><StatusDot :tone="validationTone" />{{ validationErrors.length ? t("status.failed") : t("settings.runtimeDefaults.state.valid") }}</span>
            </div>
            <div class="runtime-inline-fields">
              <label>
                <span>{{ t("settings.runtimeDefaults.field.configId") }}</span>
                <input v-model="form.config_id" type="text" autocomplete="off" />
              </label>
              <label class="runtime-toggle-field">
                <span>{{ t("settings.runtimeDefaults.field.enabled") }}</span>
                <input v-model="form.enabled" type="checkbox" />
                <em>{{ form.enabled ? t("common.enabled") : t("common.disabled") }}</em>
              </label>
              <label>
                <span>{{ t("settings.runtimeDefaults.field.schemaVersion") }}</span>
                <input
                  :value="form.metadata.schema_version"
                  type="number"
                  min="1"
                  step="1"
                  @input="form.metadata.schema_version = normalizeNumber(($event.target as HTMLInputElement).value)"
                />
              </label>
            </div>
          </article>

          <article class="settings-panel runtime-section">
            <div class="runtime-section-heading">
              <h2><Zap :size="15" />{{ t("settings.runtimeDefaults.group.orchestration") }}</h2>
              <span>{{ t("settings.runtimeDefaults.apply.orchestrationRestart") }}</span>
            </div>
            <div class="runtime-field-grid">
              <label v-for="field in orchestrationFields" :key="field.id" class="runtime-field">
                <span>
                  <strong>{{ t(field.labelKey) }}</strong>
                  <small>{{ t(field.helpKey) }}</small>
                </span>
                <div class="runtime-input-row">
                  <input
                    :value="numberFieldValue(field)"
                    type="number"
                    :min="field.min"
                    :step="field.step"
                    @input="updateNumberField(field, $event)"
                  />
                  <em>{{ t(field.unitKey) }}</em>
                </div>
                <footer>{{ fieldMeta(field) }}</footer>
              </label>
            </div>
          </article>

          <article class="settings-panel runtime-section">
            <div class="runtime-section-heading">
              <h2><ShieldCheck :size="15" />{{ t("settings.runtimeDefaults.group.compaction") }}</h2>
              <span>{{ t("settings.runtimeDefaults.apply.orchestrationRestart") }}</span>
            </div>
            <div class="runtime-compaction-row">
              <label class="runtime-toggle-card">
                <input v-model="form.orchestration.auto_compaction_enabled" type="checkbox" />
                <span>
                  <strong>{{ t("settings.runtimeDefaults.field.compactionEnabled") }}</strong>
                  <small>{{ t("settings.runtimeDefaults.help.compactionEnabled") }}</small>
                  <em>{{ t("settings.runtimeDefaults.field.source", { source: sourceLabel }) }}</em>
                </span>
              </label>
              <label v-for="field in compactionFields" :key="field.id" class="runtime-field">
                <span>
                  <strong>{{ t(field.labelKey) }}</strong>
                  <small>{{ t(field.helpKey) }}</small>
                </span>
                <div class="runtime-input-row">
                  <input
                    :value="numberFieldValue(field)"
                    type="number"
                    :min="field.min"
                    :step="field.step"
                    @input="updateNumberField(field, $event)"
                  />
                  <em>{{ t(field.unitKey) }}</em>
                </div>
                <footer>{{ fieldMeta(field) }}</footer>
              </label>
            </div>
          </article>

          <article class="settings-panel runtime-section runtime-section--tool">
            <div class="runtime-section-heading">
              <h2><Wrench :size="15" />{{ t("settings.runtimeDefaults.group.toolWorker") }}</h2>
              <span>{{ t("settings.runtimeDefaults.apply.toolWorkerRestart") }}</span>
            </div>
            <div class="runtime-field-grid runtime-field-grid--tool">
              <label v-for="field in toolWorkerFields" :key="field.id" class="runtime-field">
                <span>
                  <strong>{{ t(field.labelKey) }}</strong>
                  <small>{{ t(field.helpKey) }}</small>
                </span>
                <div class="runtime-input-row">
                  <input
                    :value="numberFieldValue(field)"
                    type="number"
                    :min="field.min"
                    :step="field.step"
                    @input="updateNumberField(field, $event)"
                  />
                  <em>{{ t(field.unitKey) }}</em>
                </div>
                <footer>{{ fieldMeta(field) }}</footer>
              </label>
            </div>
          </article>
        </section>
      </div>

      <aside class="runtime-side-column">
        <article class="settings-panel runtime-save-panel">
          <div class="runtime-section-heading">
            <h2><Save :size="15" />{{ t("settings.runtimeDefaults.save.title") }}</h2>
            <span>{{ isDirty ? t("settings.runtimeDefaults.state.changed") : t("settings.runtimeDefaults.state.clean") }}</span>
          </div>
          <label class="runtime-reason-field">
            <span>{{ t("settings.runtimeDefaults.save.reason") }}</span>
            <textarea v-model="saveReason" rows="3" :placeholder="t('settings.runtimeDefaults.save.reasonPlaceholder')" />
          </label>
          <ul v-if="validationErrors.length" class="runtime-error-list">
            <li v-for="error in validationErrors" :key="error">{{ error }}</li>
          </ul>
          <p v-else>{{ t("settings.runtimeDefaults.save.auditHint") }}</p>
        </article>

        <article class="settings-panel runtime-side-card">
          <div class="runtime-section-heading">
            <h2><Clock3 :size="15" />{{ t("settings.runtimeDefaults.apply.title") }}</h2>
            <span>{{ t("settings.runtimeDefaults.apply.restartRequiredShort") }}</span>
          </div>
          <div class="runtime-apply-list">
            <div v-for="requirement in applyRequirements" :key="requirement.id">
              <strong>{{ t(`settings.runtimeDefaults.applyRequirement.${requirement.id}`) }}</strong>
              <span>{{ requirement.applies_after ?? t("settings.runtimeDefaults.apply.restartRequired") }}</span>
            </div>
          </div>
        </article>

        <article class="settings-panel runtime-side-card">
          <div class="runtime-section-heading">
            <h2><GitBranch :size="15" />{{ t("settings.runtimeDefaults.resolution.title") }}</h2>
            <span>{{ sourceRows.length }}</span>
          </div>
          <div class="runtime-source-list">
            <div v-for="source in sourceRows.slice(0, 4)" :key="source.version_id ?? source.source_id">
              <span>{{ source.kind }}</span>
              <strong>{{ sourceName(source) }}</strong>
              <em>{{ source.applied ? t("settings.runtimeDefaults.state.applied") : t("settings.runtimeDefaults.state.skipped") }}</em>
            </div>
            <p v-if="!sourceRows.length">{{ t("settings.runtimeDefaults.resolution.empty") }}</p>
          </div>
        </article>

        <article class="settings-panel runtime-side-card">
          <div class="runtime-section-heading">
            <h2><RefreshCcw :size="15" />{{ t("settings.runtimeDefaults.version.title") }}</h2>
            <span>{{ versionRows.length }}</span>
          </div>
          <div class="runtime-version-list">
            <div v-for="version in versionRows" :key="versionValue(version, 'id')">
              <strong>v{{ versionValue(version, "version_number") }}</strong>
              <span>{{ versionValue(version, "source") }}</span>
              <em>{{ versionValue(version, "created_at") }}</em>
            </div>
            <p v-if="!versionRows.length">{{ t("settings.runtimeDefaults.version.empty") }}</p>
          </div>
        </article>

        <article class="settings-panel runtime-side-card">
          <div class="runtime-section-heading">
            <h2><AlertTriangle :size="15" />{{ t("settings.runtimeDefaults.audit.title") }}</h2>
            <span>{{ auditRows.length }}</span>
          </div>
          <div class="runtime-audit-list">
            <div v-for="row in auditRows" :key="auditValue(row, 'Audit ID')">
              <strong>{{ auditValue(row, "Action") }}</strong>
              <span>{{ auditValue(row, "Reason") }}</span>
              <em>{{ auditValue(row, "Status") }}</em>
            </div>
            <p v-if="!auditRows.length">{{ t("settings.runtimeDefaults.audit.empty") }}</p>
          </div>
        </article>
      </aside>
    </section>

    <footer class="settings-footer runtime-footer">
      <span><SlidersHorizontal :size="14" />{{ t("settings.runtimeDefaults.footer.truth") }}</span>
      <span><GitBranch :size="14" />/ui/settings/runtime-defaults/{{ selectedResourceId }}</span>
      <span><Clock3 :size="14" />{{ lastAction?.audit?.audit_id ?? t("settings.runtimeDefaults.footer.noRecentAction") }}</span>
    </footer>
  </main>
</template>

<style scoped>
.runtime-settings {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  min-height: calc(100dvh - var(--shell-topbar-height));
}

.runtime-command,
.runtime-command-controls,
.runtime-section-heading,
.runtime-section-heading h2,
.runtime-toggle-card,
.runtime-notice {
  display: flex;
  align-items: center;
}

.runtime-command {
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
}

.runtime-title h1 {
  font-size: 20px;
  line-height: 1.1;
}

.runtime-title p {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.runtime-command-controls {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.runtime-schema-pill {
  min-height: 28px;
  padding: 6px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 11px;
}

.runtime-summary-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.runtime-summary-card {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  min-height: 82px;
  padding: 10px;
}

.summary-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-blue) 18%, transparent);
  color: var(--color-blue);
}

.runtime-summary-card--success .summary-icon {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.runtime-summary-card--warning .summary-icon {
  background: color-mix(in srgb, var(--color-warning) 18%, transparent);
  color: var(--color-warning);
}

.runtime-summary-card small,
.runtime-summary-card p {
  color: var(--text-muted);
  font-size: 10.5px;
}

.runtime-summary-card strong {
  display: block;
  overflow: hidden;
  margin: 4px 0;
  font-size: 16px;
  line-height: 1.05;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-notice {
  gap: 8px;
  min-height: 36px;
  margin-bottom: 10px;
  padding: 8px 10px;
  color: var(--color-success);
  font-size: 12px;
}

.runtime-notice--danger {
  color: var(--color-danger);
}

.runtime-workspace {
  display: grid;
  grid-template-columns: minmax(680px, 1fr) minmax(320px, 360px);
  gap: 10px;
  align-items: start;
  min-height: 0;
}

.runtime-workspace--loading {
  opacity: 0.68;
  pointer-events: none;
}

.runtime-main-column,
.runtime-side-column,
.runtime-form-grid {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.runtime-form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: stretch;
}

.runtime-section {
  min-height: 0;
}

.runtime-section--identity,
.runtime-section--tool {
  grid-column: 1 / -1;
}

.runtime-section-heading {
  justify-content: space-between;
  gap: 10px;
  min-height: 24px;
  margin-bottom: 8px;
}

.runtime-section-heading h2 {
  gap: 7px;
  font-size: 13px;
}

.runtime-section-heading span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font-size: 10.5px;
  white-space: nowrap;
}

.runtime-inline-fields,
.runtime-field-grid,
.runtime-compaction-row {
  display: grid;
  gap: 8px;
}

.runtime-inline-fields {
  grid-template-columns: minmax(180px, 1.2fr) 150px 150px;
}

.runtime-field-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.runtime-field-grid--tool {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.runtime-compaction-row {
  grid-template-columns: minmax(160px, 0.85fr) repeat(2, minmax(0, 1fr));
}

.runtime-inline-fields label,
.runtime-field,
.runtime-reason-field {
  display: grid;
  gap: 5px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 11px;
}

.runtime-field {
  min-height: 96px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-base) 70%, transparent);
}

.runtime-field strong,
.runtime-toggle-card strong {
  display: block;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-field small,
.runtime-toggle-card small,
.runtime-save-panel p,
.runtime-error-list {
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1.35;
}

.runtime-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.runtime-input-row input,
.runtime-inline-fields input,
.runtime-reason-field textarea {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
}

.runtime-input-row input,
.runtime-inline-fields input {
  min-height: 30px;
  padding: 5px 8px;
}

.runtime-input-row em {
  padding-right: 8px;
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
}

.runtime-toggle-card em {
  display: block;
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
}

.runtime-field footer {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-toggle-field {
  grid-template-columns: 1fr auto auto;
  align-items: center;
}

.runtime-toggle-field input,
.runtime-toggle-card input {
  width: 34px;
  height: 18px;
  accent-color: var(--color-accent);
}

.runtime-toggle-field em {
  color: var(--text-muted);
  font-style: normal;
}

.runtime-toggle-card {
  gap: 9px;
  min-height: 96px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-base) 70%, transparent);
}

.runtime-save-panel,
.runtime-side-card {
  padding: 10px;
}

.runtime-reason-field textarea {
  min-height: 70px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  resize: vertical;
}

.runtime-error-list {
  display: grid;
  gap: 4px;
  margin: 0;
  padding-left: 16px;
  color: var(--color-danger);
}

.runtime-apply-list,
.runtime-source-list,
.runtime-version-list,
.runtime-audit-list {
  display: grid;
  gap: 6px;
}

.runtime-apply-list div,
.runtime-source-list div,
.runtime-version-list div,
.runtime-audit-list div {
  display: grid;
  grid-template-columns: minmax(88px, 0.7fr) minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 6px 8px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--surface-base) 70%, transparent);
  font-size: 11px;
}

.runtime-apply-list div {
  grid-template-columns: minmax(100px, 0.8fr) minmax(0, 1fr);
}

.runtime-version-list div {
  grid-template-columns: 42px 82px minmax(0, 1fr);
}

.runtime-apply-list strong,
.runtime-source-list strong,
.runtime-version-list strong,
.runtime-audit-list strong {
  overflow: hidden;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-apply-list span,
.runtime-source-list span,
.runtime-version-list span,
.runtime-audit-list span {
  overflow: hidden;
  color: var(--text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-source-list em,
.runtime-version-list em,
.runtime-audit-list em {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-source-list p,
.runtime-version-list p,
.runtime-audit-list p {
  display: grid;
  place-items: center;
  min-height: 54px;
  color: var(--text-muted);
  font-size: 11px;
}

@media (max-width: 1180px) {
  .runtime-summary-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .runtime-workspace {
    grid-template-columns: 1fr;
  }

  .runtime-side-column {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .runtime-command {
    align-items: flex-start;
    flex-direction: column;
  }

  .runtime-summary-strip,
  .runtime-form-grid,
  .runtime-field-grid,
  .runtime-field-grid--tool,
  .runtime-compaction-row,
  .runtime-inline-fields,
  .runtime-side-column {
    grid-template-columns: 1fr;
  }
}
</style>
