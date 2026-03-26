export interface RuntimeBinding {
  agent_id: string | null;
  llm_id: string | null;
}

export interface AgentProfileSummary {
  id: string;
  name: string;
  enabled: boolean;
  description: string;
  identity: {
    display_name: string | null;
    theme: string | null;
    emoji: string | null;
    avatar: string | null;
  };
  llm_routing_policy: {
    default_llm_id: string;
    fallback_llm_ids: string[];
    image_llm_id: string | null;
    document_llm_id: string | null;
  };
  runtime_preferences: {
    home_dir: string | null;
    workdir: string | null;
    workspace: string | null;
    sandbox_mode: string | null;
    attrs: Record<string, unknown>;
  };
}

export interface AgentHomeFile {
  name: string;
  path: string;
  exists: boolean;
  language: string;
  content: string;
}

export interface AgentHomeSnapshot {
  agent_id: string;
  agent_name: string;
  home_dir: string;
  workdir: string | null;
  files: AgentHomeFile[];
}

export interface LlmProfileSummary {
  id: string;
  model_name: string;
  provider: string;
  enabled: boolean;
}

export interface ConversationSummary {
  bulk_key: string;
  session_key: string;
  active_session_id: string;
  title: string;
  runtime_binding: RuntimeBinding;
  status: string;
  channel: string | null;
  chat_type: string | null;
  latest_run_id: string | null;
  latest_run_status: string | null;
  latest_run_stage: string | null;
  display_run_id: string | null;
  display_run_status: string | null;
  display_run_stage: string | null;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionMessage {
  id: string;
  session_key: string;
  session_id: string;
  sequence_no: number;
  role: string;
  kind: string;
  content: string | null;
  content_payload: Record<string, unknown>;
  source_kind: string | null;
  source_id: string | null;
  visibility: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TurnRun {
  id: string;
  status: string;
  stage: string;
  bulk_key: string | null;
  active_session_id: string | null;
  agent_id: string | null;
  lane_key: string | null;
  queue_policy: string;
  priority: number;
  current_step: number;
  max_steps: number;
  pending_tool_run_ids: string[];
  waiting_reason: string | null;
  inbound_instruction: {
    source: string;
    content: string | null;
    metadata: Record<string, unknown>;
  };
  delivery_target: Record<string, unknown> | null;
  result_payload: Record<string, unknown> | null;
  error: { message: string; code: string; details: Record<string, unknown> } | null;
  worker_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface TurnResponse {
  run: TurnRun;
  output_text: string | null;
}

export interface TurnSnapshotResponse extends TurnResponse {
  messages: SessionMessage[];
}

export interface TurnMessageEventPayload {
  run_id: string;
  message: SessionMessage;
}

export interface TurnTextDeltaEventPayload {
  run_id: string;
  invocation_id: string;
  text_delta: string;
  text: string;
}

export interface TurnToolEventPayload {
  run_id: string;
  status: string;
  stage: string;
  message_id: string;
  tool_name: string;
  tool_call_id: string | null;
  tool_run_id: string | null;
  tool_status: string | null;
  created_at: string;
}

export interface PendingApprovalRequestPayload {
  request_id: string;
  effect_id: string;
  label: string;
  reason: string;
  tool_ids: string[];
  scope_hint: string | null;
  created_at: string;
}

export interface RunFeedback {
  label: string;
  detail: string;
  tone: "live" | "tool" | "approval" | "idle";
}

export interface ContextBudgetSummary {
  estimatedTotalTokens: number | null;
  contextWindowTokens: number | null;
  remainingTokens: number | null;
  usagePercent: number | null;
  systemTokens: number | null;
  systemBudgetTokens: number | null;
  transcriptTokens: number | null;
  budgetSource: string | null;
}

export interface ContextMeter {
  percent: number | null;
  label: string;
  tone: "healthy" | "warn" | "critical" | "unknown";
  tooltip: string;
}

export interface MemoryCandidate {
  id: string;
  agent_id: string;
  session_key: string | null;
  run_id: string | null;
  title: string;
  content: string;
  summary: string;
  tags: string[];
  metadata: Record<string, unknown>;
  status: string;
  created_at: string;
  reviewed_at: string | null;
  review_reason: string | null;
  approved_entry_id: string | null;
}

export interface MemoryEntry {
  id: string;
  agent_id: string;
  session_key: string | null;
  run_id: string | null;
  source_candidate_id: string | null;
  title: string;
  content: string;
  summary: string;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TurnApprovalRequestedEventPayload {
  run_id: string;
  status: string;
  stage: string;
  request: PendingApprovalRequestPayload;
}

export interface TurnApprovalResolvedEventPayload {
  run_id: string;
  request_id: string;
  decision: string;
  resolved_at: string;
}

export interface CompactionRequestSummary {
  basis: string;
  label: string;
  reason: string | null;
  details: string[];
  summaryPreview: string | null;
  summaryFull: string | null;
}

export type TurnEventName =
  | "snapshot"
  | "updated"
  | "message_appended"
  | "llm_text_delta"
  | "tool_started"
  | "tool_completed"
  | "approval_requested"
  | "approval_resolved"
  | "completed"
  | "failed"
  | "cancelled"
  | "timeout";

export interface TurnEventEntry {
  id: string;
  event: TurnEventName;
  status: string;
  stage: string;
  at: string;
  detail: string | null;
}

export type DirectScope =
  | "main"
  | "per_peer"
  | "per_channel_peer"
  | "per_account_channel_peer";

export interface ConversationRoute {
  agentId: string;
  llmId?: string | null;
  channel: string;
  chatType: string;
  peerId?: string | null;
  conversationId?: string | null;
  threadId?: string | null;
  accountId?: string | null;
  mainKey: string;
  directScope: DirectScope;
}
