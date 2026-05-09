<script setup lang="ts">
import {
  ArrowRight,
  Box,
  Brain,
  CheckCircle2,
  Database,
  FileClock,
  GitBranch,
  Layers,
  Package,
  RefreshCcw,
  Shield,
  Wrench,
  Zap,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { getSettingsOverview } from "../api";

type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";
type TableRow = Record<string, string | number | null>;

interface SettingsHealthPayload {
  status?: string;
  degraded?: boolean;
  source?: string;
  missing_resource_kinds?: string[];
}

interface SettingsMetricPayload {
  id: string;
  label?: string;
  value?: number;
  tone?: StatusTone | string;
  route?: string;
}

interface SettingsTablePayload {
  title?: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
}

interface SettingsKeyValueItem {
  label?: string;
  value?: unknown;
}

interface SettingsKeyValuePayload {
  title?: string;
  items?: SettingsKeyValueItem[];
}

interface SettingsChartPayload {
  title?: string;
  series?: Array<{ label?: string; value?: number }>;
}

interface SettingsRuntimeAction {
  id?: string;
  label?: string;
  requires_reason?: boolean;
  risk?: string;
}

interface SettingsUsefulLink {
  label?: string;
  route?: string;
  href?: string;
}

interface SettingsOverviewPayload {
  resource?: "overview";
  title?: string;
  description?: string;
  status?: string;
  health?: SettingsHealthPayload;
  counts?: Record<string, number>;
  resource_counts?: SettingsMetricPayload[];
  contract_summary?: SettingsKeyValuePayload;
  configuration_summary?: SettingsKeyValuePayload;
  configuration_health?: SettingsTablePayload;
  recent_changes?: SettingsTablePayload;
  configuration_distribution?: SettingsChartPayload;
  configuration_issues?: SettingsTablePayload;
  configuration_inheritance?: SettingsKeyValuePayload;
  sources_versioning?: SettingsKeyValuePayload;
  quick_actions?: SettingsRuntimeAction[];
  useful_links?: SettingsUsefulLink[];
}

const { t } = useI18n();
const overview = ref<SettingsOverviewPayload | null>(null);
const isLoading = ref(false);
const loadError = ref<string | null>(null);

const placeholderMetrics = [
  "agent-profiles",
  "llm-profiles",
  "tool-catalog",
  "skill-catalog",
  "channel-profiles",
  "event-registry",
  "access-assets",
].map((id) => ({
  id,
  label: resourceLabel(id),
  value: undefined,
  tone: "neutral",
  route: `/settings/${id}`,
}));

const metrics = computed(() => {
  const source = overview.value?.resource_counts?.length
    ? overview.value.resource_counts
    : placeholderMetrics;
  return source.map((metric) => ({
    id: metric.id,
    label: resourceLabel(metric.id, metric.label),
    value: metric.value,
    valueLabel: formatNumber(metric.value),
    tone: statusTone(metric.tone, metric.value === 0 ? "warning" : "info"),
    icon: iconForResource(metric.id),
    to: normalizeSettingsRoute(metric.route, metric.id),
  }));
});

const healthStatus = computed(() => overview.value?.health?.status ?? overview.value?.status ?? "unknown");
const healthLabel = computed(() => titleize(healthStatus.value, t("status.unknown")));
const healthSource = computed(() => textValue(overview.value?.health?.source, "settings_application"));
const missingKinds = computed(() => overview.value?.health?.missing_resource_kinds ?? []);

const configurationHealth = computed(() => overview.value?.configuration_health);
const recentChangesSection = computed(() => overview.value?.recent_changes);
const configurationIssues = computed(() => overview.value?.configuration_issues);
const distributionSection = computed(() => overview.value?.configuration_distribution);
const inheritanceItems = computed(() => overview.value?.configuration_inheritance?.items ?? []);
const sourceItems = computed(() => overview.value?.sources_versioning?.items ?? []);
const contractItems = computed(() => overview.value?.contract_summary?.items ?? []);
const configurationItems = computed(() => overview.value?.configuration_summary?.items ?? []);
const quickActions = computed(() => overview.value?.quick_actions ?? []);
const usefulLinks = computed(() => overview.value?.useful_links ?? []);

const healthColumns = computed(() => configurationHealth.value?.columns ?? [
  t("table.component"),
  t("table.status"),
  t("table.detail"),
]);
const changeColumns = computed(() => recentChangesSection.value?.columns ?? [
  t("table.time"),
  t("table.action"),
  t("table.target"),
  t("table.status"),
  t("table.owner"),
  t("table.reason"),
]);
const issueColumns = computed(() => configurationIssues.value?.columns ?? [
  t("table.component"),
  t("table.issue"),
  t("table.severity"),
]);

const healthRows = computed(() => normalizeRows(configurationHealth.value?.rows));
const recentChanges = computed(() => normalizeRows(recentChangesSection.value?.rows));
const issueRows = computed(() => normalizeRows(configurationIssues.value?.rows));

const distributionSeries = computed(() => {
  const series = distributionSection.value?.series;
  if (series?.length) {
    return series.map((item, index) => ({
      label: textValue(item.label, `Item ${index + 1}`),
      value: Number(item.value ?? 0),
      color: distributionColor(index),
    }));
  }
  return metrics.value.map((metric, index) => ({
    label: metric.label,
    value: metric.value ?? 0,
    color: distributionColor(index),
  }));
});
const distributionTotal = computed(() =>
  distributionSeries.value.reduce((total, item) => total + item.value, 0),
);
const distributionDonutStyle = computed(() => ({
  background: donutGradient(distributionSeries.value),
}));

onMounted(() => {
  void loadOverview();
});

async function loadOverview(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    overview.value = await getSettingsOverview() as SettingsOverviewPayload;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isLoading.value = false;
  }
}

function normalizeRows(rows: Record<string, unknown>[] | undefined): TableRow[] {
  return (rows ?? []).map((row) => {
    const normalized: TableRow = {};
    for (const [key, value] of Object.entries(row)) {
      normalized[key] = tableCellValue(value);
    }
    return normalized;
  });
}

function tableCellValue(value: unknown): string | number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
  if (typeof value === "string") return value;
  return compactJson(value);
}

function resourceLabel(id: string, fallback?: string): string {
  const labels: Record<string, string> = {
    "agent-profiles": t("settings.resource.agentProfiles"),
    "llm-profiles": t("settings.resource.llmProfiles"),
    "tool-catalog": t("settings.resource.toolCatalog"),
    "skill-catalog": t("settings.resource.skillCatalog"),
    "memory-config": t("settings.resource.memoryConfig"),
    "access-assets": t("settings.resource.accessAssets"),
    "channel-profiles": t("settings.resource.channelProfiles"),
    "event-registry": fallback ?? "Event Registry",
    "runtime-defaults": t("settings.resource.runtimeDefaults"),
    environment: t("settings.resource.environment"),
    "audit-logs": t("settings.resource.auditLogs"),
    "backup-restore": t("settings.resource.backupRestore"),
  };
  return labels[id] ?? fallback ?? titleize(id);
}

function iconForResource(id: string) {
  const icons = {
    "agent-profiles": Brain,
    "llm-profiles": Layers,
    "tool-catalog": Wrench,
    "skill-catalog": Package,
    "memory-config": Database,
    "access-assets": Shield,
    "channel-profiles": GitBranch,
    "event-registry": Zap,
    "runtime-defaults": Box,
    environment: Box,
    "audit-logs": FileClock,
    "backup-restore": Box,
  };
  return icons[id as keyof typeof icons] ?? Box;
}

function statusTone(value: unknown, fallback: StatusTone = "neutral"): StatusTone {
  const text = textValue(value, "").toLowerCase();
  if (/(error|failed|danger|critical|invalid|blocked)/.test(text)) return "danger";
  if (/(warning|degraded|pending|missing|empty|unknown)/.test(text)) return "warning";
  if (/(ready|success|healthy|valid|active|configured)/.test(text)) return "success";
  if (/(info|running|loading)/.test(text)) return "info";
  return fallback;
}

function normalizeSettingsRoute(route: string | undefined, id: string): string {
  if (route?.startsWith("/settings")) return route;
  if (route?.startsWith("/ui/settings")) return route.replace(/^\/ui/, "");
  if (id === "overview") return "/settings";
  return `/settings/${id}`;
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

function formatNumber(value: number | undefined): string {
  if (value === undefined) return isLoading.value ? `${t("common.loading")}...` : "-";
  return new Intl.NumberFormat().format(value);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
  if (typeof value === "string") return value;
  return compactJson(value);
}

function compactJson(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function distributionColor(index: number): string {
  const colors = [
    "var(--color-accent)",
    "var(--color-blue)",
    "var(--color-success)",
    "var(--color-warning)",
    "var(--color-teal)",
    "var(--color-danger)",
    "var(--color-gray)",
  ];
  return colors[index % colors.length];
}

function donutGradient(series: Array<{ value: number; color: string }>): string {
  const total = series.reduce((sum, item) => sum + item.value, 0);
  if (total <= 0) {
    return "radial-gradient(circle at center, var(--surface-panel) 0 45%, transparent 46%), conic-gradient(var(--border-subtle) 0 100%)";
  }
  let cursor = 0;
  const stops = series
    .map((item) => {
      const start = cursor;
      cursor += (item.value / total) * 100;
      return `${item.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`;
    })
    .join(", ");
  return `radial-gradient(circle at center, var(--surface-panel) 0 45%, transparent 46%), conic-gradient(${stops})`;
}
</script>

<template>
  <main class="settings-module settings-overview scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>{{ t("settings.overview") }}</h1>
        <p>{{ overview?.description ?? t("settings.description") }}</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadOverview">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section v-if="loadError" class="settings-panel overview-state overview-state--error">
      <strong>{{ t("table.error") }}</strong>
      <span>{{ loadError }}</span>
      <UiButton size="sm" variant="secondary" @click="loadOverview">{{ t("common.refresh") }}</UiButton>
    </section>

    <section class="overview-contracts">
      <article class="settings-panel">
        <span class="contract-icon readonly"><FileClock :size="18" /></span>
        <div>
          <h2>{{ overview?.contract_summary?.title ?? t("settings.readonlyContracts") }}</h2>
          <p v-if="contractItems.length">
            <span v-for="item in contractItems" :key="item.label">
              {{ item.label }}: {{ formatValue(item.value) }}
            </span>
          </p>
          <p v-else>{{ t("settings.readonlyContractsDesc") }}</p>
        </div>
        <RouterLink to="/settings/event-registry">{{ t("settings.viewContracts") }} <ArrowRight :size="13" /></RouterLink>
      </article>
      <article class="settings-panel">
        <span class="contract-icon editable"><Wrench :size="18" /></span>
        <div>
          <h2>{{ overview?.configuration_summary?.title ?? t("settings.editableConfigs") }}</h2>
          <p v-if="configurationItems.length">
            <span v-for="item in configurationItems" :key="item.label">
              {{ item.label }}: {{ formatValue(item.value) }}
            </span>
          </p>
          <p v-else>{{ t("settings.editableConfigsDesc") }}</p>
        </div>
        <RouterLink to="/settings/runtime-defaults">{{ t("settings.viewEditableConfigs") }} <ArrowRight :size="13" /></RouterLink>
      </article>
    </section>

    <section class="settings-metric-strip">
      <RouterLink
        v-for="metric in metrics"
        :key="metric.id"
        :to="metric.to"
        :class="`settings-metric settings-metric--${metric.tone}`"
      >
        <span class="overview-metric-icon"><component :is="metric.icon" :size="16" /></span>
        <span class="overview-metric-copy">
          <small>{{ metric.label }}</small>
          <strong>{{ metric.valueLabel }}</strong>
          <em>{{ metric.value === 0 ? t("status.warning") : healthLabel }}</em>
        </span>
      </RouterLink>
    </section>

    <section class="overview-grid">
      <article class="settings-panel health-panel">
        <div class="settings-panel-heading">
          <h2>{{ configurationHealth?.title ?? t("settings.configurationHealth") }}</h2>
          <RouterLink to="/settings/runtime-defaults">{{ t("settings.viewHealthDetails") }} <ArrowRight :size="12" /></RouterLink>
        </div>
        <DataTable :columns="healthColumns" :rows="healthRows" section-id="settings-overview-health" />
        <div v-if="isLoading && !overview" class="overview-empty">{{ t("common.loading") }}...</div>
        <div v-else-if="!healthRows.length" class="overview-empty">{{ t("table.noRecords") }}</div>
      </article>

      <article class="settings-panel changes-panel">
        <div class="settings-panel-heading">
          <h2>{{ recentChangesSection?.title ?? t("settings.recentChanges") }}</h2>
          <RouterLink to="/settings/audit-logs">{{ t("settings.viewAuditLogs") }} <ArrowRight :size="12" /></RouterLink>
        </div>
        <DataTable :columns="changeColumns" :rows="recentChanges" section-id="settings-overview-changes" />
        <div v-if="isLoading && !overview" class="overview-empty">{{ t("common.loading") }}...</div>
        <div v-else-if="!recentChanges.length" class="overview-empty">{{ t("table.noRecords") }}</div>
      </article>

      <article class="settings-panel distribution-panel">
        <div class="settings-panel-heading"><h2>{{ distributionSection?.title ?? t("settings.distribution") }}</h2></div>
        <div class="distribution-body">
          <div class="distribution-donut" :style="distributionDonutStyle">
            <strong>{{ t("common.total") }}</strong>
            <span>{{ formatNumber(distributionTotal) }}</span>
          </div>
          <ul>
            <li v-for="item in distributionSeries" :key="item.label">
              <StatusDot :tone="item.value === 0 ? 'warning' : 'success'" />
              <span>{{ resourceLabel(item.label, item.label) }}</span>
              <strong>{{ formatNumber(item.value) }}</strong>
            </li>
          </ul>
        </div>
        <RouterLink class="panel-link" to="/settings/tool-catalog">{{ t("settings.viewAllConfigurations") }} <ArrowRight :size="12" /></RouterLink>
      </article>

      <article class="settings-panel issues-panel">
        <div class="settings-panel-heading">
          <h2>{{ configurationIssues?.title ?? t("settings.configurationIssues") }}</h2>
          <RouterLink to="/settings/audit-logs">{{ t("settings.viewAllIssues") }} <ArrowRight :size="12" /></RouterLink>
        </div>
        <DataTable :columns="issueColumns" :rows="issueRows" section-id="settings-overview-issues" />
        <div v-if="isLoading && !overview" class="overview-empty">{{ t("common.loading") }}...</div>
        <div v-else-if="!issueRows.length" class="overview-empty">{{ t("table.noRecords") }}</div>
        <p>{{ t("settings.issuesNote") }}</p>
      </article>

      <article class="settings-panel inheritance-panel">
        <div class="settings-panel-heading"><h2>{{ overview?.configuration_inheritance?.title ?? t("settings.inheritance") }}</h2></div>
        <p>{{ t("settings.inheritanceDesc") }}</p>
        <div class="inheritance-flow" v-if="inheritanceItems.length">
          <template v-for="(item, index) in inheritanceItems" :key="item.label">
            <span>{{ item.label }}: {{ formatValue(item.value) }}</span>
            <ArrowRight v-if="index < inheritanceItems.length - 1" :size="12" />
          </template>
        </div>
        <div v-else class="inheritance-flow">
          <span>{{ t("trace.summary.turn") }}</span><ArrowRight :size="12" /><span>{{ t("trace.summary.session") }}</span><ArrowRight :size="12" /><span>{{ t("settings.resource.agentProfiles") }}</span><ArrowRight :size="12" /><span>{{ t("settings.source.environment") }}</span><ArrowRight :size="12" /><span>{{ t("settings.source.system") }}</span>
        </div>
        <div class="override-card">
          <strong>{{ healthLabel }}</strong>
          <p>{{ missingKinds.length ? missingKinds.map((kind) => resourceLabel(kind, kind)).join(" / ") : healthSource }}</p>
          <RouterLink to="/settings/runtime-defaults">{{ t("settings.viewResolutionTrace") }} <ArrowRight :size="12" /></RouterLink>
        </div>
      </article>

      <article class="settings-panel quick-panel">
        <div class="settings-panel-heading"><h2>{{ t("settings.quickActions") }}</h2></div>
        <button
          v-for="action in quickActions"
          :key="action.id ?? action.label"
          class="overview-disabled-action"
          type="button"
          disabled
        >
          <Wrench :size="15" />
          <span>
            <strong>{{ action.label ?? action.id }}</strong>
            <small>{{ action.requires_reason ? t("table.reason") : titleize(action.risk, "-") }}</small>
          </span>
        </button>
        <div v-if="!quickActions.length" class="overview-empty">{{ t("table.noRecords") }}</div>
      </article>

      <article class="settings-panel sources-panel">
        <div class="settings-panel-heading"><h2>{{ overview?.sources_versioning?.title ?? t("settings.sourcesVersioning") }}</h2></div>
        <div class="source-strip">
          <span v-for="item in sourceItems" :key="item.label">
            <Database :size="15" />
            <strong>{{ item.label }}</strong>
            <em>{{ formatValue(item.value) }}</em>
          </span>
          <span v-if="!sourceItems.length"><CheckCircle2 :size="15" /><strong>{{ healthLabel }}</strong><em>{{ healthSource }}</em></span>
        </div>
      </article>

      <article class="settings-panel useful-panel">
        <div class="settings-panel-heading"><h2>{{ t("settings.usefulLinks") }}</h2></div>
        <RouterLink
          v-for="link in usefulLinks"
          :key="link.route ?? link.href ?? link.label"
          :to="normalizeSettingsRoute(link.route, 'overview')"
        >
          <FileClock :size="15" />
          <span><strong>{{ resourceLabel((link.route ?? "").split("/").pop() ?? "", link.label) }}</strong><small>{{ link.route ?? link.href }}</small></span>
          <ArrowRight :size="13" />
        </RouterLink>
        <RouterLink v-if="!usefulLinks.length" to="/settings/audit-logs">
          <FileClock :size="15" />
          <span><strong>{{ t("settings.resource.auditLogs") }}</strong><small>{{ t("settings.auditLogsDesc") }}</small></span>
          <ArrowRight :size="13" />
        </RouterLink>
      </article>
    </section>
  </main>
</template>

<style scoped>
.overview-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 54px;
  margin-bottom: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.overview-state--error {
  border-color: color-mix(in srgb, var(--color-danger) 44%, var(--border-subtle));
}

.overview-state strong {
  color: var(--color-danger);
}

.overview-contracts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.overview-contracts article {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 78px;
}

.overview-contracts p,
.issues-panel p,
.inheritance-panel p {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.overview-contracts h2 {
  font-size: 14px;
}

.overview-contracts a,
.panel-link,
.override-card a,
.useful-panel a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-accent);
  font-size: 12px;
  text-decoration: none;
}

.contract-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
}

.contract-icon.readonly {
  background: color-mix(in srgb, var(--color-accent) 22%, transparent);
  color: var(--color-accent);
}

.contract-icon.editable {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.settings-overview .settings-metric-strip {
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
}

.settings-metric {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 82px;
  color: inherit;
  text-decoration: none;
}

.overview-metric-icon {
  display: grid !important;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--metric-color, var(--color-gray)) 22%, transparent);
  color: var(--metric-color, var(--color-gray)) !important;
}

.settings-metric--success {
  --metric-color: var(--color-success);
}

.settings-metric--info {
  --metric-color: var(--color-blue);
}

.settings-metric--warning {
  --metric-color: var(--color-warning);
}

.settings-metric--danger {
  --metric-color: var(--color-danger);
}

.settings-metric--neutral {
  --metric-color: var(--color-gray);
}

.overview-metric-copy {
  display: grid !important;
  gap: 3px;
  color: var(--text-muted) !important;
  font-size: 11px !important;
}

.overview-metric-copy small {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-metric-copy strong {
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1;
}

.overview-metric-copy em {
  overflow: hidden;
  color: var(--metric-color, var(--text-muted));
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 10px;
}

.health-panel,
.changes-panel,
.distribution-panel {
  grid-column: span 4;
}

.issues-panel {
  grid-column: span 5;
}

.inheritance-panel {
  grid-column: span 4;
}

.quick-panel {
  display: grid;
  grid-column: span 3;
  gap: 8px;
}

.sources-panel {
  grid-column: span 9;
}

.useful-panel {
  display: grid;
  grid-column: span 3;
  gap: 8px;
}

.health-panel,
.changes-panel,
.issues-panel {
  min-height: 206px;
}

.overview-empty {
  display: grid;
  min-height: 68px;
  place-items: center;
  color: var(--text-muted);
  font-size: 12px;
}

.distribution-body {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 16px;
  align-items: center;
}

.distribution-donut {
  display: grid;
  grid-template-rows: auto auto;
  align-content: center;
  justify-items: center;
  gap: 3px;
  place-items: center;
  width: 142px;
  height: 142px;
  border-radius: 999px;
  text-align: center;
}

.distribution-donut strong {
  max-width: 82px;
  color: var(--text-muted);
  font-size: 9.5px;
  line-height: 1.08;
}

.distribution-donut span {
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
}

.distribution-panel ul {
  display: grid;
  gap: 8px;
  padding: 0;
  list-style: none;
}

.distribution-panel li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  color: var(--text-secondary);
  font-size: 11px;
}

.distribution-panel li span:nth-child(2) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inheritance-flow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  color: var(--text-muted);
}

.inheritance-flow span,
.override-card {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
}

.inheritance-flow span {
  padding: 7px 10px;
  color: var(--text-secondary);
  font-size: 11px;
}

.override-card {
  display: grid;
  gap: 7px;
  margin-top: 14px;
  padding: 12px;
}

.overview-disabled-action {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 42px;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  cursor: not-allowed;
  opacity: 0.66;
  text-align: left;
}

.overview-disabled-action small,
.useful-panel small,
.source-strip em {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
  font-style: normal;
}

.source-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(156px, 1fr));
  gap: 10px;
}

.source-strip > span {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 3px 8px;
  align-items: center;
  min-height: 48px;
  padding: 8px;
  border-right: 1px solid var(--border-subtle);
}

.source-strip strong,
.source-strip em,
.useful-panel strong,
.useful-panel small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-strip em {
  grid-column: 2;
}

.useful-panel a {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 42px;
  color: var(--text-primary);
}
</style>
