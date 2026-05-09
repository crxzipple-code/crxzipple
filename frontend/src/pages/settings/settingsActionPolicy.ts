import type { SettingsActionName, SettingsResourceKind } from "@/shared/runtime/types";

export type RunnableSettingsAction = Extract<
  SettingsActionName,
  "validate" | "dry-run" | "enable" | "disable"
>;

export type SettingsActionOwnership = "settings-owned" | "module-owned" | "readonly";

export interface SettingsActionPolicy {
  ownership: SettingsActionOwnership;
  ownerKey: string;
  truthSourceKey: string;
  applyPolicyKey: string;
  descriptionKey: string;
  actions: readonly RunnableSettingsAction[];
}

const settingsOwnedActions = ["validate", "dry-run", "enable", "disable"] as const;
const validationOnlyActions = ["validate", "dry-run"] as const;

const actionPolicies: Record<SettingsResourceKind, SettingsActionPolicy> = {
  "access-assets": {
    ownership: "settings-owned",
    ownerKey: "settings.actionPolicy.owner.settingsAccess",
    truthSourceKey: "settings.actionPolicy.truth.accessAssets",
    applyPolicyKey: "settings.actionPolicy.apply.settingsAudited",
    descriptionKey: "settings.actionPolicy.description.settingsOwned",
    actions: settingsOwnedActions,
  },
  "agent-profiles": {
    ownership: "module-owned",
    ownerKey: "settings.actionPolicy.owner.agent",
    truthSourceKey: "settings.actionPolicy.truth.agentProfiles",
    applyPolicyKey: "settings.actionPolicy.apply.agentProfiles",
    descriptionKey: "settings.actionPolicy.description.moduleOwned",
    actions: [],
  },
  "audit-logs": {
    ownership: "readonly",
    ownerKey: "settings.actionPolicy.owner.settingsAudit",
    truthSourceKey: "settings.actionPolicy.truth.auditLogs",
    applyPolicyKey: "settings.actionPolicy.apply.readonly",
    descriptionKey: "settings.actionPolicy.description.readonly",
    actions: [],
  },
  "backup-restore": {
    ownership: "readonly",
    ownerKey: "settings.actionPolicy.owner.settingsBackup",
    truthSourceKey: "settings.actionPolicy.truth.backupRestore",
    applyPolicyKey: "settings.actionPolicy.apply.placeholder",
    descriptionKey: "settings.actionPolicy.description.readonly",
    actions: [],
  },
  "channel-profiles": {
    ownership: "module-owned",
    ownerKey: "settings.actionPolicy.owner.channels",
    truthSourceKey: "settings.actionPolicy.truth.channelProfiles",
    applyPolicyKey: "settings.actionPolicy.apply.channelProfiles",
    descriptionKey: "settings.actionPolicy.description.moduleOwned",
    actions: [],
  },
  environment: {
    ownership: "settings-owned",
    ownerKey: "settings.actionPolicy.owner.settings",
    truthSourceKey: "settings.actionPolicy.truth.environment",
    applyPolicyKey: "settings.actionPolicy.apply.environment",
    descriptionKey: "settings.actionPolicy.description.validationOnly",
    actions: validationOnlyActions,
  },
  "event-registry": {
    ownership: "readonly",
    ownerKey: "settings.actionPolicy.owner.events",
    truthSourceKey: "settings.actionPolicy.truth.eventRegistry",
    applyPolicyKey: "settings.actionPolicy.apply.readonly",
    descriptionKey: "settings.actionPolicy.description.readonly",
    actions: [],
  },
  "llm-profiles": {
    ownership: "module-owned",
    ownerKey: "settings.actionPolicy.owner.llm",
    truthSourceKey: "settings.actionPolicy.truth.llmProfiles",
    applyPolicyKey: "settings.actionPolicy.apply.llmProfiles",
    descriptionKey: "settings.actionPolicy.description.moduleOwned",
    actions: [],
  },
  "memory-config": {
    ownership: "settings-owned",
    ownerKey: "settings.actionPolicy.owner.settingsMemory",
    truthSourceKey: "settings.actionPolicy.truth.memoryConfig",
    applyPolicyKey: "settings.actionPolicy.apply.settingsAudited",
    descriptionKey: "settings.actionPolicy.description.settingsOwned",
    actions: settingsOwnedActions,
  },
  "runtime-defaults": {
    ownership: "settings-owned",
    ownerKey: "settings.actionPolicy.owner.settingsRuntime",
    truthSourceKey: "settings.actionPolicy.truth.runtimeDefaults",
    applyPolicyKey: "settings.actionPolicy.apply.settingsAudited",
    descriptionKey: "settings.actionPolicy.description.settingsOwned",
    actions: settingsOwnedActions,
  },
  "skill-catalog": {
    ownership: "settings-owned",
    ownerKey: "settings.actionPolicy.owner.settingsSkills",
    truthSourceKey: "settings.actionPolicy.truth.skillCatalog",
    applyPolicyKey: "settings.actionPolicy.apply.skillCatalog",
    descriptionKey: "settings.actionPolicy.description.validationOnly",
    actions: validationOnlyActions,
  },
  "tool-catalog": {
    ownership: "settings-owned",
    ownerKey: "settings.actionPolicy.owner.settingsTool",
    truthSourceKey: "settings.actionPolicy.truth.toolCatalog",
    applyPolicyKey: "settings.actionPolicy.apply.settingsAudited",
    descriptionKey: "settings.actionPolicy.description.settingsOwned",
    actions: settingsOwnedActions,
  },
};

export function settingsActionPolicyFor(kind: SettingsResourceKind): SettingsActionPolicy {
  return actionPolicies[kind];
}
