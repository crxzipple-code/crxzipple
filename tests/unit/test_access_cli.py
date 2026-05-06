from __future__ import annotations

from crxzipple.modules.llm.application import RegisterLlmProfileInput
from crxzipple.modules.llm.domain import LlmApiFamily, LlmProviderKind
from tests.unit.cli_test_support import *


class AccessCliTestCase(CliModuleTestCase):
    def test_access_check_and_setup_commands(self) -> None:
        env = dict(self.env)
        env["MISSING_ACCESS_TOKEN"] = ""

        check_result = self.runner.invoke(
            app,
            ["access", "check", "env:MISSING_ACCESS_TOKEN"],
            env=env,
        )
        self.assertEqual(check_result.exit_code, 0)
        self.assertIn('"status": "setup_needed"', check_result.stdout)
        self.assertIn('"kind": "env"', check_result.stdout)

        setup_result = self.runner.invoke(
            app,
            ["access", "setup", "codex_auth_json"],
            env=env,
        )
        self.assertEqual(setup_result.exit_code, 0)
        self.assertIn('"kind": "command"', setup_result.stdout)
        self.assertIn('"codex"', setup_result.stdout)
        self.assertIn('"login"', setup_result.stdout)
        self.assertIn('"actions"', setup_result.stdout)

    def test_access_inventory_command_lists_missing_assets(self) -> None:
        container = self.harness.build_container()
        try:
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="missing-cli-model",
                    provider=LlmProviderKind.OPENAI_COMPATIBLE,
                    api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
                    model_name="llama3.2",
                    base_url="http://127.0.0.1:1/v1",
                    credential_binding="env:MISSING_CLI_MODEL_TOKEN",
                ),
            )
        finally:
            container.close()

        env = dict(self.env)
        env["MISSING_CLI_MODEL_TOKEN"] = ""
        result = self.runner.invoke(app, ["access", "inventory"], env=env)

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"resource_type": "authorization"', result.stdout)
        self.assertIn('"display_name": "MISSING_CLI_MODEL_TOKEN"', result.stdout)
        self.assertIn('"missing-cli-model"', result.stdout)
        self.assertIn('"blocked": 1', result.stdout)


if __name__ == "__main__":
    unittest.main()
