from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from crxzipple.modules.access.application.inventory import (
    AccessInventoryInput,
    AccessReadinessCheckSpec,
    collect_access_inventory_from_read_models,
)
from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.application.query import AccessControlPlaneQueryProvider
from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessAssetListReadModel,
    AccessAssetSummaryReadModel,
    AccessAuditReadModel,
    AccessConsumerBindingReadModel,
    AccessOverviewReadModel,
    AccessReadinessReadModel,
    AccessSetupSessionReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
from crxzipple.modules.settings import (
    CreateSettingsResourceInput,
    create_in_memory_settings_services,
)


class AccessReadModelTestCase(unittest.TestCase):
    def test_control_plane_read_models_return_only_governance_payloads(self) -> None:
        readiness = AccessReadinessReadModel(
            target_kind="asset",
            target_id="asset:openai",
            status="setup_needed",
            ready=False,
            reason="missing credential binding",
            checks=(
                {"target_type": "credential_binding", "requirement": "literal-secret"},
            ),
            setup_available=True,
        )
        credential = CredentialBindingReadModel(
            binding_id="credential:openai",
            asset_id="asset:openai",
            binding_kind="api_key",
            source_kind="env",
            source_ref="env:OPENAI_API_KEY",
            masked_preview="env:OPENAI_API_KEY",
            status="active",
        )
        inline_credential = CredentialBindingReadModel(
            binding_id="credential:inline",
            asset_id="asset:openai",
            binding_kind="api_key",
            source_kind="literal",
            source_ref="sk-real-secret",
            masked_preview="sk-***",
            status="active",
        )
        consumer = AccessConsumerBindingReadModel(
            binding_id="consumer:llm:default",
            consumer_module="llm",
            consumer_kind="llm_profile",
            consumer_id="default",
            credential_binding_id=credential.binding_id,
            requirement_sets=(("openai:api_key(env:OPENAI_API_KEY)",),),
        )
        asset = AccessAssetDetailReadModel(
            asset_id="asset:openai",
            asset_kind="credential_binding",
            display_name="OpenAI",
            governance_scope="workspace",
            readiness=readiness,
            credential_bindings=(credential, inline_credential),
            consumer_bindings=(consumer,),
            metadata={"secret_status": "stored", "masked_preview": "sk-***"},
        )
        setup = AccessSetupSessionReadModel(
            session_id="setup:openai",
            target_kind="asset",
            target_id=asset.asset_id,
            status="waiting_user",
            flow_kind="env",
        )
        audit = AccessAuditReadModel(
            audit_id="audit:openai",
            action_type="setup_started",
            target_type="asset",
            target_id=asset.asset_id,
            status="succeeded",
            operator="local-user",
            source="access",
            reason="manual setup",
            request_metadata={"masked_preview": "sk-***"},
        )
        overview = AccessOverviewReadModel(
            ready=False,
            counts={"assets": 1, "blocked": 1},
            assets=AccessAssetListReadModel(
                assets=(
                    AccessAssetSummaryReadModel(
                        asset_id=asset.asset_id,
                        asset_kind=asset.asset_kind,
                        display_name=asset.display_name,
                        governance_scope=asset.governance_scope,
                        readiness=readiness,
                    ),
                ),
            ),
            readiness=(readiness,),
            credential_bindings=(credential,),
            consumer_bindings=(consumer,),
            setup_sessions=(setup,),
        )

        payload_text = json.dumps(overview.to_payload(), sort_keys=True)
        audit_payload_text = json.dumps(audit.to_payload(), sort_keys=True)

        self.assertIn("env:***", payload_text)
        self.assertNotIn("env:OPENAI_API_KEY", payload_text)
        self.assertIn("sk-***", audit_payload_text)
        self.assertNotIn("sk-real-secret", payload_text)
        self.assertNotIn("literal-secret", payload_text)
        self.assertNotIn("sk-real-secret", audit_payload_text)
        self.assertNotIn("literal-secret", audit_payload_text)

    def test_overview_builds_credential_requirement_catalog_without_secret_sources(
        self,
    ) -> None:
        settings_provider = _SettingsConfigProvider(
            assets=(
                AccessAssetRecord(
                    asset_id="asset:openai",
                    asset_kind="secret_asset",
                    display_name="OpenAI",
                    governance_scope="workspace",
                ),
            ),
            credential_bindings=(
                AccessCredentialBindingRecord(
                    binding_id="credential:openai",
                    asset_id="asset:openai",
                    binding_kind="api_key",
                    source_kind="env",
                    source_ref="OPENAI_API_KEY",
                ),
                AccessCredentialBindingRecord(
                    binding_id="credential:oauth-token",
                    asset_id="asset:openai",
                    binding_kind="bearer_token",
                    source_kind="literal",
                    source_ref="secret-oauth-token",
                ),
            ),
            consumer_bindings=(
                AccessConsumerBindingRecord(
                    binding_id="consumer:tool:weather",
                    consumer_module="tool",
                    consumer_kind="openapi_provider",
                    consumer_id="weather",
                    display_name="Weather",
                    asset_id="asset:openai",
                    credential_binding_id="credential:openai",
                    requirement_sets=(("weather:api_key(env:OPENAI_API_KEY)",),),
                ),
                AccessConsumerBindingRecord(
                    binding_id="consumer:channel:lark",
                    consumer_module="channels",
                    consumer_kind="channel_account",
                    consumer_id="lark/default",
                    display_name="Lark",
                    requirement_sets=(("env:LARK_APP_SECRET",),),
                ),
                AccessConsumerBindingRecord(
                    binding_id="consumer:tool:calendar",
                    consumer_module="tool",
                    consumer_kind="openapi_provider",
                    consumer_id="calendar",
                    display_name="Calendar",
                    credential_binding_id="credential:oauth-token",
                    requirement_sets=(("calendar:oauth2(calendar.read)",),),
                ),
            ),
        )
        provider = AccessControlPlaneQueryProvider(
            governance_repository=_EmptyAccessRepository(),
            settings_config_provider=settings_provider,
        )

        payload = provider.overview().to_payload()

        self.assertEqual(payload["counts"]["credential_requirements"], 3)
        self.assertEqual(payload["counts"]["ready_requirements"], 1)
        self.assertEqual(payload["counts"]["missing_requirements"], 2)
        self.assertEqual(payload["counts"]["incompatible_requirements"], 1)
        rows = {
            item["consumer_id"]: item
            for item in payload["credential_requirements"]
        }
        self.assertEqual(rows["weather"]["slot"], "api_key")
        self.assertEqual(rows["weather"]["expected_kind"], "api_key")
        self.assertEqual(rows["weather"]["binding_id"], "credential:openai")
        self.assertTrue(rows["weather"]["ready"])
        self.assertEqual(rows["lark/default"]["status"], "missing")
        self.assertEqual(rows["calendar"]["expected_kind"], "oauth2_account")
        self.assertEqual(rows["calendar"]["status"], "credential_kind_mismatch")
        self.assertEqual(rows["calendar"]["setup_flow_hint"]["flow_kind"], "manual")
        self.assertEqual(rows["calendar"]["setup_flow_hint"]["provider"], "calendar")
        self.assertEqual(
            rows["calendar"]["setup_flow_hint"]["metadata"],
            {
                "expected_flow_kind": "browser_oauth",
                "reason": "access_oauth_provider_not_configured",
                "setup_provider_missing": True,
            },
        )
        payload_text = json.dumps(payload, sort_keys=True)
        self.assertNotIn("OPENAI_API_KEY", payload_text)
        self.assertNotIn("LARK_APP_SECRET", payload_text)
        self.assertNotIn("secret-oauth-token", payload_text)

    def test_setup_sessions_show_expired_state_and_redact_oauth_flow_secrets(
        self,
    ) -> None:
        now = datetime(2026, 5, 21, 8, 0, tzinfo=timezone.utc)
        provider = AccessControlPlaneQueryProvider(
            governance_repository=_SetupSessionRepository(
                (
                    AccessSetupSessionRecord(
                        session_id="oauthsetup_browser",
                        target_kind="oauth_provider",
                        target_id="example-oauth",
                        status="waiting_for_user",
                        flow_kind="browser_oauth",
                        expires_at=now - timedelta(seconds=1),
                        metadata={
                            "code_verifier": "pkce-secret",
                            "state": "csrf-state",
                            "requested_scopes": ["profile"],
                        },
                    ),
                    AccessSetupSessionRecord(
                        session_id="oauthsetup_device",
                        target_kind="oauth_provider",
                        target_id="device-oauth",
                        status="waiting_for_user",
                        flow_kind="device_code",
                        expires_at=now + timedelta(minutes=5),
                        metadata={
                            "device_code": "device-secret-code",
                            "verification_url": "https://auth.example.test/verify",
                        },
                    ),
                ),
            ),
            settings_config_provider=_SettingsConfigProvider(),
            generated_at_factory=lambda: now,
        )

        payload = provider.overview().to_payload()
        sessions = {
            item["session_id"]: item
            for item in payload["setup_sessions"]
        }

        self.assertEqual(sessions["oauthsetup_browser"]["status"], "expired")
        self.assertEqual(sessions["oauthsetup_browser"]["metadata"]["code_verifier"], "***")
        self.assertEqual(sessions["oauthsetup_browser"]["metadata"]["state"], "***")
        self.assertEqual(sessions["oauthsetup_device"]["status"], "waiting_for_user")
        self.assertEqual(sessions["oauthsetup_device"]["metadata"]["device_code"], "***")
        self.assertEqual(
            sessions["oauthsetup_device"]["metadata"]["verification_url"],
            "https://auth.example.test/verify",
        )

    def test_requirement_catalog_keeps_consumer_slots_separate(self) -> None:
        settings_provider = _SettingsConfigProvider(
            credential_bindings=(
                AccessCredentialBindingRecord(
                    binding_id="credential:lark-app-id",
                    asset_id=None,
                    binding_kind="api_key",
                    source_kind="env",
                    source_ref="LARK_APP_ID",
                ),
                AccessCredentialBindingRecord(
                    binding_id="credential:lark-secret",
                    asset_id=None,
                    binding_kind="app_secret",
                    source_kind="env",
                    source_ref="LARK_APP_SECRET",
                ),
            ),
            consumer_bindings=(
                AccessConsumerBindingRecord(
                    binding_id="consumer:channels:lark:default",
                    consumer_module="channels",
                    consumer_kind="channel_account",
                    consumer_id="lark/default",
                    display_name="Lark Default",
                    credential_bindings={
                        "lark_app_id": "credential:lark-app-id",
                        "lark_app_secret": "credential:lark-secret",
                    },
                    requirement_sets=(
                        (
                            "lark:api_key(lark_app_id)",
                            "lark:app_secret(lark_app_secret)",
                        ),
                    ),
                ),
            ),
        )
        provider = AccessControlPlaneQueryProvider(
            governance_repository=_EmptyAccessRepository(),
            settings_config_provider=settings_provider,
        )

        payload = provider.credential_requirements().to_payload()

        rows = {
            item["slot"]: item
            for item in payload["credential_requirements"]
        }
        self.assertEqual(rows["lark_app_id"]["binding_id"], "credential:lark-app-id")
        self.assertEqual(rows["lark_app_id"]["expected_kind"], "api_key")
        self.assertTrue(rows["lark_app_id"]["ready"])
        self.assertEqual(rows["lark_app_secret"]["binding_id"], "credential:lark-secret")
        self.assertEqual(rows["lark_app_secret"]["expected_kind"], "app_secret")
        self.assertTrue(rows["lark_app_secret"]["ready"])
        consumer = payload["requirements_by_consumer"]["channels:channel_account:lark/default"]
        self.assertEqual({item["slot"] for item in consumer}, {"lark_app_id", "lark_app_secret"})

    def test_query_projects_credential_bindings_as_visible_access_assets(
        self,
    ) -> None:
        settings_provider = _SettingsConfigProvider(
            credential_bindings=(
                AccessCredentialBindingRecord(
                    binding_id="openai-api-key",
                    asset_id=None,
                    binding_kind="api_key",
                    source_kind="env",
                    source_ref="OPENAI_API_KEY",
                    masked_preview="env:OPENAI_API_KEY",
                ),
                AccessCredentialBindingRecord(
                    binding_id="codex-oauth-default",
                    asset_id=None,
                    binding_kind="oauth2_account",
                    source_kind="oauth_account",
                    source_ref="openai-codex:default",
                    masked_preview="oauth:openai-codex:default",
                ),
            ),
            consumer_bindings=(
                AccessConsumerBindingRecord(
                    binding_id="consumer:llm:default",
                    consumer_module="llm",
                    consumer_kind="llm_profile",
                    consumer_id="default",
                    display_name="Default LLM",
                    credential_binding_id="openai-api-key",
                    requirement_sets=(("openai:api_key(env:OPENAI_API_KEY)",),),
                ),
            ),
        )
        provider = AccessControlPlaneQueryProvider(
            governance_repository=_EmptyAccessRepository(),
            settings_config_provider=settings_provider,
        )

        overview_payload = provider.overview().to_payload()
        list_payload = provider.assets().to_payload()
        detail_payload = provider.asset_detail("openai-api-key").to_payload()

        self.assertEqual(overview_payload["counts"]["assets"], 2)
        self.assertEqual(list_payload["counts"]["total"], 2)
        rows = {item["asset_id"]: item for item in list_payload["assets"]}
        self.assertEqual(rows["openai-api-key"]["asset_kind"], "credential_binding")
        self.assertEqual(rows["openai-api-key"]["credential_binding_count"], 1)
        self.assertEqual(rows["openai-api-key"]["consumer_modules"], ["llm"])
        self.assertEqual(detail_payload["asset_id"], "openai-api-key")
        self.assertEqual(
            detail_payload["credential_bindings"][0]["binding_id"],
            "openai-api-key",
        )
        self.assertEqual(
            detail_payload["consumer_bindings"][0]["binding_id"],
            "consumer:llm:default",
        )
        payload_text = json.dumps(detail_payload, sort_keys=True)
        self.assertIn('"source_ref": "env:***"', payload_text)
        self.assertNotIn("OPENAI_API_KEY", payload_text)

    def test_inventory_aggregates_from_access_read_models_without_module_services(
        self,
    ) -> None:
        source = AccessInventoryInput(
            credential_bindings=(
                CredentialBindingReadModel(
                    binding_id="credential:model",
                    binding_kind="api_key",
                    source_kind="env",
                    source_ref="env:MISSING_MODEL_TOKEN",
                ),
                CredentialBindingReadModel(
                    binding_id="credential:inline",
                    binding_kind="api_key",
                    source_kind="literal",
                    source_ref="inline-super-secret-token",
                ),
            ),
            consumer_bindings=(
                AccessConsumerBindingReadModel(
                    binding_id="consumer:llm:primary",
                    consumer_module="llm",
                    consumer_kind="llm_profile",
                    consumer_id="primary",
                    display_name="Primary Model",
                    credential_binding_id="credential:model",
                    metadata={
                        "provider": "openai_compatible",
                        "access_token": "secret-from-metadata",
                    },
                ),
                AccessConsumerBindingReadModel(
                    binding_id="consumer:tool:search",
                    consumer_module="tool",
                    consumer_kind="tool",
                    consumer_id="search",
                    display_name="Search Tool",
                    requirement_sets=(("openai:api_key(env:MISSING_MODEL_TOKEN)",),),
                ),
                AccessConsumerBindingReadModel(
                    binding_id="consumer:llm:inline",
                    consumer_module="llm",
                    consumer_kind="llm_profile",
                    consumer_id="inline",
                    display_name="Inline Model",
                    credential_binding_id="credential:inline",
                ),
            ),
        )
        observed_specs: list[tuple[AccessReadinessCheckSpec, ...]] = []

        def check_readiness(
            specs: tuple[AccessReadinessCheckSpec, ...],
        ) -> tuple[dict[str, object], ...]:
            observed_specs.append(specs)
            return tuple(
                {
                    "target_type": target_type,
                    "requirement": requirement,
                    "status": "setup_needed",
                    "ready": False,
                    "setup_available": True,
                    "reason": "fake checker",
                }
                for target_type, requirement, _allow_literal in specs
            )

        inventory = collect_access_inventory_from_read_models(
            source,
            check_readiness=check_readiness,
        )
        payload_text = json.dumps(inventory, sort_keys=True)

        self.assertEqual(inventory["counts"]["blocked"], 2)
        self.assertEqual(len(observed_specs), 2)
        targets = {item["display_name"]: item for item in inventory["targets"]}
        self.assertEqual(targets["MISSING_MODEL_TOKEN"]["metadata"]["usage_count"], 2)
        self.assertEqual(
            sorted(targets["MISSING_MODEL_TOKEN"]["metadata"]["usage_types"]),
            ["llm_profile", "tool"],
        )
        self.assertNotIn("inline-super-secret-token", payload_text)
        self.assertNotIn("secret-from-metadata", payload_text)
        self.assertIn("literal:***", payload_text)

    def test_inventory_entry_reads_settings_not_module_services(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="access:repository-only",
                resource_kind="access-assets",
                owner_module="access",
                payload={
                    "assets": [
                        {
                            "asset_id": "asset:repository-only",
                            "asset_kind": "credential_binding",
                            "display_name": "Repository Credential",
                            "governance_scope": "module",
                            "consumer_modules": ["llm"],
                        },
                    ],
                    "credential_bindings": [
                        {
                            "binding_id": "credential:repository-only",
                            "asset_id": "asset:repository-only",
                            "binding_kind": "api_key",
                            "source_kind": "env",
                            "source_ref": "REPOSITORY_ONLY_TOKEN",
                            "metadata": {"canonical_ref": "env:REPOSITORY_ONLY_TOKEN"},
                        },
                    ],
                    "consumer_bindings": [
                        {
                            "binding_id": "consumer:llm:repository-only",
                            "consumer_module": "llm",
                            "consumer_kind": "llm_profile",
                            "consumer_id": "repository-only",
                            "display_name": "Repository Only Model",
                            "asset_id": "asset:repository-only",
                            "credential_binding_id": "credential:repository-only",
                        },
                    ],
                },
                reason="seed settings-owned access inventory",
                publish=True,
            ),
        )
        container = _ContainerForInventory(services.queries)

        inventory = collect_access_inventory(container)

        self.assertEqual(inventory["counts"]["blocked"], 1)
        target = inventory["targets"][0]
        self.assertEqual(target["display_name"], "REPOSITORY_ONLY_TOKEN")
        self.assertEqual(target["metadata"]["usage_count"], 1)
        self.assertEqual(target["metadata"]["usage_types"], ["llm_profile"])
        self.assertEqual(
            target["requirement_sets"][0]["checks"][0]["requirement"],
            "env:REPOSITORY_ONLY_TOKEN",
        )

    def test_inventory_does_not_infer_settings_llm_binding_refs(self) -> None:
        services = create_in_memory_settings_services()
        services.actions.create_resource(
            CreateSettingsResourceInput(
                resource_id="legacy-openai",
                resource_kind="llm-profiles",
                owner_module="llm",
                payload={
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5",
                    "credential_binding_id": "legacy-openai-token",
                },
                reason="legacy settings llm profile fixture",
                publish=True,
            ),
        )
        container = _ContainerForInventory(services.queries)

        inventory = collect_access_inventory(container)

        self.assertTrue(inventory["ready"])
        self.assertEqual(inventory["counts"], {"total": 0, "ready": 0, "blocked": 0})
        self.assertEqual(inventory["targets"], [])
        self.assertNotIn("legacy-openai-token", repr(inventory))


class _RepositoryForInventory:
    def list_assets(self) -> tuple[AccessAssetRecord, ...]:
        return (
            AccessAssetRecord(
                asset_id="asset:repository-only",
                asset_kind="credential_binding",
                display_name="Repository Credential",
                governance_scope="module",
                consumer_modules=("llm",),
            ),
        )

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]:
        return (
            AccessCredentialBindingRecord(
                binding_id="credential:repository-only",
                asset_id="asset:repository-only",
                binding_kind="api_key",
                source_kind="env",
                source_ref="REPOSITORY_ONLY_TOKEN",
                metadata={"canonical_ref": "env:REPOSITORY_ONLY_TOKEN"},
            ),
        )

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        return (
            AccessConsumerBindingRecord(
                binding_id="consumer:llm:repository-only",
                consumer_module="llm",
                consumer_kind="llm_profile",
                consumer_id="repository-only",
                display_name="Repository Only Model",
                asset_id="asset:repository-only",
                credential_binding_id="credential:repository-only",
            ),
        )


class _ContainerForInventory:
    def __init__(self, settings_query_service: object) -> None:
        self.settings_query_service = settings_query_service
        self.settings = SimpleNamespace(environment=None)
        self.access_service = _AccessServiceForInventory()
        self.llm_service = _ExplodingService()
        self.tool_service = _ExplodingService()
        self.channel_profile_service = _ExplodingService()

    def require(self, key: str) -> object:
        return {
            "access.service": self.access_service,
            "core.settings": self.settings,
            "settings.query_service": self.settings_query_service,
        }[key]


class _SettingsConfigProvider:
    def __init__(
        self,
        *,
        assets: tuple[AccessAssetRecord, ...] = (),
        credential_bindings: tuple[AccessCredentialBindingRecord, ...] = (),
        consumer_bindings: tuple[AccessConsumerBindingRecord, ...] = (),
    ) -> None:
        self._view = SimpleNamespace(
            list_assets=lambda: assets,
            list_credential_bindings=lambda: credential_bindings,
            list_consumer_bindings=lambda: consumer_bindings,
        )

    def view(self) -> object:
        return self._view


class _EmptyAccessRepository:
    def list_readiness_snapshots(self) -> tuple[object, ...]:
        return ()

    def list_setup_sessions(self) -> tuple[object, ...]:
        return ()


class _SetupSessionRepository(_EmptyAccessRepository):
    def __init__(self, setup_sessions: tuple[AccessSetupSessionRecord, ...]) -> None:
        self._setup_sessions = setup_sessions

    def list_setup_sessions(self) -> tuple[AccessSetupSessionRecord, ...]:
        return self._setup_sessions


class _AccessServiceForInventory:
    def check_credential_binding(
        self,
        requirement: str,
        *,
        workspace_dir: str | None,
        allow_literal: bool,
    ) -> object:
        return _ReadinessForInventory(requirement)

    def check_requirement(
        self, requirement: str, *, workspace_dir: str | None
    ) -> object:
        return _ReadinessForInventory(requirement)


class _ReadinessForInventory:
    def __init__(self, requirement: str) -> None:
        self.requirement = requirement

    def to_payload(self) -> dict[str, object]:
        return {
            "requirement": self.requirement,
            "provider": None,
            "kind": None,
            "scopes": [],
            "status": "setup_needed",
            "ready": False,
            "setup_available": True,
            "reason": "repository-only fake readiness",
        }


class _ExplodingService:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"module service should not be scanned: {name}")


if __name__ == "__main__":
    unittest.main()
