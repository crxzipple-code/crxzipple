import { computed, ref, type Ref } from "vue";

import { getAgentHome, updateAgentHome } from "@/lib/api";
import type { AgentHomeSnapshot } from "@/types";

type CurrentAgentIdRef = Readonly<Ref<string | null>>;

export function useAgentHomeEditor(options: {
  currentAgentId: CurrentAgentIdRef;
  initialFileName?: string | null;
}) {
  const loading = ref(false);
  const saving = ref(false);
  const errorMessage = ref<string | null>(null);
  const snapshot = ref<AgentHomeSnapshot | null>(null);
  const selectedFileName = ref<string | null>(options.initialFileName ?? "AGENT.md");
  const drafts = ref<Record<string, string>>({});

  const activeFile = computed(
    () =>
      snapshot.value?.files.find(
        (item) => item.name === selectedFileName.value,
      ) ?? null,
  );

  const draftContent = computed(() => {
    const file = activeFile.value;
    if (!file) {
      return "";
    }
    return drafts.value[file.name] ?? file.content;
  });

  const dirtyFileNames = computed(() => {
    const currentSnapshot = snapshot.value;
    if (!currentSnapshot) {
      return [];
    }
    return currentSnapshot.files
      .filter((file) => (drafts.value[file.name] ?? file.content) !== file.content)
      .map((file) => file.name);
  });

  const currentFileDirty = computed(() => {
    const file = activeFile.value;
    if (!file) {
      return false;
    }
    return (drafts.value[file.name] ?? file.content) !== file.content;
  });

  const hasDirtyChanges = computed(() => dirtyFileNames.value.length > 0);

  function applySnapshot(nextSnapshot: AgentHomeSnapshot) {
    snapshot.value = nextSnapshot;
    drafts.value = Object.fromEntries(
      nextSnapshot.files.map((file) => [file.name, file.content]),
    );
    const preferredFile =
      nextSnapshot.files.find((item) => item.name === selectedFileName.value)?.name ??
      nextSnapshot.files.find((item) => item.name === "AGENT.md")?.name ??
      nextSnapshot.files[0]?.name ??
      null;
    selectedFileName.value = preferredFile;
  }

  function clear() {
    snapshot.value = null;
    drafts.value = {};
    selectedFileName.value = null;
  }

  async function refresh(agentId?: string | null) {
    const effectiveAgentId = agentId?.trim() || options.currentAgentId.value?.trim();
    if (!effectiveAgentId) {
      clear();
      return;
    }
    loading.value = true;
    errorMessage.value = null;
    try {
      const nextSnapshot = await getAgentHome(effectiveAgentId);
      applySnapshot(nextSnapshot);
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : String(error);
    } finally {
      loading.value = false;
    }
  }

  function selectFile(fileName: string) {
    selectedFileName.value = fileName;
  }

  function updateDraft(value: string) {
    const file = activeFile.value;
    if (!file) {
      return;
    }
    drafts.value = {
      ...drafts.value,
      [file.name]: value,
    };
  }

  async function saveCurrentFile() {
    const file = activeFile.value;
    const agentId = options.currentAgentId.value?.trim();
    if (!file || !currentFileDirty.value || !agentId) {
      return;
    }
    saving.value = true;
    errorMessage.value = null;
    try {
      const nextSnapshot = await updateAgentHome(agentId, [
        {
          name: file.name,
          content: draftContent.value,
        },
      ]);
      applySnapshot(nextSnapshot);
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : String(error);
    } finally {
      saving.value = false;
    }
  }

  return {
    loading,
    saving,
    errorMessage,
    snapshot,
    selectedFileName,
    activeFile,
    draftContent,
    dirtyFileNames,
    currentFileDirty,
    hasDirtyChanges,
    drafts,
    applySnapshot,
    clear,
    refresh,
    selectFile,
    updateDraft,
    saveCurrentFile,
  };
}
