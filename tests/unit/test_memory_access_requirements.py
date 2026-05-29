from __future__ import annotations

from types import SimpleNamespace
import unittest

from crxzipple.app.assembly.memory import build_memory_embedding_provider
from crxzipple.modules.access.application.memory_consumers import (
    memory_access_consumer_bindings,
)
from crxzipple.modules.access.application.query import AccessControlPlaneQueryProvider
from crxzipple.modules.access.application.repositories import (
    AccessCredentialBindingRecord,
)
from crxzipple.modules.memory.application import MemorySettingsBootstrapConfig


class MemoryAccessRequirementsTestCase(unittest.TestCase):
    def test_openai_compatible_memory_embedding_requirement_enters_access_catalog(
        self,
    ) -> None:
        config = MemorySettingsBootstrapConfig(
            retrieval_backend="vector",
            vector_provider="openai_compatible",
            vector_credential_binding_id="memory-openai-api-key",
        )
        provider = AccessControlPlaneQueryProvider(
            governance_repository=_EmptyAccessRepository(),
            settings_config_provider=_SettingsConfigProvider(
                credential_bindings=(
                    AccessCredentialBindingRecord(
                        binding_id="memory-openai-api-key",
                        asset_id="asset:memory-openai",
                        binding_kind="api_key",
                        source_kind="env",
                        source_ref="MEMORY_OPENAI_API_KEY",
                    ),
                ),
            ),
            external_consumer_binding_provider=lambda: memory_access_consumer_bindings(
                config,
            ),
        )

        payload = provider.credential_requirements().to_payload()

        self.assertEqual(len(payload["credential_requirements"]), 1)
        row = payload["credential_requirements"][0]
        self.assertEqual(row["consumer_module"], "memory")
        self.assertEqual(row["consumer_kind"], "memory_engine")
        self.assertEqual(row["consumer_id"], "file_markdown.vector_embeddings")
        self.assertEqual(row["slot"], "embedding_api_key")
        self.assertEqual(row["expected_kind"], "api_key")
        self.assertEqual(row["binding_id"], "memory-openai-api-key")
        self.assertTrue(row["ready"])

    def test_openai_compatible_memory_embedding_requirement_is_missing_without_binding(
        self,
    ) -> None:
        config = MemorySettingsBootstrapConfig(
            retrieval_backend="vector",
            vector_provider="openai_compatible",
        )
        provider = AccessControlPlaneQueryProvider(
            governance_repository=_EmptyAccessRepository(),
            settings_config_provider=_SettingsConfigProvider(),
            external_consumer_binding_provider=lambda: memory_access_consumer_bindings(
                config,
            ),
        )

        payload = provider.credential_requirements().to_payload()

        self.assertEqual(len(payload["credential_requirements"]), 1)
        row = payload["credential_requirements"][0]
        self.assertEqual(row["consumer_module"], "memory")
        self.assertTrue(row["missing"])
        self.assertFalse(row["ready"])

    def test_openai_compatible_embedding_provider_validates_access_binding_kind(
        self,
    ) -> None:
        config = MemorySettingsBootstrapConfig(
            vector_provider="openai_compatible",
            vector_credential_binding_id="memory-openai-api-key",
        )

        provider = build_memory_embedding_provider(
            config,
            credential_provider=_CredentialInspector(
                {
                    "binding_id": "memory-openai-api-key",
                    "binding_kind": "api_key",
                    "status": "active",
                },
            ),
        )

        self.assertEqual(provider.provider_name, "openai_compatible")

    def test_openai_compatible_embedding_provider_rejects_unknown_binding(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "unknown Access credential binding"):
            build_memory_embedding_provider(
                MemorySettingsBootstrapConfig(
                    vector_provider="openai_compatible",
                    vector_credential_binding_id="missing-memory-token",
                ),
                credential_provider=_CredentialInspector(None),
            )

    def test_openai_compatible_embedding_provider_rejects_wrong_binding_kind(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "require an Access api_key"):
            build_memory_embedding_provider(
                MemorySettingsBootstrapConfig(
                    vector_provider="openai_compatible",
                    vector_credential_binding_id="codex-oauth-default",
                ),
                credential_provider=_CredentialInspector(
                    {
                        "binding_id": "codex-oauth-default",
                        "binding_kind": "oauth2_account",
                        "status": "active",
                    },
                ),
            )


class _SettingsConfigProvider:
    def __init__(
        self,
        *,
        credential_bindings: tuple[AccessCredentialBindingRecord, ...] = (),
    ) -> None:
        self._view = SimpleNamespace(
            list_assets=lambda: (),
            list_credential_bindings=lambda: credential_bindings,
            list_consumer_bindings=lambda: (),
        )

    def view(self) -> object:
        return self._view


class _EmptyAccessRepository:
    def list_readiness_snapshots(self) -> tuple[object, ...]:
        return ()

    def list_setup_sessions(self) -> tuple[object, ...]:
        return ()


class _CredentialInspector:
    def __init__(self, metadata: dict[str, object] | None) -> None:
        self.metadata = metadata

    def describe_credential_binding(self, binding_id: str) -> dict[str, object] | None:
        if self.metadata is None:
            return None
        if self.metadata.get("binding_id") != binding_id:
            return None
        return dict(self.metadata)

    def resolve_credential(self, *_args: object, **_kwargs: object) -> str:
        return "secret-token"


if __name__ == "__main__":
    unittest.main()
