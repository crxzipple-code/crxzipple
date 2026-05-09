from __future__ import annotations

import unittest

from crxzipple.modules.settings import CreateSettingsResourceInput
from tests.unit.cli_test_support import CliModuleTestCase, app


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
            container.settings_action_service.create_resource(
                CreateSettingsResourceInput(
                    resource_id="missing-cli-model",
                    resource_kind="llm-profiles",
                    owner_module="llm",
                    payload={
                        "profile_id": "missing-cli-model",
                        "provider": "openai_compatible",
                        "api_family": "openai_chat_compatible",
                        "model_name": "llama3.2",
                        "base_url": "http://127.0.0.1:1/v1",
                        "credential_binding": "env:MISSING_CLI_MODEL_TOKEN",
                    },
                    reason="seed settings-owned llm profile",
                    publish=True,
                ),
            )
        finally:
            container.close()

        env = dict(self.env)
        env["MISSING_CLI_MODEL_TOKEN"] = ""
        result = self.runner.invoke(app, ["access", "inventory"], env=env)

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"resource_type": "access_requirement"', result.stdout)
        self.assertIn('"display_name": "MISSING_CLI_MODEL_TOKEN"', result.stdout)
        self.assertIn('"missing-cli-model"', result.stdout)
        self.assertIn('"blocked": 1', result.stdout)


if __name__ == "__main__":
    unittest.main()
