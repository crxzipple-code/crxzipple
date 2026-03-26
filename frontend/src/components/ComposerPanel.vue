<script setup lang="ts">
import type {
  AgentProfileSummary,
  ContextMeter,
  LlmProfileSummary,
  PendingApprovalRequestPayload,
  RunFeedback,
} from "@/types";

defineProps<{
  modelValue: string;
  disabled: boolean;
  busy: boolean;
  canCompact: boolean;
  canMemoryFlush: boolean;
  compactionRunning: boolean;
  memoryFlushRunning: boolean;
  agents: AgentProfileSummary[];
  llms: LlmProfileSummary[];
  selectedAgentId: string | null;
  selectedLlmId: string | null;
  pendingApproval: PendingApprovalRequestPayload | null;
  pendingMemoryCandidateCount: number;
  contextMeter: ContextMeter | null;
  runFeedback: RunFeedback | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
  cancel: [];
  compact: [];
  memoryFlush: [];
  selectAgent: [agentId: string];
  selectLlm: [llmId: string | null];
  resolveApproval: [
    decision: "allow_once" | "allow_for_session" | "always_for_agent" | "deny",
  ];
}>();

function onKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.isComposing) {
    return;
  }

  if (event.metaKey || event.ctrlKey) {
    const target = event.target as HTMLTextAreaElement | null;
    if (target === null) {
      return;
    }
    event.preventDefault();
    const start = target.selectionStart ?? target.value.length;
    const end = target.selectionEnd ?? target.value.length;
    const nextValue = `${target.value.slice(0, start)}\n${target.value.slice(end)}`;
    emit("update:modelValue", nextValue);
    requestAnimationFrame(() => {
      target.selectionStart = start + 1;
      target.selectionEnd = start + 1;
    });
    return;
  }

  if (!event.shiftKey && !event.altKey) {
    event.preventDefault();
    emit("submit");
  }
}
</script>

<template>
  <section class="composer shell">
    <div class="composer__module">
      <div v-if="pendingApproval" class="composer__approval">
        <div class="composer__approval-copy">
          <strong>{{ pendingApproval.label }}</strong>
          <p>
            {{ pendingApproval.reason || "Additional access is required before the turn can continue." }}
          </p>
        </div>
        <div class="composer__approval-actions">
          <button
            class="ghost-button"
            type="button"
            @click="emit('resolveApproval', 'allow_once')"
          >
            <span>Once</span>
          </button>
          <button
            class="ghost-button"
            type="button"
            @click="emit('resolveApproval', 'allow_for_session')"
          >
            <span>Session</span>
          </button>
          <button
            class="ghost-button"
            type="button"
            @click="emit('resolveApproval', 'always_for_agent')"
          >
            <span>Always</span>
          </button>
          <button
            class="ghost-button ghost-button--warn"
            type="button"
            @click="emit('resolveApproval', 'deny')"
          >
            <span>Deny</span>
          </button>
        </div>
      </div>
      <div
        v-if="runFeedback"
        class="composer__status"
        :class="`composer__status--${runFeedback.tone}`"
      >
        <span class="composer__status-dot" aria-hidden="true"></span>
        <div class="composer__status-copy">
          <strong>{{ runFeedback.label }}</strong>
          <p>{{ runFeedback.detail }}</p>
        </div>
      </div>
      <textarea
        :value="modelValue"
        class="composer__input"
        :disabled="busy"
        rows="3"
        placeholder="Ask crxzipple to inspect, search, explain, or continue the thread..."
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        @keydown="onKeydown"
      ></textarea>

      <div class="composer__footer">
        <div class="composer__controls">
          <label class="composer__control">
            <select
              class="composer__select"
              :value="selectedAgentId ?? ''"
              @change="emit('selectAgent', ($event.target as HTMLSelectElement).value)"
              aria-label="Select agent"
            >
              <option
                v-for="agent in agents"
                :key="agent.id"
                :value="agent.id"
              >
                {{ agent.name || agent.id }}
              </option>
            </select>
          </label>

          <label class="composer__control">
            <select
              class="composer__select"
              :value="selectedLlmId ?? ''"
              @change="
                emit(
                  'selectLlm',
                  (($event.target as HTMLSelectElement).value || null) as string | null,
                )
              "
              aria-label="Select model"
            >
              <option value="">Agent default</option>
              <option
                v-for="llm in llms"
                :key="llm.id"
                :value="llm.id"
              >
                {{ llm.id }}
              </option>
            </select>
          </label>
        </div>
        <p
          class="composer__hint"
          :class="{ 'composer__hint--live': busy }"
        >
          {{
            busy
                ? "Running current turn..."
              : pendingMemoryCandidateCount > 0
                ? `${pendingMemoryCandidateCount} memory ${
                    pendingMemoryCandidateCount === 1 ? "item" : "items"
                  } in review queue`
                : "Enter to run"
          }}
        </p>
        <div class="composer__actions">
          <div
            v-if="contextMeter"
            class="composer__context-meter"
            :class="`composer__context-meter--${contextMeter.tone}`"
            :style="{
              '--context-meter-fill': `${contextMeter.percent ?? 0}%`,
            }"
            :title="contextMeter.tooltip"
            :aria-label="contextMeter.tooltip"
            tabindex="0"
            role="img"
          >
            <span class="composer__context-meter-ring" aria-hidden="true"></span>
            <span class="composer__context-meter-label">{{ contextMeter.label }}</span>
          </div>
          <button
            class="ghost-button ghost-button--compact composer__utility-button"
            type="button"
            :disabled="!canMemoryFlush"
            :title="
              memoryFlushRunning
                ? 'Durable memory flush in progress'
                : 'Flush durable memory'
            "
            @click="emit('memoryFlush')"
          >
            <span class="button-glyph button-glyph--flush" aria-hidden="true"></span>
            <span class="sr-only">
              {{ memoryFlushRunning ? "Durable memory flush in progress" : "Flush durable memory" }}
            </span>
          </button>
          <button
            class="ghost-button ghost-button--compact composer__utility-button"
            type="button"
            :disabled="!canCompact"
            :title="
              compactionRunning
                ? 'Context compaction in progress'
                : 'Compact this thread'
            "
            @click="emit('compact')"
          >
            <span class="button-glyph button-glyph--compact" aria-hidden="true"></span>
            <span class="sr-only">
              {{ compactionRunning ? "Context compaction in progress" : "Compact this thread" }}
            </span>
          </button>
          <button
            class="primary-button primary-button--icon composer__run-toggle"
            :class="{ 'composer__run-toggle--busy': busy }"
            type="button"
            :disabled="busy ? false : disabled"
            :title="busy ? 'Cancel current turn' : 'Run turn'"
            @click="busy ? emit('cancel') : emit('submit')"
          >
            <span
              class="button-glyph"
              :class="busy ? 'button-glyph--cancel' : 'button-glyph--run'"
              aria-hidden="true"
            ></span>
            <span class="sr-only">{{ busy ? "Cancel current turn" : "Run turn" }}</span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
