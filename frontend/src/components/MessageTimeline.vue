<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import { useMarkdownRenderer } from "@/composables/useMarkdownRenderer";
import type {
  CompactionRequestSummary,
  ConversationSummary,
  RunFeedback,
  SessionMessage,
  TurnEventEntry,
  TurnResponse,
} from "@/types";

type TimelineItem =
  | { kind: "message"; at: string; sortOrder: number; id: string; message: SessionMessage }
  | { kind: "event"; at: string; sortOrder: number; id: string; event: TurnEventEntry }
  | {
      kind: "boundary";
      at: string;
      sortOrder: number;
      id: string;
      archivedCount: number;
    }
  | {
      kind: "compaction";
      at: string;
      sortOrder: number;
      id: string;
      request: CompactionRequestSummary;
    };

const props = defineProps<{
  messages: SessionMessage[];
  turnEvents: TurnEventEntry[];
  activeTurn: TurnResponse | null;
  compactionRequest: CompactionRequestSummary | null;
  conversation: ConversationSummary | null;
  loading: boolean;
  lastError: string | null;
  runFeedback: RunFeedback | null;
}>();

const stackRef = ref<HTMLElement | null>(null);
const copiedCompactionId = ref<string | null>(null);
const { renderMarkdown } = useMarkdownRenderer(
  computed(() => props.messages.length),
);
const visibleTurnEvents = computed(() =>
  props.turnEvents.filter(
    (entry) =>
      entry.event === "tool_started" ||
      entry.event === "failed" ||
      entry.event === "cancelled" ||
      entry.event === "timeout",
  ),
);

const archivedMessages = computed(() =>
  props.messages.filter((message) => message.visibility === "archived"),
);

const liveMessages = computed(() =>
  props.messages.filter((message) => message.visibility !== "archived"),
);

const timelineItems = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = [
    ...props.messages.map((message) => ({
      kind: "message" as const,
      at: message.created_at,
      sortOrder: 1,
      id: message.id,
      message,
    })),
  ];
  if (archivedMessages.value.length > 0 && liveMessages.value.length > 0) {
    items.push({
      kind: "boundary",
      at: liveMessages.value[0].created_at,
      sortOrder: 0,
      id: `boundary:${liveMessages.value[0].id}`,
      archivedCount: archivedMessages.value.length,
    });
  }
  items.push(
    ...visibleTurnEvents.value.map((event) => ({
      kind: "event" as const,
      at: event.at,
      sortOrder: 2,
      id: event.id,
      event,
    })),
  );
  const activeRun = props.activeTurn?.run;
  if (
    activeRun &&
    activeRun.inbound_instruction.source === "compaction" &&
    props.compactionRequest
  ) {
    items.push({
      kind: "compaction",
      at: activeRun.created_at,
      sortOrder: 2,
      id: `compaction:${activeRun.id}`,
      request: props.compactionRequest,
    });
  }
  const ordered = items.sort((left, right) => {
    const leftTime = new Date(left.at).getTime();
    const rightTime = new Date(right.at).getTime();
    if (leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    if (left.sortOrder !== right.sortOrder) {
      return left.sortOrder - right.sortOrder;
    }
    return left.id.localeCompare(right.id);
  });
  return ordered;
});

const latestTimelineItemId = computed(() => {
  const lastItem = timelineItems.value[timelineItems.value.length - 1];
  return lastItem?.id ?? null;
});

function isToolBlock(message: SessionMessage) {
  return message.role === "tool" || message.kind.includes("tool");
}

function isArchivedMessage(message: SessionMessage) {
  return message.visibility === "archived";
}

function isMaintenanceMessage(message: SessionMessage) {
  return message.metadata.maintenance_kind === "compaction_summary";
}

function archivedHistoryLabel(count: number) {
  return `Earlier history (${count} ${count === 1 ? "message" : "messages"})`;
}

function messageText(message: SessionMessage) {
  if (message.content && message.content.trim()) {
    return message.content;
  }
  const payloadText = message.content_payload.text;
  if (typeof payloadText === "string" && payloadText.trim()) {
    return payloadText;
  }
  return `\`\`\`json\n${JSON.stringify(message.content_payload, null, 2)}\n\`\`\``;
}

function blockTone(message: SessionMessage) {
  if (message.role === "user") {
    return "prompt";
  }
  if (message.role === "assistant") {
    return "response";
  }
  if (message.role === "tool" || message.kind.includes("tool")) {
    return "tool";
  }
  if (message.role === "system") {
    return "system";
  }
  return "signal";
}

function blockTitle(message: SessionMessage) {
  if (message.role === "user") {
    return "Prompt block";
  }
  if (message.role === "assistant") {
    return "Response block";
  }
  if (message.role === "tool" || message.kind.includes("tool")) {
    return "Tool result";
  }
  if (message.role === "system") {
    return "System note";
  }
  return message.kind;
}

function toolName(message: SessionMessage) {
  const metadataToolName = message.metadata.tool_name;
  if (typeof metadataToolName === "string" && metadataToolName.trim()) {
    return metadataToolName.trim();
  }
  const payloadToolName = message.content_payload.tool_name;
  if (typeof payloadToolName === "string" && payloadToolName.trim()) {
    return payloadToolName.trim();
  }
  return sourceLabel(message);
}

function toolStatus(message: SessionMessage) {
  const payloadStatus = message.content_payload.status;
  if (typeof payloadStatus === "string" && payloadStatus.trim()) {
    return payloadStatus.trim();
  }
  return "completed";
}

function hasToolError(message: SessionMessage) {
  return Boolean(message.content_payload.error);
}

function textPreview(value: string, maxLength = 140) {
  const collapsed = value.replace(/\s+/g, " ").trim();
  if (collapsed.length <= maxLength) {
    return collapsed;
  }
  return `${collapsed.slice(0, maxLength - 1).trimEnd()}…`;
}

function toolSummary(message: SessionMessage) {
  const payloadError = message.content_payload.error;
  if (payloadError && typeof payloadError === "object") {
    const maybeMessage = (payloadError as Record<string, unknown>).message;
    if (typeof maybeMessage === "string" && maybeMessage.trim()) {
      return textPreview(maybeMessage);
    }
  }

  const payloadOutput = message.content_payload.output;
  if (typeof payloadOutput === "string" && payloadOutput.trim()) {
    return textPreview(payloadOutput);
  }
  if (payloadOutput && typeof payloadOutput === "object") {
    const maybeText = (payloadOutput as Record<string, unknown>).text;
    if (typeof maybeText === "string" && maybeText.trim()) {
      return textPreview(maybeText);
    }
    return `Output payload with ${Object.keys(payloadOutput as Record<string, unknown>).length} field(s)`;
  }

  const text = messageText(message);
  if (text.trim()) {
    return textPreview(text.replace(/```[\s\S]*?```/g, "Code block"));
  }
  return "No output";
}

function sourceLabel(message: SessionMessage) {
  if (message.source_kind && message.source_id) {
    return `${message.source_kind}:${message.source_id}`;
  }
  if (message.source_kind) {
    return message.source_kind;
  }
  return message.kind;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function eventTitle(entry: TurnEventEntry) {
  if (entry.event === "tool_started") {
    return "Tool started";
  }
  if (entry.event === "tool_completed") {
    return "Tool completed";
  }
  if (entry.event === "completed") {
    return "Turn completed";
  }
  if (entry.event === "failed") {
    return "Turn failed";
  }
  if (entry.event === "cancelled") {
    return "Turn cancelled";
  }
  if (entry.event === "timeout") {
    return "Turn timed out";
  }
  return "Runtime update";
}

function eventBody(entry: TurnEventEntry) {
  if (entry.detail && entry.detail.trim()) {
    return entry.detail.trim();
  }
  return `${entry.status} / ${entry.stage}`;
}

function compactionBody(request: CompactionRequestSummary) {
  if (request.reason && request.reason.trim()) {
    return request.reason.trim();
  }
  return request.label;
}

async function copyCompactionSummary(id: string, summary: string) {
  try {
    await navigator.clipboard.writeText(summary);
    copiedCompactionId.value = id;
    window.setTimeout(() => {
      if (copiedCompactionId.value === id) {
        copiedCompactionId.value = null;
      }
    }, 1600);
  } catch {
    copiedCompactionId.value = null;
  }
}

async function scrollToLatest() {
  await nextTick();
  const element = stackRef.value;
  if (!element) {
    return;
  }
  element.scrollTo({
    top: element.scrollHeight,
    behavior: "auto",
  });
}

watch(
  () => props.conversation?.bulk_key ?? "__draft__",
  () => {
    void scrollToLatest();
  },
  { immediate: true },
);

watch(
  () => [timelineItems.value.length, latestTimelineItemId.value],
  () => {
    void scrollToLatest();
  },
);
</script>

<template>
  <section class="timeline shell">
    <div v-if="lastError" class="timeline__error">
      <strong>Turn failed</strong>
      <p>{{ lastError }}</p>
    </div>

    <div
      v-if="timelineItems.length === 0"
      class="timeline__empty"
    >
      <div v-if="loading" class="timeline__loading">
        <span class="loader"></span>
        <span>Loading messages...</span>
      </div>
      <template v-else>
        <p>The canvas is clear.</p>
        <span>Dispatch a prompt and the block stream will compose itself here.</span>
      </template>
    </div>

    <div v-else ref="stackRef" class="timeline__stack">
      <div
        v-if="runFeedback"
        class="timeline-live-card"
        :class="`timeline-live-card--${runFeedback.tone}`"
      >
        <div class="timeline-live-card__pulse" aria-hidden="true">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <div class="timeline-live-card__copy">
          <p class="timeline-live-card__eyebrow">Live turn</p>
          <strong>{{ runFeedback.label }}</strong>
          <p>{{ runFeedback.detail }}</p>
        </div>
      </div>

      <div class="timeline__rail">
        <template v-for="item in timelineItems" :key="item.id">
          <div v-if="item.kind === 'boundary'" class="timeline-boundary">
            <div class="timeline-boundary__line"></div>
            <div class="timeline-boundary__copy">
              <p class="timeline-boundary__eyebrow">Context boundary</p>
              <strong class="timeline-boundary__label">
                {{ archivedHistoryLabel(item.archivedCount) }}
              </strong>
              <p class="timeline-boundary__note">
                Same thread, older context archived out of future prompts.
              </p>
            </div>
          </div>
          <article
            v-else
            class="stream-block"
            :class="[
              item.kind === 'message'
                ? `stream-block--${blockTone(item.message)}`
                : 'stream-block--signal',
              item.kind === 'message' && isArchivedMessage(item.message)
                ? 'stream-block--archived'
                : null,
              item.kind === 'message' && isMaintenanceMessage(item.message)
                ? 'stream-block--maintenance'
                : null,
            ]"
          >
            <div class="stream-block__line"></div>
            <template v-if="item.kind === 'event'">
            <div class="stream-block__head">
              <div>
                <p class="stream-block__eyebrow">{{ eventTitle(item.event) }}</p>
                <strong>{{ eventBody(item.event) }}</strong>
              </div>
              <span>{{ formatTime(item.event.at) }}</span>
            </div>
          </template>
          <template v-else-if="item.kind === 'compaction'">
            <div class="stream-block__head">
              <div>
                <p class="stream-block__eyebrow">Compaction</p>
                <strong>{{ item.request.label }}</strong>
              </div>
              <span>{{ formatTime(item.at) }}</span>
            </div>
            <p class="stream-block__note">
              {{ compactionBody(item.request) }}
            </p>
            <ul
              v-if="item.request.details.length > 0"
              class="stream-block__detail-list"
            >
              <li v-for="detail in item.request.details" :key="detail">
                {{ detail }}
              </li>
            </ul>
            <details
              v-if="item.request.summaryFull"
              class="compaction-summary"
            >
              <summary class="compaction-summary__summary">
                {{ item.request.summaryPreview ?? "Summary preview" }}
              </summary>
              <div class="compaction-summary__toolbar">
                <button
                  class="ghost-button compaction-summary__copy"
                  type="button"
                  @click="copyCompactionSummary(item.id, item.request.summaryFull)"
                >
                  {{ copiedCompactionId === item.id ? "Copied" : "Copy summary" }}
                </button>
              </div>
              <p class="compaction-summary__body">
                {{ item.request.summaryFull }}
              </p>
            </details>
          </template>
          <template v-else-if="isMaintenanceMessage(item.message)">
            <div class="stream-block__head">
              <div>
                <p class="stream-block__eyebrow">Maintenance note</p>
                <strong>Context compacted for this same thread</strong>
              </div>
              <div class="stream-block__head-meta">
                <span class="stream-block__visibility">Prompt summary</span>
                <span>{{ formatTime(item.message.created_at) }}</span>
              </div>
            </div>
            <p class="stream-block__note">
              Older messages were archived out of future prompt context. This is not a
              new answer or a new session.
            </p>
            <div
              class="stream-block__content"
              v-html="renderMarkdown(messageText(item.message))"
            ></div>
          </template>
          <template v-else-if="isToolBlock(item.message)">
            <details class="tool-block" :open="hasToolError(item.message)">
              <summary class="tool-block__summary">
                <div class="stream-block__head">
                  <div>
                    <p class="stream-block__eyebrow">{{ blockTitle(item.message) }}</p>
                    <strong>{{ toolName(item.message) }}</strong>
                  </div>
                  <div class="stream-block__head-meta">
                    <span
                      v-if="isArchivedMessage(item.message)"
                      class="stream-block__visibility"
                    >
                      Archived from prompt
                    </span>
                    <span>{{ formatTime(item.message.created_at) }}</span>
                  </div>
                </div>
                <div class="tool-block__meta">
                  <span class="tool-block__status">{{ toolStatus(item.message) }}</span>
                  <span class="tool-block__source">{{ sourceLabel(item.message) }}</span>
                </div>
                <p class="tool-block__preview">{{ toolSummary(item.message) }}</p>
              </summary>
              <div
                class="stream-block__content"
                v-html="renderMarkdown(messageText(item.message))"
              ></div>
            </details>
          </template>
          <template v-else>
            <div class="stream-block__head">
              <div>
                <p class="stream-block__eyebrow">{{ blockTitle(item.message) }}</p>
                <strong>{{ sourceLabel(item.message) }}</strong>
              </div>
              <div class="stream-block__head-meta">
                <span
                  v-if="isArchivedMessage(item.message)"
                  class="stream-block__visibility"
                >
                  Archived from prompt
                </span>
                <span>{{ formatTime(item.message.created_at) }}</span>
              </div>
            </div>
            <div
              class="stream-block__content"
              v-html="renderMarkdown(messageText(item.message))"
            ></div>
          </template>
          </article>
        </template>
      </div>
    </div>
  </section>
</template>
