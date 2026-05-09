import { requestJson } from "@/shared/api/client";

export type AccessOwnerJsonRecord = Record<string, unknown>;

export interface AccessReadinessPayload {
  target_kind?: string;
  target_id?: string;
  target_type?: string;
  requirement?: string;
  provider?: string | null;
  kind?: string | null;
  scopes?: string[];
  status?: string;
  ready?: boolean;
  reason?: string | null;
  setup_available?: boolean;
  checks?: AccessOwnerJsonRecord[];
  metadata?: AccessOwnerJsonRecord;
  observed_at?: string | null;
}

export interface AccessAssetSummaryPayload {
  asset_id: string;
  asset_kind?: string;
  display_name?: string;
  governance_scope?: string;
  status?: string;
  readiness?: AccessReadinessPayload | null;
  consumer_modules?: string[];
  credential_binding_count?: number;
  metadata?: AccessOwnerJsonRecord;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AccessCredentialBindingPayload {
  binding_id: string;
  binding_kind?: string;
  source_kind?: string;
  source_ref?: string;
  asset_id?: string | null;
  masked_preview?: string | null;
  status?: string;
  metadata?: AccessOwnerJsonRecord;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AccessConsumerBindingPayload {
  binding_id: string;
  consumer_module?: string;
  consumer_kind?: string;
  consumer_id?: string;
  display_name?: string | null;
  enabled?: boolean;
  asset_id?: string | null;
  credential_binding_id?: string | null;
  requirement_sets?: string[][];
  status?: string;
  metadata?: AccessOwnerJsonRecord;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AccessSetupSessionPayload {
  session_id: string;
  target_kind?: string;
  target_id?: string;
  status?: string;
  flow_kind?: string;
  requested_by?: string | null;
  expires_at?: string | null;
  completed_at?: string | null;
  metadata?: AccessOwnerJsonRecord;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AccessAuditPayload {
  audit_id: string;
  action_type?: string;
  target_type?: string;
  target_id?: string | null;
  status?: string;
  operator?: string | null;
  source?: string;
  reason?: string;
  request_metadata?: AccessOwnerJsonRecord;
  result?: AccessOwnerJsonRecord | null;
  error?: AccessOwnerJsonRecord | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AccessQueryBasePayload {
  status?: string;
  degraded?: boolean;
  degraded_reason?: string | null;
  dependency_missing?: string[];
}

export interface AccessAssetListPayload extends AccessQueryBasePayload {
  assets?: AccessAssetSummaryPayload[];
  counts?: AccessOwnerJsonRecord;
  generated_at?: string | null;
}

export interface AccessAssetDetailPayload extends AccessAssetSummaryPayload, AccessQueryBasePayload {
  secret_policy?: AccessOwnerJsonRecord;
  storage_key?: string | null;
  readiness_policy?: AccessOwnerJsonRecord;
  rotation_policy?: AccessOwnerJsonRecord;
  audit_required?: boolean;
  export_policy?: AccessOwnerJsonRecord;
  credential_bindings?: AccessCredentialBindingPayload[];
  consumer_bindings?: AccessConsumerBindingPayload[];
}

export interface AccessOverviewPayload extends AccessQueryBasePayload {
  ready?: boolean;
  counts?: AccessOwnerJsonRecord;
  assets?: AccessAssetListPayload;
  readiness?: AccessReadinessPayload[];
  credential_bindings?: AccessCredentialBindingPayload[];
  consumer_bindings?: AccessConsumerBindingPayload[];
  setup_sessions?: AccessSetupSessionPayload[];
  audits?: AccessAuditPayload[];
  generated_at?: string | null;
}

export interface AccessConsumersPayload extends AccessQueryBasePayload {
  consumers?: AccessConsumerBindingPayload[];
}

export interface AccessAuditsPayload extends AccessQueryBasePayload {
  audits?: AccessAuditPayload[];
  limit?: number;
  offset?: number;
}

export interface AccessInventoryRequirementSetPayload {
  ready?: boolean;
  checks?: AccessReadinessPayload[];
}

export interface AccessInventoryTargetPayload {
  resource_type: string;
  resource_id: string;
  display_name?: string | null;
  ready?: boolean;
  setup_available?: boolean;
  requirement_sets?: AccessInventoryRequirementSetPayload[];
  metadata?: AccessOwnerJsonRecord;
}

export interface AccessInventoryPayload {
  ready?: boolean;
  targets?: AccessInventoryTargetPayload[];
  counts?: {
    total?: number;
    ready?: number;
    blocked?: number;
  };
}

export interface AccessSetupActionPayload {
  kind?: string;
  label?: string;
  description?: string | null;
  command?: string[];
  url?: string | null;
  path?: string | null;
  env_vars?: string[];
  metadata?: AccessOwnerJsonRecord;
}

export interface AccessSetupFlowPayload {
  kind?: string;
  title?: string;
  description?: string;
  action_label?: string | null;
  env_vars?: string[];
  path?: string | null;
  command?: string[];
  authorize_url?: string | null;
  callback_url?: string | null;
  verification_url?: string | null;
  user_code?: string | null;
  expires_at?: string | null;
  metadata?: AccessOwnerJsonRecord;
  actions?: AccessSetupActionPayload[];
}

export interface AccessActionRequestPayload {
  action_id: string;
  resource_kind: string;
  target_id?: string | null;
  intent: string;
  changes?: AccessOwnerJsonRecord;
  reason: string;
  confirmation?: string | null;
  risk_acknowledged?: boolean;
  actor?: string | null;
  trace_context?: AccessOwnerJsonRecord;
}

export interface AccessActionResultPayload {
  status?: string;
  asset?: AccessOwnerJsonRecord | null;
  audit_ref?: string | null;
  validation?: AccessOwnerJsonRecord;
  readiness?: AccessOwnerJsonRecord | null;
  warnings?: string[];
}

export function getAccessOverview(): Promise<AccessOverviewPayload> {
  return requestJson<AccessOverviewPayload>("/ui/access");
}

export function listAccessAssets(): Promise<AccessAssetListPayload> {
  return requestJson<AccessAssetListPayload>("/ui/access/assets");
}

export function getAccessAssetDetail(assetId: string): Promise<AccessAssetDetailPayload> {
  return requestJson<AccessAssetDetailPayload>(`/ui/access/assets/${encodeURIComponent(assetId)}`);
}

export function listAccessConsumers(): Promise<AccessConsumersPayload> {
  return requestJson<AccessConsumersPayload>("/ui/access/consumers");
}

export function listAccessAudits(params: { limit?: number; offset?: number } = {}): Promise<AccessAuditsPayload> {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 50));
  query.set("offset", String(params.offset ?? 0));
  return requestJson<AccessAuditsPayload>(`/ui/access/audits?${query.toString()}`);
}

export function getAccessInventory(
  params: { workspace_dir?: string; include_ready?: boolean; include_disabled?: boolean } = {},
): Promise<AccessInventoryPayload> {
  const query = new URLSearchParams();
  if (params.workspace_dir) query.set("workspace_dir", params.workspace_dir);
  query.set("include_ready", String(params.include_ready ?? true));
  query.set("include_disabled", String(params.include_disabled ?? true));
  return requestJson<AccessInventoryPayload>(`/access/inventory?${query.toString()}`);
}

export function getAccessSetup(target: string, workspaceDir?: string): Promise<AccessSetupFlowPayload> {
  const query = new URLSearchParams({ target });
  if (workspaceDir) query.set("workspace_dir", workspaceDir);
  return requestJson<AccessSetupFlowPayload>(`/access/setup?${query.toString()}`);
}

export function executeAccessAction(payload: AccessActionRequestPayload): Promise<AccessActionResultPayload> {
  return requestJson<AccessActionResultPayload>("/access/actions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
