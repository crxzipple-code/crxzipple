<script setup lang="ts">
import type { TurnEventEntry, TurnResponse } from "@/types";

defineProps<{
  open: boolean;
  activeTurn: TurnResponse | null;
  turnEvents: TurnEventEntry[];
  payload: string;
  outputPreview: string | null;
  lastError: string | null;
  streamState: string;
  formatTime: (value: string | null) => string;
}>();

defineEmits<{
  close: [];
}>();
</script>

<template>
  <aside class="inspector-drawer" :class="{ 'inspector-drawer--open': open }">
    <div class="inspector shell">
      <div class="inspector__header">
        <div>
          <p class="eyebrow">runtime lens</p>
          <h3>Turn telemetry</h3>
        </div>
        <button class="ghost-button" type="button" @click="$emit('close')">
          <span class="button-glyph button-glyph--collapse" aria-hidden="true"></span>
          <span class="sr-only">Collapse</span>
        </button>
      </div>

      <div class="inspector__section">
        <dl class="stat-grid">
          <div>
            <dt>Status</dt>
            <dd>{{ activeTurn?.run.status ?? "idle" }}</dd>
          </div>
          <div>
            <dt>Stage</dt>
            <dd>{{ activeTurn?.run.stage ?? "n/a" }}</dd>
          </div>
          <div>
            <dt>Worker</dt>
            <dd>{{ activeTurn?.run.worker_id ?? "n/a" }}</dd>
          </div>
          <div>
            <dt>Stream</dt>
            <dd>{{ streamState }}</dd>
          </div>
          <div>
            <dt>Started</dt>
            <dd>{{ formatTime(activeTurn?.run.started_at ?? null) }}</dd>
          </div>
          <div>
            <dt>Finished</dt>
            <dd>{{ formatTime(activeTurn?.run.completed_at ?? null) }}</dd>
          </div>
        </dl>
      </div>

      <div class="inspector__section">
        <p class="eyebrow">route payload</p>
        <pre class="inspector__code">{{ payload }}</pre>
      </div>

      <div v-if="outputPreview" class="inspector__section">
        <p class="eyebrow">response excerpt</p>
        <p class="inspector__summary">{{ outputPreview }}</p>
      </div>

      <div class="inspector__section">
        <p class="eyebrow">event feed</p>
        <div v-if="turnEvents.length === 0" class="event-feed__empty">
          The runtime trace will settle here after a turn is dispatched.
        </div>
        <div v-else class="event-feed">
          <article v-for="entry in turnEvents" :key="entry.id" class="event-row">
            <div>
              <strong>{{ entry.event }}</strong>
              <span v-if="entry.detail">{{ entry.detail }}</span>
              <span>{{ entry.status }} / {{ entry.stage }}</span>
            </div>
            <time>{{ formatTime(entry.at) }}</time>
          </article>
        </div>
      </div>

      <div v-if="lastError" class="inspector__error">
        <strong>error</strong>
        <p>{{ lastError }}</p>
      </div>
    </div>
  </aside>
</template>
