import { ApiClientError, buildApiUrl, requestJson, type ApiErrorPayload } from "@/shared/api/client";

export type AgentOwnerJsonRecord = Record<string, unknown>;

export interface AgentProfileApiPayload {
  id: string;
  name: string;
  enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  identity: AgentOwnerJsonRecord & {
    display_name?: string | null;
    theme?: string | null;
    emoji?: string | null;
    avatar?: string | null;
  };
  instruction_policy: AgentOwnerJsonRecord & {
    system_prompt?: string;
    response_style?: string | null;
    thinking_default?: string | null;
    stream_by_default?: boolean;
  };
  llm_routing_policy: {
    default_llm_id?: string | null;
    fallback_llm_ids?: string[];
    image_llm_id?: string | null;
    document_llm_id?: string | null;
    [key: string]: unknown;
  };
  execution_policy: AgentOwnerJsonRecord & {
    timeout_seconds?: number;
    max_turns?: number;
  };
  runtime_preferences: AgentOwnerJsonRecord & {
    home_dir?: string | null;
    workdir?: string | null;
    workspace?: string | null;
    sandbox_mode?: string | null;
    attrs?: AgentOwnerJsonRecord;
  };
  memory: AgentOwnerJsonRecord & {
    enabled?: boolean;
    scope_ref?: string | null;
    access?: string;
  };
}

export interface AgentProfileWritePayload {
  id?: string;
  name?: string;
  enabled?: boolean;
  identity?: AgentOwnerJsonRecord;
  instruction_policy?: AgentOwnerJsonRecord;
  llm_routing_policy?: AgentOwnerJsonRecord;
  execution_policy?: AgentOwnerJsonRecord;
  runtime_preferences?: AgentOwnerJsonRecord;
  memory?: AgentOwnerJsonRecord;
  reason?: string | null;
  actor?: string | null;
}

export interface AgentProfileActionPayload {
  reason?: string | null;
  actor?: string | null;
}

export interface AgentHomeFileApiPayload {
  name: string;
  path: string;
  exists: boolean;
  language: string;
  content: string;
}

export interface AgentHomeSnapshotApiPayload {
  agent_id: string;
  agent_name: string;
  home_dir: string;
  workdir: string | null;
  files: AgentHomeFileApiPayload[];
}

export interface AgentHomeConfigApiPayload {
  home_dir: string;
  path: string;
  profile: AgentProfileApiPayload;
}

export interface AgentResolutionSummaryApiPayload {
  status: string;
  llm_routes: number;
  tools: number;
  access_grants: number;
  authorization_grants: number;
  issues: number;
}

export interface AgentResolvedLlmApiPayload {
  slot: string;
  llm_id: string;
  resolved: boolean;
  enabled: boolean;
  provider?: string | null;
  model_name?: string | null;
  capabilities: string[];
  context_window_tokens?: number | null;
  credential_binding?: string | null;
}

export interface AgentResolvedToolApiPayload {
  tool_id: string;
  resolved: boolean;
  enabled: boolean;
  name?: string | null;
  kind?: string | null;
  definition_origin?: string | null;
  access_requirements: string[];
  access_requirement_sets: string[][];
  required_effect_ids: string[];
  requires_confirmation: boolean;
  mutates_state: boolean;
}

export interface AgentAccessGrantApiPayload {
  source_type: string;
  source_id: string;
  requirement: string;
  grant_kind: string;
  status: string;
  ready: boolean;
  setup_available: boolean;
  reason?: string | null;
}

export interface AgentAuthorizationGrantApiPayload {
  policy_id: string;
  effect: string;
  action: string;
  status: string;
  effect_ids: string[];
  tool_ids: string[];
  source_kind?: string | null;
  description: string;
}

export type AgentAuthorizationGrantKind = "effect" | "tool";

export interface AgentAuthorizationGrantMutationPayload {
  agent_id: string;
  kind: AgentAuthorizationGrantKind;
  id: string;
  reason?: string;
  actor?: {
    type?: string | null;
    id?: string | null;
  };
}

export interface AgentAuthorizationGrantMutationResult {
  agent_id: string;
  kind: AgentAuthorizationGrantKind;
  id: string;
  policy_id: string;
  status: "enabled" | "revoked" | "not_found";
}

export interface AgentValidationIssueApiPayload {
  severity: string;
  code: string;
  message: string;
  ref?: string | null;
}

export interface AgentResolutionTraceApiPayload {
  source: string;
  status: string;
  detail: string;
}

export interface AgentProfileResolutionApiPayload {
  profile_id: string;
  profile_updated_at: string;
  summary: AgentResolutionSummaryApiPayload;
  llm_routes: AgentResolvedLlmApiPayload[];
  tools: AgentResolvedToolApiPayload[];
  access_grants: AgentAccessGrantApiPayload[];
  authorization_grants: AgentAuthorizationGrantApiPayload[];
  validation: AgentValidationIssueApiPayload[];
  trace: AgentResolutionTraceApiPayload[];
}

export async function listAgentProfiles(): Promise<AgentProfileApiPayload[]> {
  const payload = await requestJson<unknown[]>("/agents");
  return payload.map(normalizeAgentProfilePayload);
}

export async function getAgentProfile(profileId: string): Promise<AgentProfileApiPayload> {
  const payload = await requestJson<unknown>(`/agents/${encodeURIComponent(profileId)}`);
  return normalizeAgentProfilePayload(payload);
}

export async function createAgentProfile(
  payload: AgentProfileWritePayload & { id: string; name: string; llm_routing_policy: AgentOwnerJsonRecord },
): Promise<AgentProfileApiPayload> {
  const result = await requestJson<unknown>("/agents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeAgentProfilePayload(result);
}

export async function updateAgentProfile(
  profileId: string,
  payload: AgentProfileWritePayload,
): Promise<AgentProfileApiPayload> {
  const result = await requestJson<unknown>(`/agents/${encodeURIComponent(profileId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return normalizeAgentProfilePayload(result);
}

export async function enableAgentProfile(
  profileId: string,
  payload?: AgentProfileActionPayload,
): Promise<AgentProfileApiPayload> {
  const result = await requestJson<unknown>(`/agents/${encodeURIComponent(profileId)}/enable`, {
    method: "POST",
    ...(hasActionPayload(payload) ? { body: JSON.stringify(payload) } : {}),
  });
  return normalizeAgentProfilePayload(result);
}

export async function disableAgentProfile(
  profileId: string,
  payload?: AgentProfileActionPayload,
): Promise<AgentProfileApiPayload> {
  const result = await requestJson<unknown>(`/agents/${encodeURIComponent(profileId)}/disable`, {
    method: "POST",
    ...(hasActionPayload(payload) ? { body: JSON.stringify(payload) } : {}),
  });
  return normalizeAgentProfilePayload(result);
}

export async function deleteAgentProfile(
  profileId: string,
  payload?: AgentProfileActionPayload,
): Promise<void> {
  const params = new URLSearchParams();
  if (payload?.reason) params.set("reason", payload.reason);
  if (payload?.actor) params.set("actor", payload.actor);
  const query = params.toString();
  const url = buildApiUrl(`/agents/${encodeURIComponent(profileId)}${query ? `?${query}` : ""}`);
  const response = await fetch(url, { method: "DELETE" });
  if (response.ok) return;

  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  const errorPayload = await readErrorPayload(response, url, contentType);
  throw new ApiClientError(
    response.status,
    errorPayload?.message ?? `Request failed with status ${response.status}`,
    errorPayload,
  );
}

export async function getAgentHome(profileId: string): Promise<AgentHomeSnapshotApiPayload> {
  return requestJson<AgentHomeSnapshotApiPayload>(`/agents/${encodeURIComponent(profileId)}/home`);
}

export async function getAgentProfileResolution(
  profileId: string,
): Promise<AgentProfileResolutionApiPayload> {
  return requestJson<AgentProfileResolutionApiPayload>(
    `/agents/${encodeURIComponent(profileId)}/resolution`,
  );
}

export async function grantAgentAuthorization(
  payload: AgentAuthorizationGrantMutationPayload,
): Promise<AgentAuthorizationGrantMutationResult> {
  return requestJson<AgentAuthorizationGrantMutationResult>("/authorization/agent-grants", {
    method: "POST",
    body: JSON.stringify(withSettingsActor(payload)),
  });
}

export async function revokeAgentAuthorization(
  payload: AgentAuthorizationGrantMutationPayload,
): Promise<AgentAuthorizationGrantMutationResult> {
  return requestJson<AgentAuthorizationGrantMutationResult>("/authorization/agent-grants/revoke", {
    method: "POST",
    body: JSON.stringify(withSettingsActor(payload)),
  });
}

export async function updateAgentHomeFiles(
  profileId: string,
  files: Array<{ name: string; content: string }>,
): Promise<AgentHomeSnapshotApiPayload> {
  return requestJson<AgentHomeSnapshotApiPayload>(`/agents/${encodeURIComponent(profileId)}/home`, {
    method: "PUT",
    body: JSON.stringify({ files }),
  });
}

export async function syncAgentHome(profileId: string): Promise<AgentHomeConfigApiPayload> {
  const result = await requestJson<AgentHomeConfigApiPayload>(`/agents/${encodeURIComponent(profileId)}/sync-home`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    ...result,
    profile: normalizeAgentProfilePayload(result.profile),
  };
}

export async function exportAgentHome(profileId: string): Promise<AgentHomeConfigApiPayload> {
  const result = await requestJson<AgentHomeConfigApiPayload>(`/agents/${encodeURIComponent(profileId)}/export-home`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return {
    ...result,
    profile: normalizeAgentProfilePayload(result.profile),
  };
}

function hasActionPayload(payload: AgentProfileActionPayload | undefined): payload is AgentProfileActionPayload {
  return Boolean(payload?.reason || payload?.actor);
}

function normalizeAgentProfilePayload(value: unknown): AgentProfileApiPayload {
  const payload = recordValue(value);
  if (!payload) {
    throw new Error("Expected agent profile response.");
  }
  const id = stringValue(payload.id);
  const name = stringValue(payload.name, id || "Agent");
  const identity = recordValue(payload.identity) ?? {};
  const instructionPolicy = recordValue(payload.instruction_policy) ?? {};
  const llmRoutingPolicy = recordValue(payload.llm_routing_policy) ?? {};
  const executionPolicy = recordValue(payload.execution_policy) ?? {};
  const runtimePreferences = recordValue(payload.runtime_preferences) ?? {};
  const memory = recordValue(payload.memory) ?? {};
  const attrs = recordValue(runtimePreferences.attrs) ?? {};

  return {
    ...(payload as Partial<AgentProfileApiPayload>),
    id,
    name,
    enabled: payload.enabled !== false,
    created_at: stringOrNull(payload.created_at),
    updated_at: stringOrNull(payload.updated_at),
    identity: {
      ...identity,
      display_name: stringOrNull(identity.display_name),
      theme: stringOrNull(identity.theme),
      emoji: stringOrNull(identity.emoji),
      avatar: stringOrNull(identity.avatar),
    },
    instruction_policy: {
      ...instructionPolicy,
      system_prompt: stringValue(instructionPolicy.system_prompt),
      response_style: stringOrNull(instructionPolicy.response_style),
      thinking_default: stringOrNull(instructionPolicy.thinking_default),
      stream_by_default: instructionPolicy.stream_by_default === true,
    },
    llm_routing_policy: {
      ...llmRoutingPolicy,
      default_llm_id: stringOrNull(llmRoutingPolicy.default_llm_id),
      fallback_llm_ids: Array.isArray(llmRoutingPolicy.fallback_llm_ids)
        ? llmRoutingPolicy.fallback_llm_ids.map((item) => stringValue(item)).filter(Boolean)
        : [],
      image_llm_id: stringOrNull(llmRoutingPolicy.image_llm_id),
      document_llm_id: stringOrNull(llmRoutingPolicy.document_llm_id),
    },
    execution_policy: {
      ...executionPolicy,
      timeout_seconds: positiveNumber(executionPolicy.timeout_seconds, 120),
      max_turns: positiveNumber(executionPolicy.max_turns, 99),
    },
    runtime_preferences: {
      ...runtimePreferences,
      home_dir: stringOrNull(runtimePreferences.home_dir),
      workdir: stringOrNull(runtimePreferences.workdir),
      workspace: stringOrNull(runtimePreferences.workspace),
      sandbox_mode: stringOrNull(runtimePreferences.sandbox_mode),
      attrs,
    },
    memory: {
      ...memory,
      enabled: memory.enabled !== false,
      scope_ref: stringOrNull(memory.scope_ref),
      access: stringValue(memory.access, "read_write"),
    },
  };
}

function recordValue(value: unknown): AgentOwnerJsonRecord | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as AgentOwnerJsonRecord;
  }
  return null;
}

function stringValue(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function stringOrNull(value: unknown): string | null {
  const text = stringValue(value).trim();
  return text ? text : null;
}

function positiveNumber(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function withSettingsActor(
  payload: AgentAuthorizationGrantMutationPayload,
): AgentAuthorizationGrantMutationPayload {
  return {
    ...payload,
    actor: payload.actor ?? { type: "settings-ui", id: "operator" },
  };
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
