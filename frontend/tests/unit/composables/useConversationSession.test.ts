import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  SessionMessage,
  TurnEventName,
  TurnResponse,
  TurnSnapshotResponse,
} from "@/types";

import {
  buildConversationSummary,
  buildPendingApproval,
  buildSessionMessage,
  buildTurnResponse,
} from "../support/factories";

const cancelTurnMock = vi.fn();
const createTurnMock = vi.fn();
const getConversationMock = vi.fn();
const getConversationMessagesMock = vi.fn();
const getTurnMock = vi.fn();
const listConversationsMock = vi.fn();
const requestTurnCompactionMock = vi.fn();
const requestTurnMemoryFlushMock = vi.fn();
const resolveTurnApprovalMock = vi.fn();

vi.mock("@/lib/api", () => ({
  cancelTurn: (...args: unknown[]) => cancelTurnMock(...args),
  createTurn: (...args: unknown[]) => createTurnMock(...args),
  getConversation: (...args: unknown[]) => getConversationMock(...args),
  getConversationMessages: (...args: unknown[]) => getConversationMessagesMock(...args),
  getTurn: (...args: unknown[]) => getTurnMock(...args),
  listConversations: (...args: unknown[]) => listConversationsMock(...args),
  requestTurnCompaction: (...args: unknown[]) => requestTurnCompactionMock(...args),
  requestTurnMemoryFlush: (...args: unknown[]) => requestTurnMemoryFlushMock(...args),
  resolveTurnApproval: (...args: unknown[]) => resolveTurnApprovalMock(...args),
}));

import {
  type ConversationSessionStreamBridge,
  useConversationSession,
} from "@/composables/useConversationSession";

function buildBridge(): ConversationSessionStreamBridge & {
  pushEvent: ReturnType<typeof vi.fn>;
  closeTurnStream: ReturnType<typeof vi.fn>;
  syncPendingApprovalFromTurn: ReturnType<typeof vi.fn>;
  clearTurnEvents: ReturnType<typeof vi.fn>;
  setStreamState: ReturnType<typeof vi.fn>;
  watchTurn: ReturnType<typeof vi.fn>;
} {
  const pushEvent = vi.fn<
    (event: TurnEventName, payload: TurnResponse) => void
  >();
  const closeTurnStream = vi.fn<() => void>();
  const syncPendingApprovalFromTurn = vi.fn<
    (payload: TurnResponse | TurnSnapshotResponse) => void
  >();
  const clearTurnEvents = vi.fn<() => void>();
  const setStreamState = vi.fn<(state: "idle" | "streaming" | "closed") => void>();
  const watchTurn = vi.fn<
    (runId: string, options?: { backgroundMaintenance?: boolean }) => void
  >();

  return {
    pushEvent,
    closeTurnStream,
    syncPendingApprovalFromTurn,
    clearTurnEvents,
    setStreamState,
    watchTurn,
  };
}

describe("useConversationSession", () => {
  beforeEach(() => {
    cancelTurnMock.mockReset();
    createTurnMock.mockReset();
    getConversationMock.mockReset();
    getConversationMessagesMock.mockReset();
    getTurnMock.mockReset();
    listConversationsMock.mockReset();
    requestTurnCompactionMock.mockReset();
    requestTurnMemoryFlushMock.mockReset();
    resolveTurnApprovalMock.mockReset();
  });

  it("selects a conversation, refreshes side panels, and watches maintenance in background", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>(null);
    const selectedLlmId = ref<string | null>(null);
    const refreshMemoryPanel = vi.fn().mockResolvedValue(undefined);
    const refreshAgentHomeIfSafe = vi.fn().mockResolvedValue(undefined);
    const closeDeckIfCompact = vi.fn();

    const session = useConversationSession({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      refreshMemoryPanel,
      refreshAgentHomeIfSafe,
      closeDeckIfCompact,
    });
    const bridge = buildBridge();
    session.bindStream(bridge);

    const conversation = buildConversationSummary({
      runtime_binding: {
        agent_id: "assistant",
        llm_id: "openai.gpt-5.4",
      },
      display_run_id: "display-run",
      latest_run_id: "maintenance-run",
      latest_run_status: "running",
    });

    getConversationMock.mockResolvedValue(conversation);
    getConversationMessagesMock.mockResolvedValue([buildSessionMessage()]);
    getTurnMock.mockResolvedValue(
      buildTurnResponse({
        run: {
          id: "display-run",
          status: "completed",
          stage: "completed",
          completed_at: "2026-03-26T08:00:05Z",
        },
      }),
    );

    await session.selectConversation(conversation.bulk_key);

    expect(bridge.closeTurnStream).toHaveBeenCalledTimes(1);
    expect(bridge.clearTurnEvents).toHaveBeenCalledTimes(1);
    expect(getConversationMock).toHaveBeenCalledWith(conversation.bulk_key);
    expect(getConversationMessagesMock).toHaveBeenCalledWith(
      conversation.bulk_key,
      { includeArchived: true },
    );
    expect(session.activeConversation.value).toEqual(conversation);
    expect(session.messages.value).toEqual([buildSessionMessage()]);
    expect(session.activeBulkKey.value).toBe(conversation.bulk_key);
    expect(selectedAgentId.value).toBe("assistant");
    expect(selectedLlmId.value).toBe("openai.gpt-5.4");
    expect(refreshMemoryPanel).toHaveBeenCalledWith("assistant");
    expect(refreshAgentHomeIfSafe).toHaveBeenCalledTimes(1);
    expect(bridge.watchTurn).toHaveBeenCalledWith("maintenance-run", {
      backgroundMaintenance: true,
    });
    expect(closeDeckIfCompact).toHaveBeenCalledTimes(1);
  });

  it("creates a fresh conversation and resets session state", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>("assistant");
    const selectedLlmId = ref<string | null>("openai.gpt-5.4-mini");
    const refreshMemoryPanel = vi.fn().mockResolvedValue(undefined);
    const refreshAgentHomeIfSafe = vi.fn().mockResolvedValue(undefined);
    const closeDeckIfCompact = vi.fn();

    const session = useConversationSession({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      refreshMemoryPanel,
      refreshAgentHomeIfSafe,
      closeDeckIfCompact,
    });
    const bridge = buildBridge();
    session.bindStream(bridge);

    session.activeBulkKey.value = "conversation:main:crxzipple:default:deck-old";
    session.activeConversation.value = buildConversationSummary();
    session.messages.value = [buildSessionMessage()];
    session.activeTurn.value = buildTurnResponse();
    session.pendingApproval.value = buildPendingApproval();

    await session.createFreshConversation();

    expect(bridge.closeTurnStream).toHaveBeenCalledTimes(1);
    expect(bridge.clearTurnEvents).toHaveBeenCalledTimes(1);
    expect(session.activeBulkKey.value).toBeNull();
    expect(session.activeConversation.value).toBeNull();
    expect(session.messages.value).toEqual([]);
    expect(session.activeTurn.value).toBeNull();
    expect(session.pendingApproval.value).toBeNull();
    expect(session.draftRoute.value.agentId).toBe("assistant");
    expect(selectedLlmId.value).toBeNull();
    expect(refreshMemoryPanel).toHaveBeenCalledWith("assistant");
    expect(refreshAgentHomeIfSafe).toHaveBeenCalledTimes(1);
    expect(closeDeckIfCompact).toHaveBeenCalledTimes(1);
  });

  it("submits a turn with optimistic UI and starts watching the run", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>("assistant");
    const selectedLlmId = ref<string | null>("openai.gpt-5.4-mini");
    const refreshMemoryPanel = vi.fn().mockResolvedValue(undefined);
    const refreshAgentHomeIfSafe = vi.fn().mockResolvedValue(undefined);
    const closeDeckIfCompact = vi.fn();

    const session = useConversationSession({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      refreshMemoryPanel,
      refreshAgentHomeIfSafe,
      closeDeckIfCompact,
    });
    const bridge = buildBridge();
    session.bindStream(bridge);

    const createdPayload = buildTurnResponse({
      run: {
        id: "run-submitted",
        bulk_key: "conversation:main:crxzipple:default:deck-test",
      },
    });
    createTurnMock.mockResolvedValue(createdPayload);
    listConversationsMock.mockResolvedValue([
      buildConversationSummary({
        bulk_key: "conversation:main:crxzipple:default:deck-test",
      }),
    ]);

    const submitted = await session.submitTurn("  hello world  ");

    expect(submitted).toBe(true);
    expect(createTurnMock).toHaveBeenCalledWith(
      expect.objectContaining({
        content: "hello world",
        source: "web",
        agent_id: "assistant",
        llm_id: "openai.gpt-5.4-mini",
        channel: "crxzipple",
        chat_type: "direct",
        main_key: session.draftRoute.value.mainKey,
        direct_scope: "main",
      }),
    );
    expect(session.messages.value).toHaveLength(1);
    expect(session.messages.value[0]?.metadata.optimistic).toBe(true);
    expect(session.messages.value[0]?.content).toBe("hello world");
    expect(session.activeTurn.value).toEqual(createdPayload);
    expect(session.activeBulkKey.value).toBe("conversation:main:crxzipple:default:deck-test");
    expect(session.busy.value).toBe(true);
    expect(bridge.pushEvent).toHaveBeenCalledWith("snapshot", createdPayload);
    expect(bridge.syncPendingApprovalFromTurn).toHaveBeenCalledWith(createdPayload);
    expect(listConversationsMock).toHaveBeenCalledTimes(1);
    expect(bridge.watchTurn).toHaveBeenCalledWith("run-submitted");
  });

  it("resolves an active approval and syncs the returned turn state", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>("assistant");
    const selectedLlmId = ref<string | null>(null);

    const session = useConversationSession({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      refreshMemoryPanel: vi.fn().mockResolvedValue(undefined),
      refreshAgentHomeIfSafe: vi.fn().mockResolvedValue(undefined),
      closeDeckIfCompact: vi.fn(),
    });
    const bridge = buildBridge();
    session.bindStream(bridge);

    session.activeTurn.value = buildTurnResponse({
      run: {
        id: "run-approval",
        stage: "waiting_for_confirmation",
      },
    });
    session.pendingApproval.value = buildPendingApproval();

    const resolvedPayload = buildTurnResponse({
      run: {
        id: "run-approval",
        status: "running",
        stage: "running",
      },
    });
    resolveTurnApprovalMock.mockResolvedValue(resolvedPayload);

    await session.resolveActiveApproval("allow_once");

    expect(resolveTurnApprovalMock).toHaveBeenCalledWith(
      "run-approval",
      "req-1",
      "allow_once",
    );
    expect(session.activeTurn.value).toEqual(resolvedPayload);
    expect(bridge.syncPendingApprovalFromTurn).toHaveBeenCalledWith(
      resolvedPayload,
    );
  });
});
