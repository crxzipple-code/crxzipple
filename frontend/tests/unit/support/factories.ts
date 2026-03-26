import type {
  AgentHomeSnapshot,
  AgentProfileSummary,
  ConversationRoute,
  ConversationSummary,
  LlmProfileSummary,
  PendingApprovalRequestPayload,
  SessionMessage,
  TurnResponse,
  TurnRun,
} from "@/types";

export function buildAgentProfile(
  overrides: Partial<AgentProfileSummary> = {},
): AgentProfileSummary {
  return {
    id: "assistant",
    name: "Assistant",
    enabled: true,
    description: "Default helper",
    identity: {
      display_name: "Assistant",
      theme: null,
      emoji: null,
      avatar: null,
    },
    llm_routing_policy: {
      default_llm_id: "openai.gpt-5.4-mini",
      fallback_llm_ids: [],
      image_llm_id: null,
      document_llm_id: null,
    },
    runtime_preferences: {
      home_dir: `/tmp/agents/${overrides.id ?? "assistant"}`,
      workdir: "/tmp/work",
      workspace: null,
      sandbox_mode: null,
      attrs: {},
    },
    ...overrides,
  };
}

export function buildAgentHomeSnapshot(
  overrides: Partial<AgentHomeSnapshot> = {},
): AgentHomeSnapshot {
  return {
    agent_id: "assistant",
    agent_name: "Assistant",
    home_dir: "/tmp/agents/assistant",
    workdir: "/tmp/work",
    files: [
      {
        name: "AGENT.md",
        path: "/tmp/agents/assistant/AGENT.md",
        exists: true,
        language: "markdown",
        content: "# Agent\n",
      },
      {
        name: "SOUL.md",
        path: "/tmp/agents/assistant/SOUL.md",
        exists: true,
        language: "markdown",
        content: "# Soul\n",
      },
    ],
    ...overrides,
  };
}

export function buildConversationRoute(
  overrides: Partial<ConversationRoute> = {},
): ConversationRoute {
  return {
    agentId: "assistant",
    llmId: "openai.gpt-5.4-mini",
    channel: "crxzipple",
    chatType: "direct",
    mainKey: "deck-test",
    directScope: "main",
    ...overrides,
  };
}

export function buildConversationSummary(
  overrides: Partial<ConversationSummary> = {},
): ConversationSummary {
  return {
    bulk_key: "conversation:main:crxzipple:default:deck-test",
    session_key: "agent:assistant:deck-test",
    active_session_id: "session-1",
    title: "Travel planning",
    runtime_binding: {
      agent_id: "assistant",
      llm_id: "openai.gpt-5.4-mini",
    },
    status: "active",
    channel: "crxzipple",
    chat_type: "direct",
    latest_run_id: "run-1",
    latest_run_status: "running",
    latest_run_stage: "running",
    display_run_id: "run-1",
    display_run_status: "running",
    display_run_stage: "running",
    last_message_preview: null,
    created_at: "2026-03-26T08:00:00Z",
    updated_at: "2026-03-26T08:05:00Z",
    ...overrides,
  };
}

export function buildLlmProfile(
  overrides: Partial<LlmProfileSummary> = {},
): LlmProfileSummary {
  return {
    id: "openai.gpt-5.4-mini",
    model_name: "gpt-5.4-mini",
    provider: "openai",
    enabled: true,
    ...overrides,
  };
}

export function buildPendingApproval(
  overrides: Partial<PendingApprovalRequestPayload> = {},
): PendingApprovalRequestPayload {
  return {
    request_id: "req-1",
    effect_id: "weather_data",
    label: "Weather data access",
    reason: "Needed for forecast lookup",
    tool_ids: ["open_meteo_weather.forecast_weather"],
    scope_hint: "once",
    created_at: "2026-03-26T08:00:00Z",
    ...overrides,
  };
}

export function buildRun(overrides: Partial<TurnRun> = {}): TurnRun {
  return {
    id: "run-1",
    status: "running",
    stage: "running",
    bulk_key: "conversation:main:crxzipple:default:deck-test",
    active_session_id: "session-1",
    agent_id: "assistant",
    lane_key: "bulk:conversation:main:crxzipple:default:deck-test",
    queue_policy: "jump_queue",
    priority: 100,
    current_step: 1,
    max_steps: 12,
    pending_tool_run_ids: [],
    waiting_reason: null,
    inbound_instruction: {
      source: "web",
      content: "Plan a trip",
      metadata: {},
    },
    delivery_target: null,
    result_payload: null,
    error: null,
    worker_id: "orch-1",
    metadata: {},
    created_at: "2026-03-26T08:00:00Z",
    updated_at: "2026-03-26T08:01:00Z",
    queued_at: "2026-03-26T08:00:00Z",
    started_at: "2026-03-26T08:00:01Z",
    completed_at: null,
    ...overrides,
  };
}

export function buildTurnResponse(
  overrides: Omit<Partial<TurnResponse>, "run"> & { run?: Partial<TurnRun> } = {},
): TurnResponse {
  return {
    run: buildRun(overrides.run),
    output_text: overrides.output_text ?? null,
  };
}

export function buildSessionMessage(
  overrides: Partial<SessionMessage> = {},
): SessionMessage {
  return {
    id: "message-1",
    session_key: "agent:assistant:deck-test",
    session_id: "session-1",
    sequence_no: 1,
    role: "user",
    kind: "message",
    content: "Where should we go next?",
    content_payload: { text: "Where should we go next?" },
    source_kind: "web",
    source_id: "source-1",
    visibility: "default",
    metadata: {},
    created_at: "2026-03-26T08:00:00Z",
    ...overrides,
  };
}
