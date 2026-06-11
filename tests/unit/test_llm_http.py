from __future__ import annotations

from dataclasses import replace
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from crxzipple.core.config import LlmProfileSettings, load_settings
from crxzipple.interfaces.http.app import create_app
from crxzipple.modules.access.application.repositories import AccessOAuthAccountRecord
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument
from crxzipple.modules.settings import CreateSettingsResourceInput
from tests.unit.http_test_support import (
    AppKey,
    _FakeStreamResponse,
    HttpModuleTestCase,
    SampleLlmApiServer,
    SqliteTestHarness,
)


class LlmHttpTestCase(HttpModuleTestCase):
    def test_llm_profile_endpoints_register_fetch_and_list(self) -> None:
            settings_actions = self.client.app.state.container.require(
                AppKey.SETTINGS_ACTION_SERVICE,
            )
            settings_actions.create_resource = Mock(
                side_effect=AssertionError("HTTP LLM register must not write Settings"),
            )
            settings_actions.update_resource = Mock(
                side_effect=AssertionError("HTTP LLM register must not write Settings"),
            )

            with patch(
                "crxzipple.modules.llm.interfaces.http.register_llm_profile_input_from_config",
                side_effect=AssertionError("HTTP LLM register must not use Settings sync helper"),
            ):
                create_response = self.client.post(
                    "/llms",
                    json={
                        "id": "writer",
                        "provider": "openai",
                        "api_family": "openai_responses",
                        "model_name": "gpt-5",
                        "model_family": "reasoning",
                        "capabilities": ["tool_calling"],
                        "default_params": {
                            "temperature": 0.2,
                            "max_output_tokens": 512,
                            "extra_body": {
                                "chat_template_kwargs": {"enable_thinking": False},
                            },
                        },
                        "credential_binding_id": "openai-api-key",
                        "max_concurrency": 2,
                        "concurrency_key": "provider:openai",
                    },
                )
                update_response = self.client.put(
                    "/llms/writer",
                    json={
                        "id": "writer",
                        "provider": "openai",
                        "api_family": "openai_responses",
                        "model_name": "gpt-5.1",
                        "credential_binding_id": "openai-api-key",
                    },
                )

            self.assertEqual(create_response.status_code, 201)
            self.assertEqual(update_response.status_code, 200)
            self.assertEqual(create_response.json()["id"], "writer")
            self.assertEqual(create_response.json()["api_family"], "openai_responses")
            self.assertEqual(update_response.json()["model_name"], "gpt-5.1")
            self.assertEqual(
                create_response.json()["default_params"]["extra_body"],
                {"chat_template_kwargs": {"enable_thinking": False}},
            )
            self.assertEqual(create_response.json()["max_concurrency"], 2)
            self.assertEqual(create_response.json()["concurrency_key"], "provider:openai")

            get_response = self.client.get("/llms/writer")
            list_response = self.client.get("/llms")

            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["model_name"], "gpt-5.1")
            self.assertEqual(list_response.status_code, 200)
            profiles_by_id = {
                item["id"]: item
                for item in list_response.json()
            }
            self.assertIn("writer", profiles_by_id)
            self.assertEqual(
                profiles_by_id["writer"]["credential_binding_id"],
                "openai-api-key",
            )
            self.assertEqual(profiles_by_id["writer"]["source_kind"], "manual")

    def test_llm_profile_enable_disable_updates_llm_runtime_truth(self) -> None:
            create_response = self.client.post(
                "/llms",
                json={
                    "id": "writer",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5",
                    "model_family": "reasoning",
                    "capabilities": ["tool_calling"],
                    "default_params": {
                        "temperature": 0.2,
                        "max_output_tokens": 512,
                        "extra_body": {
                            "chat_template_kwargs": {"enable_thinking": False},
                        },
                    },
                    "credential_binding_id": "openai-api-key",
                    "max_concurrency": 2,
                    "concurrency_key": "provider:openai",
                },
            )

            self.assertEqual(create_response.status_code, 201)

            settings_actions = self.client.app.state.container.require(
                AppKey.SETTINGS_ACTION_SERVICE,
            )
            settings_actions.set_resource_enabled = Mock(
                side_effect=AssertionError("HTTP LLM enablement must not write Settings"),
            )

            disable_response = self.client.post("/llms/writer/disable")
            get_disabled_response = self.client.get("/llms/writer")
            enable_response = self.client.post("/llms/writer/enable")
            get_enabled_response = self.client.get("/llms/writer")

            self.assertEqual(disable_response.status_code, 200)
            self.assertFalse(disable_response.json()["enabled"])
            self.assertFalse(get_disabled_response.json()["enabled"])
            self.assertEqual(enable_response.status_code, 200)
            self.assertTrue(enable_response.json()["enabled"])
            self.assertTrue(get_enabled_response.json()["enabled"])

            delete_response = self.client.delete("/llms/writer")
            list_response = self.client.get("/llms")

            self.assertEqual(delete_response.status_code, 204)
            self.assertNotIn("writer", {item["id"] for item in list_response.json()})

    def test_llm_invoke_endpoint_uses_openai_compatible_adapter(self) -> None:
            server = SampleLlmApiServer(tool_calls_on_tools=True)
            previous_token = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sample-compat-token"
            server.start()

            try:
                create_response = self.client.post(
                    "/llms",
                    json={
                        "id": "local-chat",
                        "provider": "openai_compatible",
                        "api_family": "openai_chat_compatible",
                        "model_name": "llama3.2",
                        "base_url": f"{server.base_url}/v1",
                        "credential_binding_id": "openai-api-key",
                    },
                )

                self.assertEqual(create_response.status_code, 201)

                invoke_response = self.client.post(
                    "/llms/local-chat/invoke",
                    json={
                        "messages": [{"role": "user", "content": "hello"}],
                        "tool_schemas": [
                            {
                                "name": "search_docs",
                                "description": "Search docs",
                                "input_schema": {
                                    "type": "object",
                                    "properties": {"query": {"type": "string"}},
                                },
                            },
                        ],
                        "request_metadata": {
                            "prompt_mode": "normal_turn",
                            "context_render_snapshot_id": "ctxsnap_llm_http",
                            "mirrored_tool_schema_count": 1,
                        },
                    },
                )

                self.assertEqual(invoke_response.status_code, 201)
                payload = invoke_response.json()
                self.assertEqual(payload["status"], "succeeded")
                self.assertEqual(payload["provider_request_id"], "chatcmpl_sample_1")
                self.assertEqual(payload["result"]["text"], "hello from sample llm")
                self.assertEqual(payload["result"]["tool_calls"][0]["name"], "search_docs")

                list_response = self.client.get("/llms/local-chat/invocations")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(len(list_response.json()), 1)
                self.assertEqual(list_response.json()[0]["id"], payload["id"])

                preview_response = self.client.get(
                    f"/llms/calls/{payload['id']}/prompt-preview",
                    params={"run_id": "run_llm_http"},
                )
                self.assertEqual(preview_response.status_code, 200)
                preview_payload = preview_response.json()
                self.assertEqual(preview_payload["run_id"], "run_llm_http")
                self.assertEqual(preview_payload["invocation_id"], payload["id"])
                self.assertEqual(preview_payload["llm_id"], "local-chat")
                self.assertEqual(preview_payload["mode"], "normal_turn")
                self.assertEqual(
                    preview_payload["context_render_snapshot_id"],
                    "ctxsnap_llm_http",
                )
                self.assertIsNone(preview_payload["prompt_report"])
                self.assertIsNone(preview_payload["context_render"])
                self.assertEqual(preview_payload["provider_attachments"], {})
                self.assertEqual(
                    preview_payload["messages"],
                    payload["messages"],
                )
                self.assertEqual(
                    preview_payload["tool_schemas"],
                    payload["tool_schemas"],
                )
                self.assertEqual(
                    preview_payload["provider_request_options"]["request_source"],
                    "llm_invocation",
                )
                self.assertEqual(
                    preview_payload["provider_request_options"]["request_metadata"][
                        "context_render_snapshot_id"
                    ],
                    "ctxsnap_llm_http",
                )
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_token
                server.close()

    def test_llm_profile_test_endpoint_invokes_current_form_without_persisting(self) -> None:
            server = SampleLlmApiServer(tool_calls_on_tools=True)
            previous_token = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sample-compat-token"
            server.start()

            try:
                response = self.client.post(
                    "/llms/test",
                    json={
                        "profile": {
                            "id": "unsaved-local-chat",
                            "provider": "openai_compatible",
                            "api_family": "openai_chat_compatible",
                            "model_name": "llama3.2",
                            "base_url": f"{server.base_url}/v1",
                            "credential_binding_id": "openai-api-key",
                        },
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                )

                self.assertEqual(response.status_code, 201)
                payload = response.json()
                self.assertEqual(payload["llm_id"], "unsaved-local-chat")
                self.assertEqual(payload["status"], "succeeded")
                self.assertEqual(payload["result"]["text"], "hello from sample llm")

                list_response = self.client.get("/llms")
                invocation_response = self.client.get(
                    "/llms/unsaved-local-chat/invocations",
                )

                self.assertEqual(list_response.status_code, 200)
                self.assertNotIn(
                    "unsaved-local-chat",
                    {item["id"] for item in list_response.json()},
                )
                self.assertEqual(invocation_response.status_code, 200)
                self.assertEqual(invocation_response.json(), [])
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_token
                server.close()

    def test_llm_stream_endpoint_returns_sse_events_for_codex(self) -> None:
        with tempfile.TemporaryDirectory():
            container = self.client.app.state.container
            container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE).write_token(
                "oauth_tokens/codex-http.json",
                OAuthTokenDocument(
                    access_token="codex-http-token",
                    refresh_token="codex-http-refresh",
                ),
            )
            container.require(AppKey.ACCESS_GOVERNANCE_REPOSITORY).upsert_oauth_account(
                AccessOAuthAccountRecord(
                    account_id="openai-codex:http-test",
                    provider_id="openai-codex",
                    credential_binding_id="codex-test",
                    storage_key="oauth_tokens/codex-http.json",
                    status="active",
                ),
            )
            self.client.app.state.container.require(
                AppKey.SETTINGS_ACTION_SERVICE,
            ).create_resource(
                CreateSettingsResourceInput(
                    resource_id="codex-test",
                    resource_kind="access-assets",
                    owner_module="access",
                    payload={
                        "access_declaration_kind": "credential_binding",
                        "binding_id": "codex-test",
                        "binding_kind": "oauth2_account",
                        "source_kind": "oauth_account",
                        "source_ref": "openai-codex:http-test",
                        "masked_preview": "oauth_account",
                        "status": "active",
                    },
                    reason="seed codex test credential binding",
                    publish=True,
                ),
            )
            create_response = self.client.post(
                "/llms",
                json={
                    "id": "codex-profile",
                    "provider": "openai_codex",
                    "api_family": "openai_codex_responses",
                    "model_name": "gpt-5-codex",
                    "model_family": "codex",
                    "credential_binding_id": "codex-test",
                },
            )

            self.assertEqual(create_response.status_code, 201)

            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.requests.post",
                return_value=_FakeStreamResponse(
                    events=(
                        (
                            "response.output_text.delta",
                            {
                                "type": "response.output_text.delta",
                                "delta": "codex-",
                            },
                        ),
                        (
                            "response.completed",
                            {
                                "type": "response.completed",
                                "response": {
                                    "id": "resp_http_codex_1",
                                    "status": "completed",
                                    "model": "gpt-5.1-codex",
                                    "output": [
                                        {
                                            "type": "message",
                                            "content": [
                                                {
                                                    "type": "output_text",
                                                    "text": "codex-http-ok",
                                                },
                                            ],
                                        },
                                    ],
                                    "usage": {
                                        "input_tokens": 5,
                                        "output_tokens": 3,
                                        "total_tokens": 8,
                                    },
                                },
                            },
                        ),
                    ),
                ),
            ):
                with self.client.stream(
                    "POST",
                    "/llms/codex-profile/stream",
                    json={
                        "messages": [
                            {"role": "system", "content": "You are a concise coding assistant."},
                            {"role": "user", "content": "Reply with codex-http-ok."},
                        ],
                    },
                ) as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers["content-type"]
                    status_code = response.status_code

            self.assertEqual(status_code, 200)
            self.assertIn("text/event-stream", content_type)
            self.assertIn("event: invocation_started", body)
            self.assertIn("event: text_delta", body)
            self.assertIn("event: completed", body)
            self.assertIn("codex-http-ok", body)

    def test_llm_sync_profiles_endpoint_loads_configured_profiles(self) -> None:
            harness = SqliteTestHarness()
            settings = replace(
                load_settings(),
                database_url=harness.database_url,
                llm_profiles=(
                    LlmProfileSettings(
                        id="openai.gpt-5.4",
                        provider="openai",
                        api_family="openai_responses",
                        model_name="gpt-5.4",
                        model_family="reasoning",
                        capabilities=("tool_calling", "structured_output"),
                        default_params={
                            "reasoning_effort": "medium",
                            "extra_body": {
                                "chat_template_kwargs": {"enable_thinking": False},
                            },
                        },
                        credential_binding_id="openai-api-key",
                        timeout_seconds=120,
                        max_concurrency=2,
                        concurrency_key="provider:openai",
                    ),
                ),
            )

            harness.initialize_schema(settings=settings)
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                ),
            )

            try:
                sync_response = client.post("/llms/sync-profiles")
                self.assertEqual(sync_response.status_code, 200)
                sync_payload = sync_response.json()
                self.assertEqual([item["id"] for item in sync_payload], ["openai.gpt-5.4"])
                self.assertEqual(
                    sync_payload[0]["default_params"]["reasoning_effort"],
                    "medium",
                )
                self.assertEqual(
                    sync_payload[0]["default_params"]["extra_body"],
                    {"chat_template_kwargs": {"enable_thinking": False}},
                )
                self.assertEqual(sync_payload[0]["max_concurrency"], 2)
                self.assertEqual(sync_payload[0]["concurrency_key"], "provider:openai")

                list_response = client.get("/llms")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(
                    [item["id"] for item in list_response.json()],
                    ["openai.gpt-5.4"],
                )
            finally:
                client.close()
                client.app.state.container.close()
                harness.close()

    def test_llm_sync_profiles_endpoint_ignores_legacy_settings_resources(self) -> None:
            harness = SqliteTestHarness()
            settings = replace(
                load_settings(),
                database_url=harness.database_url,
                llm_profiles=(),
            )

            harness.initialize_schema(settings=settings)
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                ),
            )

            try:
                client.app.state.container.require(
                    AppKey.SETTINGS_ACTION_SERVICE,
                ).create_resource(
                    CreateSettingsResourceInput(
                        resource_id="legacy-openai",
                        resource_kind="llm-profiles",
                        owner_module="llm",
                        payload={
                            "provider": "openai",
                            "api_family": "openai_responses",
                            "model_name": "legacy-gpt",
                        },
                        reason="seed legacy settings profile",
                        publish=True,
                    ),
                )

                sync_response = client.post(
                    "/llms/sync-profiles",
                    params={"profile": "legacy-openai"},
                )
                list_response = client.get("/llms")

                self.assertEqual(sync_response.status_code, 200)
                self.assertEqual(sync_response.json(), [])
                self.assertEqual(list_response.status_code, 200)
                self.assertNotIn(
                    "legacy-openai",
                    {item["id"] for item in list_response.json()},
                )
            finally:
                client.close()
                client.app.state.container.close()
                harness.close()


if __name__ == "__main__":
    unittest.main()
