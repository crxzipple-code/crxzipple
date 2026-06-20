<script setup lang="ts">
import {
  Activity,
  Braces,
  GitBranch,
  HeartPulse,
  Layers3,
  RefreshCcw,
  Search,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import { formatLocalTime } from "@/shared/i18n/formatters";
import type {
  OperationsTab,
  UiMetricCard,
  UiTableSection,
  UiTone,
} from "@/shared/runtime/types";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  loadOperationsModulePage,
  type OperationsModulePageReadModel,
} from "../api";
import { useOperationsProjectionRefresh } from "../useOperationsProjectionRefresh";

const { t } = useI18n();
const page = ref<OperationsModulePageReadModel | null>(null);
const loadError = ref<string | null>(null);
const loading = ref(false);
const activeTab = ref("workspaces");
const searchInput = ref("");
const lastLoadedAt = ref<string | null>(null);

const metricIconById: Record<string, unknown> = {
  health: HeartPulse,
  workspaces: GitBranch,
  nodes: Layers3,
  pinned: Braces,
  snapshots: Activity,
  snapshot_tokens: Activity,
};

const contextTextKeys: Record<string, string> = {
  "Context Workspace": "operations.contextWorkspace.title",
  "观察会话绑定的 Context Tree、可见节点、估算体积与上下文快照。": "operations.contextWorkspace.subtitle",
  "Context Workspace operator": "operations.contextWorkspace.role.operator",
  "Context Workspaces": "operations.contextWorkspace.section.workspaces",
  "Visible Nodes": "operations.contextWorkspace.section.visibleNodes",
  "Investigation Warnings": "operations.contextWorkspace.section.investigationWarnings",
  "Context Snapshots": "operations.contextWorkspace.section.contextSnapshots",
  "Context Budget": "operations.contextWorkspace.section.contextBudget",
  "Diagnostics": "operations.contextWorkspace.section.diagnostics",
  "Health": "operations.contextWorkspace.metric.health",
  "Workspaces": "operations.contextWorkspace.metric.workspaces",
  "Pinned": "operations.contextWorkspace.metric.pinned",
  "Snapshot Tokens": "operations.contextWorkspace.metric.snapshotTokens",
  "Provider Wire Tokens": "operations.contextWorkspace.metric.providerInputTokens",
  "context tree": "operations.contextWorkspace.delta.contextTree",
  "recent sessions": "operations.contextWorkspace.delta.recentSessions",
  "agent/user pinned nodes": "operations.contextWorkspace.delta.pinnedNodes",
  "browser no-gain signals": "operations.contextWorkspace.delta.browserNoGainSignals",
  "recent context snapshots": "operations.contextWorkspace.delta.recentContextSnapshots",
  "recent estimated tokens": "operations.contextWorkspace.delta.estimatedTokens",
  "recent provider estimate": "operations.contextWorkspace.delta.providerEstimate",
  "Open Context Tree": "operations.contextWorkspace.action.openTree",
  "healthy": "operations.health.healthy",
  "warning": "operations.health.warning",
  "error": "operations.health.error",
  "Healthy": "operations.health.healthy",
  "Warning": "operations.health.warning",
  "Error": "operations.health.error",
  "active": "text.active",
  "Active": "text.active",
};

const tabs = computed<OperationsTab[]>(() => page.value?.tabs?.length ? page.value.tabs : [
  { id: "workspaces", label: t("operations.contextWorkspace.section.workspaces") },
  { id: "visible_nodes", label: t("operations.contextWorkspace.section.visibleNodes") },
  { id: "snapshots", label: t("operations.contextWorkspace.section.contextSnapshots") },
  { id: "context_budget", label: t("operations.contextWorkspace.section.contextBudget") },
  { id: "diagnostics", label: t("operations.contextWorkspace.section.diagnostics") },
]);

const sectionsById = computed(() => {
  const mapped = new Map<string, UiTableSection>();
  for (const section of page.value?.sections ?? []) {
    mapped.set(section.id, section);
  }
  return mapped;
});

const activeSection = computed(() =>
  sectionsById.value.get(activeTab.value) ?? page.value?.sections?.[0] ?? emptySection(),
);

const filteredActiveSection = computed<UiTableSection>(() => {
  const section = activeSection.value;
  const query = searchInput.value.trim().toLowerCase();
  if (!query) return section;
  return {
    ...section,
    rows: section.rows.filter((row) =>
      Object.values(row.cells ?? {}).some((value) => String(value ?? "").toLowerCase().includes(query)),
    ),
  };
});

const workspaceSection = computed(() => sectionsById.value.get("workspaces") ?? emptySection());
const snapshotSection = computed(() => sectionsById.value.get("snapshots") ?? emptySection());
const diagnosticSection = computed(() => sectionsById.value.get("diagnostics") ?? emptySection());
const headlineMetrics = computed(() => (page.value?.metrics ?? []).slice(0, 6));

onMounted(() => {
  void refreshPage();
});

onUnmounted(() => {
  stopRefresh.clearRefreshTimer();
});

const stopRefresh = useOperationsProjectionRefresh("context_workspace", refreshPage);

async function refreshPage() {
  loading.value = true;
  loadError.value = null;
  try {
    const loaded = await loadOperationsModulePage("context_workspace");
    page.value = loaded.page;
    activeTab.value = loaded.page.active_tab || loaded.page.tabs[0]?.id || "workspaces";
    lastLoadedAt.value = loaded.page.updated_at;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

function selectTab(tabId: string) {
  activeTab.value = tabId;
}

function contextText(value: string | undefined | null): string {
  if (!value) return "-";
  const key = contextTextKeys[value];
  return key ? t(key) : value;
}

function metricIcon(metric: UiMetricCard) {
  return metricIconById[metric.id] ?? Activity;
}

function toneClass(tone: UiTone | string | undefined) {
  return `tone-${tone || "neutral"}`;
}

function emptySection(): UiTableSection {
  return {
    id: "empty",
    title: t("operations.contextWorkspace.empty.title"),
    columns: [],
    rows: [],
    total: 0,
    empty_state: t("operations.contextWorkspace.empty.noRecords"),
  };
}
</script>

<template>
  <main class="operations-module-console context-console scroll-area">
    <header class="context-header">
      <div>
        <p class="eyebrow">{{ t("operations.module.contextWorkspace") }}</p>
        <h2>
          {{ contextText(page?.title ?? "Context Workspace") }}
          <span><StatusDot :tone="page?.health === 'error' ? 'danger' : page?.health === 'warning' ? 'warning' : 'success'" />{{ contextText(page?.health ?? "-") }}</span>
        </h2>
        <p>{{ contextText(page?.subtitle ?? "观察会话绑定的 Context Tree、可见节点、估算体积与上下文快照。") }}</p>
      </div>
      <div class="context-header__ops">
        <span>{{ t("common.updatedAt") }}: <strong>{{ lastLoadedAt ? formatLocalTime(lastLoadedAt) : "-" }}</strong></span>
        <span>{{ t("operations.currentRoleLabel") }}: {{ contextText(page?.role.label ?? "Context Workspace operator") }}</span>
        <UiButton :disabled="loading" @click="refreshPage">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <div v-if="loadError" class="context-alert">
      {{ loadError }}
    </div>

    <section class="context-metrics">
      <article
        v-for="metric in headlineMetrics"
        :key="metric.id"
        class="context-metric"
        :class="toneClass(metric.tone)"
      >
        <component :is="metricIcon(metric)" :size="18" />
        <div>
          <span>{{ contextText(metric.label) }}</span>
          <strong>{{ metric.value }}</strong>
          <small>{{ contextText(metric.delta) }}</small>
        </div>
      </article>
    </section>

    <section class="context-main-grid">
      <article class="context-table-panel">
        <div class="context-panel-head">
          <nav class="context-tabs">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              :class="{ active: tab.id === activeTab }"
              @click="selectTab(tab.id)"
            >
              {{ contextText(tab.label) }}
              <span v-if="tab.count !== undefined">{{ tab.count }}</span>
            </button>
          </nav>
          <label class="context-search">
            <Search :size="14" />
            <input v-model.trim="searchInput" type="search" :placeholder="t('operations.contextWorkspace.searchPlaceholder')" />
          </label>
        </div>
        <DataTable
          :columns="filteredActiveSection.columns"
          :rows="filteredActiveSection.rows"
          section-id="context-workspace-main"
          :page-size="9"
        />
      </article>

      <aside class="context-side-panel">
        <article>
          <div class="context-side-head">
            <h3>{{ contextText(workspaceSection.title) }}</h3>
            <span>{{ workspaceSection.total ?? workspaceSection.rows.length }}</span>
          </div>
          <DataTable :columns="workspaceSection.columns" :rows="workspaceSection.rows.slice(0, 5)" section-id="context-workspaces-preview" :page-size="5" />
        </article>
        <article>
          <div class="context-side-head">
            <h3>{{ contextText(snapshotSection.title) }}</h3>
            <span>{{ snapshotSection.total ?? snapshotSection.rows.length }}</span>
          </div>
          <DataTable :columns="snapshotSection.columns" :rows="snapshotSection.rows.slice(0, 4)" section-id="context-snapshots-preview" :page-size="4" />
        </article>
        <article>
          <div class="context-side-head">
            <h3>{{ contextText(diagnosticSection.title) }}</h3>
            <span>{{ diagnosticSection.total ?? diagnosticSection.rows.length }}</span>
          </div>
          <div v-if="!diagnosticSection.rows.length" class="compact-empty">
            {{ t("operations.contextWorkspace.empty.noDiagnostics") }}
          </div>
          <DataTable
            v-else
            :columns="diagnosticSection.columns"
            :rows="diagnosticSection.rows"
            section-id="context-diagnostics-preview"
            :page-size="4"
          />
        </article>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.context-console {
  min-height: calc(100vh - var(--app-header-height, 56px));
  padding: 14px;
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  gap: 10px;
}

.context-header,
.context-header__ops,
.context-metrics,
.context-panel-head,
.context-tabs,
.context-search,
.context-side-head {
  display: flex;
  align-items: center;
}

.context-header {
  justify-content: space-between;
  gap: 16px;
}

.context-header h2 {
  margin: 2px 0 3px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 21px;
  line-height: 1.15;
}

.context-header h2 span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
}

.context-header p {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
}

.context-header__ops {
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.context-header__ops > span {
  padding: 6px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-elevated);
}

.context-alert {
  padding: 8px 10px;
  border: 1px solid rgba(248, 113, 113, 0.45);
  border-radius: 8px;
  color: var(--danger);
  background: rgba(248, 113, 113, 0.08);
  font-size: 12px;
}

.context-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 8px;
}

.context-metric {
  min-height: 72px;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-elevated);
}

.context-metric svg {
  padding: 6px;
  box-sizing: content-box;
  border-radius: 999px;
  color: var(--accent);
  background: rgba(99, 102, 241, 0.12);
}

.context-metric span,
.context-metric small {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.25;
}

.context-metric strong {
  display: block;
  margin: 2px 0;
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1.05;
}

.context-metric.tone-success svg {
  color: var(--success);
  background: rgba(34, 197, 94, 0.12);
}

.context-metric.tone-warning svg {
  color: var(--warning);
  background: rgba(245, 158, 11, 0.12);
}

.context-metric.tone-danger svg {
  color: var(--danger);
  background: rgba(248, 113, 113, 0.12);
}

.context-main-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 10px;
}

.context-table-panel,
.context-side-panel > article {
  min-height: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-elevated);
}

.context-table-panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  padding: 10px;
}

.context-panel-head {
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.context-tabs {
  gap: 4px;
  flex-wrap: wrap;
}

.context-tabs button {
  min-height: 30px;
  padding: 5px 9px;
  border: 0;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  background: transparent;
  cursor: pointer;
}

.context-tabs button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.context-tabs span {
  margin-left: 5px;
  color: var(--text-muted);
}

.context-search {
  width: min(260px, 32vw);
  gap: 7px;
  padding: 6px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-muted);
  background: var(--surface-base);
}

.context-search input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  background: transparent;
  font-size: 12px;
}

.context-side-panel {
  min-height: 0;
  display: grid;
  grid-template-rows: 1fr 1fr 0.7fr;
  gap: 10px;
}

.context-side-panel > article {
  padding: 10px;
  overflow: hidden;
}

.context-side-head {
  justify-content: space-between;
  margin-bottom: 7px;
}

.context-side-head h3 {
  margin: 0;
  font-size: 13px;
}

.context-side-head span {
  color: var(--text-muted);
  font-size: 12px;
}

.compact-empty {
  min-height: 84px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

.context-table-panel :deep(.data-table),
.context-side-panel :deep(.data-table) {
  height: 100%;
}

.context-table-panel :deep(.data-table__cell),
.context-side-panel :deep(.data-table__cell) {
  max-width: 220px;
}

@media (max-width: 1180px) {
  .context-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .context-main-grid {
    grid-template-columns: 1fr;
  }

  .context-side-panel {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    grid-template-rows: 240px;
  }
}

@media (max-width: 760px) {
  .context-console {
    padding: 10px;
  }

  .context-header,
  .context-panel-head {
    align-items: stretch;
    flex-direction: column;
  }

  .context-metrics,
  .context-side-panel {
    grid-template-columns: 1fr;
  }

  .context-search {
    width: 100%;
  }
}
</style>
