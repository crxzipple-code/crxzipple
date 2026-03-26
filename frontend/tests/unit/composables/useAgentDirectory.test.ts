import { computed, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ConversationSummary } from "@/types";

import {
  buildAgentProfile,
  buildConversationRoute,
  buildConversationSummary,
  buildLlmProfile,
} from "../support/factories";

const createAgentProfileMock = vi.fn();
const disableAgentProfileMock = vi.fn();
const enableAgentProfileMock = vi.fn();
const listAgentsMock = vi.fn();
const listLlmsMock = vi.fn();

vi.mock("@/lib/api", () => ({
  createAgentProfile: (...args: unknown[]) => createAgentProfileMock(...args),
  disableAgentProfile: (...args: unknown[]) => disableAgentProfileMock(...args),
  enableAgentProfile: (...args: unknown[]) => enableAgentProfileMock(...args),
  listAgents: (...args: unknown[]) => listAgentsMock(...args),
  listLlms: (...args: unknown[]) => listLlmsMock(...args),
}));

import { useAgentDirectory } from "@/composables/useAgentDirectory";

describe("useAgentDirectory", () => {
  beforeEach(() => {
    createAgentProfileMock.mockReset();
    disableAgentProfileMock.mockReset();
    enableAgentProfileMock.mockReset();
    listAgentsMock.mockReset();
    listLlmsMock.mockReset();
  });

  it("refreshes agent and llm lists, filters disabled llms, and refreshes the open home", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>(null);
    const selectedLlmId = ref<string | null>(null);
    const draftRoute = ref(buildConversationRoute({ agentId: "crxzipple" }));
    const activeConversation = ref<ConversationSummary | null>(null);
    const agentPanelAgentId = ref<string | null>("assistant");
    const currentAgentHomeId = computed(
      () => agentPanelAgentId.value ?? selectedAgentId.value ?? defaultAgentId.value,
    );
    const refreshMemoryPanel = vi.fn().mockResolvedValue(undefined);
    const refreshAgentHome = vi.fn().mockResolvedValue(undefined);

    listAgentsMock.mockResolvedValue([
      buildAgentProfile({ id: "assistant", enabled: true }),
      buildAgentProfile({ id: "crxzipple", enabled: true }),
      buildAgentProfile({ id: "disabled-agent", enabled: false }),
    ]);
    listLlmsMock.mockResolvedValue([
      buildLlmProfile({ id: "openai.gpt-5.4-mini", enabled: true }),
      buildLlmProfile({ id: "legacy.disabled", enabled: false }),
    ]);

    const directory = useAgentDirectory({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      draftRoute,
      activeConversation,
      agentPanelAgentId,
      currentAgentHomeId,
      agentHomeOpen: ref(true),
      hasDirtyAgentHomeChanges: ref(false),
      refreshMemoryPanel,
      refreshAgentHome,
      confirmDiscardAgentHomeChanges: vi.fn().mockReturnValue(true),
    });

    await directory.refreshProfiles();

    expect(directory.agents.value).toHaveLength(3);
    expect(directory.llms.value).toEqual([
      buildLlmProfile({ id: "openai.gpt-5.4-mini", enabled: true }),
    ]);
    expect(directory.enabledAgents.value.map((item) => item.id)).toEqual([
      "assistant",
      "crxzipple",
    ]);
    expect(selectedAgentId.value).toBe("crxzipple");
    expect(directory.suggestedAgentHomeBaseDir.value).toBe("/tmp/agents");
    expect(refreshAgentHome).toHaveBeenCalledWith("assistant");
    expect(refreshMemoryPanel).not.toHaveBeenCalled();
  });

  it("switches agents for draft conversations only after passing dirty-change confirmation", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>("assistant");
    const selectedLlmId = ref<string | null>(null);
    const draftRoute = ref(buildConversationRoute({ agentId: "assistant" }));
    const activeConversation = ref<ConversationSummary | null>(null);
    const agentPanelAgentId = ref<string | null>("assistant");
    const currentAgentHomeId = computed(
      () => agentPanelAgentId.value ?? selectedAgentId.value ?? defaultAgentId.value,
    );
    const refreshMemoryPanel = vi.fn().mockResolvedValue(undefined);
    const refreshAgentHome = vi.fn().mockResolvedValue(undefined);
    const confirmDiscardAgentHomeChanges = vi
      .fn()
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);

    const directory = useAgentDirectory({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      draftRoute,
      activeConversation,
      agentPanelAgentId,
      currentAgentHomeId,
      agentHomeOpen: ref(true),
      hasDirtyAgentHomeChanges: ref(true),
      refreshMemoryPanel,
      refreshAgentHome,
      confirmDiscardAgentHomeChanges,
    });

    directory.agents.value = [
      buildAgentProfile({ id: "assistant", enabled: true }),
      buildAgentProfile({ id: "planner", enabled: true }),
    ];

    await directory.selectAgent("planner");
    expect(selectedAgentId.value).toBe("assistant");
    expect(draftRoute.value.agentId).toBe("assistant");
    expect(refreshMemoryPanel).not.toHaveBeenCalled();

    await directory.selectAgent("planner");
    expect(selectedAgentId.value).toBe("planner");
    expect(draftRoute.value.agentId).toBe("planner");
    expect(agentPanelAgentId.value).toBe("planner");
    expect(refreshMemoryPanel).toHaveBeenCalledWith("planner");
    expect(refreshAgentHome).toHaveBeenCalledWith("planner");
  });

  it("creates a new agent, refreshes lists, and focuses the new home", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>("assistant");
    const selectedLlmId = ref<string | null>(null);
    const draftRoute = ref(buildConversationRoute({ agentId: "assistant" }));
    const activeConversation = ref<ConversationSummary | null>(null);
    const agentPanelAgentId = ref<string | null>("assistant");
    const currentAgentHomeId = computed(
      () => agentPanelAgentId.value ?? selectedAgentId.value ?? defaultAgentId.value,
    );
    const refreshMemoryPanel = vi.fn().mockResolvedValue(undefined);
    const refreshAgentHome = vi.fn().mockResolvedValue(undefined);

    createAgentProfileMock.mockResolvedValue(
      buildAgentProfile({ id: "researcher", name: "Researcher" }),
    );
    listAgentsMock.mockResolvedValue([
      buildAgentProfile({ id: "assistant", enabled: true }),
      buildAgentProfile({ id: "researcher", enabled: true }),
    ]);
    listLlmsMock.mockResolvedValue([buildLlmProfile()]);

    const directory = useAgentDirectory({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      draftRoute,
      activeConversation,
      agentPanelAgentId,
      currentAgentHomeId,
      agentHomeOpen: ref(true),
      hasDirtyAgentHomeChanges: ref(false),
      refreshMemoryPanel,
      refreshAgentHome,
      confirmDiscardAgentHomeChanges: vi.fn().mockReturnValue(true),
    });

    await directory.createAgentFromPanel({
      id: "researcher",
      name: "Researcher",
      description: "Finds things",
      defaultLlmId: "openai.gpt-5.4-mini",
      homeDir: "/tmp/agents/researcher",
      workdir: "/tmp/work/researcher",
      systemPrompt: "You are a researcher.",
    });

    expect(createAgentProfileMock).toHaveBeenCalledWith({
      id: "researcher",
      name: "Researcher",
      description: "Finds things",
      defaultLlmId: "openai.gpt-5.4-mini",
      homeDir: "/tmp/agents/researcher",
      workdir: "/tmp/work/researcher",
      systemPrompt: "You are a researcher.",
    });
    expect(selectedAgentId.value).toBe("researcher");
    expect(agentPanelAgentId.value).toBe("researcher");
    expect(draftRoute.value.agentId).toBe("researcher");
    expect(refreshMemoryPanel).toHaveBeenCalledWith("researcher");
    expect(refreshAgentHome).toHaveBeenLastCalledWith("researcher");
    expect(directory.creatingAgent.value).toBe(false);
    expect(directory.errorMessage.value).toBeNull();
  });

  it("toggles enabled state and only refreshes the open home through profile reload", async () => {
    const defaultAgentId = ref("crxzipple");
    const selectedAgentId = ref<string | null>("assistant");
    const selectedLlmId = ref<string | null>(null);
    const draftRoute = ref(buildConversationRoute({ agentId: "assistant" }));
    const activeConversation = ref<ConversationSummary | null>(
      buildConversationSummary(),
    );
    const agentPanelAgentId = ref<string | null>("assistant");
    const currentAgentHomeId = computed(
      () => agentPanelAgentId.value ?? selectedAgentId.value ?? defaultAgentId.value,
    );
    const refreshAgentHome = vi.fn().mockResolvedValue(undefined);

    listAgentsMock.mockResolvedValue([
      buildAgentProfile({ id: "assistant", enabled: true }),
      buildAgentProfile({ id: "planner", enabled: false }),
    ]);
    listLlmsMock.mockResolvedValue([buildLlmProfile()]);
    disableAgentProfileMock.mockResolvedValue(
      buildAgentProfile({ id: "assistant", enabled: false }),
    );

    const directory = useAgentDirectory({
      defaultAgentId,
      selectedAgentId,
      selectedLlmId,
      draftRoute,
      activeConversation,
      agentPanelAgentId,
      currentAgentHomeId,
      agentHomeOpen: ref(true),
      hasDirtyAgentHomeChanges: ref(true),
      refreshMemoryPanel: vi.fn().mockResolvedValue(undefined),
      refreshAgentHome,
      confirmDiscardAgentHomeChanges: vi.fn().mockReturnValue(true),
    });

    await directory.updateAgentEnabledState("assistant", false);

    expect(disableAgentProfileMock).toHaveBeenCalledWith("assistant");
    expect(listAgentsMock).toHaveBeenCalledTimes(1);
    expect(refreshAgentHome).toHaveBeenCalledTimes(1);
    expect(refreshAgentHome).toHaveBeenCalledWith("assistant");
    expect(directory.updatingAgentStatusId.value).toBeNull();
  });
});
