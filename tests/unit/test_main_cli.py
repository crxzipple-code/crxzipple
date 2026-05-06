from __future__ import annotations

from tests.unit.cli_test_support import *


class MainCliTurnTestCase(CliModuleTestCase):
    def _ensure_orchestration_runtime(self) -> None:
        for service_key in (
            "worker:orchestration-scheduler",
            "worker:orchestration",
        ):
            result = self.runner.invoke(
                app,
                ["daemon", "ensure", service_key],
                env=self.env,
            )
            self.assertEqual(result.exit_code, 0, msg=result.stdout)

    def _stop_all_daemons(self) -> None:
        result = self.runner.invoke(
            app,
            ["daemon", "stop-all"],
            env=self.env,
        )
        self.assertEqual(result.exit_code, 0, msg=result.stdout)

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

            self._ensure_orchestration_runtime()

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
            self._stop_all_daemons()
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_crxzipple_ask_requires_orchestration_runtime(self) -> None:
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

            self.assertEqual(ask_result.exit_code, 1)
            self.assertIn(
                "Orchestration runtime is not running",
                ask_result.stderr or ask_result.output,
            )
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

            self._ensure_orchestration_runtime()

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
            self._stop_all_daemons()
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()


if __name__ == "__main__":
    unittest.main()
