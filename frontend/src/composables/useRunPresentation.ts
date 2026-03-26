import { computed, type Ref } from "vue";

import { routePayload } from "@/lib/conversationRoute";
import type {
  CompactionRequestSummary,
  ContextBudgetSummary,
  ContextMeter,
  ConversationRoute,
  ConversationSummary,
  PendingApprovalRequestPayload,
  RunFeedback,
  TurnEventEntry,
  TurnResponse,
  TurnRun,
} from "@/types";

type ContextBadge = {
  label: string;
  detail: string;
  tone: "healthy" | "warn" | "critical" | "unknown";
};

function normalizeCompactionReason(reason: string | null) {
  if (!reason) {
    return null;
  }
  if (reason === "manual_compaction_from_ui") {
    return "Manual request from UI";
  }
  return reason.replace(/_/g, " ");
}

function formatCompactionBasis(basis: string) {
  switch (basis) {
    case "prompt_budget":
      return "Auto compaction · prompt budget";
    case "transcript_budget":
      return "Auto compaction · transcript budget";
    case "manual":
      return "Manual compaction";
    default:
      return "Compaction";
  }
}

function coerceInt(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatCompactTokens(value: number) {
  if (value >= 100_000) {
    return `${Math.round(value / 1000)}k`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  }
  return String(value);
}

function buildCompactionDetails(details: Record<string, unknown>) {
  const items: string[] = [];
  const estimatedTotalTokens = coerceInt(details.estimated_total_tokens);
  const promptThresholdTokens = coerceInt(details.prompt_threshold_tokens);
  const transcriptChars = coerceInt(details.transcript_chars);
  const transcriptCharThreshold = coerceInt(details.transcript_char_threshold);
  const transcriptTokens = coerceInt(details.transcript_estimated_tokens);
  const transcriptTokenThreshold = coerceInt(details.transcript_token_threshold);

  if (estimatedTotalTokens !== null && promptThresholdTokens !== null) {
    items.push(
      `Prompt estimate ${estimatedTotalTokens} / ${promptThresholdTokens} tokens`,
    );
  }
  if (transcriptChars !== null && transcriptCharThreshold !== null) {
    items.push(`Transcript ${transcriptChars} / ${transcriptCharThreshold} chars`);
  }
  if (transcriptTokens !== null && transcriptTokenThreshold !== null) {
    items.push(`Transcript ${transcriptTokens} / ${transcriptTokenThreshold} tokens`);
  }
  return items;
}

function buildCompactionSummaryPreview(summary: string) {
  const normalized = summary.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return null;
  }
  const sentences = normalized.split(/(?<=[.!?。！？])\s+/).filter(Boolean);
  if (sentences.length >= 2) {
    return `${sentences[0]} ${sentences[1]}`.trim();
  }
  if (normalized.length <= 220) {
    return normalized;
  }
  return `${normalized.slice(0, 217).trimEnd()}...`;
}

function readCompactionRequestSummary(run: TurnRun | null): CompactionRequestSummary | null {
  if (!run) {
    return null;
  }
  const raw = run.metadata.compaction_request;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const basis = String(record.basis ?? "manual");
  const details =
    record.details && typeof record.details === "object"
      ? buildCompactionDetails(record.details as Record<string, unknown>)
      : [];
  const rawResult = run.metadata.compaction_result;
  let summaryFull: string | null = null;
  if (rawResult && typeof rawResult === "object") {
    const result = rawResult as Record<string, unknown>;
    const archivedMessageCount = coerceInt(result.archived_message_count);
    if (archivedMessageCount !== null) {
      details.unshift(`Archived ${archivedMessageCount} messages`);
    }
    if (typeof result.summary === "string" && result.summary.trim()) {
      summaryFull = result.summary.trim();
    }
  }
  return {
    basis,
    label: formatCompactionBasis(basis),
    reason: normalizeCompactionReason(
      record.reason === null || record.reason === undefined
        ? null
        : String(record.reason),
    ),
    details,
    summaryPreview: summaryFull ? buildCompactionSummaryPreview(summaryFull) : null,
    summaryFull,
  };
}

function isTerminalRunStatus(status: string | null | undefined) {
  return status === "completed" ||
    status === "failed" ||
    status === "cancelled" ||
    status === "timed_out";
}

export function useRunPresentation(options: {
  activeConversation: Ref<ConversationSummary | null>;
  activeTurn: Ref<TurnResponse | null>;
  pendingApproval: Ref<PendingApprovalRequestPayload | null>;
  turnEvents: Ref<TurnEventEntry[]>;
  streamState: Ref<string>;
  busy: Ref<boolean>;
  loadingMessages: Ref<boolean>;
  currentRunId: Ref<string | null>;
  activeRoute: Ref<ConversationRoute>;
  composer: Ref<string>;
}) {
  const activeTitle = computed(() => {
    if (options.activeConversation.value?.title) {
      return options.activeConversation.value.title;
    }
    return "New thread";
  });

  const activeCompactionRequest = computed(() =>
    readCompactionRequestSummary(options.activeTurn.value?.run ?? null),
  );

  const activeContextBudget = computed<ContextBudgetSummary | null>(() => {
    const promptReport = options.activeTurn.value?.run.metadata.prompt_report;
    if (!promptReport || typeof promptReport !== "object") {
      return null;
    }
    const record = promptReport as Record<string, unknown>;
    const systemBudget =
      record.system_budget && typeof record.system_budget === "object"
        ? (record.system_budget as Record<string, unknown>)
        : null;
    const system =
      record.system && typeof record.system === "object"
        ? (record.system as Record<string, unknown>)
        : null;
    const transcript =
      record.transcript && typeof record.transcript === "object"
        ? (record.transcript as Record<string, unknown>)
        : null;

    const estimatedTotalTokens = coerceInt(record.estimated_total_tokens);
    const systemBudgetTokens = systemBudget
      ? coerceInt(systemBudget.max_estimated_tokens)
      : null;
    const contextWindowTokens = systemBudget
      ? coerceInt(systemBudget.llm_context_window_tokens)
      : null;
    const remainingTokens =
      estimatedTotalTokens !== null && contextWindowTokens !== null
        ? Math.max(contextWindowTokens - estimatedTotalTokens, 0)
        : null;
    const usagePercent =
      estimatedTotalTokens !== null &&
        contextWindowTokens !== null &&
        contextWindowTokens > 0
        ? Math.min((estimatedTotalTokens / contextWindowTokens) * 100, 100)
        : null;

    return {
      estimatedTotalTokens,
      contextWindowTokens,
      remainingTokens,
      usagePercent,
      systemTokens: system ? coerceInt(system.estimated_tokens) : null,
      systemBudgetTokens,
      transcriptTokens: transcript ? coerceInt(transcript.estimated_tokens) : null,
      budgetSource:
        systemBudget && typeof systemBudget.source === "string"
          ? systemBudget.source
          : null,
    };
  });

  const activeContextBadge = computed<ContextBadge | null>(() => {
    const budget = activeContextBudget.value;
    if (!budget) {
      return null;
    }
    if (
      budget.remainingTokens !== null &&
      budget.contextWindowTokens !== null &&
      budget.usagePercent !== null
    ) {
      const tone =
        budget.usagePercent >= 90
          ? "critical"
          : budget.usagePercent >= 75
            ? "warn"
            : "healthy";
      return {
        label: `${formatCompactTokens(budget.remainingTokens)} tok left`,
        detail: `${Math.round(budget.usagePercent)}% of ${formatCompactTokens(
          budget.contextWindowTokens,
        )} tok window used`,
        tone,
      };
    }
    if (
      budget.estimatedTotalTokens !== null &&
      budget.systemBudgetTokens !== null
    ) {
      return {
        label: `${formatCompactTokens(budget.estimatedTotalTokens)} tok in prompt`,
        detail: `Context window unavailable; tracked system budget cap ${formatCompactTokens(
          budget.systemBudgetTokens,
        )} tok`,
        tone: "unknown",
      };
    }
    return null;
  });

  const activeContextMeter = computed<ContextMeter | null>(() => {
    const budget = activeContextBudget.value;
    if (!budget) {
      return null;
    }
    if (
      budget.remainingTokens !== null &&
      budget.contextWindowTokens !== null &&
      budget.usagePercent !== null
    ) {
      const percent = Math.round(budget.usagePercent);
      return {
        percent,
        label: `${percent}%`,
        tone:
          budget.usagePercent >= 90
            ? "critical"
            : budget.usagePercent >= 75
              ? "warn"
              : "healthy",
        tooltip: `${formatCompactTokens(budget.remainingTokens)} tok left · ${percent}% of ${formatCompactTokens(
          budget.contextWindowTokens,
        )} tok window used`,
      };
    }
    if (
      budget.estimatedTotalTokens !== null &&
      budget.systemBudgetTokens !== null
    ) {
      return {
        percent: null,
        label: "?",
        tone: "unknown",
        tooltip: `${formatCompactTokens(
          budget.estimatedTotalTokens,
        )} tok estimated in prompt · Model context window not configured · System prompt budget cap ${formatCompactTokens(
          budget.systemBudgetTokens,
        )} tok`,
      };
    }
    return null;
  });

  const topbarStatusNote = computed(() => {
    const compaction = activeCompactionRequest.value;
    if (!compaction) {
      return null;
    }
    const detail = compaction.details[0];
    return detail ? `${compaction.label} · ${detail}` : compaction.label;
  });

  const activeRunFeedback = computed<RunFeedback | null>(() => {
    const run = options.activeTurn.value?.run;
    const latestToolEvent = options.turnEvents.value.find(
      (entry) => entry.event === "tool_started",
    );

    if (
      options.pendingApproval.value ||
      run?.stage === "waiting_for_confirmation"
    ) {
      return {
        label: "Waiting for approval",
        detail:
          options.pendingApproval.value?.label ??
          "This turn is paused until you approve or deny the requested action.",
        tone: "approval",
      };
    }

    if (!run || isTerminalRunStatus(run.status)) {
      return null;
    }

    if (run.inbound_instruction.source === "compaction") {
      return {
        label: "Compacting context",
        detail: "Rolling older messages into a summary while keeping this thread active.",
        tone: "live",
      };
    }

    if (run.inbound_instruction.source === "memory_flush") {
      return {
        label: "Flushing durable memory",
        detail: "Writing long-term notes from this thread without changing the session.",
        tone: "live",
      };
    }

    if (run.inbound_instruction.source === "heartbeat") {
      return {
        label: "Running heartbeat",
        detail: "Checking whether this thread needs a lightweight follow-up step.",
        tone: "live",
      };
    }

    if (run.stage === "queued" || run.status === "queued") {
      return {
        label: "Queued",
        detail: "This turn is lined up and about to start.",
        tone: "live",
      };
    }

    if (run.stage === "waiting_on_tool") {
      return {
        label: "Waiting on tool",
        detail:
          latestToolEvent?.detail ??
          "A tool is still running, and the turn will continue as soon as it finishes.",
        tone: "tool",
      };
    }

    if (latestToolEvent) {
      return {
        label: "Running tool",
        detail: latestToolEvent.detail ?? "A tool is working on the next step.",
        tone: "tool",
      };
    }

    if (options.streamState.value === "streaming") {
      return {
        label: "Generating response",
        detail: "The model is actively thinking and streaming the next reply.",
        tone: "live",
      };
    }

    return {
      label: "Working",
      detail: "This turn is still in progress.",
      tone: "live",
    };
  });

  const compactionRunning = computed(() => {
    const run = options.activeTurn.value?.run;
    if (!run) {
      return false;
    }
    const promptMode = run.metadata.prompt_mode;
    return (
      typeof promptMode === "string" &&
      promptMode === "compaction" &&
      !isTerminalRunStatus(run.status)
    );
  });

  const memoryFlushRunning = computed(() => {
    const run = options.activeTurn.value?.run;
    if (!run) {
      return false;
    }
    const promptMode = run.metadata.prompt_mode;
    return (
      typeof promptMode === "string" &&
      promptMode === "memory_flush" &&
      !isTerminalRunStatus(run.status)
    );
  });

  const canCompact = computed(
    () =>
      !options.busy.value &&
      !options.loadingMessages.value &&
      Boolean(options.activeConversation.value) &&
      Boolean(options.currentRunId.value),
  );

  const canMemoryFlush = computed(
    () =>
      !options.busy.value &&
      !options.loadingMessages.value &&
      Boolean(options.activeConversation.value) &&
      Boolean(options.currentRunId.value),
  );

  const canSubmit = computed(
    () => options.composer.value.trim().length > 0 && !options.busy.value,
  );

  const inspectorPayload = computed(() =>
    JSON.stringify(routePayload(options.activeRoute.value), null, 2),
  );

  const outputPreview = computed(() => {
    const text = options.activeTurn.value?.output_text?.trim();
    if (!text) {
      return null;
    }
    if (text.length <= 260) {
      return text;
    }
    return `${text.slice(0, 257)}...`;
  });

  return {
    activeTitle,
    activeCompactionRequest,
    activeContextBudget,
    activeContextBadge,
    activeContextMeter,
    topbarStatusNote,
    activeRunFeedback,
    compactionRunning,
    memoryFlushRunning,
    canCompact,
    canMemoryFlush,
    canSubmit,
    inspectorPayload,
    outputPreview,
  };
}
