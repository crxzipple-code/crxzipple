<script setup lang="ts">
import {
  Box,
  Brain,
  Database,
  FileClock,
  GitBranch,
  Home,
  KeyRound,
  Layers,
  Package,
  Shield,
  SlidersHorizontal,
  Wrench,
  type LucideIcon,
} from "lucide-vue-next";
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";

import { useI18n } from "@/shared/i18n";
import AccessAssetsSettingsPage from "./modules/AccessAssetsSettingsPage.vue";
import AgentProfilesSettingsPage from "./modules/AgentProfilesSettingsPage.vue";
import AuditLogsSettingsPage from "./modules/AuditLogsSettingsPage.vue";
import AuthorizationPoliciesSettingsPage from "./modules/AuthorizationPoliciesSettingsPage.vue";
import BackupRestoreSettingsPage from "./modules/BackupRestoreSettingsPage.vue";
import ChannelProfilesSettingsPage from "./modules/ChannelProfilesSettingsPage.vue";
import EnvironmentSettingsPage from "./modules/EnvironmentSettingsPage.vue";
import EventRegistrySettingsPage from "./modules/EventRegistrySettingsPage.vue";
import LlmProfilesSettingsPage from "./modules/LlmProfilesSettingsPage.vue";
import MemoryConfigSettingsPage from "./modules/MemoryConfigSettingsPage.vue";
import OverviewSettingsPage from "./modules/OverviewSettingsPage.vue";
import RuntimeDefaultsSettingsPage from "./modules/RuntimeDefaultsSettingsPage.vue";
import SkillCatalogSettingsPage from "./modules/SkillCatalogSettingsPage.vue";
import ToolCatalogSettingsPage from "./modules/ToolCatalogSettingsPage.vue";

type SettingsResourceId =
  | "overview"
  | "agent-profiles"
  | "llm-profiles"
  | "tool-catalog"
  | "skill-catalog"
  | "memory-config"
  | "access-assets"
  | "authorization-policies"
  | "channel-profiles"
  | "event-registry"
  | "runtime-defaults"
  | "environment"
  | "audit-logs"
  | "backup-restore";

interface SettingsNavItem {
  groupKey: string;
  id: SettingsResourceId;
  path: string;
  labelKey: string;
  label?: string;
  icon: LucideIcon;
}

const route = useRoute();
const { t } = useI18n();

const settingsNav: SettingsNavItem[] = [
  { groupKey: "settings.group.overview", id: "overview", path: "/settings", labelKey: "settings.resource.overview", icon: Home },
  { groupKey: "settings.group.agentLlm", id: "agent-profiles", path: "/settings/agent-profiles", labelKey: "settings.resource.agentProfiles", icon: Brain },
  { groupKey: "settings.group.agentLlm", id: "llm-profiles", path: "/settings/llm-profiles", labelKey: "settings.resource.llmProfiles", icon: Layers },
  { groupKey: "settings.group.capabilities", id: "tool-catalog", path: "/settings/tool-catalog", labelKey: "settings.resource.toolCatalog", icon: Wrench },
  { groupKey: "settings.group.capabilities", id: "skill-catalog", path: "/settings/skill-catalog", labelKey: "settings.resource.skillCatalog", label: "Skill Enablement", icon: Package },
  { groupKey: "settings.group.dataMemory", id: "memory-config", path: "/settings/memory-config", labelKey: "settings.resource.memoryConfig", icon: Database },
  { groupKey: "settings.group.accessAuth", id: "access-assets", path: "/settings/access-assets", labelKey: "settings.resource.accessAssets", icon: Shield },
  { groupKey: "settings.group.accessAuth", id: "authorization-policies", path: "/settings/authorization-policies", labelKey: "settings.resource.authorizationPolicies", icon: KeyRound },
  { groupKey: "settings.group.channelsEvents", id: "channel-profiles", path: "/settings/channel-profiles", labelKey: "settings.resource.channelProfiles", icon: GitBranch },
  { groupKey: "settings.group.runtime", id: "runtime-defaults", path: "/settings/runtime-defaults", labelKey: "settings.resource.runtimeDefaults", icon: SlidersHorizontal },
  { groupKey: "settings.group.administration", id: "environment", path: "/settings/environment", labelKey: "settings.resource.environment", icon: Box },
  { groupKey: "settings.group.administration", id: "audit-logs", path: "/settings/audit-logs", labelKey: "settings.resource.auditLogs", icon: FileClock },
];

const settingsComponents = {
  overview: OverviewSettingsPage,
  "agent-profiles": AgentProfilesSettingsPage,
  "llm-profiles": LlmProfilesSettingsPage,
  "tool-catalog": ToolCatalogSettingsPage,
  "skill-catalog": SkillCatalogSettingsPage,
  "memory-config": MemoryConfigSettingsPage,
  "access-assets": AccessAssetsSettingsPage,
  "authorization-policies": AuthorizationPoliciesSettingsPage,
  "channel-profiles": ChannelProfilesSettingsPage,
  "event-registry": EventRegistrySettingsPage,
  "runtime-defaults": RuntimeDefaultsSettingsPage,
  environment: EnvironmentSettingsPage,
  "audit-logs": AuditLogsSettingsPage,
  "backup-restore": BackupRestoreSettingsPage,
} satisfies Record<SettingsResourceId, unknown>;

const activeResource = computed<SettingsResourceId>(() => normalizeResource(route.params.resource));
const activeComponent = computed(() => settingsComponents[activeResource.value]);

function normalizeResource(value: unknown): SettingsResourceId {
  const raw = typeof value === "string" && value.trim() ? value : "overview";
  if (raw === "event-contracts" || raw === "events") return "event-registry";
  if (raw === "agent" || raw === "agents") return "agent-profiles";
  if (raw === "llm" || raw === "llms") return "llm-profiles";
  if (raw === "tool" || raw === "tools") return "tool-catalog";
  if (raw === "skill" || raw === "skills") return "skill-catalog";
  if (raw === "memory") return "memory-config";
  if (raw === "access") return "access-assets";
  if (raw === "authorization" || raw === "auth" || raw === "authorization-policies") return "authorization-policies";
  if (raw === "channel" || raw === "channels") return "channel-profiles";
  if (raw === "runtime") return "runtime-defaults";
  if (raw === "audit") return "audit-logs";
  if (raw === "backup") return "backup-restore";
  return isSettingsResourceId(raw) ? raw : "overview";
}

function navGroupStarts(index: number): boolean {
  return index === 0 || settingsNav[index - 1]?.groupKey !== settingsNav[index].groupKey;
}

function isSettingsResourceId(value: string): value is SettingsResourceId {
  return Object.prototype.hasOwnProperty.call(settingsComponents, value);
}
</script>

<template>
  <div class="settings-shell page-grid">
    <aside class="settings-sidebar scroll-area">
      <h1>{{ t("settings.title") }}</h1>
      <nav>
        <template v-for="(item, index) in settingsNav" :key="item.id">
          <h2 v-if="navGroupStarts(index)">{{ t(item.groupKey) }}</h2>
          <RouterLink :to="item.path" :class="{ active: item.id === activeResource }">
            <component :is="item.icon" :size="14" />
            <span>{{ item.label ?? t(item.labelKey) }}</span>
          </RouterLink>
        </template>
      </nav>
    </aside>

    <component :is="activeComponent" />
  </div>
</template>

<style>
.settings-shell {
  --settings-sidebar-width: 184px;
  --settings-statusbar-height: 38px;
  display: grid;
  grid-template-columns: var(--settings-sidebar-width) minmax(0, 1fr);
  background: var(--surface-page);
}

.settings-sidebar {
  display: flex;
  flex-direction: column;
  min-height: calc(100dvh - var(--shell-topbar-height));
  padding: 18px 14px;
  border-right: 1px solid var(--border-subtle);
  background: var(--surface-sidebar);
}

.settings-sidebar h1,
.settings-sidebar h2,
.settings-module h1,
.settings-module h2,
.settings-module h3,
.settings-module p,
.settings-module dl,
.settings-module ul {
  margin: 0;
}

.settings-sidebar h1 {
  font-size: 17px;
  line-height: 1.1;
}

.settings-sidebar nav {
  display: grid;
  gap: 2px;
  margin-top: 18px;
}

.settings-sidebar h2 {
  margin: 18px 4px 7px;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 750;
  text-transform: uppercase;
}

.settings-sidebar a {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 31px;
  padding: 0 9px;
  border-radius: var(--radius-2);
  color: var(--text-secondary);
  font-size: 12px;
  text-decoration: none;
}

.settings-sidebar a.active {
  background: var(--surface-active);
  color: var(--text-primary);
}

.settings-module {
  min-width: 0;
  padding: 14px 18px 0;
  background: linear-gradient(180deg, var(--surface-page-gradient-start), var(--surface-page) 260px);
}

.settings-module:has(> .settings-footer) {
  padding-bottom: calc(var(--settings-statusbar-height) + 14px);
}

.settings-page-header,
.settings-header-actions,
.settings-metric-strip,
.settings-tabs,
.settings-panel-heading,
.settings-footer,
.settings-footer span,
.settings-footer a {
  display: flex;
  align-items: center;
}

.settings-page-header {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.settings-page-header h1 {
  font-size: 20px;
  line-height: 1.15;
}

.settings-page-header p {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.settings-header-actions {
  justify-content: flex-end;
  gap: 8px;
}

.settings-metric-strip {
  display: grid;
  grid-template-columns: repeat(var(--metric-count, 6), minmax(118px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.settings-metric,
.settings-panel {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 90%, transparent);
}

.settings-metric {
  min-height: 74px;
  padding: 12px;
}

.settings-metric span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 11px;
}

.settings-metric strong {
  display: block;
  margin-top: 7px;
  font-size: 21px;
  line-height: 1;
}

.settings-metric em {
  display: block;
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 10.5px;
  font-style: normal;
}

.settings-metric--success strong,
.settings-tone-success {
  color: var(--color-success);
}

.settings-metric--warning strong,
.settings-tone-warning {
  color: var(--color-warning);
}

.settings-metric--danger strong,
.settings-tone-danger {
  color: var(--color-danger);
}

.settings-metric--info strong,
.settings-tone-info {
  color: var(--color-blue);
}

.settings-tabs {
  gap: 26px;
  min-height: 40px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.settings-tabs button {
  height: 40px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}

.settings-tabs .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.settings-panel {
  min-width: 0;
  padding: 12px;
}

.settings-panel-heading {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.settings-panel-heading h2,
.settings-panel-heading h3 {
  font-size: 13px;
}

.settings-panel-heading a,
.settings-panel-heading span {
  color: var(--color-blue);
  font-size: 11px;
  text-decoration: none;
}

.settings-kv {
  display: grid;
  gap: 8px;
}

.settings-kv div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 11px;
}

.settings-kv dt {
  color: var(--text-muted);
}

.settings-kv dd {
  margin: 0;
  font-weight: 800;
  text-align: right;
}

.settings-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.settings-chip-row span {
  min-height: 23px;
  padding: 4px 8px;
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 11px;
}

.settings-footer {
  position: fixed;
  right: 0;
  bottom: 0;
  left: var(--settings-sidebar-width);
  z-index: 12;
  justify-content: space-between;
  gap: 10px;
  min-height: var(--settings-statusbar-height);
  margin: 0;
  padding: 0 18px;
  border-top: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-nav) 92%, transparent);
  backdrop-filter: blur(14px);
  color: var(--text-muted);
  font-size: 11px;
}

.settings-footer span,
.settings-footer a {
  gap: 6px;
  color: var(--text-muted);
  white-space: nowrap;
  text-decoration: none;
}

.settings-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.settings-form-grid label {
  display: grid;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 11px;
}

.settings-form-grid input,
.settings-form-grid textarea,
.settings-form-grid select {
  width: 100%;
  min-height: 30px;
  padding: 5px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 12px;
}

.settings-form-grid textarea {
  min-height: 58px;
  resize: vertical;
}

.settings-field-wide {
  grid-column: 1 / -1;
}

@media (max-width: 860px) {
  .settings-footer {
    left: 0;
  }
}
</style>
