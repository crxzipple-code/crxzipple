from __future__ import annotations

from dataclasses import replace

from crxzipple.core.config import load_settings
from crxzipple.modules.settings import CreateSettingsResourceInput
from tests.unit.cli_test_support import *


class LlmCliTestCase(CliModuleTestCase):
    def test_llm_register_profile_and_list_commands_return_v2_payload(self) -> None:
        with patch(
            "crxzipple.modules.llm.interfaces.cli.register_llm_profile_input_from_config",
            side_effect=AssertionError("CLI LLM register must not use Settings sync helper"),
        ):
            result = self.runner.invoke(
                app,
                [
                    "llm",
                    "register-profile",
                    "writer",
                    "openai",
                    "openai_responses",
                    "gpt-5",
                    "--model-family",
                    "reasoning",
                    "--capability",
                    "tool_calling",
                    "--temperature",
                    "0.2",
                    "--max-output-tokens",
                    "512",
                    "--max-concurrency",
                    "2",
                    "--concurrency-key",
                    "provider:openai",
                    "--credential-binding",
                    "env:OPENAI_API_KEY",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"id": "writer"', result.stdout)
        self.assertIn('"api_family": "openai_responses"', result.stdout)
        self.assertIn('"model_family": "reasoning"', result.stdout)
        self.assertIn('"max_concurrency": 2', result.stdout)
        self.assertIn('"concurrency_key": "provider:openai"', result.stdout)

        list_result = self.runner.invoke(app, ["llm", "list"], env=self.env)

        self.assertEqual(list_result.exit_code, 0)
        self.assertIn('"id": "writer"', list_result.stdout)
        self.assertIn('"credential_binding": "env:OPENAI_API_KEY"', list_result.stdout)

    def test_llm_enable_disable_commands_update_runtime_profile(self) -> None:
            register_result = self.runner.invoke(
                app,
                [
                    "llm",
                    "register-profile",
                    "writer",
                    "openai",
                    "openai_responses",
                    "gpt-5",
                ],
                env=self.env,
            )
            self.assertEqual(register_result.exit_code, 0)

            disable_result = self.runner.invoke(
                app,
                ["llm", "disable", "writer"],
                env=self.env,
            )
            get_disabled_result = self.runner.invoke(
                app,
                ["llm", "get", "writer"],
                env=self.env,
            )
            enable_result = self.runner.invoke(
                app,
                ["llm", "enable", "writer"],
                env=self.env,
            )
            get_enabled_result = self.runner.invoke(
                app,
                ["llm", "get", "writer"],
                env=self.env,
            )

            self.assertEqual(disable_result.exit_code, 0)
            self.assertFalse(json.loads(disable_result.stdout)["enabled"])
            self.assertFalse(json.loads(get_disabled_result.stdout)["enabled"])
            self.assertEqual(enable_result.exit_code, 0)
            self.assertTrue(json.loads(enable_result.stdout)["enabled"])
            self.assertTrue(json.loads(get_enabled_result.stdout)["enabled"])

    def test_llm_invoke_command_uses_openai_compatible_adapter(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
            os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
            server.start()
            try:
                register_result = self.runner.invoke(
                    app,
                    [
                        "llm",
                        "register-profile",
                        "local-chat",
                        "openai_compatible",
                        "openai_chat_compatible",
                        "llama3.2",
                        "--base-url",
                        f"{server.base_url}/v1",
                        "--credential-binding",
                        "env:OPENAI_COMPATIBLE_TOKEN",
                    ],
                    env=self.env,
                )

                self.assertEqual(register_result.exit_code, 0)

                invoke_result = self.runner.invoke(
                    app,
                    [
                        "llm",
                        "invoke",
                        "local-chat",
                        "--messages",
                        '[{"role":"user","content":"hello"}]',
                        "--tool-schemas",
                        '[{"name":"search_docs","description":"Search docs","input_schema":{"type":"object","properties":{"query":{"type":"string"}}}}]',
                    ],
                    env=self.env,
                )

                self.assertEqual(invoke_result.exit_code, 0)
                self.assertIn('"status": "succeeded"', invoke_result.stdout)
                self.assertIn('"provider_request_id": "chatcmpl_sample_1"', invoke_result.stdout)
                self.assertIn('"text": "hello from sample llm"', invoke_result.stdout)
                self.assertIn('"name": "search_docs"', invoke_result.stdout)
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_llm_sync_profiles_loads_yaml_configs(self) -> None:
            env = dict(self.env)

            with tempfile.TemporaryDirectory() as tempdir:
                profiles_dir = Path(tempdir) / "llm_profiles"
                profiles_dir.mkdir()
                (profiles_dir / "openai_gpt_5_4.yaml").write_text(
                    "\n".join(
                        [
                            "id: openai.gpt-5.4",
                            "provider: openai",
                            "api_family: openai_responses",
                            "model_name: gpt-5.4",
                            "context_window_tokens: 1050000",
                            "model_family: reasoning",
                            "capabilities:",
                            "  - tool_calling",
                            "  - structured_output",
                            "default_params:",
                            "  reasoning_effort: medium",
                            "  extra_body:",
                            "    chat_template_kwargs:",
                            "      enable_thinking: false",
                            "credential_binding: env:OPENAI_API_KEY",
                            "timeout_seconds: 120",
                            "max_concurrency: 2",
                            "concurrency_key: provider:openai",
                            "",
                        ],
                    ),
                    encoding="utf-8",
                )
                env["APP_LLM_PROFILE_PATHS"] = str(profiles_dir)

                sync_result = self.runner.invoke(
                    app,
                    ["llm", "sync-profiles"],
                    env=env,
                )

                self.assertEqual(sync_result.exit_code, 0)
                sync_payload = json.loads(sync_result.stdout)
                synced_by_id = {item["id"]: item for item in sync_payload}
                synced_profile = synced_by_id["openai.gpt-5.4"]
                self.assertEqual(synced_profile["api_family"], "openai_responses")
                self.assertEqual(synced_profile["context_window_tokens"], 1050000)
                self.assertEqual(synced_profile["max_concurrency"], 2)
                self.assertEqual(synced_profile["concurrency_key"], "provider:openai")
                self.assertEqual(
                    synced_profile["default_params"]["reasoning_effort"],
                    "medium",
                )
                self.assertEqual(
                    synced_profile["default_params"]["extra_body"],
                    {"chat_template_kwargs": {"enable_thinking": False}},
                )

                list_result = self.runner.invoke(app, ["llm", "list"], env=env)
                self.assertEqual(list_result.exit_code, 0)
                list_payload = json.loads(list_result.stdout)
                self.assertIn("openai.gpt-5.4", {item["id"] for item in list_payload})

    def test_llm_sync_profiles_command_ignores_legacy_settings_resources(self) -> None:
            env = dict(self.env)

            with tempfile.TemporaryDirectory() as tempdir:
                env["APP_LLM_PROFILE_PATHS"] = str(Path(tempdir) / "empty-profiles")
                settings = replace(
                    load_settings(),
                    database_url=self.harness.database_url,
                    llm_profiles=(),
                )
                container = self.harness.build_container(settings=settings)
                container.settings_action_service.create_resource(
                    CreateSettingsResourceInput(
                        resource_id="legacy-openai",
                        resource_kind="llm-profiles",
                        owner_module="llm",
                        payload={
                            "provider": "openai",
                            "api_family": "openai_responses",
                            "model_name": "legacy-gpt",
                        },
                        reason="seed legacy settings profile",
                        publish=True,
                    ),
                )

                sync_result = self.runner.invoke(
                    app,
                    ["llm", "sync-profiles", "--profile", "legacy-openai"],
                    env=env,
                )
                list_result = self.runner.invoke(app, ["llm", "list"], env=env)

                self.assertEqual(sync_result.exit_code, 0)
                self.assertEqual(json.loads(sync_result.stdout), [])
                self.assertEqual(list_result.exit_code, 0)
                self.assertNotIn(
                    "legacy-openai",
                    {item["id"] for item in json.loads(list_result.stdout)},
                )


if __name__ == "__main__":
    unittest.main()
