from __future__ import annotations

import unittest

from crxzipple.modules.channels.application.settings_integration import (
    channel_profile_from_settings,
)
from crxzipple.modules.channels.application.services import (
    ChannelProfileApplicationService,
)
from crxzipple.modules.channels.infrastructure import (
    InMemoryChannelSystemConfigStore,
)
from crxzipple.modules.memory.application.settings_integration import (
    MemorySettingsBootstrapConfig,
    memory_bootstrap_config_from_settings,
)
from crxzipple.app.assembly.runtime_defaults import (
    RuntimeSettingsBootstrapConfig,
    runtime_bootstrap_config_from_settings,
)
from crxzipple.shared.settings import (
    MemoryConfig,
    RuntimeDefaultsConfig,
)


class ChannelMemoryRuntimeSettingsIntegrationTestCase(unittest.TestCase):
    def test_channel_bootstrap_payload_maps_to_domain_profile(self) -> None:
        profile = channel_profile_from_settings(
            {
                "channel_type": "lark",
                "enabled": True,
                "capabilities": {
                    "supports_streaming": True,
                    "supports_ack": True,
                    "metadata": {"mode": "event"},
                },
                "accounts": [
                    {
                        "account_id": "team-a",
                        "enabled": False,
                        "transport_mode": "pull",
                        "credential_bindings": {
                            "lark_app_id": "access-binding:lark-app-id",
                            "lark_app_secret": "access-binding:lark-app-secret",
                            "lark_verification_token": "access-binding:lark-token",
                        },
                        "metadata": {"tenant": "cn"},
                    },
                ],
                "metadata": {"source": "bootstrap"},
            },
        )

        self.assertEqual(profile.channel_type, "lark")
        self.assertTrue(profile.capabilities.supports_streaming)
        self.assertTrue(profile.capabilities.supports_ack)
        self.assertEqual(profile.accounts[0].account_id, "team-a")
        self.assertFalse(profile.accounts[0].enabled)
        self.assertEqual(
            profile.accounts[0].credential_bindings,
            {
                "lark_app_id": "access-binding:lark-app-id",
                "lark_app_secret": "access-binding:lark-app-secret",
                "lark_verification_token": "access-binding:lark-token",
            },
        )
        self.assertEqual(
            profile.accounts[0].metadata["lark_app_secret_binding"],
            "access-binding:lark-app-secret",
        )
        credential_requirements = profile.accounts[0].credential_requirements
        self.assertIsNotNone(credential_requirements)
        assert credential_requirements is not None
        self.assertEqual(len(credential_requirements.requirements), 5)
        self.assertEqual(profile.metadata["source"], "bootstrap")

    def test_legacy_channel_payload_maps_to_domain_profile(self) -> None:
        profile = channel_profile_from_settings(
            {
                "profile_id": "web-main",
                "channel_kind": "web",
                "account_id": "browser",
                "display_name": "Web",
                "transport": {"mode": "push"},
                "routing": {"default_agent_id": "assistant"},
                "metadata": {"owner": "settings"},
            },
        )

        self.assertEqual(profile.channel_type, "web")
        self.assertEqual(profile.accounts[0].account_id, "browser")
        self.assertEqual(profile.accounts[0].metadata["transport"], {"mode": "push"})
        self.assertEqual(profile.metadata["profile_id"], "web-main")
        self.assertEqual(profile.metadata["routing"], {"default_agent_id": "assistant"})

    def test_channel_settings_helper_does_not_persist_profile_without_owner_service(
        self,
    ) -> None:
        service = ChannelProfileApplicationService(
            system_config_store=InMemoryChannelSystemConfigStore(),
        )
        profile = channel_profile_from_settings(
            {
                "channel_type": "webhook",
                "enabled": False,
                "accounts": [{"account_id": "default"}],
            },
        )

        self.assertIsNone(service.get_profile("webhook"))
        saved = service.upsert_profile(profile)

        self.assertFalse(saved.enabled)
        self.assertEqual(service.get_profile("webhook"), saved)

    def test_memory_bootstrap_payload_maps_to_bootstrap_config(self) -> None:
        config = memory_bootstrap_config_from_settings(
            {
                "retrieval_backend": "vector",
                "vector_provider": "openai_compatible",
                "vector_model": "text-embedding-3-small",
                "vector_base_url": "https://api.openai.test/v1",
                "vector_credential_binding_id": "memory-openai-api-key",
                "vector_timeout_seconds": "45",
                "watch_interval_seconds": "12.5",
            },
        )

        self.assertEqual(
            config,
            MemorySettingsBootstrapConfig(
                retrieval_backend="vector",
                vector_provider="openai_compatible",
                vector_model="text-embedding-3-small",
                vector_base_url="https://api.openai.test/v1",
                vector_credential_binding_id="memory-openai-api-key",
                vector_timeout_seconds=45,
                watch_interval_seconds=12.5,
            ),
        )

    def test_memory_dto_maps_to_bootstrap_config(self) -> None:
        config = memory_bootstrap_config_from_settings(
            MemoryConfig(
                config_id="default",
                retrieval_backend="hybrid",
                vector_provider="local",
                watch_interval_seconds=10,
                defaults={
                    "vector_model": "local-test-v1",
                    "vector_timeout_seconds": 5,
                },
            ),
        )

        self.assertEqual(config.retrieval_backend, "hybrid")
        self.assertEqual(config.vector_provider, "local")
        self.assertEqual(config.vector_model, "local-test-v1")
        self.assertEqual(config.vector_timeout_seconds, 5)
        self.assertEqual(config.watch_interval_seconds, 10.0)

    def test_runtime_bootstrap_payload_maps_to_bootstrap_config(self) -> None:
        config = runtime_bootstrap_config_from_settings(
            {
                "orchestration": {
                    "run_lease_seconds": 45,
                    "run_heartbeat_seconds": 6.5,
                    "executor_max_concurrent_assignments": 8,
                    "auto_compaction_enabled": "false",
                    "auto_compaction_reserve_tokens": 30_000,
                    "auto_compaction_soft_threshold_tokens": 5_000,
                },
                "tool_worker": {
                    "run_max_attempts": 5,
                    "run_lease_seconds": 55,
                    "run_heartbeat_seconds": 7.5,
                    "max_in_flight": 9,
                    "default_run_concurrency": 6,
                    "image_run_concurrency": 3,
                    "shared_state_run_concurrency": 2,
                    "remote_default_max_concurrency": 12,
                },
            },
        )

        self.assertEqual(
            config,
            RuntimeSettingsBootstrapConfig(
                orchestration_run_lease_seconds=45,
                orchestration_run_heartbeat_seconds=6.5,
                orchestration_executor_max_concurrent_assignments=8,
                orchestration_auto_compaction_enabled=False,
                orchestration_auto_compaction_reserve_tokens=30_000,
                orchestration_auto_compaction_soft_threshold_tokens=5_000,
                tool_run_max_attempts=5,
                tool_run_lease_seconds=55,
                tool_run_heartbeat_seconds=7.5,
                tool_worker_max_in_flight=9,
                tool_worker_default_run_concurrency=6,
                tool_worker_image_run_concurrency=3,
                tool_worker_shared_state_run_concurrency=2,
                tool_remote_default_max_concurrency=12,
            ),
        )

    def test_runtime_dto_maps_to_bootstrap_config(self) -> None:
        config = runtime_bootstrap_config_from_settings(
            RuntimeDefaultsConfig(
                config_id="defaults",
                orchestration={
                    "run_lease_seconds": 33,
                    "run_heartbeat_seconds": 4.5,
                    "executor_max_concurrent_assignments": 7,
                    "auto_compaction_enabled": True,
                    "auto_compaction_reserve_tokens": 12_000,
                    "auto_compaction_soft_threshold_tokens": 2_000,
                },
                tool_worker={
                    "run_max_attempts": 4,
                    "run_lease_seconds": 44,
                    "run_heartbeat_seconds": 3.5,
                    "max_in_flight": 11,
                    "default_run_concurrency": 5,
                    "image_run_concurrency": 2,
                    "shared_state_run_concurrency": 1,
                    "remote_default_max_concurrency": 13,
                },
            ),
        )

        self.assertEqual(config.orchestration_run_lease_seconds, 33)
        self.assertEqual(config.orchestration_executor_max_concurrent_assignments, 7)
        self.assertEqual(config.tool_run_max_attempts, 4)
        self.assertEqual(config.tool_worker_max_in_flight, 11)
        self.assertEqual(config.tool_worker_default_run_concurrency, 5)
        self.assertEqual(config.tool_remote_default_max_concurrency, 13)


if __name__ == "__main__":
    unittest.main()
