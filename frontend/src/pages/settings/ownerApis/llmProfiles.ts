import { requestJson } from "@/shared/api/client";

export interface LlmDefaultsApiPayload {
  temperature?: number | null;
  top_p?: number | null;
  max_output_tokens?: number | null;
  reasoning_effort?: string | null;
  extra_body?: Record<string, unknown>;
}

export interface LlmProfileApiPayload {
  id: string;
  provider: string;
  api_family: string;
  model_name: string;
  context_window_tokens: number | null;
  model_family: string;
  capabilities: string[];
  default_params: LlmDefaultsApiPayload;
  base_url: string | null;
  credential_binding_id: string | null;
  timeout_seconds: number;
  max_concurrency: number | null;
  concurrency_key: string | null;
  source_kind: string;
  enabled: boolean;
}

export interface LlmInvocationApiPayload {
  id: string;
  llm_id: string;
  status: string;
  result?: {
    text?: string | null;
    usage?: Record<string, unknown> | null;
    finish_reason?: string | null;
    metadata?: Record<string, unknown>;
  } | null;
  error?: {
    message: string;
    code: string;
    details?: Record<string, unknown>;
  } | null;
  provider_request_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface LlmWarmupApiPayload {
  llm_id: string;
  status: string;
  details: Record<string, unknown>;
}

export interface LlmInvokeRequestPayload {
  messages: Array<{
    role: "system" | "user" | "assistant" | "tool";
    content: unknown;
    name?: string | null;
    tool_call_id?: string | null;
    metadata?: Record<string, unknown>;
  }>;
  tool_schemas?: unknown[];
  response_format?: Record<string, unknown> | null;
  overrides?: Record<string, unknown>;
  invocation_id?: string | null;
}

export type LlmProfileWritePayload = Omit<LlmProfileApiPayload, "source_kind"> & {
  reason?: string | null;
};

export type LlmProfileTestPayload = LlmInvokeRequestPayload & {
  profile: LlmProfileWritePayload;
};

export function listLlmProfiles(): Promise<LlmProfileApiPayload[]> {
  return requestJson<LlmProfileApiPayload[]>("/llms");
}

export function createLlmProfile(payload: LlmProfileWritePayload): Promise<LlmProfileApiPayload> {
  return requestJson<LlmProfileApiPayload>("/llms", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getLlmProfile(profileId: string): Promise<LlmProfileApiPayload> {
  return requestJson<LlmProfileApiPayload>(`/llms/${encodeURIComponent(profileId)}`);
}

export function updateLlmProfile(
  profileId: string,
  payload: LlmProfileWritePayload,
): Promise<LlmProfileApiPayload> {
  return requestJson<LlmProfileApiPayload>(`/llms/${encodeURIComponent(profileId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function setLlmProfileEnabled(
  profileId: string,
  enabled: boolean,
): Promise<LlmProfileApiPayload> {
  return requestJson<LlmProfileApiPayload>(
    `/llms/${encodeURIComponent(profileId)}/${enabled ? "enable" : "disable"}`,
    { method: "POST" },
  );
}

export function invokeLlmProfile(
  profileId: string,
  payload: LlmInvokeRequestPayload,
): Promise<LlmInvocationApiPayload> {
  return requestJson<LlmInvocationApiPayload>(`/llms/${encodeURIComponent(profileId)}/invoke`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function warmupLlmProfile(profileId: string): Promise<LlmWarmupApiPayload> {
  return requestJson<LlmWarmupApiPayload>(`/llms/${encodeURIComponent(profileId)}/warmup`, {
    method: "POST",
  });
}

export function testLlmProfile(payload: LlmProfileTestPayload): Promise<LlmInvocationApiPayload> {
  return requestJson<LlmInvocationApiPayload>("/llms/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
