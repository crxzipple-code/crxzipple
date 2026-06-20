export type RuntimeModuleId =
  | "orchestration"
  | "tool"
  | "browser"
  | "llm"
  | "access"
  | "channels"
  | "memory"
  | "context_workspace"
  | "skills"
  | "events"
  | "daemon";

export type SettingsResourceId =
  | "overview"
  | "agent-profiles"
  | "llm-profiles"
  | "tool-catalog"
  | "skill-catalog"
  | "memory-config"
  | "access-assets"
  | "channel-profiles"
  | "event-registry"
  | "runtime-defaults"
  | "environment"
  | "audit-logs"
  | "backup-restore";

export type SettingsResourceKind = Exclude<SettingsResourceId, "overview">;

export type UiTone = "neutral" | "info" | "success" | "warning" | "danger";
export type UiHealthStatus = "healthy" | "warning" | "error" | "unknown";
export type UiRuntimeStatus =
  | "accepted"
  | "queued"
  | "running"
  | "waiting"
  | "success"
  | "failed"
  | "cancelled"
  | "completed"
  | "active"
  | "inactive"
  | "draft"
  | "unknown";

export type RuntimeActionRisk = "normal" | "controlled" | "dangerous";
export type RuntimeActionMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type RuntimeActionKind = "operation" | "navigation";

export interface UiTraceContext {
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

export interface UiLinkedEntity {
  type: string;
  id: string;
  label?: string;
  owner?: RuntimeModuleId | string;
  route?: string;
  copy_value?: string;
  trace?: UiTraceContext;
}

export interface UiRuntimeAction {
  id: string;
  label: string;
  owner: RuntimeModuleId | SettingsResourceId | string;
  kind?: RuntimeActionKind;
  target?: UiLinkedEntity | null;
  method?: RuntimeActionMethod | null;
  endpoint?: string | null;
  risk: RuntimeActionRisk;
  allowed: boolean;
  disabled_reason?: string | null;
  requires_confirmation: boolean;
  reason_required: boolean;
  audit_event?: string | null;
  trace?: UiTraceContext | null;
}

export interface UiMetricCard {
  id: string;
  label: string;
  value: string;
  delta?: string;
  tone: UiTone;
  trend?: "up" | "down" | "flat";
  trace?: UiTraceContext;
}

export interface UiStatusBadge {
  label: string;
  tone: UiTone;
}

export interface UiTableColumn {
  key: string;
  label: string;
  align?: "start" | "center" | "end";
  width?: string;
  sortable?: boolean;
}

export interface UiTableCellValue {
  text: string;
  tone?: UiTone;
  badge?: boolean;
  mono?: boolean;
  route?: string;
  copy_value?: string;
}

export interface UiTableRow {
  id: string;
  cells: Record<string, string | number | null | UiTableCellValue>;
  status?: UiRuntimeStatus | UiHealthStatus | string | null;
  tone?: UiTone;
  trace?: UiTraceContext | null;
  linked_entities?: UiLinkedEntity[];
  actions?: UiRuntimeAction[];
}

export interface UiTableSection {
  id: string;
  title: string;
  description?: string;
  columns: UiTableColumn[];
  rows: UiTableRow[];
  total?: number;
  view_all_route?: string | null;
  empty_state?: string | null;
  actions?: UiRuntimeAction[];
}

export interface UiKeyValueItem {
  label: string;
  value: string;
  tone?: UiTone;
  route?: string;
  copy_value?: string;
}

export interface UiKeyValueSection {
  id: string;
  title: string;
  items: UiKeyValueItem[];
  actions?: UiRuntimeAction[];
}

export interface UiChartSeries {
  id: string;
  label: string;
  tone: UiTone;
  points: Array<{ x: string; y: number }>;
}

export interface UiChartSection {
  id: string;
  title: string;
  kind: "line" | "bar" | "donut" | "flow" | "graph";
  total?: string | number;
  series?: UiChartSeries[];
  segments?: Array<{ id: string; label: string; value: number; tone: UiTone }>;
  rows?: UiTableRow[];
  actions?: UiRuntimeAction[];
}

export interface UiConnectionState {
  status: "connected" | "connecting" | "degraded" | "offline";
  label: string;
  updated_at: string | null;
  details?: string;
}

export interface UiModuleRole {
  label: string;
  can_operate: boolean;
  scope?: string;
}

export interface WorkbenchThreadSummary {
  id: string;
  run_id?: string;
  session_key: string;
  title: string;
  agent: string;
  status: UiRuntimeStatus;
  current_activity: string;
  waiting_reason?: string;
  updated_at: string;
  starred?: boolean;
  trace?: UiTraceContext;
}

export interface WorkbenchHomeReadModel {
  connection: UiConnectionState;
  filters: Array<{ id: string; label: string; count: number }>;
  threads: WorkbenchThreadSummary[];
  active_thread_id: string | null;
  active_run_id: string | null;
  actions: UiRuntimeAction[];
}

export interface WorkbenchRunHeader {
  run_id: string;
  session_key: string;
  title: string;
  status: UiRuntimeStatus;
  cover_artifact?: UiLinkedEntity;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  agent: UiLinkedEntity;
  model: UiLinkedEntity;
  metrics: {
    tool_calls: number;
    llm_calls: number;
    tokens: number;
    estimated_cost_usd: number | null;
  };
  trace: UiTraceContext;
  actions: UiRuntimeAction[];
}

export interface WorkbenchTurnSummary {
  turn_id: string;
  ordinal: number;
  status: UiRuntimeStatus;
  duration_ms: number | null;
  summary?: string;
  trace?: UiTraceContext;
}

export interface WorkbenchStepArtifact {
  artifact_id: string;
  name: string;
  kind: "image" | "json" | "file" | "markdown" | string;
  size_bytes: number | null;
  mime_type?: string | null;
  width?: number | null;
  height?: number | null;
  preview_url?: string;
  download_url?: string;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface WorkbenchStepView {
  step_id: string;
  turn_id: string;
  run_id: string;
  type:
    | "user_input"
    | "agent_thinking"
    | "llm"
    | "continuation_decision"
    | "tool_call"
    | "tool_result"
    | "approval_required"
    | "missing_access"
    | "error"
    | "final_response";
  status: UiRuntimeStatus;
  title: string;
  summary: string;
  markdown?: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  artifacts: WorkbenchStepArtifact[];
  badges: UiStatusBadge[];
  details_available: boolean;
  linked_entities: UiLinkedEntity[];
  actions: UiRuntimeAction[];
  approval?: ApprovalRequestDetail | null;
  trace: UiTraceContext;
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

export interface WorkbenchInspectorReadModel {
  tabs: Array<"overview" | "debug" | "memory" | "agent">;
  active_tab: "overview" | "debug" | "memory" | "agent";
  overview: UiKeyValueSection[];
  current_turn_summary?: string;
  linked_assets: UiLinkedEntity[];
  quick_actions: UiRuntimeAction[];
}

export interface WorkbenchRunReadModel {
  header: WorkbenchRunHeader;
  turns: WorkbenchTurnSummary[];
  current_turn_id: string | null;
  steps: WorkbenchStepView[];
  status_strip?: {
    label: string;
    eta_ms: number | null;
    queue_wait_ms: number;
  };
  inspector: WorkbenchInspectorReadModel;
  composer: {
    enabled: boolean;
    placeholder: string;
    tool_menu_enabled: boolean;
  };
}

export interface TraceFilterReadModel {
  quick_search?: string;
  common_ids: Array<{ id: string; label: string; value?: string }>;
  time_range?: { from: string | null; to: string | null };
  status_counts: Array<{ status: string; label: string; count: number; selected: boolean }>;
  family_counts: Array<{ family: string; label: string; count: number; selected: boolean }>;
  owner_counts?: Array<{ owner: string; count: number; selected: boolean }>;
  key_events_only: boolean;
}

export interface TraceTimelineEvent {
  event_id: string;
  name: string;
  family: string;
  owner: string;
  status: UiRuntimeStatus | string;
  timestamp: string;
  relative_ms: number;
  summary: string;
  key_event: boolean;
  linked_entities: UiLinkedEntity[];
  topic?: string;
  cursor?: string;
  payload?: Record<string, unknown>;
  trace: UiTraceContext;
}

export interface TraceInspectorReadModel {
  selected_index: number;
  total: number;
  event: TraceTimelineEvent | null;
  tabs: Array<"overview" | "payload" | "payload_diff" | "logs" | "events" | "linked">;
  overview: UiKeyValueSection[];
  linked_entities: UiLinkedEntity[];
  quick_actions: UiRuntimeAction[];
}

export interface TraceTimelineReadModel {
  trace_id: string;
  status: UiRuntimeStatus | string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  event_count: number;
  key_event_count: number;
  owners: string[];
  linked_entities: UiLinkedEntity[];
  filters: TraceFilterReadModel;
  events: TraceTimelineEvent[];
  inspector: TraceInspectorReadModel;
}

export interface TraceGraphLane {
  id: string;
  label: string;
  owner: RuntimeModuleId | "observation" | "error" | string;
  count: number;
  tone: UiTone;
}

export interface TraceGraphNode {
  id: string;
  lane_id: string;
  event_id: string;
  label: string;
  owner: string;
  service?: string;
  status: UiRuntimeStatus | string;
  duration_ms?: number;
  position?: { x: number; y: number };
  linked_entities: UiLinkedEntity[];
  trace: UiTraceContext;
}

export interface TraceGraphEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  relation: "causal" | "impact" | "observation";
  tone?: UiTone;
}

export interface TraceGraphReadModel {
  trace_id: string;
  status: UiRuntimeStatus | string;
  summary: UiKeyValueItem[];
  lanes: TraceGraphLane[];
  nodes: TraceGraphNode[];
  edges: TraceGraphEdge[];
  selected_node_id: string | null;
  inspector: TraceInspectorReadModel;
  legend: Array<{ id: string; label: string; tone: UiTone }>;
}

export interface OperationsTab {
  id: string;
  label: string;
  count?: number;
  tone?: UiTone;
}

export interface OperationsPageBase {
  module: RuntimeModuleId;
  title: string;
  subtitle: string;
  health: UiHealthStatus;
  updated_at: string;
  auto_refresh: boolean;
  role: UiModuleRole;
  metrics: UiMetricCard[];
  tabs: OperationsTab[];
  active_tab: string;
  trace?: UiTraceContext;
  actions: UiRuntimeAction[];
}

export interface OperationsOrchestrationReadModel extends OperationsPageBase {
  module: "orchestration";
  scheduler_status: UiKeyValueSection;
  backpressure: UiChartSection;
  stuck_runs: UiTableSection;
  policy_limits: UiKeyValueSection;
  run_queue: UiTableSection;
  execution_chains: UiTableSection;
  lane_locks: UiTableSection;
  executor_overview: UiTableSection;
  ingress_queue: UiTableSection;
  recent_failures: UiTableSection;
  ops_event_log: UiTableSection;
}

export interface OperationsToolReadModel extends OperationsPageBase {
  module: "tool";
  active_tool_runs: UiTableSection;
  tool_queue_runs: UiTableSection;
  tool_waiting_io: UiTableSection;
  tool_runs: UiTableSection;
  tool_types: UiChartSection;
  source_health: UiTableSection;
  discovery_failures: UiTableSection;
  function_catalog: UiTableSection;
  provider_backend_health: UiTableSection;
  cli_process_health: UiTableSection;
  auth_missing: UiTableSection;
  worker_pool: UiChartSection;
  workers: UiTableSection;
  tool_queue: UiTableSection;
  capability_limits: UiTableSection;
  provider_limits: UiTableSection;
  provider_history: UiTableSection;
  run_blockers: UiTableSection;
  inline_risk: UiKeyValueSection;
  recent_artifacts: UiTableSection;
  tool_lifecycle_events: UiTableSection;
  strategies: UiTableSection;
  worker_details: OperationsToolWorkerDetail[];
  tool_run_details: OperationsToolRunDetail[];
}

export interface OperationsBrowserReadModel extends OperationsPageBase {
  module: "browser";
  profiles: UiTableSection;
  profile_pools: UiTableSection;
  profile_allocations: UiTableSection;
  page_observations: UiTableSection;
  daemon_runtimes: UiTableSection;
  network_activity: UiTableSection;
  diagnostics: UiTableSection;
}

export interface OperationsToolWorkerDetail {
  worker_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  capabilities: UiKeyValueSection;
  runtimes: UiTableSection;
  provider_limits: UiTableSection;
  events: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsToolRunDetail {
  run_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  invocation_context: UiKeyValueItem[];
  input_payload: unknown;
  result_payload: unknown;
  result_summary: string;
  error: string;
  error_facts: UiKeyValueSection;
  assignments: UiTableSection;
  events: UiTableSection;
  artifacts: UiTableSection;
}

export interface OperationsLlmReadModel extends OperationsPageBase {
  module: "llm";
  provider_access_health: UiTableSection;
  provider_auth_blocked: UiTableSection;
  model_resolver: UiChartSection | UiTableSection;
  rate_limiter: UiKeyValueSection;
  limiter_queue: UiTableSection;
  streaming_requests: UiTableSection;
  recent_invocations: UiTableSection;
  failed_invocations: UiTableSection;
  latency: UiChartSection;
  token_usage: UiChartSection;
  invocation_rate: UiChartSection;
  stream_health: UiKeyValueSection;
  execution_blocking_risk: UiKeyValueSection;
  fallback_problems: UiTableSection;
  context_pressure: UiChartSection;
  model_availability: UiTableSection;
  error_summary: UiTableSection;
  llm_lifecycle_events: UiTableSection;
  invocation_details: OperationsLlmInvocationDetail[];
}

export interface OperationsLlmInvocationDetail {
  invocation_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  request_context: UiKeyValueItem[];
  runtime_observations: UiKeyValueSection;
  runtime_request_summary: Record<string, unknown>;
  request_payload: unknown;
  provider_render_report: Record<string, unknown>;
  provider_wire_preview: Record<string, unknown>;
  provider_context_mapping: UiTableSection;
  result_payload: unknown;
  result_summary: string;
  error: string;
  resolver: UiKeyValueSection;
  error_facts: UiKeyValueSection;
  policy_trace: UiTableSection;
  response_items: UiTableSection;
  response_runtime_mapping: UiTableSection;
  response_events: UiTableSection;
  events: UiTableSection;
}

export interface OperationsAccessReadModel extends OperationsPageBase {
  module: "access";
  access_targets: UiTableSection;
  access_requirements: UiTableSection;
  access_audit_summary: UiTableSection;
  missing_access: UiTableSection;
  credential_health: UiChartSection;
  provider_auth_blocked: UiTableSection;
  credentials_by_kind: UiChartSection;
  expiring_soon: UiTableSection;
  auth_success_rate: UiChartSection;
  authentication_status: UiTableSection;
  access_usage: UiTableSection;
  recent_access_events: UiTableSection;
  fallback_problems: UiTableSection;
  setup_flows: UiTableSection;
  target_details: OperationsAccessTargetDetail[];
}

export interface OperationsAccessTargetDetail {
  target_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  checks: UiTableSection;
  usages: UiTableSection;
  setup: UiTableSection;
  events: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsChannelsReadModel extends OperationsPageBase {
  module: "channels";
  channel_status: UiTableSection;
  message_flow: UiChartSection;
  delivery_trend: UiChartSection;
  top_channels: UiChartSection;
  dead_letter_queue: UiTableSection;
  recent_messages: UiTableSection;
  interactions: UiTableSection;
  failures_by_category: UiChartSection;
  channel_bindings: UiTableSection;
  connection_bindings: UiTableSection;
  channel_profiles: UiTableSection;
  channel_events: UiTableSection;
  contracts: UiTableSection;
  runtime_details: OperationsChannelRuntimeDetail[];
  record_details: OperationsChannelRecordDetail[];
  interaction_details: OperationsChannelInteractionDetail[];
}

export interface OperationsChannelRuntimeDetail {
  runtime_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  capabilities: UiKeyValueSection;
  account_bindings: UiTableSection;
  connection_bindings: UiTableSection;
  events: UiTableSection;
  dead_letters: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsChannelRecordDetail {
  record_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  payload: unknown;
  trace: unknown;
  related: UiTableSection;
}

export interface OperationsChannelInteractionDetail {
  interaction_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  routing: UiKeyValueSection;
  reply_address: UiKeyValueSection;
  metadata: UiKeyValueSection;
  events: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsMemoryReadModel extends OperationsPageBase {
  module: "memory";
  memory_stores: UiTableSection;
  context_resolution: UiTableSection;
  index_health: UiChartSection;
  index_jobs: UiTableSection;
  index_sync_activity: UiTableSection;
  retrieval_performance: UiChartSection;
  retrieval_trace: UiTableSection;
  write_flush: UiTableSection;
  memory_usage: UiTableSection;
  recent_retrieval_logs: UiTableSection;
  source_scan_status: UiTableSection;
  source_files: UiTableSection;
  file_details: OperationsMemoryFileDetail[];
}

export interface OperationsMemoryFileDetail {
  file_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  excerpt: string;
  related: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsSkillsReadModel extends OperationsPageBase {
  module: "skills";
  recently_resolved_skills: UiTableSection;
  resolution_outcomes: UiChartSection;
  top_used_skills: UiTableSection;
  missing_capabilities: UiTableSection;
  access_requirements: UiTableSection;
  capability_requirements: UiTableSection;
  resolution_logs: UiTableSection;
  skill_reads: UiTableSection;
  resolver_detail: UiTableSection;
  authoring_backlog: UiTableSection;
  authoring_failures: UiTableSection;
  import_normalize: UiRuntimeAction[];
  skill_package_sources: UiChartSection;
  conflicts_overrides: UiTableSection;
  profile_usage: UiTableSection;
  skill_inspector?: SettingsDetailPanel;
  skill_details?: OperationsSkillDetail[];
}

export interface OperationsSkillDetail {
  skill_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  requirements: UiTableSection;
  resources: UiTableSection;
  events: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsEventsReadModel extends OperationsPageBase {
  module: "events";
  events_over_time: UiChartSection;
  events_by_surface: UiChartSection;
  owners_by_volume: UiTableSection;
  contract_compatibility: UiKeyValueSection;
  recent_events: UiTableSection;
  consumer_health: UiTableSection;
  observer_health: UiTableSection;
  observer_lag: UiTableSection;
  topics: UiTableSection;
  subscriptions: UiTableSection;
  observer_coverage: UiTableSection;
  dead_letters: UiTableSection;
  contracts: UiTableSection;
  routes: UiTableSection;
  event_details: OperationsEventsEventDetail[];
  event_inspector?: TraceInspectorReadModel;
}

export interface OperationsEventsEventDetail {
  event_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  payload: unknown;
  trace: unknown;
  contracts: UiTableSection;
  subscriptions: UiTableSection;
}

export interface OperationsDaemonReadModel extends OperationsPageBase {
  module: "daemon";
  service_sets: UiTableSection;
  services: UiTableSection;
  instances: UiTableSection;
  leases: UiTableSection;
  drain_overview: UiKeyValueSection;
  dependency_health: UiTableSection;
  processes: UiTableSection;
  process_health: UiChartSection;
  restart_summary: UiChartSection;
  lease_health: UiChartSection;
  daemon_events: UiTableSection;
  quick_actions: UiRuntimeAction[];
  links_to_operations: UiLinkedEntity[];
  instance_details: OperationsDaemonInstanceDetail[];
  lease_details: OperationsDaemonLeaseDetail[];
  process_details: OperationsDaemonProcessDetail[];
}

export interface OperationsDaemonInstanceDetail {
  instance_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  environment: UiKeyValueSection;
  service: UiKeyValueSection;
  leases: UiTableSection;
  events: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsDaemonLeaseDetail {
  lease_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  metadata: UiKeyValueSection;
  events: UiTableSection;
  raw_payload: unknown;
}

export interface OperationsDaemonProcessDetail {
  process_id: string;
  title: string;
  status: string;
  tone: UiTone;
  summary: UiKeyValueItem[];
  metadata: UiKeyValueSection;
  output: UiTableSection;
  raw_payload: unknown;
}

export type OperationsReadModel =
  | OperationsOrchestrationReadModel
  | OperationsToolReadModel
  | OperationsBrowserReadModel
  | OperationsLlmReadModel
  | OperationsAccessReadModel
  | OperationsChannelsReadModel
  | OperationsMemoryReadModel
  | OperationsSkillsReadModel
  | OperationsEventsReadModel
  | OperationsDaemonReadModel;

export type SettingsStatus =
  | "ready"
  | "empty"
  | "warning"
  | "error"
  | "valid"
  | "invalid"
  | "unknown"
  | (string & {});

export type SettingsPayload = Record<string, unknown>;
export type SettingsTableColumn = string | UiTableColumn;
export type SettingsTableCellValue = string | number | boolean | null | UiTableCellValue;
export type SettingsTableRow = Record<string, SettingsTableCellValue> | UiTableRow;

export type SettingsActionName =
  | "dry-run"
  | "validate"
  | "publish"
  | "rollback"
  | "enable"
  | "disable"
  | "create"
  | "update";

export interface SettingsHealth {
  status: SettingsStatus;
  degraded: boolean;
  source: string;
  missing_resource_kinds?: SettingsResourceKind[];
}

export interface SettingsKeyValueItem {
  label: string;
  value: string | number | boolean | null;
  tone?: UiTone;
  route?: string;
  copy_value?: string;
}

export interface SettingsKeyValueSection {
  id?: string;
  title: string;
  items: SettingsKeyValueItem[];
  actions?: SettingsActionDescriptor[];
}

export interface SettingsTableSection {
  id?: string;
  title: string;
  description?: string;
  columns: SettingsTableColumn[];
  rows: SettingsTableRow[];
  total?: number;
  limit?: number;
  offset?: number;
  view_all_route?: string | null;
  empty_state?: string | null;
  actions?: SettingsActionDescriptor[];
}

export interface SettingsChartSeriesItem {
  id?: string;
  label: string;
  value?: number;
  tone?: UiTone;
  points?: Array<{ x: string; y: number }>;
}

export interface SettingsChartSection {
  id?: string;
  title: string;
  kind?: "line" | "bar" | "donut" | "flow" | "graph" | (string & {});
  total?: string | number;
  series?: SettingsChartSeriesItem[];
  segments?: Array<{ id: string; label: string; value: number; tone?: UiTone }>;
  rows?: SettingsTableRow[];
  actions?: SettingsActionDescriptor[];
}

export interface SettingsActionDescriptor {
  id: string;
  label: string;
  method?: RuntimeActionMethod | string;
  route?: string;
  endpoint?: string | null;
  requires_reason?: boolean;
  reason_required?: boolean;
  risk?: "low" | "medium" | "high" | RuntimeActionRisk | (string & {});
  allowed?: boolean;
  disabled_reason?: string | null;
  requires_confirmation?: boolean;
}

export interface SettingsLink {
  id?: string;
  label: string;
  route: string;
}

export interface SettingsOverviewReadModel {
  resource: "overview";
  title: string;
  description: string;
  status: SettingsStatus;
  health: SettingsHealth;
  counts: {
    resources: number;
    kinds: number;
    audits: number;
  };
  resource_counts: Array<{
    id: SettingsResourceKind;
    label: string;
    value: number;
    tone: UiTone | (string & {});
    route: string;
  }>;
  contract_summary: SettingsKeyValueSection;
  configuration_summary: SettingsKeyValueSection;
  configuration_health: SettingsTableSection;
  recent_changes: SettingsTableSection;
  configuration_distribution: SettingsChartSection;
  configuration_issues: SettingsTableSection;
  configuration_inheritance: SettingsChartSection | SettingsKeyValueSection;
  sources_versioning: SettingsKeyValueSection;
  quick_actions: SettingsActionDescriptor[];
  useful_links: SettingsLink[];
}

export interface SettingsResolutionSource {
  kind: string;
  name: string;
  source_id: string;
  version?: number | string | null;
  version_id?: string | null;
  override_id?: string | null;
  applied: boolean;
  reason?: string | null;
}

export interface SettingsResolutionPayload {
  resource_ref: {
    kind: SettingsResourceKind | string;
    id: string;
  };
  value: unknown;
  source: SettingsResolutionSource;
  sources: SettingsResolutionSource[];
  override_trace: SettingsResolutionSource[];
  snapshot_id: string | null;
  resolved_at: string | null;
  validation: SettingsPayload;
}

export interface SettingsResourceSummary {
  id: string;
  resource_id: string;
  kind: SettingsResourceKind;
  display_name: string;
  status: SettingsStatus;
  enabled: boolean;
  source: string | null;
  version: number | null;
  updated_at: string | null;
  metadata: SettingsPayload;
  effective_config: unknown;
  resolution: SettingsResolutionPayload;
}

export interface SettingsDetailPanel {
  id: string;
  title: string;
  status?: SettingsStatus;
  tabs: OperationsTab[];
  active_tab: string;
  sections: Array<SettingsKeyValueSection | SettingsTableSection | SettingsChartSection>;
  actions: SettingsActionDescriptor[];
  linked_entities?: UiLinkedEntity[];
}

export interface SettingsValidationSummary {
  status: SettingsStatus;
  checks: SettingsTableSection;
  result?: SettingsPayload;
  last_validated_at?: string | null;
  actions: SettingsActionDescriptor[];
}

export interface SettingsEffectiveConfiguration {
  title: string;
  values: SettingsTableSection;
  resolution_trace?: SettingsTableSection | SettingsChartSection;
  export_actions: SettingsActionDescriptor[];
}

export interface SettingsImpactPreview {
  level: UiTone | (string & {});
  summary: SettingsKeyValueSection;
  affected_entities: SettingsTableSection;
  dry_run_action?: SettingsActionDescriptor;
}

export interface SettingsDangerZone {
  title: string;
  description?: string;
  actions: SettingsActionDescriptor[];
}

export interface SettingsAuditRecord {
  audit_id: string;
  id: string;
  action: SettingsActionName | (string & {});
  action_type: string;
  kind: SettingsResourceKind | string;
  resource_id: string | null;
  actor: string | null;
  reason: string | null;
  risk: string | null;
  dry_run: boolean;
  status: SettingsStatus;
  request_metadata: unknown;
  result: unknown;
  error: unknown;
  created_at: string | null;
  completed_at: string | null;
}

export interface SettingsAuditSummary {
  recent_changes: SettingsTableSection;
  audit_history_route?: string;
  reason_required: boolean;
}

export interface SettingsRuntimeDefaultsField {
  path: string;
  value: string | number | boolean | null;
  default: string | number | boolean | null;
  unit?: string | null;
  minimum?: number | null;
  consumer?: string | null;
  apply_requirement?: string | null;
  input?: "number" | "toggle" | (string & {});
}

export interface SettingsRuntimeDefaultsGroup {
  id: "orchestration" | "compaction" | "tool_worker" | (string & {});
  fields: SettingsRuntimeDefaultsField[];
}

export interface SettingsRuntimeDefaultsApplyRequirement {
  id: string;
  mode?: "restart_required" | "hot_apply" | (string & {});
  owner?: string | null;
  applies_after?: string | null;
}

export interface SettingsRuntimeDefaultsReadModel {
  schema: "runtime-defaults.v1" | (string & {});
  resource_id: string;
  status: SettingsStatus;
  enabled: boolean;
  source?: string | null;
  version?: number | string | null;
  updated_at?: string | null;
  resolved_at?: string | null;
  effective_payload: SettingsPayload;
  groups: SettingsRuntimeDefaultsGroup[];
  apply_requirements: SettingsRuntimeDefaultsApplyRequirement[];
  validation: SettingsValidationSummary;
}

export interface SettingsResourceDetailReadModel {
  resource: SettingsResourceKind;
  kind: SettingsResourceKind;
  id: string;
  resource_id: string;
  title: string;
  status: SettingsStatus;
  enabled: boolean;
  version: number | null;
  source: string | null;
  payload: unknown;
  effective_config: unknown;
  resolution: SettingsResolutionPayload;
  detail: SettingsDetailPanel;
  validation: SettingsValidationSummary;
  impact: SettingsImpactPreview;
  audit: SettingsAuditSummary;
  actions: SettingsActionDescriptor[];
  versions: SettingsPayload[];
  runtime_defaults?: SettingsRuntimeDefaultsReadModel;
}

export interface SettingsResourcePageReadModel {
  resource: Exclude<SettingsResourceKind, "audit-logs">;
  kind: Exclude<SettingsResourceKind, "audit-logs">;
  title: string;
  description: string;
  status: SettingsStatus;
  health: SettingsHealth;
  tabs: OperationsTab[];
  active_tab: string;
  resources: SettingsResourceSummary[];
  list: SettingsTableSection;
  detail: SettingsResourceDetailReadModel | null;
  summary: SettingsKeyValueSection[];
  effective_configuration: SettingsEffectiveConfiguration;
  validation: SettingsValidationSummary;
  impact: SettingsImpactPreview;
  audit: SettingsAuditSummary;
  danger_zone: SettingsDangerZone;
  actions: SettingsActionDescriptor[];
}

export interface SettingsAuditLogsPageReadModel {
  resource: "audit-logs";
  kind: "audit-logs";
  title: string;
  description: string;
  status: SettingsStatus;
  health: SettingsHealth;
  tabs: OperationsTab[];
  active_tab: string;
  resources: SettingsAuditRecord[];
  list: SettingsTableSection;
  detail: SettingsAuditRecord | null;
  summary: SettingsKeyValueSection[];
  validation: SettingsValidationSummary;
  audit: SettingsAuditSummary;
  actions: SettingsActionDescriptor[];
}

export type SettingsKindPageReadModel =
  | SettingsResourcePageReadModel
  | SettingsAuditLogsPageReadModel;

export type SettingsDetailReadModel =
  | SettingsResourceDetailReadModel
  | SettingsAuditRecord;

export interface SettingsActionRequest {
  resource_id?: string | null;
  payload?: SettingsPayload;
  reason?: string | null;
  actor?: string | null;
  risk?: string | null;
  dry_run?: boolean;
  metadata?: SettingsPayload;
}

export interface SettingsActionResultPayload {
  resource_id?: string | null;
  mutation: SettingsActionName | (string & {});
  applied: boolean;
  resource?: SettingsPayload | null;
  version?: SettingsPayload | null;
  validation?: SettingsValidationSummary | SettingsPayload;
  resolution?: SettingsResolutionPayload;
  impact?: SettingsImpactPreview;
  runtime_defaults?: SettingsRuntimeDefaultsReadModel;
  apply_requirement?: SettingsRuntimeDefaultsApplyRequirement[];
  [key: string]: unknown;
}

export interface SettingsActionResponse<
  Result extends SettingsActionResultPayload | SettingsPayload = SettingsActionResultPayload,
> {
  action: SettingsActionName | (string & {});
  kind: SettingsResourceKind | string;
  resource_id: string | null;
  status: SettingsStatus;
  dry_run: boolean;
  audit: SettingsAuditRecord;
  result: Result;
}

export interface SettingsBootstrapImportResponse {
  action: "bootstrap-import";
  status: SettingsStatus;
  result: SettingsPayload;
  imported_counts: Record<string, number>;
}

export type SettingsReadModel = SettingsOverviewReadModel | SettingsKindPageReadModel;
