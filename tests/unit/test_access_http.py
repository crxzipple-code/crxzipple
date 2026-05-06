from __future__ import annotations

import tempfile

from crxzipple.modules.channels import ChannelAccountProfile, ChannelProfile
from tests.unit.http_test_support import *


class AccessHttpTestCase(HttpModuleTestCase):
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

    def test_access_inventory_reports_backend_tool_and_channel_setup_needs(self) -> None:
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
            self.assertFalse(payload["ready"])
            self.assertEqual(payload["counts"]["blocked"], 4)
            targets = {item["display_name"]: item for item in payload["targets"]}
            self.assertEqual(
                sorted(target["resource_type"] for target in targets.values()),
                ["authorization", "authorization", "authorization", "authorization"],
            )
            self.assertIn("MISSING_MODEL_TOKEN", targets)
            self.assertIn("MISSING_TOOL_TOKEN", targets)
            self.assertIn("MISSING_WEBHOOK_TOKEN", targets)
            self.assertIn("codex_auth_json", targets)
            llm_target = targets["MISSING_MODEL_TOKEN"]
            self.assertEqual(llm_target["metadata"]["asset_kind"], "env")
            self.assertEqual(llm_target["metadata"]["usage_count"], 3)
            self.assertEqual(
                sorted(llm_target["metadata"]["usage_types"]),
                ["llm_profile", "tool"],
            )
            self.assertEqual(
                sorted(llm_target["metadata"]["llm_profile_ids"]),
                ["missing-access-model", "missing-access-model-alt"],
            )
            self.assertEqual(
                sorted(llm_target["metadata"]["tool_ids"]),
                ["missing-access-model-tool"],
            )
            self.assertEqual(
                sorted(llm_target["metadata"]["declared_requirements"]),
                [
                    "env:MISSING_MODEL_TOKEN",
                    "openai:api_key(env:MISSING_MODEL_TOKEN)",
                ],
            )
            llm_check = llm_target["requirement_sets"][0]["checks"][0]
            self.assertEqual(llm_check["target_type"], "credential_binding")
            self.assertEqual(llm_check["requirement"], "env:MISSING_MODEL_TOKEN")
            self.assertEqual(
                llm_check["setup_flow"]["actions"][0]["kind"],
                "configure_env",
            )
            codex_target = targets["codex_auth_json"]
            self.assertEqual(codex_target["metadata"]["asset_kind"], "codex_auth_json")
            self.assertEqual(codex_target["metadata"]["usage_count"], 2)
            self.assertEqual(
                sorted(codex_target["metadata"]["llm_profile_ids"]),
                ["missing-codex-model", "missing-codex-model-alt"],
            )
            codex_check = codex_target["requirement_sets"][0]["checks"][0]
            self.assertEqual(codex_check["target_type"], "credential_binding")
            self.assertEqual(codex_check["requirement"], "codex_auth_json")
            self.assertEqual(
                codex_check["setup_flow"]["actions"][0]["kind"],
                "run_command",
            )
            tool_target = targets["MISSING_TOOL_TOKEN"]
            self.assertEqual(
                sorted(tool_target["metadata"]["tool_ids"]),
                ["missing-access-tool", "missing-access-tool-alt"],
            )
            tool_check = tool_target["requirement_sets"][0]["checks"][0]
            self.assertEqual(tool_check["target_type"], "credential_binding")
            self.assertEqual(tool_check["setup_flow"]["env_vars"], ["MISSING_TOOL_TOKEN"])
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
