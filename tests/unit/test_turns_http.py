from __future__ import annotations

import asyncio
from crxzipple.modules.context_workspace.application import CONTEXT_TREE_SCHEMA_VERSION
from crxzipple.modules.llm.domain import LlmApiFamily, LlmProviderKind
from crxzipple.modules.orchestration.domain import OrchestrationRunStatus
from crxzipple.modules.session.application import (
    EnsureSessionInput,
    ListSessionItemsInput,
)
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunStatus

from tests.unit.http_test_support import *


class TurnsHttpTestCase(HttpModuleTestCase):
    def _process_turn_ingress(self, run_id: str) -> OrchestrationRun | None:
            return self.client.app.state.container.require(AppKey.ORCHESTRATION_SUBMISSION_SERVICE).process_run_request(
                run_id=run_id,
                worker_id="http-test-scheduler",
            )

    def _process_turn_execution(self) -> OrchestrationRun | None:
            return process_next_orchestration_assignment(self.client.app.state.container, worker_id="http-test-worker")

    def test_turns_endpoint_repairs_web_mojibake_for_east_asian_text(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sample-compat-token"
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
                        "credential_binding_id": "openai-api-key",
                    },
                )
                self.assertEqual(llm_response.status_code, 201)

                with tempfile.TemporaryDirectory() as tempdir:
                    workspace = Path(tempdir)
                    agent_response = self.client.post(
                        "/agents",
                        json={
                            "id": "crxzipple",
                            "name": "crxzipple",
                            "llm_routing_policy": {"default_llm_id": "local-chat"},
                            "instruction_policy": {"system_prompt": "Be helpful."},
                            "runtime_preferences": {"workspace": str(workspace)},
                        },
                    )
                    self.assertEqual(agent_response.status_code, 201)

                    expected = (
                        "你现在可以使用 mobile 工具控制这台已连接的 Android 手机。"
                        "先创建会话并抓取 snapshot。"
                    )
                    garbled = expected.encode("utf-8").decode("latin1")

                    turn_response = self.client.post(
                        "/turns",
                        json={
                            "content": {
                                "blocks": [
                                    {"type": "text", "text": garbled},
                                ],
                            },
                            "agent_id": "crxzipple",
                            "source": "web",
                        },
                    )

                    self.assertEqual(turn_response.status_code, 202)
                    payload = turn_response.json()
                    self.assertEqual(
                        payload["run"]["inbound_instruction"]["content"]["blocks"][0]["text"],
                        expected,
                    )

                    run_id = payload["run"]["id"]
                    scheduled = self._process_turn_ingress(run_id)
                    self.assertIsNotNone(scheduled)
                    processed = self._process_turn_execution()
                    self.assertIsNotNone(processed)

                    get_response = self.client.get(f"/turns/{run_id}")
                    self.assertEqual(get_response.status_code, 200)
                    self.assertEqual(
                        get_response.json()["run"]["inbound_instruction"]["content"]["blocks"][0]["text"],
                        expected,
                    )

                    session_key = get_response.json()["run"]["session_key"]
                    history = self.client.app.state.container.require(AppKey.SESSION_SERVICE).list_items(
                        ListSessionItemsInput(
                            session_key=session_key,
                        ),
                    )
                    self.assertEqual(
                        history[0].content_payload["blocks"][0]["text"],
                        expected,
                    )
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_token
                server.close()

    def test_turns_endpoint_submits_async_turn_without_exposing_orchestration(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sample-compat-token"
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
                        "credential_binding_id": "openai-api-key",
                    },
                )
                self.assertEqual(llm_response.status_code, 201)

                with tempfile.TemporaryDirectory() as tempdir:
                    workspace = Path(tempdir)
                    (workspace / "AGENTS.md").write_text(
                        "# AGENTS.md\n\nUse the local project context.\n",
                        encoding="utf-8",
                    )
                    agent_response = self.client.post(
                        "/agents",
                        json={
                            "id": "crxzipple",
                            "name": "crxzipple",
                            "llm_routing_policy": {"default_llm_id": "local-chat"},
                            "instruction_policy": {"system_prompt": "Be helpful."},
                            "runtime_preferences": {"workspace": str(workspace)},
                        },
                    )
                    self.assertEqual(agent_response.status_code, 201)

                    turn_response = self.client.post(
                        "/turns",
                        json={
                            "content": "hello",
                            "agent_id": "crxzipple",
                            "new_session": True,
                            "metadata": {
                                "runtime_task_policy": {
                                    "runtime_request_bootstrap": {
                                        "default_tool_schema_group_refs": [
                                            {
                                                "source_id": "bundled.local_package.browser",
                                                "group_key": "observation",
                                            },
                                        ],
                                    },
                                },
                            },
                        },
                    )

                    self.assertEqual(turn_response.status_code, 202)
                    payload = turn_response.json()
                    self.assertIsNone(payload["output_text"])
                    self.assertEqual(payload["run"]["status"], "accepted")
                    self.assertEqual(payload["run"]["stage"], "accepted")
                    self.assertEqual(payload["run"]["current_step"], 0)
                    accepted_session_key = payload["run"]["session_key"]
                    self.assertIsInstance(accepted_session_key, str)
                    self.assertTrue(
                        accepted_session_key.startswith(
                            "agent:crxzipple:conversation:",
                        ),
                    )
                    self.assertIsNone(payload["run"]["active_session_id"])

                    scheduled = self._process_turn_ingress(payload["run"]["id"])
                    self.assertIsNotNone(scheduled)
                    assert scheduled is not None
                    self.assertEqual(
                        scheduled.metadata["runtime_request_flow_hint"][
                            "default_tool_schema_group_refs"
                        ],
                        [
                            {
                                "source_id": "bundled.local_package.browser",
                                "group_key": "observation",
                            },
                        ],
                    )
                    self.assertEqual(
                        scheduled.metadata["runtime_request_flow_hint"][
                            "default_tool_schema_source"
                        ],
                        "runtime_request_bootstrap_policy",
                    )
                    processed = self._process_turn_execution()
                    self.assertIsNotNone(processed)

                    get_response = self.client.get(f"/turns/{payload['run']['id']}")
                    self.assertEqual(get_response.status_code, 200)
                    get_payload = get_response.json()
                    self.assertEqual(get_payload["run"]["id"], payload["run"]["id"])
                    self.assertEqual(get_payload["run"]["status"], "completed")
                    self.assertEqual(get_payload["run"]["stage"], "completed")
                    self.assertEqual(get_payload["run"]["current_step"], 1)
                    self.assertEqual(
                        get_payload["run"]["session_key"],
                        accepted_session_key,
                    )
                    self.assertEqual(get_payload["output_text"], "hello from sample llm")
                    self.assertNotIn(
                        "workspace_context_workspace",
                        get_payload["run"]["metadata"],
                    )
                    self.assertNotIn(
                        "workspace_context_files",
                        get_payload["run"]["metadata"],
                    )
                    self.assertEqual(get_payload["run"]["metadata"]["runtime_request_mode"], "session_start")
                    self.assertEqual(
                        get_payload["run"]["metadata"]["runtime_request_report"]["context_budget"]["source"],
                        "fixed",
                    )
                    self.assertEqual(
                        get_payload["run"]["metadata"]["runtime_request_report"]["context_budget"]["max_estimated_tokens"],
                        30000,
                    )
                    self.assertNotIn(
                        "context_blocks",
                        get_payload["run"]["metadata"]["runtime_request_report"],
                    )
                    preview_response = self.client.get(
                        f"/turns/{payload['run']['id']}/llm-request-preview",
                    )
                    self.assertEqual(preview_response.status_code, 200)
                    preview_payload = preview_response.json()
                    self.assertEqual(preview_payload["run_id"], payload["run"]["id"])
                    self.assertEqual(preview_payload["llm_id"], "local-chat")
                    self.assertEqual(preview_payload["mode"], "normal_turn")
                    self.assertIsNotNone(preview_payload["runtime_request_report"])
                    self.assertTrue(
                        str(
                            get_payload["run"]["metadata"][
                                "request_render_snapshot_id"
                            ],
                        ).startswith("ctxsnap_"),
                    )
                    self.assertEqual(
                        preview_payload["request_render_snapshot_id"],
                        get_payload["run"]["metadata"]["request_render_snapshot_id"],
                    )
                    self.assertNotIn("context_snapshot_id", preview_payload)
                    self.assertIsNotNone(preview_payload["request_render_snapshot"])
                    self.assertEqual(
                        preview_payload["request_render_snapshot"]["snapshot_id"],
                        preview_payload["request_render_snapshot_id"],
                    )
                    self.assertEqual(
                        preview_payload["request_render_snapshot_metadata"]["snapshot_kind"],
                        "request_render",
                    )
                    self.assertNotIn("provider_attachments", preview_payload)
                    self.assertEqual(
                        preview_payload["provider_request_options"][
                            "request_metadata"
                        ]["runtime_request_surface"],
                        "interactive",
                    )
                    self.assertNotIn(
                        "context_slice_summary",
                        preview_payload["provider_request_options"][
                            "request_metadata"
                        ],
                    )
                    self.assertNotIn("context_slice_summary", preview_payload)
                    self.assertEqual(
                        preview_payload["request_render_snapshot"]["snapshot_id"],
                        preview_payload["request_render_snapshot_id"],
                    )
                    self.assertNotIn(
                        "raw_tree_body",
                        preview_payload["request_render_snapshot"],
                    )
                    self.assertEqual(
                        preview_payload["tool_surface"]["metadata"][
                            "request_render_snapshot_id"
                        ],
                        preview_payload["request_render_snapshot_id"],
                    )
                    self.assertEqual(
                        preview_payload["tool_surface"]["id"],
                        f"tool_surface:{preview_payload['request_render_snapshot_id']}",
                    )
                    self.assertEqual(
                        preview_payload["provider_request_options"]["response_format"],
                        None,
                    )
                    self.assertEqual(
                        preview_payload["provider_request_options"]["output_schema"],
                        None,
                    )
                    self.assertEqual(
                        preview_payload["provider_request_options"]["overrides"],
                        {},
                    )
                    self.assertEqual(
                        preview_payload["provider_request_options"]["request_metadata"][
                            "request_render_snapshot_id"
                        ],
                        preview_payload["request_render_snapshot_id"],
                    )
                    self.assertEqual(
                        preview_payload["provider_request_options"]["request_metadata"][
                            "tool_surface_id"
                        ],
                        preview_payload["tool_surface"]["id"],
                    )
                    if "mirrored_schema_names" in preview_payload["tool_surface"]:
                        self.assertIsInstance(
                            preview_payload["tool_surface"]["mirrored_schema_names"],
                            list,
                        )
                    self.assertEqual(
                        preview_payload["provider_request_options"]["request_metadata"][
                            "tool_surface_mirrored_schema_count"
                        ],
                        len(
                            preview_payload["tool_surface"].get(
                                "mirrored_schema_names",
                                [],
                            ),
                        ),
                    )
                    self.assertEqual(
                        preview_payload["provider_request_options"]["request_metadata"][
                            "tree_schema_version"
                        ],
                        "request-render-snapshot",
                    )
                    self.assertIn("input_items", preview_payload)
                    self.assertTrue(preview_payload["input_items"])
                    self.assertEqual(
                        preview_payload["input_items"][0]["kind"],
                        "message",
                    )
                    self.assertIn("runtime_context", preview_payload)
                    self.assertEqual(
                        preview_payload["runtime_context"][
                            "request_render_snapshot_id"
                        ],
                        preview_payload["request_render_snapshot_id"],
                    )
                    self.assertTrue(
                        any(
                            item["role"] == "user"
                            and item["content"] == [{"type": "text", "text": "hello"}]
                            for item in preview_payload["messages"]
                        ),
                    )
                    self.assertFalse(
                        any(
                            item["role"] == "assistant"
                            and item["content"] == "hello from sample llm"
                            for item in preview_payload["messages"]
                        ),
                    )
                    self.assertNotIn("workspace_context_files", preview_payload)
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_token
                server.close()

    def test_turns_endpoint_continues_session_by_opaque_session_key(self) -> None:
            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "opaque-session-llm",
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
                    "llm_routing_policy": {"default_llm_id": "opaque-session-llm"},
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)
            session = self.client.app.state.container.require(
                AppKey.SESSION_SERVICE,
            ).ensure_session(
                EnsureSessionInput(
                    key="agent:crxzipple:conversation:server-owned",
                    agent_id="crxzipple",
                ),
            )

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "continue existing",
                    "session_key": session.id,
                },
            )

            self.assertEqual(turn_response.status_code, 202)
            payload = turn_response.json()
            self.assertEqual(payload["run"]["status"], "accepted")
            self.assertEqual(payload["run"]["session_key"], session.id)
            self.assertIsNone(payload["run"]["active_session_id"])

            scheduled = self._process_turn_ingress(payload["run"]["id"])
            self.assertIsNotNone(scheduled)
            assert scheduled is not None
            self.assertEqual(scheduled.session_key, session.id)
            self.assertEqual(scheduled.active_session_id, session.active_session_id)

    def test_turns_endpoint_routes_auto_llm_to_image_model_for_image_input(self) -> None:
            self.client.app.state.container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                _SequentialTextAdapter("vision answer"),
            )

            default_llm_response = self.client.post(
                "/llms",
                json={
                    "id": "text-default",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
                    "credential_binding_id": "openai-api-key",
                },
            )
            self.assertEqual(default_llm_response.status_code, 201)
            image_llm_response = self.client.post(
                "/llms",
                json={
                    "id": "vision-special",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
                    "capabilities": ["vision_input"],
                    "model_family": "vision",
                    "credential_binding_id": "openai-api-key",
                },
            )
            self.assertEqual(image_llm_response.status_code, 201)
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "crxzipple",
                    "name": "crxzipple",
                    "llm_routing_policy": {
                        "default_llm_id": "text-default",
                        "image_llm_id": "vision-special",
                    },
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": {
                        "blocks": [
                            {
                                "type": "image",
                                "data": "aGVsbG8=",
                                "mime_type": "image/png",
                            },
                        ],
                    },
                    "agent_id": "crxzipple",
                    "llm_id": "auto",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            run_id = turn_response.json()["run"]["id"]

            scheduled = self._process_turn_ingress(run_id)
            self.assertIsNotNone(scheduled)
            processed = self._process_turn_execution()
            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.result_payload["llm_id"], "vision-special")

            preview_response = self.client.get(f"/turns/{run_id}/llm-request-preview")
            self.assertEqual(preview_response.status_code, 200)

            get_response = self.client.get(f"/turns/{run_id}")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["output_text"], "vision answer")
            session_key = get_response.json()["run"]["session_key"]
            assert session_key is not None
            session = self.client.app.state.container.require(AppKey.SESSION_SERVICE).get_session(session_key)
            self.assertEqual(session.runtime_binding().agent_id, "crxzipple")

    def test_turn_compaction_endpoint_creates_compaction_run(self) -> None:
            adapter = _SequentialTextAdapter("initial answer", "compacted summary")
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
            run_id = turn_response.json()["run"]["id"]

            scheduled = self._process_turn_ingress(run_id)
            self.assertIsNotNone(scheduled)
            processed = self._process_turn_execution()
            self.assertIsNotNone(processed)

            compact_response = self.client.post(
                f"/turns/{run_id}/compact",
                json={
                    "reason": "manual compaction",
                    "preserve": "open tasks and constraints",
                },
            )
            self.assertEqual(compact_response.status_code, 202)
            compact_payload = compact_response.json()
            self.assertEqual(compact_payload["run"]["status"], "queued")
            self.assertEqual(
                compact_payload["run"]["metadata"]["runtime_request_flow_hint"]["mode"],
                "compaction",
            )
            self.assertEqual(
                compact_payload["run"]["metadata"]["compaction_request"]["basis"],
                "manual",
            )

            compact_run = process_next_orchestration_assignment(self.client.app.state.container, worker_id="http-test-worker")
            self.assertIsNotNone(compact_run)
            assert compact_run is not None
            self.assertEqual(compact_run.metadata["runtime_request_mode"], "compaction")

            conversations_response = self.client.get("/conversations")
            self.assertEqual(conversations_response.status_code, 200)
            conversations_payload = conversations_response.json()
            self.assertEqual(conversations_payload[0]["title"], "hello")
            self.assertEqual(conversations_payload[0]["latest_run_id"], compact_run.id)
            self.assertEqual(conversations_payload[0]["latest_run_status"], "completed")
            self.assertEqual(conversations_payload[0]["display_run_id"], run_id)
            self.assertEqual(conversations_payload[0]["display_run_status"], "completed")
            self.assertEqual(conversations_payload[0]["last_message_preview"], "initial answer")

            live_history_response = self.client.get(
                f"/conversations/{compact_payload['run']['session_key']}/messages",
            )
            self.assertEqual(live_history_response.status_code, 200)
            live_history_payload = live_history_response.json()
            self.assertTrue(
                all(item["lifecycle_state"] != "archived" for item in live_history_payload),
            )

            full_history_response = self.client.get(
                f"/conversations/{compact_payload['run']['session_key']}/messages?include_archived=true",
            )
            self.assertEqual(full_history_response.status_code, 200)
            full_history_payload = full_history_response.json()
            self.assertGreater(len(full_history_payload), len(live_history_payload))
            self.assertTrue(
                any(
                    item["lifecycle_state"] == "archived"
                    for item in full_history_payload
                ),
            )

            session_key = str(compact_run.metadata["session_key"])
            session_items = self.client.app.state.container.require(AppKey.SESSION_SERVICE).list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                ),
            )
            archived_items = [
                item
                for item in session_items
                if item.metadata.get("archived_by_compaction_run_id")
            ]
            self.assertGreaterEqual(len(archived_items), 2)

    def test_turn_heartbeat_endpoint_creates_heartbeat_run(self) -> None:
            adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
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
            run_id = turn_response.json()["run"]["id"]

            scheduled = self._process_turn_ingress(run_id)
            self.assertIsNotNone(scheduled)
            processed = self._process_turn_execution()
            self.assertIsNotNone(processed)

            heartbeat_response = self.client.post(
                f"/turns/{run_id}/heartbeat",
                json={
                    "reason": "scheduled_check",
                },
            )
            self.assertEqual(heartbeat_response.status_code, 202)
            heartbeat_payload = heartbeat_response.json()
            self.assertEqual(heartbeat_payload["run"]["status"], "queued")
            self.assertEqual(
                heartbeat_payload["run"]["metadata"]["runtime_request_flow_hint"]["mode"],
                "heartbeat",
            )
            self.assertEqual(
                heartbeat_payload["run"]["metadata"]["heartbeat_request"]["basis"],
                "manual",
            )

            heartbeat_run = process_next_orchestration_assignment(self.client.app.state.container, worker_id="http-test-worker")
            self.assertIsNotNone(heartbeat_run)
            assert heartbeat_run is not None
            self.assertEqual(heartbeat_run.metadata["runtime_request_mode"], "heartbeat")

    def test_turn_memory_flush_endpoint_creates_memory_flush_run(self) -> None:
            adapter = _SequentialResultAdapter(
                "initial answer",
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-memory-write-http-1",
                            name="memory_write_daily",
                            arguments={
                                "content": (
                                    "# Durable Memory\n\n"
                                    "Keep effect approvals as the default path for risky actions."
                                ),
                            },
                        ),
                    ),
                ),
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
            with tempfile.TemporaryDirectory() as tempdir:
                workspace = Path(tempdir)
                agent_response = self.client.post(
                    "/agents",
                    json={
                        "id": "crxzipple",
                        "name": "crxzipple",
                        "llm_routing_policy": {"default_llm_id": "local-chat"},
                        "instruction_policy": {"system_prompt": "Be helpful."},
                        "runtime_preferences": {"workspace": str(workspace)},
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
                run_id = turn_response.json()["run"]["id"]

                scheduled = self._process_turn_ingress(run_id)
                self.assertIsNotNone(scheduled)
                processed = self._process_turn_execution()
                self.assertIsNotNone(processed)

                flush_response = self.client.post(
                    f"/turns/{run_id}/memory-flush",
                    json={
                        "reason": "manual memory flush",
                    },
                )
                self.assertEqual(flush_response.status_code, 202)
                flush_payload = flush_response.json()
                self.assertEqual(flush_payload["run"]["status"], "queued")
                self.assertEqual(
                    flush_payload["run"]["metadata"]["runtime_request_flow_hint"]["mode"],
                    "memory_flush",
                )
                self.assertEqual(
                    flush_payload["run"]["metadata"]["memory_flush_request"]["basis"],
                    "manual",
                )

                flush_run = process_next_orchestration_assignment(self.client.app.state.container, worker_id="http-test-worker")
                self.assertIsNotNone(flush_run)
                assert flush_run is not None
                self.assertEqual(flush_run.metadata["runtime_request_mode"], "memory_flush")
                self.assertNotIn("memory_flush_result", flush_run.metadata)
                self.assertEqual(
                    len(
                        execution_tool_run_ids_for_run(
                            self.client.app.state.container,
                            flush_run.id,
                        ),
                    ),
                    1,
                )
                entries = self.client.get(
                    "/memory/search",
                    params={"agent_id": "crxzipple", "query": "risky actions"},
                )
                self.assertEqual(entries.status_code, 200)
                search_hits = entries.json()
                self.assertTrue(
                    any(
                        "risky actions" in hit["snippet"]
                        for hit in search_hits
                    ),
                )

    def test_turn_approval_endpoint_resumes_waiting_run(self) -> None:
            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "local-capability",
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
                    "id": "writer",
                    "name": "Writer",
                    "llm_routing_policy": {"default_llm_id": "local-capability"},
                    "instruction_policy": {"system_prompt": "Use tools when needed."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)
            tool = seed_catalog_tool(
                self.client.app.state.container,
                tool_id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                required_effect_ids=("local_tool_access",),
                runtime_key="echo",
            )

            async def echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"echo": arguments.get("message")},
                )

            self.client.app.state.container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, echo)
            self.client.app.state.container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                _FakeEffectApprovalAdapter(),
            )

            created = self.client.post(
                "/turns",
                json={"content": "please continue", "agent_id": "writer"},
            )
            self.assertEqual(created.status_code, 202)
            run_id = created.json()["run"]["id"]

            scheduled = self._process_turn_ingress(run_id)
            self.assertIsNotNone(scheduled)
            waiting = self._process_turn_execution()
            self.assertIsNotNone(waiting)
            assert waiting is not None
            self.assertEqual(waiting.stage.value, "waiting_for_confirmation")

            pending_request = waiting.pending_approval_request()
            assert pending_request is not None
            request_id = pending_request.request_id

            approval_response = self.client.post(
                f"/turns/{run_id}/approvals/{request_id}",
                json={"decision": "allow_once"},
            )
            self.assertEqual(approval_response.status_code, 202)
            self.assertEqual(approval_response.json()["run"]["status"], "completed")

    def test_turn_cancel_endpoint_cancels_submitted_turn(self) -> None:
            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "local-chat",
                    "provider": "openai_compatible",
                    "api_family": "openai_chat_compatible",
                    "model_name": "llama3.2",
                    "base_url": "http://example.invalid/v1",
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
                    "content": "cancel me",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            turn_id = turn_response.json()["run"]["id"]

            long_reason = "user_cancelled_" + ("because_validation_reason_is_long_" * 4)
            expected_waiting_reason = f"{long_reason[:97]}..."
            cancel_response = self.client.post(
                f"/turns/{turn_id}/cancel",
                json={"reason": long_reason},
            )
            self.assertEqual(cancel_response.status_code, 200)
            cancel_payload = cancel_response.json()
            self.assertEqual(cancel_payload["run"]["status"], "cancelled")
            self.assertEqual(cancel_payload["run"]["stage"], "cancelled")
            self.assertEqual(
                cancel_payload["run"]["waiting_reason"],
                expected_waiting_reason,
            )
            self.assertEqual(
                cancel_payload["run"]["metadata"]["cancellation_reason"],
                long_reason,
            )

            get_response = self.client.get(f"/turns/{turn_id}")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["run"]["status"], "cancelled")

    def test_turn_cancel_endpoint_cascades_to_spawned_child_runs_after_parent_completed(self) -> None:
            container = self.client.app.state.container
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                _SequentialTextAdapter("parent complete"),
            )

            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "session-stop-llm",
                    "provider": LlmProviderKind.OPENAI.value,
                    "api_family": LlmApiFamily.OPENAI_RESPONSES.value,
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
                    "llm_routing_policy": {"default_llm_id": "session-stop-llm"},
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "parent request",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            turn_id = turn_response.json()["run"]["id"]

            scheduled = self._process_turn_ingress(turn_id)
            self.assertIsNotNone(scheduled)
            processed = self._process_turn_execution()
            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)

            session_key = processed.session_key
            self.assertIsNotNone(session_key)
            assert session_key is not None

            spawn_tool_run = asyncio.run(
                container.require(AppKey.TOOL_SERVICE).execute(
                    ExecuteToolInput(
                        tool_id="sessions_spawn",
                        arguments={"text": "background child work"},
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": session_key,
                                "agent_id": "crxzipple",
                                "run_id": turn_id,
                            },
                        ),
                    ),
                ),
            )
            self.assertEqual(spawn_tool_run.status, ToolRunStatus.SUCCEEDED)
            child_run_id = spawn_tool_run.result.metadata["run_id"]

            cancel_response = self.client.post(
                f"/turns/{turn_id}/cancel",
                json={"reason": "user_stopped_requester"},
            )
            self.assertEqual(cancel_response.status_code, 200)
            cancel_payload = cancel_response.json()
            self.assertEqual(cancel_payload["run"]["status"], "completed")
            self.assertEqual(
                cancel_payload["run"]["metadata"]["cancel_cascade"]["cancelled_run_count"],
                1,
            )
            self.assertEqual(
                cancel_payload["run"]["metadata"]["cancel_cascade"]["session_keys"],
                [session_key, spawn_tool_run.result.metadata["child_session_key"]],
            )

            child_run = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(child_run_id)
            self.assertEqual(child_run.status, OrchestrationRunStatus.CANCELLED)

if __name__ == "__main__":
    unittest.main()
