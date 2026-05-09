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
from tests.unit.support import SqliteTestHarness


class LlmSettingsIntegrationTestCase(unittest.TestCase):
    def test_legacy_settings_payload_converts_to_owner_input_and_profile(self) -> None:
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
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            },
            "credential_binding": "env:OPENAI_API_KEY",
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
            (LlmCapability.TOOL_CALLING, LlmCapability.STRUCTURED_OUTPUT),
        )
        self.assertEqual(register_input.default_params.temperature, 0.2)
        self.assertEqual(register_input.default_params.reasoning_effort, "medium")
        self.assertEqual(
            register_input.default_params.extra_body,
            {"chat_template_kwargs": {"enable_thinking": False}},
        )
        self.assertEqual(register_input.credential_binding, "env:OPENAI_API_KEY")
        self.assertEqual(register_input.source_kind, LlmSourceKind.IMPORTED)
        self.assertEqual(profile.id, "settings-openai")
        self.assertEqual(profile.credential_binding, "env:OPENAI_API_KEY")

    def test_mapping_config_defaults_to_imported_runtime_cache_input(self) -> None:
        register_input = register_llm_profile_input_from_config(
            {
                "id": "settings-compatible",
                "provider": "openai_compatible",
                "api_family": "openai_chat_compatible",
                "model_name": "llama3.2",
                "default_params": LlmDefaults(top_p=0.9),
                "credential_binding_ref": {
                    "binding_id": "compatible-dev",
                    "source_ref": "env:OPENAI_COMPATIBLE_TOKEN",
                },
            },
        )

        self.assertEqual(register_input.source_kind, LlmSourceKind.IMPORTED)
        self.assertEqual(register_input.default_params.top_p, 0.9)
        self.assertEqual(
            register_input.credential_binding,
            "env:OPENAI_COMPATIBLE_TOKEN",
        )

    def test_settings_profile_config_can_sync_into_llm_runtime_index(self) -> None:
        harness = SqliteTestHarness()
        harness.initialize_schema()
        container = harness.build_container()
        service = LlmApplicationService(container.uow_factory, LlmAdapterRegistry())

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
