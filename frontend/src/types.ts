export interface RuntimeBinding {
  agent_id: string | null;
  llm_id: string | null;
}

export interface AgentProfileSummary {
  id: string;
  name: string;
  enabled: boolean;
  description: string;
  llm_routing_policy: {
    default_llm_id: string;
  };
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
  runtime_binding: RuntimeBinding;
  status: string;
  channel: string | null;
  chat_type: string | null;
  latest_run_id: string | null;
  latest_run_status: string | null;
  latest_run_stage: string | null;
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

export type TurnEventName =
  | "snapshot"
  | "updated"
  | "message_appended"
  | "llm_text_delta"
  | "tool_started"
  | "tool_completed"
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
