from __future__ import annotations

from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput,
    EnqueueOrchestrationRunInput,
    PrepareSessionRunInput,
)
from crxzipple.modules.orchestration.domain import InboundInstruction
from crxzipple.modules.session.domain import SessionRouteContext
from tests.unit.http_test_support import *


class ConversationsHttpTestCase(HttpModuleTestCase):
    def _register_local_chat(self, *responses: str) -> _SequentialTextAdapter:
        adapter = _SequentialTextAdapter(
            *(responses or ("hello from sample llm",)),
        )
        self.client.app.state.container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
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
                "credential_binding_id": "openai-api-key",
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
        return adapter

    def _process_turn(self, run_id: str, *, worker_id: str) -> OrchestrationRun | None:
        _ = self.client.app.state.container.require(
            AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE,
        ).process_run_request(
            run_id=run_id,
            worker_id=f"{worker_id}-scheduler",
        )
        return process_next_orchestration_assignment(self.client.app.state.container, worker_id=worker_id)

    def test_conversations_use_origin_source_label_for_subagent_sessions(self) -> None:
        run = self.client.app.state.container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
            AcceptOrchestrationRunInput(
                run_id="run-subagent-thread",
                inbound_instruction=InboundInstruction(
                    source="sessions_spawn",
                    content="inspect this in a child session",
                ),
            ),
        )
        self.client.app.state.container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    main_key="subagent:child-1",
                    label="subagent",
                    surface="session_tool",
                ),
            ),
        )
        self.client.app.state.container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        processed = process_next_orchestration_assignment(self.client.app.state.container, worker_id="subagent-conversation-worker")
        self.assertIsNotNone(processed)
        session = self.client.app.state.container.require(AppKey.SESSION_SERVICE).get_session(
            "agent:assistant:subagent:child-1",
        )

        list_response = self.client.get("/conversations")
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        self.assertEqual(len(list_payload), 1)
        self.assertEqual(list_payload[0]["session_key"], session.id)
        self.assertEqual(list_payload[0]["source_label"], "Subagent")
        self.assertIsNone(list_payload[0]["channel"])

        get_response = self.client.get(f"/conversations/{session.id}")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["source_label"], "Subagent")

    def test_conversation_messages_endpoint_reads_history_by_session_key(self) -> None:
        self._register_local_chat("hello from sample llm")

        turn_response = self.client.post(
            "/turns",
            json={
                "content": "hello",
                "agent_id": "crxzipple",
            },
        )
        self.assertEqual(turn_response.status_code, 202)
        payload = turn_response.json()

        processed = self._process_turn(
            payload["run"]["id"],
            worker_id="http-history-worker",
        )
        self.assertIsNotNone(processed)
        session_key = self.client.app.state.container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(
            payload["run"]["id"],
        ).session_key
        self.assertIsNotNone(session_key)

        history_response = self.client.get(f"/conversations/{session_key}/messages")
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual([item["role"] for item in history_payload], ["user", "assistant"])
        self.assertEqual(
            [item["kind"] for item in history_payload],
            ["user_message", "assistant_message"],
        )
        self.assertEqual(
            [item["source_module"] for item in history_payload],
            ["orchestration", "llm"],
        )
        self.assertEqual(history_payload[0]["lifecycle_state"], "active")
        self.assertEqual(history_payload[1]["lifecycle_state"], "active")
        self.assertNotIn("content", history_payload[0])
        self.assertTrue(history_payload[0]["created_at"].endswith("+00:00"))
        self.assertTrue(history_payload[1]["created_at"].endswith("+00:00"))
        self.assertEqual(
            history_payload[0]["content_payload"],
            {"blocks": [{"type": "text", "text": "hello"}]},
        )
        self.assertNotIn("content", history_payload[1])
        self.assertEqual(
            history_payload[1]["content_payload"]["text"],
            "hello from sample llm",
        )

    def test_conversations_endpoints_list_and_get_summaries(self) -> None:
            self._register_local_chat("hello from sample llm")

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "hello",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            payload = turn_response.json()

            processed = self._process_turn(
                payload["run"]["id"],
                worker_id="http-conversations-worker",
            )
            self.assertIsNotNone(processed)
            session_key = self.client.app.state.container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(
                payload["run"]["id"],
            ).session_key
            self.assertIsNotNone(session_key)

            list_response = self.client.get("/conversations")
            self.assertEqual(list_response.status_code, 200)
            list_payload = list_response.json()
            self.assertEqual(len(list_payload), 1)
            self.assertEqual(list_payload[0]["session_key"], "agent:crxzipple:main")
            self.assertEqual(list_payload[0]["title"], "hello")
            self.assertEqual(list_payload[0]["latest_run_status"], "completed")
            self.assertEqual(list_payload[0]["last_message_preview"], "hello from sample llm")
            self.assertTrue(list_payload[0]["created_at"].endswith("+00:00"))
            self.assertTrue(list_payload[0]["updated_at"].endswith("+00:00"))

            get_response = self.client.get(f"/conversations/{session_key}")
            self.assertEqual(get_response.status_code, 200)
            get_payload = get_response.json()
            self.assertEqual(get_payload["session_key"], session_key)
            self.assertEqual(get_payload["title"], "hello")
            self.assertEqual(get_payload["latest_run_status"], "completed")
            self.assertTrue(get_payload["created_at"].endswith("+00:00"))
            self.assertTrue(get_payload["updated_at"].endswith("+00:00"))

    def test_conversation_messages_endpoint_supports_after_sequence_no(self) -> None:
        self._register_local_chat("hello from sample llm")

        turn_response = self.client.post(
            "/turns",
            json={
                "content": "hello",
                "agent_id": "crxzipple",
            },
        )
        self.assertEqual(turn_response.status_code, 202)
        payload = turn_response.json()

        processed = self._process_turn(
            payload["run"]["id"],
            worker_id="http-history-after-sequence-worker",
        )
        self.assertIsNotNone(processed)
        session_key = self.client.app.state.container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(
            payload["run"]["id"],
        ).session_key
        self.assertIsNotNone(session_key)

        history_response = self.client.get(
            f"/conversations/{session_key}/messages?after_sequence_no=1",
        )
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["role"], "assistant")
        self.assertEqual(history_payload[0]["kind"], "assistant_message")
        self.assertEqual(history_payload[0]["sequence_no"], 2)

    def test_conversation_messages_endpoint_supports_before_sequence_no(self) -> None:
        self._register_local_chat("hello from sample llm", "hello from sample llm")

        for prompt in ("hello", "tell me more"):
            turn_response = self.client.post(
                "/turns",
                json={
                    "content": prompt,
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            processed = self._process_turn(
                turn_response.json()["run"]["id"],
                worker_id="http-history-before-sequence-worker",
            )
            self.assertIsNotNone(processed)
            session_key = self.client.app.state.container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(
                turn_response.json()["run"]["id"],
            ).session_key
            self.assertIsNotNone(session_key)

        history_response = self.client.get(
            f"/conversations/{session_key}/messages?before_sequence_no=3",
        )
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual([item["sequence_no"] for item in history_payload], [1, 2])
        self.assertEqual([item["role"] for item in history_payload], ["user", "assistant"])
        self.assertEqual(
            [item["kind"] for item in history_payload],
            ["user_message", "assistant_message"],
        )

    def test_conversation_runs_endpoint_lists_session_turns(self) -> None:
        self._register_local_chat("hello from sample llm", "hello from sample llm")

        run_ids: list[str] = []
        session_key: str | None = None
        for prompt in ("hello", "tell me more"):
            turn_response = self.client.post(
                "/turns",
                json={
                    "content": prompt,
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            run_id = turn_response.json()["run"]["id"]
            run_ids.append(run_id)
            processed = self._process_turn(
                run_id,
                worker_id="http-conversation-runs-worker",
            )
            self.assertIsNotNone(processed)
            session_key = self.client.app.state.container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(
                run_id,
            ).session_key
            self.assertIsNotNone(session_key)

        runs_response = self.client.get(f"/conversations/{session_key}/runs")
        self.assertEqual(runs_response.status_code, 200)
        runs_payload = runs_response.json()
        self.assertEqual([item["id"] for item in runs_payload], list(reversed(run_ids)))
        self.assertTrue(runs_payload[0]["created_at"].endswith("+00:00"))
        self.assertEqual(runs_payload[0]["session_key"], session_key)

    def test_conversations_use_stable_title_instead_of_latest_message_preview(self) -> None:
            self._register_local_chat(
                "hello from sample llm",
                "hello from sample llm",
                "hello from sample llm",
            )

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
                processed = self._process_turn(
                    turn_response.json()["run"]["id"],
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

    def test_conversation_preview_strips_markdown_formatting(self) -> None:
            adapter = _SequentialTextAdapter(
                "# Heading\n\nUse **bold** and `code` with [link](https://example.com).\n\n- [x] done\n- [ ] todo\n\n$$x^2$$ and \\(a+b\\)\n\n---",
            )
            self.client.app.state.container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
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
                    "credential_binding_id": "openai-api-key",
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

            processed = self._process_turn(
                turn_response.json()["run"]["id"],
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
            self.client.app.state.container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
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
                    "credential_binding_id": "openai-api-key",
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

            processed = self._process_turn(
                turn_response.json()["run"]["id"],
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
