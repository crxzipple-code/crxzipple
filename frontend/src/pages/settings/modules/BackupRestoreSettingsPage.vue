<script setup lang="ts">
import { Archive, GitBranch, RefreshCcw, Shield } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

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

const backupRows = computed(() =>
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
  void loadBackupRestore();
});

async function loadBackupRestore(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    settingsPage.value = await listSettingsResources("backup-restore") as SettingsResourcePagePayload;
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
  <main class="settings-module backup-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Backup / Restore</h1>
        <p>No backend backup workflow, storage policy, dry-run, or restore flow is currently connected. This page is intentionally out of the main Settings navigation.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" @click="loadBackupRestore"><RefreshCcw :size="14" /> {{ t("common.refresh") }}</UiButton>
      </div>
    </header>

    <section class="settings-panel backup-notice">
      <Archive :size="20" />
      <div>
        <h2>Placeholder only</h2>
        <p>Settings may return placeholder configuration resources at /ui/settings/backup-restore, but this UI does not show backup inventories or restore actions until the backend workflows exist.</p>
      </div>
    </section>

    <section class="settings-panel backup-list">
      <div v-if="loadError" class="backup-empty">{{ loadError }}</div>
      <div v-else-if="isLoading" class="backup-empty">Loading backup placeholder resources...</div>
      <DataTable
        v-else
        :columns="['Name', 'ID', 'Status', 'Source', 'Version', 'Updated At']"
        :rows="backupRows"
        section-id="backup-restore-placeholder"
      />
      <footer>Showing {{ backupRows.length }} of {{ settingsPage?.list?.total ?? backupRows.length }} Settings resources</footer>
    </section>

    <section v-if="selectedResource" class="backup-detail-grid">
      <article class="settings-panel">
        <div class="settings-panel-heading"><h2>Placeholder Resource</h2><span>{{ settingsResourceId(selectedResource) }}</span></div>
        <DataTable :columns="['Key', 'Value']" :rows="selectedRows" section-id="backup-placeholder-detail" />
      </article>
      <article class="settings-panel">
        <div class="settings-panel-heading"><h2>Hidden Until Backend Exists</h2><span>Workflow absent</span></div>
        <dl class="settings-kv">
          <div><dt>Backup list</dt><dd>Hidden</dd></div>
          <div><dt>Create backup</dt><dd>Hidden</dd></div>
          <div><dt>Restore dry-run</dt><dd>Hidden</dd></div>
          <div><dt>Restore flow</dt><dd>Hidden</dd></div>
        </dl>
      </article>
    </section>

    <section v-else class="settings-panel backup-empty-state">
      <Archive :size="22" />
      <h2>No backup Settings resources</h2>
      <p>/ui/settings/backup-restore returned no Settings-owned resources, and no backup inventory is synthesized.</p>
    </section>

    <footer class="settings-footer">
      <span><Archive :size="14" />Config source: /ui/settings/backup-restore</span>
      <span><GitBranch :size="14" />No backup workflow backend is connected</span>
      <span><Shield :size="14" />No fake backup inventory is rendered</span>
    </footer>
  </main>
</template>

<style scoped>
.backup-notice {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 10px;
}

.backup-notice svg {
  color: var(--color-warning);
}

.backup-notice h2 {
  font-size: 14px;
}

.backup-notice p,
.backup-empty {
  color: var(--text-muted);
  font-size: 12px;
}

.backup-list {
  padding: 0;
  overflow: hidden;
}

.backup-empty {
  padding: 22px;
}

.backup-list footer {
  min-height: 30px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.backup-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(260px, 0.8fr);
  gap: 10px;
  margin-top: 10px;
}

.backup-empty-state {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 220px;
  margin-top: 10px;
  color: var(--text-muted);
  text-align: center;
}

.backup-empty-state h2 {
  color: var(--text-primary);
  font-size: 15px;
}
</style>
