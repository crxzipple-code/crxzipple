<script setup lang="ts">
import { ref } from "vue";

import type {
  CompactionRequestSummary,
  ContextBudgetSummary,
  TurnEventEntry,
  TurnResponse,
} from "@/types";

defineProps<{
  open: boolean;
  activeTurn: TurnResponse | null;
  compactionRequest: CompactionRequestSummary | null;
  turnEvents: TurnEventEntry[];
  payload: string;
  outputPreview: string | null;
  lastError: string | null;
  streamState: string;
  contextBudget: ContextBudgetSummary | null;
  formatTime: (value: string | null) => string;
}>();

defineEmits<{
  close: [];
}>();

const copiedSummary = ref(false);

async function copyCompactionSummary(summary: string) {
  try {
    await navigator.clipboard.writeText(summary);
    copiedSummary.value = true;
    window.setTimeout(() => {
      copiedSummary.value = false;
    }, 1600);
  } catch {
    copiedSummary.value = false;
  }
}
</script>

<template>
  <aside class="inspector-drawer" :class="{ 'inspector-drawer--open': open }">
    <div class="inspector shell">
      <div class="inspector__header">
        <div>
          <p class="eyebrow">runtime lens</p>
          <h3>Turn telemetry</h3>
        </div>
        <button
          class="ghost-button ghost-button--compact panel-tool-button panel-tool-button--icon inspector__close"
          type="button"
          title="Close inspector"
          @click="$emit('close')"
        >
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
        <pre class="inspector__code inspector__code--log">{{ payload }}</pre>
      </div>

      <div v-if="outputPreview" class="inspector__section">
        <p class="eyebrow">response excerpt</p>
        <p class="inspector__summary">{{ outputPreview }}</p>
      </div>

      <div v-if="contextBudget" class="inspector__section">
        <p class="eyebrow">remaining context</p>
        <div
          v-if="contextBudget.usagePercent !== null"
          class="budget-meter"
        >
          <div class="budget-meter__track">
            <div
              class="budget-meter__fill"
              :style="{ width: `${contextBudget.usagePercent}%` }"
            ></div>
          </div>
          <span class="budget-meter__label">
            {{ Math.round(contextBudget.usagePercent) }}% used
          </span>
        </div>
        <dl class="stat-grid">
          <div>
            <dt>Used</dt>
            <dd>
              {{
                contextBudget.estimatedTotalTokens !== null
                  ? `${contextBudget.estimatedTotalTokens} tok`
                  : "n/a"
              }}
            </dd>
          </div>
          <div>
            <dt>Remaining</dt>
            <dd>
              {{
                contextBudget.remainingTokens !== null
                  ? `${contextBudget.remainingTokens} tok`
                  : "unknown"
              }}
            </dd>
          </div>
          <div>
            <dt>Window</dt>
            <dd>
              {{
                contextBudget.contextWindowTokens !== null
                  ? `${contextBudget.contextWindowTokens} tok`
                  : "unknown"
              }}
            </dd>
          </div>
          <div>
            <dt>Budget source</dt>
            <dd>{{ contextBudget.budgetSource ?? "unknown" }}</dd>
          </div>
          <div>
            <dt>System budget</dt>
            <dd>
              {{
                contextBudget.systemBudgetTokens !== null
                  ? `${contextBudget.systemBudgetTokens} tok`
                  : "n/a"
              }}
            </dd>
          </div>
          <div>
            <dt>System</dt>
            <dd>
              {{
                contextBudget.systemTokens !== null
                  ? `${contextBudget.systemTokens} tok`
                  : "n/a"
              }}
            </dd>
          </div>
          <div>
            <dt>Transcript</dt>
            <dd>
              {{
                contextBudget.transcriptTokens !== null
                  ? `${contextBudget.transcriptTokens} tok`
                  : "n/a"
              }}
            </dd>
          </div>
        </dl>
        <p class="inspector__note">
          Estimated from the current prompt report. Real provider-side usage can be a little higher.
        </p>
      </div>

      <div v-if="compactionRequest" class="inspector__section">
        <p class="eyebrow">compaction trigger</p>
        <dl class="stat-grid stat-grid--single">
          <div>
            <dt>Basis</dt>
            <dd>{{ compactionRequest.label }}</dd>
          </div>
          <div v-if="compactionRequest.reason">
            <dt>Reason</dt>
            <dd>{{ compactionRequest.reason }}</dd>
          </div>
        </dl>
        <ul
          v-if="compactionRequest.details.length > 0"
          class="inspector__detail-list"
        >
          <li v-for="detail in compactionRequest.details" :key="detail">
            {{ detail }}
          </li>
        </ul>
        <p class="inspector__note inspector__note--compaction">
          Compaction does not create a new session. This thread keeps the same
          session history; older messages are only archived out of future prompt
          context.
        </p>
        <details
          v-if="compactionRequest.summaryFull"
          class="compaction-summary"
        >
          <summary class="compaction-summary__summary">
            {{ compactionRequest.summaryPreview ?? "Summary preview" }}
          </summary>
          <div class="compaction-summary__toolbar">
            <button
              class="ghost-button ghost-button--compact panel-tool-button compaction-summary__copy"
              type="button"
              @click="copyCompactionSummary(compactionRequest.summaryFull)"
            >
              {{ copiedSummary ? "Copied" : "Copy summary" }}
            </button>
          </div>
          <p class="compaction-summary__body">
            {{ compactionRequest.summaryFull }}
          </p>
        </details>
      </div>

      <div class="inspector__section">
        <p class="eyebrow">event feed</p>
        <div v-if="turnEvents.length === 0" class="event-feed__empty">
          The runtime trace will settle here after a turn is dispatched.
        </div>
        <div v-else class="event-feed">
          <article v-for="entry in turnEvents" :key="entry.id" class="event-row">
            <div class="event-row__copy">
              <strong class="event-row__event">{{ entry.event }}</strong>
              <span v-if="entry.detail" class="event-row__detail">{{ entry.detail }}</span>
              <span class="event-row__state">{{ entry.status }} / {{ entry.stage }}</span>
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
