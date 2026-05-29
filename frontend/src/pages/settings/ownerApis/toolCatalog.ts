import { buildApiUrl, requestJson } from "@/shared/api/client";

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

export interface ToolSourceApiPayload {
  source_id: string;
  kind: string;
  display_name: string;
  description: string;
  config: Record<string, unknown>;
  credential_requirements: Record<string, unknown>[];
  runtime_requirements: string[];
  status: string;
  revision: number;
  config_hash: string;
  last_discovered_at: string | null;
  last_discovery_status: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ToolSourceDiscoveryRunApiPayload {
  discovery_run_id: string;
  source_id: string;
  source_revision: number;
  config_hash: string;
  status: string;
  discovered_at: string;
  function_count: number;
  provider_backend_count: number;
  error_message: string | null;
  metadata: Record<string, unknown>;
}

export interface ToolSourceSyncApiPayload {
  source: ToolSourceApiPayload;
  skipped: boolean;
  error_message: string | null;
  discovery: ToolSourceDiscoveryRunApiPayload | null;
}

export interface ToolSourceWriteApiRequest {
  source_id: string;
  kind: string;
  display_name: string;
  description?: string;
  config?: Record<string, unknown>;
  credential_requirements?: Record<string, unknown>[];
  runtime_requirements?: string[];
  status?: string;
}

export interface ToolFunctionApiPayload {
  function_id: string;
  source_id: string;
  stable_key: string;
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  runtime_kind: string;
  handler_ref: string;
  capabilities: string[];
  kind: string;
  parameters: ToolParameterApiPayload[];
  tags: string[];
  required_effect_ids: string[];
  access_requirement_sets: string[][];
  runtime_requirement_sets: string[][];
  context_requirements: string[];
  credential_requirements: ToolCredentialRequirementSetApiPayload[];
  execution_policy: ToolExecutionPolicyApiPayload;
  execution_support: ToolExecutionSupportApiPayload;
  definition_origin: string;
  runtime_key: string | null;
  schema_hash: string;
  status: string;
  enabled: boolean;
  revision: number;
  trust_policy: Record<string, unknown>;
  approval_policy: Record<string, unknown>;
  credential_binding_overrides: Record<string, string>;
  required_effect_overrides: string[] | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
  last_seen_at: string | null;
  stale_since: string | null;
  deprecated_at: string | null;
}

export interface ToolProviderBackendApiPayload {
  backend_id: string;
  source_id: string;
  capability: string;
  display_name: string;
  credential_requirements: Record<string, unknown>[];
  runtime_ref: Record<string, unknown>;
  priority: number;
  enabled: boolean;
  status: string;
  readiness: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ToolFunctionPolicyApiRequest {
  trust_policy: Record<string, unknown>;
  approval_policy: Record<string, unknown>;
  credential_binding_overrides: Record<string, string>;
  required_effect_overrides: string[] | null;
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

export interface ToolCredentialRequirementConsumerApiPayload {
  consumer_id: string;
  module: string;
  component: string;
  runtime_ref: string | null;
  metadata: Record<string, unknown>;
}

export interface ToolCredentialRequirementSlotApiPayload {
  slot: string;
  expected_kind: string;
  binding_id: string | null;
  required: boolean;
  display_name: string | null;
  scopes: string[];
  metadata: Record<string, unknown>;
}

export interface ToolCredentialSetupFlowHintApiPayload {
  flow_kind: string;
  provider: string | null;
  authorization_url: string | null;
  token_url: string | null;
  device_code_url: string | null;
  callback_url: string | null;
  metadata: Record<string, unknown>;
}

export interface ToolCredentialRequirementApiPayload {
  requirement_id: string;
  consumer: ToolCredentialRequirementConsumerApiPayload;
  slot: ToolCredentialRequirementSlotApiPayload;
  provider: string | null;
  transport: string;
  parameter_name: string | null;
  setup_flow_hint: ToolCredentialSetupFlowHintApiPayload;
  metadata: Record<string, unknown>;
}

export interface ToolCredentialRequirementSetApiPayload {
  requirement_set_id: string;
  consumer: ToolCredentialRequirementConsumerApiPayload;
  requirements: ToolCredentialRequirementApiPayload[];
  alternative: boolean;
  metadata: Record<string, unknown>;
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
  runtime_requirement_sets: string[][];
  context_requirements: string[];
  credential_requirements?: ToolCredentialRequirementSetApiPayload[];
  execution_policy: ToolExecutionPolicyApiPayload;
  execution_support: ToolExecutionSupportApiPayload;
  definition_origin: string;
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
  function_id: string | null;
  function_revision: number | null;
  source_id: string | null;
  source_revision: number | null;
  schema_hash: string | null;
  target: ToolExecutionTargetApiPayload;
  status: string;
  input_payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
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

export interface ToolAccessCredentialBindingPayload {
  binding_id: string;
  binding_kind?: string;
  source_kind?: string;
  source_ref?: string;
  asset_id?: string | null;
  masked_preview?: string | null;
  status?: string;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ToolAccessCredentialRequirementPayload {
  requirement_id?: string;
  consumer_module?: string;
  consumer_kind?: string;
  consumer_id?: string;
  slot?: string;
  expected_kind?: string;
  binding_id?: string | null;
  consumer_binding_id?: string | null;
  display_name?: string | null;
  provider?: string | null;
  required?: boolean;
  ready?: boolean;
  missing?: boolean;
  status?: string;
  reason?: string | null;
  setup_flow_hint?: {
    flow_kind?: string;
    provider?: string | null;
    authorization_url?: string | null;
    token_url?: string | null;
    device_code_url?: string | null;
    callback_url?: string | null;
    metadata?: Record<string, unknown>;
  };
  metadata?: Record<string, unknown>;
  last_checked_at?: string | null;
}

export interface ToolAccessCredentialContextPayload {
  status?: string;
  degraded?: boolean;
  degraded_reason?: string | null;
  credential_bindings?: ToolAccessCredentialBindingPayload[];
  credential_requirements?: ToolAccessCredentialRequirementPayload[];
}

export interface BindToolCredentialRequirementRequest {
  tool_id: string;
  consumer_id: string;
  slot: string;
  display_name?: string | null;
  provider?: string | null;
  expected_kind: string;
  credential_binding_id: string;
  requirement_sets?: string[][];
}

export interface ToolAccessActionResultPayload {
  status?: string;
  asset?: Record<string, unknown> | null;
  audit_ref?: string | null;
  validation?: Record<string, unknown>;
  readiness?: Record<string, unknown> | null;
  warnings?: string[];
}

export interface ToolEventConsoleRecord {
  cursor: string;
  event_id: string;
  event_name: string;
  topic: string;
  kind: string;
  source_payload?: Record<string, unknown>;
  created_at?: string;
}

export interface ToolEventStreamSnapshot {
  records?: ToolEventConsoleRecord[];
}

export interface ToolCliOutputStreamHandlers {
  event?: (record: ToolEventConsoleRecord) => void;
  snapshot?: (snapshot: ToolEventStreamSnapshot) => void;
  error?: (event: Event) => void;
}

export function listTools(enabledOnly = false): Promise<ToolApiPayload[]> {
  return requestJson<ToolApiPayload[]>(`/tools${enabledOnly ? "?enabled_only=true" : ""}`);
}

export function listToolRoots(): Promise<ToolRootApiPayload[]> {
  return requestJson<ToolRootApiPayload[]>("/tools/roots");
}

export function listToolSources(params: { kind?: string; status?: string } = {}): Promise<ToolSourceApiPayload[]> {
  const query = new URLSearchParams();
  if (params.kind) query.set("kind", params.kind);
  if (params.status) query.set("status", params.status);
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  return requestJson<ToolSourceApiPayload[]>(`/tools/sources${suffix}`);
}

export function getToolSource(sourceId: string): Promise<ToolSourceApiPayload> {
  return requestJson<ToolSourceApiPayload>(`/tools/sources/${encodeURIComponent(sourceId)}`);
}

export function createToolSource(payload: ToolSourceWriteApiRequest): Promise<ToolSourceApiPayload> {
  return requestJson<ToolSourceApiPayload>("/tools/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateToolSource(sourceId: string, payload: ToolSourceWriteApiRequest): Promise<ToolSourceApiPayload> {
  return requestJson<ToolSourceApiPayload>(`/tools/sources/${encodeURIComponent(sourceId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listToolSourceDiscoveryRuns(
  sourceId: string,
  limit = 20,
): Promise<ToolSourceDiscoveryRunApiPayload[]> {
  return requestJson<ToolSourceDiscoveryRunApiPayload[]>(
    `/tools/sources/${encodeURIComponent(sourceId)}/discovery-runs?limit=${encodeURIComponent(String(limit))}`,
  );
}

export function refreshToolSource(sourceId: string): Promise<ToolSourceSyncApiPayload> {
  return requestJson<ToolSourceSyncApiPayload>(
    `/tools/sources/${encodeURIComponent(sourceId)}/refresh`,
    { method: "POST" },
  );
}

export function disableToolSource(sourceId: string): Promise<ToolSourceApiPayload> {
  return requestJson<ToolSourceApiPayload>(
    `/tools/sources/${encodeURIComponent(sourceId)}/disable`,
    { method: "POST" },
  );
}

export function restoreToolSource(sourceId: string): Promise<ToolSourceApiPayload> {
  return requestJson<ToolSourceApiPayload>(
    `/tools/sources/${encodeURIComponent(sourceId)}/restore`,
    { method: "POST" },
  );
}

export function deleteToolSource(sourceId: string): Promise<ToolSourceApiPayload> {
  return requestJson<ToolSourceApiPayload>(
    `/tools/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  );
}

export function listToolFunctions(params: { sourceId?: string; status?: string } = {}): Promise<ToolFunctionApiPayload[]> {
  const query = new URLSearchParams();
  if (params.sourceId) query.set("source_id", params.sourceId);
  if (params.status) query.set("status", params.status);
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  return requestJson<ToolFunctionApiPayload[]>(`/tools/functions${suffix}`);
}

export function getToolFunction(functionId: string): Promise<ToolFunctionApiPayload> {
  return requestJson<ToolFunctionApiPayload>(`/tools/functions/${encodeURIComponent(functionId)}`);
}

export function listToolProviderBackends(params: { sourceId?: string; capability?: string; status?: string } = {}): Promise<ToolProviderBackendApiPayload[]> {
  const query = new URLSearchParams();
  if (params.sourceId) query.set("source_id", params.sourceId);
  if (params.capability) query.set("capability", params.capability);
  if (params.status) query.set("status", params.status);
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  return requestJson<ToolProviderBackendApiPayload[]>(`/tools/provider-backends${suffix}`);
}

export function enableToolFunction(functionId: string): Promise<ToolFunctionApiPayload> {
  return requestJson<ToolFunctionApiPayload>(
    `/tools/functions/${encodeURIComponent(functionId)}/enable`,
    { method: "POST" },
  );
}

export function disableToolFunction(functionId: string): Promise<ToolFunctionApiPayload> {
  return requestJson<ToolFunctionApiPayload>(
    `/tools/functions/${encodeURIComponent(functionId)}/disable`,
    { method: "POST" },
  );
}

export function updateToolFunctionPolicy(
  functionId: string,
  payload: ToolFunctionPolicyApiRequest,
): Promise<ToolFunctionApiPayload> {
  return requestJson<ToolFunctionApiPayload>(
    `/tools/functions/${encodeURIComponent(functionId)}/policy`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
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

export function openToolCliOutputStream(
  processId: string,
  handlers: ToolCliOutputStreamHandlers,
): () => void {
  const query = new URLSearchParams({
    topic_prefix: "events.named.tool.cli.output_observed",
    event_name: "tool.cli.output_observed",
    payload_key: "process_id",
    payload_value: processId,
    snapshot_limit: "20",
    timeout_seconds: "300",
  });
  const source = new EventSource(buildApiUrl(`/events/stream?${query.toString()}`));
  source.addEventListener("event", (event) => {
    const record = parseEventData<ToolEventConsoleRecord>(event);
    if (record) handlers.event?.(record);
  });
  source.addEventListener("snapshot", (event) => {
    const snapshot = parseEventData<ToolEventStreamSnapshot>(event);
    if (snapshot) handlers.snapshot?.(snapshot);
  });
  source.addEventListener("error", (event) => {
    handlers.error?.(event);
  });
  return () => source.close();
}

function parseEventData<T>(event: MessageEvent): T | null {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    return null;
  }
}

export function pruneExpiredToolWorkers(retentionSeconds = 3600): Promise<PruneExpiredToolWorkersApiPayload> {
  return requestJson<PruneExpiredToolWorkersApiPayload>(
    `/tools/workers/prune-expired?retention_seconds=${encodeURIComponent(String(retentionSeconds))}`,
    { method: "POST" },
  );
}

export function getToolAccessCredentialContext(): Promise<ToolAccessCredentialContextPayload> {
  return requestJson<ToolAccessCredentialContextPayload>("/ui/access");
}

export function bindToolCredentialRequirement(
  payload: BindToolCredentialRequirementRequest,
): Promise<ToolAccessActionResultPayload> {
  return requestJson<ToolAccessActionResultPayload>("/access/actions", {
    method: "POST",
    body: JSON.stringify({
      action_id: `settings_tool_bind_credential_${Date.now()}`,
      resource_kind: "credential_requirement",
      target_id: `consumer:tool:tool:${payload.consumer_id}:${payload.slot}`,
      intent: "bind_credential_requirement",
      changes: {
        consumer_module: "tool",
        consumer_kind: "tool",
        consumer_id: payload.consumer_id,
        slot: payload.slot,
        display_name: payload.display_name,
        provider: payload.provider,
        expected_kind: payload.expected_kind,
        credential_binding_id: payload.credential_binding_id,
        requirement_sets: payload.requirement_sets,
        status: "active",
      },
      reason: `Bind Tool credential slot ${payload.tool_id}/${payload.slot}.`,
      actor: "settings-ui",
      trace_context: {
        page: "settings.tool-catalog",
        endpoint: "/access/actions",
        tool_id: payload.tool_id,
        slot: payload.slot,
      },
    }),
  });
}
