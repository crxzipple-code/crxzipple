import { ApiClientError, buildApiUrl, requestJson, type ApiErrorPayload } from "@/shared/api/client";

import {
  getAccessOverview,
  type AccessCredentialBindingPayload,
  type AccessCredentialRequirementPayload,
} from "./accessAssets";

export type MemoryOwnerJsonRecord = Record<string, unknown>;

export interface MemorySpaceApiPayload {
  scope_ref: string;
  owner_kind: string;
  owner_id: string;
  engine_id: string;
  storage_root: string;
  retrieval_backend: string;
  status: string;
  metadata: MemoryOwnerJsonRecord;
  created_at: string;
  updated_at: string;
}

export interface MemoryPolicyApiPayload {
  policy_id: string;
  target_kind: string;
  target_id?: string | null;
  recall_enabled: boolean;
  remember_enabled: boolean;
  max_recall_items: number;
  retention: string;
  status: string;
  metadata: MemoryOwnerJsonRecord;
  created_at: string;
  updated_at: string;
}

export interface MemorySpaceActionPayload {
  scope_ref: string;
  action: string;
  status: string;
  rebuilt?: boolean;
  file_count?: number;
  indexed_file_count?: number | null;
  generated_at?: string;
}

export interface MemorySpaceExportPayload {
  scope_ref: string;
  generated_at?: string;
  space?: MemoryOwnerJsonRecord;
  policies?: MemoryOwnerJsonRecord[];
  files?: MemoryOwnerJsonRecord[];
}

export interface MemoryResolvedScopePayload {
  scope_ref: string;
  space_id: string;
  storage_root: string;
  retrieval_backend: string;
  engine_id: string;
}

export interface MemoryResolvedLayerPayload extends MemoryResolvedScopePayload {
  owner_kind: string;
  layer_kind: string;
  access: string;
  default_write: boolean;
}

export interface MemoryRuntimeRecallItemPayload {
  path: string;
  kind: string;
  citation: string;
  text: string;
  start_line: number;
  end_line: number;
  score?: number | null;
  source_scope_ref?: string | null;
  source_layer_kind?: string | null;
  source_owner_kind?: string | null;
}

export interface MemoryRuntimeRecallPayload {
  scope: MemoryResolvedScopePayload;
  searched_layers?: MemoryResolvedLayerPayload[];
  query?: string | null;
  citation?: string | null;
  items: MemoryRuntimeRecallItemPayload[];
}

export interface MemoryRuntimeRememberPayload {
  scope: MemoryResolvedScopePayload;
  target_layer?: MemoryResolvedLayerPayload | null;
  status: string;
  write_result?: {
    path: string;
    line_start: number;
    line_end: number;
    kind: string;
  } | null;
  metadata: MemoryOwnerJsonRecord;
}

export interface MemoryRuntimeRecallRequestPayload {
  agent_id?: string | null;
  scope_ref?: string | null;
  query?: string | null;
  citation?: string | null;
  intent?: string | null;
  max_items?: number;
  max_tokens?: number | null;
  metadata?: MemoryOwnerJsonRecord;
}

export interface MemoryRuntimeRememberRequestPayload {
  agent_id?: string | null;
  scope_ref?: string | null;
  target_scope_ref?: string | null;
  target_layer_kind?: string | null;
  content: string;
  title?: string | null;
  intent?: string;
  retention?: string;
  metadata?: MemoryOwnerJsonRecord;
}

export interface MemoryLegacyMigrationPayload {
  agent_ids?: string[];
  dry_run?: boolean;
  delete_sidecar?: boolean;
}

export interface MemoryLegacyMigrationResultPayload {
  dry_run: boolean;
  scanned: number;
  updated_profiles: number;
  created_spaces: number;
  copied_files: number;
  agents?: MemoryOwnerJsonRecord[];
}

export interface MemorySpaceWritePayload {
  owner_kind: string;
  owner_id: string;
  storage_root?: string | null;
  retrieval_backend: string;
  engine_id: string;
  status: string;
  metadata?: MemoryOwnerJsonRecord;
}

export interface MemoryPolicyWritePayload {
  target_kind: string;
  target_id?: string | null;
  recall_enabled: boolean;
  remember_enabled: boolean;
  max_recall_items: number;
  retention: string;
  status: string;
  metadata?: MemoryOwnerJsonRecord;
}

export interface MemoryRuntimeDefaultsPayload {
  id?: string;
  storage_root?: string | null;
  retrieval_backend?: string;
  vector_provider?: string;
  vector_model?: string | null;
  vector_base_url?: string | null;
  vector_credential_binding_id?: string | null;
  vector_timeout_seconds?: number;
  watch_interval_seconds?: number;
  enabled?: boolean;
}

export interface MemoryCredentialBindingOption {
  binding_id: string;
  label: string;
  binding_kind: string;
  source_kind: string;
  source_ref: string;
  status: string;
  asset_id: string | null;
  masked_preview: string | null;
}

export interface MemoryAccessSupportPayload {
  runtime_defaults: MemoryRuntimeDefaultsPayload;
  credential_bindings: MemoryCredentialBindingOption[];
  credential_requirement: AccessCredentialRequirementPayload | null;
}

export function listMemorySpaces(includeDisabled = true): Promise<MemorySpaceApiPayload[]> {
  const query = includeDisabled ? "?include_disabled=true" : "";
  return requestJson<MemorySpaceApiPayload[]>(`/memory/spaces${query}`);
}

export function getMemorySpace(scopeRef: string): Promise<MemorySpaceApiPayload> {
  return requestJson<MemorySpaceApiPayload>(`/memory/spaces/${encodeURIComponent(scopeRef)}`);
}

export function upsertMemorySpace(
  scopeRef: string,
  payload: MemorySpaceWritePayload,
): Promise<MemorySpaceApiPayload> {
  return requestJson<MemorySpaceApiPayload>(`/memory/spaces/${encodeURIComponent(scopeRef)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function disableMemorySpace(scopeRef: string): Promise<MemorySpaceApiPayload> {
  return requestJson<MemorySpaceApiPayload>(`/memory/spaces/${encodeURIComponent(scopeRef)}/disable`, {
    method: "POST",
  });
}

export async function deleteMemorySpace(scopeRef: string): Promise<void> {
  await requestVoid(`/memory/spaces/${encodeURIComponent(scopeRef)}`, { method: "DELETE" });
}

export function rebuildMemorySpaceIndex(scopeRef: string): Promise<MemorySpaceActionPayload> {
  return requestJson<MemorySpaceActionPayload>(
    `/memory/spaces/${encodeURIComponent(scopeRef)}/actions/rebuild-index`,
    { method: "POST" },
  );
}

export function exportMemorySpace(scopeRef: string): Promise<MemorySpaceExportPayload> {
  return requestJson<MemorySpaceExportPayload>(
    `/memory/spaces/${encodeURIComponent(scopeRef)}/actions/export`,
    { method: "POST" },
  );
}

export function recallMemoryRuntime(
  payload: MemoryRuntimeRecallRequestPayload,
): Promise<MemoryRuntimeRecallPayload> {
  return requestJson<MemoryRuntimeRecallPayload>("/memory/runtime/recall", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function rememberMemoryRuntime(
  payload: MemoryRuntimeRememberRequestPayload,
): Promise<MemoryRuntimeRememberPayload> {
  return requestJson<MemoryRuntimeRememberPayload>("/memory/runtime/remember", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function migrateLegacyAgentHomes(
  payload: MemoryLegacyMigrationPayload,
): Promise<MemoryLegacyMigrationResultPayload> {
  return requestJson<MemoryLegacyMigrationResultPayload>(
    "/memory/actions/migrate-legacy-agent-homes",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function listMemoryPolicies(includeDisabled = true): Promise<MemoryPolicyApiPayload[]> {
  const query = includeDisabled ? "?include_disabled=true" : "";
  return requestJson<MemoryPolicyApiPayload[]>(`/memory/policies${query}`);
}

export function upsertMemoryPolicy(
  policyId: string,
  payload: MemoryPolicyWritePayload,
): Promise<MemoryPolicyApiPayload> {
  return requestJson<MemoryPolicyApiPayload>(`/memory/policies/${encodeURIComponent(policyId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function disableMemoryPolicy(policyId: string): Promise<MemoryPolicyApiPayload> {
  return requestJson<MemoryPolicyApiPayload>(`/memory/policies/${encodeURIComponent(policyId)}/disable`, {
    method: "POST",
  });
}

export async function deleteMemoryPolicy(policyId: string): Promise<void> {
  await requestVoid(`/memory/policies/${encodeURIComponent(policyId)}`, { method: "DELETE" });
}

export async function getMemoryAccessSupport(): Promise<MemoryAccessSupportPayload> {
  const [runtimeDefaults, accessOverview] = await Promise.all([
    getMemoryRuntimeDefaults(),
    getAccessOverview(),
  ]);
  const credentialRequirement = (accessOverview.credential_requirements ?? []).find(
    (requirement) =>
      requirement.consumer_module === "memory" &&
      requirement.consumer_kind === "memory_engine",
  ) ?? null;
  const credentialBindings = (accessOverview.credential_bindings ?? [])
    .filter((binding) => binding.binding_kind === "api_key")
    .map(memoryCredentialBindingOption)
    .sort((left, right) => left.label.localeCompare(right.label));
  return {
    runtime_defaults: runtimeDefaults,
    credential_bindings: credentialBindings,
    credential_requirement: credentialRequirement,
  };
}

export async function getMemoryRuntimeDefaults(): Promise<MemoryRuntimeDefaultsPayload> {
  return requestJson<MemoryRuntimeDefaultsPayload>("/memory/runtime-defaults");
}

export async function updateMemoryRuntimeDefaults(
  changes: MemoryRuntimeDefaultsPayload,
): Promise<MemoryRuntimeDefaultsPayload> {
  return requestJson<MemoryRuntimeDefaultsPayload>("/memory/runtime-defaults", {
    method: "PUT",
    body: JSON.stringify(changes),
  });
}

async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const url = buildApiUrl(path);
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (response.ok) return;

  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  const errorPayload = await readErrorPayload(response, url, contentType);
  throw new ApiClientError(
    response.status,
    errorPayload?.message ?? `Request failed with status ${response.status}`,
    errorPayload,
  );
}

async function readErrorPayload(
  response: Response,
  url: string,
  contentType: string,
): Promise<ApiErrorPayload | null> {
  if (!contentType.includes("json")) {
    const body = await response.text();
    const preview = body.trim().replace(/\s+/g, " ").slice(0, 160);
    return {
      code: "non_json_error_response",
      message: preview
        ? `Expected JSON error payload from ${url}, but received ${contentType || "unknown content type"}: ${preview}`
        : `Expected JSON error payload from ${url}, but received ${contentType || "unknown content type"}.`,
    };
  }

  try {
    const value = await response.json() as { detail?: unknown; message?: unknown; code?: unknown };
    const message = typeof value.message === "string"
      ? value.message
      : typeof value.detail === "string"
        ? value.detail
        : Array.isArray(value.detail)
          ? "Request validation failed."
          : null;
    if (!message) return null;
    return {
      code: typeof value.code === "string" ? value.code : "request_failed",
      message,
    };
  } catch {
    return null;
  }
}

function memoryCredentialBindingOption(
  binding: AccessCredentialBindingPayload,
): MemoryCredentialBindingOption {
  const bindingId = binding.binding_id;
  const sourceKind = binding.source_kind ?? "unknown";
  const sourceRef = binding.source_ref ?? "";
  return {
    binding_id: bindingId,
    label: sourceRef ? `${bindingId} (${sourceKind}:${sourceRef})` : bindingId,
    binding_kind: binding.binding_kind ?? "unknown",
    source_kind: sourceKind,
    source_ref: sourceRef,
    status: binding.status ?? "unknown",
    asset_id: binding.asset_id ?? null,
    masked_preview: binding.masked_preview ?? null,
  };
}
