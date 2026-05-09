import { requestJson } from "@/shared/api/client";
import type {
  SettingsActionName,
  SettingsActionRequest,
  SettingsActionResponse,
  SettingsBootstrapImportResponse,
  SettingsDetailReadModel,
  SettingsKindPageReadModel,
  SettingsOverviewReadModel,
  SettingsPayload,
  SettingsReadModel,
  SettingsResourceId,
  SettingsResourceKind,
} from "@/shared/runtime/types";

export interface SettingsPaginationParams {
  limit?: number;
  offset?: number;
}

export type SettingsResourceRouteAlias =
  | SettingsResourceId
  | "agent"
  | "agents"
  | "agent_profiles"
  | "llm"
  | "llms"
  | "llm_profiles"
  | "tool"
  | "tools"
  | "tool_providers"
  | "skill"
  | "skills"
  | "memory"
  | "memory_config"
  | "access"
  | "access_assets"
  | "channel"
  | "channels"
  | "channel_profiles"
  | "event"
  | "events"
  | "event-contracts"
  | "event_contracts"
  | "event_registry"
  | "runtime"
  | "runtime_defaults"
  | "audit"
  | "audits"
  | "audit_logs"
  | "backup"
  | "backup_restore";

export type SettingsResourceKindInput = Exclude<SettingsResourceRouteAlias, "overview">;
export type SettingsActionOptions = Omit<SettingsActionRequest, "payload" | "reason">;
export type SettingsOwnerJsonRecord = Record<string, unknown>;

export interface AuthorizationObligationApiPayload {
  name: string;
  params: SettingsOwnerJsonRecord;
}

export interface AuthorizationPolicyApiPayload {
  id: string;
  description: string;
  effect: "allow" | "deny" | string;
  actions: string[];
  subject_type?: string | null;
  subject_id?: string | null;
  subject_match: SettingsOwnerJsonRecord;
  resource_kind?: string | null;
  resource_id?: string | null;
  resource_match: SettingsOwnerJsonRecord;
  context_match: SettingsOwnerJsonRecord;
  condition?: SettingsOwnerJsonRecord | null;
  obligations: AuthorizationObligationApiPayload[];
  priority: number;
  enabled: boolean;
  source_kind: string;
}

export interface AuthorizationPolicyWritePayload extends AuthorizationPolicyApiPayload {
  actor?: {
    type?: string | null;
    id?: string | null;
  };
  reason?: string;
}

export interface AuthorizationDecisionApiPayload {
  allowed: boolean;
  reason: string;
  code: string;
  matched_policy_ids: string[];
  obligations: AuthorizationObligationApiPayload[];
  details: SettingsOwnerJsonRecord;
}

export interface AuthorizationCheckRequestPayload {
  subject?: {
    type?: string;
    id?: string | null;
    attrs?: SettingsOwnerJsonRecord;
  };
  action: string;
  resource: {
    kind: string;
    id?: string | null;
    attrs?: SettingsOwnerJsonRecord;
  };
  context?: {
    attrs?: SettingsOwnerJsonRecord;
  };
}

export interface AuthorizationImpactApiPayload {
  changed: boolean;
  before: AuthorizationDecisionApiPayload;
  after: AuthorizationDecisionApiPayload;
  added_policy_ids: string[];
  updated_policy_ids: string[];
  removed_policy_ids: string[];
}

export interface AuthorizationAuditApiPayload {
  id: string;
  action: string;
  status: string;
  actor_type?: string | null;
  actor_id?: string | null;
  target_policy_id?: string | null;
  reason: string;
  before_payload: SettingsOwnerJsonRecord;
  after_payload: SettingsOwnerJsonRecord;
  decision_payload: SettingsOwnerJsonRecord;
  metadata: SettingsOwnerJsonRecord;
  created_at: string;
}

export interface AuthorizationPolicyExportPayload {
  kind: string;
  version: number;
  policies: SettingsOwnerJsonRecord[];
}

const SETTINGS_BASE = "/ui/settings";
const AUTHORIZATION_BASE = "/authorization";

const settingsResourceIds = new Set<string>([
  "overview",
  "agent-profiles",
  "llm-profiles",
  "tool-catalog",
  "skill-catalog",
  "memory-config",
  "access-assets",
  "channel-profiles",
  "event-registry",
  "runtime-defaults",
  "environment",
  "audit-logs",
  "backup-restore",
]);

const settingsKindAliases: Record<string, SettingsResourceId> = {
  agent: "agent-profiles",
  agents: "agent-profiles",
  "agent-profiles": "agent-profiles",
  llm: "llm-profiles",
  llms: "llm-profiles",
  "llm-profiles": "llm-profiles",
  tool: "tool-catalog",
  tools: "tool-catalog",
  "tool-providers": "tool-catalog",
  skill: "skill-catalog",
  skills: "skill-catalog",
  memory: "memory-config",
  "memory-config": "memory-config",
  access: "access-assets",
  "access-assets": "access-assets",
  channel: "channel-profiles",
  channels: "channel-profiles",
  "channel-profiles": "channel-profiles",
  event: "event-registry",
  events: "event-registry",
  "event-contracts": "event-registry",
  "event-registry": "event-registry",
  runtime: "runtime-defaults",
  "runtime-defaults": "runtime-defaults",
  audit: "audit-logs",
  audits: "audit-logs",
  "audit-logs": "audit-logs",
  backup: "backup-restore",
  "backup-restore": "backup-restore",
};

const writeActions = new Set<SettingsActionName>([
  "publish",
  "rollback",
  "enable",
  "disable",
  "create",
  "update",
]);

export function isSettingsResourceId(value: unknown): value is SettingsResourceId {
  return typeof value === "string" && settingsResourceIds.has(value);
}

export function isSettingsResourceKind(value: unknown): value is SettingsResourceKind {
  return isSettingsResourceId(value) && value !== "overview";
}

export function normalizeSettingsResourceId(value: unknown): SettingsResourceId {
  const normalized = normalizeSettingsResourceKey(value);
  if (isSettingsResourceId(normalized)) {
    return normalized;
  }
  return settingsKindAliases[normalized] ?? "overview";
}

export function normalizeSettingsResourceKind(
  value: SettingsResourceKindInput,
): SettingsResourceKind {
  const resource = normalizeSettingsResourceId(value);
  if (resource === "overview") {
    throw new Error("Settings overview is not a listable resource kind.");
  }
  return resource;
}

export function settingsActionRequiresReason(action: SettingsActionName): boolean {
  return writeActions.has(action);
}

export async function getSettingsOverview(): Promise<SettingsOverviewReadModel> {
  return requestJson<SettingsOverviewReadModel>(SETTINGS_BASE);
}

export async function listSettingsResources(
  kind: SettingsResourceKindInput,
  pagination: SettingsPaginationParams = {},
): Promise<SettingsKindPageReadModel> {
  const resourceKind = normalizeSettingsResourceKind(kind);
  return requestJson<SettingsKindPageReadModel>(
    `${SETTINGS_BASE}/${encodeURIComponent(resourceKind)}${paginationQuery(pagination)}`,
  );
}

export async function getSettingsResource(
  kind: SettingsResourceKindInput,
  resourceId: string,
): Promise<SettingsDetailReadModel> {
  const resourceKind = normalizeSettingsResourceKind(kind);
  return requestJson<SettingsDetailReadModel>(
    `${SETTINGS_BASE}/${encodeURIComponent(resourceKind)}/${encodeURIComponent(resourceId)}`,
  );
}

export async function loadSettingsReadModel(
  resource: SettingsResourceRouteAlias,
  pagination: SettingsPaginationParams = {},
): Promise<SettingsReadModel> {
  const normalized = normalizeSettingsResourceId(resource);
  if (normalized === "overview") {
    return getSettingsOverview();
  }
  return listSettingsResources(normalized, pagination);
}

export async function runSettingsAction(
  kind: SettingsResourceKindInput,
  resourceId: string | null | undefined,
  action: SettingsActionName,
  payload: SettingsPayload = {},
  reason: string | null = null,
  options: SettingsActionOptions = {},
): Promise<SettingsActionResponse> {
  const resourceKind = normalizeSettingsResourceKind(kind);
  const pathResourceId = resourceId?.trim() || null;
  const body = buildSettingsActionRequest(
    pathResourceId ?? options.resource_id ?? null,
    payload,
    reason,
    options,
  );
  const target = pathResourceId
    ? `${SETTINGS_BASE}/${encodeURIComponent(resourceKind)}/${encodeURIComponent(
        pathResourceId,
      )}/actions/${encodeURIComponent(action)}`
    : `${SETTINGS_BASE}/${encodeURIComponent(resourceKind)}/actions/${encodeURIComponent(action)}`;

  return requestJson<SettingsActionResponse>(target, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listAuthorizationPolicies(): Promise<AuthorizationPolicyApiPayload[]> {
  return requestJson<AuthorizationPolicyApiPayload[]>(`${AUTHORIZATION_BASE}/policies`);
}

export async function createAuthorizationPolicy(
  payload: AuthorizationPolicyWritePayload,
): Promise<AuthorizationPolicyApiPayload> {
  return requestJson<AuthorizationPolicyApiPayload>(`${AUTHORIZATION_BASE}/policies`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAuthorizationPolicy(
  policyId: string,
  payload: AuthorizationPolicyWritePayload,
): Promise<AuthorizationPolicyApiPayload> {
  return requestJson<AuthorizationPolicyApiPayload>(
    `${AUTHORIZATION_BASE}/policies/${encodeURIComponent(policyId)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function setAuthorizationPolicyEnabled(
  policyId: string,
  enabled: boolean,
  reason = "",
): Promise<AuthorizationPolicyApiPayload> {
  return requestJson<AuthorizationPolicyApiPayload>(
    `${AUTHORIZATION_BASE}/policies/${encodeURIComponent(policyId)}/${enabled ? "enable" : "disable"}`,
    {
      method: "POST",
      body: JSON.stringify({
        actor: { type: "settings-ui", id: "operator" },
        reason,
      }),
    },
  );
}

export async function deleteAuthorizationPolicy(
  policyId: string,
  reason = "",
): Promise<AuthorizationPolicyApiPayload> {
  return requestJson<AuthorizationPolicyApiPayload>(
    `${AUTHORIZATION_BASE}/policies/${encodeURIComponent(policyId)}`,
    {
      method: "DELETE",
      body: JSON.stringify({
        actor: { type: "settings-ui", id: "operator" },
        reason,
      }),
    },
  );
}

export async function exportAuthorizationPolicies(): Promise<AuthorizationPolicyExportPayload> {
  return requestJson<AuthorizationPolicyExportPayload>(`${AUTHORIZATION_BASE}/policies/export`);
}

export async function dryRunAuthorizationPolicy(
  request: AuthorizationCheckRequestPayload,
  reason = "",
): Promise<AuthorizationDecisionApiPayload> {
  return requestJson<AuthorizationDecisionApiPayload>(`${AUTHORIZATION_BASE}/policies/dry-run`, {
    method: "POST",
    body: JSON.stringify({
      request,
      actor: { type: "settings-ui", id: "operator" },
      reason,
    }),
  });
}

export async function previewAuthorizationPolicyImpact(
  request: AuthorizationCheckRequestPayload,
  proposedPolicies: AuthorizationPolicyWritePayload[],
  reason = "",
): Promise<AuthorizationImpactApiPayload> {
  return requestJson<AuthorizationImpactApiPayload>(`${AUTHORIZATION_BASE}/policies/impact`, {
    method: "POST",
    body: JSON.stringify({
      request,
      proposed_policies: proposedPolicies,
      actor: { type: "settings-ui", id: "operator" },
      reason,
    }),
  });
}

export async function listAuthorizationAudits(
  pagination: SettingsPaginationParams = {},
): Promise<AuthorizationAuditApiPayload[]> {
  return requestJson<AuthorizationAuditApiPayload[]>(
    `${AUTHORIZATION_BASE}/audits${paginationQuery(pagination)}`,
  );
}

export async function bootstrapImportSettings(
  reason: string,
  options: SettingsActionOptions = {},
): Promise<SettingsBootstrapImportResponse> {
  const body = buildSettingsActionRequest(options.resource_id ?? null, {}, reason, options);
  return requestJson<SettingsBootstrapImportResponse>(`${SETTINGS_BASE}/bootstrap-import`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export const settingsApi = {
  bootstrapImportSettings,
  getSettingsOverview,
  getSettingsResource,
  listSettingsResources,
  loadSettingsReadModel,
  normalizeSettingsResourceId,
  normalizeSettingsResourceKind,
  runSettingsAction,
  settingsActionRequiresReason,
};

function buildSettingsActionRequest(
  resourceId: string | null,
  payload: SettingsPayload,
  reason: string | null,
  options: SettingsActionOptions,
): SettingsActionRequest {
  return {
    resource_id: resourceId,
    payload,
    reason: reason?.trim() || null,
    actor: options.actor ?? null,
    risk: options.risk ?? null,
    dry_run: options.dry_run ?? false,
    metadata: options.metadata ?? {},
  };
}

function paginationQuery(pagination: SettingsPaginationParams): string {
  const params = new URLSearchParams();
  if (pagination.limit !== undefined) {
    params.set("limit", String(pagination.limit));
  }
  if (pagination.offset !== undefined) {
    params.set("offset", String(pagination.offset));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function normalizeSettingsResourceKey(value: unknown): string {
  return typeof value === "string" && value.trim()
    ? value.trim().toLowerCase().replace(/_/g, "-")
    : "overview";
}
