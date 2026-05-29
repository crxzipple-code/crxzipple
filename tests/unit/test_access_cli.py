from __future__ import annotations

import json
import unittest

from crxzipple.modules.settings import CreateSettingsResourceInput
from crxzipple.interfaces.runtime_container import AppKey
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
            ["access", "setup", "env:MISSING_ACCESS_TOKEN"],
            env=env,
        )
        self.assertEqual(setup_result.exit_code, 0)
        self.assertIn('"kind": "env"', setup_result.stdout)
        self.assertIn('"MISSING_ACCESS_TOKEN"', setup_result.stdout)
        self.assertIn('"actions"', setup_result.stdout)

    def test_access_inventory_command_does_not_reverse_scan_llm_profiles(self) -> None:
        container = self.harness.build_runtime_container()
        container.require(AppKey.SETTINGS_ACTION_SERVICE).create_resource(
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
                    "credential_binding_id": "missing-cli-model-token",
                },
                reason="seed settings-owned llm profile",
                publish=True,
            ),
        )

        env = dict(self.env)
        env["MISSING_CLI_MODEL_TOKEN"] = ""
        result = self.runner.invoke(app, ["access", "inventory"], env=env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertGreaterEqual(payload["counts"]["total"], 1)
        self.assertNotIn("missing-cli-model-token", result.stdout)
        self.assertNotIn("missing-cli-model", result.stdout)


if __name__ == "__main__":
    unittest.main()
