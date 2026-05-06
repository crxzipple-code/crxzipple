<script setup lang="ts">
import { ArrowRight, Box, Brain, CheckCircle2, Database, FileClock, GitBranch, Layers, Package, Shield, Wrench, Zap } from "lucide-vue-next";
import { computed } from "vue";
import { RouterLink } from "vue-router";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";

const { t } = useI18n();

const tableColumns = computed(() => [
  t("table.component"),
  t("table.status"),
  t("table.detail"),
]);

const changeColumns = computed(() => [
  t("table.time"),
  t("table.change"),
  t("table.owner"),
  t("table.type"),
]);

const issueColumns = computed(() => [
  t("table.severity"),
  t("table.category"),
  t("table.component"),
  t("table.issue"),
]);

const metrics = computed(() => [
  { label: t("settings.resource.agentProfiles"), value: "12", delta: t("common.active"), tone: "success", icon: Brain, to: "/settings/agent-profiles" },
  { label: t("settings.resource.llmProfiles"), value: "8", delta: t("common.configured"), tone: "info", icon: Layers, to: "/settings/llm-profiles" },
  { label: t("settings.metric.tools"), value: "34", delta: t("common.available"), tone: "success", icon: Wrench, to: "/settings/tool-catalog" },
  { label: t("settings.metric.skills"), value: "10", delta: t("common.installed"), tone: "warning", icon: Package, to: "/settings/skill-catalog" },
  { label: t("settings.metric.channels"), value: "6", delta: t("common.configured"), tone: "info", icon: GitBranch, to: "/settings/channel-profiles" },
  { label: t("settings.metric.events"), value: "128", delta: t("common.registered"), tone: "warning", icon: Zap, to: "/settings/event-registry" },
  { label: t("settings.resource.accessAssets"), value: "18", delta: t("common.configured"), tone: "success", icon: Shield, to: "/settings/access-assets" },
] as const);

const healthRows = computed(() => [
  { [t("table.component")]: t("settings.resource.agentProfiles"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.agentProfiles") },
  { [t("table.component")]: t("settings.resource.llmProfiles"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.llmProfiles") },
  { [t("table.component")]: t("settings.metric.tools"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.tools") },
  { [t("table.component")]: t("settings.metric.skills"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.skills") },
  { [t("table.component")]: t("settings.resource.memoryConfig"), [t("table.status")]: t("text.warning"), [t("table.detail")]: t("settings.health.memoryWarning") },
  { [t("table.component")]: t("settings.resource.accessAssets"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.accessAssets") },
  { [t("table.component")]: t("settings.metric.channels"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.channels") },
  { [t("table.component")]: t("settings.metric.events"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.events") },
  { [t("table.component")]: t("settings.resource.runtimeDefaults"), [t("table.status")]: t("text.healthy"), [t("table.detail")]: t("settings.health.runtimeDefaults") },
]);

const recentChanges = computed(() => [
  { [t("table.time")]: t("settings.time.2HoursAgo"), [t("table.change")]: t("settings.change.updatedAgent"), [t("table.owner")]: "Jane Doe", [t("table.type")]: t("settings.resource.agentProfiles") },
  { [t("table.time")]: t("settings.time.5HoursAgo"), [t("table.change")]: t("settings.change.addedTool"), [t("table.owner")]: "John Smith", [t("table.type")]: t("settings.metric.tools") },
  { [t("table.time")]: t("settings.time.1DayAgo"), [t("table.change")]: t("settings.change.updatedSkill"), [t("table.owner")]: "Jane Doe", [t("table.type")]: t("settings.metric.skills") },
  { [t("table.time")]: t("settings.time.2DaysAgo"), [t("table.change")]: t("settings.change.modifiedChannel"), [t("table.owner")]: "Mike Lee", [t("table.type")]: t("settings.metric.channels") },
  { [t("table.time")]: t("settings.time.3DaysAgo"), [t("table.change")]: t("settings.change.updatedDefaults"), [t("table.owner")]: t("settings.source.system"), [t("table.type")]: t("settings.group.runtime") },
]);

const issueRows = computed(() => [
  { [t("table.severity")]: t("text.warning"), [t("table.category")]: t("text.memory"), [t("table.component")]: "memory-store", [t("table.issue")]: t("settings.issue.memoryLatency") },
  { [t("table.severity")]: t("text.error"), [t("table.category")]: t("text.access"), [t("table.component")]: "openai_api_key", [t("table.issue")]: t("settings.issue.rateLimit") },
  { [t("table.severity")]: t("text.warning"), [t("table.category")]: t("text.tool"), [t("table.component")]: "sql_query", [t("table.issue")]: t("settings.issue.schemaWarning") },
]);

const quickActions = computed(() => [
  { label: t("settings.action.createAgentProfile"), summary: t("settings.action.createAgentProfileDesc"), to: "/settings/agent-profiles", icon: Brain },
  { label: t("settings.action.addLlmProfile"), summary: t("settings.action.addLlmProfileDesc"), to: "/settings/llm-profiles", icon: Layers },
  { label: t("settings.action.registerTool"), summary: t("settings.action.registerToolDesc"), to: "/settings/tool-catalog", icon: Wrench },
  { label: t("settings.action.createSkill"), summary: t("settings.action.createSkillDesc"), to: "/settings/skill-catalog", icon: Package },
  { label: t("settings.action.addChannel"), summary: t("settings.action.addChannelDesc"), to: "/settings/channel-profiles", icon: GitBranch },
  { label: t("settings.action.defineEvent"), summary: t("settings.action.defineEventDesc"), to: "/settings/event-registry", icon: FileClock },
] as const);
</script>

<template>
  <main class="settings-module settings-overview scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>{{ t("settings.overview") }}</h1>
        <p>{{ t("settings.description") }}</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary">{{ t("theme.dark") }}</UiButton>
        <UiButton size="sm" variant="secondary"><Box :size="14" /></UiButton>
        <UiButton size="sm" variant="secondary"><Brain :size="14" /></UiButton>
      </div>
    </header>

    <section class="overview-contracts">
      <article class="settings-panel">
        <span class="contract-icon readonly"><FileClock :size="18" /></span>
        <div>
          <h2>{{ t("settings.readonlyContracts") }}</h2>
          <p>{{ t("settings.readonlyContractsDesc") }}</p>
        </div>
        <RouterLink to="/settings/event-registry">{{ t("settings.viewContracts") }} <ArrowRight :size="13" /></RouterLink>
      </article>
      <article class="settings-panel">
        <span class="contract-icon editable"><Wrench :size="18" /></span>
        <div>
          <h2>{{ t("settings.editableConfigs") }}</h2>
          <p>{{ t("settings.editableConfigsDesc") }}</p>
        </div>
        <RouterLink to="/settings/runtime-defaults">{{ t("settings.viewEditableConfigs") }} <ArrowRight :size="13" /></RouterLink>
      </article>
    </section>

    <section class="settings-metric-strip" style="--metric-count: 7">
      <RouterLink
        v-for="metric in metrics"
        :key="metric.label"
        :to="metric.to"
        :class="`settings-metric settings-metric--${metric.tone}`"
      >
        <span class="overview-metric-icon"><component :is="metric.icon" :size="16" /></span>
        <span class="overview-metric-copy">
          <small>{{ metric.label }}</small>
          <strong>{{ metric.value }}</strong>
          <em>{{ metric.delta }}</em>
        </span>
      </RouterLink>
    </section>

    <section class="overview-grid">
      <article class="settings-panel health-panel">
        <div class="settings-panel-heading">
          <h2>{{ t("settings.configurationHealth") }}</h2>
          <RouterLink to="/settings/runtime-defaults">{{ t("settings.viewHealthDetails") }} <ArrowRight :size="12" /></RouterLink>
        </div>
        <DataTable :columns="tableColumns" :rows="healthRows" />
      </article>

      <article class="settings-panel changes-panel">
        <div class="settings-panel-heading">
          <h2>{{ t("settings.recentChanges") }}</h2>
          <RouterLink to="/settings/audit-logs">{{ t("settings.viewAuditLogs") }} <ArrowRight :size="12" /></RouterLink>
        </div>
        <DataTable :columns="changeColumns" :rows="recentChanges" />
      </article>

      <article class="settings-panel distribution-panel">
        <div class="settings-panel-heading"><h2>{{ t("settings.distribution") }}</h2></div>
        <div class="distribution-body">
          <div class="distribution-donut"><strong>{{ t("common.total") }}</strong><span>216</span></div>
          <ul>
            <li v-for="metric in metrics" :key="metric.label">
              <StatusDot :tone="metric.tone" />
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </li>
          </ul>
        </div>
        <RouterLink class="panel-link" to="/settings/tool-catalog">{{ t("settings.viewAllConfigurations") }} <ArrowRight :size="12" /></RouterLink>
      </article>

      <article class="settings-panel issues-panel">
        <div class="settings-panel-heading">
          <h2>{{ t("settings.configurationIssues") }}</h2>
          <RouterLink to="/settings/audit-logs">{{ t("settings.viewAllIssues") }} <ArrowRight :size="12" /></RouterLink>
        </div>
        <DataTable :columns="issueColumns" :rows="issueRows" />
        <p>{{ t("settings.issuesNote") }}</p>
      </article>

      <article class="settings-panel inheritance-panel">
        <div class="settings-panel-heading"><h2>{{ t("settings.inheritance") }}</h2></div>
        <p>{{ t("settings.inheritanceDesc") }}</p>
        <div class="inheritance-flow">
          <span>{{ t("trace.summary.turn") }}</span><ArrowRight :size="12" /><span>{{ t("trace.summary.session") }}</span><ArrowRight :size="12" /><span>{{ t("settings.resource.agentProfiles") }}</span><ArrowRight :size="12" /><span>{{ t("settings.source.environment") }}</span><ArrowRight :size="12" /><span>{{ t("settings.source.system") }}</span>
        </div>
        <div class="override-card">
          <strong>{{ t("settings.overrideExample") }}</strong>
          <p>{{ t("settings.overrideExampleValue") }}</p>
          <RouterLink to="/settings/agent-profiles">{{ t("settings.viewResolutionTrace") }} <ArrowRight :size="12" /></RouterLink>
        </div>
      </article>

      <article class="settings-panel quick-panel">
        <div class="settings-panel-heading"><h2>{{ t("settings.quickActions") }}</h2></div>
        <RouterLink v-for="action in quickActions" :key="action.label" :to="action.to">
          <component :is="action.icon" :size="15" />
          <span><strong>{{ action.label }}</strong><small>{{ action.summary }}</small></span>
          <ArrowRight :size="13" />
        </RouterLink>
      </article>

      <article class="settings-panel sources-panel">
        <div class="settings-panel-heading"><h2>{{ t("settings.sourcesVersioning") }}</h2></div>
        <div class="source-strip">
          <span><Database :size="15" /><strong>{{ t("settings.source.system") }}</strong><em>{{ t("settings.source.version") }}</em></span>
          <span><Box :size="15" /><strong>{{ t("settings.source.environment") }}</strong><em>{{ t("settings.source.environmentVersion") }}</em></span>
          <span><Wrench :size="15" /><strong>{{ t("settings.source.agentProfiles") }}</strong><em>{{ t("settings.source.profileCount") }}</em></span>
          <span><Shield :size="15" /><strong>{{ t("settings.source.sessions") }}</strong><em>{{ t("settings.source.activeSessions") }}</em></span>
          <span><CheckCircle2 :size="15" /><strong>{{ t("settings.source.allSynced") }}</strong><em>{{ t("settings.source.lastSync") }}</em></span>
        </div>
      </article>

      <article class="settings-panel useful-panel">
        <div class="settings-panel-heading"><h2>{{ t("settings.usefulLinks") }}</h2></div>
        <RouterLink to="/settings/audit-logs">
          <FileClock :size="15" />
          <span><strong>{{ t("settings.resource.auditLogs") }}</strong><small>{{ t("settings.auditLogsDesc") }}</small></span>
          <ArrowRight :size="13" />
        </RouterLink>
        <RouterLink to="/settings/backup-restore">
          <Box :size="15" />
          <span><strong>{{ t("settings.configurationExport") }}</strong><small>{{ t("settings.configurationExportDesc") }}</small></span>
          <ArrowRight :size="13" />
        </RouterLink>
      </article>
    </section>
  </main>
</template>

<style scoped>
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
.quick-panel a,
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

.overview-metric-copy {
  display: grid !important;
  gap: 3px;
  color: var(--text-muted) !important;
  font-size: 11px !important;
}

.overview-metric-copy small {
  color: var(--text-secondary);
  font-size: 11px;
}

.overview-metric-copy strong {
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1;
}

.overview-metric-copy em {
  color: var(--metric-color, var(--text-muted));
  font-style: normal;
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

.distribution-body {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
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
  background:
    radial-gradient(circle at center, var(--surface-panel) 0 45%, transparent 46%),
    conic-gradient(var(--color-warning) 0 59%, var(--color-success) 59% 76%, var(--color-blue) 76% 84%, var(--color-accent) 84% 92%, var(--color-teal) 92% 100%);
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

.quick-panel a {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 42px;
  color: var(--text-primary);
}

.useful-panel a {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 52px;
  color: var(--text-primary);
}

.quick-panel small,
.useful-panel small,
.source-strip em {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
  font-style: normal;
}

.source-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
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

.source-strip em {
  grid-column: 2;
}
</style>
