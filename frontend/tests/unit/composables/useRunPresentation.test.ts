import { ref } from "vue";
import { describe, expect, it } from "vitest";

import { useRunPresentation } from "@/composables/useRunPresentation";
import type { PendingApprovalRequestPayload, TurnEventEntry } from "@/types";

import {
  buildConversationRoute,
  buildConversationSummary,
  buildPendingApproval,
  buildTurnResponse,
} from "../support/factories";

describe("useRunPresentation", () => {
  it("builds compaction summary and topbar state from run metadata", () => {
    const activeConversation = ref(buildConversationSummary());
    const activeTurn = ref(
      buildTurnResponse({
        run: {
          inbound_instruction: {
            source: "compaction",
            content: null,
            metadata: {},
          },
          metadata: {
            compaction_request: {
              basis: "prompt_budget",
              reason: "manual_compaction_from_ui",
              details: {
                estimated_total_tokens: 9700,
                prompt_threshold_tokens: 9500,
              },
            },
            compaction_result: {
              archived_message_count: 18,
              summary: "First sentence. Second sentence. Third sentence.",
            },
          },
        },
      }),
    );

    const presentation = useRunPresentation({
      activeConversation,
      activeTurn,
      pendingApproval: ref<PendingApprovalRequestPayload | null>(null),
      turnEvents: ref<TurnEventEntry[]>([]),
      streamState: ref("idle"),
      busy: ref(false),
      loadingMessages: ref(false),
      currentRunId: ref("run-1"),
      activeRoute: ref(buildConversationRoute()),
      composer: ref(""),
    });

    expect(presentation.activeTitle.value).toBe("Travel planning");
    expect(presentation.activeCompactionRequest.value).toEqual({
      basis: "prompt_budget",
      label: "Auto compaction · prompt budget",
      reason: "Manual request from UI",
      details: [
        "Archived 18 messages",
        "Prompt estimate 9700 / 9500 tokens",
      ],
      summaryPreview: "First sentence. Second sentence.",
      summaryFull: "First sentence. Second sentence. Third sentence.",
    });
    expect(presentation.topbarStatusNote.value).toBe(
      "Auto compaction · prompt budget · Archived 18 messages",
    );
    expect(presentation.activeRunFeedback.value).toEqual({
      label: "Compacting context",
      detail:
        "Rolling older messages into a summary while keeping this thread active.",
      tone: "live",
    });
  });

  it("derives context budget badges and submission affordances", () => {
    const activeTurn = ref(
      buildTurnResponse({
        output_text: "A very long answer that should preview cleanly.",
        run: {
          metadata: {
            prompt_report: {
              estimated_total_tokens: 6000,
              system_budget: {
                max_estimated_tokens: 1500,
                llm_context_window_tokens: 10000,
                source: "context_window_scaled",
              },
              system: {
                estimated_tokens: 240,
              },
              transcript: {
                estimated_tokens: 5760,
              },
            },
          },
        },
      }),
    );

    const busy = ref(false);
    const presentation = useRunPresentation({
      activeConversation: ref(buildConversationSummary()),
      activeTurn,
      pendingApproval: ref<PendingApprovalRequestPayload | null>(null),
      turnEvents: ref<TurnEventEntry[]>([]),
      streamState: ref("idle"),
      busy,
      loadingMessages: ref(false),
      currentRunId: ref("run-1"),
      activeRoute: ref(buildConversationRoute()),
      composer: ref("hello"),
    });

    expect(presentation.activeContextBudget.value).toEqual({
      estimatedTotalTokens: 6000,
      contextWindowTokens: 10000,
      remainingTokens: 4000,
      usagePercent: 60,
      systemTokens: 240,
      systemBudgetTokens: 1500,
      transcriptTokens: 5760,
      budgetSource: "context_window_scaled",
    });
    expect(presentation.activeContextBadge.value).toEqual({
      label: "4k tok left",
      detail: "60% of 10k tok window used",
      tone: "healthy",
    });
    expect(presentation.canCompact.value).toBe(true);
    expect(presentation.canMemoryFlush.value).toBe(true);
    expect(presentation.canSubmit.value).toBe(true);
    expect(presentation.inspectorPayload.value).toContain('"agent_id": "assistant"');
    expect(presentation.outputPreview.value).toBe(
      "A very long answer that should preview cleanly.",
    );

    busy.value = true;
    expect(presentation.canCompact.value).toBe(false);
    expect(presentation.canMemoryFlush.value).toBe(false);
    expect(presentation.canSubmit.value).toBe(false);
  });

  it("prioritizes approval feedback over active tool or stream activity", () => {
    const pendingApproval = ref<PendingApprovalRequestPayload | null>(
      buildPendingApproval({
        reason: "Needed to call the live forecast tool.",
      }),
    );
    const activeTurn = ref(buildTurnResponse());
    const turnEvents = ref<TurnEventEntry[]>([
      {
        id: "tool-started-1",
        event: "tool_started",
        status: "running",
        stage: "waiting_on_tool",
        at: "2026-03-26T08:00:02Z",
        detail: "open_meteo_weather.forecast_weather",
      },
    ]);

    const presentation = useRunPresentation({
      activeConversation: ref(buildConversationSummary()),
      activeTurn,
      pendingApproval,
      turnEvents,
      streamState: ref("streaming"),
      busy: ref(true),
      loadingMessages: ref(false),
      currentRunId: ref("run-1"),
      activeRoute: ref(buildConversationRoute()),
      composer: ref("weather?"),
    });

    expect(presentation.activeRunFeedback.value).toEqual({
      label: "Waiting for approval",
      detail: "Weather data access",
      tone: "approval",
    });
  });
});
