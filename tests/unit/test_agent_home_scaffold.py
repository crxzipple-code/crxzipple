from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.value_objects import (
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.infrastructure.home_scaffold import (
    ensure_agent_home_scaffold,
)


class AgentHomeScaffoldTestCase(unittest.TestCase):
    def test_scaffold_skips_legacy_workspace_only_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            profile = AgentProfile(
                id="assistant",
                name="Assistant",
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
                runtime_preferences=AgentRuntimePreferences(workspace=str(root)),
            )

            ensure_agent_home_scaffold(profile)

            self.assertFalse((root / "agent.json").exists())
            self.assertFalse((root / "AGENT.md").exists())
            self.assertFalse((root / "memory").exists())

    def test_scaffold_respects_existing_agent_alias_files(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "AGENTS.md").write_text("legacy agent rules", encoding="utf-8")
            (root / "memory.md").write_text("legacy memory", encoding="utf-8")
            profile = AgentProfile(
                id="assistant",
                name="Assistant",
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="openai.gpt-5.4-mini",
                ),
                runtime_preferences=AgentRuntimePreferences(home_dir=str(root)),
            )

            ensure_agent_home_scaffold(profile)

            self.assertTrue((root / "agent.json").is_file())
            self.assertFalse((root / "AGENT.md").exists())
            self.assertEqual((root / "memory.md").read_text(encoding="utf-8"), "legacy memory")
            self.assertTrue((root / "skills").is_dir())
            self.assertTrue((root / ".state").is_dir())


if __name__ == "__main__":
    unittest.main()
