from __future__ import annotations

from tests.unit.http_test_support import *


class LlmHttpTestCase(HttpModuleTestCase):
    def test_llm_profile_endpoints_register_fetch_and_list(self) -> None:
            create_response = self.client.post(
                "/llms",
                json={
                    "id": "writer",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5",
                    "model_family": "reasoning",
                    "capabilities": ["tool_calling"],
                    "default_params": {"temperature": 0.2, "max_output_tokens": 512},
                    "credential_binding": "env:OPENAI_API_KEY",
                },
            )

            self.assertEqual(create_response.status_code, 201)
            self.assertEqual(create_response.json()["id"], "writer")
            self.assertEqual(create_response.json()["api_family"], "openai_responses")

            get_response = self.client.get("/llms/writer")
            list_response = self.client.get("/llms")

            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["model_name"], "gpt-5")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(len(list_response.json()), 1)
            self.assertEqual(list_response.json()[0]["credential_binding"], "env:OPENAI_API_KEY")

    def test_llm_invoke_endpoint_uses_openai_compatible_adapter(self) -> None:
            server = SampleLlmApiServer(tool_calls_on_tools=True)
            previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
            os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
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
                        "credential_binding": "env:OPENAI_COMPATIBLE_TOKEN",
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
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_llm_stream_endpoint_returns_sse_events_for_codex(self) -> None:
            create_response = self.client.post(
                "/llms",
                json={
                    "id": "codex-profile",
                    "provider": "openai_codex",
                    "api_family": "openai_codex_responses",
                    "model_name": "gpt-5-codex",
                    "model_family": "codex",
                    "credential_binding": "codex-inline-token",
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
                        default_params={"reasoning_effort": "medium"},
                        credential_binding="env:OPENAI_API_KEY",
                        timeout_seconds=120,
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

                list_response = client.get("/llms")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(
                    [item["id"] for item in list_response.json()],
                    ["openai.gpt-5.4"],
                )
            finally:
                client.close()
                client.app.state.container.engine.dispose()
                harness.close()


if __name__ == "__main__":
    unittest.main()
