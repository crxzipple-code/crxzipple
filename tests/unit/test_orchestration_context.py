from __future__ import annotations

import threading

from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain import LlmCapability

from tests.unit.orchestration_test_support import *  # noqa: F403


class _BlockingStreamingAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []
        self.started = threading.Event()
        self.release = threading.Event()

    def invoke(
        self,
        _profile: object,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(result=LlmResult(text="fallback"))

    def stream_invoke(
        self,
        _profile: object,
        request: LlmAdapterRequest,
    ):
        self.requests.append(request)
        self.started.set()
        self.release.wait(timeout=2.0)
        yield LlmStreamEvent(
            type="text_delta",
            sequence=1,
            data={"text": "hello"},
        )
        yield LlmStreamEvent(
            type="completed",
            sequence=2,
            data={"result": LlmResult(text="hello").to_payload()},
        )


class OrchestrationContextTestCase(OrchestrationTestCaseBase):
    def test_prompt_preview_routes_auto_to_vision_model_for_tool_attachments(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="text-default",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="image-special",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4",
                capabilities=(LlmCapability.VISION_INPUT,),
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="text-default",
                    image_llm_id="image-special",
                ),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-attachment-routing",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id="auto",
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser",
                    "tool_call_id": "call-browser-1",
                    "status": "succeeded",
                    "output": {"ok": True},
                    "blocks": [
                        {
                            "type": "text",
                            "text": "Browser screenshot captured.",
                        },
                        {
                            "type": "image",
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                        },
                    ],
                    "text": "Browser screenshot captured.",
                },
                source_kind="tool_run",
                source_id="tool-run-browser-1",
                metadata={
                    "tool_call_id": "call-browser-1",
                    "tool_name": "browser",
                },
            ),
        )

        preview = self.container.orchestration_service.preview_prompt(run.id)
        self.assertEqual(preview.llm_id, "image-special")

    def test_prompt_preview_materializes_image_ref_tool_attachments(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="text-default",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="image-special",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4",
                capabilities=(LlmCapability.VISION_INPUT,),
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Be helpful and concise.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="text-default",
                    image_llm_id="image-special",
                ),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )
        artifact = self.container.artifact_service.create_artifact(
            data=b"fake-png",
            mime_type="image/png",
            name="browser-screenshot.png",
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-ref-materialization",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id="auto",
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser",
                    "tool_call_id": "call-browser-ref-1",
                    "status": "succeeded",
                    "details": {"ok": True},
                    "content": [
                        {
                            "type": "text",
                            "text": "Browser screenshot captured.",
                        },
                        {
                            "type": "image_ref",
                            "artifact_id": artifact.id,
                            "mime_type": "image/png",
                            "name": "browser-screenshot.png",
                            "preview_url": f"/artifacts/{artifact.id}/preview",
                            "original_url": f"/artifacts/{artifact.id}/original",
                        },
                    ],
                },
                source_kind="tool_run",
                source_id="tool-run-browser-ref-1",
                metadata={
                    "tool_call_id": "call-browser-ref-1",
                    "tool_name": "browser",
                },
            ),
        )

        preview = self.container.orchestration_service.preview_prompt(run.id)

        self.assertEqual(preview.llm_id, "image-special")
        tool_message = next(
            message for message in preview.messages if message.role.value == "tool"
        )
        self.assertEqual(
            tool_message.content[0],
            {"type": "text", "text": "Browser screenshot captured."},
        )
        self.assertEqual(tool_message.content[1]["type"], "image")
        self.assertEqual(tool_message.content[1]["mime_type"], "image/png")
        self.assertEqual(tool_message.content[1]["data"], "ZmFrZS1wbmc=")

    def test_prompt_preview_omits_oversized_file_ref_attachments(self) -> None:
        self._register_agent_and_llm()
        artifact = self.container.artifact_service.create_artifact(
            data=b"x" * 4_000_001,
            mime_type="application/pdf",
            name="huge.pdf",
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-oversized-file-materialization",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser",
                    "tool_call_id": "call-browser-file-1",
                    "status": "succeeded",
                    "details": {"ok": True},
                    "content": [
                        {
                            "type": "file_ref",
                            "artifact_id": artifact.id,
                            "mime_type": "application/pdf",
                            "name": "huge.pdf",
                        },
                    ],
                },
                source_kind="tool_run",
                source_id="tool-run-browser-file-1",
                metadata={
                    "tool_call_id": "call-browser-file-1",
                    "tool_name": "browser",
                },
            ),
        )

        preview = self.container.orchestration_service.preview_prompt(run.id)

        tool_message = next(
            message for message in preview.messages if message.role.value == "tool"
        )
        self.assertEqual(
            tool_message.content,
            [
                {
                    "type": "text",
                    "text": "[file attachment omitted - exceeds llm size budget:huge.pdf]",
                },
            ],
        )

    def test_prompt_preview_materializes_text_file_ref_as_text(self) -> None:
        self._register_agent_and_llm()
        artifact = self.container.artifact_service.create_artifact(
            data=b"# Notes\n\nHello world",
            mime_type="text/markdown",
            name="notes.md",
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-text-file-materialization",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "reader",
                    "tool_call_id": "call-reader-1",
                    "status": "succeeded",
                    "details": {"ok": True},
                    "content": [
                        {
                            "type": "file_ref",
                            "artifact_id": artifact.id,
                            "mime_type": "text/markdown",
                            "name": "notes.md",
                        },
                    ],
                },
                source_kind="tool_run",
                source_id="tool-run-reader-1",
                metadata={
                    "tool_call_id": "call-reader-1",
                    "tool_name": "reader",
                },
            ),
        )

        preview = self.container.orchestration_service.preview_prompt(run.id)

        tool_message = next(
            message for message in preview.messages if message.role.value == "tool"
        )
        self.assertEqual(
            tool_message.content,
            [
                {
                    "type": "text",
                    "text": "[file:notes.md]\n# Notes\n\nHello world",
                },
            ],
        )

    def test_prompt_preview_filters_orphan_function_calls_from_transcript(self) -> None:
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-orphan-tool-call-preview",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        run = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None

        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="assistant",
                kind=SessionMessageKind.MESSAGE,
                content_payload={
                    "type": "function_call",
                    "call_id": "orphan-call-1",
                    "name": "echo",
                    "arguments": {"message": "orphan"},
                },
                source_kind="llm_invocation",
                source_id="llm-1",
                metadata={
                    "tool_call_id": "orphan-call-1",
                    "tool_name": "echo",
                },
            ),
        )
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="assistant",
                kind=SessionMessageKind.MESSAGE,
                content_payload={
                    "type": "function_call",
                    "call_id": "paired-call-1",
                    "name": "echo",
                    "arguments": {"message": "paired"},
                },
                source_kind="llm_invocation",
                source_id="llm-1",
                metadata={
                    "tool_call_id": "paired-call-1",
                    "tool_name": "echo",
                },
            ),
        )
        self.container.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "echo",
                    "tool_call_id": "paired-call-1",
                    "status": "succeeded",
                    "output": {"echo": "paired"},
                },
                source_kind="tool_run",
                source_id="tool-run-1",
                metadata={
                    "tool_call_id": "paired-call-1",
                    "tool_name": "echo",
                },
            ),
        )

        preview = self.container.orchestration_service.preview_prompt(run.id)
        transcript_function_call_ids = [
            str(message.tool_call_id)
            for message in preview.messages
            if message.role is LlmMessageRole.ASSISTANT
            and isinstance(message.content, dict)
            and message.content.get("type") == "function_call"
        ]
        self.assertEqual(transcript_function_call_ids, ["paired-call-1"])

    def test_process_next_queued_run_completes_minimal_llm_loop(self) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.current_step, 1)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "hello from fake llm")
        self.assertEqual(
            processed.result_payload["llm_id"],
            "openai.gpt-5.4-mini",
        )
        self.assertEqual(processed.worker_id, "worker-1")

        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(adapter.requests[0].messages[0].role, LlmMessageRole.SYSTEM)
        self.assertEqual(
            adapter.requests[0].messages[0].content,
            "Be helpful and concise.",
        )
        self.assertEqual(adapter.requests[0].messages[1].role, LlmMessageRole.SYSTEM)
        self.assertIn("# Runtime Context", str(adapter.requests[0].messages[1].content))
        self.assertEqual(adapter.requests[0].messages[-1].role, LlmMessageRole.USER)
        self.assertEqual(
            adapter.requests[0].messages[-1].content,
            [{"type": "text", "text": "hello"}],
        )

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual([message.role for message in session_messages], ["user", "assistant"])
        self.assertEqual(session_messages[0].source_kind, "orchestration_run")
        self.assertEqual(session_messages[0].source_id, run.id)
        self.assertEqual(session_messages[1].source_kind, "llm_invocation")

    def test_process_next_queued_run_scales_system_budget_to_llm_context_window(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="small-window",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-small",
                context_window_tokens=2_000,
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="assistant",
                name="Assistant",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="A" * 20_000,
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="small-window"),
                runtime_preferences=AgentRuntimePreferences(),
            ),
        )

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-small-window-budget",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id="small-window",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        prompt_report = processed.metadata["prompt_report"]
        self.assertEqual(prompt_report["system_budget"]["source"], "context_window_scaled")
        self.assertEqual(prompt_report["system_budget"]["max_estimated_tokens"], 300)
        self.assertEqual(prompt_report["system_budget"]["llm_context_window_tokens"], 2_000)
        self.assertLessEqual(prompt_report["system"]["estimated_tokens"], 300)
        self.assertTrue(
            any(
                block["kind"] == "agent_instruction" and block["truncated"]
                for block in prompt_report["system_blocks"]
            ),
        )

    def test_process_next_queued_run_injects_agents_workspace_context(self) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir)
            (workspace / "AGENTS.md").write_text(
                "# AGENTS.md\n\nFollow workspace conventions.\n",
                encoding="utf-8",
            )
            (workspace / "SOUL.md").write_text(
                "Respond with calm confidence.\n",
                encoding="utf-8",
            )
            (workspace / "TOOLS.md").write_text(
                "Prefer tools when grounded facts are needed.\n",
                encoding="utf-8",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-workspace-context",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            self.container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                    requested_llm_id="openai.gpt-5.4-mini",
                ),
            )
            self.container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = self.container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            self.assertEqual(len(adapter.requests), 1)
            messages = adapter.requests[0].messages
            self.assertGreaterEqual(len(messages), 4)
            system_messages = [
                message
                for message in messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            self.assertEqual(str(system_messages[0].content), "Be helpful and concise.")
            self.assertIn("# Runtime Context", str(system_messages[1].content))
            self.assertIn("- Agent: assistant", str(system_messages[1].content))
            self.assertIn("- Model: openai.gpt-5.4-mini", str(system_messages[1].content))
            self.assertIn("# Session Start", str(system_messages[2].content))
            self.assertIn("# Workspace Context", str(system_messages[3].content))
            self.assertIn("## AGENTS.md", str(system_messages[3].content))
            self.assertIn("Follow workspace conventions.", str(system_messages[3].content))
            self.assertIn("## SOUL.md", str(system_messages[3].content))
            self.assertIn("Respond with calm confidence.", str(system_messages[3].content))
            self.assertIn("## TOOLS.md", str(system_messages[3].content))
            self.assertIn(
                "Prefer tools when grounded facts are needed.",
                str(system_messages[3].content),
            )
            self.assertIn(
                f"- Agent home / workspace: {workspace}",
                str(system_messages[1].content),
            )
            self.assertEqual(processed.metadata["prompt_mode"], "session_start")
            self.assertEqual(processed.metadata["prompt_report"]["mode"], "session_start")
            self.assertEqual(
                [block["kind"] for block in processed.metadata["prompt_report"]["system_blocks"]],
                [
                    "agent_instruction",
                    "runtime_context",
                    "flow_prompt",
                    "project_context",
                    "skills_catalog",
                ],
            )
            self.assertGreater(
                processed.metadata["prompt_report"]["system"]["estimated_tokens"],
                0,
            )
            self.assertGreater(
                processed.metadata["prompt_report"]["transcript"]["estimated_tokens"],
                0,
            )
            self.assertEqual(processed.metadata["workspace_context_workspace"], str(workspace))
            self.assertIn(
                {"path": "AGENTS.md", "chars": len("# AGENTS.md\n\nFollow workspace conventions.")},
                processed.metadata["workspace_context_files"],
            )
            self.assertIn(
                {"path": "SOUL.md", "chars": len("Respond with calm confidence.")},
                processed.metadata["workspace_context_files"],
            )
            self.assertIn(
                {
                    "path": "TOOLS.md",
                    "chars": len("Prefer tools when grounded facts are needed."),
                },
                processed.metadata["workspace_context_files"],
            )
            self.assertEqual(messages[-1].role, LlmMessageRole.USER)
            self.assertEqual(
                messages[-1].content,
                [{"type": "text", "text": "hello"}],
            )

    def test_process_next_queued_run_uses_session_bound_workspace_context(self) -> None:
        adapter = _StaticTextAdapter(text="workspace pinned")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as first_workspace, tempfile.TemporaryDirectory() as second_workspace:
            first_root = Path(first_workspace)
            second_root = Path(second_workspace)
            (first_root / "AGENTS.md").write_text(
                "# AGENTS.md\n\nUse the first workspace context.\n",
                encoding="utf-8",
            )
            (second_root / "AGENTS.md").write_text(
                "# AGENTS.md\n\nUse the second workspace context.\n",
                encoding="utf-8",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(first_root)),
            )

            run = self.container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-session-workspace-binding",
                    inbound_instruction=InboundInstruction(
                        source="http",
                        content="hello",
                    ),
                    priority=10,
                    max_steps=3,
                ),
            )
            prepared = self.container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                    ),
                    requested_llm_id="openai.gpt-5.4-mini",
                    priority=10,
                ),
            )
            self.container.agent_service.update_profile(
                UpdateAgentProfileInput(
                    id="assistant",
                    runtime_preferences=AgentRuntimePreferences(workspace=str(second_root)),
                ),
            )

            self.container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(
                    run_id=prepared.id,
                    priority=10,
                ),
            )
            processed = self.container.orchestration_service.process_next_queued_run(
                worker_id="worker-session-workspace",
            )

            self.assertIsNotNone(processed)
            self.assertEqual(
                processed.metadata["workspace_context_workspace"],
                str(first_root),
            )
            self.assertIn(
                {
                    "path": "AGENTS.md",
                    "chars": len("# AGENTS.md\n\nUse the first workspace context."),
                },
                processed.metadata["workspace_context_files"],
            )
            self.assertNotIn(
                {
                    "path": "AGENTS.md",
                    "chars": len("# AGENTS.md\n\nUse the second workspace context."),
                },
                processed.metadata["workspace_context_files"],
            )
            request = adapter.requests[-1]
            self.assertTrue(
                any(
                    message.role is LlmMessageRole.SYSTEM
                    and "Use the first workspace context." in str(message.content)
                    for message in request.messages
                )
            )
            self.assertFalse(
                any(
                    message.role is LlmMessageRole.SYSTEM
                    and "Use the second workspace context." in str(message.content)
                    for message in request.messages
                )
            )

    def test_process_next_queued_run_ignores_legacy_session_llm_metadata(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="binding-aware llm")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-binding-llm",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        prepared = self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id="openai.gpt-5.4-mini",
            ),
        )
        assert prepared.active_session_id is not None
        with self.container.uow_factory() as uow:
            session = uow.sessions.get("agent:assistant:main")
            assert session is not None
            session.metadata["runtime_binding"] = {
                "agent_id": "assistant",
            }
            uow.sessions.add(session)
            instance = uow.session_instances.get(prepared.active_session_id)
            assert instance is not None
            instance.metadata["runtime_binding"] = {
                "agent_id": "assistant",
            }
            instance.metadata["agent_id"] = "assistant"
            instance.metadata["llm_id"] = "legacy-stale-llm"
            uow.session_instances.add(instance)
            uow.commit()

        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(processed.result_payload["output_text"], "binding-aware llm")

    def test_llm_adapter_failure_is_surface_in_orchestration_error(self) -> None:
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _FailingAdapter(),
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-llm-failure",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id="openai.gpt-5.4-mini",
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(processed.stage, OrchestrationRunStage.FAILED)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "engine_failed")
        self.assertIn("adapter_error", processed.error.message)
        self.assertIn("sample adapter failure", processed.error.message)

    def test_process_next_queued_run_tolerates_cancelled_streaming_run(self) -> None:
        adapter = _BlockingStreamingAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-stream-cancelled",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        outcome: dict[str, object] = {}

        def _process() -> None:
            try:
                outcome["run"] = self.container.orchestration_service.process_next_queued_run(
                    worker_id="worker-1",
                )
            except Exception as exc:  # pragma: no cover - asserted below
                outcome["error"] = exc

        worker = threading.Thread(target=_process, daemon=True)
        worker.start()
        self.assertTrue(adapter.started.wait(timeout=2.0))

        cancelled = self.container.orchestration_service.cancel_run(
            run.id,
            reason="user_cancelled",
        )
        self.assertEqual(cancelled.status, OrchestrationRunStatus.CANCELLED)
        adapter.release.set()

        worker.join(timeout=3.0)
        self.assertFalse(worker.is_alive())
        self.assertNotIn("error", outcome)
        processed = outcome.get("run")
        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.CANCELLED)
        refreshed = self.container.orchestration_service.get_run(run.id)
        self.assertEqual(refreshed.status, OrchestrationRunStatus.CANCELLED)
