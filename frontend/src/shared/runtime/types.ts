import type {
  UiKeyValueSection,
  UiLinkedEntity,
  UiRuntimeAction,
} from "./contracts";

export * from "./contracts";

export type RuntimeStatus =
  | "accepted"
  | "queued"
  | "running"
  | "waiting"
  | "success"
  | "failed"
  | "cancelled"
  | "completed"
  | "unknown";

export type HealthStatus = "healthy" | "warning" | "error" | "unknown";

export interface TraceContext {
  trace_id: string;
  correlation_id?: string;
  source_event_id?: string;
  source_owner?: string;
  source_surface_id?: string;
  source_event_name?: string;
  observed_event_id?: string;
  observed_event_name?: string;
  session_key?: string;
  session_id?: string;
  turn_id?: string;
  run_id?: string;
  step_id?: string;
  execution_item_id?: string;
  tool_run_id?: string;
  tool_call_id?: string;
  llm_invocation_id?: string;
  llm_response_item_id?: string;
  request_render_snapshot_id?: string;
  session_item_id?: string;
  continuation_decision_id?: string;
  artifact_id?: string;
  approval_request_id?: string;
}

export interface ConsoleSection<T> {
  id: string;
  owner: string;
  status: "ready" | "loading" | "degraded" | "error" | "unauthorized";
  updated_at: string | null;
  data: T | null;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
    trace_id?: string;
  };
}

export interface ThreadSummary {
  id: string;
  title: string;
  agent: string;
  status: RuntimeStatus;
  last_action: string;
  updated_at: string;
}

export interface TurnSummary {
  turn_id: string;
  ordinal: number;
  status: RuntimeStatus;
  duration_ms: number;
}

export interface ArtifactPreview {
  artifact_id: string;
  name: string;
  kind: "image" | "json" | "file" | "markdown" | string;
  size_bytes: number | null;
  mime_type?: string | null;
  width?: number | null;
  height?: number | null;
  preview_url?: string;
  download_url?: string;
  thumbnail_url?: string;
  metadata?: Record<string, unknown>;
}

export interface TurnStepView {
  step_id: string;
  turn_id: string;
  run_id: string;
  type:
    | "user_input"
    | "agent_progress"
    | "agent_thinking"
    | "llm"
    | "continuation_decision"
    | "tool_call"
    | "tool_result"
    | "approval_required"
    | "missing_access"
    | "error"
    | "final_response";
  status: RuntimeStatus;
  title: string;
  summary: string;
  markdown?: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  artifacts: ArtifactPreview[];
  badges: Array<{ label: string; tone: "neutral" | "info" | "success" | "warning" | "danger" }>;
  linked_entities?: UiLinkedEntity[];
  actions?: UiRuntimeAction[];
  approval?: ApprovalRequestDetail | null;
  details_available: boolean;
  trace: TraceContext;
}

export interface ApprovalRequestDetail {
  request_id: string;
  effect_id: string;
  label: string;
  reason: string;
  tool_name?: string | null;
  tool_ids: string[];
  tool_arguments: Record<string, string | number | boolean | null>;
  execution_mode?: string | null;
  execution_strategy?: string | null;
  execution_environment?: string | null;
  draft_id?: string | null;
}

export interface WorkbenchInspectorView {
  tabs: Array<"overview" | "debug" | "memory" | "agent" | string>;
  active_tab: "overview" | "debug" | "memory" | "agent" | string;
  overview: UiKeyValueSection[];
  debug: UiKeyValueSection[];
  memory: UiKeyValueSection[];
  agent: UiKeyValueSection[];
  current_turn_summary?: string | null;
  linked_assets: UiLinkedEntity[];
  quick_actions: UiRuntimeAction[];
}

export interface WorkbenchRunView {
  run_id: string;
  session_key: string;
  title: string;
  status: RuntimeStatus;
  agent: { id: string; name: string };
  model: { id: string; name: string };
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  metrics: {
    tool_calls: number;
    llm_calls: number;
    tokens: number;
    estimated_cost_usd: number | null;
  };
  turns: TurnSummary[];
  current_turn_id: string | null;
  status_strip: {
    label: string;
    eta_ms: number | null;
    queue_wait_ms: number;
  } | null;
  cover_artifact?: ArtifactPreview | null;
  timeline: WorkbenchTimelineItem[];
  actions?: UiRuntimeAction[];
  inspector?: WorkbenchInspectorView | null;
  trace: TraceContext;
}

export interface WorkbenchTimelineItem {
  id: string;
  turn_id: string;
  run_id: string;
  kind: string;
  status: RuntimeStatus | string;
  title: string;
  content: Record<string, unknown>;
  phase?: string | null;
  source_refs: Record<string, string>;
  started_at: string | null;
  completed_at: string | null;
  trace: TraceContext;
}

export interface WorkbenchLinkedEntityDetail {
  type: string;
  id: string;
  owner: string;
  label: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface TraceLinkedEntity {
  type: string;
  id: string;
}

export interface TraceSummaryView {
  trace_id: string;
  status: RuntimeStatus | string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  event_count: number;
  key_event_count: number;
  owners: string[];
  linked_entities: TraceLinkedEntity[];
}

export interface TraceEventView {
  event_id: string;
  name: string;
  family: string;
  owner: string;
  status: RuntimeStatus | string;
  timestamp: string;
  relative_ms: number;
  summary: string;
  key_event: boolean;
  linked_entities: TraceLinkedEntity[];
  trace: TraceContext;
  topic?: string;
  cursor?: string;
  payload?: Record<string, unknown>;
}

export interface MetricCardModel {
  id: string;
  label: string;
  value: string;
  delta: string;
  tone: "neutral" | "info" | "success" | "warning" | "danger";
}

export interface OperationsModuleOverview {
  module: string;
  title: string;
  subtitle: string;
  health: HealthStatus;
  updated_at: string;
  metrics: MetricCardModel[];
  queue: Array<Record<string, string>>;
  lane_locks: Array<Record<string, string>>;
  executor: Array<Record<string, string>>;
  actions: Array<{ id: string; label: string; risk: "normal" | "controlled" | "dangerous" }>;
}

export interface SettingsSummary {
  resource_counts: Array<MetricCardModel>;
  health_rows: Array<Record<string, string>>;
  recent_changes: Array<Record<string, string>>;
  issues: Array<Record<string, string>>;
  quick_actions: Array<{ id: string; label: string; summary: string; tone: MetricCardModel["tone"] }>;
}
