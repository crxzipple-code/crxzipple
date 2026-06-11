from __future__ import annotations

import threading

from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain import LlmCapability
from crxzipple.modules.orchestration.application.observers import (
    turn_session_live_topic,
)
from crxzipple.shared.domain.events import named_event_topic

from tests.unit.orchestration_test_support import *  # noqa: F403


class _StreamingTextAdapter:
    def __init__(self, *deltas: str) -> None:
        self.deltas = deltas
        self.requests: list[LlmAdapterRequest] = []

    def invoke(
        self,
        _profile: object,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(result=LlmResult(text="".join(self.deltas)))

    def stream_invoke(
        self,
        _profile: object,
        request: LlmAdapterRequest,
    ):
        self.requests.append(request)
        text = ""
        for index, delta in enumerate(self.deltas, start=1):
            text += delta
            yield LlmStreamEvent(
                type="text_delta",
                sequence=index,
                data={"text": delta},
            )
        yield LlmStreamEvent(
            type="completed",
            sequence=len(self.deltas) + 1,
            data={"result": LlmResult(text=text).to_payload()},
        )


class _ToolThenFollowupAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(
        self,
        _profile: object,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        self.requests.append(request)
        request_number = len(self.requests)
        if request_number == 1:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        _expand_tool_bundle_call(
                            call_id="call-expand-echo",
                            source_id="test.local_package.echo",
                        ),
                    ),
                ),
            )
        if request_number == 2:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-expand-echo-group",
                            name="context_tree.expand",
                            arguments={
                                "node_id": "tools.bundle.test.local_package.echo.group.source",
                            },
                        ),
                    ),
                ),
            )
        if request_number == 3:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        _enable_tool_schema_call(
                            call_id="call-enable-echo-history",
                            tool_id="echo",
                        ),
                    ),
                ),
            )
        if request_number == 4:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-history-1",
                            name="echo",
                            arguments={"message": "first tool hello"},
                        ),
                    ),
                ),
            )
        if request_number == 5:
            return LlmAdapterResponse(result=LlmResult(text="first tool answer"))
        return LlmAdapterResponse(result=LlmResult(text="second answer"))


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
    def setUp(self) -> None:
        super().setUp()
        self._llm_credential_binding_id = self._install_default_llm_access_binding(
            self.container,
        )

    def test_prompt_preview_routes_auto_to_vision_model_for_tool_attachments(self) -> None:
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="text-default",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="image-special",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4",
                capabilities=(LlmCapability.VISION_INPUT,),
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.agent_service.register_profile(
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

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-attachment-routing",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.orchestration_intake_service.prepare_session_run(
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
        self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser.screenshot",
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
                    "tool_name": "browser.screenshot",
                },
            ),
        )

        preview = self.orchestration_inspection_service.preview_prompt(run.id)
        self.assertEqual(preview.llm_id, "image-special")
        self.assertEqual(preview.provider_request_options["response_format"], None)
        self.assertEqual(preview.provider_request_options["output_schema"], None)
        self.assertEqual(preview.provider_request_options["overrides"], {})
        self.assertEqual(
            preview.provider_request_options["request_metadata"][
                "context_render_snapshot_id"
            ],
            preview.context_render_snapshot_id,
        )
        events_service = self.events_service
        assert events_service is not None
        records = events_service.read_event_topic(
            named_event_topic("orchestration.llm_resolved"),
            limit=10,
        )
        resolver_event = next(
            record.envelope
            for record in records
            if record.envelope.payload.get("run_id") == run.id
        )
        self.assertEqual(resolver_event.payload["status"], "resolved")
        self.assertEqual(resolver_event.payload["requested_llm_id"], "auto")
        self.assertEqual(resolver_event.payload["resolved_llm_id"], "image-special")
        self.assertEqual(resolver_event.payload["strategy"], "auto-image")
        self.assertTrue(resolver_event.payload["input_has_image"])

    def test_prompt_preview_materializes_image_ref_tool_attachments(self) -> None:
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="text-default",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="image-special",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4",
                capabilities=(LlmCapability.VISION_INPUT,),
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.agent_service.register_profile(
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
        artifact = self.artifact_service.create_artifact(
            data=b"fake-png",
            mime_type="image/png",
            name="browser-screenshot.png",
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-ref-materialization",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.orchestration_intake_service.prepare_session_run(
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
        self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser.screenshot",
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
                    "tool_name": "browser.screenshot",
                },
            ),
        )

        preview = self.orchestration_inspection_service.preview_prompt(run.id)

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

    def test_prompt_preview_downgrades_image_ref_for_explicit_non_vision_model(self) -> None:
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="text-default",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="image-special",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4",
                capabilities=(LlmCapability.VISION_INPUT,),
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.agent_service.register_profile(
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
        artifact = self.artifact_service.create_artifact(
            data=b"fake-png",
            mime_type="image/png",
            name="browser-screenshot.png",
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-ref-non-vision-downgrade",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id="text-default",
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None
        self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser.screenshot",
                    "tool_call_id": "call-browser-ref-2",
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
                source_id="tool-run-browser-ref-2",
                metadata={
                    "tool_call_id": "call-browser-ref-2",
                    "tool_name": "browser.screenshot",
                },
            ),
        )

        preview = self.orchestration_inspection_service.preview_prompt(run.id)

        self.assertEqual(preview.llm_id, "text-default")
        tool_message = next(
            message for message in preview.messages if message.role.value == "tool"
        )
        self.assertEqual(
            tool_message.content[0],
            {"type": "text", "text": "Browser screenshot captured."},
        )
        self.assertEqual(
            tool_message.content[1],
            {
                "type": "text",
                "text": "[image attachment omitted for non-vision model:browser-screenshot.png]",
            },
        )

    def test_prompt_preview_omits_oversized_file_ref_attachments(self) -> None:
        self._register_agent_and_llm()
        artifact = self.artifact_service.create_artifact(
            data=b"x" * 4_000_001,
            mime_type="application/pdf",
            name="huge.pdf",
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-oversized-file-materialization",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.orchestration_intake_service.prepare_session_run(
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
        self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser.screenshot",
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
                    "tool_name": "browser.screenshot",
                },
            ),
        )

        preview = self.orchestration_inspection_service.preview_prompt(run.id)

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
        artifact = self.artifact_service.create_artifact(
            data=b"# Notes\n\nHello world",
            mime_type="text/markdown",
            name="notes.md",
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-text-file-materialization",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.orchestration_intake_service.prepare_session_run(
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
        self.session_service.append_message(
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

        preview = self.orchestration_inspection_service.preview_prompt(run.id)

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

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-orphan-tool-call-preview",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        run = self.orchestration_intake_service.prepare_session_run(
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

        self.session_service.append_message(
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
        self.session_service.append_message(
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
        self.session_service.append_message(
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

        preview = self.orchestration_inspection_service.preview_prompt(run.id)
        transcript_function_call_ids = [
            str(message.tool_call_id)
            for message in preview.messages
            if message.role is LlmMessageRole.ASSISTANT
            and isinstance(message.content, dict)
            and message.content.get("type") == "function_call"
        ]
        self.assertEqual(transcript_function_call_ids, ["paired-call-1"])

    def test_process_next_orchestration_assignment_completes_minimal_llm_loop(self) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.current_step, 1)
        schema_names = sorted(schema.name for schema in adapter.requests[0].tool_schemas)
        self.assertIn("context_tree.expand", schema_names)
        self.assertIn("context_tree.enable_tool_schema", schema_names)
        self.assertIn("context_tree.list", schema_names)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "hello from fake llm")
        self.assertEqual(
            processed.result_payload["llm_id"],
            "openai.gpt-5.4-mini",
        )

    def test_normal_turn_delivers_history_through_context_tree_not_direct_transcript(
        self,
    ) -> None:
        adapter = _SequentialTextAdapter("first answer", "second answer")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        first = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-history-tree-first",
                inbound_instruction=InboundInstruction(source="cli", content="first"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=first.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=first.id),
        )
        first_processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )
        self.assertIsNotNone(first_processed)

        second = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-history-tree-followup",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="continue please",
                ),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=second.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=second.id),
        )

        second_processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(second_processed)
        assert second_processed is not None
        self.assertEqual(second_processed.metadata["prompt_mode"], "normal_turn")
        self.assertEqual(len(adapter.requests), 2)
        request = adapter.requests[1]
        direct_messages = [
            message for message in request.messages if message.role is not LlmMessageRole.SYSTEM
        ]
        self.assertEqual(len(direct_messages), 1)
        self.assertEqual(direct_messages[0].role, LlmMessageRole.USER)
        self.assertEqual(
            direct_messages[0].content,
            [{"type": "text", "text": "continue please"}],
        )
        context_tree_message = next(
            message
            for message in request.messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        context_body = str(context_tree_message.content)
        self.assertIn("first answer", context_body)
        self.assertIn("Delivered as provider user message for this turn.", context_body)
        self.assertNotIn("<content>\n          continue please\n        </content>", context_body)

    def test_followup_turn_delivers_prior_tool_history_as_context_tree_interaction(
        self,
    ) -> None:
        adapter = _ToolThenFollowupAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Returns the input payload for local inline execution tests.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)

        first = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-history-tool-first",
                inbound_instruction=InboundInstruction(source="cli", content="use echo"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=first.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=first.id),
        )
        first_processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )
        self.assertIsNotNone(first_processed)
        assert first_processed is not None
        self.assertEqual(first_processed.status, OrchestrationRunStatus.COMPLETED)

        second = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-history-tool-followup",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="what happened?",
                ),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=second.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=second.id),
        )

        second_processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(second_processed)
        assert second_processed is not None
        self.assertEqual(second_processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(len(adapter.requests), 6)
        followup_request = adapter.requests[5]
        direct_messages = [
            message
            for message in followup_request.messages
            if message.role is not LlmMessageRole.SYSTEM
        ]
        self.assertEqual(len(direct_messages), 1)
        self.assertEqual(direct_messages[0].role, LlmMessageRole.USER)
        self.assertEqual(
            direct_messages[0].content,
            [{"type": "text", "text": "what happened?"}],
        )
        self.assertFalse(
            any(message.role is LlmMessageRole.TOOL for message in followup_request.messages),
        )
        context_tree_message = next(
            message
            for message in followup_request.messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        context_body = str(context_tree_message.content)
        self.assertIn('<tool_interaction tool_name="echo"', context_body)
        self.assertIn("call-echo-history-1", context_body)
        self.assertIn("first tool hello", context_body)

    def test_process_next_orchestration_assignment_downgrades_image_history_for_explicit_non_vision_model(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="handled without vision")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="text-default",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="image-special",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4",
                capabilities=(LlmCapability.VISION_INPUT,),
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.agent_service.register_profile(
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
        artifact = self.artifact_service.create_artifact(
            data=b"fake-png",
            mime_type="image/png",
            name="browser-screenshot.png",
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-non-vision-image-history",
                inbound_instruction=InboundInstruction(source="cli", content="look"),
            ),
        )
        run = self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
                requested_llm_id="text-default",
            ),
        )
        session_key = str(run.metadata["session_key"])
        active_session_id = run.active_session_id
        assert active_session_id is not None
        self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": "browser.screenshot",
                    "tool_call_id": "call-browser-ref-process-1",
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
                source_id="tool-run-browser-ref-process-1",
                metadata={
                    "tool_call_id": "call-browser-ref-process-1",
                    "tool_name": "browser.screenshot",
                },
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.result_payload["output_text"], "handled without vision")
        self.assertEqual(processed.result_payload["llm_id"], "text-default")
        tool_messages = [
            message
            for message in adapter.requests[-1].messages
            if message.role is LlmMessageRole.TOOL
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(
            tool_messages[0].content[1],
            {
                "type": "text",
                "text": "[image attachment omitted for non-vision model:browser-screenshot.png]",
            },
        )
        self.assertEqual(len(adapter.requests), 1)

    def test_process_next_orchestration_assignment_scales_context_budget_to_llm_context_window(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="small-window",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-small",
                context_window_tokens=2_000,
                credential_binding_id=self._llm_credential_binding_id,
            ),
        )
        self.agent_service.register_profile(
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

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-small-window-budget",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
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
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        prompt_report = processed.metadata["prompt_report"]
        self.assertEqual(prompt_report["context_budget"]["source"], "context_window_scaled")
        self.assertEqual(prompt_report["context_budget"]["max_estimated_tokens"], 300)
        self.assertEqual(prompt_report["context_budget"]["llm_context_window_tokens"], 2_000)
        self.assertLessEqual(prompt_report["context"]["estimated_tokens"], 300)
        self.assertTrue(
            any(
                block["kind"] == "agent_instruction" and block["truncated"]
                for block in prompt_report["context_blocks"]
            ),
        )

    def test_process_next_orchestration_assignment_exposes_workspace_context_tree_handle(self) -> None:
        adapter = _StaticTextAdapter(text="hello from fake llm")
        self.llm_adapter_registry.register(
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

            run = self.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-workspace-context",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            self.orchestration_intake_service.prepare_session_run(
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
            self.orchestration_intake_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = process_next_orchestration_assignment(self.container,
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            self.assertEqual(len(adapter.requests), 1)
            messages = adapter.requests[0].messages
            self.assertGreaterEqual(len(messages), 2)
            system_messages = [
                message
                for message in messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            self.assertFalse(
                any("# Available Tools" in str(message.content) for message in system_messages),
            )
            self.assertFalse(
                any("# Session Tools" in str(message.content) for message in system_messages),
            )
            self.assertFalse(
                any("# Session Start" in str(message.content) for message in system_messages),
            )
            tool_schema_names = {schema.name for schema in adapter.requests[0].tool_schemas}
            self.assertIn("context_tree.expand", tool_schema_names)
            self.assertNotIn("context_tree.recall_memory", tool_schema_names)
            self.assertNotIn("memory_search", tool_schema_names)
            self.assertIn("context_tree.enable_tool_schema", tool_schema_names)
            context_tree_message = next(
                message
                for message in system_messages
                if message.metadata.get("prompt_block_kind") == "context_workspace"
            )
            context_tree_content = str(context_tree_message.content)
            self.assertIn("<context_tree", context_tree_content)
            self.assertIn("Be helpful and concise.", context_tree_content)
            self.assertIn("# Runtime Context", context_tree_content)
            self.assertIn("- Agent: assistant", context_tree_content)
            self.assertIn("- Model: openai.gpt-5.4-mini", context_tree_content)
            self.assertIn("run.flow", context_tree_content)
            self.assertIn("Flow: Session Start", context_tree_content)
            self.assertIn("workspace.resources", context_tree_content)
            self.assertIn(
                "Collapsed nodes are actionable handles",
                context_tree_content,
            )
            self.assertIn(
                "Before saying a file, skill, memory, artifact, data source, or tool",
                context_tree_content,
            )
            self.assertIn(
                "Tool function nodes with `schema_enabled=true`",
                context_tree_content,
            )
            self.assertNotIn("Follow workspace conventions.", context_tree_content)
            self.assertFalse(
                any("# Workspace Context" in str(message.content) for message in system_messages),
            )
            self.assertIn(
                f"- Workspace: {workspace}",
                str(context_tree_message.content),
            )
            self.assertEqual(processed.metadata["prompt_mode"], "session_start")
            self.assertTrue(str(processed.metadata["context_render_snapshot_id"]).startswith("ctxsnap_"))
            self.assertEqual(processed.metadata["prompt_report"]["mode"], "session_start")
            self.assertEqual(
                processed.metadata["prompt_report"]["context_render"]["snapshot_id"],
                processed.metadata["context_render_snapshot_id"],
            )
            self.assertIn(
                "agent.identity",
                processed.metadata["prompt_report"]["context_render"]["included_node_ids"],
            )
            self.assertEqual(
                [block["kind"] for block in processed.metadata["prompt_report"]["context_blocks"]],
                [
                    "agent_instruction",
                    "runtime_context",
                ],
            )
            self.assertGreater(
                processed.metadata["prompt_report"]["context"]["estimated_tokens"],
                0,
            )
            self.assertGreater(
                processed.metadata["prompt_report"]["transcript"]["estimated_tokens"],
                0,
            )
            self.assertNotIn("workspace_context_workspace", processed.metadata)
            self.assertNotIn("workspace_context_files", processed.metadata)
            self.assertEqual(messages[-1].role, LlmMessageRole.USER)
            self.assertEqual(
                messages[-1].content,
                [{"type": "text", "text": "hello"}],
            )

    def test_process_next_orchestration_assignment_uses_session_bound_workspace_context(self) -> None:
        adapter = _StaticTextAdapter(text="workspace pinned")
        self.llm_adapter_registry.register(
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

            run = self.orchestration_intake_service.accept(
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
            prepared = self.orchestration_intake_service.prepare_session_run(
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
            self.agent_service.update_profile(
                UpdateAgentProfileInput(
                    id="assistant",
                    runtime_preferences=AgentRuntimePreferences(workspace=str(second_root)),
                ),
            )

            self.orchestration_intake_service.enqueue(
                EnqueueOrchestrationRunInput(
                    run_id=prepared.id,
                    priority=10,
                ),
            )
            processed = process_next_orchestration_assignment(self.container,
                worker_id="worker-session-workspace",
            )

            self.assertIsNotNone(processed)
            self.assertNotIn("workspace_context_workspace", processed.metadata)
            self.assertNotIn("workspace_context_files", processed.metadata)
            request = adapter.requests[-1]
            self.assertTrue(
                any(
                    message.role is LlmMessageRole.SYSTEM
                    and f"- Workspace: {first_root}" in str(message.content)
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

    def test_process_next_orchestration_assignment_ignores_legacy_session_llm_metadata(
        self,
    ) -> None:
        adapter = _StaticTextAdapter(text="binding-aware llm")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-binding-llm",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        prepared = self.orchestration_intake_service.prepare_session_run(
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
        with self.uow_factory() as uow:
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

        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(processed.result_payload["output_text"], "binding-aware llm")

    def test_llm_adapter_failure_is_surface_in_orchestration_error(self) -> None:
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _FailingAdapter(),
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-llm-failure",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
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
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
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

    def test_process_next_orchestration_assignment_publishes_raw_llm_text_delta(self) -> None:
        adapter = _StreamingTextAdapter("he", "llo")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-stream-delta-live",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        prepared = self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        live_records = self.events_service.read_event_topic(
            turn_session_live_topic(str(prepared.metadata["session_key"])),
            limit=10,
        )
        live_payloads = [
            record.envelope.payload
            for record in live_records
            if record.envelope.payload.get("event_name")
            == "orchestration.run.llm_text_delta"
        ]
        self.assertEqual(
            [payload.get("text") for payload in live_payloads],
            ["", "he", "hello"],
        )
        self.assertEqual(
            [payload.get("text_delta") for payload in live_payloads],
            ["", "he", "llo"],
        )
        named_records = self.events_service.read_event_topic(
            named_event_topic("orchestration.run.llm_text_delta"),
            limit=10,
        )
        named_payloads = [
            record.envelope.payload
            for record in named_records
            if record.envelope.payload.get("run_id") == run.id
        ]
        self.assertEqual(
            [payload.get("text") for payload in named_payloads],
            ["", "he", "hello"],
        )

    def test_process_next_orchestration_assignment_tolerates_cancelled_streaming_run(self) -> None:
        adapter = _BlockingStreamingAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-stream-cancelled",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        outcome: dict[str, object] = {}

        def _process() -> None:
            try:
                outcome["run"] = process_next_orchestration_assignment(self.container,
                    worker_id="worker-1",
                )
            except Exception as exc:  # pragma: no cover - asserted below
                outcome["error"] = exc

        worker = threading.Thread(target=_process, daemon=True)
        worker.start()
        self.assertTrue(adapter.started.wait(timeout=2.0))

        cancelled = self.orchestration_cancellation_service.cancel_run(
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
        refreshed = self.orchestration_run_query_service.get_run(run.id)
        self.assertEqual(refreshed.status, OrchestrationRunStatus.CANCELLED)
