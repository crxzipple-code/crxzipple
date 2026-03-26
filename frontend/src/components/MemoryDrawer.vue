<script setup lang="ts">
import type { MemoryCandidate, MemoryEntry } from "@/types";

defineProps<{
  open: boolean;
  loading: boolean;
  currentThreadMemoryCandidates: MemoryCandidate[];
  otherMemoryCandidates: MemoryCandidate[];
  entries: MemoryEntry[];
  query: string;
  formatTime: (value: string | null) => string;
}>();

const emit = defineEmits<{
  close: [];
  approveMemoryCandidate: [candidateId: string];
  rejectMemoryCandidate: [candidateId: string];
  "update:query": [value: string];
  refresh: [];
}>();
</script>

<template>
  <aside class="memory-drawer" :class="{ 'memory-drawer--open': open }">
    <div class="memory-panel shell">
      <div class="memory-panel__header">
        <div>
          <p class="eyebrow">memory</p>
          <h3>Memory log</h3>
        </div>
        <button
          class="ghost-button ghost-button--compact panel-tool-button panel-tool-button--icon memory-panel__close"
          type="button"
          title="Close memory panel"
          @click="$emit('close')"
        >
          <span class="button-glyph button-glyph--collapse" aria-hidden="true"></span>
          <span class="sr-only">Collapse</span>
        </button>
      </div>

      <div class="memory-panel__section">
        <div class="memory-panel__toolbar">
          <input
            :value="query"
            class="memory-panel__search"
            type="search"
            placeholder="Search memory log"
            @input="
              $emit(
                'update:query',
                ($event.target as HTMLInputElement).value,
              )
            "
          />
          <button
            class="ghost-button ghost-button--compact panel-tool-button memory-panel__refresh"
            type="button"
            title="Refresh memory"
            @click="$emit('refresh')"
          >
            <span class="button-glyph button-glyph--reload" aria-hidden="true"></span>
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <div class="memory-panel__section">
        <p class="eyebrow">review queue</p>
        <div
          v-if="
            currentThreadMemoryCandidates.length === 0 &&
            otherMemoryCandidates.length === 0
          "
          class="event-feed__empty"
        >
          Captured memories will appear here so you can keep or forget them later.
        </div>
        <div v-else class="memory-inbox">
          <section
            v-if="currentThreadMemoryCandidates.length > 0"
            class="memory-inbox__section"
          >
            <p class="memory-inbox__label">Current thread</p>
            <article
              v-for="candidate in currentThreadMemoryCandidates"
              :key="candidate.id"
              class="memory-card"
            >
              <div class="memory-card__copy">
                <strong>{{ candidate.title }}</strong>
                <p>
                  {{
                    candidate.summary ||
                    "A captured memory from this thread is ready for review."
                  }}
                </p>
                <div class="memory-card__meta">
                  <span v-if="candidate.tags.length > 0">
                    {{ candidate.tags.join(" · ") }}
                  </span>
                  <time>{{ formatTime(candidate.created_at) }}</time>
                </div>
              </div>
              <div class="memory-card__actions">
                <button
                  class="ghost-button ghost-button--compact memory-card__action memory-card__action--approve"
                  type="button"
                  @click="$emit('approveMemoryCandidate', candidate.id)"
                >
                  <span class="button-glyph button-glyph--save" aria-hidden="true"></span>
                  <span>Keep</span>
                </button>
                <button
                  class="ghost-button ghost-button--compact memory-card__action memory-card__action--reject"
                  type="button"
                  @click="$emit('rejectMemoryCandidate', candidate.id)"
                >
                  <span class="button-glyph button-glyph--cancel" aria-hidden="true"></span>
                  <span>Forget</span>
                </button>
              </div>
            </article>
          </section>

          <section
            v-if="otherMemoryCandidates.length > 0"
            class="memory-inbox__section"
          >
            <p class="memory-inbox__label">Other threads</p>
            <article
              v-for="candidate in otherMemoryCandidates"
              :key="candidate.id"
              class="memory-card"
            >
              <div class="memory-card__copy">
                <strong>{{ candidate.title }}</strong>
                <p>
                  {{
                    candidate.summary ||
                    "A captured memory from another thread is ready for review."
                  }}
                </p>
                <div class="memory-card__meta">
                  <span v-if="candidate.session_key">{{ candidate.session_key }}</span>
                  <span v-if="candidate.tags.length > 0">
                    {{ candidate.tags.join(" · ") }}
                  </span>
                  <time>{{ formatTime(candidate.created_at) }}</time>
                </div>
              </div>
              <div class="memory-card__actions">
                <button
                  class="ghost-button ghost-button--compact memory-card__action memory-card__action--approve"
                  type="button"
                  @click="$emit('approveMemoryCandidate', candidate.id)"
                >
                  <span class="button-glyph button-glyph--save" aria-hidden="true"></span>
                  <span>Keep</span>
                </button>
                <button
                  class="ghost-button ghost-button--compact memory-card__action memory-card__action--reject"
                  type="button"
                  @click="$emit('rejectMemoryCandidate', candidate.id)"
                >
                  <span class="button-glyph button-glyph--cancel" aria-hidden="true"></span>
                  <span>Forget</span>
                </button>
              </div>
            </article>
          </section>
        </div>
      </div>

      <div class="memory-panel__section">
        <p class="eyebrow">captured memory</p>
        <div v-if="loading" class="event-feed__empty">
          Loading memory...
        </div>
        <div v-else-if="entries.length === 0" class="event-feed__empty">
          Captured memory entries will appear here.
        </div>
        <div v-else class="memory-log">
          <article v-for="entry in entries" :key="entry.id" class="memory-log__entry">
            <div class="memory-log__head">
              <strong>{{ entry.title }}</strong>
              <time>{{ formatTime(entry.updated_at) }}</time>
            </div>
            <p>{{ entry.summary || entry.content }}</p>
            <div v-if="entry.tags.length > 0" class="memory-log__meta">
              {{ entry.tags.join(" · ") }}
            </div>
          </article>
        </div>
      </div>
    </div>
  </aside>
</template>
