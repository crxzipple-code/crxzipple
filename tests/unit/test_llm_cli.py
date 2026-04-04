from __future__ import annotations

from tests.unit.cli_test_support import *


class LlmCliTestCase(CliModuleTestCase):
    def test_llm_register_profile_and_list_commands_return_v2_payload(self) -> None:
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
                    "--credential-binding",
                    "env:OPENAI_API_KEY",
                ],
                env=self.env,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertIn('"id": "writer"', result.stdout)
            self.assertIn('"api_family": "openai_responses"', result.stdout)
            self.assertIn('"model_family": "reasoning"', result.stdout)

            list_result = self.runner.invoke(app, ["llm", "list"], env=self.env)

            self.assertEqual(list_result.exit_code, 0)
            self.assertIn('"id": "writer"', list_result.stdout)
            self.assertIn('"credential_binding": "env:OPENAI_API_KEY"', list_result.stdout)

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
                            "credential_binding: env:OPENAI_API_KEY",
                            "timeout_seconds: 120",
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
                self.assertEqual([item["id"] for item in sync_payload], ["openai.gpt-5.4"])
                self.assertEqual(sync_payload[0]["api_family"], "openai_responses")
                self.assertEqual(sync_payload[0]["context_window_tokens"], 1050000)
                self.assertEqual(
                    sync_payload[0]["default_params"]["reasoning_effort"],
                    "medium",
                )

                list_result = self.runner.invoke(app, ["llm", "list"], env=env)
                self.assertEqual(list_result.exit_code, 0)
                list_payload = json.loads(list_result.stdout)
                self.assertEqual([item["id"] for item in list_payload], ["openai.gpt-5.4"])


if __name__ == "__main__":
    unittest.main()
