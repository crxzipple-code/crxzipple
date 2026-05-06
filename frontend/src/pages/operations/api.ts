import { operationsModules, operationsOrchestrationPage } from "@/mocks/fixtures/runtime";
import { buildApiUrl, dataMode, requestJson } from "@/shared/api/client";
import type {
  OperationsModuleOverview,
  OperationsAccessReadModel,
  OperationsChannelsReadModel,
  OperationsDaemonReadModel,
  OperationsEventsReadModel,
  OperationsLlmReadModel,
  OperationsLlmInvocationDetail,
  OperationsMemoryReadModel,
  OperationsOrchestrationReadModel,
  OperationsSkillsReadModel,
  OperationsToolReadModel,
  OperationsToolRunDetail,
  OperationsTab,
  UiMetricCard,
  UiModuleRole,
  UiRuntimeAction,
  UiTableSection,
} from "@/shared/runtime/types";

export interface OperationsData {
  overview: OperationsModuleOverview;
  source: "fixture" | "api";
}

export type OperationsRuntimeTone = "neutral" | "info" | "success" | "warning" | "danger";

export type RawRecord = Record<string, unknown>;

export interface OperationsActionAuditPayload {
  operator?: string | null;
  source?: string | null;
  metadata?: RawRecord;
}

export interface OperationsActionPayload {
  reason?: string | null;
  confirmation?: boolean | string | null;
  risk_acknowledged?: boolean;
  risk_ack?: boolean;
  operator?: string | null;
  source?: string | null;
  metadata?: RawRecord;
  audit?: OperationsActionAuditPayload | null;
}

export interface OperationsRuntimeStatusItem {
  id: string;
  label: string;
  value: string;
  status: string;
  tone: OperationsRuntimeTone;
  details?: string | null;
}

export interface OperationsRuntimeStatus {
  updated_at: string;
  checks: OperationsRuntimeStatusItem[];
}

export interface OperationsRuntimeStatusData {
  status: OperationsRuntimeStatus;
  source: "fixture" | "api";
}

export interface OperationsRefreshEvent {
  event_type: "connected" | "snapshot" | "projection_updated" | "timeout" | string;
  event_id?: string;
  module?: string | null;
  modules: string[];
  kinds?: string[];
  query_key?: string;
  updated_at?: string;
  records?: OperationsRefreshEvent[];
}

export interface OperationsStreamHandlers {
  event?: (record: OperationsRefreshEvent) => void;
  snapshot?: (snapshot: OperationsRefreshEvent) => void;
  error?: (event: Event) => void;
}

export interface OrchestrationOperationsData {
  page: OperationsOrchestrationReadModel;
  source: "fixture" | "api";
}

export interface ToolOperationsData {
  page: OperationsToolReadModel;
  source: "fixture" | "api";
}

export interface LlmOperationsData {
  page: OperationsLlmReadModel;
  source: "fixture" | "api";
}

export interface ToolOperationsQueryParams {
  status?: string;
  time_window?: string;
  search?: string;
  tool_id?: string;
  provider?: string;
  mode?: string;
  strategy?: string;
  environment?: string;
  worker_id?: string;
  has_artifact?: string;
  retryable?: string;
  limit?: number;
  offset?: number;
}

export interface LlmOperationsQueryParams {
  status?: string;
  time_window?: string;
  search?: string;
  llm_id?: string;
  provider?: string;
  streaming?: string;
  limit?: number;
  offset?: number;
}

export interface MemoryOperationsQueryParams {
  kind?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface MemoryWriteResultResponse {
  path: string;
  line_start: number;
  line_end: number;
  kind: string;
}

export interface SkillsOperationsQueryParams {
  surface?: string;
  source?: string;
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface ChannelsOperationsQueryParams {
  status?: string;
  channel_type?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface AccessOperationsQueryParams {
  status?: string;
  kind?: string;
  usage_type?: string;
  search?: string;
  include_ready?: boolean;
  include_disabled?: boolean;
  limit?: number;
  offset?: number;
}

export interface DaemonOperationsQueryParams {
  status?: string;
  service_key?: string;
  service_group?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface EventsOperationsQueryParams {
  status?: string;
  topic_prefix?: string;
  search?: string;
  owner?: string;
  limit?: number;
  offset?: number;
}

export interface ToolRunActionResponse {
  id: string;
  tool_id: string;
  status: string;
  cancel_requested_at?: string | null;
}

export interface PruneExpiredToolWorkersResponse {
  pruned_count: number;
  worker_ids: string[];
  cutoff: string;
}

export interface AdvanceEventSubscriptionsRequest extends OperationsActionPayload {
  subscription_id?: string | null;
  source_topic?: string | null;
  status?: string;
  observer_only?: boolean;
  dry_run?: boolean;
}

export interface AdvanceEventSubscriptionsResponse {
  matched_count: number;
  advanced_count: number;
  skipped_count: number;
  dry_run: boolean;
  reason?: string | null;
  items: {
    subscription_id: string;
    source_topic: string;
    previous_cursor: string;
    latest_cursor: string;
    status: string;
    changed: boolean;
  }[];
}

export interface PruneStaleChannelRuntimesRequest extends OperationsActionPayload {
  runtime_id?: string | null;
  channel_type?: string | null;
  stale_after_seconds?: number;
  dry_run?: boolean;
}

export interface PruneStaleChannelRuntimesResponse {
  matched_count: number;
  pruned_count: number;
  skipped_count: number;
  dry_run: boolean;
  reason?: string | null;
  items: {
    runtime_id: string;
    channel_type: string;
    status: string;
    heartbeat_age_seconds: number;
    account_bindings_removed: number;
    connection_bindings_removed: number;
    pruned: boolean;
  }[];
}

export interface ChannelDeadLetterReplayRequest extends OperationsActionPayload {
  runtime_id?: string | null;
  cursor?: string | null;
  event_id?: string | null;
}

export interface ChannelDeadLetterReplayResponse {
  replayed: boolean;
  dead_letter_topic: string;
  dead_letter_cursor: string;
  dead_letter_event_id: string;
  outbound_id: string;
  replay_mode: string;
  callback_status?: string | null;
}

export interface SkillPackageResponse {
  name: string;
  description?: string;
  version?: string | null;
  source?: string;
  root_path?: string;
}

export interface SkillInstallResponse {
  scope: "workspace" | "global" | string;
  target_root: string;
  target_path: string;
  skill: SkillPackageResponse;
}

export interface AccessCheckRequest extends OperationsActionPayload {
  requirements?: string[];
  credential_bindings?: string[];
  workspace_dir?: string | null;
  allow_literal_credentials?: boolean;
}

export interface AccessReadinessResponse {
  target_type: "requirement" | "credential_binding" | string;
  requirement: string;
  provider?: string | null;
  kind?: string | null;
  scopes: string[];
  status: string;
  ready: boolean;
  setup_available: boolean;
  reason: string;
  setup_flow?: AccessSetupFlowResponse | null;
}

export interface AccessCheckResponse {
  ready: boolean;
  checks: AccessReadinessResponse[];
}

export interface AccessSetupFlowResponse {
  kind: string;
  title: string;
  description: string;
  action_label?: string | null;
  env_vars: string[];
  path?: string | null;
  command: string[];
  authorize_url?: string | null;
  callback_url?: string | null;
  verification_url?: string | null;
  user_code?: string | null;
  expires_at?: string | null;
  metadata: RawRecord;
  actions: RawRecord[];
}

export interface AccessInventoryResponse {
  ready: boolean;
  targets: RawRecord[];
  counts: {
    total: number;
    ready: number;
    blocked: number;
  };
}

export type DaemonServiceActionKind = "ensure" | "healthcheck" | "reconcile" | "stop";

export interface OperationsModulePageReadModel {
  module: string;
  title: string;
  subtitle: string;
  health: string;
  updated_at: string;
  auto_refresh: boolean;
  role: UiModuleRole;
  metrics: UiMetricCard[];
  tabs: OperationsTab[];
  active_tab: string;
  actions: UiRuntimeAction[];
  sections: UiTableSection[];
}

export interface OperationsModulePageData {
  page: OperationsModulePageReadModel;
  source: "fixture" | "api";
}

const apiModules = new Set([
  "orchestration",
  "tool",
  "llm",
  "access",
  "channels",
  "memory",
  "skills",
  "events",
  "daemon",
]);

function operationsActionPayload(
  payload: OperationsActionPayload & {
    defaultReason: string;
    dangerous?: boolean;
  },
): OperationsActionPayload {
  const explicitReason = payload.reason?.trim() || null;
  const reason = explicitReason ?? (payload.dangerous ? null : payload.defaultReason);
  const hasRiskAcknowledgement = (
    typeof payload.risk_acknowledged === "boolean"
    || typeof payload.risk_ack === "boolean"
  );
  const metadata = {
    ...(payload.metadata ?? {}),
    action_source: payload.source ?? payload.audit?.source ?? "operations",
  };
  const actionPayload: OperationsActionPayload = {
    reason,
    operator: payload.operator ?? null,
    source: payload.source ?? "operations",
    metadata,
    audit: payload.audit ?? {
      operator: payload.operator ?? null,
      source: payload.source ?? "operations",
      metadata,
    },
  };
  if (payload.confirmation !== undefined) {
    actionPayload.confirmation = payload.confirmation;
  }
  if (hasRiskAcknowledgement) {
    actionPayload.risk_acknowledged = Boolean(payload.risk_acknowledged ?? payload.risk_ack);
  }
  return actionPayload;
}

export function openOperationsStream(handlers: OperationsStreamHandlers): () => void {
  const query = new URLSearchParams({
    snapshot_limit: "0",
    timeout_seconds: "300",
  });
  const source = new EventSource(buildApiUrl(`/operations/stream?${query.toString()}`));

  source.addEventListener("projection_updated", (event) => {
    const record = parseEventData<OperationsRefreshEvent>(event);
    if (record) handlers.event?.(record);
  });
  source.addEventListener("snapshot", (event) => {
    const snapshot = parseEventData<OperationsRefreshEvent>(event);
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

export interface DaemonOperationsData {
  page: OperationsDaemonReadModel;
  source: "fixture" | "api";
}

export interface SkillsOperationsData {
  page: OperationsSkillsReadModel;
  source: "fixture" | "api";
}

export interface AccessOperationsData {
  page: OperationsAccessReadModel;
  source: "fixture" | "api";
}

export interface ChannelsOperationsData {
  page: OperationsChannelsReadModel;
  source: "fixture" | "api";
}

export interface EventsOperationsData {
  page: OperationsEventsReadModel;
  source: "fixture" | "api";
}

export interface MemoryOperationsData {
  page: OperationsMemoryReadModel;
  source: "fixture" | "api";
}

export async function loadOrchestrationOperations(): Promise<OrchestrationOperationsData> {
  if (dataMode !== "api") {
    return {
      page: operationsOrchestrationPage,
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsOrchestrationReadModel>(
      "/operations/orchestration",
    ),
    source: "api",
  };
}

export async function cancelOrchestrationRun(
  runId: string,
  reason?: string | null,
): Promise<RawRecord> {
  return requestJson<RawRecord>(
    `/operations/orchestration/runs/${encodeURIComponent(runId)}/cancel`,
    {
      method: "POST",
      body: JSON.stringify(operationsActionPayload({
        reason,
        defaultReason: "Operations orchestration run cancellation",
      })),
    },
  );
}

export async function resumeOrchestrationRun(
  runId: string,
  reason?: string | null,
): Promise<RawRecord> {
  return requestJson<RawRecord>(
    `/operations/orchestration/runs/${encodeURIComponent(runId)}/resume`,
    {
      method: "POST",
      body: JSON.stringify(operationsActionPayload({
        reason,
        defaultReason: "Operations orchestration run resume",
      })),
    },
  );
}

export async function loadToolOperations(
  params: ToolOperationsQueryParams = {},
): Promise<ToolOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureToolPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsToolReadModel>(toolOperationsPath(params)),
    source: "api",
  };
}

export async function loadLlmOperations(
  params: LlmOperationsQueryParams = {},
): Promise<LlmOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureLlmPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsLlmReadModel>(llmOperationsPath(params)),
    source: "api",
  };
}

export async function loadToolRunDetail(runId: string): Promise<OperationsToolRunDetail | null> {
  if (dataMode !== "api") {
    return fixtureToolPage().tool_run_details.find((item) => item.run_id === runId) ?? null;
  }
  return requestJson<OperationsToolRunDetail>(
    `/operations/tool/runs/${encodeURIComponent(runId)}/detail`,
  );
}

export async function loadLlmInvocationDetail(
  invocationId: string,
): Promise<OperationsLlmInvocationDetail | null> {
  if (dataMode !== "api") {
    return fixtureLlmPage().invocation_details.find((item) => item.invocation_id === invocationId) ?? null;
  }
  return requestJson<OperationsLlmInvocationDetail>(
    `/operations/llm/invocations/${encodeURIComponent(invocationId)}/detail`,
  );
}

function toolOperationsPath(params: ToolOperationsQueryParams): string {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.time_window) search.set("time_window", params.time_window);
  if (params.search) search.set("search", params.search);
  if (params.tool_id) search.set("tool_id", params.tool_id);
  if (params.provider) search.set("provider", params.provider);
  if (params.mode) search.set("mode", params.mode);
  if (params.strategy) search.set("strategy", params.strategy);
  if (params.environment) search.set("environment", params.environment);
  if (params.worker_id) search.set("worker_id", params.worker_id);
  if (params.has_artifact) search.set("has_artifact", params.has_artifact);
  if (params.retryable) search.set("retryable", params.retryable);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/tool${query ? `?${query}` : ""}`;
}

function llmOperationsPath(params: LlmOperationsQueryParams): string {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.time_window) search.set("time_window", params.time_window);
  if (params.search) search.set("search", params.search);
  if (params.llm_id) search.set("llm_id", params.llm_id);
  if (params.provider) search.set("provider", params.provider);
  if (params.streaming) search.set("streaming", params.streaming);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/llm${query ? `?${query}` : ""}`;
}

export async function cancelToolRun(runId: string): Promise<ToolRunActionResponse> {
  return requestJson<ToolRunActionResponse>(
    `/operations/tool/runs/${encodeURIComponent(runId)}/cancel`,
    {
      method: "POST",
      body: JSON.stringify(operationsActionPayload({
        defaultReason: "Operations tool run cancellation",
      })),
    },
  );
}

export async function retryToolRun(runId: string): Promise<ToolRunActionResponse> {
  return requestJson<ToolRunActionResponse>(
    `/operations/tool/runs/${encodeURIComponent(runId)}/retry`,
    {
      method: "POST",
      body: JSON.stringify(operationsActionPayload({
        defaultReason: "Operations tool run retry",
      })),
    },
  );
}

export async function pruneExpiredToolWorkers(
  retentionSeconds = 3600,
): Promise<PruneExpiredToolWorkersResponse> {
  return requestJson<PruneExpiredToolWorkersResponse>(
    "/operations/tool/workers/prune-expired",
    {
      method: "POST",
      body: JSON.stringify({
        retention_seconds: retentionSeconds,
        ...operationsActionPayload({
          defaultReason: "Operations prune expired tool workers",
        }),
      }),
    },
  );
}

export async function advanceEventSubscriptionsToHead(
  payload: AdvanceEventSubscriptionsRequest,
): Promise<AdvanceEventSubscriptionsResponse> {
  return requestJson<AdvanceEventSubscriptionsResponse>(
    "/operations/events/subscriptions/advance-to-head",
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        ...operationsActionPayload({
          ...payload,
          defaultReason: "Operations event subscription cursor advance",
          dangerous: !payload.dry_run,
        }),
      }),
    },
  );
}

export async function advanceEventObserversToHead(
  payload: AdvanceEventSubscriptionsRequest,
): Promise<AdvanceEventSubscriptionsResponse> {
  return requestJson<AdvanceEventSubscriptionsResponse>(
    "/operations/events/observers/advance-to-head",
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        ...operationsActionPayload({
          ...payload,
          defaultReason: "Operations observer cursor advance",
          dangerous: !payload.dry_run,
        }),
      }),
    },
  );
}

export async function pruneStaleChannelRuntimes(
  payload: PruneStaleChannelRuntimesRequest,
): Promise<PruneStaleChannelRuntimesResponse> {
  return requestJson<PruneStaleChannelRuntimesResponse>(
    "/operations/channels/runtimes/prune-stale",
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        ...operationsActionPayload({
          ...payload,
          defaultReason: "Operations stale channel runtime prune",
          dangerous: !payload.dry_run,
        }),
      }),
    },
  );
}

export async function replayChannelDeadLetter(
  channelType: string,
  payload: ChannelDeadLetterReplayRequest,
): Promise<ChannelDeadLetterReplayResponse> {
  return requestJson<ChannelDeadLetterReplayResponse>(
    `/operations/channels/dead-letters/${encodeURIComponent(channelType)}/replay`,
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        ...operationsActionPayload({
          ...payload,
          defaultReason: "Operations channel dead-letter replay",
        }),
      }),
    },
  );
}

export async function validateSkillPackage(path: string): Promise<SkillPackageResponse> {
  return requestJson<SkillPackageResponse>(
    "/operations/skills/validate",
    {
      method: "POST",
      body: JSON.stringify({
        path,
        ...operationsActionPayload({
          defaultReason: "Operations skill package validation",
        }),
      }),
    },
  );
}

export async function installGlobalSkill(sourceDir: string): Promise<SkillInstallResponse> {
  return requestJson<SkillInstallResponse>(
    "/operations/skills/install",
    {
      method: "POST",
      body: JSON.stringify({
        source_dir: sourceDir,
        ...operationsActionPayload({
          defaultReason: "Operations global skill install",
        }),
      }),
    },
  );
}

export async function loadAccessInventory(
  includeReady = true,
  includeDisabled = false,
): Promise<AccessInventoryResponse> {
  const search = new URLSearchParams({
    include_ready: String(includeReady),
    include_disabled: String(includeDisabled),
  });
  return requestJson<AccessInventoryResponse>(`/operations/access/inventory?${search.toString()}`);
}

export async function checkAccess(
  payload: AccessCheckRequest,
): Promise<AccessCheckResponse> {
  return requestJson<AccessCheckResponse>(
    "/operations/access/check",
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        ...operationsActionPayload({
          ...payload,
          defaultReason: "Operations access readiness check",
        }),
      }),
    },
  );
}

export async function getAccessSetup(target: string): Promise<AccessSetupFlowResponse> {
  return requestJson<AccessSetupFlowResponse>(
    `/operations/access/setup?target=${encodeURIComponent(target)}`,
  );
}

export async function runDaemonServiceAction(
  serviceKey: string,
  action: DaemonServiceActionKind,
  reason: string,
  payload: OperationsActionPayload = {},
): Promise<RawRecord[]> {
  return requestJson<RawRecord[]>(
    `/operations/daemon/services/${encodeURIComponent(serviceKey)}/${action}`,
    {
      method: "POST",
      body: JSON.stringify(operationsActionPayload({
        ...payload,
        reason,
        defaultReason: `Operations daemon action ${action} for ${serviceKey}`,
        dangerous: action === "stop",
      })),
    },
  );
}

export async function loadOperationsModulePage(
  moduleId: string,
): Promise<OperationsModulePageData> {
  if (dataMode !== "api") {
    return {
      page: fixtureModulePage(moduleId),
      source: "fixture",
    };
  }
  ensureKnownOperationsModule(moduleId);
  if (moduleId === "orchestration") {
    throw new Error("Use loadOrchestrationOperations for the orchestration operations page.");
  }

  return {
    page: await requestJson<OperationsModulePageReadModel>(
      `/operations/${encodeURIComponent(moduleId)}`,
    ),
    source: "api",
  };
}

export async function loadOperationsOverview(moduleId: string): Promise<OperationsData> {
  if (dataMode !== "api") {
    return {
      overview: fixtureOverview(moduleId),
      source: "fixture",
    };
  }
  ensureKnownOperationsModule(moduleId);

  return {
    overview: await requestJson<OperationsModuleOverview>(
      `/operations/${encodeURIComponent(moduleId)}/overview`,
    ),
    source: "api",
  };
}

export async function loadOperationsRuntimeStatus(): Promise<OperationsRuntimeStatusData> {
  if (dataMode !== "api") {
    return {
      status: {
        updated_at: new Date().toISOString(),
        checks: [
          {
            id: "database",
            label: "Database",
            value: "Fixture",
            status: "fixture",
            tone: "warning",
            details: "Runtime status is unavailable in fixture mode.",
          },
          {
            id: "events",
            label: "Events",
            value: "Fixture",
            status: "fixture",
            tone: "warning",
            details: "Runtime status is unavailable in fixture mode.",
          },
          {
            id: "migration",
            label: "Migration",
            value: "-",
            status: "fixture",
            tone: "warning",
            details: "Runtime status is unavailable in fixture mode.",
          },
        ],
      },
      source: "fixture",
    };
  }

  return {
    status: await requestJson<OperationsRuntimeStatus>("/operations/runtime"),
    source: "api",
  };
}

export async function loadDaemonOperations(
  params: DaemonOperationsQueryParams = {},
): Promise<DaemonOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureDaemonPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsDaemonReadModel>(daemonOperationsPath(params)),
    source: "api",
  };
}

function daemonOperationsPath(params: DaemonOperationsQueryParams): string {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.service_key) search.set("service_key", params.service_key);
  if (params.service_group) search.set("service_group", params.service_group);
  if (params.search) search.set("search", params.search);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/daemon${query ? `?${query}` : ""}`;
}

export async function loadSkillsOperations(
  params: SkillsOperationsQueryParams = {},
): Promise<SkillsOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureSkillsPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsSkillsReadModel>(skillsOperationsPath(params)),
    source: "api",
  };
}

function skillsOperationsPath(params: SkillsOperationsQueryParams): string {
  const search = new URLSearchParams();
  if (params.surface) search.set("surface", params.surface);
  if (params.source) search.set("source", params.source);
  if (params.status) search.set("status", params.status);
  if (params.search) search.set("search", params.search);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/skills${query ? `?${query}` : ""}`;
}

export async function loadAccessOperations(
  params: AccessOperationsQueryParams = {},
): Promise<AccessOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureAccessPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsAccessReadModel>(accessOperationsPath(params)),
    source: "api",
  };
}

function accessOperationsPath(params: AccessOperationsQueryParams): string {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.kind) search.set("kind", params.kind);
  if (params.usage_type) search.set("usage_type", params.usage_type);
  if (params.search) search.set("search", params.search);
  if (typeof params.include_ready === "boolean") search.set("include_ready", String(params.include_ready));
  if (typeof params.include_disabled === "boolean") search.set("include_disabled", String(params.include_disabled));
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/access${query ? `?${query}` : ""}`;
}

export async function loadChannelsOperations(
  params: ChannelsOperationsQueryParams = {},
): Promise<ChannelsOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureChannelsPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsChannelsReadModel>(channelsOperationsPath(params)),
    source: "api",
  };
}

function channelsOperationsPath(params: ChannelsOperationsQueryParams): string {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.channel_type) search.set("channel_type", params.channel_type);
  if (params.search) search.set("search", params.search);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/channels${query ? `?${query}` : ""}`;
}

export async function loadEventsOperations(
  params: EventsOperationsQueryParams = {},
): Promise<EventsOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureEventsPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsEventsReadModel>(eventsOperationsPath(params)),
    source: "api",
  };
}

function eventsOperationsPath(params: EventsOperationsQueryParams): string {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.topic_prefix) search.set("topic_prefix", params.topic_prefix);
  if (params.search) search.set("search", params.search);
  if (params.owner) search.set("owner", params.owner);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/events${query ? `?${query}` : ""}`;
}

export async function loadMemoryOperations(
  agentId?: string,
  params: MemoryOperationsQueryParams = {},
): Promise<MemoryOperationsData> {
  if (dataMode !== "api") {
    return {
      page: fixtureMemoryPage(),
      source: "fixture",
    };
  }

  return {
    page: await requestJson<OperationsMemoryReadModel>(
      memoryOperationsPath(agentId, params),
    ),
    source: "api",
  };
}

export async function writeLongTermMemory(
  agentId: string,
  content: string,
): Promise<MemoryWriteResultResponse> {
  return requestJson<MemoryWriteResultResponse>(
    "/operations/memory/long-term",
    {
      method: "POST",
      body: JSON.stringify({
        agent_id: agentId,
        content,
        ...operationsActionPayload({
          defaultReason: "Operations long-term memory write",
        }),
      }),
    },
  );
}

function memoryOperationsPath(
  agentId?: string,
  params: MemoryOperationsQueryParams = {},
): string {
  const search = new URLSearchParams();
  if (agentId) search.set("agent_id", agentId);
  if (params.kind) search.set("kind", params.kind);
  if (params.search) search.set("search", params.search);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  return `/operations/memory${query ? `?${query}` : ""}`;
}

function fixtureOverview(moduleId: string): OperationsModuleOverview {
  const overview = operationsModules.find((module) => module.module === moduleId);
  if (overview) return overview;
  return {
    module: moduleId,
    title: titleCase(moduleId),
    subtitle: "Fixture operations overview.",
    health: "warning",
    updated_at: new Date().toISOString(),
    metrics: [],
    queue: [],
    lane_locks: [],
    executor: [],
    actions: [],
  };
}

function ensureKnownOperationsModule(moduleId: string): void {
  if (!apiModules.has(moduleId)) {
    throw new Error(`Operations module '${moduleId}' is not registered.`);
  }
}

function titleCase(value: string): string {
  return value
    .split(/[-_]/g)
    .filter(Boolean)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ") || "Operations";
}

function fixtureModulePage(moduleId: string): OperationsModulePageReadModel {
  const overview = fixtureOverview(moduleId);
  return {
    ...overview,
    auto_refresh: true,
    role: {
      label: `${overview.title} operator`,
      can_operate: true,
      scope: overview.module,
    },
    tabs: [],
    active_tab: "overview",
    actions: overview.actions.map((action) => ({
      ...action,
      owner: overview.module,
      allowed: true,
      requires_confirmation: action.risk !== "normal",
      reason_required: action.risk === "dangerous",
      method: null,
      endpoint: null,
    })),
    sections: [],
  };
}

function fixtureToolPage(): OperationsToolReadModel {
  const overview = fixtureOverview("tool");
  const base = fixtureModulePage("tool");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  return {
    ...base,
    module: "tool",
    health: base.health as OperationsToolReadModel["health"],
    active_tool_runs: emptyTable("active_tool_runs", "Active Tool Runs"),
    tool_queue_runs: emptyTable("tool_queue_runs", "Queued Tool Runs"),
    tool_waiting_io: emptyTable("tool_waiting_io", "Waiting IO"),
    tool_runs: emptyTable("tool_runs", "Recent Tool Runs"),
    tool_types: {
      id: "tool_types",
      title: "Tool Types",
      kind: "donut",
      total: Number(overview.metrics.find((metric) => metric.id === "catalog")?.value ?? 0),
      segments: [],
    },
    auth_missing: emptyTable("auth_missing", "Runtime Risk / Access"),
    worker_pool: {
      id: "worker_pool",
      title: "Worker Pool",
      kind: "donut",
      total: 0,
      segments: [],
    },
    workers: emptyTable("workers", "Workers"),
    tool_queue: emptyTable("tool_queue", "Tool Queue"),
    capability_limits: emptyTable("capability_limits", "Capability Concurrency"),
    provider_limits: emptyTable("provider_limits", "Provider Limits"),
    provider_history: emptyTable("provider_history", "Provider History"),
    run_blockers: emptyTable("run_blockers", "Run Scheduling Diagnostics"),
    inline_risk: {
      id: "inline_risk",
      title: "Inline Risk",
      items: [],
    },
    recent_artifacts: emptyTable("recent_artifacts", "Recent Artifacts"),
    tool_lifecycle_events: emptyTable("tool_lifecycle_events", "Tool Lifecycle Events"),
    strategies: emptyTable("strategies", "Execution Strategies"),
    worker_details: [],
    tool_run_details: [],
  };
}

function fixtureLlmPage(): OperationsLlmReadModel {
  const overview = fixtureOverview("llm");
  const base = fixtureModulePage("llm");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  const emptyChart = (id: string, title: string) => ({
    id,
    title,
    kind: "donut" as const,
    total: 0,
    segments: [],
  });
  const emptyKeyValue = (id: string, title: string) => ({
    id,
    title,
    items: [],
  });
  return {
    ...base,
    module: "llm",
    health: base.health as OperationsLlmReadModel["health"],
    metrics: overview.metrics,
    provider_access_health: emptyTable("provider_access_health", "Provider Access & Health"),
    provider_auth_blocked: emptyTable("provider_auth_blocked", "Provider Auth / Access Blocked"),
    model_resolver: emptyChart("model_resolver", "Model Resolver"),
    rate_limiter: emptyKeyValue("rate_limiter", "LLM Rate Limiter"),
    limiter_queue: emptyTable("limiter_queue", "Limiter Queue"),
    streaming_requests: emptyTable("streaming_requests", "Streaming Requests"),
    recent_invocations: emptyTable("recent_invocations", "Recent Invocations"),
    failed_invocations: emptyTable("failed_invocations", "Failed Invocations"),
    latency: emptyChart("latency", "Latency"),
    token_usage: emptyChart("token_usage", "Token Usage"),
    invocation_rate: emptyChart("invocation_rate", "Invocation Rate"),
    stream_health: emptyKeyValue("stream_health", "Stream Health"),
    execution_blocking_risk: emptyKeyValue("execution_blocking_risk", "Execution Blocking Risk"),
    fallback_problems: emptyTable("fallback_problems", "Fallback / Resolver Problems"),
    context_pressure: emptyChart("context_pressure", "Context Window Pressure"),
    model_availability: emptyTable("model_availability", "Model Availability"),
    error_summary: emptyTable("error_summary", "Error Summary"),
    llm_lifecycle_events: emptyTable("llm_lifecycle_events", "LLM Lifecycle Events"),
    invocation_details: [],
  };
}

function fixtureAccessPage(): OperationsAccessReadModel {
  const base = fixtureModulePage("access");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  const emptyChart = (id: string, title: string, kind: "bar" | "donut" = "donut") => ({
    id,
    title,
    kind,
    total: 0,
    segments: [],
  });
  return {
    ...base,
    module: "access",
    health: base.health as OperationsAccessReadModel["health"],
    access_targets: emptyTable("access_targets", "Access Targets"),
    missing_access: emptyTable("missing_access", "Missing Access"),
    credential_health: emptyChart("credential_health", "Credential Health"),
    provider_auth_blocked: emptyTable("provider_auth_blocked", "Provider Auth / Access Blocked"),
    credentials_by_kind: emptyChart("credentials_by_kind", "Credentials by Kind"),
    expiring_soon: emptyTable("expiring_soon", "Expiring Soon"),
    auth_success_rate: emptyChart("auth_success_rate", "Access Readiness Share"),
    authentication_status: emptyTable("authentication_status", "Authentication Status"),
    access_usage: emptyTable("access_usage", "Access Usage"),
    recent_access_events: emptyTable("recent_access_events", "Recent Access Events"),
    fallback_problems: emptyTable("fallback_problems", "Fallback / Resolver Problems"),
    setup_flows: emptyTable("setup_flows", "Setup Flows"),
    target_details: [],
  };
}

function fixtureMemoryPage(): OperationsMemoryReadModel {
  const base = fixtureModulePage("memory");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  const emptyChart = (id: string, title: string, kind: "bar" | "donut" = "donut") => ({
    id,
    title,
    kind,
    total: 0,
    segments: [],
  });
  return {
    ...base,
    module: "memory",
    health: base.health as OperationsMemoryReadModel["health"],
    memory_stores: emptyTable("memory_stores", "Memory Stores"),
    context_resolution: emptyTable("context_resolution", "Context Resolution"),
    index_health: emptyChart("index_health", "Index Health"),
    index_jobs: emptyTable("index_jobs", "Index Jobs"),
    index_sync_activity: emptyTable("index_sync_activity", "Index Sync Activity"),
    retrieval_performance: emptyChart("retrieval_performance", "Retrieval Backend Mix"),
    retrieval_trace: emptyTable("retrieval_trace", "Retrieval Trace"),
    write_flush: emptyTable("write_flush", "Write / Flush"),
    memory_usage: emptyTable("memory_usage", "Memory Usage"),
    recent_retrieval_logs: emptyTable("recent_retrieval_logs", "Recent Retrieval Logs"),
    source_scan_status: emptyTable("source_scan_status", "Source Scan Status"),
    source_files: emptyTable("source_files", "Source Files"),
    file_details: [],
  };
}

function fixtureSkillsPage(): OperationsSkillsReadModel {
  const base = fixtureModulePage("skills");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  const emptyChart = (id: string, title: string, kind: "bar" | "donut" = "donut") => ({
    id,
    title,
    kind,
    total: 0,
    segments: [],
  });
  return {
    ...base,
    module: "skills",
    health: base.health as OperationsSkillsReadModel["health"],
    recently_resolved_skills: emptyTable("recently_resolved_skills", "Installed Skills"),
    resolution_outcomes: emptyChart("resolution_outcomes", "Skill Readiness"),
    top_used_skills: emptyTable("top_used_skills", "Requirement Footprint"),
    missing_capabilities: emptyTable("missing_capabilities", "Missing Capabilities"),
    access_requirements: emptyTable("access_requirements", "Access Requirements"),
    capability_requirements: emptyTable("capability_requirements", "Capability Requirements"),
    resolution_logs: emptyTable("resolution_logs", "Resolution Logs"),
    resolver_detail: emptyTable("resolver_detail", "Resolver Detail"),
    import_normalize: [],
    skill_package_sources: emptyChart("skill_package_sources", "Skill Package Sources"),
    conflicts_overrides: emptyTable("conflicts_overrides", "Conflicts / Overrides"),
    profile_usage: emptyTable("profile_usage", "Profile Usage"),
    skill_details: [],
  };
}

function fixtureEventsPage(): OperationsEventsReadModel {
  const base = fixtureModulePage("events");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  const emptyChart = (id: string, title: string, kind: "bar" | "donut" = "bar") => ({
    id,
    title,
    kind,
    total: 0,
    segments: [],
  });
  const emptyKeyValue = (id: string, title: string) => ({
    id,
    title,
    items: [],
  });
  return {
    ...base,
    module: "events",
    health: base.health as OperationsEventsReadModel["health"],
    events_over_time: emptyChart("events_over_time", "Events by Kind"),
    events_by_surface: emptyChart("events_by_surface", "Events by Surface", "donut"),
    owners_by_volume: emptyTable("owners_by_volume", "Owners by Volume"),
    contract_compatibility: emptyKeyValue("contract_compatibility", "Contract Compatibility"),
    recent_events: emptyTable("recent_events", "Recent Events"),
    consumer_health: emptyTable("consumer_health", "Consumer Health"),
    observer_health: emptyTable("observer_health", "Observer Health"),
    observer_lag: emptyTable("observer_lag", "Observer Lag"),
    topics: emptyTable("topics", "Topics"),
    subscriptions: emptyTable("subscriptions", "Subscriptions"),
    observer_coverage: emptyTable("observer_coverage", "Observer Coverage"),
    dead_letters: emptyTable("dead_letters", "Dead Letters"),
    contracts: emptyTable("contracts", "Contracts"),
    routes: emptyTable("routes", "Routes"),
    event_details: [],
  };
}

function fixtureChannelsPage(): OperationsChannelsReadModel {
  const base = fixtureModulePage("channels");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  const emptyChart = (id: string, title: string, kind: "bar" | "donut" = "bar") => ({
    id,
    title,
    kind,
    total: 0,
    segments: [],
  });
  return {
    ...base,
    module: "channels",
    health: base.health as OperationsChannelsReadModel["health"],
    channel_status: emptyTable("channel_status", "Channel Runtimes"),
    message_flow: emptyChart("message_flow", "Message Flow", "donut"),
    delivery_trend: emptyChart("delivery_trend", "Runtime / Delivery Status"),
    top_channels: emptyChart("top_channels", "Top Channels"),
    dead_letter_queue: emptyTable("dead_letter_queue", "Dead Letter Queue"),
    recent_messages: emptyTable("recent_messages", "Recent Messages"),
    interactions: emptyTable("interactions", "Interactions"),
    failures_by_category: emptyChart("failures_by_category", "Failures by Category"),
    channel_bindings: emptyTable("channel_bindings", "Account Bindings"),
    connection_bindings: emptyTable("connection_bindings", "Connection Bindings"),
    channel_profiles: emptyTable("channel_profiles", "Channel Profiles"),
    channel_events: emptyTable("channel_events", "Channel Events"),
    contracts: emptyTable("contracts", "Contracts"),
    runtime_details: [],
    record_details: [],
    interaction_details: [],
  };
}

function fixtureDaemonPage(): OperationsDaemonReadModel {
  const base = fixtureModulePage("daemon");
  const emptyTable = (id: string, title: string) => ({
    id,
    title,
    columns: [],
    rows: [],
    total: 0,
    empty_state: "No records.",
  });
  const emptyChart = (id: string, title: string, kind: "bar" | "donut" = "bar") => ({
    id,
    title,
    kind,
    total: 0,
    segments: [],
  });
  const emptyKeyValue = (id: string, title: string) => ({
    id,
    title,
    items: [],
  });
  return {
    ...base,
    module: "daemon",
    health: base.health as OperationsDaemonReadModel["health"],
    service_sets: emptyTable("service_sets", "Service Sets"),
    services: emptyTable("services", "Services"),
    instances: emptyTable("instances", "Instances"),
    leases: emptyTable("leases", "Leases"),
    processes: emptyTable("processes", "Process Sessions"),
    process_health: emptyChart("process_health", "Process Health", "donut"),
    restart_summary: emptyChart("restart_summary", "State Changes / Drift"),
    lease_health: emptyChart("lease_health", "Lease Health", "donut"),
    dependency_health: emptyTable("dependency_health", "Dependency Health"),
    drain_overview: emptyKeyValue("drain_overview", "Lease / Drain Indicators"),
    daemon_events: emptyTable("daemon_events", "Daemon Events"),
    quick_actions: [],
    links_to_operations: [],
    instance_details: [],
    lease_details: [],
    process_details: [],
  };
}
