from __future__ import annotations

from tests.unit.http_test_support import *


class AuthHttpTestCase(HttpModuleTestCase):
    def test_authorization_endpoints_list_policies_and_check(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            policies_response = client.get("/authorization/policies")
            self.assertEqual(policies_response.status_code, 200)
            policy_ids = [item["id"] for item in policies_response.json()]
            self.assertIn("allow_llm_invocation", policy_ids)
            self.assertIn("allow_safe_tool_execution", policy_ids)

            check_response = client.post(
                "/authorization/check",
                json={
                    "action": "tool.run",
                    "resource": {
                        "kind": "tool",
                        "id": "echo",
                        "attrs": {"mutates_state": False},
                    },
                    "context": {"attrs": {"interface": "http"}},
                },
            )
            self.assertEqual(check_response.status_code, 200)
            self.assertTrue(check_response.json()["allowed"])
        finally:
            client.close()

    def test_http_guard_returns_403_when_abac_blocks_tool_run(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            client.app.state.container.tool_service.register(
                RegisterToolInput(
                    id="dangerous_write",
                    name="Dangerous Write",
                    description="Mutates external state.",
                    mutates_state=True,
                ),
            )

            run_response = client.post(
                "/tools/dangerous_write/runs",
                json={"arguments": {}},
            )
            self.assertEqual(run_response.status_code, 403)
            self.assertIn("Authorization denied", run_response.json()["detail"])
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
