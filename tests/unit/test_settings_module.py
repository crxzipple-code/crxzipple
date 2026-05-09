from __future__ import annotations

import unittest

from crxzipple.modules.settings import (
    CreateSettingsResourceInput,
    PublishSettingsVersionInput,
    RollbackSettingsResourceInput,
    UpdateSettingsResourceInput,
    UpsertSettingsOverrideInput,
    create_in_memory_settings_services,
)
from crxzipple.modules.settings.domain import SettingsActionStatus


class SettingsModuleTestCase(unittest.TestCase):
    def test_create_update_publish_disable_enable_and_rollback_in_memory(self) -> None:
        services = create_in_memory_settings_services()

        created = services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="llm:default",
                resource_kind="llm_profile",
                owner_module="llm",
                payload={
                    "provider": "openai",
                    "model_name": "gpt-4.1",
                    "timeout_seconds": 60,
                },
                actor="operator",
                reason="bootstrap default llm",
                publish=True,
            ),
        )
        self.assertEqual(created.status, "succeeded")
        self.assertEqual(created.version.version_number, 1)
        self.assertEqual(created.resource.active_version_id, "llm:default:v1")

        updated = services.actions.update_resource(
            UpdateSettingsResourceInput(
                resource_id="llm:default",
                payload={
                    "provider": "openai",
                    "model_name": "gpt-4.1-mini",
                    "timeout_seconds": 30,
                },
                actor="operator",
                reason="switch default llm",
                publish=True,
            ),
        )
        self.assertEqual(updated.version.version_number, 2)
        self.assertEqual(
            services.queries.get_effective("llm:default").effective_value["model_name"],
            "gpt-4.1-mini",
        )

        disabled = services.actions.disable_resource("llm:default", actor="operator")
        self.assertFalse(disabled.resource.enabled)
        self.assertFalse(services.queries.get_effective("llm:default").effective_value["enabled"])

        enabled = services.actions.enable_resource("llm:default", actor="operator")
        self.assertTrue(enabled.resource.enabled)

        rolled_back = services.actions.rollback_resource(
            RollbackSettingsResourceInput(
                resource_id="llm:default",
                target_version_id="llm:default:v1",
                actor="operator",
                reason="rollback bad model choice",
            ),
        )
        self.assertEqual(rolled_back.version.id, "llm:default:v1")
        self.assertEqual(
            services.queries.get_effective("llm:default").effective_value["model_name"],
            "gpt-4.1",
        )
        self.assertGreaterEqual(len(services.queries.list_audits()), 5)

    def test_environment_override_affects_effective_resolution_trace(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="runtime:defaults",
                resource_kind="runtime_defaults",
                owner_module="runtime",
                payload={
                    "tool_worker": {"max_in_flight": 2},
                    "orchestration": {"queue_poll_seconds": 1},
                },
                reason="bootstrap runtime defaults",
                publish=True,
            ),
        )

        override = services.actions.upsert_override(
            UpsertSettingsOverrideInput(
                resource_id="runtime:defaults",
                override_id="runtime:dev",
                environment="dev",
                values={"tool_worker": {"max_in_flight": 8}},
                reason="developer workstation can run more tools",
            ),
        )
        resolution = services.queries.get_effective("runtime:defaults", environment="dev")

        self.assertEqual(override.status, "succeeded")
        self.assertEqual(resolution.effective_value["tool_worker"]["max_in_flight"], 8)
        self.assertEqual(resolution.overrides[0].override_id, "runtime:dev")
        self.assertEqual(resolution.sources[-1].source_kind, "environment_override")

        services.actions.disable_override("runtime:dev", reason="disable dev override")
        base_resolution = services.queries.get_effective("runtime:defaults", environment="dev")
        self.assertEqual(base_resolution.effective_value["tool_worker"]["max_in_flight"], 2)
        self.assertEqual(base_resolution.overrides, ())

    def test_validation_failure_does_not_mutate_published_state(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="memory:default",
                resource_kind="memory_config",
                owner_module="memory",
                payload={"retrieval_backend": "keyword", "timeout_seconds": 5},
                reason="bootstrap memory defaults",
                publish=True,
            ),
        )

        failed = services.actions.update_resource(
            UpdateSettingsResourceInput(
                resource_id="memory:default",
                payload={"retrieval_backend": "vector", "timeout_seconds": 0},
                reason="invalid timeout",
                publish=True,
            ),
        )

        self.assertEqual(failed.status, "validation_failed")
        self.assertFalse(failed.validation.ok)
        self.assertEqual(len(services.queries.list_versions("memory:default")), 1)
        self.assertEqual(
            services.queries.get_effective("memory:default").effective_value["retrieval_backend"],
            "keyword",
        )
        self.assertEqual(services.queries.list_audits()[-1].status, SettingsActionStatus.FAILED)

    def test_publish_latest_draft_separately(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="tool:provider:weather",
                resource_kind="tool_provider",
                owner_module="tool",
                payload={"provider_kind": "openapi", "base_url": "https://weather.test"},
                reason="create provider",
            ),
        )

        self.assertIsNone(services.queries.get_resource("tool:provider:weather").active_version_id)
        published = services.actions.publish_version(
            PublishSettingsVersionInput(
                resource_id="tool:provider:weather",
                reason="publish provider",
            ),
        )

        self.assertEqual(published.status, "succeeded")
        self.assertEqual(published.resource.active_version_id, "tool:provider:weather:v1")
        self.assertEqual(
            services.queries.get_effective("tool:provider:weather").effective_value["provider_kind"],
            "openapi",
        )


if __name__ == "__main__":
    unittest.main()
