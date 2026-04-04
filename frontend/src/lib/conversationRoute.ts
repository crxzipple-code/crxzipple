import type { ConversationRoute, ConversationSummary, DirectScope } from "@/types";

const DEFAULT_CHANNEL = "crxzipple";

function stripThread(parts: string[]) {
  if (parts.length >= 2 && parts[parts.length - 2] === "thread") {
    return {
      core: parts.slice(0, -2),
      threadId: parts[parts.length - 1] ?? null,
    };
  }
  return { core: parts, threadId: null };
}

export function createDraftRoute(agentId: string): ConversationRoute {
  return {
    agentId,
    channel: DEFAULT_CHANNEL,
    chatType: "direct",
    mainKey: `deck-${Date.now().toString(36)}`,
    directScope: "main",
  };
}

export function routeFromConversation(
  conversation: ConversationSummary,
  fallbackAgentId: string,
): ConversationRoute {
  const sessionKey = conversation.session_key.trim();
  const parts = sessionKey ? sessionKey.split(":") : [];
  const { core, threadId } = stripThread(parts);
  const agentId = core[1] ?? conversation.runtime_binding.agent_id ?? fallbackAgentId;

  if (core[0] !== "agent") {
    return createDraftRoute(agentId);
  }

  if (core.length === 3) {
    return {
      agentId,
      llmId: conversation.runtime_binding.llm_id,
      channel: conversation.channel ?? DEFAULT_CHANNEL,
      chatType: "direct",
      mainKey: core[2] ?? "main",
      directScope: "main",
      threadId,
    };
  }

  if (core[2] === "dm" && core.length === 4) {
    return {
      agentId,
      llmId: conversation.runtime_binding.llm_id,
      channel: conversation.channel ?? DEFAULT_CHANNEL,
      chatType: "direct",
      peerId: core[3] ?? null,
      mainKey: "main",
      directScope: "per_peer",
      threadId,
    };
  }

  if (core[3] === "dm" && core.length === 5) {
    return {
      agentId,
      llmId: conversation.runtime_binding.llm_id,
      channel: core[2] ?? DEFAULT_CHANNEL,
      chatType: "direct",
      peerId: core[4] ?? null,
      mainKey: "main",
      directScope: "per_channel_peer",
      threadId,
    };
  }

  if (core[4] === "dm" && core.length === 6) {
    return {
      agentId,
      llmId: conversation.runtime_binding.llm_id,
      channel: core[2] ?? DEFAULT_CHANNEL,
      chatType: "direct",
      accountId: core[3] ?? "default",
      peerId: core[5] ?? null,
      mainKey: "main",
      directScope: "per_account_channel_peer",
      threadId,
    };
  }

  if (
    core.length === 5 &&
    (core[3] === "group" || core[3] === "channel")
  ) {
    return {
      agentId,
      llmId: conversation.runtime_binding.llm_id,
      channel: core[2] ?? DEFAULT_CHANNEL,
      chatType: core[3],
      conversationId: core[4] ?? null,
      mainKey: "main",
      directScope: "main",
      threadId,
    };
  }

  return createDraftRoute(agentId);
}

export function routePayload(route: ConversationRoute) {
  return {
    agent_id: route.agentId,
    llm_id: route.llmId ?? undefined,
    channel: route.channel,
    chat_type: route.chatType,
    peer_id: route.peerId ?? undefined,
    conversation_id: route.conversationId ?? undefined,
    thread_id: route.threadId ?? undefined,
    account_id: route.accountId ?? undefined,
    main_key: route.mainKey,
    direct_scope: route.directScope as DirectScope,
  };
}
