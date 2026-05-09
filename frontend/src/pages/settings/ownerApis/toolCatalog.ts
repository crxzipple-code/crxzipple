import { requestJson } from "@/shared/api/client";

export interface ToolExecutionPolicyApiPayload {
  timeout_seconds: number;
  requires_confirmation: boolean;
  mutates_state: boolean;
}

export interface ToolExecutionSupportApiPayload {
  supported_modes: string[];
  supported_strategies: string[];
  supported_environments: string[];
}

export interface ToolDiscoveryProviderApiPayload {
  name: string;
  description: string;
  source_kind: string;
}

export interface ToolExecutionTargetApiPayload {
  mode: string;
  strategy: string;
  environment: string;
}

export interface ToolParameterApiPayload {
  name: string;
  data_type: string;
  description: string;
  required: boolean;
}

export interface ToolApiPayload {
  id: string;
  name: string;
  description: string;
  kind: string;
  parameters: ToolParameterApiPayload[];
  tags: string[];
  required_effect_ids: string[];
  access_requirements: string[];
  access_requirement_sets: string[][];
  execution_policy: ToolExecutionPolicyApiPayload;
  execution_support: ToolExecutionSupportApiPayload;
  source_kind: string;
  runtime_key: string | null;
  enabled: boolean;
}

export interface ToolRootApiPayload {
  path: string;
  exists: boolean;
}

export interface ToolRunResultApiPayload {
  content: unknown;
  details: unknown;
  metadata: Record<string, unknown>;
}

export interface ToolRunErrorApiPayload {
  message: string;
  code: string;
  details: Record<string, unknown>;
}

export interface ToolRunApiPayload {
  id: string;
  tool_id: string;
  target: ToolExecutionTargetApiPayload;
  status: string;
  input_payload: Record<string, unknown>;
  result: ToolRunResultApiPayload | null;
  error: ToolRunErrorApiPayload | null;
  output_payload: unknown;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  attempt_count: number;
  max_attempts: number;
  worker_id: string | null;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
  cancel_requested_at: string | null;
}

export interface ExecuteToolRunApiRequest {
  arguments?: Record<string, unknown>;
  mode?: string;
  strategy?: string;
  environment?: string;
  run_id?: string | null;
}

export interface PruneExpiredToolWorkersApiPayload {
  pruned_count: number;
  worker_ids: string[];
  cutoff: string;
}

export function listTools(enabledOnly = false): Promise<ToolApiPayload[]> {
  return requestJson<ToolApiPayload[]>(`/tools${enabledOnly ? "?enabled_only=true" : ""}`);
}

export function listToolRoots(): Promise<ToolRootApiPayload[]> {
  return requestJson<ToolRootApiPayload[]>("/tools/roots");
}

export function listDiscoveryProviders(): Promise<ToolDiscoveryProviderApiPayload[]> {
  return requestJson<ToolDiscoveryProviderApiPayload[]>("/tools/providers");
}

export function discoverTools(provider?: string | null): Promise<ToolApiPayload[]> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return requestJson<ToolApiPayload[]>(`/tools/discover${query}`, { method: "POST" });
}

export function discoverLocalTools(): Promise<ToolApiPayload[]> {
  return requestJson<ToolApiPayload[]>("/tools/discover-local", { method: "POST" });
}

export function executeToolRun(
  toolId: string,
  payload: ExecuteToolRunApiRequest,
): Promise<ToolRunApiPayload> {
  return requestJson<ToolRunApiPayload>(`/tools/${encodeURIComponent(toolId)}/runs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listToolRuns(toolId: string): Promise<ToolRunApiPayload[]> {
  return requestJson<ToolRunApiPayload[]>(`/tools/${encodeURIComponent(toolId)}/runs`);
}

export function getToolRun(runId: string): Promise<ToolRunApiPayload> {
  return requestJson<ToolRunApiPayload>(`/tools/runs/${encodeURIComponent(runId)}`);
}

export function cancelToolRun(runId: string): Promise<ToolRunApiPayload> {
  return requestJson<ToolRunApiPayload>(`/tools/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  });
}

export function retryToolRun(runId: string): Promise<ToolRunApiPayload> {
  return requestJson<ToolRunApiPayload>(`/tools/runs/${encodeURIComponent(runId)}/retry`, {
    method: "POST",
  });
}

export function pruneExpiredToolWorkers(retentionSeconds = 3600): Promise<PruneExpiredToolWorkersApiPayload> {
  return requestJson<PruneExpiredToolWorkersApiPayload>(
    `/tools/workers/prune-expired?retention_seconds=${encodeURIComponent(String(retentionSeconds))}`,
    { method: "POST" },
  );
}
