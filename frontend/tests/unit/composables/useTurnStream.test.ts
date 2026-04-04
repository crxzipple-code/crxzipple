import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  PendingApprovalRequestPayload,
  SessionMessage,
  TurnResponse,
} from "@/types";

import {
  buildConversationSummary,
  buildPendingApproval,
  buildSessionMessage,
  buildTurnResponse,
} from "../support/factories";

const openTurnEventsMock = vi.fn();
const getConversationMessagesMock = vi.fn();

vi.mock("@/lib/api", () => ({
  openTurnEvents: (...args: unknown[]) => openTurnEventsMock(...args),
  getConversationMessages: (...args: unknown[]) => getConversationMessagesMock(...args),
}));

import { useTurnStream } from "@/composables/useTurnStream";

describe("useTurnStream", () => {
  beforeEach(() => {
    openTurnEventsMock.mockReset();
    getConversationMessagesMock.mockReset();
  });

  it("syncs and clears pending approval requests from turn payloads", () => {
    const messages = ref<SessionMessage[]>([]);
    const activeTurn = ref<TurnResponse | null>(null);
    const pendingApproval = ref<PendingApprovalRequestPayload | null>(null);

    const stream = useTurnStream({
      messages,
      activeTurn,
      pendingApproval,
      activeSessionKey: ref<string | null>(null),
      busy: ref(false),
      lastError: ref<string | null>(null),
      activeConversation: ref(buildConversationSummary()),
      draftMainKey: ref("deck-test"),
      hydrateConversationAfterTurn: vi.fn().mockResolvedValue(undefined),
      refreshConversations: vi.fn().mockResolvedValue(undefined),
    });

    stream.syncPendingApprovalFromTurn(
      buildTurnResponse({
        run: {
          stage: "waiting_for_confirmation",
          metadata: {
            pending_approval_request: buildPendingApproval(),
          },
        },
      }),
    );

    expect(pendingApproval.value).toEqual(buildPendingApproval());

    stream.syncPendingApprovalFromTurn(buildTurnResponse());
    expect(pendingApproval.value).toBeNull();
  });

  it("merges stream events into local state and completes the turn lifecycle", async () => {
    const source = { close: vi.fn() };
    let handlers:
      | {
          onEvent: (event: string, payload: unknown) => Promise<void> | void;
          onError?: (error: Event) => void;
        }
      | undefined;

    openTurnEventsMock.mockImplementation((_runId, options) => {
      handlers = options as typeof handlers;
      return source as unknown as EventSource;
    });

    const optimisticMessage = buildSessionMessage({
      id: "optimistic-1",
      metadata: { optimistic: true },
      source_id: "local-pending",
    });
    const messages = ref<SessionMessage[]>([optimisticMessage]);
    const activeTurn = ref<TurnResponse | null>(null);
    const pendingApproval = ref<PendingApprovalRequestPayload | null>(
      buildPendingApproval(),
    );
    const busy = ref(true);
    const lastError = ref<string | null>(null);
    const hydrateConversationAfterTurn = vi.fn().mockResolvedValue(undefined);
    const refreshConversations = vi.fn().mockResolvedValue(undefined);

    const stream = useTurnStream({
      messages,
      activeTurn,
      pendingApproval,
      activeSessionKey: ref<string | null>(null),
      busy,
      lastError,
      activeConversation: ref(buildConversationSummary()),
      draftMainKey: ref("deck-test"),
      hydrateConversationAfterTurn,
      refreshConversations,
    });

    stream.watchTurn("run-1");
    expect(stream.streamState.value).toBe("streaming");
    expect(openTurnEventsMock).toHaveBeenCalledWith(
      "run-1",
      expect.objectContaining({
        pollIntervalSeconds: 0.35,
        timeoutSeconds: 90,
      }),
    );

    await handlers?.onEvent("message_appended", {
      run_id: "run-1",
      message: buildSessionMessage({
        id: "server-user-1",
        metadata: {},
      }),
    });
    expect(messages.value).toEqual([
      buildSessionMessage({
        id: "server-user-1",
        metadata: {},
      }),
    ]);

    await handlers?.onEvent("tool_started", {
      run_id: "run-1",
      status: "running",
      stage: "waiting_on_tool",
      message_id: "tool-msg-1",
      tool_name: "open_meteo_weather.forecast_weather",
      tool_call_id: "call-1",
      tool_run_id: "tool-run-1",
      tool_status: null,
      created_at: "2026-03-26T08:00:03Z",
    });
    expect(stream.turnEvents.value[0]).toMatchObject({
      event: "tool_started",
      detail: "open_meteo_weather.forecast_weather",
    });

    const completedPayload = buildTurnResponse({
      output_text: "Sunny and mild.",
      run: {
        status: "completed",
        stage: "completed",
        updated_at: "2026-03-26T08:00:05Z",
      },
    });
    await handlers?.onEvent("completed", completedPayload);

    expect(activeTurn.value).toEqual(completedPayload);
    expect(busy.value).toBe(false);
    expect(pendingApproval.value).toBeNull();
    expect(stream.streamState.value).toBe("closed");
    expect(source.close).toHaveBeenCalledTimes(1);
    expect(hydrateConversationAfterTurn).toHaveBeenCalledWith(
      "agent:assistant:deck-test",
    );
    expect(refreshConversations).not.toHaveBeenCalled();
    expect(lastError.value).toBeNull();
  });

  it("surfaces failed run reasons to the main error state", async () => {
    const source = { close: vi.fn() };
    let handlers:
      | {
          onEvent: (event: string, payload: unknown) => Promise<void> | void;
          onError?: (error: Event) => void;
        }
      | undefined;

    openTurnEventsMock.mockImplementation((_runId, options) => {
      handlers = options as typeof handlers;
      return source as unknown as EventSource;
    });

    const lastError = ref<string | null>(null);
    const stream = useTurnStream({
      messages: ref<SessionMessage[]>([]),
      activeTurn: ref<TurnResponse | null>(null),
      pendingApproval: ref<PendingApprovalRequestPayload | null>(null),
      activeSessionKey: ref<string | null>(null),
      busy: ref(true),
      lastError,
      activeConversation: ref(buildConversationSummary()),
      draftMainKey: ref("deck-test"),
      hydrateConversationAfterTurn: vi.fn().mockResolvedValue(undefined),
      refreshConversations: vi.fn().mockResolvedValue(undefined),
    });

    stream.watchTurn("run-vision-fail");

    await handlers?.onEvent(
      "failed",
      buildTurnResponse({
        run: {
          id: "run-vision-fail",
          status: "failed",
          stage: "failed",
          error: {
            message:
              "LLM profile 'openai_codex.gpt-5.4' does not support vision input.",
            code: "engine_failed",
            details: {},
          },
          metadata: {
            requested_llm_id: "openai_codex.gpt-5.4",
          },
        },
      }),
    );

    expect(lastError.value).toContain("does not support vision input");
    expect(lastError.value).toContain(
      "Switch openai_codex.gpt-5.4 to Auto or another vision-capable model.",
    );
  });

  it("refreshes the active thread after background maintenance completes", async () => {
    const source = { close: vi.fn() };
    let handlers:
      | {
          onEvent: (event: string, payload: unknown) => Promise<void> | void;
          onError?: (error: Event) => void;
        }
      | undefined;

    openTurnEventsMock.mockImplementation((_runId, options) => {
      handlers = options as typeof handlers;
      return source as unknown as EventSource;
    });
    getConversationMessagesMock.mockResolvedValue([
      buildSessionMessage({
        id: "archived-1",
        visibility: "archived",
      }),
      buildSessionMessage({
        id: "live-1",
        sequence_no: 2,
        content: "Fresh reply",
        content_payload: {
          blocks: [{ type: "text", text: "Fresh reply" }],
        },
      }),
    ]);

    const messages = ref<SessionMessage[]>([]);
    const refreshConversations = vi.fn().mockResolvedValue(undefined);
    const activeSessionKey = ref("agent:assistant:deck-test");

    const stream = useTurnStream({
      messages,
      activeTurn: ref<TurnResponse | null>(null),
      pendingApproval: ref<PendingApprovalRequestPayload | null>(null),
      activeSessionKey,
      busy: ref(false),
      lastError: ref<string | null>(null),
      activeConversation: ref(buildConversationSummary()),
      draftMainKey: ref("deck-test"),
      hydrateConversationAfterTurn: vi.fn().mockResolvedValue(undefined),
      refreshConversations,
    });

    stream.watchTurn("run-maint", { backgroundMaintenance: true });
    expect(stream.streamState.value).toBe("idle");

    await handlers?.onEvent(
      "completed",
      buildTurnResponse({
        run: {
          id: "run-maint",
          inbound_instruction: {
            source: "compaction",
            content: null,
            metadata: {},
          },
          status: "completed",
          stage: "completed",
        },
      }),
    );

    expect(source.close).toHaveBeenCalledTimes(1);
    expect(refreshConversations).toHaveBeenCalledTimes(1);
    expect(getConversationMessagesMock).toHaveBeenCalledWith(
      "agent:assistant:deck-test",
      { includeArchived: true },
    );
    expect(messages.value).toHaveLength(2);
    expect(messages.value[0]?.visibility).toBe("archived");
    expect(messages.value[1]?.content).toBe("Fresh reply");
  });
});
