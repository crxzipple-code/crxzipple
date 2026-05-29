from __future__ import annotations

import inspect
import unittest

import crxzipple.shared.settings as shared_settings
from crxzipple.shared.settings import (
    ConfigResolution,
    ConfigSource,
    EnvironmentOverrideConfig,
    MemoryConfig,
    RuntimeDefaultsConfig,
    SettingsResourceRef,
)


class SettingsContractsTestCase(unittest.TestCase):
    def test_resource_ref_and_resolution_trace_round_trip(self) -> None:
        ref = SettingsResourceRef(
            resource_id=" llm:default ",
            resource_kind=" llm_profile ",
            owner_module=" llm ",
            display_name=" Default LLM ",
        )
        source = ConfigSource(
            source_id="version:llm:default:v1",
            source_kind="published_version",
            resource=ref,
            version_id="llm:default:v1",
            value={"model_name": "gpt-4.1"},
        )
        override = ConfigSource(
            source_id="override:dev",
            source_kind="environment_override",
            resource=ref,
            override_id="dev",
            priority=200,
            value={"timeout_seconds": 30},
        )

        resolution = ConfigResolution(
            resource=ref,
            effective_value={"model_name": "gpt-4.1", "timeout_seconds": 30},
            sources=(source, override),
            overrides=(override,),
            snapshot_id="snap-1",
        )
        payload = resolution.to_payload()

        self.assertEqual(ref.resource_id, "llm:default")
        self.assertEqual(ref.key, ("llm_profile", "llm:default"))
        self.assertEqual(resolution.value["timeout_seconds"], 30)
        self.assertEqual(payload["resource"]["owner_module"], "llm")
        self.assertEqual(payload["sources"][0]["version_id"], "llm:default:v1")
        self.assertEqual(payload["overrides"][0]["override_id"], "dev")

    def test_config_dtos_round_trip_without_module_domain_entities(self) -> None:
        memory = MemoryConfig(
            config_id="default",
            retrieval_backend="hybrid",
            vector_provider="openai_compatible",
            vector_model="text-embedding-3-small",
            vector_base_url="https://api.openai.test/v1",
            vector_credential_binding_id="memory-openai-api-key",
            vector_timeout_seconds=45,
            watch_interval_seconds=10,
        )
        override = EnvironmentOverrideConfig(
            override_id="dev-llm",
            environment="dev",
            target=SettingsResourceRef(
                resource_id="default",
                resource_kind="llm_profile",
                owner_module="llm",
            ),
            values={"model_name": "gpt-4.1-mini"},
        )

        restored_memory = MemoryConfig.from_payload(memory.to_payload())
        self.assertEqual(restored_memory.retrieval_backend, "hybrid")
        self.assertEqual(restored_memory.vector_provider, "openai_compatible")
        self.assertEqual(restored_memory.vector_model, "text-embedding-3-small")
        self.assertEqual(restored_memory.vector_base_url, "https://api.openai.test/v1")
        self.assertEqual(
            restored_memory.vector_credential_binding_id, "memory-openai-api-key"
        )
        self.assertEqual(restored_memory.vector_timeout_seconds, 45)
        self.assertEqual(
            EnvironmentOverrideConfig.from_payload(
                override.to_payload()
            ).target.owner_module,
            "llm",
        )

        source = inspect.getsource(shared_settings)
        self.assertNotIn("crxzipple.modules.", source)
        self.assertFalse(hasattr(shared_settings, "LlmProfileConfig"))
        self.assertFalse(hasattr(shared_settings, "AgentProfileConfig"))
        self.assertFalse(hasattr(shared_settings, "ChannelProfileConfig"))
        self.assertFalse(hasattr(shared_settings, "ToolEnablementConfig"))

    def test_runtime_defaults_config_has_no_empty_daemon_bucket(self) -> None:
        runtime = RuntimeDefaultsConfig.from_payload(
            {
                "config_id": "defaults",
                "enabled": True,
                "orchestration": {"run_lease_seconds": 30},
                "tool_worker": {"max_in_flight": 4},
                "daemon": {"placeholder": True},
            }
        )

        self.assertEqual(runtime.orchestration["run_lease_seconds"], 30)
        self.assertEqual(runtime.tool_worker["max_in_flight"], 4)
        self.assertFalse(hasattr(runtime, "daemon"))
        self.assertNotIn("daemon", runtime.to_payload())


if __name__ == "__main__":
    unittest.main()
