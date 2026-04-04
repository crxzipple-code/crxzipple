<script setup lang="ts">
import { nextTick, ref, watch } from "vue";

import type { MemoryExcerpt, MemoryFileSummary, MemorySearchHit } from "@/types";

const props = defineProps<{
  open: boolean;
  loading: boolean;
  longTermMemory: MemoryExcerpt | null;
  recentFiles: MemoryFileSummary[];
  searchResults: MemorySearchHit[];
  selectedExcerpt: MemoryExcerpt | null;
  query: string;
  formatTime: (value: string | null) => string;
}>();

const emit = defineEmits<{
  close: [];
  openExcerpt: [path: string, startLine?: number | null, lineCount?: number | null];
  "update:query": [value: string];
  refresh: [];
}>();

type PendingOpenRequest = {
  path: string;
  startLine: number | null;
  endLine: number | null;
};

const selectedExcerptSection = ref<HTMLElement | null>(null);
const pendingOpenRequest = ref<PendingOpenRequest | null>(null);

function normalizeLineNumber(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function createPendingOpenRequest(
  path: string,
  startLine?: number | null,
  lineCount?: number | null,
): PendingOpenRequest {
  const normalizedStartLine = normalizeLineNumber(startLine);
  const normalizedLineCount = normalizeLineNumber(lineCount);
  return {
    path,
    startLine: normalizedStartLine,
    endLine:
      normalizedStartLine != null && normalizedLineCount != null
        ? normalizedStartLine + Math.max(normalizedLineCount, 1) - 1
        : null,
  };
}

function handleOpenExcerpt(
  path: string,
  startLine?: number | null,
  lineCount?: number | null,
) {
  pendingOpenRequest.value = createPendingOpenRequest(path, startLine, lineCount);
  emit("openExcerpt", path, startLine ?? null, lineCount ?? null);
}

function isActivePath(path: string) {
  return props.selectedExcerpt?.path === path;
}

function isActiveSearchHit(hit: MemorySearchHit) {
  const selectedExcerpt = props.selectedExcerpt;
  if (!selectedExcerpt || selectedExcerpt.path !== hit.path) {
    return false;
  }
  return !(
    selectedExcerpt.end_line < hit.start_line ||
    selectedExcerpt.start_line > hit.end_line
  );
}

function actionLabel(active: boolean) {
  return active ? "Opened" : "Open";
}

watch(
  () => [
    props.selectedExcerpt?.path ?? null,
    props.selectedExcerpt?.start_line ?? null,
    props.selectedExcerpt?.end_line ?? null,
  ],
  async ([path, startLine, endLine]) => {
    const pendingRequest = pendingOpenRequest.value;
    if (!pendingRequest || !path || pendingRequest.path !== path) {
      return;
    }
    if (
      pendingRequest.startLine != null &&
      pendingRequest.startLine !== startLine
    ) {
      return;
    }
    if (pendingRequest.endLine != null && pendingRequest.endLine !== endLine) {
      return;
    }
    pendingOpenRequest.value = null;
    await nextTick();
    selectedExcerptSection.value?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  },
  { flush: "post" },
);
</script>

<template>
  <aside class="memory-drawer" :class="{ 'memory-drawer--open': open }">
    <div class="memory-panel shell">
      <div class="memory-panel__header">
        <div>
          <p class="eyebrow">memory</p>
          <h3>Memory files</h3>
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
            placeholder="Search memory files"
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
        <p class="eyebrow">long-term memory</p>
        <div v-if="!longTermMemory" class="event-feed__empty">
          No root `MEMORY.md` file is available for this agent yet.
        </div>
        <article
          v-else
          class="memory-log__entry"
          :class="{ 'memory-log__entry--active': isActivePath(longTermMemory.path) }"
        >
          <div class="memory-log__head">
            <strong>{{ longTermMemory.path }}</strong>
            <div class="memory-log__head-actions">
              <button
                class="ghost-button ghost-button--compact"
                type="button"
                :aria-pressed="isActivePath(longTermMemory.path)"
                @click="handleOpenExcerpt(longTermMemory.path)"
              >
                {{ actionLabel(isActivePath(longTermMemory.path)) }}
              </button>
            </div>
          </div>
          <p>{{ longTermMemory.text.slice(0, 220) }}<span v-if="longTermMemory.text.length > 220">...</span></p>
        </article>
      </div>

      <div class="memory-panel__section">
        <p class="eyebrow">recent memory</p>
        <div v-if="loading" class="event-feed__empty">
          Loading memory...
        </div>
        <div v-else-if="recentFiles.length === 0" class="event-feed__empty">
          Recent daily and archived memory files will appear here.
        </div>
        <div v-else class="memory-log">
          <article
            v-for="item in recentFiles"
            :key="item.path"
            class="memory-log__entry"
            :class="{ 'memory-log__entry--active': isActivePath(item.path) }"
          >
            <div class="memory-log__head">
              <strong>{{ item.title }}</strong>
              <div class="memory-log__head-actions">
                <time>{{ formatTime(item.updated_at) }}</time>
                <button
                  class="ghost-button ghost-button--compact"
                  type="button"
                  :aria-pressed="isActivePath(item.path)"
                  @click="handleOpenExcerpt(item.path)"
                >
                  {{ actionLabel(isActivePath(item.path)) }}
                </button>
              </div>
            </div>
            <p>{{ item.preview || item.path }}</p>
            <div class="memory-log__meta">
              {{ item.path }} · {{ item.kind }}
            </div>
          </article>
        </div>
      </div>

      <div class="memory-panel__section">
        <p class="eyebrow">search results</p>
        <div v-if="!query.trim()" class="event-feed__empty">
          Search across memory files to inspect specific notes and citations.
        </div>
        <div v-else-if="searchResults.length === 0" class="event-feed__empty">
          No memory files matched this query.
        </div>
        <div v-else class="memory-log">
          <article
            v-for="hit in searchResults"
            :key="`${hit.path}:${hit.start_line}:${hit.end_line}`"
            class="memory-log__entry"
            :class="{ 'memory-log__entry--active': isActiveSearchHit(hit) }"
          >
            <div class="memory-log__head">
              <strong>{{ hit.path }}</strong>
              <div class="memory-log__head-actions">
                <button
                  class="ghost-button ghost-button--compact"
                  type="button"
                  :aria-pressed="isActiveSearchHit(hit)"
                  @click="
                    handleOpenExcerpt(
                      hit.path,
                      hit.start_line,
                      Math.max(hit.end_line - hit.start_line + 1, 1),
                    )
                  "
                >
                  {{ actionLabel(isActiveSearchHit(hit)) }}
                </button>
              </div>
            </div>
            <p>{{ hit.snippet }}</p>
            <div class="memory-log__meta">
              L{{ hit.start_line }}<span v-if="hit.end_line > hit.start_line">-L{{ hit.end_line }}</span> · {{ hit.kind }}
            </div>
          </article>
        </div>
      </div>

      <div class="memory-panel__section">
        <p class="eyebrow">selected excerpt</p>
        <div v-if="!selectedExcerpt" class="event-feed__empty">
          Pick a file or search hit to inspect a memory excerpt.
        </div>
        <article
          v-else
          ref="selectedExcerptSection"
          class="memory-log__entry memory-log__entry--active memory-log__entry--selected"
        >
          <div class="memory-log__head">
            <strong>{{ selectedExcerpt.path }}</strong>
            <div class="memory-log__head-actions">
              <span>L{{ selectedExcerpt.start_line }}<span v-if="selectedExcerpt.end_line > selectedExcerpt.start_line">-L{{ selectedExcerpt.end_line }}</span></span>
            </div>
          </div>
          <pre class="memory-panel__excerpt">{{ selectedExcerpt.text }}</pre>
        </article>
      </div>
    </div>
  </aside>
</template>
