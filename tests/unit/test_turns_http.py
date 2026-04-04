from __future__ import annotations

from crxzipple.modules.tool.domain import ToolRunResult

from tests.unit.http_test_support import *


class TurnsHttpTestCase(HttpModuleTestCase):
    def test_turns_endpoint_submits_async_turn_without_exposing_orchestration(self) -> None:
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
                        },
                    )

                    self.assertEqual(turn_response.status_code, 202)
                    payload = turn_response.json()
                    self.assertIsNone(payload["output_text"])
                    self.assertEqual(payload["run"]["status"], "queued")
                    self.assertEqual(payload["run"]["stage"], "queued")
                    self.assertEqual(payload["run"]["current_step"], 0)

                    processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                        worker_id="http-test-worker",
                    )
                    self.assertIsNotNone(processed)

                    get_response = self.client.get(f"/turns/{payload['run']['id']}")
                    self.assertEqual(get_response.status_code, 200)
                    get_payload = get_response.json()
                    self.assertEqual(get_payload["run"]["id"], payload["run"]["id"])
                    self.assertEqual(get_payload["run"]["status"], "completed")
                    self.assertEqual(get_payload["run"]["stage"], "completed")
                    self.assertEqual(get_payload["run"]["current_step"], 1)
                    self.assertEqual(get_payload["output_text"], "hello from sample llm")
                    self.assertEqual(
                        get_payload["run"]["metadata"]["workspace_context_workspace"],
                        str(workspace),
                    )
                    workspace_context_files = get_payload["run"]["metadata"]["workspace_context_files"]
                    self.assertIn(
                        {"path": "AGENTS.md", "chars": len("# AGENTS.md\n\nUse the local project context.")},
                        workspace_context_files,
                    )
                    self.assertEqual(get_payload["run"]["metadata"]["prompt_mode"], "session_start")
                    self.assertEqual(
                        get_payload["run"]["metadata"]["prompt_report"]["system_budget"]["source"],
                        "fixed",
                    )
                    self.assertEqual(
                        get_payload["run"]["metadata"]["prompt_report"]["system_budget"]["max_estimated_tokens"],
                        30000,
                    )
                    self.assertEqual(
                        [block["kind"] for block in get_payload["run"]["metadata"]["prompt_report"]["system_blocks"]],
                        [
                            "agent_instruction",
                            "runtime_context",
                            "flow_prompt",
                            "project_context",
                            "skills_catalog",
                        ],
                    )
                    preview_response = self.client.get(
                        f"/turns/{payload['run']['id']}/prompt-preview",
                    )
                    self.assertEqual(preview_response.status_code, 200)
                    preview_payload = preview_response.json()
                    self.assertEqual(preview_payload["run_id"], payload["run"]["id"])
                    self.assertEqual(preview_payload["llm_id"], "local-chat")
                    self.assertEqual(preview_payload["mode"], "normal_turn")
                    self.assertIsNotNone(preview_payload["prompt_report"])
                    self.assertTrue(
                        any(
                            item["role"] == "user"
                            and item["content"] == [{"type": "text", "text": "hello"}]
                            for item in preview_payload["messages"]
                        ),
                    )
                    self.assertIn(
                        {"path": "AGENTS.md", "chars": len("# AGENTS.md\n\nUse the local project context.")},
                        preview_payload["workspace_context_files"],
                    )
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_turns_endpoint_routes_auto_llm_to_image_model_for_image_input(self) -> None:
            self.client.app.state.container.llm_adapter_registry.register(
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

            processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-test-worker",
            )
            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.result_payload["llm_id"], "vision-special")

            preview_response = self.client.get(f"/turns/{run_id}/prompt-preview")
            self.assertEqual(preview_response.status_code, 200)

            get_response = self.client.get(f"/turns/{run_id}")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["output_text"], "vision answer")
            session_key = get_response.json()["run"]["session_key"]
            assert session_key is not None
            session = self.client.app.state.container.session_service.get_session(session_key)
            self.assertEqual(session.runtime_binding().agent_id, "crxzipple")

    def test_turn_compaction_endpoint_creates_compaction_run(self) -> None:
            adapter = _SequentialTextAdapter("initial answer", "compacted summary")
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
            run_id = turn_response.json()["run"]["id"]

            processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-test-worker",
            )
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
                compact_payload["run"]["metadata"]["prompt_flow_hint"]["mode"],
                "compaction",
            )
            self.assertEqual(
                compact_payload["run"]["metadata"]["compaction_request"]["basis"],
                "manual",
            )

            compact_run = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-test-worker",
            )
            self.assertIsNotNone(compact_run)
            assert compact_run is not None
            self.assertEqual(compact_run.metadata["prompt_mode"], "compaction")

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
                all(item["visibility"] != "archived" for item in live_history_payload),
            )

            full_history_response = self.client.get(
                f"/conversations/{compact_payload['run']['session_key']}/messages?include_archived=true",
            )
            self.assertEqual(full_history_response.status_code, 200)
            full_history_payload = full_history_response.json()
            self.assertGreater(len(full_history_payload), len(live_history_payload))
            self.assertTrue(
                any(item["visibility"] == "archived" for item in full_history_payload),
            )

            session_key = str(compact_run.metadata["session_key"])
            session_messages = self.client.app.state.container.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    active_session_only=True,
                ),
            )
            archived_messages = [
                message for message in session_messages if message.visibility.value == "archived"
            ]
            self.assertGreaterEqual(len(archived_messages), 2)

    def test_turn_heartbeat_endpoint_creates_heartbeat_run(self) -> None:
            adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
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
            run_id = turn_response.json()["run"]["id"]

            processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-test-worker",
            )
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
                heartbeat_payload["run"]["metadata"]["prompt_flow_hint"]["mode"],
                "heartbeat",
            )
            self.assertEqual(
                heartbeat_payload["run"]["metadata"]["heartbeat_request"]["basis"],
                "manual",
            )

            heartbeat_run = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-test-worker",
            )
            self.assertIsNotNone(heartbeat_run)
            assert heartbeat_run is not None
            self.assertEqual(heartbeat_run.metadata["prompt_mode"], "heartbeat")

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

                processed = self.client.app.state.container.orchestration_service.process_next_queued_run(
                    worker_id="http-test-worker",
                )
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
                    flush_payload["run"]["metadata"]["prompt_flow_hint"]["mode"],
                    "memory_flush",
                )
                self.assertEqual(
                    flush_payload["run"]["metadata"]["memory_flush_request"]["basis"],
                    "manual",
                )

                flush_run = self.client.app.state.container.orchestration_service.process_next_queued_run(
                    worker_id="http-test-worker",
                )
                self.assertIsNotNone(flush_run)
                assert flush_run is not None
                self.assertEqual(flush_run.metadata["prompt_mode"], "memory_flush")
                self.assertNotIn("memory_flush_result", flush_run.metadata)
                self.assertEqual(
                    len(flush_run.result_payload.get("inline_tool_run_ids", [])),
                    1,
                )
                entries = self.client.get(
                    "/memory/search",
                    params={"agent_id": "crxzipple", "query": "risky actions"},
                )
                self.assertEqual(entries.status_code, 200)
                self.assertEqual(len(entries.json()), 1)

    def test_turn_events_emit_approval_request_and_endpoint_resumes_run(self) -> None:
            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "local-capability",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
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
            tool = self.client.app.state.container.tool_service.register(
                RegisterToolInput(
                    id="echo",
                    name="Echo",
                    description="Echoes a message.",
                    supported_modes=(ToolMode.INLINE,),
                    required_effect_ids=("local_tool_access",),
                    runtime_key="echo",
                ),
            )

            async def echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"echo": arguments.get("message")},
                )

            self.client.app.state.container.local_tool_catalog.register(tool, echo)
            self.client.app.state.container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                _FakeEffectApprovalAdapter(),
            )

            created = self.client.post(
                "/turns",
                json={"content": "please continue", "agent_id": "writer"},
            )
            self.assertEqual(created.status_code, 202)
            run_id = created.json()["run"]["id"]

            waiting = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-test-worker",
            )
            self.assertIsNotNone(waiting)
            assert waiting is not None
            self.assertEqual(waiting.stage.value, "waiting_for_confirmation")

            with self.client.stream("GET", f"/turns/{run_id}/events") as response:
                self.assertEqual(response.status_code, 200)
                event_names: list[str] = []
                request_id: str | None = None
                current_event: str | None = None
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                    if decoded.startswith("event: "):
                        current_event = decoded.removeprefix("event: ").strip()
                        event_names.append(current_event)
                        continue
                    if decoded.startswith("data: ") and current_event == "approval_requested":
                        payload = json.loads(decoded.removeprefix("data: "))
                        request_id = payload["request"]["request_id"]
                        break

            self.assertIn("snapshot", event_names)
            self.assertIn("approval_requested", event_names)
            self.assertIsNotNone(request_id)
            assert request_id is not None

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
                    "content": "cancel me",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            turn_id = turn_response.json()["run"]["id"]

            cancel_response = self.client.post(
                f"/turns/{turn_id}/cancel",
                json={"reason": "user_cancelled"},
            )
            self.assertEqual(cancel_response.status_code, 200)
            cancel_payload = cancel_response.json()
            self.assertEqual(cancel_payload["run"]["status"], "cancelled")
            self.assertEqual(cancel_payload["run"]["stage"], "cancelled")
            self.assertEqual(cancel_payload["run"]["waiting_reason"], "user_cancelled")

            get_response = self.client.get(f"/turns/{turn_id}")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["run"]["status"], "cancelled")

    def test_turn_events_endpoint_streams_snapshot_and_completion(self) -> None:
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
                run_id = turn_response.json()["run"]["id"]

                def _process_later() -> None:
                    time.sleep(0.1)
                    self.client.app.state.container.orchestration_service.process_next_queued_run(
                        worker_id="http-sse-worker",
                    )

                worker = threading.Thread(target=_process_later)
                worker.start()
                try:
                    with self.client.stream(
                        "GET",
                        f"/turns/{run_id}/events",
                        params={"poll_interval_seconds": 0.05, "timeout_seconds": 2.0},
                    ) as response:
                        body = response.read().decode("utf-8")
                        content_type = response.headers["content-type"]
                        status_code = response.status_code
                finally:
                    worker.join(timeout=1.0)

                self.assertEqual(status_code, 200)
                self.assertIn("text/event-stream", content_type)
                self.assertIn("event: snapshot", body)
                self.assertIn("event: message_appended", body)
                self.assertIn("event: completed", body)
                self.assertIn("hello from sample llm", body)
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
                else:
                    os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
                server.close()

    def test_turn_events_endpoint_streams_llm_text_delta(self) -> None:
            container = self.client.app.state.container
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_CODEX_RESPONSES,
                _FakeStreamingAdapter(),
            )

            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "streaming-codex",
                    "provider": LlmProviderKind.OPENAI_CODEX.value,
                    "api_family": LlmApiFamily.OPENAI_CODEX_RESPONSES.value,
                    "model_name": "gpt-5-codex",
                },
            )
            self.assertEqual(llm_response.status_code, 201)

            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "crxzipple",
                    "name": "crxzipple",
                    "llm_routing_policy": {"default_llm_id": "streaming-codex"},
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

            def _process_later() -> None:
                time.sleep(0.1)
                container.orchestration_service.process_next_queued_run(
                    worker_id="http-stream-worker",
                )

            worker = threading.Thread(target=_process_later)
            worker.start()
            try:
                with self.client.stream(
                    "GET",
                    f"/turns/{run_id}/events",
                    params={"poll_interval_seconds": 0.05, "timeout_seconds": 2.0},
                ) as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers["content-type"]
                    status_code = response.status_code
            finally:
                worker.join(timeout=1.0)

            self.assertEqual(status_code, 200)
            self.assertIn("text/event-stream", content_type)
            self.assertIn("event: snapshot", body)
            self.assertIn("event: llm_text_delta", body)
            self.assertIn("hello from stream", body)
            self.assertIn("event: completed", body)

    def test_turn_events_endpoint_streams_tool_started_and_completed(self) -> None:
            container = self.client.app.state.container
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                _FakeInlineToolAdapter(),
            )

            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "inline-tool-llm",
                    "provider": LlmProviderKind.OPENAI.value,
                    "api_family": LlmApiFamily.OPENAI_RESPONSES.value,
                    "model_name": "gpt-5.4-mini",
                },
            )
            self.assertEqual(llm_response.status_code, 201)

            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "crxzipple",
                    "name": "crxzipple",
                    "llm_routing_policy": {"default_llm_id": "inline-tool-llm"},
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="echo",
                    name="Echo",
                    description="Echoes a message.",
                    supported_modes=(ToolMode.INLINE,),
                    runtime_key="echo",
                ),
            )

            async def echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"echo": arguments.get("message")},
                )

            container.local_tool_catalog.register(tool, echo)

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "hello",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            run_id = turn_response.json()["run"]["id"]

            def _process_later() -> None:
                time.sleep(0.1)
                container.orchestration_service.process_next_queued_run(
                    worker_id="http-tool-sse-worker",
                )

            worker = threading.Thread(target=_process_later)
            worker.start()
            try:
                with self.client.stream(
                    "GET",
                    f"/turns/{run_id}/events",
                    params={"poll_interval_seconds": 0.05, "timeout_seconds": 2.0},
                ) as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers["content-type"]
                    status_code = response.status_code
            finally:
                worker.join(timeout=1.0)

            self.assertEqual(status_code, 200)
            self.assertIn("text/event-stream", content_type)
            self.assertIn("event: snapshot", body)
            self.assertIn("event: message_appended", body)
            self.assertIn("event: tool_started", body)
            self.assertIn("event: tool_completed", body)
            self.assertIn("\"tool_name\": \"echo\"", body)
            self.assertIn("\"tool_status\": \"succeeded\"", body)
            self.assertIn("tool loop complete", body)
            self.assertIn("event: completed", body)


if __name__ == "__main__":
    unittest.main()
