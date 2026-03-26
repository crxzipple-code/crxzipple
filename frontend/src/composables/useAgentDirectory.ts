import { computed, ref, type Ref } from "vue";

import {
  createAgentProfile,
  disableAgentProfile,
  enableAgentProfile,
  listAgents,
  listLlms,
} from "@/lib/api";
import type {
  AgentProfileSummary,
  ConversationRoute,
  ConversationSummary,
  LlmProfileSummary,
} from "@/types";

export function useAgentDirectory(options: {
  defaultAgentId: Ref<string>;
  selectedAgentId: Ref<string | null>;
  selectedLlmId: Ref<string | null>;
  draftRoute: Ref<ConversationRoute>;
  activeConversation: Ref<ConversationSummary | null>;
  agentPanelAgentId: Ref<string | null>;
  currentAgentHomeId: Ref<string>;
  agentHomeOpen: Ref<boolean>;
  hasDirtyAgentHomeChanges: Ref<boolean>;
  refreshMemoryPanel: (agentId?: string | null) => Promise<void>;
  refreshAgentHome: (agentId?: string | null) => Promise<void>;
  confirmDiscardAgentHomeChanges: (reason: string) => boolean;
}) {
  const agents = ref<AgentProfileSummary[]>([]);
  const llms = ref<LlmProfileSummary[]>([]);
  const creatingAgent = ref(false);
  const updatingAgentStatusId = ref<string | null>(null);
  const errorMessage = ref<string | null>(null);

  const enabledAgents = computed(() =>
    agents.value.filter((item) => item.enabled),
  );

  const suggestedAgentHomeBaseDir = computed(() => {
    for (const agent of agents.value) {
      const homeDir = agent.runtime_preferences.home_dir;
      if (!homeDir) {
        continue;
      }
      const normalized = homeDir.replace(/\/+$/, "");
      const index = normalized.lastIndexOf("/");
      if (index > 0) {
        return normalized.slice(0, index);
      }
    }
    return null;
  });

  async function refreshProfiles() {
    const [agentItems, llmItems] = await Promise.all([listAgents(), listLlms()]);
    agents.value = agentItems;
    llms.value = llmItems.filter((item) => item.enabled);
    const enabledAgentItems = agentItems.filter((item) => item.enabled);

    if (
      options.selectedAgentId.value === null ||
      !enabledAgentItems.some((item) => item.id === options.selectedAgentId.value)
    ) {
      options.selectedAgentId.value =
        enabledAgentItems.find(
          (item) => item.id === options.defaultAgentId.value,
        )?.id ??
        enabledAgentItems[0]?.id ??
        options.defaultAgentId.value;
    }

    if (
      options.agentHomeOpen.value &&
      options.currentAgentHomeId.value
    ) {
      await options.refreshAgentHome(options.currentAgentHomeId.value);
    }
  }

  async function selectAgent(agentId: string) {
    if (!enabledAgents.value.some((item) => item.id === agentId)) {
      return;
    }
    if (
      options.agentHomeOpen.value &&
      options.activeConversation.value === null &&
      agentId !== options.currentAgentHomeId.value &&
      !options.confirmDiscardAgentHomeChanges(
        "Switching agents will discard those edits.",
      )
    ) {
      return;
    }
    options.selectedAgentId.value = agentId;
    if (options.activeConversation.value === null) {
      options.draftRoute.value = {
        ...options.draftRoute.value,
        agentId,
      };
    }
    await options.refreshMemoryPanel(
      options.activeConversation.value?.runtime_binding.agent_id ?? agentId,
    );
    if (options.agentHomeOpen.value && options.activeConversation.value === null) {
      options.agentPanelAgentId.value = agentId;
      await options.refreshAgentHome(agentId);
    }
  }

  async function selectAgentHomeAgent(agentId: string) {
    if (
      agentId !== options.currentAgentHomeId.value &&
      !options.confirmDiscardAgentHomeChanges(
        "Switching agents will discard those edits.",
      )
    ) {
      return;
    }
    options.agentPanelAgentId.value = agentId;
    await options.refreshAgentHome(agentId);
  }

  async function useAgentForNewChats(agentId: string) {
    if (!enabledAgents.value.some((item) => item.id === agentId)) {
      return;
    }
    if (
      options.agentHomeOpen.value &&
      agentId !== options.currentAgentHomeId.value &&
      !options.confirmDiscardAgentHomeChanges(
        "Switching the agent home view will discard those edits.",
      )
    ) {
      return;
    }
    options.selectedAgentId.value = agentId;
    options.draftRoute.value = {
      ...options.draftRoute.value,
      agentId,
    };
    options.agentPanelAgentId.value = agentId;
    if (options.activeConversation.value === null) {
      await options.refreshMemoryPanel(agentId);
    }
    if (options.agentHomeOpen.value) {
      await options.refreshAgentHome(agentId);
    }
  }

  async function createAgentFromPanel(payload: {
    id: string;
    name: string;
    description: string;
    defaultLlmId: string;
    homeDir: string | null;
    workdir: string | null;
    systemPrompt: string;
  }) {
    if (
      payload.id !== options.currentAgentHomeId.value &&
      !options.confirmDiscardAgentHomeChanges(
        "Opening the new agent home will discard those edits.",
      )
    ) {
      return;
    }
    creatingAgent.value = true;
    errorMessage.value = null;
    try {
      await createAgentProfile(payload);
      await refreshProfiles();
      options.selectedAgentId.value = payload.id;
      options.agentPanelAgentId.value = payload.id;
      if (options.activeConversation.value === null) {
        options.draftRoute.value = {
          ...options.draftRoute.value,
          agentId: payload.id,
        };
      }
      await options.refreshMemoryPanel(
        options.activeConversation.value?.runtime_binding.agent_id ?? payload.id,
      );
      await options.refreshAgentHome(payload.id);
    } catch (error) {
      errorMessage.value =
        error instanceof Error ? error.message : String(error);
    } finally {
      creatingAgent.value = false;
    }
  }

  async function updateAgentEnabledState(agentId: string, enabled: boolean) {
    updatingAgentStatusId.value = agentId;
    errorMessage.value = null;
    try {
      if (enabled) {
        await enableAgentProfile(agentId);
      } else {
        await disableAgentProfile(agentId);
      }
      await refreshProfiles();
      if (
        options.agentHomeOpen.value &&
        (!options.hasDirtyAgentHomeChanges.value ||
          options.currentAgentHomeId.value !== agentId)
      ) {
        await options.refreshAgentHome(agentId);
      }
    } catch (error) {
      errorMessage.value =
        error instanceof Error ? error.message : String(error);
    } finally {
      updatingAgentStatusId.value = null;
    }
  }

  function selectLlm(llmId: string | null) {
    options.selectedLlmId.value = llmId;
    if (options.activeConversation.value === null) {
      options.draftRoute.value = {
        ...options.draftRoute.value,
        llmId: llmId ?? undefined,
      };
    }
  }

  return {
    agents,
    llms,
    creatingAgent,
    updatingAgentStatusId,
    errorMessage,
    enabledAgents,
    suggestedAgentHomeBaseDir,
    refreshProfiles,
    selectAgent,
    selectAgentHomeAgent,
    useAgentForNewChats,
    createAgentFromPanel,
    updateAgentEnabledState,
    selectLlm,
  };
}
