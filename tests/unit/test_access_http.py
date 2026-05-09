from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from crxzipple.modules.channels import ChannelAccountProfile, ChannelProfile
from crxzipple.modules.tool.application import RegisterToolInput
from tests.unit.http_test_support import HttpModuleTestCase


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
        resolution = container.settings_query_service.get_effective(
            "cred_openai_env",
        )
        binding = resolution.effective_value["credential_bindings"][0]
        self.assertEqual(binding["source_kind"], "env")
        self.assertEqual(binding["source_ref"], "OPENAI_API_KEY")
        persisted_payload = repr(binding) + repr(
            container.settings_query_service.list_audits(),
        )
        self.assertNotIn("sk-should-not-persist", persisted_payload)
        self.assertNotIn("trace-secret", persisted_payload)
        self.assertEqual(container.access_action_audit_repository.list_recent(), ())

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

    def test_access_setup_returns_codex_login_action(self) -> None:
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
            self.assertEqual(payload["kind"], "command")
            self.assertEqual(payload["command"], ["codex", "login"])
            self.assertIn("auth.json", payload["path"])
            self.assertEqual(payload["actions"][0]["kind"], "run_command")
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
                    "credential_binding": "env:MISSING_MODEL_TOKEN",
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
                    "credential_binding": "env:MISSING_MODEL_TOKEN",
                },
            )
            self.assertEqual(second_llm_response.status_code, 201)
            codex_llm_response = client.post(
                "/llms",
                json={
                    "id": "missing-codex-model",
                    "provider": "openai_codex",
                    "api_family": "openai_codex_responses",
                    "model_name": "gpt-5-codex",
                    "model_family": "codex",
                    "credential_binding": "codex_auth_json",
                },
            )
            self.assertEqual(codex_llm_response.status_code, 201)
            codex_alias_llm_response = client.post(
                "/llms",
                json={
                    "id": "missing-codex-model-alt",
                    "provider": "openai_codex",
                    "api_family": "openai_codex_responses",
                    "model_name": "gpt-5-codex-alt",
                    "model_family": "codex",
                    "credential_binding": "codex-cli",
                },
            )
            self.assertEqual(codex_alias_llm_response.status_code, 201)
            inline_llm_response = client.post(
                "/llms",
                json={
                    "id": "inline-secret-model",
                    "provider": "openai_compatible",
                    "api_family": "openai_chat_compatible",
                    "model_name": "inline-secret-model",
                    "base_url": "http://127.0.0.1:1/v1",
                    "credential_binding": "inline-secret-token",
                },
            )
            self.assertEqual(inline_llm_response.status_code, 201)
            client.app.state.container.tool_service.register(
                RegisterToolInput(
                    id="missing-access-model-tool",
                    name="Missing Access Model Tool",
                    description="Needs the same OpenAI API token.",
                    access_requirements=("openai:api_key(env:MISSING_MODEL_TOKEN)",),
                ),
            )
            client.app.state.container.tool_service.register(
                RegisterToolInput(
                    id="missing-access-tool",
                    name="Missing Access Tool",
                    description="Needs a token.",
                    access_requirements=("env:MISSING_TOOL_TOKEN",),
                ),
            )
            client.app.state.container.tool_service.register(
                RegisterToolInput(
                    id="missing-access-tool-alt",
                    name="Missing Access Tool Alt",
                    description="Needs the same token.",
                    access_requirements=("env:MISSING_TOOL_TOKEN",),
                ),
            )
            client.app.state.container.channel_profile_service.upsert_profile(
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
            self.assertNotIn("inline-secret-token", include_ready_response.text)
            payload = response.json()
            include_ready_payload = include_ready_response.json()
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["counts"], {"total": 0, "ready": 0, "blocked": 0})
            self.assertNotIn("MISSING_MODEL_TOKEN", response.text)
            self.assertNotIn("codex_auth_json", response.text)
            self.assertNotIn("MISSING_TOOL_TOKEN", include_ready_response.text)
            self.assertNotIn("MISSING_WEBHOOK_TOKEN", include_ready_response.text)
            self.assertEqual(
                include_ready_payload["counts"],
                {"total": 0, "ready": 0, "blocked": 0},
            )
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
