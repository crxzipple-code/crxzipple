from __future__ import annotations

import json
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
)
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
            audits=(audit,),
        )

        payload_text = json.dumps(overview.to_payload(), sort_keys=True)

        self.assertIn("env:OPENAI_API_KEY", payload_text)
        self.assertIn("sk-***", payload_text)
        self.assertNotIn("sk-real-secret", payload_text)
        self.assertNotIn("literal-secret", payload_text)

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

    def test_inventory_can_infer_legacy_settings_llm_payloads(self) -> None:
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
                    "credential_binding": "env:LEGACY_OPENAI_TOKEN",
                },
                reason="legacy settings llm profile fixture",
                publish=True,
            ),
        )
        container = _ContainerForInventory(services.queries)

        inventory = collect_access_inventory(container)

        self.assertFalse(inventory["ready"])
        self.assertEqual(inventory["counts"], {"total": 1, "ready": 0, "blocked": 1})
        target = inventory["targets"][0]
        self.assertEqual(target["display_name"], "LEGACY_OPENAI_TOKEN")
        self.assertEqual(target["metadata"]["usage_types"], ["llm_profile"])


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
