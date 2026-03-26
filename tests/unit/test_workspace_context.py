from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from crxzipple.modules.orchestration.application.workspace_context import (
    load_workspace_context_files,
)


class WorkspaceContextTestCase(unittest.TestCase):
    def test_load_workspace_context_files_returns_empty_when_workspace_missing(self) -> None:
        self.assertEqual(
            load_workspace_context_files("/tmp/crxzipple-workspace-does-not-exist"),
            (),
        )

    def test_load_workspace_context_files_loads_agents_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            (workspace / "AGENTS.md").write_text(
                "# AGENTS.md\n\nUse the repository conventions.\n",
                encoding="utf-8",
            )

            context_files = load_workspace_context_files(str(workspace))

            self.assertEqual(len(context_files), 1)
            self.assertEqual(context_files[0].path, "AGENTS.md")
            self.assertIn("Use the repository conventions.", context_files[0].content)

    def test_load_workspace_context_files_loads_companion_files_in_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            (workspace / "AGENTS.md").write_text("agent rules", encoding="utf-8")
            (workspace / "SOUL.md").write_text("persona", encoding="utf-8")
            (workspace / "TOOLS.md").write_text("tool guide", encoding="utf-8")

            context_files = load_workspace_context_files(str(workspace))

            self.assertEqual(
                [item.path for item in context_files],
                ["AGENTS.md", "SOUL.md", "TOOLS.md"],
            )
            self.assertEqual(
                [item.content for item in context_files],
                ["agent rules", "persona", "tool guide"],
            )

    def test_load_workspace_context_files_prefers_agent_markdown_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            (workspace / "AGENT.md").write_text("new agent rules", encoding="utf-8")
            (workspace / "AGENTS.md").write_text("legacy agent rules", encoding="utf-8")

            context_files = load_workspace_context_files(str(workspace))

            self.assertEqual([item.path for item in context_files], ["AGENT.md"])
            self.assertEqual([item.content for item in context_files], ["new agent rules"])

    def test_load_workspace_context_files_refreshes_when_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            agents = workspace / "AGENTS.md"
            agents.write_text("first version", encoding="utf-8")

            first = load_workspace_context_files(str(workspace))
            agents.write_text("second version with more text", encoding="utf-8")
            second = load_workspace_context_files(str(workspace))

            self.assertEqual(first[0].content, "first version")
            self.assertEqual(second[0].content, "second version with more text")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is unavailable")
    def test_load_workspace_context_files_rejects_symlinked_agents_file_outside_workspace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            outside = root / "outside"
            workspace.mkdir()
            outside.mkdir()
            outside_agents = outside / "AGENTS.md"
            outside_agents.write_text(
                "outside content should not be injected",
                encoding="utf-8",
            )
            os.symlink(outside_agents, workspace / "AGENTS.md")

            context_files = load_workspace_context_files(str(workspace))

            self.assertEqual(context_files, ())
