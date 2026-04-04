from __future__ import annotations

from tests.unit.cli_test_support import *


class AuthCliTestCase(CliModuleTestCase):
    def test_auth_commands_list_policies_and_evaluate_requests(self) -> None:
            env = dict(self.env)
            env["APP_AUTHORIZATION_ENABLED"] = "true"
            env["APP_AUTHORIZATION_POLICY_PATHS"] = str(
                Path(__file__).resolve().parents[2]
                / "config"
                / "authorization_policies"
                / "default.yaml"
            )

            policies_result = self.runner.invoke(app, ["auth", "policies"], env=env)
            self.assertEqual(policies_result.exit_code, 0)
            self.assertIn('"id": "allow_llm_invocation"', policies_result.stdout)

            check_result = self.runner.invoke(
                app,
                [
                    "auth",
                    "check",
                    "llm.invoke",
                    "llm_profile",
                    "--resource-id",
                    "writer",
                    "--context",
                    '{"interface":"cli"}',
                ],
                env=env,
            )
            self.assertEqual(check_result.exit_code, 0)
            self.assertIn('"allowed": true', check_result.stdout)


if __name__ == "__main__":
    unittest.main()
