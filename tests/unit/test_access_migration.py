from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import unittest

from crxzipple.modules.access.application.importer import (
    AccessBootstrapImporter,
    AccessSettingsBootstrapImporter,
)
from crxzipple.modules.access.application.migration import (
    AccessMigration,
    AccessMigrationPlan,
    AccessMigrationSnapshot,
    build_access_migration_plan,
)
from crxzipple.modules.access.application.read_models import (
    AccessConsumerBindingReadModel,
)
from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.settings import (
    SettingsEffectiveConfigMaterializer,
    create_in_memory_settings_services,
)


@dataclass(frozen=True)
class LegacyLlmProfile:
    id: str
    provider: str
    api_family: str
    model_name: str
    credential_binding_id: str
    enabled: bool = True


@dataclass(frozen=True)
class LegacyToolSpec:
    id: str
    name: str
    provider_name: str
    access_requirement_sets: tuple[tuple[str, ...], ...]
    access_requirements: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class LegacyChannelAccount:
    account_id: str
    auth_ref: str | None = None
    enabled: bool = True
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LegacyChannelProfile:
    channel_type: str
    enabled: bool = True
    metadata: dict[str, object] = field(default_factory=dict)
    accounts: tuple[LegacyChannelAccount, ...] = ()


class InMemoryAccessGovernanceRepository:
    def __init__(self) -> None:
        self.assets: dict[str, object] = {}
        self.credential_bindings: dict[str, object] = {}
        self.consumer_bindings: dict[str, object] = {}

    def create_asset(self, record: object) -> object:
        self.assets[getattr(record, "asset_id")] = record
        return record

    def get_asset(self, asset_id: str) -> object | None:
        return self.assets.get(asset_id)

    def list_assets(self) -> tuple[object, ...]:
        return tuple(self.assets.values())

    def create_credential_binding(self, record: object) -> object:
        self.credential_bindings[getattr(record, "binding_id")] = record
        return record

    def get_credential_binding(self, binding_id: str) -> object | None:
        return self.credential_bindings.get(binding_id)

    def list_credential_bindings(self) -> tuple[object, ...]:
        return tuple(self.credential_bindings.values())

    def create_consumer_binding(self, record: object) -> object:
        self.consumer_bindings[getattr(record, "binding_id")] = record
        return record

    def get_consumer_binding(self, binding_id: str) -> object | None:
        return self.consumer_bindings.get(binding_id)

    def list_consumer_bindings(self) -> tuple[object, ...]:
        return tuple(self.consumer_bindings.values())


class AccessMigrationTests(unittest.TestCase):
    def test_scans_llm_tool_channel_and_env_without_secret_values(self) -> None:
        plan = build_access_migration_plan(
            AccessMigrationSnapshot(
                llm_profiles=(
                    LegacyLlmProfile(
                        id="gpt-main",
                        provider="openai",
                        api_family="responses",
                        model_name="gpt-5",
                        credential_binding_id="openai-api-key",
                    ),
                ),
                tool_specs=(
                    LegacyToolSpec(
                        id="search.docs",
                        name="Search docs",
                        provider_name="docs",
                        access_requirement_sets=(
                            ("openai:api_key(env:OPENAI_TOOL_KEY)",),
                            ("github:oauth_connector(repo_read)",),
                        ),
                    ),
                ),
                channel_profiles=(
                    LegacyChannelProfile(
                        channel_type="webhook",
                        metadata={
                            "webhook_signing_secret": "super-secret-webhook-token",
                            "access_requirements": ["env:WEBHOOK_ACCOUNT_TOKEN"],
                        },
                        accounts=(
                            LegacyChannelAccount(
                                account_id="default",
                                auth_ref="github:oauth_connector(repo_read)",
                                metadata={
                                    "lark_app_secret_binding": "env:LARK_APP_SECRET",
                                    "token": "super-secret-channel-token",
                                },
                            ),
                        ),
                    ),
                ),
                ready_auth_requirements=("gmail:oauth_connector(mail_read)",),
                ready_auth_requirements_env=(
                    "slack:oauth_connector(chat_write), env:READY_AUTH_TOKEN"
                ),
                source="unit-test",
            ),
        )

        self.assertGreaterEqual(len(plan.assets), 1)
        self.assertGreaterEqual(len(plan.credential_bindings), 1)
        self.assertGreaterEqual(len(plan.consumer_bindings), 1)

        payload = json.dumps(asdict(plan), sort_keys=True, default=str)
        self.assertIn("llm_profiles[*].credential_binding_id", payload)
        self.assertIn("tool.access_requirement_sets", payload)
        self.assertIn("CRXZIPPLE_READY_AUTH_REQUIREMENTS", payload)
        self.assertIn("OPENAI_TOOL_KEY", payload)
        self.assertIn("WEBHOOK_ACCOUNT_TOKEN", payload)
        self.assertIn("LARK_APP_SECRET", payload)

        self.assertNotIn("super-secret-webhook-token", payload)
        self.assertNotIn("super-secret-channel-token", payload)

    def test_thin_container_adapter_only_collects_snapshots(self) -> None:
        class Settings:
            llm_profiles = (
                {"id": "model", "credential_binding_id": "model-token"},
            )
            ready_auth_requirements = ("github:oauth_connector(repo_read)",)

        class ToolService:
            def list_specs(self) -> tuple[LegacyToolSpec, ...]:
                return (
                    LegacyToolSpec(
                        id="tool",
                        name="Tool",
                        provider_name="builtin",
                        access_requirement_sets=(("env:TOOL_TOKEN",),),
                    ),
                )

        class ChannelService:
            def list_profiles(self) -> tuple[LegacyChannelProfile, ...]:
                return (
                    LegacyChannelProfile(
                        channel_type="webhook",
                        metadata={"webhook_token_binding": "env:WEBHOOK_TOKEN"},
                    ),
                )

        class Container:
            settings = Settings()
            tool_service = ToolService()
            channel_profile_service = ChannelService()

        snapshot = AccessMigration.from_legacy_container(Container())
        plan = build_access_migration_plan(snapshot)
        payload = json.dumps(asdict(plan), sort_keys=True, default=str)

        self.assertIn("model-token", payload)
        self.assertIn("env:TOOL_TOKEN", payload)
        self.assertIn("env:WEBHOOK_TOKEN", payload)
        self.assertNotIn("runtime-abac.yaml", payload)

    def test_bootstrap_importer_writes_plan_once_without_secret_values(self) -> None:
        repository = InMemoryAccessGovernanceRepository()
        plan = build_access_migration_plan(
            AccessMigrationSnapshot(
                llm_profiles=(
                    LegacyLlmProfile(
                        id="model",
                        provider="openai",
                        api_family="responses",
                        model_name="gpt-5",
                        credential_binding_id="openai-api-key",
                    ),
                ),
                tool_specs=(
                    LegacyToolSpec(
                        id="search",
                        name="Search",
                        provider_name="builtin",
                        access_requirement_sets=(("env:SEARCH_TOKEN",),),
                    ),
                ),
                source="unit-test",
            ),
        )

        importer = AccessBootstrapImporter(repository)
        first = importer.import_plan(plan)
        second = importer.import_plan(plan)
        payload = json.dumps(
            {
                "assets": [asdict(item) for item in repository.assets.values()],
                "credentials": [
                    asdict(item) for item in repository.credential_bindings.values()
                ],
                "consumers": [
                    asdict(item) for item in repository.consumer_bindings.values()
                ],
            },
            sort_keys=True,
            default=str,
        )

        self.assertGreater(first.created["assets"], 0)
        self.assertGreater(first.created["credential_bindings"], 0)
        self.assertGreater(first.created["consumer_bindings"], 0)
        self.assertEqual(second.created["assets"], 0)
        self.assertEqual(second.created["credential_bindings"], 0)
        self.assertEqual(second.created["consumer_bindings"], 0)
        self.assertEqual(second.skipped["assets"], len(plan.assets))
        self.assertNotIn("super-secret-token", payload)

    def test_settings_bootstrap_importer_writes_access_plan_as_settings_truth(self) -> None:
        settings_services = create_in_memory_settings_services()
        plan = AccessMigrationPlan(
            assets=(
                AccessAssetRecord(
                    asset_id="asset_openai",
                    asset_kind="connection_asset",
                    display_name="OpenAI API",
                    governance_scope="workspace",
                    metadata={"source": "unit-test"},
                ),
            ),
            credential_bindings=(
                AccessCredentialBindingRecord(
                    binding_id="cred_openai",
                    asset_id="asset_openai",
                    binding_kind="api_key",
                    source_kind="env",
                    source_ref="OPENAI_API_KEY",
                    masked_preview="env:OPENAI_API_KEY",
                    metadata={"source": "unit-test"},
                ),
            ),
            consumer_bindings=(
                AccessConsumerBindingReadModel(
                    binding_id="consumer_llm_primary",
                    consumer_module="llm",
                    consumer_kind="llm_profile",
                    consumer_id="primary",
                    asset_id="asset_openai",
                    credential_binding_id="cred_openai",
                    requirement_sets=(("env:OPENAI_API_KEY",),),
                    metadata={"source": "unit-test"},
                ),
            ),
            provider_scope_enablements=(
                {"provider_id": "openai", "scope": "llm", "enabled": True},
            ),
            permission_enablements=(
                {
                    "permission_id": "tool.write",
                    "permission": "tool.write",
                    "scope": "workspace",
                    "enabled": False,
                },
            ),
            metadata={"source": "unit-test"},
        )

        importer = AccessSettingsBootstrapImporter(
            action_service=settings_services.actions,
            query_service=settings_services.queries,
        )
        first = importer.import_plan(plan, reason="import access settings plan")
        second = importer.import_plan(plan, reason="import access settings plan")
        materializer = SettingsEffectiveConfigMaterializer(settings_services.queries)
        configs = materializer.access_configs()
        payload = json.dumps(
            [config.to_payload() for config in configs],
            sort_keys=True,
            default=str,
        )

        self.assertEqual(first.imported_counts["assets"], 1)
        self.assertEqual(first.imported_counts["credential_bindings"], 1)
        self.assertEqual(first.imported_counts["consumer_bindings"], 1)
        self.assertEqual(first.imported_counts["provider_scope_enablements"], 1)
        self.assertEqual(first.imported_counts["permission_enablements"], 1)
        self.assertGreaterEqual(first.created, 5)
        self.assertEqual(second.created, 0)
        self.assertGreaterEqual(second.skipped, 5)
        self.assertIn("asset_openai", payload)
        self.assertIn("cred_openai", payload)
        self.assertIn("provider_scope_enablements", payload)
        self.assertIn("permission_enablements", payload)
        self.assertNotIn("runtime_readiness", payload)
        self.assertEqual(materializer.warnings, ())


if __name__ == "__main__":
    unittest.main()
