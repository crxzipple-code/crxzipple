import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getAgentHomeMock = vi.fn();
const updateAgentHomeMock = vi.fn();

vi.mock("@/lib/api", () => ({
  getAgentHome: (...args: unknown[]) => getAgentHomeMock(...args),
  updateAgentHome: (...args: unknown[]) => updateAgentHomeMock(...args),
}));

import { useAgentHomeEditor } from "@/composables/useAgentHomeEditor";
import { buildAgentHomeSnapshot } from "../support/factories";

describe("useAgentHomeEditor", () => {
  beforeEach(() => {
    getAgentHomeMock.mockReset();
    updateAgentHomeMock.mockReset();
  });

  it("refreshes the current agent home and prefers AGENT.md as the selected file", async () => {
    const currentAgentId = ref<string | null>("assistant");
    const snapshot = buildAgentHomeSnapshot({
      files: [
        {
          name: "SOUL.md",
          path: "/tmp/agents/assistant/SOUL.md",
          exists: true,
          language: "markdown",
          content: "# Soul\n",
        },
        {
          name: "AGENT.md",
          path: "/tmp/agents/assistant/AGENT.md",
          exists: true,
          language: "markdown",
          content: "# Agent\n",
        },
      ],
    });
    getAgentHomeMock.mockResolvedValue(snapshot);

    const editor = useAgentHomeEditor({
      currentAgentId,
      initialFileName: "MEMORY.md",
    });

    await editor.refresh();

    expect(getAgentHomeMock).toHaveBeenCalledWith("assistant");
    expect(editor.snapshot.value).toEqual(snapshot);
    expect(editor.selectedFileName.value).toBe("AGENT.md");
    expect(editor.draftContent.value).toBe("# Agent\n");
    expect(editor.hasDirtyChanges.value).toBe(false);
  });

  it("tracks dirty drafts and saves the active file back through the api", async () => {
    const currentAgentId = ref<string | null>("assistant");
    const initialSnapshot = buildAgentHomeSnapshot();
    const savedSnapshot = buildAgentHomeSnapshot({
      files: [
        {
          name: "AGENT.md",
          path: "/tmp/agents/assistant/AGENT.md",
          exists: true,
          language: "markdown",
          content: "# Updated agent\n",
        },
        {
          name: "SOUL.md",
          path: "/tmp/agents/assistant/SOUL.md",
          exists: true,
          language: "markdown",
          content: "# Soul\n",
        },
      ],
    });
    getAgentHomeMock.mockResolvedValue(initialSnapshot);
    updateAgentHomeMock.mockResolvedValue(savedSnapshot);

    const editor = useAgentHomeEditor({
      currentAgentId,
      initialFileName: "AGENT.md",
    });

    await editor.refresh();
    editor.updateDraft("# Updated agent\n");

    expect(editor.currentFileDirty.value).toBe(true);
    expect(editor.dirtyFileNames.value).toEqual(["AGENT.md"]);
    expect(editor.hasDirtyChanges.value).toBe(true);

    await editor.saveCurrentFile();

    expect(updateAgentHomeMock).toHaveBeenCalledWith("assistant", [
      {
        name: "AGENT.md",
        content: "# Updated agent\n",
      },
    ]);
    expect(editor.snapshot.value).toEqual(savedSnapshot);
    expect(editor.draftContent.value).toBe("# Updated agent\n");
    expect(editor.currentFileDirty.value).toBe(false);
    expect(editor.hasDirtyChanges.value).toBe(false);
  });

  it("clears state when no agent is available and captures refresh errors", async () => {
    const currentAgentId = ref<string | null>("assistant");
    const editor = useAgentHomeEditor({
      currentAgentId,
      initialFileName: "AGENT.md",
    });

    editor.applySnapshot(buildAgentHomeSnapshot());
    currentAgentId.value = null;
    await editor.refresh();
    expect(editor.snapshot.value).toBeNull();
    expect(editor.selectedFileName.value).toBeNull();

    currentAgentId.value = "assistant";
    getAgentHomeMock.mockRejectedValue(new Error("boom"));
    await editor.refresh();

    expect(editor.errorMessage.value).toBe("boom");
    expect(editor.loading.value).toBe(false);
  });
});
