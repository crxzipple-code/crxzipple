import { computed, ref, type Ref } from "vue";

import {
  getMemoryExcerpt,
  getMemoryOverview,
  searchMemory,
} from "@/lib/api";
import type {
  MemoryExcerpt,
  MemoryFileSummary,
  MemorySearchHit,
} from "@/types";

export function useMemoryPanel(options: {
  activeAgentId: Ref<string | null>;
  lastError: Ref<string | null>;
}) {
  const longTermMemory = ref<MemoryExcerpt | null>(null);
  const recentMemoryFiles = ref<MemoryFileSummary[]>([]);
  const memorySearchResults = ref<MemorySearchHit[]>([]);
  const selectedMemoryExcerpt = ref<MemoryExcerpt | null>(null);
  const selectedMemoryPath = ref<string | null>(null);
  const memoryQuery = ref("");
  const loadingMemory = ref(false);

  const memoryItemCount = computed(
    () => recentMemoryFiles.value.length + (longTermMemory.value ? 1 : 0),
  );

  async function refreshMemoryPanel(agentId?: string | null) {
    const effectiveAgentId =
      agentId?.trim() || options.activeAgentId.value?.trim();
    if (!effectiveAgentId) {
      longTermMemory.value = null;
      recentMemoryFiles.value = [];
      memorySearchResults.value = [];
      selectedMemoryExcerpt.value = null;
      selectedMemoryPath.value = null;
      return;
    }
    loadingMemory.value = true;
    try {
      const [overview, hits] = await Promise.all([
        getMemoryOverview({
          agentId: effectiveAgentId,
          recentLimit: 20,
        }),
        memoryQuery.value.trim()
          ? searchMemory({
              agentId: effectiveAgentId,
              query: memoryQuery.value.trim(),
              limit: 20,
            })
          : Promise.resolve([]),
      ]);
      longTermMemory.value = overview.long_term;
      recentMemoryFiles.value = overview.recent_files;
      memorySearchResults.value = hits;

      const nextSelectedPath =
        selectedMemoryPath.value ??
        overview.long_term?.path ??
        overview.recent_files[0]?.path ??
        null;
      if (!nextSelectedPath) {
        selectedMemoryExcerpt.value = null;
        selectedMemoryPath.value = null;
        return;
      }
      await openMemoryExcerpt(nextSelectedPath, {
        agentId: effectiveAgentId,
      });
    } finally {
      loadingMemory.value = false;
    }
  }

  async function openMemoryExcerpt(
    path: string,
    optionsOverride?: {
      agentId?: string | null;
      startLine?: number | null;
      lineCount?: number | null;
    },
  ) {
    const effectiveAgentId =
      optionsOverride?.agentId?.trim() || options.activeAgentId.value?.trim();
    if (!effectiveAgentId) {
      return;
    }
    options.lastError.value = null;
    try {
      const excerpt = await getMemoryExcerpt({
        agentId: effectiveAgentId,
        path,
        startLine: optionsOverride?.startLine ?? null,
        lineCount: optionsOverride?.lineCount ?? null,
      });
      selectedMemoryExcerpt.value = excerpt;
      selectedMemoryPath.value = excerpt.path;
    } catch (error) {
      options.lastError.value =
        error instanceof Error ? error.message : String(error);
    }
  }

  return {
    longTermMemory,
    recentMemoryFiles,
    memorySearchResults,
    selectedMemoryExcerpt,
    memoryQuery,
    loadingMemory,
    memoryItemCount,
    refreshMemoryPanel,
    openMemoryExcerpt,
  };
}
