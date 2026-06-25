from __future__ import annotations

import unittest
from types import SimpleNamespace

from crxzipple.modules.settings import (
    CreateSettingsResourceInput,
    SettingsEffectiveConfigMaterializer,
    create_bootstrap_settings_services,
    create_in_memory_settings_services,
    import_core_settings_resources,
    seed_core_settings_resources,
)


class CountingSettingsQueryProxy:
    def __init__(self, wrapped) -> None:
        self.wrapped = wrapped
        self.list_resources_calls: dict[str | None, int] = {}
        self.get_effective_calls: dict[str, int] = {}
        self.list_effective_payloads_calls: dict[str, int] = {}

    def list_resources(self, *, resource_kind=None, owner_module=None):
        del owner_module
        self.list_resources_calls[resource_kind] = (
            self.list_resources_calls.get(resource_kind, 0) + 1
        )
        return self.wrapped.list_resources(resource_kind=resource_kind)

    def get_effective(self, resource_id: str, *, environment=None):
        self.get_effective_calls[resource_id] = (
            self.get_effective_calls.get(resource_id, 0) + 1
        )
        return self.wrapped.get_effective(resource_id, environment=environment)

    def list_effective_payloads(self, *, resource_kind: str, environment=None):
        del environment
        self.list_effective_payloads_calls[resource_kind] = (
            self.list_effective_payloads_calls.get(resource_kind, 0) + 1
        )
        return self.wrapped.list_effective_payloads(resource_kind=resource_kind)


class SettingsMaterializationTestCase(unittest.TestCase):
    def test_bootstrap_settings_materializes_shared_runtime_configs(self) -> None:
        services = create_bootstrap_settings_services(
            SimpleNamespace(
                llm_profiles=(
                    {
                        "id": "primary",
                        "provider": "openai",
                        "api_family": "responses",
                        "model_name": "gpt-4.1",
                        "capabilities": ("chat", "tools"),
                    },
                ),
                tool_local_paths=("/tmp/crxzipple/tools",),
                tool_openapi_providers=(
                    {
                        "name": "weather",
                        "spec_location": "/tmp/weather.yaml",
                        "base_url": "https://weather.test",
                    },
                ),
                tool_mcp_providers=(),
                channel_profiles=(),
                agent_profiles=(),
                memory_retrieval_backend="hybrid",
                memory_storage_root="/tmp/crxzipple/memory",
                memory_vector_provider="local",
                memory_watch_interval_seconds=15.0,
                orchestration_run_lease_seconds=45,
                tool_worker_max_in_flight=7,
                tool_run_max_attempts=5,
                environment="test",
            ),
        )
        materializer = SettingsEffectiveConfigMaterializer(services.queries)

        tool_roots = materializer.tool_roots()
        tool_providers = materializer.tool_providers()
        memory = materializer.memory_config()
        runtime = materializer.runtime_defaults()

        self.assertEqual(materializer.legacy_llm_profile_payloads(), ())
        self.assertEqual(materializer.legacy_agent_profile_payloads(), ())
        self.assertEqual(materializer.legacy_channel_profile_payloads(), ())
        self.assertEqual(tool_roots[0].root_id, "local-root-1")
        self.assertEqual(tool_roots[0].path, "/tmp/crxzipple/tools")
        self.assertEqual(tool_providers[0].provider_id, "weather")
        self.assertEqual(tool_providers[0].spec_path, "/tmp/weather.yaml")
        self.assertIsNotNone(memory)
        self.assertEqual(memory.retrieval_backend, "hybrid")
        self.assertEqual(memory.storage_root, "/tmp/crxzipple/memory")
        self.assertIsNotNone(runtime)
        self.assertEqual(runtime.orchestration["run_lease_seconds"], 45)
        self.assertEqual(runtime.tool_worker["max_in_flight"], 7)
        self.assertEqual(runtime.tool_worker["run_max_attempts"], 5)
        access_bindings = {
            binding["binding_id"]: binding
            for config in materializer.access_configs()
            for binding in config.credential_bindings
        }
        self.assertEqual(
            access_bindings["openai-api-key"]["source_ref"],
            "OPENAI_API_KEY",
        )
        self.assertEqual(
            access_bindings["codex-oauth-default"]["binding_kind"],
            "oauth2_account",
        )
        self.assertEqual(materializer.warnings, ())

    def test_materializer_reuses_effective_payloads_for_same_kind(self) -> None:
        services = create_bootstrap_settings_services(
            SimpleNamespace(
                llm_profiles=(),
                tool_local_paths=("/tmp/crxzipple/tools",),
                tool_openapi_providers=(
                    {
                        "name": "weather",
                        "spec_location": "/tmp/weather.yaml",
                        "base_url": "https://weather.test",
                    },
                ),
                tool_mcp_providers=(),
                channel_profiles=(),
                agent_profiles=(),
                environment="test",
            ),
        )
        query = CountingSettingsQueryProxy(services.queries)
        materializer = SettingsEffectiveConfigMaterializer(query)

        self.assertEqual(len(materializer.tool_roots()), 1)
        self.assertEqual(len(materializer.tool_providers()), 1)

        self.assertEqual(query.list_effective_payloads_calls.get("tool-catalog"), 1)
        self.assertEqual(query.list_resources_calls, {})
        self.assertEqual(query.get_effective_calls, {})

    def test_startup_seed_does_not_overwrite_existing_runtime_defaults(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="defaults",
                resource_kind="runtime-defaults",
                owner_module="runtime",
                payload={
                    "config_id": "defaults",
                    "enabled": True,
                    "orchestration": {"run_lease_seconds": 99},
                    "tool_worker": {"max_in_flight": 8},
                },
                reason="user published runtime defaults",
                publish=True,
            ),
        )

        result = seed_core_settings_resources(
            SimpleNamespace(
                environment="test",
                llm_profiles=(),
                tool_local_paths=(),
                tool_openapi_providers=(),
                tool_mcp_providers=(),
                channel_profiles=(),
                agent_profiles=(),
                orchestration_run_lease_seconds=11,
                tool_worker_max_in_flight=2,
            ),
            services=services,
        )
        runtime = SettingsEffectiveConfigMaterializer(services.queries).runtime_defaults()

        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertGreaterEqual(result.skipped, 1)
        self.assertEqual(runtime.orchestration["run_lease_seconds"], 99)
        self.assertEqual(runtime.tool_worker["max_in_flight"], 8)

    def test_explicit_import_updates_runtime_defaults(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="defaults",
                resource_kind="runtime-defaults",
                owner_module="runtime",
                payload={
                    "config_id": "defaults",
                    "enabled": True,
                    "orchestration": {"run_lease_seconds": 99},
                    "tool_worker": {"max_in_flight": 8},
                },
                reason="user published runtime defaults",
                publish=True,
            ),
        )

        result = import_core_settings_resources(
            SimpleNamespace(
                environment="test",
                llm_profiles=(),
                tool_local_paths=(),
                tool_openapi_providers=(),
                tool_mcp_providers=(),
                channel_profiles=(),
                agent_profiles=(),
                orchestration_run_lease_seconds=11,
                tool_worker_max_in_flight=2,
            ),
            services=services,
            actor="unit-test",
            reason="explicit runtime defaults import",
        )
        runtime = SettingsEffectiveConfigMaterializer(services.queries).runtime_defaults()

        self.assertEqual(result.updated, 1)
        self.assertGreaterEqual(len(result.audit_refs), 1)
        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertEqual(runtime.orchestration["run_lease_seconds"], 11)
        self.assertEqual(runtime.tool_worker["max_in_flight"], 2)

    def test_environment_snapshot_is_seeded_not_live_runtime_truth(self) -> None:
        settings = SimpleNamespace(
            environment="initial-env",
            llm_profiles=(),
            tool_local_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            channel_profiles=(),
            agent_profiles=(),
        )
        services = create_bootstrap_settings_services(settings)

        settings.environment = "mutated-env"

        seeded = services.queries.get_effective("initial-env").effective_value
        self.assertEqual(seeded["environment"], "initial-env")
        self.assertNotIn(
            "mutated-env",
            {resource.id for resource in services.queries.list_resources()},
        )

    def test_missing_kind_returns_empty_or_none(self) -> None:
        services = create_in_memory_settings_services()
        materializer = SettingsEffectiveConfigMaterializer(services.queries)

        self.assertEqual(materializer.legacy_llm_profile_payloads(), ())
        self.assertEqual(materializer.tool_roots(), ())
        self.assertEqual(materializer.tool_providers(), ())
        self.assertEqual(materializer.legacy_channel_profile_payloads(), ())
        self.assertEqual(materializer.access_configs(), ())
        self.assertIsNone(materializer.memory_config())
        self.assertIsNone(materializer.runtime_defaults())
        self.assertEqual(materializer.warnings, ())

    def test_tool_catalog_enablement_is_not_materialized_by_settings(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="legacy-tool-enable-weather",
                resource_kind="tool-catalog",
                owner_module="settings",
                payload={
                    "tool_id": "weather.forecast",
                    "enabled": False,
                    "pattern": "weather.*",
                },
                reason="legacy Settings-owned tool enablement",
                publish=True,
            ),
        )
        materializer = SettingsEffectiveConfigMaterializer(services.queries)

        self.assertFalse(hasattr(materializer, "tool_enablements"))
        self.assertEqual(materializer.tool_roots(), ())
        self.assertEqual(materializer.tool_providers(), ())
        self.assertEqual(materializer.warnings, ())

    def test_access_declarations_materialize_as_settings_truth(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="access:asset:openai",
                resource_kind="access-assets",
                owner_module="access",
                payload={
                    "access_declaration_kind": "asset",
                    "asset_id": "openai-api",
                    "asset_kind": "connection_asset",
                    "display_name": "OpenAI API",
                    "governance_scope": "workspace",
                    "enabled": True,
                    "metadata": {"owner": "settings"},
                },
                reason="seed access asset from settings",
                publish=True,
            ),
        )
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="access:credential:openai-key",
                resource_kind="access-assets",
                owner_module="access",
                payload={
                    "access_declaration_kind": "credential_binding",
                    "binding_id": "openai-api-key",
                    "asset_id": "openai-api",
                    "source_kind": "env",
                    "source_ref": "OPENAI_API_KEY",
                    "metadata": {"secret_preview": "redacted"},
                },
                reason="seed access credential binding from settings",
                publish=True,
            ),
        )
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="access:provider-scope:openai-llm",
                resource_kind="access-assets",
                owner_module="access",
                payload={
                    "access_declaration_kind": "provider_scope_enablement",
                    "provider_id": "openai",
                    "scope": "llm",
                    "metadata": {"reason": "disabled in test"},
                },
                reason="seed access provider scope from settings",
                publish=True,
            ),
        )
        services.actions.disable_resource(
            "access:provider-scope:openai-llm",
            reason="disable provider scope from settings",
        )
        materializer = SettingsEffectiveConfigMaterializer(services.queries)

        configs = materializer.access_configs()

        assets = {
            str(asset["asset_id"]): asset
            for config in configs
            for asset in config.assets
        }
        bindings = {
            str(binding["binding_id"]): binding
            for config in configs
            for binding in config.credential_bindings
        }
        provider_scopes = {
            f"{scope['provider_id']}:{scope['scope']}": scope
            for config in configs
            for scope in config.provider_scope_enablements
        }
        self.assertEqual(assets["openai-api"]["display_name"], "OpenAI API")
        self.assertEqual(bindings["openai-api-key"]["source_ref"], "OPENAI_API_KEY")
        self.assertFalse(provider_scopes["openai:llm"]["enabled"])
        self.assertNotIn("access_declaration_kind", assets["openai-api"])
        self.assertNotIn("runtime_readiness", assets["openai-api"])
        self.assertEqual(materializer.warnings, ())

    def test_bad_payload_is_skipped_and_reported_as_warning(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="broken",
                resource_kind="llm-profiles",
                owner_module="llm",
                payload={"provider": "openai", "api_family": "responses"},
                reason="bad bootstrap fixture",
                publish=True,
            ),
        )
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="good",
                resource_kind="llm-profiles",
                owner_module="llm",
                payload={
                    "provider": "openai",
                    "api_family": "responses",
                    "model_name": "gpt-4.1-mini",
                },
                reason="good bootstrap fixture",
                publish=True,
            ),
        )
        materializer = SettingsEffectiveConfigMaterializer(services.queries)

        profiles = materializer.legacy_llm_profile_payloads()

        self.assertEqual(
            tuple(profile["profile_id"] for profile in profiles), ("good",)
        )
        self.assertEqual(len(materializer.warnings), 1)
        self.assertEqual(materializer.warnings[0].resource_id, "broken")
        self.assertEqual(materializer.warnings[0].code, "invalid_effective_payload")


if __name__ == "__main__":
    unittest.main()
