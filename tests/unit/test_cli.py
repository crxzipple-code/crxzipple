from __future__ import annotations

from tests.unit.cli_test_support import *


class CliInterfaceTestCase(CliModuleTestCase):
    def test_root_help_exposes_module_groups(self) -> None:
            result = self.runner.invoke(app, ["--help"], env=self.env)

            self.assertEqual(result.exit_code, 0)
            self.assertIn("ask", result.stdout)
            self.assertIn("chat", result.stdout)
            self.assertIn("serve", result.stdout)
            self.assertIn("tool", result.stdout)
            self.assertIn("browser", result.stdout)
            self.assertIn("tool-worker", result.stdout)
            self.assertIn("dispatch", result.stdout)
            self.assertIn("orchestration", result.stdout)
            self.assertIn("orchestration-worker", result.stdout)
            self.assertIn("session", result.stdout)
            self.assertIn("llm", result.stdout)
            self.assertIn("agent", result.stdout)
            self.assertIn("auth", result.stdout)
            self.assertIn("db", result.stdout)

    def test_crxzipple_ask_completes_a_turn_in_one_command(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
            os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
            server.start()

            try:
                llm_result = self.runner.invoke(
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
                self.assertEqual(llm_result.exit_code, 0)

                agent_result = self.runner.invoke(
                    app,
                    [
                        "agent",
                        "register-profile",
                        "crxzipple",
                        "crxzipple",
                        "local-chat",
                        "--system-prompt",
                        "Be helpful.",
                    ],
                    env=self.env,
                )
                self.assertEqual(agent_result.exit_code, 0)

                ask_result = self.runner.invoke(
                    app,
                    [
                        "ask",
                        "hello",
                        "--agent",
                        "crxzipple",
                    ],
                    env=self.env,
                )

                self.assertEqual(ask_result.exit_code, 0)
                self.assertEqual(ask_result.stdout.strip(), "hello from sample llm")
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_crxzipple_chat_completes_a_turn_and_exits(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
            os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
            server.start()

            try:
                llm_result = self.runner.invoke(
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
                self.assertEqual(llm_result.exit_code, 0)

                agent_result = self.runner.invoke(
                    app,
                    [
                        "agent",
                        "register-profile",
                        "crxzipple",
                        "crxzipple",
                        "local-chat",
                        "--system-prompt",
                        "Be helpful.",
                    ],
                    env=self.env,
                )
                self.assertEqual(agent_result.exit_code, 0)

                chat_result = self.runner.invoke(
                    app,
                    [
                        "chat",
                        "--agent",
                        "crxzipple",
                    ],
                    env=self.env,
                    input="hello\n/exit\n",
                )

                self.assertEqual(chat_result.exit_code, 0)
                self.assertIn("Chatting with crxzipple. Type /exit to quit.", chat_result.stdout)
                self.assertIn("hello from sample llm", chat_result.stdout)
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_cli_schema_error_detector_matches_missing_schema_messages(self) -> None:
            self.assertTrue(_is_missing_database_schema_error(RuntimeError("no such table: tools")))
            self.assertTrue(
                _is_missing_database_schema_error(
                    RuntimeError("no such column: llm_profiles.context_window_tokens"),
                ),
            )
            self.assertTrue(
                _is_missing_database_schema_error(
                    RuntimeError('relation "tools" does not exist'),
                ),
            )
            self.assertFalse(
                _is_missing_database_schema_error(RuntimeError("database is locked")),
            )


if __name__ == "__main__":
    unittest.main()
