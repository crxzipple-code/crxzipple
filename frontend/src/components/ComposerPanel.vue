<script setup lang="ts">
import type { AgentProfileSummary, LlmProfileSummary } from "@/types";

defineProps<{
  modelValue: string;
  disabled: boolean;
  busy: boolean;
  agents: AgentProfileSummary[];
  llms: LlmProfileSummary[];
  selectedAgentId: string | null;
  selectedLlmId: string | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
  cancel: [];
  selectAgent: [agentId: string];
  selectLlm: [llmId: string | null];
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
        <p class="composer__hint">
          {{ busy ? "Running current turn..." : "Enter to run" }}
        </p>
        <div class="composer__actions">
          <button
            v-if="busy"
            class="ghost-button ghost-button--warn"
            type="button"
            @click="emit('cancel')"
          >
            <span class="button-glyph button-glyph--cancel" aria-hidden="true"></span>
            <span>Cancel</span>
          </button>
          <button
            class="primary-button"
            type="button"
            :disabled="disabled"
            @click="emit('submit')"
          >
            <span class="button-glyph button-glyph--run" aria-hidden="true"></span>
            <span>{{ busy ? "Running..." : "Run" }}</span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
