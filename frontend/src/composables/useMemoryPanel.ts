import { computed, ref, type Ref } from "vue";

import {
  approveMemoryCandidate,
  listMemoryCandidates,
  listMemoryEntries,
  rejectMemoryCandidate,
} from "@/lib/api";
import type {
  ConversationSummary,
  MemoryCandidate,
  MemoryEntry,
} from "@/types";

export function useMemoryPanel(options: {
  activeAgentId: Ref<string | null>;
  activeConversation: Ref<ConversationSummary | null>;
  lastError: Ref<string | null>;
}) {
  const pendingMemoryCandidates = ref<MemoryCandidate[]>([]);
  const approvedMemoryEntries = ref<MemoryEntry[]>([]);
  const memoryQuery = ref("");
  const loadingMemory = ref(false);

  const currentSessionKey = computed(
    () => options.activeConversation.value?.session_key ?? null,
  );

  const currentThreadMemoryCandidates = computed(() => {
    if (!currentSessionKey.value) {
      return [];
    }
    return pendingMemoryCandidates.value.filter(
      (candidate) => candidate.session_key === currentSessionKey.value,
    );
  });

  const otherMemoryCandidates = computed(() => {
    if (!currentSessionKey.value) {
      return pendingMemoryCandidates.value;
    }
    return pendingMemoryCandidates.value.filter(
      (candidate) => candidate.session_key !== currentSessionKey.value,
    );
  });

  async function refreshPendingMemoryCandidates(agentId?: string | null) {
    const effectiveAgentId =
      agentId?.trim() || options.activeAgentId.value?.trim();
    if (!effectiveAgentId) {
      pendingMemoryCandidates.value = [];
      return;
    }
    pendingMemoryCandidates.value = await listMemoryCandidates({
      agentId: effectiveAgentId,
      status: "pending",
      limit: 25,
    });
  }

  async function refreshApprovedMemoryEntries(agentId?: string | null) {
    const effectiveAgentId =
      agentId?.trim() || options.activeAgentId.value?.trim();
    if (!effectiveAgentId) {
      approvedMemoryEntries.value = [];
      return;
    }
    loadingMemory.value = true;
    try {
      approvedMemoryEntries.value = await listMemoryEntries({
        agentId: effectiveAgentId,
        query: memoryQuery.value.trim() || null,
        limit: 20,
      });
    } finally {
      loadingMemory.value = false;
    }
  }

  async function refreshMemoryPanel(agentId?: string | null) {
    await Promise.all([
      refreshPendingMemoryCandidates(agentId),
      refreshApprovedMemoryEntries(agentId),
    ]);
  }

  async function approveMemoryCandidateById(candidateId: string) {
    const candidate = pendingMemoryCandidates.value.find(
      (item) => item.id === candidateId,
    );
    if (!candidate) {
      return;
    }
    options.lastError.value = null;
    try {
      await approveMemoryCandidate(candidate.id);
      await refreshMemoryPanel(candidate.agent_id);
    } catch (error) {
      options.lastError.value =
        error instanceof Error ? error.message : String(error);
    }
  }

  async function rejectMemoryCandidateById(candidateId: string) {
    const candidate = pendingMemoryCandidates.value.find(
      (item) => item.id === candidateId,
    );
    if (!candidate) {
      return;
    }
    options.lastError.value = null;
    try {
      await rejectMemoryCandidate(candidate.id);
      await refreshMemoryPanel(candidate.agent_id);
    } catch (error) {
      options.lastError.value =
        error instanceof Error ? error.message : String(error);
    }
  }

  return {
    pendingMemoryCandidates,
    approvedMemoryEntries,
    memoryQuery,
    loadingMemory,
    currentSessionKey,
    currentThreadMemoryCandidates,
    otherMemoryCandidates,
    refreshPendingMemoryCandidates,
    refreshApprovedMemoryEntries,
    refreshMemoryPanel,
    approveMemoryCandidateById,
    rejectMemoryCandidateById,
  };
}
