<script setup lang="ts">
import { ArrowRight, Brain, CheckCircle2, Copy, GitBranch, Layers, ListFilter, Play, RefreshCcw, Save, Search, Shield } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { listSettingsResources } from "../api";
import {
  getLlmProfile,
  invokeLlmProfile,
  listLlmProfiles,
  setLlmProfileEnabled,
  updateLlmProfile,
  type LlmInvocationApiPayload,
  type LlmProfileApiPayload,
  type LlmProfileWritePayload,
} from "../ownerApis/llmProfiles";

type TableRow = Record<string, string | number | null>;
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

interface SettingsSourcePayload {
  kind?: string;
  name?: string;
  source_id?: string;
  version?: number | string | null;
  version_id?: string | null;
  override_id?: string | null;
  applied?: boolean;
  reason?: string | null;
}

interface SettingsResolutionPayload {
  value?: unknown;
  source?: SettingsSourcePayload;
  sources?: SettingsSourcePayload[];
  override_trace?: SettingsSourcePayload[];
  snapshot_id?: string | null;
  resolved_at?: string | null;
  validation?: {
    ok?: boolean;
    errors?: unknown[];
    warnings?: unknown[];
    metadata?: Record<string, unknown>;
  };
}

interface SettingsResourceSummary {
  resource_id: string;
  id?: string;
  display_name?: string;
  status?: string;
  enabled?: boolean;
  source?: string | null;
  version?: number | string | null;
  updated_at?: string | null;
  metadata?: Record<string, unknown>;
  effective_config?: Record<string, unknown>;
  resolution?: SettingsResolutionPayload;
}

interface SettingsVersionPayload {
  id?: string;
  version_number?: number | string | null;
  status?: string;
  source?: string | null;
  reason?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  published_at?: string | null;
  validation?: {
    ok?: boolean;
    errors?: unknown[];
    warnings?: unknown[];
  };
}

interface SettingsValidationPayload {
  status?: string;
  last_validated_at?: string | null;
  checks?: {
    columns?: string[];
    rows?: TableRow[];
  };
  result?: {
    ok?: boolean;
    errors?: unknown[];
    warnings?: unknown[];
  };
}

interface SettingsAuditPayload {
  recent_changes?: {
    columns?: string[];
    rows?: TableRow[];
  };
  reason_required?: boolean;
  audit_history_route?: string;
}

interface SettingsResourceDetail extends SettingsResourceSummary {
  title?: string;
  payload?: Record<string, unknown>;
  validation?: SettingsValidationPayload;
  audit?: SettingsAuditPayload;
  versions?: SettingsVersionPayload[];
}

interface SettingsListPayload {
  total?: number;
  limit?: number;
  offset?: number;
}

interface SettingsKindPayload {
  title?: string;
  description?: string;
  status?: string;
  resources?: SettingsResourceSummary[];
  list?: SettingsListPayload;
  detail?: SettingsResourceDetail | null;
  audit?: SettingsAuditPayload;
}

const page = ref<SettingsKindPayload | null>(null);
const selectedDetail = ref<SettingsResourceDetail | null>(null);
const selectedResourceId = ref<string | null>(null);
const isLoading = ref(false);
const detailLoading = ref(false);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const searchTerm = ref("");
const editorText = ref("");
const editorError = ref<string | null>(null);
const actionMessage = ref<string | null>(null);
const actionError = ref<string | null>(null);
const testError = ref<string | null>(null);
const isSaving = ref(false);
const isToggling = ref(false);
const isTesting = ref(false);
const testPrompt = ref("Reply with a short readiness check.");
const testResult = ref<LlmInvocationApiPayload | null>(null);

const resources = computed(() => page.value?.resources ?? []);
const backendTotal = computed(() => page.value?.list?.total ?? resources.value.length);
const listLimit = computed(() => page.value?.list?.limit ?? resources.value.length);
const listOffset = computed(() => page.value?.list?.offset ?? 0);

const filteredResources = computed(() => {
  const query = searchTerm.value.trim().toLowerCase();
  if (!query) return resources.value;
  return resources.value.filter((resource) => {
    const config = effectiveConfig(resource);
    return [
      resource.display_name,
      resource.resource_id,
      config.provider,
      config.api_family,
      config.model_name,
      config.model_family,
      resource.status,
      resource.source,
    ].some((value) => textValue(value, "").toLowerCase().includes(query));
  });
});

const profileRows = computed<TableRow[]>(() =>
  filteredResources.value.map((resource) => {
    const config = effectiveConfig(resource);
    return {
      Name: textValue(resource.display_name, resource.resource_id),
      ID: resource.resource_id,
      Provider: textValue(config.provider),
      "API Family": textValue(config.api_family),
      Model: textValue(config.model_name),
      Status: titleize(resource.status),
      Enabled: yesNo(resource.enabled),
      Source: textValue(resource.source),
      Version: textValue(resource.version),
      "Updated At": textValue(resource.updated_at),
    };
  }),
);

const selectedConfig = computed(() => selectedDetail.value?.effective_config ?? {});
const selectedResolution = computed(() => selectedDetail.value?.resolution ?? null);
const selectedSource = computed(() => selectedResolution.value?.source ?? null);
const validationStatus = computed(() => {
  const explicit = selectedDetail.value?.validation?.status;
  if (explicit) return explicit;
  return selectedResolution.value?.validation?.ok === true ? "valid" : "unknown";
});
const validationTone = computed<StatusTone>(() => toneForStatus(validationStatus.value));

const effectiveRows = computed<TableRow[]>(() =>
  objectRows(selectedConfig.value, [
    "provider",
    "api_family",
    "model_name",
    "model_family",
    "capabilities",
    "default_params",
    "base_url",
    "credential_binding",
    "timeout_seconds",
    "max_concurrency",
    "concurrency_key",
    "source_kind",
    "enabled",
  ]),
);

const payloadRows = computed<TableRow[]>(() => objectRows(selectedDetail.value?.payload ?? {}, []));

const resolutionRows = computed<TableRow[]>(() => {
  const sources = selectedResolution.value?.sources ?? [];
  return sources.map((source, index) => ({
    Step: index + 1,
    Kind: titleize(source.kind),
    Source: textValue(source.name ?? source.source_id),
    Version: textValue(source.version ?? source.version_id),
    Applied: yesNo(source.applied),
    Reason: textValue(source.reason),
  }));
});

const overrideRows = computed<TableRow[]>(() =>
  (selectedResolution.value?.override_trace ?? []).map((source, index) => ({
    Step: index + 1,
    Kind: titleize(source.kind),
    Source: textValue(source.name ?? source.source_id),
    Version: textValue(source.version ?? source.version_id),
    Applied: yesNo(source.applied),
    Reason: textValue(source.reason),
  })),
);

const validationRows = computed<TableRow[]>(() => {
  const checkRows = selectedDetail.value?.validation?.checks?.rows;
  if (checkRows?.length) return checkRows;
  const validation = selectedDetail.value?.validation?.result ?? selectedResolution.value?.validation;
  return [
    { Check: "schema", Result: validation?.ok === false ? "failed" : textValue(validationStatus.value) },
    { Check: "warnings", Result: String(validation?.warnings?.length ?? 0) },
    { Check: "errors", Result: String(validation?.errors?.length ?? 0) },
  ];
});

const versionRows = computed<TableRow[]>(() =>
  (selectedDetail.value?.versions ?? []).map((version) => ({
    Version: textValue(version.version_number, version.id ?? "-"),
    Status: titleize(version.status),
    Source: textValue(version.source),
    "Created By": textValue(version.created_by),
    "Created At": textValue(version.created_at),
    "Published At": textValue(version.published_at),
    Reason: textValue(version.reason),
  })),
);

const auditRows = computed<TableRow[]>(() => selectedDetail.value?.audit?.recent_changes?.rows ?? []);
const selectedStatusTone = computed<StatusTone>(() => toneForStatus(selectedDetail.value?.status));
const selectedTitle = computed(() => selectedDetail.value?.title ?? selectedDetail.value?.display_name ?? selectedDetail.value?.resource_id ?? "No profile selected");
const sourceCount = computed(() => selectedResolution.value?.sources?.length ?? 0);
const overrideCount = computed(() => selectedResolution.value?.override_trace?.length ?? 0);
const capabilities = computed(() => arrayValue(selectedConfig.value.capabilities));
const canRunOwnerAction = computed(() => Boolean(selectedResourceId.value && selectedDetail.value));
const testDisabledReason = computed(() => {
  if (!selectedResourceId.value) return "Select a profile before running a probe.";
  if (selectedDetail.value?.enabled === false) return "Disabled LLM profiles cannot be invoked.";
  return "Dedicated /test endpoint is not exposed; this probe uses /llms/{id}/invoke.";
});

onMounted(() => {
  void loadProfiles();
});

async function loadProfiles(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [profiles, overlay] = await Promise.all([
      listLlmProfiles(),
      loadSettingsOverlay(),
    ]);
    const payload = buildLlmProfilePage(profiles, overlay);
    page.value = payload;
    const firstResourceId = payload.resources?.[0]?.resource_id ?? null;
    selectedResourceId.value = firstResourceId;
    selectedDetail.value = payload.detail ?? null;
    syncEditorFromDetail();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    page.value = null;
    selectedDetail.value = null;
    selectedResourceId.value = null;
  } finally {
    isLoading.value = false;
  }
}

async function loadProfileDetail(resourceId: string): Promise<void> {
  detailLoading.value = true;
  detailError.value = null;
  selectedResourceId.value = resourceId;
  testResult.value = null;
  testError.value = null;
  try {
    selectedDetail.value = llmProfileToDetail(await getLlmProfile(resourceId));
    syncEditorFromDetail();
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

async function saveProfileJson(): Promise<void> {
  if (!selectedResourceId.value) return;
  isSaving.value = true;
  editorError.value = null;
  actionError.value = null;
  actionMessage.value = null;
  try {
    const payload = parseProfileWritePayload(editorText.value, selectedResourceId.value);
    const updated = await updateLlmProfile(selectedResourceId.value, payload);
    selectedDetail.value = llmProfileToDetail(updated);
    syncEditorFromDetail();
    actionMessage.value = `Updated ${updated.id} through the LLM module API.`;
    await refreshListKeepingSelection(updated.id);
  } catch (error) {
    editorError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isSaving.value = false;
  }
}

async function toggleProfileEnabled(enabled: boolean): Promise<void> {
  if (!selectedResourceId.value) return;
  isToggling.value = true;
  actionError.value = null;
  actionMessage.value = null;
  try {
    const updated = await setLlmProfileEnabled(selectedResourceId.value, enabled);
    selectedDetail.value = llmProfileToDetail(updated);
    syncEditorFromDetail();
    actionMessage.value = `${enabled ? "Enabled" : "Disabled"} ${updated.id} through the LLM module API.`;
    await refreshListKeepingSelection(updated.id);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isToggling.value = false;
  }
}

async function runProfileProbe(): Promise<void> {
  if (!selectedResourceId.value || selectedDetail.value?.enabled === false) return;
  isTesting.value = true;
  testError.value = null;
  testResult.value = null;
  try {
    testResult.value = await invokeLlmProfile(selectedResourceId.value, {
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

async function refreshListKeepingSelection(resourceId: string): Promise<void> {
  const [profiles, overlay] = await Promise.all([
    listLlmProfiles(),
    loadSettingsOverlay(),
  ]);
  page.value = buildLlmProfilePage(profiles, overlay, resourceId);
}

async function loadSettingsOverlay(): Promise<SettingsKindPayload | null> {
  try {
    return await listSettingsResources("llm-profiles", { limit: 1, offset: 0 }) as SettingsKindPayload;
  } catch {
    return null;
  }
}

function buildLlmProfilePage(
  profiles: LlmProfileApiPayload[],
  overlay: SettingsKindPayload | null,
  preferredResourceId?: string | null,
): SettingsKindPayload {
  const selectedProfile =
    profiles.find((profile) => profile.id === preferredResourceId) ?? profiles[0] ?? null;
  return {
    title: overlay?.title ?? "LLM Profiles",
    description: overlay?.description ?? "LLM module profiles with Settings governance overlay.",
    status: overlay?.status ?? (profiles.length ? "ready" : "empty"),
    resources: profiles.map(llmProfileToResource),
    list: {
      total: profiles.length,
      limit: profiles.length,
      offset: 0,
    },
    detail: selectedProfile ? llmProfileToDetail(selectedProfile) : null,
    audit: overlay?.audit,
  };
}

function llmProfileToResource(profile: LlmProfileApiPayload): SettingsResourceSummary {
  const effectiveConfig = llmProfileConfig(profile);
  return {
    id: profile.id,
    resource_id: profile.id,
    display_name: `${profile.provider} / ${profile.model_name}`,
    status: profile.enabled ? "ready" : "disabled",
    enabled: profile.enabled,
    source: "llm_module_api",
    version: null,
    updated_at: null,
    metadata: {
      owner: "llm",
      source_kind: profile.source_kind,
    },
    effective_config: effectiveConfig,
    resolution: ownerResolution("LLM module API", effectiveConfig),
  };
}

function llmProfileToDetail(profile: LlmProfileApiPayload): SettingsResourceDetail {
  return {
    ...llmProfileToResource(profile),
    title: `${profile.provider} / ${profile.model_name}`,
    payload: llmProfileConfig(profile),
    validation: {
      status: "owner-api",
      result: { ok: true, errors: [], warnings: [] },
      checks: {
        rows: [
          { Check: "truth source", Result: "LLM module API" },
          { Check: "settings role", Result: "governance overlay only" },
        ],
      },
    },
    audit: { recent_changes: { rows: [] } },
    versions: [],
  };
}

function llmProfileConfig(profile: LlmProfileApiPayload): Record<string, unknown> {
  return {
    id: profile.id,
    provider: profile.provider,
    api_family: profile.api_family,
    model_name: profile.model_name,
    context_window_tokens: profile.context_window_tokens,
    model_family: profile.model_family,
    capabilities: profile.capabilities,
    default_params: profile.default_params,
    base_url: profile.base_url,
    credential_binding: profile.credential_binding,
    timeout_seconds: profile.timeout_seconds,
    max_concurrency: profile.max_concurrency,
    concurrency_key: profile.concurrency_key,
    source_kind: profile.source_kind,
    enabled: profile.enabled,
  };
}

function ownerResolution(
  name: string,
  value: Record<string, unknown>,
): SettingsResolutionPayload {
  return {
    value,
    source: { kind: "owner_module", name },
    sources: [{ kind: "owner_module", name, version_id: null, applied: true }],
    override_trace: [],
    validation: { ok: true, errors: [], warnings: [] },
  };
}

function syncEditorFromDetail(): void {
  editorText.value = formatJson(selectedDetail.value?.payload ?? {});
  editorError.value = null;
}

function parseProfileWritePayload(text: string, expectedId: string): LlmProfileWritePayload {
  const parsed = parseJsonObject(text);
  if (parsed.id !== expectedId) {
    throw new Error("JSON id must match the selected LLM profile.");
  }
  return {
    id: stringField(parsed, "id"),
    provider: stringField(parsed, "provider"),
    api_family: stringField(parsed, "api_family"),
    model_name: stringField(parsed, "model_name"),
    context_window_tokens: nullableNumberField(parsed, "context_window_tokens"),
    model_family: stringField(parsed, "model_family", "general"),
    capabilities: stringArrayField(parsed, "capabilities"),
    default_params: defaultsField(parsed.default_params),
    base_url: nullableStringField(parsed, "base_url"),
    credential_binding: nullableStringField(parsed, "credential_binding"),
    timeout_seconds: numberField(parsed, "timeout_seconds", 60),
    max_concurrency: nullableNumberField(parsed, "max_concurrency"),
    concurrency_key: nullableStringField(parsed, "concurrency_key"),
    enabled: booleanField(parsed, "enabled", true),
  };
}

function parseJsonObject(text: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (error) {
    throw new Error(`Invalid JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
  if (!isRecord(value)) {
    throw new Error("Profile JSON must be an object.");
  }
  return value;
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function stringField(source: Record<string, unknown>, key: string, fallback?: string): string {
  const value = source[key];
  if (typeof value === "string" && value.trim()) return value;
  if (fallback !== undefined) return fallback;
  throw new Error(`Profile JSON must include string field "${key}".`);
}

function nullableStringField(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "string") return value;
  throw new Error(`Profile JSON field "${key}" must be a string or null.`);
}

function numberField(source: Record<string, unknown>, key: string, fallback: number): number {
  const value = source[key];
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new Error(`Profile JSON field "${key}" must be a number.`);
}

function nullableNumberField(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new Error(`Profile JSON field "${key}" must be a number or null.`);
}

function booleanField(source: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const value = source[key];
  if (value === null || value === undefined) return fallback;
  if (typeof value === "boolean") return value;
  throw new Error(`Profile JSON field "${key}" must be a boolean.`);
}

function stringArrayField(source: Record<string, unknown>, key: string): string[] {
  const value = source[key];
  if (value === null || value === undefined) return [];
  if (Array.isArray(value) && value.every((item) => typeof item === "string")) return value;
  throw new Error(`Profile JSON field "${key}" must be a string array.`);
}

function defaultsField(value: unknown): LlmProfileWritePayload["default_params"] {
  if (value === null || value === undefined) return { extra_body: {} };
  if (!isRecord(value)) throw new Error('Profile JSON field "default_params" must be an object.');
  const extraBody = value.extra_body;
  return {
    temperature: optionalNumberValue(value.temperature, "default_params.temperature"),
    top_p: optionalNumberValue(value.top_p, "default_params.top_p"),
    max_output_tokens: optionalNumberValue(value.max_output_tokens, "default_params.max_output_tokens"),
    reasoning_effort: optionalStringValue(value.reasoning_effort, "default_params.reasoning_effort"),
    extra_body: isRecord(extraBody) ? extraBody : {},
  };
}

function optionalNumberValue(value: unknown, label: string): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new Error(`${label} must be a number or null.`);
}

function optionalStringValue(value: unknown, label: string): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "string") return value;
  throw new Error(`${label} must be a string or null.`);
}

function selectProfile(row: unknown): void {
  const resourceId = rowValue(row, "ID");
  if (resourceId && resourceId !== selectedResourceId.value) {
    void loadProfileDetail(resourceId);
  }
}

function effectiveConfig(resource: SettingsResourceSummary): Record<string, unknown> {
  return resource.effective_config ?? {};
}

function rowValue(row: unknown, key: string): string | null {
  if (!isRecord(row)) return null;
  const value = row[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function objectRows(source: Record<string, unknown>, preferredKeys: string[]): TableRow[] {
  const entries = Object.entries(source);
  const orderedKeys = [
    ...preferredKeys.filter((key) => Object.prototype.hasOwnProperty.call(source, key)),
    ...entries.map(([key]) => key).filter((key) => !preferredKeys.includes(key)),
  ];
  return orderedKeys.map((key) => ({
    Setting: humanizeKey(key),
    Value: shortValue(source[key]),
  }));
}

function arrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => textValue(item, "")).filter(Boolean);
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

function shortValue(value: unknown): string {
  const text = textValue(value);
  return text.length > 160 ? `${text.slice(0, 157)}...` : text;
}

function yesNo(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
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

function humanizeKey(value: string): string {
  return titleize(value);
}

function toneForStatus(value: unknown): StatusTone {
  const text = textValue(value, "").toLowerCase();
  if (/(failed|invalid|error|disabled|blocked)/.test(text)) return "danger";
  if (/(warning|draft|pending|unknown)/.test(text)) return "warning";
  if (/(active|ready|valid|success|published|enabled)/.test(text)) return "success";
  if (text) return "info";
  return "neutral";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
</script>

<template>
  <main class="settings-module llm-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>LLM Profiles</h1>
        <p>Owner view from <code>/llms</code>. Settings only contributes governance ownership and policy overlay.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" @click="loadProfiles"><RefreshCcw :size="14" /> Refresh</UiButton>
      </div>
    </header>

    <section class="llm-summary-grid">
      <article class="settings-panel llm-summary-card">
        <span><Layers :size="18" /></span>
        <div><small>Owner total</small><strong>{{ backendTotal }}</strong><p>Count from the LLM module API.</p></div>
      </article>
      <article class="settings-panel llm-summary-card">
        <span><Shield :size="18" /></span>
        <div><small>Health</small><strong>{{ titleize(page?.status ?? "unknown") }}</strong><p>{{ page?.description ?? "Loading Settings status." }}</p></div>
      </article>
      <article class="settings-panel llm-summary-card">
        <span><GitBranch :size="18" /></span>
        <div><small>Selected source</small><strong>{{ textValue(selectedSource?.name ?? selectedDetail?.source) }}</strong><p>{{ sourceCount }} resolution sources, {{ overrideCount }} overrides.</p></div>
      </article>
      <article class="settings-panel llm-summary-card">
        <span><CheckCircle2 :size="18" /></span>
        <div><small>Validation</small><strong>{{ titleize(validationStatus) }}</strong><p>{{ selectedDetail?.validation?.last_validated_at ?? "No validation timestamp yet." }}</p></div>
      </article>
    </section>

    <section class="llm-toolbar">
      <label>
        <Search :size="14" />
        <input v-model="searchTerm" placeholder="Search loaded LLM profiles..." />
      </label>
      <button type="button" aria-label="Filters are local to loaded rows"><ListFilter :size="14" /></button>
    </section>

    <section class="settings-panel llm-list">
      <div v-if="isLoading" class="settings-state">Loading LLM profiles from owner API...</div>
      <div v-else-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
      <div v-else-if="!resources.length" class="settings-state">No LLM profiles were returned. Create, update, enable, and disable profiles through the LLM module API.</div>
      <DataTable
        v-else
        :columns="['Name', 'ID', 'Provider', 'API Family', 'Model', 'Status', 'Enabled', 'Source', 'Version', 'Updated At']"
        :rows="profileRows"
        section-id="llm-profiles"
        clickable-rows
        @row-click="selectProfile"
      />
      <footer>Showing {{ profileRows.length }} loaded rows from {{ backendTotal }} owner profiles (limit {{ listLimit }}, offset {{ listOffset }}).</footer>
    </section>

    <section v-if="resources.length || selectedDetail || detailLoading" class="llm-detail-layout">
      <div class="llm-main-column">
        <article class="settings-panel llm-editor">
          <aside class="llm-editor-tabs">
            <button class="active" type="button">Resource</button>
            <button type="button">Effective Config</button>
            <button type="button">Resolution</button>
            <button type="button">Validation</button>
            <button type="button">Versions</button>
            <button type="button">Audit</button>
          </aside>

          <div class="llm-form">
            <div v-if="detailLoading" class="settings-state detail-state">Loading selected profile...</div>
            <div v-else-if="detailError" class="settings-state settings-state--error detail-state">{{ detailError }}</div>
            <template v-else-if="selectedDetail">
              <header>
                <div class="profile-title">
                  <h2>{{ selectedTitle }}</h2>
                  <em><StatusDot :tone="selectedStatusTone" />{{ titleize(selectedDetail.status) }}</em>
                  <span>{{ selectedDetail.enabled ? "Enabled" : "Disabled" }}</span>
                </div>
              </header>

              <div class="profile-id">
                <span>ID <code>{{ selectedDetail.resource_id }}</code></span>
                <Copy :size="13" />
                <span>Version {{ textValue(selectedDetail.version) }}</span>
              </div>

              <section class="llm-form-grid">
                <article>
                  <h3><Shield :size="15" />Governed Provider</h3>
                  <dl class="settings-kv">
                    <div><dt>Provider</dt><dd>{{ textValue(selectedConfig.provider) }}</dd></div>
                    <div><dt>API Family</dt><dd>{{ textValue(selectedConfig.api_family) }}</dd></div>
                    <div><dt>Model</dt><dd>{{ textValue(selectedConfig.model_name) }}</dd></div>
                    <div><dt>Credential Binding</dt><dd>{{ textValue(selectedConfig.credential_binding) }}</dd></div>
                  </dl>
                </article>

                <article>
                  <h3>Resource State</h3>
                  <dl class="settings-kv">
                    <div><dt>Status</dt><dd>{{ titleize(selectedDetail.status) }}</dd></div>
                    <div><dt>Enabled</dt><dd>{{ yesNo(selectedDetail.enabled) }}</dd></div>
                    <div><dt>Source</dt><dd>{{ textValue(selectedDetail.source) }}</dd></div>
                    <div><dt>Updated</dt><dd>{{ textValue(selectedDetail.updated_at) }}</dd></div>
                  </dl>
                </article>

                <article class="llm-notes">
                  <h3>Configured Capabilities</h3>
                  <div class="settings-chip-row">
                    <span v-for="capability in capabilities" :key="capability">{{ titleize(capability) }}</span>
                    <span v-if="!capabilities.length">No capability list in Settings payload.</span>
                  </div>
                </article>
              </section>

              <dl class="llm-meta-strip">
                <div><dt>Snapshot</dt><dd>{{ textValue(selectedResolution?.snapshot_id) }}</dd></div>
                <div><dt>Resolved At</dt><dd>{{ textValue(selectedResolution?.resolved_at) }}</dd></div>
                <div><dt>Sources</dt><dd>{{ sourceCount }}</dd></div>
                <div><dt>Overrides</dt><dd>{{ overrideCount }}</dd></div>
              </dl>
            </template>
            <div v-else class="settings-state detail-state">Select a profile to inspect its owner detail.</div>
          </div>
        </article>

        <article class="settings-panel effective-preview">
          <div class="settings-panel-heading"><h3>Effective Configuration</h3><span>Owner detail</span></div>
          <DataTable v-if="effectiveRows.length" :columns="['Setting', 'Value']" :rows="effectiveRows" section-id="llm-effective-config" />
          <div v-else class="settings-state settings-state--compact">No effective configuration returned for the selected profile.</div>
        </article>

        <article class="settings-panel llm-json-editor">
          <div class="settings-panel-heading">
            <div>
              <h3>Profile JSON</h3>
              <span>Writes go to <code>PUT /llms/{{ selectedResourceId ?? ":id" }}</code></span>
            </div>
            <UiButton
              size="sm"
              variant="primary"
              :disabled="!canRunOwnerAction || isSaving"
              @click="saveProfileJson"
            >
              <Save :size="13" /> {{ isSaving ? "Saving" : "Save" }}
            </UiButton>
          </div>
          <textarea v-model="editorText" spellcheck="false" :disabled="!selectedDetail || isSaving" />
          <p v-if="editorError" class="llm-inline-error">{{ editorError }}</p>
          <p v-else>Credential binding is a read-only reference label from the LLM owner response. Readiness stays in Access.</p>
          <DataTable v-if="payloadRows.length" :columns="['Setting', 'Value']" :rows="payloadRows" section-id="llm-payload" />
          <div v-else class="settings-state settings-state--compact">No payload returned for the selected profile.</div>
        </article>
      </div>

      <aside class="llm-summary-stack">
        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Resolution Trace</h2><span>{{ sourceCount }} sources</span></div>
          <DataTable v-if="resolutionRows.length" :columns="['Step', 'Kind', 'Source', 'Version', 'Applied', 'Reason']" :rows="resolutionRows" section-id="llm-resolution" />
          <div v-else class="settings-state settings-state--compact">No resolution sources returned.</div>
          <DataTable v-if="overrideRows.length" class="llm-overrides" :columns="['Step', 'Kind', 'Source', 'Version', 'Applied', 'Reason']" :rows="overrideRows" section-id="llm-overrides" />
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Validation</h2><span><StatusDot :tone="validationTone" />{{ titleize(validationStatus) }}</span></div>
          <DataTable :columns="['Check', 'Result']" :rows="validationRows" section-id="llm-validation" />
        </article>

        <article class="settings-panel llm-owner-actions">
          <div class="settings-panel-heading">
            <h2>Owner Actions</h2>
            <span>/llms</span>
          </div>
          <div class="llm-action-row">
            <UiButton
              size="sm"
              variant="secondary"
              :disabled="!canRunOwnerAction || selectedDetail?.enabled === true || isToggling"
              @click="toggleProfileEnabled(true)"
            >
              Enable
            </UiButton>
            <UiButton
              size="sm"
              variant="secondary"
              :disabled="!canRunOwnerAction || selectedDetail?.enabled === false || isToggling"
              @click="toggleProfileEnabled(false)"
            >
              Disable
            </UiButton>
          </div>
          <p>Enable and disable call the LLM module directly. Settings does not use the generic write proxy here.</p>
          <p v-if="actionMessage" class="llm-inline-success">{{ actionMessage }}</p>
          <p v-if="actionError" class="llm-inline-error">{{ actionError }}</p>
        </article>

        <article class="settings-panel llm-test-panel">
          <div class="settings-panel-heading">
            <h2>Probe</h2>
            <span>/invoke</span>
          </div>
          <textarea v-model="testPrompt" spellcheck="false" />
          <UiButton
            size="sm"
            variant="primary"
            :disabled="!canRunOwnerAction || selectedDetail?.enabled === false || isTesting"
            @click="runProfileProbe"
          >
            <Play :size="13" /> {{ isTesting ? "Running" : "Run Probe" }}
          </UiButton>
          <p>{{ testDisabledReason }}</p>
          <p v-if="testError" class="llm-inline-error">{{ testError }}</p>
          <pre v-if="testResult">{{ formatJson(testResult) }}</pre>
          <div v-else class="settings-state settings-state--compact">No probe result yet.</div>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Versions</h2><span>{{ versionRows.length }}</span></div>
          <DataTable v-if="versionRows.length" :columns="['Version', 'Status', 'Source', 'Created By', 'Created At', 'Published At', 'Reason']" :rows="versionRows" section-id="llm-versions" />
          <div v-else class="settings-state settings-state--compact">No versions returned for this profile.</div>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Settings Audit</h2><span>{{ auditRows.length }}</span></div>
          <DataTable v-if="auditRows.length" :columns="['Audit ID', 'Action', 'Target', 'Status', 'Actor', 'Reason']" :rows="auditRows" section-id="llm-audit" />
          <div v-else class="settings-state settings-state--compact">No Settings audit entries yet.</div>
          <a class="panel-link" href="/settings/audit-logs">Open audit logs <ArrowRight :size="12" /></a>
        </article>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><Brain :size="14" />Truth source: LLM module API</span>
      <span><GitBranch :size="14" />Detail: /llms/{{ selectedResourceId ?? ":id" }}</span>
      <span><Shield :size="14" />Settings provides governance, validation, and audit only.</span>
    </footer>
  </main>
</template>

<style scoped>
.llm-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.llm-summary-card {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 88px;
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

.llm-summary-card small,
.llm-summary-card p {
  color: var(--text-muted);
  font-size: 11px;
}

.llm-summary-card strong {
  display: block;
  overflow: hidden;
  margin: 3px 0;
  color: var(--text-primary);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-toolbar {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) 34px;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}

.llm-toolbar label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-muted);
}

.llm-toolbar input,
.llm-toolbar button {
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.llm-toolbar input {
  border: 0;
  outline: 0;
  background: transparent;
}

.llm-toolbar button {
  display: grid;
  place-items: center;
  padding: 0;
}

.llm-list {
  padding: 0;
  overflow: hidden;
}

.llm-list :deep(tbody tr:first-child) {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.llm-list :deep(td:first-child) {
  position: relative;
  padding-left: 38px;
  color: var(--text-primary);
  font-weight: 750;
}

.llm-list :deep(td:first-child)::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 12px;
  width: 18px;
  height: 18px;
  transform: translateY(-50%);
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-gray) 22%, transparent);
}

.llm-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.llm-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.llm-main-column {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.llm-editor {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.llm-editor-tabs {
  display: grid;
  align-content: start;
  gap: 1px;
  padding: 6px;
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 72%, transparent);
}

.llm-editor-tabs button {
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

.llm-editor-tabs .active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.llm-form {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
}

.llm-form header,
.profile-title,
.profile-id,
.llm-form-grid h3,
.panel-link {
  display: flex;
  align-items: center;
}

.llm-form header {
  justify-content: space-between;
  gap: 10px;
}

.profile-title {
  flex-wrap: wrap;
  gap: 8px;
}

.profile-title h2 {
  font-size: 16px;
}

.profile-title span,
.profile-title em {
  min-height: 20px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-accent) 18%, transparent);
  color: var(--color-accent);
  font-size: 11px;
  font-style: normal;
}

.profile-title em {
  display: inline-flex;
  gap: 5px;
  background: transparent;
  color: var(--text-secondary);
}

.profile-id {
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.profile-id code {
  color: var(--text-primary);
}

.llm-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 10px;
}

.llm-form-grid article,
.llm-meta-strip {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel-soft) 74%, transparent);
}

.llm-form-grid article {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
}

.llm-notes {
  grid-column: 1 / -1;
}

.llm-form-grid h3 {
  gap: 7px;
  font-size: 13px;
}

.llm-meta-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.llm-meta-strip div {
  display: grid;
  gap: 4px;
  min-height: 42px;
  padding: 8px 10px;
  border-right: 1px solid var(--border-subtle);
}

.llm-meta-strip dt {
  color: var(--text-muted);
  font-size: 10.5px;
}

.llm-meta-strip dd {
  overflow: hidden;
  margin: 0;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.llm-summary-stack {
  display: grid;
  align-content: start;
  gap: 8px;
}

.llm-summary-stack .settings-panel {
  padding: 10px 12px;
}

.llm-summary-stack :deep(th),
.llm-summary-stack :deep(td),
.effective-preview :deep(th),
.effective-preview :deep(td) {
  padding-block: 4px;
  font-size: 10.5px;
}

.llm-overrides {
  margin-top: 8px;
}

.llm-json-editor {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
}

.llm-json-editor textarea,
.llm-test-panel textarea,
.llm-test-panel pre {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
}

.llm-json-editor textarea {
  min-height: 220px;
  max-height: 340px;
  resize: vertical;
  padding: 10px;
}

.llm-json-editor p,
.llm-owner-actions p,
.llm-test-panel p {
  margin: 0;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.45;
}

.llm-owner-actions,
.llm-test-panel {
  display: grid;
  gap: 8px;
}

.llm-action-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.llm-test-panel textarea {
  min-height: 72px;
  resize: vertical;
  padding: 8px;
}

.llm-test-panel pre {
  overflow: auto;
  max-height: 180px;
  margin: 0;
  padding: 8px;
  white-space: pre-wrap;
}

.llm-inline-error {
  color: var(--color-danger) !important;
}

.llm-inline-success {
  color: var(--color-success) !important;
}

.panel-link {
  gap: 5px;
  margin-top: 8px;
  color: var(--color-accent);
  font-size: 11px;
  text-decoration: none;
}

.settings-state {
  display: grid;
  place-items: center;
  min-height: 168px;
  padding: 18px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

.settings-state--compact {
  min-height: 74px;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-2);
}

.settings-state--error {
  color: var(--color-danger);
}

.detail-state {
  min-height: 300px;
}
</style>
