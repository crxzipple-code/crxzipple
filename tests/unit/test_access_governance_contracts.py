from __future__ import annotations

import unittest

from crxzipple.modules.access.domain import (
    AccessGovernanceScope,
    AccessResourceDefinition,
    AccessResourceKind,
    AccessResourceRegistry,
    AccessRotationInterval,
    AccessRotationPolicy,
    AccessSecretPolicy,
    AccessSecretStorageMode,
)
from crxzipple.shared.access import (
    AccessAssetRef,
    AccessConsumerRef,
    AccessCredentialKind,
    AccessDecision,
    AccessDecisionEffect,
    AccessReadiness,
    AccessReadinessStatus,
    AccessRequirementRef,
    CredentialBindingRef,
)


class AccessGovernanceContractsTestCase(unittest.TestCase):
    def test_credential_kind_contract_excludes_legacy_direct_sources(self) -> None:
        self.assertEqual(
            {kind.value for kind in AccessCredentialKind},
            {
                "api_key",
                "bearer_token",
                "basic",
                "oauth2_account",
                "openid_connect",
                "app_secret",
                "webhook_secret",
                "certificate",
            },
        )

    def test_resource_registry_indexes_governed_resources(self) -> None:
        credential = AccessResourceDefinition(
            resource_id="credential:openai",
            resource_kind=AccessResourceKind.CREDENTIAL_BINDING,
            governance_scope=AccessGovernanceScope.WORKSPACE,
            storage_key="env:OPENAI_API_KEY",
            consumer_modules=("llm", "tool"),
            masked_preview="env:OPENAI_API_KEY",
        )
        provider_scope = AccessResourceDefinition(
            resource_id="provider-scope:github:repo-read",
            resource_kind=AccessResourceKind.PROVIDER_SCOPE,
            governance_scope=AccessGovernanceScope.GLOBAL,
            display_name="GitHub repo read",
            metadata={"provider": "github", "scope": "repo:read"},
        )

        registry = AccessResourceRegistry().register(credential).register(provider_scope)

        self.assertEqual(registry.require("credential:openai"), credential)
        self.assertEqual(
            registry.by_kind(AccessResourceKind.PROVIDER_SCOPE),
            (provider_scope,),
        )
        self.assertEqual(registry.by_consumer_module("llm"), (credential,))
        with self.assertRaises(ValueError):
            registry.register(credential)

    def test_secret_policy_requires_masking_and_never_exports_secret_material(self) -> None:
        policy = AccessSecretPolicy(
            storage_mode=AccessSecretStorageMode.LOCAL_SECRET_STORE,
            secret_material_allowed=True,
            masked_preview_required=True,
            exportable=False,
        )
        resource = AccessResourceDefinition(
            resource_id="secret:github-token",
            resource_kind=AccessResourceKind.SECRET_ASSET,
            governance_scope=AccessGovernanceScope.WORKSPACE,
            secret_policy=policy,
            storage_key="vault:github-token",
            masked_preview="ghp_****",
            rotation_policy=AccessRotationPolicy(
                interval=AccessRotationInterval.MONTHLY,
                rotate_after_days=30,
            ),
        )

        self.assertFalse(resource.secret_policy.exportable)
        self.assertEqual(resource.storage_key, "vault:github-token")
        self.assertEqual(resource.rotation_policy.rotate_after_days, 30)
        with self.assertRaises(ValueError):
            AccessResourceDefinition(
                resource_id="secret:missing-mask",
                resource_kind=AccessResourceKind.SECRET_ASSET,
                governance_scope=AccessGovernanceScope.WORKSPACE,
                secret_policy=policy,
                storage_key="vault:missing-mask",
            )

    def test_shared_protocol_dataclasses_capture_refs_without_secret_values(self) -> None:
        asset = AccessAssetRef(asset_id="asset:openai", asset_kind="connection_asset")
        binding = CredentialBindingRef(
            binding_id="credential:openai",
            source_type="env",
            source_ref="OPENAI_API_KEY",
            asset=asset,
            masked_preview="env:OPENAI_API_KEY",
            scopes=(" chat ", "responses"),
        )
        consumer = AccessConsumerRef(consumer_id="llm:default", module="llm")
        requirement = AccessRequirementRef(
            requirement_id="openai:api_key(chat)",
            provider="openai",
            kind="api_key",
            required_scopes=("chat",),
            asset_refs=(asset,),
        )
        readiness = AccessReadiness(
            requirement=requirement,
            consumer=consumer,
            status=AccessReadinessStatus.READY,
            reason="credential binding resolved",
            asset_refs=(asset,),
            credential_bindings=(binding,),
            masked_preview=binding.masked_preview,
        )
        decision = AccessDecision(
            effect=AccessDecisionEffect.ALLOW,
            reason="external credential ready",
            code="access_ready",
            consumer=consumer,
            asset=asset,
        )
        lease = AccessResourceDefinition(
            resource_id="lease:openai:setup",
            resource_kind=AccessResourceKind.CREDENTIAL_LEASE,
            governance_scope=AccessGovernanceScope.USER,
            display_name="OpenAI setup lease",
            metadata={"consumer_id": consumer.consumer_id, "asset_id": asset.asset_id},
        )

        self.assertTrue(readiness.ready)
        self.assertEqual(binding.scopes, ("chat", "responses"))
        self.assertTrue(decision.allowed)
        self.assertEqual(lease.resource_kind, AccessResourceKind.CREDENTIAL_LEASE)


if __name__ == "__main__":
    unittest.main()
