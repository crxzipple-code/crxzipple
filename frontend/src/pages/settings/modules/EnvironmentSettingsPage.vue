<script setup lang="ts">
import { Box, GitBranch, Info, RefreshCcw, Shield } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { listSettingsResources } from "../api";

type JsonRecord = Record<string, unknown>;

interface SettingsResourceSummaryPayload {
  id?: string;
  resource_id?: string;
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
    override_trace?: unknown[];
  };
}

interface SettingsResourcePagePayload {
  resource?: string;
  status?: string;
  description?: string;
  resources?: SettingsResourceSummaryPayload[];
  list?: {
    total?: number;
  };
}

const settingsPage = ref<SettingsResourcePagePayload | null>(null);
const isLoading = ref(false);
const loadError = ref<string | null>(null);
const { t } = useI18n();

const resources = computed(() => settingsPage.value?.resources ?? []);
const selectedResource = computed(() => resources.value[0] ?? null);
const selectedConfig = computed(() => selectedResource.value ? resourceConfig(selectedResource.value) : {});

const environmentRows = computed(() =>
  resources.value.map((resource) => {
    const config = resourceConfig(resource);
    return {
      Name: textValue(resource.display_name, settingsResourceId(resource)),
      Environment: textValue(config.environment, settingsResourceId(resource)),
      Status: resource.enabled === false ? t("text.disabled") : textValue(resource.status, "ready"),
      Source: textValue(resource.source, resource.resolution?.source?.name ?? "settings_application"),
      Version: textValue(resource.version, "-"),
      "Updated At": formatTime(resource.updated_at),
    };
  }),
);

const effectiveRows = computed(() =>
  Object.entries(selectedConfig.value)
    .filter(([key]) => key !== "metadata")
    .map(([key, value]) => ({
      Key: key,
      Value: formatConfigValue(key, value),
    })),
);

const metadataRows = computed(() => {
  const metadata = objectValue(selectedConfig.value.metadata) ?? objectValue(selectedResource.value?.metadata) ?? {};
  return Object.entries(metadata).slice(0, 10).map(([key, value]) => ({
    Key: key,
    Value: formatConfigValue(key, value),
  }));
});

const resolutionRows = computed(() => {
  const source = selectedResource.value?.resolution?.source;
  const overrideTrace = selectedResource.value?.resolution?.override_trace;
  return [
    {
      Layer: "Effective environment",
      Source: textValue(source?.name, textValue(selectedResource.value?.source, "settings_application")),
      Overrides: String(Array.isArray(overrideTrace) ? overrideTrace.length : 0),
    },
  ];
});

const environmentName = computed(() =>
  textValue(selectedConfig.value.environment, selectedResource.value ? settingsResourceId(selectedResource.value) : "-"),
);

onMounted(() => {
  void loadEnvironment();
});

async function loadEnvironment(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    settingsPage.value = await listSettingsResources("environment") as SettingsResourcePagePayload;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    settingsPage.value = null;
  } finally {
    isLoading.value = false;
  }
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

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function formatConfigValue(key: string, value: unknown): string {
  if (isSensitiveKey(key)) return "***";
  if (typeof value === "string") return maskUrlCredentials(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item) => formatConfigValue(key, item)).join(", ") || "-";
  if (value && typeof value === "object") {
    return JSON.stringify(redactRecord(value as JsonRecord));
  }
  return "-";
}

function redactRecord(value: JsonRecord): JsonRecord {
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      isSensitiveKey(key)
        ? "***"
        : item && typeof item === "object" && !Array.isArray(item)
          ? redactRecord(item as JsonRecord)
          : typeof item === "string"
            ? maskUrlCredentials(item)
            : item,
    ]),
  );
}

function isSensitiveKey(key: string): boolean {
  return /(api[_-]?key|token|secret|password|credential|private[_-]?key)/i.test(key);
}

function maskUrlCredentials(value: string): string {
  const masked = value.replace(/\/\/([^:/\s]+):([^@\s]+)@/g, "//***:***@");
  if (masked !== value) return masked;
  try {
    const parsed = new URL(value);
    if (parsed.username || parsed.password) {
      parsed.username = "***";
      parsed.password = "***";
      return parsed.toString();
    }
  } catch {
    return value;
  }
  return value;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", " UTC");
}
</script>

<template>
  <main class="settings-module environment-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Effective Environment</h1>
        <p>Read-only effective environment resolved by Settings. Variable editors, secret editors, groups, and import/export are hidden until backend workflows exist.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" @click="loadEnvironment"><RefreshCcw :size="14" /> {{ t("common.refresh") }}</UiButton>
      </div>
    </header>

    <section class="settings-panel environment-info-band">
      <article><Info :size="16" /><div><span>Settings Read Model</span><small>Configuration source is /ui/settings/environment.</small></div></article>
      <article><GitBranch :size="16" /><div><span>Resolution</span><small>Values are effective Settings output, not a local editor buffer.</small></div></article>
      <article><Shield :size="16" /><div><span>Secrets</span><small>Sensitive keys and URL credentials are masked in this page.</small></div></article>
    </section>

    <section class="settings-panel environment-list-panel">
      <div v-if="loadError" class="environment-empty">{{ loadError }}</div>
      <div v-else-if="isLoading" class="environment-empty">Loading effective environment...</div>
      <DataTable
        v-else
        :columns="['Name', 'Environment', 'Status', 'Source', 'Version', 'Updated At']"
        :rows="environmentRows"
        section-id="environment-effective-resources"
      />
      <footer>Showing {{ environmentRows.length }} of {{ settingsPage?.list?.total ?? environmentRows.length }} Settings resources</footer>
    </section>

    <section v-if="selectedResource" class="environment-layout">
      <section class="settings-panel environment-detail">
        <header>
          <div class="environment-title">
            <span><Box :size="19" /></span>
            <div>
              <h2>{{ environmentName }} <em><StatusDot :tone="selectedResource.enabled === false ? 'warning' : 'success'" />{{ selectedResource.enabled === false ? t("text.disabled") : textValue(selectedResource.status, "ready") }}</em></h2>
              <p>ID: <code>{{ settingsResourceId(selectedResource) }}</code></p>
            </div>
          </div>
        </header>

        <div class="environment-overview-grid">
          <article>
            <h3>Effective Values</h3>
            <DataTable :columns="['Key', 'Value']" :rows="effectiveRows" section-id="environment-effective-values" />
          </article>
          <article>
            <h3>Resolution Trace</h3>
            <DataTable :columns="['Layer', 'Source', 'Overrides']" :rows="resolutionRows" section-id="environment-resolution-trace" />
          </article>
          <article>
            <h3>Resource Metadata</h3>
            <DataTable :columns="['Key', 'Value']" :rows="metadataRows" section-id="environment-metadata" />
          </article>
        </div>
      </section>
    </section>

    <section v-else class="settings-panel environment-empty-state">
      <Box :size="22" />
      <h2>No environment resources</h2>
      <p>/ui/settings/environment returned no Settings-owned effective environment resources.</p>
    </section>

    <footer class="settings-footer">
      <span><Box :size="14" />Config source: /ui/settings/environment</span>
      <span><GitBranch :size="14" />Read-only effective Settings resolution</span>
      <span><Shield :size="14" />No secret values are rendered</span>
    </footer>
  </main>
</template>

<style scoped>
.environment-info-band {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin-bottom: 10px;
  padding: 0;
  overflow: hidden;
}

.environment-info-band article {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  min-height: 82px;
  padding: 18px 20px;
  border-right: 1px solid var(--border-subtle);
}

.environment-info-band article:last-child {
  border-right: 0;
}

.environment-info-band article > svg {
  color: var(--color-blue);
  margin-top: 2px;
}

.environment-info-band span,
.environment-info-band small {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

.environment-info-band span {
  color: var(--text-primary);
  font-weight: 750;
}

.environment-list-panel {
  padding: 0;
  overflow: hidden;
}

.environment-list-panel footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.environment-empty {
  padding: 22px;
  color: var(--text-muted);
  font-size: 12px;
}

.environment-layout {
  display: grid;
  gap: 12px;
  margin-top: 10px;
}

.environment-detail {
  padding: 0;
  overflow: hidden;
}

.environment-detail > header,
.environment-title,
.environment-title h2,
.environment-title p {
  display: flex;
  align-items: center;
}

.environment-detail > header {
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.environment-title {
  gap: 10px;
}

.environment-title > span {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-accent) 22%, transparent);
  color: var(--color-accent);
}

.environment-title h2 {
  gap: 9px;
  font-size: 16px;
}

.environment-title h2 em {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 7px;
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
  font-size: 11px;
  font-style: normal;
}

.environment-title p {
  gap: 6px;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 11px;
}

.environment-overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(240px, 0.8fr) minmax(240px, 0.8fr);
  gap: 10px;
  padding: 12px;
}

.environment-overview-grid article {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-elevated) 70%, transparent);
}

.environment-overview-grid h3 {
  margin-bottom: 9px;
  font-size: 13px;
}

.environment-empty-state {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 220px;
  margin-top: 10px;
  color: var(--text-muted);
  text-align: center;
}

.environment-empty-state h2 {
  color: var(--text-primary);
  font-size: 15px;
}
</style>
