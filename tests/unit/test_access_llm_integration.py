from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.access.application.repositories import (
    AccessCredentialBindingRecord,
    AccessOAuthAccountRecord,
)
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument
from crxzipple.modules.llm.application import (
    InvokeLlmInput,
    LlmAdapterRequest,
    LlmAdapterResponse,
    LlmApplicationService,
    RegisterLlmProfileInput,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    LlmProviderKind,
    LlmResult,
)
from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.modules.llm.infrastructure import LlmAdapterRegistry
from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.support import SqliteTestHarness


class _RecordingAdapter:
    def __init__(self) -> None:
        self.requests: dict[str, LlmAdapterRequest] = {}

    def invoke(self, profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        self.requests[profile.id] = request
        return LlmAdapterResponse(result=LlmResult(text=f"ok:{profile.id}"))


class _StaticAccessConfigView:
    def __init__(self, records: dict[str, AccessCredentialBindingRecord]) -> None:
        self.records = records

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None:
        return self.records.get(binding_id)


class _StaticOAuthRepository:
    def __init__(self, accounts: dict[str, AccessOAuthAccountRecord]) -> None:
        self.accounts = accounts

    def get_oauth_account(self, account_id: str) -> AccessOAuthAccountRecord | None:
        return self.accounts.get(account_id)

    def get_oauth_provider(self, provider_id: str):  # noqa: ANN201
        return None


class _StaticOAuthTokenStore:
    def __init__(self, tokens: dict[str, OAuthTokenDocument]) -> None:
        self.tokens = tokens

    def read_token(self, storage_key: str) -> OAuthTokenDocument:
        return self.tokens[storage_key]

    def write_token(self, storage_key: str, document):  # noqa: ANN001, ANN201
        self.tokens[storage_key] = document


class AccessLlmIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_env = dict(os.environ)
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_runtime_container()
        self.uow_factory = self.container.require(AppKey.UNIT_OF_WORK_FACTORY)
        self.adapter = _RecordingAdapter()
        self.registry = LlmAdapterRegistry()
        self.registry.register(LlmApiFamily.OPENAI_RESPONSES, self.adapter)
        self.registry.register(LlmApiFamily.OPENAI_CODEX_RESPONSES, self.adapter)
        self.service: LlmApplicationService | None = None

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.previous_env)
        self.harness.close()

    def test_access_provider_injects_env_file_and_oauth_account_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            os.environ["LLM_ENV_ACCESS_TOKEN"] = "env-access-token"
            token_path = temp_path / "llm-token.txt"
            token_path.write_text("file-access-token\n", encoding="utf-8")
            self.service = LlmApplicationService(
                self.uow_factory,
                self.registry,
                credential_provider=AccessApplicationService(
                    config_view=_StaticAccessConfigView(
                        {
                            "env-llm-token": AccessCredentialBindingRecord(
                                asset_id=None,
                                binding_id="env-llm-token",
                                binding_kind="api_key",
                                source_kind="env",
                                source_ref="LLM_ENV_ACCESS_TOKEN",
                                masked_preview="env:LLM_ENV_ACCESS_TOKEN",
                            ),
                            "file-llm-token": AccessCredentialBindingRecord(
                                asset_id=None,
                                binding_id="file-llm-token",
                                binding_kind="api_key",
                                source_kind="file",
                                source_ref=str(token_path),
                                masked_preview="file:***",
                            ),
                            "codex-llm-token": AccessCredentialBindingRecord(
                                asset_id=None,
                                binding_id="codex-llm-token",
                                binding_kind="oauth2_account",
                                source_kind="oauth_account",
                                source_ref="openai-codex:default",
                                masked_preview="codex...oken",
                            ),
                        },
                    ),
                    oauth_account_repository=_StaticOAuthRepository(
                        {
                            "openai-codex:default": AccessOAuthAccountRecord(
                                account_id="openai-codex:default",
                                provider_id="openai-codex",
                                credential_binding_id="codex-llm-token",
                                storage_key="codex-token",
                            ),
                        },
                    ),
                    oauth_token_store=_StaticOAuthTokenStore(
                        {
                            "codex-token": OAuthTokenDocument(
                                access_token="codex-access-token",
                                refresh_token="codex-refresh-token",
                            ),
                        },
                    ),
                ),
            )

            self._register_and_invoke(
                profile_id="env-profile",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                credential_binding_id="env-llm-token",
            )
            self._register_and_invoke(
                profile_id="file-profile",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                credential_binding_id="file-llm-token",
            )
            self._register_and_invoke(
                profile_id="codex-profile",
                provider=LlmProviderKind.OPENAI_CODEX,
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                credential_binding_id="codex-llm-token",
            )

        self.assertEqual(
            self.adapter.requests["env-profile"].resolved_credential,
            "env-access-token",
        )
        self.assertEqual(
            self.adapter.requests["file-profile"].resolved_credential,
            "file-access-token",
        )
        self.assertEqual(
            self.adapter.requests["codex-profile"].resolved_credential,
            "codex-access-token",
        )

    def test_access_metadata_rejects_provider_credential_type_mismatch(self) -> None:
        self.service = LlmApplicationService(
            self.uow_factory,
            self.registry,
            credential_provider=AccessApplicationService(
                config_view=_StaticAccessConfigView(
                    {
                        "env-llm-token": AccessCredentialBindingRecord(
                            asset_id=None,
                            binding_id="env-llm-token",
                            binding_kind="api_key",
                            source_kind="env",
                            source_ref="LLM_ENV_ACCESS_TOKEN",
                        ),
                        "legacy-credential-binding": AccessCredentialBindingRecord(
                            asset_id=None,
                            binding_id="legacy-credential-binding",
                            binding_kind="credential_binding",
                            source_kind="env",
                            source_ref="LLM_ENV_ACCESS_TOKEN",
                        ),
                        "generic-token": AccessCredentialBindingRecord(
                            asset_id=None,
                            binding_id="generic-token",
                            binding_kind="token",
                            source_kind="env",
                            source_ref="LLM_ENV_ACCESS_TOKEN",
                        ),
                        "codex-llm-token": AccessCredentialBindingRecord(
                            asset_id=None,
                            binding_id="codex-llm-token",
                            binding_kind="oauth2_account",
                            source_kind="oauth_account",
                            source_ref="openai-codex:default",
                        ),
                    },
                ),
            ),
        )

        with self.assertRaisesRegex(LlmValidationError, "expects API key"):
            self.service.register_profile(
                RegisterLlmProfileInput(
                    id="openai-with-codex",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5",
                    credential_binding_id="codex-llm-token",
                ),
            )

        with self.assertRaisesRegex(LlmValidationError, "expects OAuth account"):
            self.service.register_profile(
                RegisterLlmProfileInput(
                    id="codex-with-api-key",
                    provider=LlmProviderKind.OPENAI_CODEX,
                    api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                    model_name="gpt-5",
                    credential_binding_id="env-llm-token",
                ),
            )

        for binding_id in ("legacy-credential-binding", "generic-token"):
            with self.subTest(binding_id=binding_id):
                with self.assertRaisesRegex(LlmValidationError, "expects API key"):
                    self.service.register_profile(
                        RegisterLlmProfileInput(
                            id=f"openai-with-{binding_id}",
                            provider=LlmProviderKind.OPENAI,
                            api_family=LlmApiFamily.OPENAI_RESPONSES,
                            model_name="gpt-5",
                            credential_binding_id=binding_id,
                        ),
                    )

    def _register_and_invoke(
        self,
        *,
        profile_id: str,
        provider: LlmProviderKind,
        api_family: LlmApiFamily,
        credential_binding_id: str | None,
    ) -> None:
        assert self.service is not None
        self.service.register_profile(
            RegisterLlmProfileInput(
                id=profile_id,
                provider=provider,
                api_family=api_family,
                model_name="gpt-5",
                credential_binding_id=credential_binding_id,
            ),
        )
        invocation = self.service.invoke(
            InvokeLlmInput(
                llm_id=profile_id,
                messages=(
                    LlmMessage(role=LlmMessageRole.USER, content="hello"),
                ),
                input_items=(
                    LlmInputItem(
                        kind=LlmInputItemKind.MESSAGE,
                        payload={"role": "user", "content": "hello"},
                    ),
                ),
            ),
        )
        self.assertEqual(invocation.status.value, "succeeded")


if __name__ == "__main__":
    unittest.main()
