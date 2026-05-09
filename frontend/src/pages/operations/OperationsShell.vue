<script setup lang="ts">
import {
  Brain,
  ChevronRight,
  Database,
  Grid2X2,
  LayoutGrid,
  MessageCircle,
  Puzzle,
  Radio,
  Settings,
  Shield,
  Wrench,
} from "lucide-vue-next";
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch, type Component } from "vue";
import { RouterLink, useRoute } from "vue-router";

import { useI18n } from "@/shared/i18n";
import type { OperationsModuleOverview } from "@/shared/runtime/types";
import StatusDot from "@/shared/ui/StatusDot.vue";
import {
  loadOperationsRuntimeStatus,
  loadOperationsOverview,
  openOperationsStream,
  type OperationsRefreshEvent,
  type OperationsRuntimeStatus,
  type OperationsRuntimeStatusItem,
} from "./api";
import type { OperationsModuleId } from "./useOperationsProjectionRefresh";

interface ModuleNavItem {
  id: OperationsModuleId;
  labelKey: string;
  tone: "success" | "warning" | "danger";
  healthy: number;
  warning: number;
  error: number;
  icon: Component;
}

const route = useRoute();
const { t } = useI18n();
const moduleOverviews = ref<Partial<Record<OperationsModuleId, OperationsModuleOverview>>>({});
const runtimeStatus = ref<OperationsRuntimeStatus | null>(null);
const runtimeRefreshTimer = ref<number | null>(null);
const overviewRefreshTimer = ref<number | null>(null);
const eventStreamCleanup = ref<(() => void) | null>(null);
const eventDrivenRefreshTimers = new Map<OperationsModuleId | "runtime", number>();

const moduleNav: ModuleNavItem[] = [
  { id: "orchestration", labelKey: "operations.module.orchestration", tone: "success", healthy: 0, warning: 0, error: 0, icon: Grid2X2 },
  { id: "tool", labelKey: "operations.module.tool", tone: "success", healthy: 0, warning: 0, error: 0, icon: Wrench },
  { id: "llm", labelKey: "operations.module.llm", tone: "success", healthy: 0, warning: 0, error: 0, icon: Brain },
  { id: "access", labelKey: "operations.module.access", tone: "success", healthy: 0, warning: 0, error: 0, icon: Shield },
  { id: "channels", labelKey: "operations.module.channels", tone: "success", healthy: 0, warning: 0, error: 0, icon: MessageCircle },
  { id: "memory", labelKey: "operations.module.memory", tone: "success", healthy: 0, warning: 0, error: 0, icon: Database },
  { id: "skills", labelKey: "operations.module.skills", tone: "success", healthy: 0, warning: 0, error: 0, icon: Puzzle },
  { id: "events", labelKey: "operations.module.events", tone: "success", healthy: 0, warning: 0, error: 0, icon: Radio },
  { id: "daemon", labelKey: "operations.module.daemon", tone: "success", healthy: 0, warning: 0, error: 0, icon: Settings },
];

const moduleComponents = {
  orchestration: defineAsyncComponent(() => import("./modules/OrchestrationOperationsPage.vue")),
  tool: defineAsyncComponent(() => import("./modules/ToolOperationsPage.vue")),
  llm: defineAsyncComponent(() => import("./modules/LlmOperationsPage.vue")),
  access: defineAsyncComponent(() => import("./modules/AccessOperationsPage.vue")),
  channels: defineAsyncComponent(() => import("./modules/ChannelsOperationsPage.vue")),
  memory: defineAsyncComponent(() => import("./modules/MemoryOperationsPage.vue")),
  skills: defineAsyncComponent(() => import("./modules/SkillsOperationsPage.vue")),
  events: defineAsyncComponent(() => import("./modules/EventsOperationsPage.vue")),
  daemon: defineAsyncComponent(() => import("./modules/DaemonOperationsPage.vue")),
} satisfies Record<OperationsModuleId, Component>;

const activeModule = computed<OperationsModuleId>(() => {
  const requested = String(route.params.module ?? "orchestration");
  return moduleNav.some((item) => item.id === requested)
    ? requested as OperationsModuleId
    : "orchestration";
});

const activeComponent = computed(() => moduleComponents[activeModule.value]);

const displayedModuleNav = computed(() =>
  moduleNav.map((item) => {
    const overview = moduleOverviews.value[item.id];
    if (!overview) {
      return item;
    }
    const warning = overview.metrics.filter((metric) => metric.tone === "warning").length;
    const error = overview.metrics.filter((metric) => metric.tone === "danger").length;
    const healthy = Math.max(overview.metrics.length - warning - error, 0);
    return {
      ...item,
      tone: healthTone(overview.health),
      healthy,
      warning,
      error,
    };
  }),
);
const runtimeChecks = computed(() => runtimeStatus.value?.checks ?? []);

onMounted(() => {
  void refreshModuleOverviews();
  void refreshRuntimeStatus();
  openOperationsEventStream();
  overviewRefreshTimer.value = window.setInterval(() => {
    void refreshModuleOverviews();
  }, 30_000);
  runtimeRefreshTimer.value = window.setInterval(() => {
    void refreshRuntimeStatus();
  }, 15_000);
});

onUnmounted(() => {
  if (runtimeRefreshTimer.value !== null) {
    window.clearInterval(runtimeRefreshTimer.value);
  }
  if (overviewRefreshTimer.value !== null) {
    window.clearInterval(overviewRefreshTimer.value);
  }
  eventStreamCleanup.value?.();
  eventStreamCleanup.value = null;
  for (const timer of eventDrivenRefreshTimers.values()) {
    window.clearTimeout(timer);
  }
  eventDrivenRefreshTimers.clear();
});

watch(activeModule, (moduleId) => {
  void refreshSingleModuleOverview(moduleId);
});

async function refreshModuleOverviews() {
  for (const moduleId of orderedModuleIds()) {
    await refreshSingleModuleOverview(moduleId);
  }
}

function orderedModuleIds(): OperationsModuleId[] {
  return [
    activeModule.value,
    ...moduleNav.map((item) => item.id).filter((moduleId) => moduleId !== activeModule.value),
  ];
}

async function refreshSingleModuleOverview(moduleId: OperationsModuleId) {
  try {
    const loaded = await loadOperationsOverview(moduleId);
    moduleOverviews.value = {
      ...moduleOverviews.value,
      [moduleId]: loaded.overview,
    };
  } catch {
    // Keep the sidebar usable even if one module read model is temporarily unavailable.
  }
}

async function refreshRuntimeStatus() {
  try {
    const loaded = await loadOperationsRuntimeStatus();
    runtimeStatus.value = loaded.status;
  } catch {
    runtimeStatus.value = {
      updated_at: new Date().toISOString(),
      checks: [
        {
          id: "operations",
          label: "Operations",
          value: "-",
          status: "unavailable",
          tone: "danger",
          details: "Runtime status endpoint is unavailable.",
        },
      ],
    };
  }
}

function openOperationsEventStream() {
  eventStreamCleanup.value?.();
  eventStreamCleanup.value = openOperationsStream({
    event: handleOperationsEvent,
    error: () => scheduleRuntimeStatusRefresh(2500),
  });
}

function handleOperationsEvent(record: OperationsRefreshEvent) {
  window.dispatchEvent(new CustomEvent("crxzipple:operations-event", { detail: record }));
  for (const moduleId of modulesForEvent(record)) {
    scheduleModuleOverviewRefresh(moduleId);
  }
  scheduleRuntimeStatusRefresh();
}

function modulesForEvent(record: OperationsRefreshEvent): OperationsModuleId[] {
  const modules = new Set<OperationsModuleId>();
  for (const candidate of record.modules ?? []) {
    if (isOperationsModuleId(candidate)) {
      modules.add(candidate);
    }
  }
  return [...modules];
}

function isOperationsModuleId(value: string): value is OperationsModuleId {
  return moduleNav.some((item) => item.id === value);
}

function scheduleModuleOverviewRefresh(moduleId: OperationsModuleId) {
  scheduleEventDrivenRefresh(moduleId, () => {
    void refreshSingleModuleOverview(moduleId);
  });
}

function scheduleRuntimeStatusRefresh(delayMs = 700) {
  scheduleEventDrivenRefresh("runtime", () => {
    void refreshRuntimeStatus();
  }, delayMs);
}

function scheduleEventDrivenRefresh(
  key: OperationsModuleId | "runtime",
  callback: () => void,
  delayMs = 700,
) {
  if (eventDrivenRefreshTimers.has(key)) return;
  const timer = window.setTimeout(() => {
    eventDrivenRefreshTimers.delete(key);
    callback();
  }, delayMs);
  eventDrivenRefreshTimers.set(key, timer);
}

function healthTone(health: string): ModuleNavItem["tone"] {
  if (health === "error") return "danger";
  if (health === "warning") return "warning";
  return "success";
}

function runtimeLabel(check: OperationsRuntimeStatusItem): string {
  if (check.id === "database") return t("operations.runtime.database");
  if (check.id === "events") return t("operations.runtime.events");
  if (check.id === "migration") return t("operations.runtime.migration");
  return check.label;
}

function runtimeStatusText(check: OperationsRuntimeStatusItem): string {
  const key = `operations.runtime.status.${check.status}`;
  const translated = t(key);
  return translated === key ? check.status : translated;
}
</script>

<template>
  <div class="operations-page page-grid">
    <aside class="module-sidebar scroll-area">
      <h1>{{ t("operations.modules") }}</h1>
      <section v-if="runtimeChecks.length" class="runtime-facts" aria-live="polite">
        <header>{{ t("operations.runtime.title") }}</header>
        <div class="runtime-fact-list">
          <div
            v-for="check in runtimeChecks"
            :key="check.id"
            class="runtime-fact"
            :title="check.details ?? undefined"
          >
            <span class="runtime-fact-label">
              <StatusDot :tone="check.tone" />
              {{ runtimeLabel(check) }}
            </span>
            <strong>{{ check.value }}</strong>
            <small>{{ runtimeStatusText(check) }}</small>
          </div>
        </div>
      </section>
      <nav>
        <RouterLink
          v-for="item in displayedModuleNav"
          :key="item.id"
          :class="{ active: item.id === activeModule }"
          :to="`/operations/${item.id}`"
        >
          <span class="module-icon">
            <component :is="item.icon" :size="15" />
          </span>
          <span class="module-label">
            <strong>{{ t(item.labelKey) }}</strong>
            <em :class="`module-health module-health--${item.tone}`">
              {{ item.tone === "success" ? t("operations.health.healthy") : item.tone === "warning" ? t("operations.health.warning") : t("operations.health.error") }}
            </em>
          </span>
          <small class="module-stats">
            <span><StatusDot tone="success" /> {{ item.healthy }}</span>
            <span><StatusDot tone="warning" /> {{ item.warning }}</span>
            <span><StatusDot tone="danger" /> {{ item.error }}</span>
          </small>
          <ChevronRight class="module-chevron" :size="14" />
        </RouterLink>
      </nav>

      <div class="legend">
        <span><StatusDot tone="success" /> {{ t("operations.health.healthy") }}</span>
        <span><StatusDot tone="warning" /> {{ t("operations.health.warning") }}</span>
        <span><StatusDot tone="danger" /> {{ t("operations.health.error") }}</span>
      </div>

      <button class="all-modules-button" type="button">
        <LayoutGrid :size="13" />
        {{ t("operations.allModules") }}
      </button>
    </aside>

    <component :is="activeComponent" />
  </div>
</template>

<style scoped>
.operations-page {
  display: grid;
  grid-template-columns: 172px minmax(0, 1fr);
  width: 100%;
  height: calc(100dvh - var(--shell-topbar-height));
  min-height: 0;
  overflow: hidden;
  background: var(--surface-page);
}

.operations-page > :deep(main) {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
}

h1 {
  margin: 0;
  font-size: var(--font-size-3);
}

.module-sidebar {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - var(--shell-topbar-height));
  min-height: calc(100dvh - var(--shell-topbar-height));
  padding: 14px 10px 10px;
  border-right: 1px solid var(--border-subtle);
  background: var(--surface-sidebar);
}

.module-sidebar nav {
  display: grid;
  gap: var(--space-1);
  margin-top: var(--space-3);
}

.runtime-facts {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 78%, transparent);
}

.runtime-facts header {
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0;
}

.runtime-fact-list {
  display: grid;
  gap: 7px;
}

.runtime-fact {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 8px;
  min-width: 0;
}

.runtime-fact-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-fact strong {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 11px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-fact small {
  grid-column: 1 / -1;
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.module-sidebar a,
.legend span,
.all-modules-button {
  display: flex;
  align-items: center;
}

.module-sidebar a {
  position: relative;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  gap: 7px;
  min-height: 52px;
  padding: 7px;
  border: 1px solid transparent;
  border-radius: var(--radius-2);
  color: var(--text-secondary);
  text-decoration: none;
}

.module-sidebar a.active {
  border-color: var(--color-accent);
  background: var(--surface-active);
  color: var(--text-primary);
}

.module-icon {
  display: grid;
  grid-row: span 2;
  place-items: center;
  width: 27px;
  height: 27px;
  border-radius: 50%;
  background: var(--surface-raised);
  color: var(--text-muted);
}

.module-sidebar a.active .module-icon {
  background: color-mix(in srgb, var(--color-accent) 22%, transparent);
  color: var(--color-accent);
}

.module-label {
  display: grid;
  min-width: 0;
}

.module-label strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  line-height: 1.12;
}

.module-health {
  font-size: 10.5px;
  font-style: normal;
  font-weight: 700;
}

.module-health--success {
  color: var(--color-success);
}

.module-health--warning {
  color: var(--color-warning);
}

.module-health--danger {
  color: var(--color-danger);
}

.module-stats {
  display: flex;
  align-items: center;
  gap: 4px;
  grid-column: 2;
  color: var(--text-muted);
  font-size: 10.5px;
}

.module-stats span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.module-chevron {
  grid-column: 3;
  grid-row: 1 / span 2;
  color: var(--text-muted);
}

.legend {
  display: grid;
  gap: var(--space-2);
  margin-top: auto;
  color: var(--text-muted);
  font-size: var(--font-size-1);
}

.legend span {
  gap: var(--space-2);
}

.all-modules-button {
  justify-content: center;
  gap: var(--space-2);
  width: max-content;
  min-height: 30px;
  margin-top: var(--space-4);
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-panel);
  color: var(--color-accent);
  cursor: pointer;
  font-size: var(--font-size-1);
}

@media (max-width: 760px) {
  .operations-page {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    max-width: 100%;
  }

  .module-sidebar {
    max-width: 100%;
    min-width: 0;
    height: auto;
    min-height: 0;
    overflow: hidden;
    padding: 8px 10px;
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .module-sidebar nav {
    display: flex;
    gap: 8px;
    max-width: 100%;
    min-width: 0;
    margin-top: 10px;
    overflow-x: auto;
    padding-bottom: 4px;
    scrollbar-gutter: stable;
  }

  .runtime-facts,
  .legend {
    display: none;
  }

  .module-sidebar a {
    flex: 0 0 142px;
    min-height: 46px;
  }

  .all-modules-button {
    display: none;
  }
}
</style>
