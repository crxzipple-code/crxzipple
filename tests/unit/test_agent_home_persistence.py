from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.value_objects import (
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.infrastructure import home_config, home_registry


class AgentHomePersistenceTestCase(unittest.TestCase):
    def test_home_config_write_preserves_previous_config_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"
            original = _profile("writer", "Writer", home_dir)
            updated = _profile("writer", "Writer Updated", home_dir)

            config_path = home_config.write_agent_home_config(
                original,
                home_dir=str(home_dir),
            )
            previous_body = config_path.read_text(encoding="utf-8")

            with patch.object(home_config.os, "replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    home_config.write_agent_home_config(updated, home_dir=str(home_dir))

            self.assertEqual(config_path.read_text(encoding="utf-8"), previous_body)
            self.assertEqual(list(home_dir.glob(".agent.json.*.tmp")), [])

    def test_registry_write_preserves_previous_entries_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "registry"
            writer_home = Path(tempdir) / "homes" / "writer"
            reviewer_home = Path(tempdir) / "homes" / "reviewer"

            home_registry.register_agent_home(
                root,
                agent_id="writer",
                home_dir=str(writer_home),
            )
            registry_path = root / "registry.json"
            previous_body = registry_path.read_text(encoding="utf-8")

            with patch.object(home_registry.os, "replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    home_registry.register_agent_home(
                        root,
                        agent_id="reviewer",
                        home_dir=str(reviewer_home),
                    )

            self.assertEqual(registry_path.read_text(encoding="utf-8"), previous_body)
            self.assertEqual(
                home_registry.list_registered_agent_homes(root),
                (("writer", str(writer_home)),),
            )
            self.assertEqual(list(root.glob(".registry.json.*.tmp")), [])

    def test_registry_updates_are_isolated_across_concurrent_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "registry"
            homes_root = Path(tempdir) / "homes"
            agent_ids = tuple(f"agent-{index}" for index in range(12))

            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [
                    executor.submit(
                        home_registry.register_agent_home,
                        root,
                        agent_id=agent_id,
                        home_dir=str(homes_root / agent_id),
                    )
                    for agent_id in agent_ids
                ]
                for future in futures:
                    future.result()

            self.assertEqual(
                home_registry.list_registered_agent_homes(root),
                tuple(
                    (agent_id, str(homes_root / agent_id))
                    for agent_id in sorted(agent_ids)
                ),
            )


def _profile(agent_id: str, name: str, home_dir: Path) -> AgentProfile:
    return AgentProfile(
        id=agent_id,
        name=name,
        llm_routing_policy=AgentLlmRoutingPolicy(
            default_llm_id="openai.gpt-5.4-mini",
        ),
        runtime_preferences=AgentRuntimePreferences(home_dir=str(home_dir)),
    )


if __name__ == "__main__":
    unittest.main()
