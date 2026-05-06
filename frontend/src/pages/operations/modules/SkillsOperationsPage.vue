<script setup lang="ts">
import {
  Boxes,
  FileCode2,
  GitBranch,
  PackageCheck,
  PackagePlus,
  Puzzle,
  RefreshCcw,
  Search,
  ShieldAlert,
  X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, type Component } from "vue";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime, formatRawKeyLabel } from "@/shared/i18n/formatters";
import type {
  OperationsSkillDetail,
  OperationsSkillsReadModel,
  OperationsTab,
  UiChartSection,
  UiKeyValueItem,
  UiMetricCard,
  UiRuntimeAction,
  UiTableRow,
  UiTableSection,
  UiTone,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { installGlobalSkill, loadSkillsOperations, validateSkillPackage } from "../api";

interface ChartSegmentView {
  id: string;
  label: string;
  value: number;
  tone: UiTone;
  pct: number;
}

type DataTableRow = UiTableRow | Record<string, unknown>;

const { t } = useI18n();
const metricIconById: Record<string, Component> = {
  health: PackageCheck,
  installed_skills: Puzzle,
  ready_skills: PackageCheck,
  missing_capabilities: ShieldAlert,
  declared_access: FileCode2,
  resolution_events: GitBranch,
};
const fallbackTabs: OperationsTab[] = [
  { id: "installed", label: "Installed Skills" },
  { id: "requirements", label: "Capability Requirements" },
  { id: "access", label: "Access Requirements" },
  { id: "missing", label: "Missing Capabilities" },
  { id: "logs", label: "Resolution Logs" },
  { id: "resolver", label: "Resolver Detail" },
  { id: "conflicts", label: "Conflicts / Overrides" },
  { id: "profiles", label: "Profile Usage" },
];
const knownTabIds = new Set(fallbackTabs.map((tab) => tab.id));
const selectableTabs = new Set(["installed", "requirements", "access", "missing", "resolver"]);
const skillsTextKeys: Record<string, string> = {
  "Skills": "operations.skills.title",
  "观察技能包目录、声明能力、访问要求、解析结果与导入入口的运维视图。": "operations.skills.subtitle",
  "Skills operator": "operations.skills.role.operator",
  "Overall Health": "operations.skills.metric.health",
  "Installed Skills": "operations.skills.metric.installed",
  "Ready Skills": "operations.skills.metric.ready",
  "Missing Capabilities": "operations.skills.metric.missing",
  "Declared Access": "operations.skills.metric.access",
  "Resolution Events": "operations.skills.metric.events",
  "Capability Requirements": "operations.skills.tab.requirements",
  "Access Requirements": "operations.skills.tab.access",
  "Resolution Logs": "operations.skills.tab.logs",
  "Resolver Detail": "operations.skills.tab.resolver",
  "Conflicts / Overrides": "operations.skills.tab.conflicts",
  "Profile Usage": "operations.skills.tab.profiles",
  "Skill Readiness": "operations.skills.section.readiness",
  "Skill Package Sources": "operations.skills.section.sources",
  "Requirement Footprint": "operations.skills.section.footprint",
  "Import / Normalize": "operations.skills.section.import",
  "List Skills": "operations.skills.action.listSkills",
  "Validate Skill": "operations.skills.action.validateSkill",
  "Validate Package": "operations.skills.action.validatePackage",
  "Install Global Skill": "operations.skills.action.installGlobal",
  "Skill": "text.skill",
  "Source": "table.source",
  "Version": "table.version",
  "Tags": "table.tags",
  "Required Tools": "table.requiredTools",
  "Path": "table.path",
  "Ready": "text.ready",
  "Setup Needed": "text.setupNeeded",
  "Healthy": "text.healthy",
  "Warning": "text.warning",
  "Error": "text.error",
  "healthy": "text.healthy",
  "warning": "text.warning",
  "error": "text.error",
  "system": "operations.skills.source.system",
  "global": "operations.skills.source.global",
  "workspace": "operations.skills.source.workspace",
  "Installed": "common.installed",
  "Available": "common.available",
  "Enabled": "operations.channels.status.enabled",
  "Disabled": "operations.channels.status.disabled",
  "Declared": "operations.skills.status.declared",
  "Required": "operations.skills.status.required",
  "Required Tool": "operations.skills.requirement.requiredTool",
  "Suggested Tool": "operations.skills.requirement.suggestedTool",
  "Optional Tool": "operations.skills.requirement.optionalTool",
  "Required Effect": "operations.skills.requirement.requiredEffect",
  "Access": "operations.module.access",
  "Secret": "operations.skills.requirement.secret",
  "Credential File": "operations.skills.requirement.credentialFile",
  "Setup Hint": "operations.skills.requirement.setupHint",
  "No skills available for this surface.": "operations.skills.empty.installed",
  "No missing skill capabilities.": "operations.skills.empty.missing",
  "No access requirements declared by skills.": "operations.skills.empty.access",
  "No capability requirements declared by skills.": "operations.skills.empty.requirements",
  "No skill resolution events.": "operations.skills.empty.logs",
  "No resolver detail.": "operations.skills.empty.resolver",
  "No skill conflicts or overrides.": "operations.skills.empty.conflicts",
  "No profile usage is available.": "operations.skills.empty.profiles",
  "No skill requirement footprint.": "operations.skills.empty.footprint",
  "No skill package sources.": "operations.skills.empty.sources",
  "No requirements declared.": "operations.skills.empty.detailRequirements",
  "No resources bundled with this skill.": "operations.skills.empty.resources",
  "No related skill events.": "operations.skills.empty.relatedEvents",
  "No records.": "table.noRecords",
};

const page = ref<OperationsSkillsReadModel | null>(null);
const loading = ref(false);
const loadError = ref<string | null>(null);
const actionBusy = ref<string | null>(null);
const actionNotice = ref<string | null>(null);
const selectedTabId = ref<string | null>(null);
const selectedSkillId = ref<string | null>(null);
const queryInput = ref("");
const submittedSearch = ref("");
const statusFilter = ref("all");
const sourceFilter = ref("all");
const refreshTimer = ref<number | null>(null);

const displayMetrics = computed(() => page.value?.metrics ?? []);
const lastUpdatedLabel = computed(() => page.value?.updated_at ? formatLocalTime(page.value.updated_at) : "-");
const tabs = computed(() => {
  const sourceTabs = page.value?.tabs.length ? page.value.tabs : [];
  const sourceById = new Map(sourceTabs.map((tab) => [tab.id, tab]));
  return fallbackTabs.map((tab) => sourceById.get(tab.id) ?? tab);
});
const activeTab = computed(() => {
  const candidate = selectedTabId.value ?? page.value?.active_tab ?? "installed";
  return knownTabIds.has(candidate) ? candidate : "installed";
});
const mainTable = computed(() => {
  if (activeTab.value === "requirements") return page.value?.capability_requirements ?? emptyTable("capability_requirements", "Capability Requirements");
  if (activeTab.value === "access") return page.value?.access_requirements ?? emptyTable("access_requirements", "Access Requirements");
  if (activeTab.value === "missing") return page.value?.missing_capabilities ?? emptyTable("missing_capabilities", "Missing Capabilities");
  if (activeTab.value === "logs") return page.value?.resolution_logs ?? emptyTable("resolution_logs", "Resolution Logs");
  if (activeTab.value === "resolver") return page.value?.resolver_detail ?? emptyTable("resolver_detail", "Resolver Detail");
  if (activeTab.value === "conflicts") return page.value?.conflicts_overrides ?? emptyTable("conflicts_overrides", "Conflicts / Overrides");
  if (activeTab.value === "profiles") return page.value?.profile_usage ?? emptyTable("profile_usage", "Profile Usage");
  return page.value?.recently_resolved_skills ?? emptyTable("recently_resolved_skills", "Installed Skills");
});
const filteredMainRows = computed(() => {
  const rows = mainTable.value.rows;
  const needle = queryInput.value.trim().toLowerCase();
  if (!needle || submittedSearch.value === needle) return rows;
  return rows.filter((row) => {
    const values = isUiTableRow(row) ? Object.values(row.cells) : Object.values(row);
    return values.some((value) => cellValueText(value).toLowerCase().includes(needle));
  });
});
const readinessChart = computed(() => page.value?.resolution_outcomes ?? emptyChart("resolution_outcomes", "Skill Readiness", "donut"));
const sourceChart = computed(() => page.value?.skill_package_sources ?? emptyChart("skill_package_sources", "Skill Package Sources", "donut"));
const missingCapabilities = computed(() => page.value?.missing_capabilities ?? emptyTable("missing_capabilities", "Missing Capabilities"));
const missingPreviewRows = computed(() => missingCapabilities.value.rows.slice(0, 3));
const missingPreviewOverflow = computed(() => Math.max(
  (missingCapabilities.value.total ?? missingCapabilities.value.rows.length) - missingPreviewRows.value.length,
  0,
));
const requirementFootprint = computed(() => page.value?.top_used_skills ?? emptyTable("top_used_skills", "Requirement Footprint"));
const requirementFootprintPreview = computed<UiTableSection>(() => {
  const previewColumns = new Set(["skill", "required_tools", "suggested_tools", "status"]);
  return {
    ...requirementFootprint.value,
    columns: requirementFootprint.value.columns.filter((column) => previewColumns.has(column.key)),
  };
});
const resolutionLogs = computed(() => page.value?.resolution_logs ?? emptyTable("resolution_logs", "Resolution Logs"));
const readinessSegments = computed(() => chartSegments(readinessChart.value));
const sourceSegments = computed(() => chartSegments(sourceChart.value));
const drawerDetail = computed<OperationsSkillDetail | null>(() => {
  if (!selectedSkillId.value) return null;
  return page.value?.skill_details?.find((item) => item.skill_id === selectedSkillId.value) ?? null;
});
const drawerOpen = computed(() => Boolean(drawerDetail.value));

function selectTab(tabId: string) {
  selectedTabId.value = tabId;
  if (!selectableTabs.has(tabId)) selectedSkillId.value = null;
}

function selectRow(row: DataTableRow) {
  if (!selectableTabs.has(activeTab.value)) return;
  selectedSkillId.value = resolveSkillId(row);
}

function openMissingCapability(row: DataTableRow) {
  selectTab("missing");
  selectRow(row);
}

function resolveSkillId(row: DataTableRow): string | null {
  const id = rowId(row);
  const details = page.value?.skill_details ?? [];
  if (id && details.some((item) => item.skill_id === id)) return id;
  const skill = isUiTableRow(row) ? cellValueText(row.cells.skill ?? row.cells.by) : cellValueText(row.skill ?? row.by);
  return details.find((item) => item.skill_id === skill || item.title === skill)?.skill_id ?? null;
}

function rowId(row: DataTableRow): string | null {
  return "id" in row && typeof row.id === "string" ? row.id : null;
}

function isUiTableRow(row: DataTableRow): row is UiTableRow {
  return typeof row === "object"
    && row !== null
    && "cells" in row
    && typeof (row as { cells?: unknown }).cells === "object"
    && (row as { cells?: unknown }).cells !== null;
}

function cellText(row: DataTableRow, key: string): string | null {
  if (isUiTableRow(row)) {
    return cellValueText(row.cells[key]);
  }
  const value = row[key];
  return value == null ? null : String(value);
}

function firstCellText(row: DataTableRow, keys: string[]): string {
  for (const key of keys) {
    const value = cellText(row, key);
    if (value && value !== "-") return value;
  }
  return "-";
}

function missingCapabilityTitle(row: DataTableRow): string {
  const value = firstCellText(row, ["capability", "required_tool", "required_item", "requirement", "skill", "by"]);
  return value !== "-" ? skillsText(value) : rowId(row) ?? "-";
}

function missingCapabilityMeta(row: DataTableRow): string {
  const by = firstCellText(row, ["by", "skill", "source", "surface"]);
  const impact = firstCellText(row, ["impact", "reason", "setup_hint", "required_by"]);
  return [by, impact].filter((value) => value && value !== "-").map(skillsText).join(" / ") || "-";
}

function missingCapabilityStatus(row: DataTableRow): string {
  const value = firstCellText(row, ["status", "kind", "type", "requirement_type"]);
  return value !== "-" ? skillsText(value) : "-";
}

function missingCapabilityTone(row: DataTableRow): UiTone {
  const value = firstCellText(row, ["tone", "status", "kind", "type", "requirement_type"]).toLowerCase();
  if (/error|fail|missing|required|blocked|invalid/.test(value)) return "danger";
  if (/suggested|optional|setup|warning/.test(value)) return "warning";
  if (/ready|resolved|declared|available/.test(value)) return "success";
  return "neutral";
}

function cellValueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object" && value !== null && "text" in value) {
    return String((value as { text: string }).text);
  }
  return String(value);
}

function chartSegments(section: UiChartSection): ChartSegmentView[] {
  const rawSegments = section.segments ?? [];
  const total = rawSegments.reduce((sum, segment) => sum + Number(segment.value || 0), 0);
  return rawSegments.map((segment) => ({
    id: segment.id,
    label: skillsText(segment.label),
    value: Number(segment.value || 0),
    tone: segment.tone,
    pct: total > 0 ? Math.round((Number(segment.value || 0) / total) * 100) : 0,
  }));
}

function metricIcon(metric: UiMetricCard, index: number): Component {
  return metricIconById[metric.id] ?? [PackageCheck, Puzzle, ShieldAlert, FileCode2, GitBranch, Boxes][index % 6];
}

function metricLabel(metric: UiMetricCard) {
  return skillsText(metric.label);
}

function metricDelta(metric: UiMetricCard) {
  return skillsText(metric.delta ?? "");
}

function tabLabel(tab: OperationsTab) {
  return skillsText(tab.label);
}

function sectionTitle(section: UiTableSection | UiChartSection | { title: string }) {
  return skillsText(section.title);
}

function emptyState(section: UiTableSection) {
  return skillsText(section.empty_state ?? "No records.");
}

function actionLabel(action: UiRuntimeAction) {
  return skillsText(action.label);
}

function actionMethodLabel(action: UiRuntimeAction) {
  return action.method ?? "POST";
}

function canRunImportAction(action: UiRuntimeAction) {
  return action.allowed && !loading.value && actionBusy.value === null;
}

async function runImportAction(action: UiRuntimeAction) {
  if (!canRunImportAction(action)) return;
  const sourcePath = promptSkillPath(action);
  if (!sourcePath) return;
  if (action.requires_confirmation && !window.confirm(t("operations.skills.action.installConfirm", { path: sourcePath }))) {
    return;
  }

  actionBusy.value = action.id;
  actionNotice.value = null;
  loadError.value = null;
  try {
    if (action.id === "validate_skill_package") {
      const result = await validateSkillPackage(sourcePath);
      actionNotice.value = t("operations.skills.action.validateNotice", { skill: result.name });
    } else if (action.id === "install_global_skill") {
      const result = await installGlobalSkill(sourcePath);
      actionNotice.value = t("operations.skills.action.installNotice", {
        skill: result.skill.name,
        path: result.target_path,
      });
    } else {
      throw new Error(t("operations.skills.action.unsupportedAction"));
    }
    await refreshPage();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionBusy.value = null;
  }
}

function promptSkillPath(action: UiRuntimeAction): string | null {
  const promptKey = action.id === "install_global_skill"
    ? "operations.skills.action.installSourcePrompt"
    : "operations.skills.action.validatePathPrompt";
  const value = window.prompt(t(promptKey));
  const normalized = value?.trim() ?? "";
  return normalized || null;
}

function detailItems(items: UiKeyValueItem[]) {
  return items.map((item) => ({
    ...item,
    label: skillsText(item.label),
    value: skillsText(item.value),
  }));
}

function detailPayload(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function skillsText(value: string | null | undefined): string {
  if (!value) return "";
  const sources = value.match(/^(\d+) sources$/);
  if (sources) return t("operations.skills.delta.sources", { count: sources[1] });
  const failed = value.match(/^(\d+) failed$/);
  if (failed) return t("operations.skills.delta.failed", { count: failed[1] });
  const key = skillsTextKeys[value];
  if (key) return t(key);
  if (value === "requirements currently satisfied") return t("operations.skills.delta.ready");
  if (value === "required tools or access not ready") return t("operations.skills.delta.missing");
  if (value === "auth, secrets, credential files") return t("operations.skills.delta.access");
  if (value === "Skill packages are queryable") return t("operations.skills.delta.queryable");
  if (value === "Some skill requirements need setup") return t("operations.skills.delta.attention");
  if (value === "Skill manager is not connected") return t("operations.skills.delta.disconnected");
  return formatRawKeyLabel(value);
}

function emptyTable(id: string, title: string): UiTableSection {
  return {
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  };
}

function emptyChart(id: string, title: string, kind: "bar" | "donut"): UiChartSection {
  return {
    id,
    title,
    kind,
    total: 0,
    segments: [],
  };
}

function submitSearch() {
  submittedSearch.value = queryInput.value.trim();
  selectedSkillId.value = null;
  void refreshPage();
}

function resetSearch() {
  queryInput.value = "";
  submittedSearch.value = "";
  statusFilter.value = "all";
  sourceFilter.value = "all";
  selectedSkillId.value = null;
  void refreshPage();
}

async function refreshPage() {
  if (loading.value) return;
  loading.value = true;
  try {
    const loaded = await loadSkillsOperations({
      surface: "interactive",
      source: sourceFilter.value,
      status: statusFilter.value,
      search: submittedSearch.value,
      limit: 80,
    });
    page.value = loaded.page;
    loadError.value = null;
    if (selectedSkillId.value && !loaded.page.skill_details?.some((item) => item.skill_id === selectedSkillId.value)) {
      selectedSkillId.value = null;
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refreshPage();
  refreshTimer.value = window.setInterval(() => {
    void refreshPage();
  }, 30000);
});

onUnmounted(() => {
  if (refreshTimer.value !== null) {
    window.clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
});
</script>

<template>
  <main class="operations-module-console skills-console scroll-area" :class="{ 'has-drawer': drawerOpen }">
    <header class="skills-header">
      <div>
        <h2>{{ skillsText(page?.title ?? "Skills") }} <span>{{ page?.health ? skillsText(page.health) : "-" }}</span></h2>
        <p>{{ skillsText(page?.subtitle ?? "观察技能包目录、声明能力、访问要求、解析结果与导入入口的运维视图。") }}</p>
      </div>
      <div class="skills-header__ops">
        <span>{{ t("common.lastUpdated") }}: <strong>{{ lastUpdatedLabel }}</strong></span>
        <span class="auto-toggle">{{ t("common.autoRefresh") }} <i /></span>
        <UiButton size="sm" variant="secondary" :disabled="loading" @click="refreshPage">
          <RefreshCcw :class="{ 'motion-spin': loading }" :size="13" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton class="role-badge" size="sm" variant="secondary">
          <Puzzle :size="13" /> {{ t("operations.currentRoleLabel") }}: {{ skillsText(page?.role.label ?? "Skills operator") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="skills-alert">
      <StatusDot tone="danger" />
      <span>{{ loadError }}</span>
    </div>
    <div v-if="actionNotice" class="skills-alert skills-alert--success">
      <StatusDot tone="success" />
      <span>{{ actionNotice }}</span>
    </div>

    <section class="skills-metrics">
      <article v-for="(metric, index) in displayMetrics" :key="metric.id" :class="`metric metric--${metric.tone}`">
        <span class="metric-icon"><component :is="metricIcon(metric, index)" :size="21" /></span>
        <span class="metric-copy">
          <em>{{ metricLabel(metric) }}</em>
          <strong>{{ skillsText(metric.value) }}</strong>
          <small>{{ metricDelta(metric) }}</small>
        </span>
      </article>
    </section>

    <section class="skills-status-strip">
      <article class="readiness-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(readinessChart) }}</h3>
        </div>
        <div class="chart-card-body">
          <div class="donut-visual">
            <strong>{{ readinessChart.total ?? 0 }}</strong>
            <span>{{ t("common.total") }}</span>
          </div>
          <dl class="segment-list">
            <div v-for="segment in readinessSegments" :key="segment.id">
              <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
              <dd>{{ segment.value }} <span>{{ segment.pct }}%</span></dd>
            </div>
          </dl>
        </div>
        <p v-if="!readinessSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="source-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(sourceChart) }}</h3>
        </div>
        <dl class="bar-list">
          <div v-for="segment in sourceSegments.slice(0, 6)" :key="segment.id">
            <dt><StatusDot :tone="segment.tone" />{{ segment.label }}</dt>
            <dd><span :style="{ width: `${Math.max(segment.pct, 4)}%` }" />{{ segment.value }}</dd>
          </div>
        </dl>
        <p v-if="!sourceSegments.length" class="panel-empty">{{ t("table.noRecords") }}</p>
      </article>

      <article class="missing-panel">
        <div class="panel-heading">
          <h3>{{ sectionTitle(missingCapabilities) }}</h3>
          <a href="/operations/skills?tab=missing" @click.prevent="selectTab('missing')">{{ t("common.viewAll") }}</a>
        </div>
        <div v-if="missingPreviewRows.length" class="status-preview-list">
          <button
            v-for="(row, index) in missingPreviewRows"
            :key="rowId(row) ?? `${missingCapabilityTitle(row)}-${index}`"
            type="button"
            class="status-preview-row"
            @click="openMissingCapability(row)"
          >
            <span class="status-preview-copy">
              <strong :title="missingCapabilityTitle(row)">{{ missingCapabilityTitle(row) }}</strong>
              <small :title="missingCapabilityMeta(row)">{{ missingCapabilityMeta(row) }}</small>
            </span>
            <span :class="`status-preview-pill status-preview-pill--${missingCapabilityTone(row)}`">
              {{ missingCapabilityStatus(row) }}
            </span>
          </button>
          <p v-if="missingPreviewOverflow" class="status-preview-more">+{{ missingPreviewOverflow }} {{ t("common.more") }}</p>
        </div>
        <p v-if="!missingCapabilities.rows.length" class="panel-empty">{{ emptyState(missingCapabilities) }}</p>
      </article>
    </section>

    <nav class="skills-tabs">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: tab.id === activeTab }" type="button" @click="selectTab(tab.id)">
        {{ tabLabel(tab) }}<span v-if="tab.count != null">{{ tab.count }}</span>
      </button>
    </nav>

    <section class="skills-main-grid">
      <article class="skills-table-panel">
        <div class="panel-heading panel-heading--table">
          <h3>{{ sectionTitle(mainTable) }} <span>{{ mainTable.total ?? mainTable.rows.length }}</span></h3>
          <form class="table-controls" @submit.prevent="submitSearch">
            <label class="table-search">
              <Search :size="13" />
              <input v-model.trim="queryInput" type="search" :placeholder="t('operations.skills.searchPlaceholder')" />
            </label>
            <label class="status-filter">
              <span>{{ t("table.status") }}</span>
              <select v-model="statusFilter" @change="submitSearch">
                <option value="all">{{ t("common.all") }}</option>
                <option value="ready">{{ t("text.ready") }}</option>
                <option value="setup_needed">{{ t("text.setupNeeded") }}</option>
              </select>
            </label>
            <UiButton size="sm" variant="secondary" type="submit" :disabled="loading">
              <Search :size="13" /> {{ t("common.searchAction") }}
            </UiButton>
            <UiButton size="sm" variant="ghost" type="button" :disabled="loading" @click="resetSearch">
              {{ t("common.reset") }}
            </UiButton>
          </form>
        </div>
        <DataTable
          v-if="filteredMainRows.length"
          :columns="mainTable.columns"
          :rows="filteredMainRows"
          section-id="skills-main-table"
          :page-size="12"
          :clickable-rows="selectableTabs.has(activeTab)"
          @row-click="selectRow"
        />
        <p v-else class="table-empty">{{ emptyState(mainTable) }}</p>
      </article>

      <aside class="skills-side-panel">
        <article class="footprint-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(requirementFootprint) }}</h3>
            <a href="/operations/skills?tab=requirements" @click.prevent="selectTab('requirements')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable :columns="requirementFootprintPreview.columns" :rows="requirementFootprintPreview.rows" section-id="requirement-footprint" :page-size="5" :clickable-rows="true" @row-click="selectRow" />
          <p v-if="!requirementFootprint.rows.length" class="panel-empty">{{ emptyState(requirementFootprint) }}</p>
        </article>

        <article class="import-panel">
          <div class="panel-heading">
            <h3>{{ t("operations.skills.section.import") }}</h3>
          </div>
          <div class="import-actions">
            <button
              v-for="action in page?.import_normalize ?? []"
              :key="action.id"
              type="button"
              :class="{ busy: actionBusy === action.id }"
              :disabled="!canRunImportAction(action)"
              :title="action.endpoint ?? ''"
              @click="runImportAction(action)"
            >
              <PackagePlus :class="{ 'motion-spin': actionBusy === action.id }" :size="15" />
              <span>{{ actionLabel(action) }}</span>
              <small>{{ actionMethodLabel(action) }}</small>
            </button>
          </div>
          <p v-if="!(page?.import_normalize ?? []).length" class="panel-empty">{{ t("table.noRecords") }}</p>
        </article>

        <article class="logs-panel">
          <div class="panel-heading">
            <h3>{{ sectionTitle(resolutionLogs) }}</h3>
            <a href="/operations/skills?tab=logs" @click.prevent="selectTab('logs')">{{ t("common.viewAll") }}</a>
          </div>
          <DataTable :columns="resolutionLogs.columns" :rows="resolutionLogs.rows" section-id="resolution-logs" :page-size="4" />
          <p v-if="!resolutionLogs.rows.length" class="panel-empty">{{ emptyState(resolutionLogs) }}</p>
        </article>
      </aside>
    </section>

    <aside v-if="drawerDetail" class="detail-drawer">
      <header>
        <div>
          <span>{{ t("operations.skills.drawer.skill") }}</span>
          <h3>{{ drawerDetail.title }}</h3>
          <p><StatusDot :tone="drawerDetail.tone" />{{ skillsText(drawerDetail.status) }}</p>
        </div>
        <button type="button" :aria-label="t('common.collapseDetails')" @click="selectedSkillId = null">
          <X :size="16" />
        </button>
      </header>

      <section class="drawer-section">
        <h4>{{ t("operations.skills.drawer.summary") }}</h4>
        <dl class="drawer-kv">
          <div v-for="item in detailItems(drawerDetail.summary)" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd :class="`tone-${item.tone ?? 'neutral'}`">{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.skills.drawer.requirements") }}</h4>
        <DataTable :columns="drawerDetail.requirements.columns" :rows="drawerDetail.requirements.rows" section-id="skill-detail-requirements" :page-size="6" />
        <p v-if="!drawerDetail.requirements.rows.length" class="panel-empty">{{ emptyState(drawerDetail.requirements) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.skills.drawer.resources") }}</h4>
        <DataTable :columns="drawerDetail.resources.columns" :rows="drawerDetail.resources.rows" section-id="skill-detail-resources" :page-size="5" />
        <p v-if="!drawerDetail.resources.rows.length" class="panel-empty">{{ emptyState(drawerDetail.resources) }}</p>
      </section>

      <section class="drawer-section">
        <h4>{{ t("operations.skills.drawer.events") }}</h4>
        <DataTable :columns="drawerDetail.events.columns" :rows="drawerDetail.events.rows" section-id="skill-detail-events" :page-size="4" />
        <p v-if="!drawerDetail.events.rows.length" class="panel-empty">{{ emptyState(drawerDetail.events) }}</p>
      </section>

      <section class="drawer-section raw-section">
        <h4>{{ t("operations.skills.drawer.raw") }}</h4>
        <pre>{{ detailPayload(drawerDetail.raw_payload) }}</pre>
      </section>
    </aside>
  </main>
</template>

<style scoped>
.skills-console {
  position: relative;
  height: 100%;
  overflow: auto;
  padding: 8px 12px 12px;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
}

.skills-header,
.skills-header__ops,
.skills-metrics,
.panel-heading,
.skills-tabs,
.auto-toggle,
.metric,
.metric-copy,
.chart-card-body,
.segment-list div,
.bar-list div,
.table-controls,
.table-search,
.status-filter,
.detail-drawer header,
.drawer-kv div {
  display: flex;
  align-items: center;
}

.skills-header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

h2,
h3,
h4,
p,
dl {
  margin: 0;
}

h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  line-height: 1.15;
}

h2 span {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10.5px;
}

h3 {
  font-size: 13px;
  line-height: 1.2;
}

h4 {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 750;
  text-transform: uppercase;
}

.skills-header p {
  max-width: 760px;
  margin-top: 1px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skills-header__ops {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}

.skills-header__ops span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.auto-toggle i {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--color-success);
}

.role-badge {
  color: var(--text-secondary);
}

.skills-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  margin-bottom: 6px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 36%, var(--border-subtle));
  border-radius: var(--radius-1);
  background: color-mix(in srgb, var(--color-danger) 9%, var(--surface-panel));
  color: var(--text-secondary);
  font-size: 11px;
}

.skills-alert--success {
  border-color: color-mix(in srgb, var(--color-success) 34%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-success) 8%, var(--surface-panel));
}

.skills-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(112px, 1fr));
  gap: 6px;
}

.metric,
.skills-status-strip > article,
.skills-table-panel,
.skills-side-panel > article,
.detail-drawer {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
}

.metric {
  gap: 6px;
  height: 68px;
  min-height: 0;
  padding: 7px 9px;
  overflow: hidden;
}

.metric-icon {
  display: grid;
  flex: 0 0 28px;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--color-accent);
}

.metric-copy {
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
}

.metric em,
.metric small {
  overflow: hidden;
  max-width: 100%;
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric strong {
  font-size: 17px;
  line-height: 1;
}

.metric--success strong {
  color: var(--color-success);
}

.metric--warning strong {
  color: var(--color-warning);
}

.metric--danger strong {
  color: var(--color-danger);
}

.skills-status-strip {
  display: grid;
  grid-template-columns: minmax(250px, 0.82fr) minmax(260px, 0.88fr) minmax(410px, 1.3fr);
  gap: 6px;
  align-items: start;
  margin-top: 6px;
}

.skills-status-strip > article,
.skills-side-panel > article {
  min-width: 0;
  padding: 8px;
}

.readiness-panel,
.source-panel,
.missing-panel {
  min-height: 118px;
  overflow: visible;
}

.panel-heading {
  justify-content: space-between;
  gap: 8px;
  min-height: 20px;
  margin-bottom: 5px;
}

.panel-heading a {
  color: var(--color-accent);
  font-size: 11px;
  font-weight: 650;
  text-decoration: none;
}

.panel-heading--table {
  align-items: flex-start;
  margin-bottom: 9px;
}

.panel-heading--table h3 span {
  margin-left: 6px;
  color: var(--text-muted);
  font-weight: 500;
}

.status-preview-list {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.status-preview-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 27px;
  padding: 4px 6px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel-soft);
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.status-preview-row:hover,
.status-preview-row:focus-visible {
  border-color: color-mix(in srgb, var(--color-accent) 42%, var(--border-subtle));
  outline: none;
}

.status-preview-copy {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.status-preview-copy strong,
.status-preview-copy small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-preview-copy strong {
  color: var(--text-primary);
  font-size: 11px;
  line-height: 1.12;
}

.status-preview-copy small {
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.1;
}

.status-preview-pill {
  max-width: 110px;
  padding: 2px 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-preview-pill--success {
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
  color: var(--color-success);
}

.status-preview-pill--warning {
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
  color: var(--color-warning);
}

.status-preview-pill--danger {
  background: color-mix(in srgb, var(--color-danger) 14%, transparent);
  color: var(--color-danger);
}

.status-preview-more {
  margin: 0;
  color: var(--text-muted);
  font-size: 10.5px;
  line-height: 1;
  text-align: right;
}

.chart-card-body {
  gap: 9px;
  min-height: 76px;
}

.donut-visual {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 76px;
  height: 76px;
  border: 1px solid var(--border-default);
  border-radius: 999px;
  background: radial-gradient(circle, var(--surface-panel) 58%, var(--surface-raised) 59%);
}

.donut-visual strong {
  font-size: 20px;
}

.donut-visual span {
  margin-top: -28px;
  color: var(--text-muted);
  font-size: 10px;
}

.segment-list,
.bar-list {
  display: grid;
  gap: 8px;
  width: 100%;
}

.segment-list div,
.bar-list div {
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.segment-list dt,
.bar-list dt {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 11px;
}

.segment-list dd,
.bar-list dd {
  margin: 0;
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 700;
}

.segment-list dd {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.segment-list dd span {
  color: var(--text-muted);
  font-weight: 500;
}

.bar-list dd {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 96px;
  height: 16px;
}

.bar-list dd span {
  position: absolute;
  left: 0;
  z-index: 0;
  height: 7px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent) 36%, var(--surface-raised));
}

.panel-empty,
.table-empty {
  display: grid;
  place-items: center;
  flex: 1 1 auto;
  min-height: 54px;
  color: var(--text-muted);
  font-size: 11px;
  text-align: center;
}

.skills-tabs {
  gap: 6px;
  margin-top: 6px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.skills-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 0 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-panel);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
  font-weight: 650;
  white-space: nowrap;
}

.skills-tabs .active {
  border-color: color-mix(in srgb, var(--color-accent) 42%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-accent) 11%, var(--surface-panel));
  color: var(--text-primary);
}

.skills-tabs span {
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-muted);
  font-size: 10px;
}

.skills-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 6px;
  margin-top: 6px;
}

.skills-table-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: clamp(500px, calc(100dvh - var(--shell-topbar-height) - 300px), 760px);
  padding: 8px;
}

.skills-table-panel :deep(.data-table) {
  flex: 1 1 auto;
  min-height: 0;
}

.skills-side-panel {
  display: grid;
  align-content: start;
  gap: 6px;
  min-width: 0;
}

.skills-side-panel > article {
  min-height: 136px;
}

.table-controls {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

.table-search,
.status-filter {
  gap: 6px;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-muted);
}

.table-search {
  width: min(320px, 34vw);
  padding: 0 9px;
}

.table-search input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.status-filter {
  padding: 0 8px;
  font-size: 11px;
}

.status-filter select {
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 11px;
}

.import-actions {
  display: grid;
  gap: 8px;
}

.import-actions button {
  display: grid;
  grid-template-columns: 22px 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  text-align: left;
}

.import-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.import-actions button.busy {
  border-color: color-mix(in srgb, var(--color-accent) 42%, var(--border-subtle));
}

.import-actions small {
  color: var(--text-muted);
}

.detail-drawer {
  position: fixed;
  top: 84px;
  right: 20px;
  bottom: 20px;
  z-index: 30;
  width: min(438px, calc(100vw - 36px));
  overflow: auto;
  padding: 14px;
  box-shadow: var(--shadow-floating);
}

.detail-drawer header {
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.detail-drawer header span {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 750;
  text-transform: uppercase;
}

.detail-drawer header h3 {
  margin-top: 3px;
  font-size: 16px;
}

.detail-drawer header p {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 11px;
}

.detail-drawer header button {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-muted);
  cursor: pointer;
}

.drawer-section {
  display: grid;
  gap: 8px;
  padding-top: 13px;
}

.drawer-kv {
  display: grid;
  gap: 7px;
}

.drawer-kv div {
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.drawer-kv dt {
  flex: 0 0 104px;
  color: var(--text-muted);
  font-size: 11px;
}

.drawer-kv dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 650;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.raw-section pre {
  overflow: auto;
  max-height: 260px;
  margin: 0;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
}

@media (max-width: 1180px) {
  .skills-metrics {
    grid-template-columns: repeat(3, minmax(140px, 1fr));
  }

  .skills-status-strip,
  .skills-main-grid {
    grid-template-columns: 1fr;
  }

  .skills-side-panel {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .skills-console {
    padding: 8px 10px 10px;
  }

  .skills-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .skills-header__ops {
    justify-content: flex-start;
  }

  .skills-metrics,
  .skills-status-strip {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .metric {
    flex: 0 0 156px;
  }

  .skills-status-strip > article {
    flex: 0 0 286px;
  }

  .skills-side-panel {
    grid-template-columns: 1fr;
  }

  .panel-heading--table {
    flex-direction: column;
    align-items: stretch;
  }

  .table-controls {
    justify-content: flex-start;
  }

  .table-search {
    width: 100%;
  }

  .detail-drawer {
    top: 70px;
    right: 12px;
    bottom: 12px;
  }
}
</style>
