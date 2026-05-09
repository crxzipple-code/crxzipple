<script setup lang="ts">
import { ArrowRight, FileClock, GitBranch, RefreshCcw, Shield } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
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

const eventRegistryRows = computed(() =>
  resources.value.map((resource) => ({
    Name: textValue(resource.display_name, settingsResourceId(resource)),
    ID: settingsResourceId(resource),
    Status: resource.enabled === false ? t("text.disabled") : textValue(resource.status, "placeholder"),
    Source: textValue(resource.source, resource.resolution?.source?.name ?? "settings_application"),
    Version: textValue(resource.version, "-"),
    "Updated At": formatTime(resource.updated_at),
  })),
);

const selectedRows = computed(() =>
  Object.entries(selectedConfig.value).slice(0, 12).map(([key, value]) => ({
    Key: key,
    Value: formatValue(value),
  })),
);

onMounted(() => {
  void loadEventRegistry();
});

async function loadEventRegistry(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    settingsPage.value = await listSettingsResources("event-registry") as SettingsResourcePagePayload;
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

function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => textValue(item, String(item))).join(", ") || "-";
  if (value && typeof value === "object") return JSON.stringify(value);
  return textValue(value, "-");
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", " UTC");
}
</script>

<template>
  <main class="settings-module event-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Event Registry</h1>
        <p>Settings currently exposes this as a placeholder read model. Event contracts are not editable from Settings.</p>
      </div>
      <div class="settings-header-actions">
        <RouterLink class="event-link-button" to="/operations/events">Operations Events <ArrowRight :size="12" /></RouterLink>
        <UiButton size="sm" variant="secondary" @click="loadEventRegistry"><RefreshCcw :size="14" /> {{ t("common.refresh") }}</UiButton>
      </div>
    </header>

    <section class="settings-panel event-notice">
      <FileClock :size="20" />
      <div>
        <h2>Read-only and intentionally out of main navigation</h2>
        <p>The Events module remains the owner of event definitions and runtime observation. This Settings page only shows any Settings-owned placeholder resources returned by /ui/settings/event-registry.</p>
      </div>
    </section>

    <section class="settings-panel event-list">
      <div v-if="loadError" class="event-empty">{{ loadError }}</div>
      <div v-else-if="isLoading" class="event-empty">Loading event registry placeholder...</div>
      <DataTable
        v-else
        :columns="['Name', 'ID', 'Status', 'Source', 'Version', 'Updated At']"
        :rows="eventRegistryRows"
        section-id="event-registry"
      />
      <footer>Showing {{ eventRegistryRows.length }} of {{ settingsPage?.list?.total ?? eventRegistryRows.length }} Settings resources</footer>
    </section>

    <section v-if="selectedResource" class="event-detail-grid">
      <article class="settings-panel">
        <div class="settings-panel-heading"><h2>Placeholder Resource</h2><span>{{ settingsResourceId(selectedResource) }}</span></div>
        <DataTable :columns="['Key', 'Value']" :rows="selectedRows" section-id="event-registry-placeholder-detail" />
      </article>
      <article class="settings-panel">
        <div class="settings-panel-heading"><h2>Boundary</h2><span>Read-only</span></div>
        <dl class="settings-kv">
          <div><dt>Settings source</dt><dd>/ui/settings/event-registry</dd></div>
          <div><dt>Event truth</dt><dd>Events registry / Operations Events</dd></div>
          <div><dt>Write actions</dt><dd>Hidden</dd></div>
        </dl>
      </article>
    </section>

    <section v-else class="settings-panel event-empty-state">
      <FileClock :size="22" />
      <h2>No Settings event registry resources</h2>
      <p>This is expected while event registry governance remains outside Settings.</p>
    </section>

    <footer class="settings-footer">
      <span><FileClock :size="14" />Config source: /ui/settings/event-registry</span>
      <span><GitBranch :size="14" />Definitions remain owned by Events</span>
      <span><Shield :size="14" />No event editing workflow is exposed</span>
    </footer>
  </main>
</template>

<style scoped>
.event-link-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  color: var(--text-primary);
  font-size: 12px;
  text-decoration: none;
}

.event-notice {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 10px;
}

.event-notice svg {
  color: var(--color-warning);
}

.event-notice h2 {
  font-size: 14px;
}

.event-notice p,
.event-empty {
  color: var(--text-muted);
  font-size: 12px;
}

.event-list {
  padding: 0;
  overflow: hidden;
}

.event-empty {
  padding: 22px;
}

.event-list footer {
  min-height: 30px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.event-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(260px, 0.8fr);
  gap: 10px;
  margin-top: 10px;
}

.event-empty-state {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 220px;
  margin-top: 10px;
  color: var(--text-muted);
  text-align: center;
}

.event-empty-state h2 {
  color: var(--text-primary);
  font-size: 15px;
}
</style>
