from __future__ import annotations

import unittest

from crxzipple.modules.llm.application import (
    LlmApplicationService,
    RegisterLlmProfileInput,
)
from crxzipple.modules.llm.application.services import (
    llm_profile_from_config,
    register_llm_profile_input_from_config,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmModelFamily,
    LlmProviderKind,
    LlmSourceKind,
)
from crxzipple.modules.llm.infrastructure import LlmAdapterRegistry
from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.support import SqliteTestHarness


class LlmSettingsIntegrationTestCase(unittest.TestCase):
    def test_settings_payload_converts_to_owner_input_and_profile(self) -> None:
        config = {
            "profile_id": "settings-openai",
            "provider": "openai",
            "api_family": "openai_responses",
            "model_name": "gpt-5",
            "context_window_tokens": 128_000,
            "model_family": "reasoning",
            "capabilities": ("tool_calling", "structured_output"),
            "default_params": {
                "temperature": 0.2,
                "max_output_tokens": 1024,
                "reasoning_effort": "medium",
                "provider_transport": "websocket",
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            },
            "credential_binding_id": "openai-api-key",
            "timeout_seconds": 120,
            "max_concurrency": 2,
            "concurrency_key": "provider:openai",
        }

        register_input = RegisterLlmProfileInput.from_config(config)
        profile = llm_profile_from_config(config)

        self.assertEqual(register_input.provider, LlmProviderKind.OPENAI)
        self.assertEqual(register_input.api_family, LlmApiFamily.OPENAI_RESPONSES)
        self.assertEqual(register_input.model_family, LlmModelFamily.REASONING)
        self.assertEqual(
            register_input.capabilities,
            (
                LlmCapability.TOOL_CALLING,
                LlmCapability.STRUCTURED_OUTPUT,
                LlmCapability.PROVIDER_NATIVE_CONTINUATION,
            ),
        )
        self.assertEqual(register_input.default_params.temperature, 0.2)
        self.assertEqual(register_input.default_params.reasoning_effort, "medium")
        self.assertEqual(register_input.default_params.provider_transport, "websocket")
        self.assertEqual(
            register_input.default_params.extra_body,
            {"chat_template_kwargs": {"enable_thinking": False}},
        )
        self.assertEqual(register_input.credential_binding_id, "openai-api-key")
        self.assertEqual(register_input.source_kind, LlmSourceKind.IMPORTED)
        self.assertEqual(profile.id, "settings-openai")
        self.assertEqual(profile.credential_binding_id, "openai-api-key")

    def test_mapping_config_defaults_to_imported_runtime_cache_input(self) -> None:
        register_input = register_llm_profile_input_from_config(
            {
                "id": "settings-compatible",
                "provider": "openai_compatible",
                "api_family": "openai_chat_compatible",
                "model_name": "llama3.2",
                "default_params": LlmDefaults(top_p=0.9),
                "credential_binding_id": "compatible-dev",
            },
        )

        self.assertEqual(register_input.source_kind, LlmSourceKind.IMPORTED)
        self.assertEqual(register_input.default_params.top_p, 0.9)
        self.assertEqual(register_input.credential_binding_id, "compatible-dev")
        self.assertNotIn(
            LlmCapability.PROVIDER_NATIVE_CONTINUATION,
            register_input.capabilities,
        )

    def test_codex_websocket_capabilities_enable_provider_native_continuation(
        self,
    ) -> None:
        register_input = register_llm_profile_input_from_config(
            {
                "id": "codex-websocket",
                "provider": "openai_codex",
                "api_family": "openai_codex_responses",
                "model_name": "gpt-5.5",
                "capabilities": (
                    "provider_websocket_transport",
                    "provider_incremental_input",
                ),
            },
        )

        self.assertEqual(
            register_input.capabilities,
            (
                LlmCapability.PROVIDER_WEBSOCKET_TRANSPORT,
                LlmCapability.PROVIDER_INCREMENTAL_INPUT,
                LlmCapability.PROVIDER_NATIVE_CONTINUATION,
            ),
        )

    def test_legacy_credential_source_keys_are_rejected(self) -> None:
        base_config = {
            "id": "legacy-openai",
            "provider": "openai",
            "api_family": "openai_responses",
            "model_name": "gpt-5",
        }
        for forbidden_key, forbidden_value in (
            ("credential_binding", "env:OPENAI_API_KEY"),
            ("credential_binding_ref", "file:/tmp/openai-token"),
            ("auth_ref", "codex_auth_json"),
        ):
            with self.subTest(forbidden_key=forbidden_key):
                with self.assertRaises(ValueError):
                    register_llm_profile_input_from_config(
                        {**base_config, forbidden_key: forbidden_value},
                    )

    def test_credential_binding_id_rejects_direct_sources(self) -> None:
        base_config = {
            "id": "legacy-openai",
            "provider": "openai",
            "api_family": "openai_responses",
            "model_name": "gpt-5",
        }
        for forbidden_binding_id in (
            "env:OPENAI_API_KEY",
            "file:/tmp/openai-token",
            "codex_auth_json",
            "auth_ref",
        ):
            with self.subTest(forbidden_binding_id=forbidden_binding_id):
                with self.assertRaises(ValueError):
                    register_llm_profile_input_from_config(
                        {
                            **base_config,
                            "credential_binding_id": forbidden_binding_id,
                        },
                    )

    def test_settings_profile_config_can_sync_into_llm_runtime_index(self) -> None:
        harness = SqliteTestHarness()
        harness.initialize_schema()
        container = harness.build_runtime_container()
        service = LlmApplicationService(
            container.require(AppKey.UNIT_OF_WORK_FACTORY),
            LlmAdapterRegistry(),
        )

        try:
            synced = service.sync_profiles(
                (
                    RegisterLlmProfileInput.from_config(
                        {
                            "profile_id": "settings-openai",
                            "provider": "openai",
                            "api_family": "openai_responses",
                            "model_name": "gpt-5",
                        },
                    ),
                ),
            )

            self.assertEqual([item.id for item in synced], ["settings-openai"])
            self.assertEqual(service.get_profile("settings-openai").model_name, "gpt-5")
        finally:
            harness.close()


if __name__ == "__main__":
    unittest.main()
