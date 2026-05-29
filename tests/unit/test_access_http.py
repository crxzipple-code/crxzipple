from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from crxzipple.modules.channels import ChannelAccountProfile, ChannelProfile
from tests.unit.http_test_support import AppKey, HttpModuleTestCase
from tests.unit.tool_catalog_seed import seed_catalog_tool


class AccessHttpTestCase(HttpModuleTestCase):
    def test_access_action_rejects_internal_abac_policy_governance(
        self,
    ) -> None:
        response = self.client.post(
            "/access/actions",
            json={
                "action_id": "act_create_policy",
                "resource_kind": "authorization_policy",
                "target_id": "policy_allow_http_llm",
                "intent": "create_authorization_policy",
                "changes": {
                    "name": "Allow HTTP LLM",
                    "effect": "allow",
                    "policy_spec": {
                        "actions": ["llm.invoke.special"],
                        "subject": {"type": "interface", "id": "http"},
                        "resource": {"kind": "llm_profile", "id": "writer"},
                    },
                },
                "reason": "internal ABAC policy belongs to authorization",
                "actor": "unit-test",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unsupported access action intent", response.text)
        self.assertNotIn("raw-secret", response.text)

    def test_access_action_registers_binding_through_settings_actions(self) -> None:
        response = self.client.post(
            "/access/actions",
            json={
                "action_id": "act_register_openai",
                "resource_kind": "credential_binding",
                "target_id": "cred_openai_env",
                "intent": "register_env_binding",
                "changes": {
                    "source_ref": "OPENAI_API_KEY",
                    "binding_kind": "api_key",
                },
                "reason": "register OpenAI credential source",
                "actor": "unit-test",
                "trace_context": {"request_id": "trace-1"},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["asset"]["binding_id"], "cred_openai_env")
        self.assertNotIn("sk-should-not-persist", response.text)
        self.assertNotIn("trace-secret", response.text)

        container = self.client.app.state.container
        settings_query_service = container.require(AppKey.SETTINGS_QUERY_SERVICE)
        resolution = settings_query_service.get_effective(
            "cred_openai_env",
        )
        binding = resolution.effective_value["credential_bindings"][0]
        self.assertEqual(binding["source_kind"], "env")
        self.assertEqual(binding["source_ref"], "OPENAI_API_KEY")
        persisted_payload = repr(binding) + repr(
            settings_query_service.list_audits(),
        )
        self.assertNotIn("sk-should-not-persist", persisted_payload)
        self.assertNotIn("trace-secret", persisted_payload)
        self.assertEqual(
            container.require(AppKey.ACCESS_ACTION_AUDIT_REPOSITORY).list_recent(),
            (),
        )

    def test_access_action_updates_binding_through_settings_actions(self) -> None:
        register_response = self.client.post(
            "/access/actions",
            json={
                "action_id": "act_register_openai",
                "resource_kind": "credential_binding",
                "target_id": "cred_openai_env",
                "intent": "register_env_binding",
                "changes": {
                    "source_ref": "OPENAI_API_KEY",
                    "binding_kind": "api_key",
                    "asset_id": "asset_openai",
                },
                "reason": "register OpenAI credential source",
                "actor": "unit-test",
            },
        )
        self.assertEqual(register_response.status_code, 200)

        response = self.client.post(
            "/access/actions",
            json={
                "action_id": "act_update_openai",
                "resource_kind": "credential_binding",
                "target_id": "cred_openai_env",
                "intent": "update_credential_binding",
                "changes": {
                    "source_kind": "file",
                    "source_ref": "file:/tmp/openai-token.txt",
                    "binding_kind": "api_key",
                    "masked_preview": "file:***",
                    "status": "disabled",
                },
                "reason": "move OpenAI credential source",
                "confirmation": "cred_openai_env",
                "risk_acknowledged": True,
                "actor": "unit-test",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["asset"]["binding_id"], "cred_openai_env")
        self.assertEqual(payload["asset"]["asset_id"], "asset_openai")
        self.assertEqual(payload["asset"]["source_ref"], "file:/tmp/openai-token.txt")
        self.assertEqual(
            payload["validation"]["before_redacted"]["source_ref"],
            "env:OPENAI_API_KEY",
        )
        self.assertEqual(
            payload["validation"]["after_redacted"]["source_ref"],
            "file:/tmp/openai-token.txt",
        )

        container = self.client.app.state.container
        resolution = container.require(AppKey.SETTINGS_QUERY_SERVICE).get_effective(
            "cred_openai_env",
        )
        binding = resolution.effective_value["credential_bindings"][0]
        self.assertEqual(binding["source_kind"], "file")
        self.assertEqual(binding["source_ref"], "/tmp/openai-token.txt")
        self.assertEqual(binding["asset_id"], "asset_openai")
        self.assertEqual(binding["status"], "disabled")
        self.assertEqual(
            container.require(AppKey.ACCESS_ACTION_AUDIT_REPOSITORY).list_recent(),
            (),
        )

    def test_access_action_rejects_raw_secret_inputs(self) -> None:
        response = self.client.post(
            "/access/actions",
            json={
                "action_id": "act_register_openai",
                "resource_kind": "credential_binding",
                "target_id": "cred_openai_env",
                "intent": "register_env_binding",
                "changes": {
                    "source_ref": "OPENAI_API_KEY",
                    "api" + "_key": "sk-should-not-persist",
                },
                "reason": "register OpenAI credential source",
                "actor": "unit-test",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("raw secret values", response.text)
        self.assertNotIn("sk-should-not-persist", response.text)

    def test_access_check_returns_missing_env_setup_flow(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            with patch.dict("os.environ", {"MISSING_ACCESS_TOKEN": ""}):
                response = client.post(
                    "/access/check",
                    json={"requirements": ["env:MISSING_ACCESS_TOKEN"]},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertFalse(payload["ready"])
            check = payload["checks"][0]
            self.assertEqual(check["target_type"], "requirement")
            self.assertEqual(check["status"], "setup_needed")
            self.assertEqual(check["setup_flow"]["kind"], "env")
            self.assertEqual(check["setup_flow"]["env_vars"], ["MISSING_ACCESS_TOKEN"])
            self.assertEqual(
                check["setup_flow"]["actions"][0]["kind"],
                "configure_env",
            )
            self.assertNotIn("value", check["setup_flow"])
        finally:
            client.close()

    def test_access_setup_no_longer_returns_codex_cli_login_action(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            response = client.post("/access/setup", json={"target": "codex_auth_json"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["kind"], "unsupported")
            self.assertEqual(payload["command"], [])
            self.assertEqual(payload["actions"], [])
        finally:
            client.close()

    def test_access_inventory_does_not_reverse_scan_backend_services(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            llm_response = client.post(
                "/llms",
                json={
                    "id": "missing-access-model",
                    "provider": "openai_compatible",
                    "api_family": "openai_chat_compatible",
                    "model_name": "llama3.2",
                    "base_url": "http://127.0.0.1:1/v1",
                },
            )
            self.assertEqual(llm_response.status_code, 201)
            second_llm_response = client.post(
                "/llms",
                json={
                    "id": "missing-access-model-alt",
                    "provider": "openai_compatible",
                    "api_family": "openai_chat_compatible",
                    "model_name": "llama3.2-alt",
                    "base_url": "http://127.0.0.1:1/v1",
                },
            )
            self.assertEqual(second_llm_response.status_code, 201)
            seed_catalog_tool(
                client.app.state.container,
                tool_id="missing-access-model-tool",
                name="Missing Access Model Tool",
                description="Needs the same OpenAI API token.",
                access_requirements=("openai:api_key(env:MISSING_MODEL_TOKEN)",),
            )
            seed_catalog_tool(
                client.app.state.container,
                tool_id="missing-access-tool",
                name="Missing Access Tool",
                description="Needs a token.",
                access_requirements=("env:MISSING_TOOL_TOKEN",),
            )
            seed_catalog_tool(
                client.app.state.container,
                tool_id="missing-access-tool-alt",
                name="Missing Access Tool Alt",
                description="Needs the same token.",
                access_requirements=("env:MISSING_TOOL_TOKEN",),
            )
            client.app.state.container.require(AppKey.CHANNEL_PROFILE_SERVICE).upsert_profile(
                ChannelProfile(
                    channel_type="webhook",
                    accounts=(
                        ChannelAccountProfile(
                            account_id="default",
                            metadata={
                                "access_requirements": ["env:MISSING_WEBHOOK_TOKEN"],
                            },
                        ),
                    ),
                ),
            )

            with tempfile.TemporaryDirectory() as codex_home:
                with patch.dict(
                    "os.environ",
                    {
                        "CODEX_HOME": codex_home,
                        "MISSING_MODEL_TOKEN": "",
                        "MISSING_TOOL_TOKEN": "",
                        "MISSING_WEBHOOK_TOKEN": "",
                    },
                ):
                    response = client.get("/access/inventory")
                    include_ready_response = client.get(
                        "/access/inventory?include_ready=true",
                    )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(include_ready_response.status_code, 200)
            payload = response.json()
            include_ready_payload = include_ready_response.json()
            self.assertGreaterEqual(payload["counts"]["total"], 1)
            self.assertNotIn("MISSING_MODEL_TOKEN", response.text)
            self.assertNotIn("missing-access-model", include_ready_response.text)
            self.assertNotIn("missing-access-model-tool", include_ready_response.text)
            self.assertNotIn("MISSING_TOOL_TOKEN", include_ready_response.text)
            self.assertNotIn("MISSING_WEBHOOK_TOKEN", include_ready_response.text)
            self.assertGreaterEqual(include_ready_payload["counts"]["total"], 1)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
