import { ref, watch, type Ref } from "vue";

const STORAGE_KEYS = {
  deckOpen: "crxzipple.ui.deckOpen",
  activeRightPanel: "crxzipple.ui.activeRightPanel",
  agentPanelAgentId: "crxzipple.ui.agentPanelAgentId",
} as const;

type RightPanel = "inspect" | "memory" | "agent" | null;

function readBoolean(key: string, fallback: boolean) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return fallback;
}

function readRightPanel(key: string, fallback: RightPanel) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  if (value === "inspect" || value === "memory" || value === "agent") {
    return value;
  }
  return fallback;
}

function readNullableString(key: string) {
  if (typeof window === "undefined") {
    return null;
  }
  const value = window.localStorage.getItem(key);
  return value && value.trim() ? value : null;
}

export function usePersistentUiState() {
  const deckOpen = ref(readBoolean(STORAGE_KEYS.deckOpen, true));
  const preferredRightPanel = ref<RightPanel>(
    readRightPanel(STORAGE_KEYS.activeRightPanel, null),
  );
  const activeRightPanel = ref<RightPanel>(preferredRightPanel.value);
  const agentPanelAgentId = ref<string | null>(
    readNullableString(STORAGE_KEYS.agentPanelAgentId),
  );

  watch(deckOpen, (value) => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(STORAGE_KEYS.deckOpen, String(value));
  });

  watch(preferredRightPanel, (value) => {
    if (typeof window === "undefined") {
      return;
    }
    if (value === null) {
      window.localStorage.removeItem(STORAGE_KEYS.activeRightPanel);
      return;
    }
    window.localStorage.setItem(STORAGE_KEYS.activeRightPanel, value);
  });

  watch(agentPanelAgentId, (value) => {
    if (typeof window === "undefined") {
      return;
    }
    if (!value) {
      window.localStorage.removeItem(STORAGE_KEYS.agentPanelAgentId);
      return;
    }
    window.localStorage.setItem(STORAGE_KEYS.agentPanelAgentId, value);
  });

  function setActiveRightPanel(
    value: RightPanel,
    options?: { persist?: boolean },
  ) {
    activeRightPanel.value = value;
    if (options?.persist ?? true) {
      preferredRightPanel.value = value;
    }
  }

  return {
    deckOpen,
    preferredRightPanel,
    activeRightPanel,
    setActiveRightPanel,
    agentPanelAgentId,
  } satisfies {
    deckOpen: Ref<boolean>;
    preferredRightPanel: Ref<RightPanel>;
    activeRightPanel: Ref<RightPanel>;
    setActiveRightPanel: (value: RightPanel, options?: { persist?: boolean }) => void;
    agentPanelAgentId: Ref<string | null>;
  };
}
