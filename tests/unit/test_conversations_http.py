from __future__ import annotations

from tests.unit.http_test_support import *


class ConversationsHttpTestCase(HttpModuleTestCase):
    def test_conversation_messages_endpoint_reads_history_by_session_key(self) -> None:
        server = SampleLlmApiServer()
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
        server.start()

        try:
            llm_response = self.client.post(
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
            self.assertEqual(llm_response.status_code, 201)

            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "crxzipple",
                    "name": "crxzipple",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "hello",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            payload = turn_response.json()
            session_key = payload["run"]["session_key"]

            processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-history-worker",
            )
            self.assertIsNotNone(processed)

            history_response = self.client.get(f"/conversations/{session_key}/messages")
            self.assertEqual(history_response.status_code, 200)
            history_payload = history_response.json()
            self.assertEqual([item["role"] for item in history_payload], ["user", "assistant"])
            self.assertNotIn("content", history_payload[0])
            self.assertEqual(
                history_payload[0]["content_payload"],
                {"blocks": [{"type": "text", "text": "hello"}]},
            )
            self.assertNotIn("content", history_payload[1])
            self.assertEqual(
                history_payload[1]["content_payload"]["blocks"],
                [{"type": "text", "text": "hello from sample llm"}],
            )
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_conversations_endpoints_list_and_get_summaries(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
            os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
            server.start()

            try:
                llm_response = self.client.post(
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
                self.assertEqual(llm_response.status_code, 201)

                agent_response = self.client.post(
                    "/agents",
                    json={
                        "id": "crxzipple",
                        "name": "crxzipple",
                        "llm_routing_policy": {"default_llm_id": "local-chat"},
                        "instruction_policy": {"system_prompt": "Be helpful."},
                    },
                )
                self.assertEqual(agent_response.status_code, 201)

                turn_response = self.client.post(
                    "/turns",
                    json={
                        "content": "hello",
                        "agent_id": "crxzipple",
                    },
                )
                self.assertEqual(turn_response.status_code, 202)
                payload = turn_response.json()
                session_key = payload["run"]["session_key"]

                processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                    worker_id="http-conversations-worker",
                )
                self.assertIsNotNone(processed)

                list_response = self.client.get("/conversations")
                self.assertEqual(list_response.status_code, 200)
                list_payload = list_response.json()
                self.assertEqual(len(list_payload), 1)
                self.assertEqual(list_payload[0]["session_key"], "agent:crxzipple:main")
                self.assertEqual(list_payload[0]["title"], "hello")
                self.assertEqual(list_payload[0]["latest_run_status"], "completed")
                self.assertEqual(list_payload[0]["last_message_preview"], "hello from sample llm")

                get_response = self.client.get(f"/conversations/{session_key}")
                self.assertEqual(get_response.status_code, 200)
                get_payload = get_response.json()
                self.assertEqual(get_payload["session_key"], session_key)
                self.assertEqual(get_payload["title"], "hello")
                self.assertEqual(get_payload["latest_run_status"], "completed")
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_conversations_use_stable_title_instead_of_latest_message_preview(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
            os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
            server.start()

            try:
                llm_response = self.client.post(
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
                self.assertEqual(llm_response.status_code, 201)

                agent_response = self.client.post(
                    "/agents",
                    json={
                        "id": "crxzipple",
                        "name": "crxzipple",
                        "llm_routing_policy": {"default_llm_id": "local-chat"},
                        "instruction_policy": {"system_prompt": "Be helpful."},
                    },
                )
                self.assertEqual(agent_response.status_code, 201)

                for prompt in (
                    "hello",
                    "plan a long weekend in Beijing with museums and food",
                    "去北京呢",
                ):
                    turn_response = self.client.post(
                        "/turns",
                        json={
                            "content": prompt,
                            "agent_id": "crxzipple",
                        },
                    )
                    self.assertEqual(turn_response.status_code, 202)
                    processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                        worker_id="http-conversation-title-worker",
                    )
                    self.assertIsNotNone(processed)

                list_response = self.client.get("/conversations")
                self.assertEqual(list_response.status_code, 200)
                list_payload = list_response.json()
                self.assertEqual(len(list_payload), 1)
                self.assertEqual(
                    list_payload[0]["title"],
                    "plan a long weekend in Beijing with museums and food",
                )
                self.assertEqual(list_payload[0]["last_message_preview"], "hello from sample llm")
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_conversation_preview_strips_markdown_formatting(self) -> None:
            adapter = _SequentialTextAdapter(
                "# Heading\n\nUse **bold** and `code` with [link](https://example.com).\n\n- [x] done\n- [ ] todo\n\n$$x^2$$ and \\(a+b\\)\n\n---",
            )
            self.client.app.state.container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )

            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "local-chat",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
                },
            )
            self.assertEqual(llm_response.status_code, 201)
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "crxzipple",
                    "name": "crxzipple",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "hello",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)

            processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-preview-worker",
            )
            self.assertIsNotNone(processed)

            list_response = self.client.get("/conversations")
            self.assertEqual(list_response.status_code, 200)
            list_payload = list_response.json()
            self.assertEqual(
                list_payload[0]["last_message_preview"],
                "Heading Use bold and code with link. done todo x^2 and a+b",
            )

    def test_conversation_preview_strips_markdown_headings_without_spaces(self) -> None:
            adapter = _SequentialTextAdapter(
                "###标题\n\n* 列表一\n* 列表二\n\n**重点**\n\n#一级\n##二级",
            )
            self.client.app.state.container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )

            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "local-chat",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
                },
            )
            self.assertEqual(llm_response.status_code, 201)
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "crxzipple",
                    "name": "crxzipple",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "hello",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)

            processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-preview-worker",
            )
            self.assertIsNotNone(processed)

            list_response = self.client.get("/conversations")
            self.assertEqual(list_response.status_code, 200)
            list_payload = list_response.json()
            self.assertEqual(
                list_payload[0]["last_message_preview"],
                "标题 列表一 列表二 重点 一级 二级",
            )

    def test_conversation_preview_strips_inline_markdown_markers(self) -> None:
            preview = _normalize_preview_text(
                "可以，给你安排一个**“拍夕阳 + 吃晚饭”**的轻松版行程。 "
                "## 推荐路线：滇池看夕阳 + 附近吃晚饭 "
                "### 16:30-17:30 出发 - 先去 **海埂大坝 / 滇池海埂公园** "
                "- 先走一圈找机位，边走边拍 "
                "### 19:40-20:30 吃晚饭 "
                "1. **适合两个人约会版** 2. **适合一个人散步拍照版**",
            )

            self.assertEqual(
                preview,
                "可以，给你安排一个“拍夕阳 + 吃晚饭”的轻松版行程。 推荐路线：滇池看夕阳 + "
                "附近吃晚饭 16:30-17:30 出发 先去 海埂大坝 / 滇池海埂公园 先走一圈找机位，边走边拍 "
                "19:40-20:30 吃晚饭 适合两个人约会版 适合一个人散步拍照版",
            )


if __name__ == "__main__":
    unittest.main()
