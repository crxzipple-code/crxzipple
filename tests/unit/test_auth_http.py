from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from tests.unit.http_test_support import HttpModuleTestCase
from tests.unit.tool_catalog_seed import seed_catalog_tool


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
            self.assertIn("allow_browser_tool_execution", policy_ids)

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

            browser_check_response = client.post(
                "/authorization/check",
                json={
                    "action": "tool.run",
                    "resource": {
                        "kind": "tool",
                        "id": "browser.navigate",
                        "attrs": {
                            "source_id": "configured.browser",
                            "mutates_state": True,
                        },
                    },
                    "context": {"attrs": {"interface": "http"}},
                },
            )
            self.assertEqual(browser_check_response.status_code, 200)
            self.assertTrue(browser_check_response.json()["allowed"])
        finally:
            client.close()

    def test_authorization_governance_endpoints_manage_policies(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            policy_payload = {
                "id": "local_allow_echo_http",
                "effect": "allow",
                "actions": ["tool.run"],
                "resource_kind": "tool",
                "resource_id": "echo",
                "priority": 20,
                "actor": {"type": "test", "id": "operator"},
                "reason": "http governance test",
            }
            create_response = client.post(
                "/authorization/policies",
                json=policy_payload,
            )
            self.assertEqual(create_response.status_code, 201)
            self.assertEqual(create_response.json()["id"], "local_allow_echo_http")

            dry_run_payload = {
                "request": {
                    "action": "tool.run",
                    "resource": {"kind": "tool", "id": "echo"},
                    "context": {"attrs": {"interface": "http"}},
                },
                "actor": {"type": "test", "id": "operator"},
            }
            dry_run_response = client.post(
                "/authorization/policies/dry-run",
                json=dry_run_payload,
            )
            self.assertEqual(dry_run_response.status_code, 200)
            self.assertTrue(dry_run_response.json()["allowed"])

            disable_response = client.post(
                "/authorization/policies/local_allow_echo_http/disable",
                json={"actor": {"type": "test", "id": "operator"}},
            )
            self.assertEqual(disable_response.status_code, 200)
            self.assertFalse(disable_response.json()["enabled"])

            impact_response = client.post(
                "/authorization/policies/impact",
                json={
                    **dry_run_payload,
                    "proposed_policies": [
                        {
                            **policy_payload,
                            "enabled": True,
                            "actor": {"type": "test", "id": "operator"},
                        },
                    ],
                },
            )
            self.assertEqual(impact_response.status_code, 200)
            self.assertTrue(impact_response.json()["changed"])
            self.assertTrue(impact_response.json()["after"]["allowed"])

            import_response = client.post(
                "/authorization/policies/import",
                json={
                    "source": "test.yaml",
                    "content": """
- id: local_allow_llm_http
  effect: allow
  actions:
    - llm.invoke
  resource:
    kind: llm_profile
""",
                    "actor": {"type": "test", "id": "operator"},
                },
            )
            self.assertEqual(import_response.status_code, 200)
            self.assertEqual(import_response.json()["imported"], 1)

            export_response = client.get("/authorization/policies/export")
            self.assertEqual(export_response.status_code, 200)
            self.assertIn(
                "local_allow_llm_http",
                [item["id"] for item in export_response.json()["policies"]],
            )

            audit_response = client.get(
                "/authorization/audits",
                params={"action": "policy.import"},
            )
            self.assertEqual(audit_response.status_code, 200)
            self.assertEqual(audit_response.json()[0]["action"], "policy.import")
        finally:
            client.close()

    def test_agent_grant_endpoints_hide_abac_policy_shape(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            grant_response = client.post(
                "/authorization/agent-grants",
                json={
                    "agent_id": "assistant",
                    "kind": "effect",
                    "id": "weather_data",
                    "actor": {"type": "test", "id": "operator"},
                    "reason": "agent profile preauthorization",
                },
            )
            self.assertEqual(grant_response.status_code, 200)
            grant = grant_response.json()
            self.assertEqual(grant["status"], "enabled")
            self.assertEqual(
                grant["policy_id"],
                "local_allow_agent_effect__assistant__weather_data",
            )
            self.assertEqual(grant["policy"]["actions"], ["tool.effect.authorize"])

            check_response = client.post(
                "/authorization/check",
                json={
                    "action": "tool.effect.authorize",
                    "resource": {
                        "kind": "tool",
                        "id": "weather.forecast",
                        "attrs": {"authorization_effect_ids": ["weather_data"]},
                    },
                    "context": {"attrs": {"agent_id": "assistant"}},
                },
            )
            self.assertEqual(check_response.status_code, 200)
            self.assertTrue(check_response.json()["allowed"])

            revoke_response = client.post(
                "/authorization/agent-grants/revoke",
                json={
                    "agent_id": "assistant",
                    "kind": "effect",
                    "id": "weather_data",
                    "actor": {"type": "test", "id": "operator"},
                    "reason": "agent profile revoke",
                },
            )
            self.assertEqual(revoke_response.status_code, 200)
            self.assertEqual(revoke_response.json()["status"], "revoked")

            policies_response = client.get("/authorization/policies")
            self.assertEqual(policies_response.status_code, 200)
            self.assertNotIn(
                "local_allow_agent_effect__assistant__weather_data",
                [item["id"] for item in policies_response.json()],
            )
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
            seed_catalog_tool(
                client.app.state.container,
                tool_id="dangerous_write",
                name="Dangerous Write",
                description="Mutates external state.",
                mutates_state=True,
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
