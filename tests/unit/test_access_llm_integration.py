from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.llm.application import (
    InvokeLlmInput,
    LlmAdapterRequest,
    LlmAdapterResponse,
    LlmApplicationService,
    RegisterLlmProfileInput,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmMessage,
    LlmMessageRole,
    LlmProviderKind,
    LlmResult,
)
from crxzipple.modules.llm.infrastructure import LlmAdapterRegistry
from tests.unit.support import SqliteTestHarness


class _RecordingAdapter:
    def __init__(self) -> None:
        self.requests: dict[str, LlmAdapterRequest] = {}

    def invoke(self, profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        self.requests[profile.id] = request
        return LlmAdapterResponse(result=LlmResult(text=f"ok:{profile.id}"))


class AccessLlmIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_env = dict(os.environ)
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_container()
        self.adapter = _RecordingAdapter()
        self.registry = LlmAdapterRegistry()
        self.registry.register(LlmApiFamily.OPENAI_RESPONSES, self.adapter)
        self.registry.register(LlmApiFamily.OPENAI_CODEX_RESPONSES, self.adapter)
        self.service = LlmApplicationService(
            self.container.uow_factory,
            self.registry,
            credential_provider=AccessApplicationService(),
        )

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.previous_env)
        self.harness.close()

    def test_access_provider_injects_env_file_and_codex_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            os.environ["LLM_ENV_ACCESS_TOKEN"] = "env-access-token"
            token_path = temp_path / "llm-token.txt"
            token_path.write_text("file-access-token\n", encoding="utf-8")
            codex_home = temp_path / "codex-home"
            codex_home.mkdir()
            (codex_home / "auth.json").write_text(
                '{"tokens": {"access_token": "codex-access-token"}}',
                encoding="utf-8",
            )
            os.environ["CODEX_HOME"] = str(codex_home)

            self._register_and_invoke(
                profile_id="env-profile",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                credential_binding="env:LLM_ENV_ACCESS_TOKEN",
            )
            self._register_and_invoke(
                profile_id="file-profile",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                credential_binding=f"file:{token_path}",
            )
            self._register_and_invoke(
                profile_id="codex-profile",
                provider=LlmProviderKind.OPENAI_CODEX,
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                credential_binding=None,
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

    def _register_and_invoke(
        self,
        *,
        profile_id: str,
        provider: LlmProviderKind,
        api_family: LlmApiFamily,
        credential_binding: str | None,
    ) -> None:
        self.service.register_profile(
            RegisterLlmProfileInput(
                id=profile_id,
                provider=provider,
                api_family=api_family,
                model_name="gpt-5",
                credential_binding=credential_binding,
            ),
        )
        invocation = self.service.invoke(
            InvokeLlmInput(
                llm_id=profile_id,
                messages=(
                    LlmMessage(role=LlmMessageRole.USER, content="hello"),
                ),
            ),
        )
        self.assertEqual(invocation.status.value, "succeeded")


if __name__ == "__main__":
    unittest.main()
