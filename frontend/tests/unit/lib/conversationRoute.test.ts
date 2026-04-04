import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDraftRoute,
  routeFromConversation,
  routePayload,
} from "@/lib/conversationRoute";

import { buildConversationSummary } from "../support/factories";

describe("conversationRoute", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("creates deterministic draft routes from the current time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-26T12:00:00Z"));

    const route = createDraftRoute("assistant");

    expect(route).toMatchObject({
      agentId: "assistant",
      channel: "crxzipple",
      chatType: "direct",
      directScope: "main",
    });
    expect(route.mainKey).toMatch(/^deck-[a-z0-9]+$/);
  });

  it("maps main conversations and preserves thread ids", () => {
    const route = routeFromConversation(
      buildConversationSummary({
        session_key: "agent:assistant:deck-42:thread:thread-7",
        channel: "wechat",
        runtime_binding: {
          agent_id: "assistant",
          llm_id: "openai.gpt-5.4-mini",
        },
      }),
      "fallback-agent",
    );

    expect(route).toEqual({
      agentId: "assistant",
      llmId: "openai.gpt-5.4-mini",
      channel: "wechat",
      chatType: "direct",
      mainKey: "deck-42",
      directScope: "main",
      threadId: "thread-7",
    });
  });

  it("maps dm conversations for both peer-only and channel/account scoped keys", () => {
    const perPeerRoute = routeFromConversation(
      buildConversationSummary({
        session_key: "agent:assistant:dm:peer-9",
        runtime_binding: {
          agent_id: null,
          llm_id: "openai.gpt-5.4-mini",
        },
      }),
      "fallback-agent",
    );
    const scopedRoute = routeFromConversation(
      buildConversationSummary({
        session_key: "agent:assistant:telegram:acct-1:dm:peer-9",
        runtime_binding: {
          agent_id: "assistant",
          llm_id: "openai.gpt-5.4",
        },
      }),
      "fallback-agent",
    );

    expect(perPeerRoute).toEqual({
      agentId: "assistant",
      llmId: "openai.gpt-5.4-mini",
      channel: "crxzipple",
      chatType: "direct",
      peerId: "peer-9",
      mainKey: "main",
      directScope: "per_peer",
      threadId: null,
    });
    expect(scopedRoute).toEqual({
      agentId: "assistant",
      llmId: "openai.gpt-5.4",
      channel: "telegram",
      chatType: "direct",
      accountId: "acct-1",
      peerId: "peer-9",
      mainKey: "main",
      directScope: "per_account_channel_peer",
      threadId: null,
    });
  });

  it("maps non-main group conversations and falls back to draft for unknown keys", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-26T12:00:00Z"));

    const groupRoute = routeFromConversation(
      buildConversationSummary({
        session_key: "agent:assistant:slack:group:conv-55",
        runtime_binding: {
          agent_id: "assistant",
          llm_id: "openai.gpt-5.4-mini",
        },
      }),
      "fallback-agent",
    );
    const fallbackRoute = routeFromConversation(
      buildConversationSummary({
        session_key: "legacy-key-without-shape",
        runtime_binding: {
          agent_id: null,
          llm_id: null,
        },
      }),
      "fallback-agent",
    );

    expect(groupRoute).toEqual({
      agentId: "assistant",
      llmId: "openai.gpt-5.4-mini",
      channel: "slack",
      chatType: "group",
      conversationId: "conv-55",
      mainKey: "main",
      directScope: "main",
      threadId: null,
    });
    expect(fallbackRoute).toMatchObject({
      agentId: "fallback-agent",
      channel: "crxzipple",
      chatType: "direct",
      directScope: "main",
    });
    expect(fallbackRoute.mainKey).toMatch(/^deck-[a-z0-9]+$/);
  });

  it("serializes route payloads without leaking null fields", () => {
    expect(routePayload({
      agentId: "assistant",
      llmId: "openai.gpt-5.4-mini",
      channel: "wechat",
      chatType: "direct",
      peerId: null,
      conversationId: "conv-1",
      threadId: "thread-2",
      accountId: "acct-1",
      mainKey: "deck-42",
      directScope: "per_account_channel_peer",
    })).toEqual({
      agent_id: "assistant",
      llm_id: "openai.gpt-5.4-mini",
      channel: "wechat",
      chat_type: "direct",
      peer_id: undefined,
      conversation_id: "conv-1",
      thread_id: "thread-2",
      account_id: "acct-1",
      main_key: "deck-42",
      direct_scope: "per_account_channel_peer",
    });
  });
});
