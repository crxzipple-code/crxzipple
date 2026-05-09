<script setup lang="ts">
import {
  ArrowRight,
  CalendarDays,
  Download,
  FileClock,
  GitBranch,
  ListFilter,
  MoreVertical,
  RefreshCcw,
  Save,
  Search,
  User,
  X,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import UiButton from "@/shared/ui/UiButton.vue";
import { getSettingsResource, listSettingsResources } from "../api";

interface SettingsAuditPayload {
  audit_id?: string;
  id?: string;
  action?: string;
  action_type?: string;
  kind?: string;
  resource_id?: string | null;
  actor?: string | null;
  reason?: string | null;
  risk?: string | null;
  dry_run?: boolean;
  status?: string;
  request_metadata?: unknown;
  result?: unknown;
  error?: unknown;
  created_at?: string;
  completed_at?: string;
}

interface SettingsAuditListPayload {
  total?: number;
  limit?: number;
  offset?: number;
}

interface SettingsAuditPagePayload {
  title?: string;
  description?: string;
  status?: string;
  resources?: SettingsAuditPayload[];
  list?: SettingsAuditListPayload;
  detail?: SettingsAuditPayload | null;
}

const { t } = useI18n();
const auditPage = ref<SettingsAuditPagePayload | null>(null);
const selectedAuditDetail = ref<SettingsAuditPayload | null>(null);
const selectedAuditId = ref<string | null>(null);
const isLoading = ref(false);
const detailLoading = ref(false);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const searchQuery = ref("");
const currentPage = ref(1);
const pageSize = 10;

const audits = computed(() => auditPage.value?.resources ?? []);
const filteredAudits = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return audits.value;
  return audits.value.filter((audit) =>
    [
      audit.audit_id,
      audit.action,
      audit.kind,
      audit.resource_id,
      audit.actor,
      audit.reason,
      audit.status,
      audit.risk,
    ]
      .map((value) => textValue(value, "").toLowerCase())
      .some((value) => value.includes(query)),
  );
});
const totalRecords = computed(() => auditPage.value?.list?.total ?? audits.value.length);
const totalPages = computed(() => Math.max(1, Math.ceil(totalRecords.value / pageSize)));
const pageStart = computed(() => {
  if (!totalRecords.value || !filteredAudits.value.length) return 0;
  return (currentPage.value - 1) * pageSize + 1;
});
const pageEnd = computed(() =>
  Math.min((currentPage.value - 1) * pageSize + filteredAudits.value.length, totalRecords.value),
);
const timeRangeLabel = computed(() => {
  const first = audits.value[0]?.created_at;
  const last = audits.value[audits.value.length - 1]?.created_at;
  if (!first || !last) return t("table.noRecords");
  return `${formatTime(last)} - ${formatTime(first)}`;
});
const selectedActor = computed(() => actorLabel(selectedAuditDetail.value?.actor));
const selectedTarget = computed(() => targetLabel(selectedAuditDetail.value));
const selectedRequestMetadata = computed(() => formatJson(selectedAuditDetail.value?.request_metadata));
const selectedResult = computed(() => {
  if (selectedAuditDetail.value?.error) return formatJson(selectedAuditDetail.value.error);
  return formatJson(selectedAuditDetail.value?.result);
});

onMounted(() => {
  void loadAuditLogs();
});

async function loadAuditLogs(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const offset = (currentPage.value - 1) * pageSize;
    const payload = await listSettingsResources("audit-logs", {
      limit: pageSize,
      offset,
    }) as SettingsAuditPagePayload;
    auditPage.value = payload;
    const firstAudit = payload.resources?.[0] ?? null;
    if (!firstAudit) {
      selectedAuditId.value = null;
      selectedAuditDetail.value = null;
      return;
    }
    const existingDetail = payload.detail?.audit_id === auditId(firstAudit) ? payload.detail : null;
    await selectAudit(auditId(firstAudit), existingDetail);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isLoading.value = false;
  }
}

async function selectAudit(auditIdValue: string, existingDetail?: SettingsAuditPayload | null): Promise<void> {
  if (!auditIdValue) return;
  selectedAuditId.value = auditIdValue;
  detailError.value = null;
  if (existingDetail) {
    selectedAuditDetail.value = existingDetail;
    return;
  }
  detailLoading.value = true;
  try {
    selectedAuditDetail.value = await getSettingsResource(
      "audit-logs",
      auditIdValue,
    ) as SettingsAuditPayload;
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

function goToPreviousPage(): void {
  if (currentPage.value <= 1 || isLoading.value) return;
  currentPage.value -= 1;
  void loadAuditLogs();
}

function goToNextPage(): void {
  if (currentPage.value >= totalPages.value || isLoading.value) return;
  currentPage.value += 1;
  void loadAuditLogs();
}

function auditId(audit: SettingsAuditPayload | null | undefined): string {
  return textValue(audit?.audit_id ?? audit?.id, "");
}

function actorLabel(actor: unknown): string {
  return textValue(actor, t("text.system"));
}

function actorInitials(actor: unknown): string {
  const label = actorLabel(actor);
  return label
    .split(/[\s._@-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("") || "SY";
}

function targetLabel(audit: SettingsAuditPayload | null | undefined): string {
  if (!audit) return "-";
  const kind = resourceLabel(audit.kind);
  const resourceId = textValue(audit.resource_id, "*");
  return `${kind} / ${resourceId}`;
}

function resourceLabel(value: unknown): string {
  const raw = textValue(value, "settings");
  const labels: Record<string, string> = {
    "agent-profiles": t("settings.resource.agentProfiles"),
    "llm-profiles": t("settings.resource.llmProfiles"),
    "tool-catalog": t("settings.resource.toolCatalog"),
    "skill-catalog": t("settings.resource.skillCatalog"),
    "memory-config": t("settings.resource.memoryConfig"),
    "access-assets": t("settings.resource.accessAssets"),
    "channel-profiles": t("settings.resource.channelProfiles"),
    "event-registry": "Event Registry",
    "runtime-defaults": t("settings.resource.runtimeDefaults"),
    environment: t("settings.resource.environment"),
    "audit-logs": t("settings.resource.auditLogs"),
    "backup-restore": t("settings.resource.backupRestore"),
    settings: t("common.settings"),
  };
  return labels[raw] ?? titleize(raw);
}

function statusClass(value: unknown): string {
  const text = textValue(value, "").toLowerCase();
  if (/(failed|error|invalid|blocked)/.test(text)) return "failed";
  if (/(warning|pending|empty|unknown)/.test(text)) return "warning";
  return "success";
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
    .split(/[_\s.-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatJson(value: unknown): string {
  if (value === null || value === undefined || value === "") return "{}";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
</script>

<template>
  <main class="settings-module audit-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>{{ t("settings.resource.auditLogs") }}</h1>
        <p>{{ auditPage?.description ?? t("settings.auditLogsDesc") }}</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadAuditLogs">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section class="audit-filter-row">
      <button class="date-range" type="button" disabled>{{ timeRangeLabel }} <CalendarDays :size="14" /></button>
      <select disabled><option>{{ t("common.all") }} {{ t("common.actions") }}</option></select>
      <select disabled><option>{{ t("common.all") }} {{ t("table.resources") }}</option></select>
      <select disabled><option>{{ t("common.all") }} {{ t("common.owner") }}</option></select>
      <select disabled><option>{{ t("common.all") }} {{ t("common.status") }}</option></select>
      <label><Search :size="14" /><input v-model="searchQuery" :placeholder="t('common.search')" /></label>
      <button type="button" disabled><ListFilter :size="14" /> {{ t("trace.threadFilters") }}</button>
      <button type="button" disabled><Download :size="14" /> {{ t("common.export") }}</button>
    </section>

    <section v-if="loadError" class="settings-panel audit-state audit-state--error">
      <strong>{{ t("table.error") }}</strong>
      <span>{{ loadError }}</span>
      <UiButton size="sm" variant="secondary" @click="loadAuditLogs">{{ t("common.refresh") }}</UiButton>
    </section>

    <section class="audit-layout">
      <article class="settings-panel audit-list-panel">
        <div class="audit-table">
          <div class="audit-table-head">
            <span>{{ t("table.time") }}</span><span>{{ t("table.owner") }}</span><span>{{ t("table.action") }}</span><span>{{ t("table.type") }}</span><span>{{ t("table.target") }}</span><span>{{ t("table.status") }}</span><span>{{ t("operations.tool.tab.risk") }}</span><span></span>
          </div>
          <button
            v-for="log in filteredAudits"
            :key="auditId(log)"
            :class="{ active: auditId(log) === selectedAuditId }"
            type="button"
            class="audit-row"
            @click="selectAudit(auditId(log))"
          >
            <span>{{ formatTime(log.created_at) }}</span>
            <span class="audit-user"><em>{{ actorInitials(log.actor) }}</em><strong>{{ actorLabel(log.actor) }}<small>{{ auditId(log) }}</small></strong></span>
            <span :class="['audit-action', statusClass(log.status)]">{{ titleize(log.action) }}</span>
            <span>{{ resourceLabel(log.kind) }}</span>
            <span class="audit-resource">{{ textValue(log.resource_id, "*") }}</span>
            <span :class="['audit-status', statusClass(log.status)]">{{ titleize(log.status, t("status.unknown")) }}</span>
            <span>{{ titleize(log.risk, "-") }}</span>
            <span class="audit-menu"><MoreVertical :size="15" /></span>
          </button>

          <div v-if="isLoading && !auditPage" class="audit-empty">{{ t("common.loading") }}...</div>
          <div v-else-if="!filteredAudits.length" class="audit-empty">{{ t("table.noRecords") }}</div>
        </div>
        <footer>
          <span>{{ pageStart }}-{{ pageEnd }} / {{ totalRecords }}</span>
          <nav>
            <button type="button" :disabled="currentPage <= 1 || isLoading" @click="goToPreviousPage">{{ t("common.previous") }}</button>
            <button type="button" class="active-page">{{ currentPage }}</button>
            <button type="button" :disabled="currentPage >= totalPages || isLoading" @click="goToNextPage">{{ t("common.next") }}</button>
          </nav>
        </footer>
      </article>

      <aside class="settings-panel audit-detail-panel">
        <header>
          <h2>{{ t("table.details") }}</h2>
          <button type="button" disabled><X :size="15" /></button>
        </header>

        <div v-if="detailError" class="audit-detail-empty">{{ detailError }}</div>
        <div v-else-if="detailLoading" class="audit-detail-empty">{{ t("common.loading") }}...</div>
        <div v-else-if="!selectedAuditDetail" class="audit-detail-empty">{{ t("table.noRecords") }}</div>
        <template v-else>
          <section class="detail-block">
            <h3>{{ t("table.time") }}</h3>
            <p>{{ formatTime(selectedAuditDetail.created_at) }}</p>
          </section>

          <section class="detail-block">
            <h3>{{ t("table.owner") }}</h3>
            <div class="detail-user"><em>{{ actorInitials(selectedAuditDetail.actor) }}</em><strong>{{ selectedActor }}<small>{{ auditId(selectedAuditDetail) }}</small></strong></div>
          </section>

          <section class="detail-block compact">
            <h3>{{ t("table.action") }}</h3>
            <p>{{ titleize(selectedAuditDetail.action) }}</p>
            <h3>{{ t("table.target") }}</h3>
            <p>{{ selectedTarget }}</p>
            <h3>{{ t("table.status") }}</h3>
            <p :class="`${statusClass(selectedAuditDetail.status)}-dot`">{{ titleize(selectedAuditDetail.status, t("status.unknown")) }}</p>
            <h3>{{ t("table.reason") }}</h3>
            <p>{{ selectedAuditDetail.reason ?? "-" }}</p>
            <h3>{{ t("operations.tool.tab.risk") }}</h3>
            <p>{{ titleize(selectedAuditDetail.risk, "-") }}</p>
            <h3>{{ t("table.completedAt") }}</h3>
            <p>{{ formatTime(selectedAuditDetail.completed_at) }}</p>
          </section>

          <section class="detail-block changes">
            <h3>{{ t("table.metadata") }}</h3>
            <pre>{{ selectedRequestMetadata }}</pre>
          </section>

          <section class="detail-block changes">
            <h3>{{ selectedAuditDetail.error ? t("table.error") : t("table.result") }}</h3>
            <pre>{{ selectedResult }}</pre>
          </section>
        </template>
      </aside>
    </section>

    <footer class="settings-footer">
      <span><FileClock :size="14" />{{ auditPage?.title ?? t("settings.resource.auditLogs") }}</span>
      <span><GitBranch :size="14" />{{ totalRecords }} {{ t("table.resources") }}</span>
      <span><User :size="14" />{{ selectedActor }}</span>
      <span><Save :size="14" />{{ auditPage?.status ?? t("status.unknown") }}</span>
      <a>{{ t("settings.resource.auditLogs") }} <ArrowRight :size="13" /></a>
    </footer>
  </main>
</template>

<style scoped>
.audit-settings {
  padding-top: 38px;
}

.audit-filter-row {
  display: grid;
  grid-template-columns: 234px 130px 142px 130px 130px minmax(210px, 1fr) 86px 86px;
  gap: 12px;
  align-items: center;
  margin: 30px 0 18px;
}

.audit-filter-row label,
.audit-filter-row button,
.audit-filter-row select {
  min-height: 32px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.audit-filter-row label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 0 10px;
  color: var(--text-muted);
}

.audit-filter-row input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
}

.audit-filter-row select {
  padding: 0 10px;
}

.audit-filter-row button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 10px;
}

.audit-filter-row button:disabled,
.audit-filter-row select:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.date-range {
  justify-content: space-between !important;
}

.audit-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 54px;
  margin-bottom: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}

.audit-state--error {
  border-color: color-mix(in srgb, var(--color-danger) 44%, var(--border-subtle));
}

.audit-state strong {
  color: var(--color-danger);
}

.audit-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 328px;
  gap: 18px;
  align-items: start;
}

.audit-list-panel,
.audit-detail-panel {
  padding: 0;
  overflow: hidden;
}

.audit-table {
  overflow: auto;
}

.audit-table-head,
.audit-row {
  display: grid;
  grid-template-columns: 170px 156px 88px 146px 128px 98px 86px 34px;
  align-items: center;
  min-width: 910px;
}

.audit-table-head {
  min-height: 46px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 650;
}

.audit-row {
  width: 100%;
  min-height: 61px;
  padding: 0 14px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.audit-row.active {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.audit-row > span {
  min-width: 0;
  overflow: hidden;
  padding-right: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.audit-user,
.detail-user {
  display: flex;
  align-items: center;
  gap: 9px;
}

.audit-user em,
.detail-user em {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--color-blue) 22%, transparent);
  color: var(--color-blue);
  font-size: 10px;
  font-style: normal;
  font-weight: 750;
}

.audit-user strong,
.audit-user small,
.detail-user strong,
.detail-user small {
  display: block;
  min-width: 0;
}

.audit-user small,
.detail-user small {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 500;
}

.audit-action.failed {
  color: var(--color-danger);
}

.audit-action.warning {
  color: var(--color-warning);
}

.audit-resource {
  color: var(--color-accent);
}

.audit-status {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  min-height: 20px;
  padding: 0 8px;
  border-radius: var(--radius-1);
  font-size: 11px;
  font-weight: 650;
}

.audit-status.success {
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
}

.audit-status.warning {
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
  color: var(--color-warning);
}

.audit-status.failed {
  background: color-mix(in srgb, var(--color-danger) 16%, transparent);
  color: var(--color-danger);
}

.audit-menu {
  display: grid;
  place-items: center;
  color: var(--text-muted);
}

.audit-empty,
.audit-detail-empty {
  display: grid;
  min-height: 320px;
  place-items: center;
  color: var(--text-muted);
  font-size: 12px;
}

.audit-list-panel footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 62px;
  padding: 0 16px;
  color: var(--text-muted);
  font-size: 12px;
}

.audit-list-panel footer nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.audit-list-panel footer button {
  min-width: 30px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-1);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
}

.audit-list-panel footer button:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}

.audit-list-panel footer .active-page {
  border-color: color-mix(in srgb, var(--color-accent) 70%, var(--border-subtle));
  background: var(--surface-active);
  color: var(--text-primary);
}

.audit-detail-panel {
  min-height: 786px;
}

.audit-detail-panel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 54px;
  padding: 0 14px;
}

.audit-detail-panel h2 {
  font-size: 14px;
}

.audit-detail-panel header button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
}

.detail-block {
  padding: 10px 14px;
}

.detail-block h3 {
  margin-bottom: 7px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 650;
}

.detail-block p {
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.42;
}

.detail-block.compact {
  display: grid;
  gap: 6px;
}

.success-dot {
  color: var(--color-success) !important;
}

.warning-dot {
  color: var(--color-warning) !important;
}

.failed-dot {
  color: var(--color-danger) !important;
}

.changes pre {
  margin: 0;
  min-height: 126px;
  max-height: 210px;
  overflow: auto;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-input) 88%, transparent);
  color: var(--color-success);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
}
</style>
