import { ApiClientError, buildApiUrl, requestJson, type ApiErrorPayload } from "@/shared/api/client";

export type AgentOwnerJsonRecord = Record<string, unknown>;

export interface AgentProfileApiPayload {
  id: string;
  name: string;
  description: string;
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
    memory_retrieval_backend?: string | null;
    attrs?: AgentOwnerJsonRecord;
  };
}

export interface AgentProfileWritePayload {
  id?: string;
  name?: string;
  description?: string;
  enabled?: boolean;
  identity?: AgentOwnerJsonRecord;
  instruction_policy?: AgentOwnerJsonRecord;
  llm_routing_policy?: AgentOwnerJsonRecord;
  execution_policy?: AgentOwnerJsonRecord;
  runtime_preferences?: AgentOwnerJsonRecord;
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
  skills: number;
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
  source_kind?: string | null;
  access_requirements: string[];
  access_requirement_sets: string[][];
  required_effect_ids: string[];
  requires_confirmation: boolean;
  mutates_state: boolean;
}

export interface AgentResolvedSkillApiPayload {
  skill_id: string;
  resolved: boolean;
  name?: string | null;
  source?: string | null;
  required_tools: string[];
  optional_tools: string[];
  suggested_tools: string[];
  required_effects: string[];
  access_requirements: string[];
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
  skills: AgentResolvedSkillApiPayload[];
  access_grants: AgentAccessGrantApiPayload[];
  authorization_grants: AgentAuthorizationGrantApiPayload[];
  validation: AgentValidationIssueApiPayload[];
  trace: AgentResolutionTraceApiPayload[];
}

export interface EventRecordApiPayload {
  cursor: string;
  event_id: string;
  event_name: string;
  topic: string | null;
  kind: string;
  source_event_name: string;
  source_payload: AgentOwnerJsonRecord;
  source_created_at: string;
  created_at: string;
}

export interface EventRecordsApiPayload {
  filters: Record<string, string>;
  topic_count: number;
  records: EventRecordApiPayload[];
}

export async function listAgentProfiles(): Promise<AgentProfileApiPayload[]> {
  return requestJson<AgentProfileApiPayload[]>("/agents");
}

export async function getAgentProfile(profileId: string): Promise<AgentProfileApiPayload> {
  return requestJson<AgentProfileApiPayload>(`/agents/${encodeURIComponent(profileId)}`);
}

export async function createAgentProfile(
  payload: AgentProfileWritePayload & { id: string; name: string; llm_routing_policy: AgentOwnerJsonRecord },
): Promise<AgentProfileApiPayload> {
  return requestJson<AgentProfileApiPayload>("/agents", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAgentProfile(
  profileId: string,
  payload: AgentProfileWritePayload,
): Promise<AgentProfileApiPayload> {
  return requestJson<AgentProfileApiPayload>(`/agents/${encodeURIComponent(profileId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function enableAgentProfile(
  profileId: string,
  payload?: AgentProfileActionPayload,
): Promise<AgentProfileApiPayload> {
  return requestJson<AgentProfileApiPayload>(`/agents/${encodeURIComponent(profileId)}/enable`, {
    method: "POST",
    ...(hasActionPayload(payload) ? { body: JSON.stringify(payload) } : {}),
  });
}

export async function disableAgentProfile(
  profileId: string,
  payload?: AgentProfileActionPayload,
): Promise<AgentProfileApiPayload> {
  return requestJson<AgentProfileApiPayload>(`/agents/${encodeURIComponent(profileId)}/disable`, {
    method: "POST",
    ...(hasActionPayload(payload) ? { body: JSON.stringify(payload) } : {}),
  });
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
  return requestJson<AgentHomeConfigApiPayload>(`/agents/${encodeURIComponent(profileId)}/sync-home`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function exportAgentHome(profileId: string): Promise<AgentHomeConfigApiPayload> {
  return requestJson<AgentHomeConfigApiPayload>(`/agents/${encodeURIComponent(profileId)}/export-home`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function listAgentProfileEvents(
  profileId: string,
  limit = 25,
): Promise<EventRecordsApiPayload> {
  const query = new URLSearchParams({
    topic_prefix: "events.named.agent.profile",
    payload_key: "agent_profile_id",
    payload_value: profileId,
    limit: String(limit),
  });
  return requestJson<EventRecordsApiPayload>(`/events/records?${query.toString()}`);
}

function hasActionPayload(payload: AgentProfileActionPayload | undefined): payload is AgentProfileActionPayload {
  return Boolean(payload?.reason || payload?.actor);
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
