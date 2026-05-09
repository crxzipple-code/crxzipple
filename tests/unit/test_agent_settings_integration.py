from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from crxzipple.core.config import AgentProfileSettings, load_settings
from crxzipple.modules.agent.application import agent_profile_input_from_settings
from crxzipple.modules.settings import (
    CreateSettingsResourceInput,
    SettingsEffectiveConfigMaterializer,
    create_in_memory_settings_services,
)
from tests.unit.support import SqliteTestHarness


class AgentSettingsIntegrationTestCase(unittest.TestCase):
    def test_legacy_settings_payload_maps_to_runtime_input(self) -> None:
        config = {
            "profile_id": "builder",
            "name": "Builder",
            "description": "Builds local changes.",
            "display_name": "Builder Agent",
            "instructions_path": "AGENT.md",
            "model_profile_id": "openai.gpt-5.4-mini",
            "tool_ids": ("shell", "shell", "apply_patch"),
            "skill_ids": ("memory-recall",),
            "memory_space": "builder-space",
            "identity": {"emoji": ":hammer:"},
            "instruction_policy": {"system_prompt": "Be direct."},
            "execution_policy": {"timeout_seconds": 90, "max_turns": 8},
            "runtime_preferences": {"sandbox_mode": "sandbox"},
        }

        data = agent_profile_input_from_settings(config)

        self.assertEqual(data.id, "builder")
        self.assertEqual(data.name, "Builder")
        self.assertEqual(data.description, "Builds local changes.")
        self.assertEqual(data.identity.display_name, "Builder Agent")
        self.assertEqual(data.identity.emoji, ":hammer:")
        self.assertEqual(data.llm_routing_policy.default_llm_id, "openai.gpt-5.4-mini")
        self.assertEqual(data.execution_policy.timeout_seconds, 90)
        self.assertEqual(data.execution_policy.max_turns, 8)
        self.assertEqual(data.runtime_preferences.sandbox_mode, "sandbox")
        self.assertEqual(
            data.runtime_preferences.attrs["tool_ids"],
            ["shell", "apply_patch"],
        )
        self.assertEqual(
            data.runtime_preferences.attrs["skill_ids"],
            ["memory-recall"],
        )
        self.assertEqual(
            data.runtime_preferences.attrs["instructions_path"], "AGENT.md"
        )
        sidecar = json.loads(data.home_sidecar_files[".state/memory-binding.json"])
        self.assertEqual(sidecar["space_id"], "builder-space")

    def test_materializer_reads_effective_agent_profile_resources(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="writer",
                resource_kind="agent_profile",
                owner_module="agent",
                payload={
                    "name": "Writer",
                    "description": "Writes concise summaries.",
                    "model_profile_id": "openai.gpt-5.4-mini",
                    "runtime_preferences": {"sandbox_mode": "sandbox"},
                },
                reason="test agent profile",
                publish=True,
            ),
        )
        materializer = SettingsEffectiveConfigMaterializer(services.queries)

        profiles = materializer.legacy_agent_profile_payloads()

        self.assertEqual(
            tuple(profile["profile_id"] for profile in profiles), ("writer",)
        )
        self.assertEqual(profiles[0]["name"], "Writer")
        self.assertEqual(profiles[0]["model_profile_id"], "openai.gpt-5.4-mini")
        self.assertEqual(
            profiles[0]["runtime_preferences"]["sandbox_mode"],
            "sandbox",
        )
        self.assertEqual(materializer.warnings, ())

    def test_container_bootstraps_agent_profiles_from_effective_settings(self) -> None:
        harness = SqliteTestHarness()
        self.addCleanup(harness.close)
        home_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home_root, True)
        home_dir = home_root / "writer-home"
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            agent_profiles=(
                AgentProfileSettings(
                    id="writer",
                    name="Writer",
                    description="Default writer profile.",
                    identity={"display_name": "Writer Agent"},
                    instruction_policy={
                        "system_prompt": "Be concise.",
                        "stream_by_default": True,
                    },
                    llm_routing_policy={"default_llm_id": "openai.gpt-5.4-mini"},
                    execution_policy={"timeout_seconds": 75, "max_turns": 7},
                    runtime_preferences={
                        "home_dir": str(home_dir),
                        "sandbox_mode": "sandbox",
                    },
                ),
            ),
            channel_profiles=(),
            llm_profiles=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
        )

        container = harness.build_container(settings=settings)
        profile = container.agent_service.get_profile("writer")

        self.assertEqual(profile.name, "Writer")
        self.assertEqual(profile.identity.display_name, "Writer Agent")
        self.assertEqual(profile.execution_policy.timeout_seconds, 75)
        self.assertEqual(profile.runtime_preferences.home_dir, str(home_dir))
        self.assertTrue((home_dir / "agent.json").is_file())


if __name__ == "__main__":
    unittest.main()
