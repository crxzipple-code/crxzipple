import {
  steps as fixtureSteps,
  threads as fixtureThreadsSource,
  workbenchRun as fixtureRun,
} from "@/mocks/fixtures/runtime";
import { ApiClientError, buildApiUrl, dataMode, requestJson } from "@/shared/api/client";
import type {
  RuntimeLlmRequestPreview,
} from "@/shared/runtime/runtimeRequestPreview";
import type {
  TurnStepView,
  WorkbenchLinkedEntityDetail,
  WorkbenchHomeReadModel,
  WorkbenchRunView,
} from "@/shared/runtime/types";

export interface WorkbenchData {
  home: WorkbenchHomeReadModel;
  run: WorkbenchRunView | null;
  steps: TurnStepView[];
  source: "fixture" | "api";
}

export interface EventConsoleRecord {
  cursor: string;
  event_id: string;
  event_name: string;
  topic: string;
  kind: string;
  source_event_name?: string | null;
  source_event_owner?: string | null;
  source_topic?: string | null;
  source_payload?: Record<string, unknown>;
  created_at?: string;
}

export interface EventStreamSnapshot {
  records?: EventConsoleRecord[];
}

export interface EventStreamOptions {
  topicPrefix: string;
  snapshotLimit?: number;
  timeoutSeconds?: number;
}

export interface EventStreamHandlers {
  event?: (record: EventConsoleRecord) => void;
  snapshot?: (snapshot: EventStreamSnapshot) => void;
  error?: (event: Event) => void;
}

export interface LoadWorkbenchOptions {
  runId?: string | null;
  sessionKey?: string | null;
  activeTurnId?: string | null;
}

export interface CreateTurnPayload {
  content: string | WorkbenchContentBlock[];
  agent_id?: string;
  llm_id?: string;
  session_key?: string;
  new_session?: boolean;
  channel?: string;
  chat_type?: "direct" | "channel" | "group" | string;
  peer_id?: string;
  conversation_id?: string;
  thread_id?: string;
  account_id?: string;
  direct_scope?: "main" | "per_peer" | "per_channel_peer" | "per_account_channel_peer" | string;
  source?: string;
  queue_policy?: "fifo" | "jump_queue" | string;
  priority?: number;
  max_steps?: number;
}

export type WorkbenchContentBlock =
  | {
    type: "text";
    text: string;
  }
  | {
    type: "image_ref";
    artifact_id: string;
    mime_type: string;
    name?: string;
    width?: number | null;
    height?: number | null;
    preview_url?: string;
    original_url?: string;
  }
  | {
    type: "file_ref";
    artifact_id: string;
    mime_type: string;
    name?: string;
    download_url?: string;
  };

export interface WorkbenchToolSummary {
  id: string;
  name: string;
  description: string;
  kind: string;
  tags: string[];
  required_effect_ids: string[];
  execution_policy: {
    timeout_seconds: number;
    requires_confirmation: boolean;
    mutates_state: boolean;
  };
  enabled: boolean;
}

export interface WorkbenchArtifactUpload {
  id: string;
  kind: string;
  mime_type: string;
  name: string | null;
  size_bytes: number;
  width: number | null;
  height: number | null;
  preview_url: string;
  original_url: string;
  download_url: string;
  created_at: string;
}

export interface WorkbenchAgentProfile {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  llm_routing_policy: {
    default_llm_id: string;
    fallback_llm_ids: string[];
    image_llm_id: string | null;
    document_llm_id: string | null;
  };
  memory?: {
    enabled?: boolean;
    scope_ref?: string | null;
    access?: string;
  };
}

export interface WorkbenchLlmProfile {
  id: string;
  provider: string;
  api_family: string;
  model_name: string;
  model_family: string;
  capabilities: string[];
  enabled: boolean;
}

export interface WorkbenchContextEstimate {
  text_chars: number;
  text_tokens: number;
  tool_schema_tokens: number;
  image_count: number;
  file_count: number;
  file_tokens: number;
  provider_attachment_count: number;
}

export interface WorkbenchContextWorkspace {
  id: string;
  session_key: string;
  agent_id: string;
  status: string;
  active_revision: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WorkbenchContextNode {
  id: string;
  workspace_id: string;
  parent_id: string | null;
  owner: string;
  kind: string;
  title: string;
  summary: string;
  state: {
    collapsed: boolean;
    loaded: boolean;
    pinned: boolean;
    snapshot_visible: boolean;
    schema_enabled: boolean;
    opened: boolean;
    consumed: boolean;
    archived: boolean;
  };
  actions: string[];
  owner_ref: Record<string, unknown>;
  estimate: WorkbenchContextEstimate;
  revision: string | null;
  freshness: string;
  display_order: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WorkbenchContextTree {
  workspace: WorkbenchContextWorkspace;
  nodes: WorkbenchContextNode[];
  estimate: WorkbenchContextEstimate;
}

export interface WorkbenchContextSnapshot {
  id: string;
  workspace_id: string;
  session_key: string;
  run_id: string;
  tree_revision: number;
  debug_body?: string;
  provider_attachments: Record<string, unknown>;
  estimate: WorkbenchContextEstimate;
  included_node_ids: string[];
  mirrored_node_ids: string[];
  included_refs: Array<Record<string, unknown>>;
  collapsed_refs: Array<Record<string, unknown>>;
  protocol_required_refs: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TurnCommandResponse {
  run: {
    id: string;
    status: string;
    stage: string;
    session_key: string | null;
    agent_id: string | null;
    created_at: string;
    updated_at: string;
  };
  output_text: string | null;
}

export type ApprovalDecision = "allow_once" | "allow_for_session" | "always_for_agent" | "deny";

export async function loadWorkbenchData(options: LoadWorkbenchOptions = {}): Promise<WorkbenchData> {
  const runId = options.runId ?? null;
  const sessionKey = options.sessionKey ?? null;

  if (dataMode !== "api") {
    return {
      home: fixtureHome(),
      run: fixtureRun,
      steps: fixtureSteps,
      source: "fixture",
    };
  }

  const home = await loadWorkbenchHome({ runId, sessionKey });
  const selectedRunId = runId || home.active_run_id || home.threads.find((thread) => thread.run_id)?.run_id || null;
  if (!selectedRunId) {
    return {
      home,
      run: null,
      steps: [],
      source: "api",
    };
  }

  const run = await requestJson<WorkbenchRunView>(
    `/ui/workbench/runs/${encodeURIComponent(selectedRunId)}?include_timeline=false`,
  );
  const requestedTurnId = options.activeTurnId?.trim() || null;
  const selectedTurnId = (
    requestedTurnId && run.turns.some((turn) => turn.turn_id === requestedTurnId)
      ? requestedTurnId
      : run.current_turn_id
  );
  const steps = await loadWorkbenchRunSteps(selectedRunId, selectedTurnId);
  return {
    home,
    run,
    steps,
    source: "api",
  };
}

export function loadWorkbenchRunSteps(
  runId: string,
  turnId?: string | null,
): Promise<TurnStepView[]> {
  const query = new URLSearchParams();
  if (turnId) query.set("turn_id", turnId);
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  return requestJson<TurnStepView[]>(
    `/ui/workbench/runs/${encodeURIComponent(runId)}/steps${suffix}`,
  );
}

export function loadWorkbenchHome(options: LoadWorkbenchOptions = {}): Promise<WorkbenchHomeReadModel> {
  const query = new URLSearchParams();
  if (options.runId) query.set("run_id", options.runId);
  if (options.sessionKey) query.set("session_key", options.sessionKey);
  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  return requestJson<WorkbenchHomeReadModel>(`/ui/workbench/home${suffix}`);
}

export function loadWorkbenchLinkedEntityDetail(
  entityType: string,
  entityId: string,
): Promise<WorkbenchLinkedEntityDetail> {
  return requestJson<WorkbenchLinkedEntityDetail>(
    `/ui/workbench/linked-entities/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
  );
}

export function createWorkbenchTurn(payload: CreateTurnPayload): Promise<TurnCommandResponse> {
  return requestJson<TurnCommandResponse>("/ui/workbench/turns", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function cancelWorkbenchTurn(runId: string, reason: string): Promise<TurnCommandResponse> {
  return requestJson<TurnCommandResponse>(`/ui/workbench/turns/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function resolveWorkbenchApproval(
  runId: string,
  requestId: string,
  decision: ApprovalDecision,
): Promise<TurnCommandResponse> {
  return requestJson<TurnCommandResponse>(
    `/ui/workbench/turns/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(requestId)}`,
    {
      method: "POST",
      body: JSON.stringify({ decision }),
    },
  );
}

export function listWorkbenchTools(): Promise<WorkbenchToolSummary[]> {
  return requestJson<WorkbenchToolSummary[]>("/ui/workbench/tools?enabled_only=true");
}

export function listWorkbenchAgents(): Promise<WorkbenchAgentProfile[]> {
  return requestJson<WorkbenchAgentProfile[]>("/ui/workbench/agents");
}

export function listWorkbenchModels(): Promise<WorkbenchLlmProfile[]> {
  return requestJson<WorkbenchLlmProfile[]>("/ui/workbench/models");
}

export async function loadWorkbenchContextTree(sessionKey: string): Promise<WorkbenchContextTree | null> {
  try {
    return await requestJson<WorkbenchContextTree>(
      `/ui/workbench/context-tree/by-session/${encodeURIComponent(sessionKey)}`,
    );
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export async function loadWorkbenchContextSnapshot(
  runId: string,
  options: { includeDebugBody?: boolean } = {},
): Promise<WorkbenchContextSnapshot | null> {
  try {
    const query = options.includeDebugBody ? "?include_debug_body=true" : "";
    const payload = await requestJson<{ snapshot: WorkbenchContextSnapshot }>(
      `/ui/workbench/context-snapshots/runs/${encodeURIComponent(runId)}${query}`,
    );
    return payload.snapshot;
  } catch {
    return null;
  }
}

export async function loadWorkbenchContextSnapshotById(
  snapshotId: string,
  options: { includeDebugBody?: boolean } = {},
): Promise<WorkbenchContextSnapshot | null> {
  try {
    const query = options.includeDebugBody ? "?include_debug_body=true" : "";
    const payload = await requestJson<{ snapshot: WorkbenchContextSnapshot }>(
      `/ui/workbench/context-snapshots/${encodeURIComponent(snapshotId)}${query}`,
    );
    return payload.snapshot;
  } catch {
    return null;
  }
}

export async function loadWorkbenchRuntimeRequestPreview(runId: string): Promise<RuntimeLlmRequestPreview | null> {
  try {
    return await requestJson<RuntimeLlmRequestPreview>(
      `/ui/workbench/runs/${encodeURIComponent(runId)}/llm-request-preview`,
    );
  } catch {
    return null;
  }
}

export async function loadWorkbenchInvocationRuntimeRequestPreview(
  invocationId: string,
  runId: string,
): Promise<RuntimeLlmRequestPreview | null> {
  try {
    const query = new URLSearchParams({ run_id: runId });
    return await requestJson<RuntimeLlmRequestPreview>(
      `/ui/workbench/llm-invocations/${encodeURIComponent(invocationId)}/llm-request-preview?${query.toString()}`,
    );
  } catch {
    return null;
  }
}

export function applyWorkbenchContextAction(
  sessionKey: string,
  nodeId: string,
  action: string,
  runId: string | null,
): Promise<{ workspace: WorkbenchContextWorkspace; node: WorkbenchContextNode; action: string; operation_id: string }> {
  return requestJson(
    `/ui/workbench/context-tree/by-session/${encodeURIComponent(sessionKey)}/nodes/${encodeURIComponent(nodeId)}/actions/${encodeURIComponent(action)}`,
    {
      method: "POST",
      body: JSON.stringify({
        actor_kind: "user",
        actor_id: "workbench",
        run_id: runId,
        payload: { surface: "workbench" },
      }),
    },
  );
}

export function openEventStream(
  options: EventStreamOptions,
  handlers: EventStreamHandlers,
): () => void {
  const query = new URLSearchParams({
    topic_prefix: options.topicPrefix,
    snapshot_limit: String(options.snapshotLimit ?? 0),
    timeout_seconds: String(options.timeoutSeconds ?? 300),
  });
  const source = new EventSource(buildApiUrl(`/events/stream?${query.toString()}`));

  source.addEventListener("event", (event) => {
    const record = parseEventData<EventConsoleRecord>(event);
    if (record) handlers.event?.(record);
  });
  source.addEventListener("snapshot", (event) => {
    const snapshot = parseEventData<EventStreamSnapshot>(event);
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

export async function uploadWorkbenchArtifact(file: File): Promise<WorkbenchArtifactUpload> {
  const query = new URLSearchParams({
    name: file.name,
    mime_type: file.type || "application/octet-stream",
  });
  const response = await fetch(buildApiUrl(`/artifacts?${query.toString()}`), {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-Artifact-Name": file.name,
    },
    body: file,
  });
  if (!response.ok) {
    throw new Error(`Artifact upload failed with status ${response.status}`);
  }
  return (await response.json()) as WorkbenchArtifactUpload;
}

function fixtureHome(): WorkbenchHomeReadModel {
  const threads = fixtureThreads();
  return {
    connection: {
      status: "connected",
      label: "Connected",
      updated_at: fixtureRun.started_at,
      details: "Fixture data",
    },
    filters: [
      { id: "all", label: "All", count: threads.length },
      { id: "running", label: "Running", count: threads.filter((thread) => thread.status === "running" || thread.status === "waiting").length },
      { id: "completed", label: "Completed", count: threads.filter((thread) => thread.status === "completed").length },
      { id: "failed", label: "Failed", count: threads.filter((thread) => thread.status === "failed").length },
    ],
    threads,
    active_thread_id: fixtureRun.session_key,
    active_run_id: fixtureRun.run_id,
    actions: [],
  };
}

function fixtureThreads(): WorkbenchHomeReadModel["threads"] {
  return fixtureThreadsSource.map((thread) => ({
    id: thread.id,
    run_id: thread.id === fixtureRun.session_key ? fixtureRun.run_id : undefined,
    session_key: thread.id,
    title: thread.title,
    agent: thread.agent,
    status: thread.status,
    current_activity: thread.last_action,
    updated_at: thread.updated_at,
    starred: thread.id === "ses_market",
  }));
}
