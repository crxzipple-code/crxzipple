from __future__ import annotations

import asyncio
import threading

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmContinuationReason,
    LlmContinuationSignal,
    LlmDefaults,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
    LlmMessagePhase,
    LlmProfile,
    LlmProviderContinuation,
    LlmProviderKind,
    LlmResponseItem,
    LlmResponseItemKind,
    ToolSchema,
)
from crxzipple.modules.llm.application.runtime_request import (
    RuntimeLlmRequestRenderSnapshot,
    RuntimeLlmRequest,
    RuntimeToolSurface,
)
from crxzipple.modules.llm.application.provider_continuation import (
    build_provider_continuation_state_from_invocation,
    provider_continuation_from_state,
)
from crxzipple.modules.orchestration.infrastructure.adapters import (
    AuthorizationServiceAdapter,
)
from crxzipple.modules.orchestration.application.engine_llm_invoker import (
    OrchestrationEngineLlmInvoker,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.orchestration.domain import ExecutionOwnerReference
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses import (
    OpenAICodexResponsesAdapter,
)
from crxzipple.modules.access.application.repositories import AccessOAuthAccountRecord
from crxzipple.modules.access.infrastructure.oauth_tokens import OAuthTokenDocument
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
    TOOL_RESULT_ENVELOPE_SCHEMA_VERSION,
)
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.modules.tool.domain import ToolExecutionTarget
from crxzipple.shared.domain.events import Event

from tests.unit.orchestration_test_support import *  # noqa: F403
from tests.unit.tool_runtime_test_support import process_next_background_tool_run
from tools.skills.local import SkillsToolDeps, skill_read


def test_provider_continuation_state_omits_codex_websocket_fallback() -> None:
    class _Invocation:
        id = "llm-invocation-fallback"
        provider_request_id = "resp-fallback"
        provider_request_payload_preview = {
            "api_family": LlmApiFamily.OPENAI_CODEX_RESPONSES.value,
            "transport": "websocket",
            "has_previous_response_id": True,
            "input_baseline_fingerprints": ["fingerprint-1", "fingerprint-2"],
            "instructions_fingerprint": "instructions-fingerprint",
            "tool_fingerprints": ["tool-fingerprint"],
        }
        result = LlmResult(
            text="fallback completed",
            metadata={
                "provider_continuation_fallback": True,
                "provider_continuation_fallback_reason": (
                    "websocket_continuation_failed_before_output"
                ),
            },
        )

    state = build_provider_continuation_state_from_invocation(_Invocation())

    assert state == {}
    assert provider_continuation_from_state(state) is None


def _tool_call_response_item(
    request: LlmAdapterRequest,
    *,
    sequence_no: int,
    call_id: str,
    name: str,
    arguments: dict[str, object],
) -> LlmResponseItem:
    return LlmResponseItem(
        id=f"{request.invocation_id}:item:{sequence_no}",
        invocation_id=request.invocation_id,
        sequence_no=sequence_no,
        kind=LlmResponseItemKind.TOOL_CALL,
        phase=LlmMessagePhase.COMMENTARY,
        content_payload={
            "call_id": call_id,
            "tool_name": name,
            "arguments": dict(arguments),
        },
        provider_item_id=f"provider-{call_id}",
        call_id=call_id,
        tool_name=name,
        provider_replay_candidate=True,
        user_timeline_candidate=False,
    )


def _request_render_snapshot(request: LlmAdapterRequest) -> dict[str, object]:
    request_render_snapshot = request.request_metadata.get("request_render_snapshot")
    assert isinstance(request_render_snapshot, dict)
    assert isinstance(request_render_snapshot.get("snapshot_id"), str)
    assert "raw_tree_body" not in request_render_snapshot
    assert "<context_tree" not in str([message.content for message in request.messages])
    return request_render_snapshot


class _ResponseItemsInlineToolLoopAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        request_index = len(self.requests) - 1
        if request_index == 0:
            return LlmAdapterResponse(
                result=LlmResult(text=""),
                response_items=(
                    _tool_call_response_item(
                        request,
                        sequence_no=1,
                        call_id="item-call-search-echo",
                        name="capability.search",
                        arguments={
                            "query": "test.local_package.echo",
                            "enable": True,
                            "limit": 8,
                        },
                    ),
                ),
                continuation=LlmContinuationSignal(
                    end_turn=False,
                    needs_follow_up=True,
                    reason=LlmContinuationReason.TOOL_CALL,
                ),
            )
        if request_index == 1:
            return LlmAdapterResponse(
                result=LlmResult(text=""),
                response_items=(
                    _tool_call_response_item(
                        request,
                        sequence_no=1,
                        call_id="item-call-enable-echo",
                        name="capability.search",
                        arguments={"query": "echo", "enable": True, "limit": 8},
                    ),
                ),
                continuation=LlmContinuationSignal(
                    end_turn=False,
                    needs_follow_up=True,
                    reason=LlmContinuationReason.TOOL_CALL,
                ),
            )
        if request_index == 2:
            return LlmAdapterResponse(
                result=LlmResult(text=""),
                response_items=(
                    _tool_call_response_item(
                        request,
                        sequence_no=1,
                        call_id="item-call-echo-1",
                        name="echo",
                        arguments={"message": "hello from response item"},
                    ),
                ),
                continuation=LlmContinuationSignal(
                    end_turn=False,
                    needs_follow_up=True,
                    reason=LlmContinuationReason.TOOL_CALL,
                ),
            )
        return LlmAdapterResponse(
            result=LlmResult(text="response item tool loop complete"),
            continuation=LlmContinuationSignal(
                end_turn=True,
                needs_follow_up=False,
                reason=LlmContinuationReason.NONE,
            ),
        )


class _ContinuationFollowupAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            return LlmAdapterResponse(
                result=LlmResult(text="still thinking"),
                continuation=LlmContinuationSignal(
                    end_turn=False,
                    needs_follow_up=True,
                    reason=LlmContinuationReason.PROVIDER_END_TURN_FALSE,
                    provider_payload={"end_turn": False},
                ),
            )
        return LlmAdapterResponse(
            result=LlmResult(text="final answer after provider continuation"),
            continuation=LlmContinuationSignal(
                end_turn=True,
                needs_follow_up=False,
                reason=LlmContinuationReason.NONE,
            ),
        )


class _ProviderNativeToolContinuationAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def preview_request(self, _profile: object, request: LlmAdapterRequest) -> dict[str, object]:
        self.requests.append(request)
        continuation = request.continuation
        tool_outputs = [
            item
            for item in request.input_items
            if item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT
        ]
        input_types = (
            ("function_call_output",)
            if continuation is not None and tool_outputs
            else ("message",)
        )
        return {
            "preview_source": "test_adapter",
            "api_family": "openai_responses",
            "transport": "http",
            "has_previous_response_id": continuation is not None,
            "previous_response_id": (
                continuation.previous_response_id
                if continuation is not None
                else None
            ),
            "input_item_count": len(input_types),
            "input_item_types": input_types,
            "payload_preview": {
                "previous_response_id": (
                    continuation.previous_response_id
                    if continuation is not None
                    else None
                ),
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": tool_outputs[-1].payload.get("call_id"),
                    },
                ]
                if continuation is not None and tool_outputs
                else [{"type": "message"}],
            },
        }

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        if len(self.requests) == 1:
            return LlmAdapterResponse(
                result=LlmResult(text=""),
                response_items=(
                    _tool_call_response_item(
                        request,
                        sequence_no=1,
                        call_id="call-provider-native-search",
                        name="capability.search",
                        arguments={"query": "echo", "enable": True, "limit": 8},
                    ),
                ),
                provider_request_id="resp_first",
                continuation=LlmContinuationSignal(
                    end_turn=False,
                    needs_follow_up=True,
                    reason=LlmContinuationReason.TOOL_CALL,
                ),
            )
        return LlmAdapterResponse(
            result=LlmResult(text="provider native final"),
            provider_request_id="resp_second",
            continuation=LlmContinuationSignal(
                end_turn=True,
                needs_follow_up=False,
                reason=LlmContinuationReason.NONE,
            ),
        )


class _CodexWebSocketProviderNativeToolContinuationAdapter(
    _ProviderNativeToolContinuationAdapter,
):
    def __init__(self) -> None:
        super().__init__()
        self._preview_adapter = OpenAICodexResponsesAdapter()

    def preview_request(self, profile: object, request: LlmAdapterRequest) -> dict[str, object]:
        self.requests.append(request)
        return self._preview_adapter.preview_request(profile, request)  # type: ignore[arg-type]


class _TestAccessConfigView:
    def __init__(
        self,
        records: dict[str, AccessCredentialBindingRecord],
        *,
        fallback: object | None,
    ) -> None:
        self.records = records
        self.fallback = fallback

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | object | None:
        if binding_id in self.records:
            return self.records[binding_id]
        get_binding = getattr(self.fallback, "get_credential_binding", None)
        if callable(get_binding):
            return get_binding(binding_id)
        return None


class _ProviderContinuationUnsupportedToolAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            return LlmAdapterResponse(
                result=LlmResult(text=""),
                response_items=(
                    _tool_call_response_item(
                        request,
                        sequence_no=1,
                        call_id="call-unsupported-search",
                        name="capability.search",
                        arguments={"query": "echo", "enable": True, "limit": 8},
                    ),
                ),
                provider_request_id="chat-first",
                continuation=LlmContinuationSignal(
                    end_turn=False,
                    needs_follow_up=True,
                    reason=LlmContinuationReason.TOOL_CALL,
                ),
            )
        return LlmAdapterResponse(
            result=LlmResult(text="fallback final"),
            provider_request_id="chat-second",
            continuation=LlmContinuationSignal(
                end_turn=True,
                needs_follow_up=False,
                reason=LlmContinuationReason.NONE,
            ),
        )


class _ProviderNativeRuntimeToolSurfaceUpdateAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        request_index = len(self.requests) - 1
        response_items: tuple[LlmResponseItem, ...] = ()
        if request_index == 0:
            result = LlmResult(text="")
            response_items = (
                _tool_call_response_item(
                    request,
                    sequence_no=1,
                    call_id="call-provider-search-echo",
                    name="capability.search",
                    arguments={"query": "echo", "enable": True, "limit": 8},
                ),
            )
            provider_request_id = "resp-surface-1"
        elif request_index == 1:
            result = LlmResult(text="")
            response_items = (
                _tool_call_response_item(
                    request,
                    sequence_no=1,
                    call_id="call-provider-echo",
                    name="echo",
                    arguments={"message": "provider surface updated"},
                ),
            )
            provider_request_id = "resp-surface-2"
        elif request_index == 2:
            result = LlmResult(text="provider surface final")
            provider_request_id = "resp-surface-3"
        else:
            result = LlmResult(text="provider surface final")
            provider_request_id = "resp-surface-extra"
        return LlmAdapterResponse(
            result=result,
            response_items=response_items,
            provider_request_id=provider_request_id,
            continuation=LlmContinuationSignal(
                end_turn=request_index >= 2,
                needs_follow_up=request_index < 2,
                reason=(
                    LlmContinuationReason.NONE
                    if request_index >= 2
                    else LlmContinuationReason.TOOL_CALL
                ),
            ),
        )


class _ProviderExternalOnlyAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(
            result=LlmResult(text="provider search completed"),
            response_items=(
                LlmResponseItem(
                    id=f"{request.invocation_id}:item:provider-search",
                    invocation_id=request.invocation_id,
                    sequence_no=1,
                    kind=LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={
                        "provider_tool_name": "web_search",
                        "status": "completed",
                    },
                    provider_item_id="provider-search-item-1",
                    tool_name="web_search",
                    provider_replay_candidate=True,
                    user_timeline_candidate=True,
                ),
            ),
            continuation=LlmContinuationSignal(
                end_turn=True,
                needs_follow_up=False,
                reason=LlmContinuationReason.NONE,
            ),
        )


class _FinalAnswerResponseItemAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(
            result=LlmResult(text="final item answer"),
            response_items=(
                LlmResponseItem(
                    id=f"{request.invocation_id}:item:final",
                    invocation_id=request.invocation_id,
                    sequence_no=1,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    role=LlmMessageRole.ASSISTANT,
                    phase=LlmMessagePhase.FINAL_ANSWER,
                    content_payload={"text": "final item answer"},
                    provider_item_id="provider-final-item-1",
                    provider_replay_candidate=True,
                    user_timeline_candidate=True,
                ),
            ),
            continuation=LlmContinuationSignal(
                end_turn=True,
                needs_follow_up=False,
                reason=LlmContinuationReason.NONE,
            ),
        )


class _CommentaryOnlyResponseItemAdapter:
    def __init__(self) -> None:
        self.requests: list[LlmAdapterRequest] = []

    def invoke(self, _profile: object, request: LlmAdapterRequest) -> LlmAdapterResponse:
        self.requests.append(request)
        return LlmAdapterResponse(
            result=LlmResult(text="I will inspect the current state first."),
            response_items=(
                LlmResponseItem(
                    id=f"{request.invocation_id}:item:commentary",
                    invocation_id=request.invocation_id,
                    sequence_no=1,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    role=LlmMessageRole.ASSISTANT,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={
                        "text": "I will inspect the current state first.",
                    },
                    provider_item_id="provider-commentary-item-1",
                    provider_replay_candidate=True,
                    user_timeline_candidate=True,
                ),
            ),
            continuation=LlmContinuationSignal(
                end_turn=True,
                needs_follow_up=False,
                reason=LlmContinuationReason.NONE,
            ),
        )


class OrchestrationToolsTestCase(OrchestrationTestCaseBase):
    def test_sessions_yield_stops_inline_tool_auto_continue(self) -> None:
        adapter = _SequentialResultAdapter(
            LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-expand-sessions",
                        name="capability.search",
                        arguments={
                            "query": "bundled.local_package.sessions",
                            "enable": True,
                            "limit": 8,
                        },
                    ),
                ),
            ),
            LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-expand-sessions-run-control",
                        name="capability.search",
                        arguments={
                            "query": "sessions run control",
                            "enable": True,
                            "limit": 8,
                        },
                    ),
                ),
            ),
            LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-yield-1",
                        name="capability.search",
                        arguments={"query": "sessions_yield", "enable": True, "limit": 8},
                    ),
                ),
            ),
            LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-yield-2",
                        name="sessions_yield",
                        arguments={"reason": "wait for delegated work"},
                    ),
                ),
            ),
            "second invocation should not run",
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-sessions-yield",
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
        self.assertEqual(
            processed.status,
            OrchestrationRunStatus.COMPLETED,
            processed.error.to_payload() if processed.error is not None else None,
        )
        self.assertEqual(len(adapter.requests), 4)
        self.assertEqual(processed.result_payload["yield_requested"], True)
        self.assertEqual(
            processed.result_payload["yield_reason"],
            "wait for delegated work",
        )

    def test_access_blocked_stale_tool_call_fails_with_setup_payload(self) -> None:
        adapter = _SequentialResultAdapter(
            LlmResult(
                text="calling hidden tool",
                tool_calls=(
                    ToolCallIntent(
                        id="call-missing-access-tool",
                        name="missing_access_tool",
                        arguments={},
                    ),
                ),
            ),
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        self.seed_tool(
            tool_id="missing_access_tool",
            name="Missing Access Tool",
            description="Requires an external credential.",
            access_requirements=("env:MISSING_STALE_TOOL_TOKEN",),
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-stale-access-tool-call",
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

        with patch.dict("os.environ", {"MISSING_STALE_TOOL_TOKEN": ""}):
            processed = process_next_orchestration_assignment(
                self.container,
                worker_id="worker-1",
            )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertIsNotNone(processed.error)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "tool_surface_not_visible")
        self.assertIn("missing_access_tool", processed.error.message)

    def test_wait_on_tool_reconciles_when_tool_finished_before_wait_mapping(self) -> None:
        self._register_agent_and_llm()

        tool = self.seed_tool(
            tool_id="background_echo",
            name="Background Echo",
            description="Only runs in the background.",
            supported_modes=(ToolMode.BACKGROUND,),
            runtime_key="background_echo",
        )

        async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"message": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, background_echo)

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-early-tool-finish",
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
        claimed = assign_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert claimed is not None

        queued_tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="background_echo",
                    arguments={"message": "background hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        self.orchestration_executor_service.advance_assignment(
            run_id=run.id,
            worker_id="worker-1",
            stage=OrchestrationRunStage.LLM,
            step_increment=1,
        )
        self.orchestration_executor_service.advance_assignment(
            run_id=run.id,
            worker_id="worker-1",
            stage=OrchestrationRunStage.TOOL,
            execution_payload={
                "llm_invocation_id": "llm-early-tool-finish",
                "tool_run_links": [
                    {
                        "tool_call_id": "call-early-tool-finish",
                        "tool_name": "background_echo",
                        "tool_run_id": queued_tool_run.id,
                        "tool_id": "background_echo",
                        "status": "queued",
                        "background": True,
                    },
                ],
            },
        )
        finished_tool_run = process_next_background_tool_run(
            self.container,
            worker_id="tool-worker-1",
        )

        self.assertEqual(queued_tool_run.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(finished_tool_run)
        assert finished_tool_run is not None
        self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

        reconciled = self.orchestration_executor_service.wait_assignment_on_tool(
            run_id=run.id,
            worker_id="worker-1",
            pending_tool_run_ids=(queued_tool_run.id,),
            reason="tool_background_wait",
        )

        self.assertEqual(reconciled.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(reconciled.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(reconciled.pending_tool_run_ids, ())
        self.assertEqual(reconciled.queue_policy, OrchestrationQueuePolicy.RESUME_FIRST)

    def test_process_next_orchestration_assignment_heartbeats_dispatch_during_long_execution(self) -> None:
        custom_harness = SqliteTestHarness()
        custom_settings = replace(
            load_settings(),
            orchestration_run_lease_seconds=1,
            orchestration_run_heartbeat_seconds=0.05,
        )
        custom_harness.initialize_schema(settings=custom_settings)
        container = custom_harness.build_runtime_container(settings=custom_settings)
        try:
            adapter = _SlowStaticTextAdapter(
                text="slow llm response",
                delay_seconds=0.15,
            )
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).sync_profiles(
                (
                    RegisterLlmProfileInput(
                        id="openai.gpt-5.4-mini",
                        provider=LlmProviderKind.OPENAI,
                        api_family=LlmApiFamily.OPENAI_RESPONSES,
                        model_name="gpt-5.4-mini",
                        credential_binding_id=credential_binding_id,
                    ),
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-heartbeat-loop",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                    metadata={
                        "runtime_request_bootstrap_policy": {
                            "default_tool_schema_ids": ["background_echo"],
                        },
                    },
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
            self.assertIn(
                "dispatch.task.heartbeated",
                [
                    event.event_name
                    for event in published_event_bus_events(container)
                    if isinstance(event, Event) and bool(event.name)
                ],
            )
        finally:
            custom_harness.close()

    def test_process_next_orchestration_assignment_exposes_skill_tools_via_context_tree_surface(self) -> None:
        adapter = _StaticTextAdapter(text="hello with skill catalog")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Use this skill when reviewing repository changes.",
                instructions=(
                    "# Repo Review\n\nUse this skill when reviewing repository changes.\n"
                ),
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            with patch(
                "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_GLOBAL_SKILLS_DIR",
                root / "global",
            ), patch(
                "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_SYSTEM_SKILLS_DIR",
                root / "system",
            ):
                run = self.orchestration_intake_service.accept(
                    AcceptOrchestrationRunInput(
                        run_id="run-skill-catalog",
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
            system_messages = [
                message
                for message in adapter.requests[0].messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            _request_render_snapshot(adapter.requests[0])
            self.assertFalse(
                any("# Available Skills" in str(message.content) for message in system_messages),
            )
            context_workspace = self.container.require(
                AppKey.CONTEXT_WORKSPACE_SERVICE,
            ).get_by_session("agent:assistant:main")
            self.assertIn(
                "skill_read",
                context_workspace.metadata["available_tool_names"],
            )
            self.assertNotIn(
                "context_blocks",
                processed.metadata["runtime_request_report"],
            )

    def test_process_next_orchestration_assignment_uses_tool_descriptions_for_session_tools(self) -> None:
        adapter = _StaticTextAdapter(text="hello with session tools")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-session-tools-guidance",
                inbound_instruction=InboundInstruction(source="cli", content="continue the task"),
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
        self.assertEqual(
            processed.status,
            OrchestrationRunStatus.COMPLETED,
            processed.error.to_payload() if processed.error is not None else None,
        )
        system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertFalse(
            any("# Session Tools" in str(message.content) for message in system_messages),
        )
        self.assertFalse(
            any("# Available Tools" in str(message.content) for message in system_messages),
        )
        tool_schema_names = {schema.name for schema in adapter.requests[0].tool_schemas}
        self.assertIn("capability.search", tool_schema_names)
        self.assertNotIn("sessions_send", tool_schema_names)
        self.assertNotIn("sessions_spawn", tool_schema_names)
        self.assertNotIn("sessions_yield", tool_schema_names)
        _request_render_snapshot(adapter.requests[0])
        self.assertNotIn(
            "context_blocks",
            processed.metadata["runtime_request_report"],
        )

    def test_process_next_orchestration_assignment_can_use_skill_read_and_continue(self) -> None:
        adapter = _SkillReadingAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review changes carefully and cite concrete findings.",
                version="1",
                tags=("review", "repository"),
                allowed_tools=("memory_search",),
                instructions=(
                    "# Repo Review\n\n"
                    "Review changes carefully and cite concrete findings.\n"
                ),
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-read-skill",
                    inbound_instruction=InboundInstruction(source="cli", content="review the repo"),
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

            completed = process_next_orchestration_assignment(self.container,
                worker_id="worker-1",
            )
            for _ in range(3):
                if (
                    completed is not None
                    and completed.status is not OrchestrationRunStatus.RUNNING
                ):
                    break
                completed = process_next_orchestration_assignment(
                    self.container,
                    worker_id="worker-1",
                )

            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(completed.result_payload["output_text"], "used repo-review skill")
            self.assertEqual(len(adapter.requests), 3)
            skill_tool_messages = [
                message
                for message in adapter.requests[2].messages
                if message.role is LlmMessageRole.TOOL
                and message.name == "skill_read"
            ]
            self.assertEqual(len(skill_tool_messages), 1)
            _request_render_snapshot(adapter.requests[2])
            self.assertIn("SKILL.md", str(skill_tool_messages[0].content))
            self.assertIn("Repo Review", str(skill_tool_messages[0].content))
            session_items = self.session_service.list_items(
                ListSessionItemsInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            skill_results = [
                item
                for item in session_items
                if item.source_kind == "tool_run"
                and item.tool_name == "skill_read"
            ]
            self.assertEqual(len(skill_results), 1)
            self.assertEqual(skill_results[0].tool_name, "skill_read")
            self.assertIn(
                "# Repo Review",
                str(skill_results[0].content_payload.get("content")),
            )

    def test_skill_read_projects_normalized_requirements_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            skill_root = workspace / ".crxzipple" / "skills" / "repo-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review changes carefully.\n"
                "required_tools: [git_diff]\n"
                "suggested_tools: [git_diff, memory_search]\n"
                "required_effects: [workspace_read]\n"
                "required_access: [git-credential-binding]\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )

            handler = skill_read(
                SkillsToolDeps(
                    skill_manager=self.skill_manager,
                ),
            )
            self.assertIsNotNone(handler)
            assert handler is not None

            result = asyncio.run(
                handler(
                    {"skill": "repo-review"},
                    ToolExecutionContext(
                        attrs={
                            "workspace_dir": str(workspace),
                            "surface": "interactive",
                        },
                    ),
                ),
            )

            self.assertEqual(
                result.metadata["requirements"]["required_tools"],
                ["git_diff"],
            )
            self.assertEqual(
                result.metadata["requirements"]["suggested_tools"],
                ["git_diff", "memory_search"],
            )
            self.assertEqual(
                result.metadata["requirements"]["required_access"],
                ["git-credential-binding"],
            )
            self.assertIn("- Required effects: workspace_read", str(result.blocks))
            with self.assertRaisesRegex(
                ValueError,
                "not available in this orchestration run",
            ):
                asyncio.run(
                    handler(
                        {"skill": "repo-review"},
                        ToolExecutionContext(
                            attrs={
                                "workspace_dir": str(workspace),
                                "surface": "interactive",
                                "available_skill_names": ["other-skill"],
                            },
                        ),
                    ),
                )

    def test_prompt_assembly_resolves_skill_visibility_from_runtime_readiness(self) -> None:
        adapter = _StaticTextAdapter(text="skill visibility resolved")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            ready_skill = workspace / ".crxzipple" / "skills" / "ready-review"
            ready_skill.mkdir(parents=True)
            (ready_skill / "SKILL.md").write_text(
                "---\n"
                "name: ready-review\n"
                "description: Review with a ready local tool.\n"
                "required_tools: [ready_review_tool]\n"
                "---\n"
                "# Ready Review\n",
                encoding="utf-8",
            )
            blocked_skill = workspace / ".crxzipple" / "skills" / "blocked-review"
            blocked_skill.mkdir(parents=True)
            (blocked_skill / "SKILL.md").write_text(
                "---\n"
                "name: blocked-review\n"
                "description: Review with missing setup.\n"
                "required_tools: [missing_review_tool]\n"
                "required_access:\n"
                "  - provider: gmail\n"
                "    kind: oauth_connector\n"
                "    scopes: [mail_read]\n"
                "---\n"
                "# Blocked Review\n",
                encoding="utf-8",
            )
            ready_tool = self.seed_tool(
                tool_id="ready_review_tool",
                name="Ready Review Tool",
                description="Supports ready review skills.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="ready_review_tool",
            )

            async def ready_review_tool(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(str(arguments))

            self.local_runtime_registry.register(ready_tool, ready_review_tool)
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-resolve-skill-visibility",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="review with configured skills",
                    ),
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
            processed = process_next_orchestration_assignment(
                self.container,
                worker_id="worker-1",
            )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        _request_render_snapshot(adapter.requests[0])
        self.assertFalse(
            any("# Available Skills" in str(message.content) for message in system_messages),
        )
        context_workspace = self.container.require(
            AppKey.CONTEXT_WORKSPACE_SERVICE,
        ).get_by_session("agent:assistant:main")
        self.assertIn(
            "ready-review",
            context_workspace.metadata["available_skill_names"],
        )
        self.assertNotIn(
            "blocked-review",
            context_workspace.metadata["available_skill_names"],
        )
        resolution_event = next(
            event
            for event in self.published_event_bus_events()
            if event.event_name == "skills.resolution.completed"
            and event.payload.get("run_id") == "run-resolve-skill-visibility"
        )
        resolved_skills = resolution_event.payload["skills"]
        readiness_by_name = {
            item["skill"]: item["status"]
            for item in resolved_skills
        }
        self.assertEqual(readiness_by_name["ready-review"], "ready")
        self.assertEqual(readiness_by_name["blocked-review"], "setup_needed")
        blocked_readiness = next(
            item
            for item in resolved_skills
            if item["skill"] == "blocked-review"
        )
        self.assertEqual(blocked_readiness["missing_tools"], ["missing_review_tool"])
        self.assertEqual(
            blocked_readiness["missing_access"],
            ["gmail:oauth_connector(mail_read)"],
        )

    def test_prompt_assembly_reports_blocked_skills_when_none_are_ready(self) -> None:
        adapter = _StaticTextAdapter(text="no skills ready")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            blocked_memory_skill = workspace / ".crxzipple" / "skills" / "memory-recall"
            blocked_memory_skill.mkdir(parents=True)
            (blocked_memory_skill / "SKILL.md").write_text(
                "---\n"
                "name: memory-recall\n"
                "description: Recall memory through a missing memory tool.\n"
                "required_tools: [missing_memory_tool]\n"
                "---\n"
                "# Blocked Memory Recall\n",
                encoding="utf-8",
            )
            blocked_review_skill = workspace / ".crxzipple" / "skills" / "blocked-review"
            blocked_review_skill.mkdir(parents=True)
            (blocked_review_skill / "SKILL.md").write_text(
                "---\n"
                "name: blocked-review\n"
                "description: Review with a missing review tool.\n"
                "required_tools: [missing_review_tool]\n"
                "---\n"
                "# Blocked Review\n",
                encoding="utf-8",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-blocked-skills-observed",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="review with unavailable skills",
                    ),
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
            processed = process_next_orchestration_assignment(
                self.container,
                worker_id="worker-1",
            )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        _request_render_snapshot(adapter.requests[0])
        self.assertFalse(
            any("# Available Skills" in str(message.content) for message in system_messages),
        )
        context_workspace = self.container.require(
            AppKey.CONTEXT_WORKSPACE_SERVICE,
        ).get_by_session("agent:assistant:main")
        self.assertEqual(context_workspace.metadata["available_skill_names"], [])
        resolution_event = next(
            event
            for event in self.published_event_bus_events()
            if event.event_name == "skills.resolution.completed"
            and event.payload.get("run_id") == "run-blocked-skills-observed"
        )
        self.assertEqual(resolution_event.payload["ready_count"], 0)
        self.assertEqual(resolution_event.payload["setup_needed_count"], 2)
        resolved_skills = resolution_event.payload["skills"]
        readiness_by_name = {
            item["skill"]: item
            for item in resolved_skills
        }
        self.assertEqual(
            readiness_by_name["blocked-review"]["status"],
            "setup_needed",
        )
        self.assertEqual(
            readiness_by_name["blocked-review"]["missing_tools"],
            ["missing_review_tool"],
        )
        self.assertEqual(
            readiness_by_name["memory-recall"]["missing_tools"],
            ["missing_memory_tool"],
        )

    def test_process_next_orchestration_assignment_allows_skill_read_alongside_other_tools(self) -> None:
        adapter = _SkillReadAndEchoAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review changes carefully and cite concrete findings.",
                instructions=(
                    "# Repo Review\n\n"
                    "Review changes carefully and cite concrete findings.\n"
                ),
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )
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

            run = self.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-read-skill-and-echo",
                    inbound_instruction=InboundInstruction(source="cli", content="review the repo"),
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

            completed = process_next_orchestration_assignment(self.container,
                worker_id="worker-1",
            )

            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "used skill guidance without mode switch",
            )
            self.assertEqual(len(adapter.requests), 3)
            second_request_tool_names = [
                message.name
                for message in adapter.requests[2].messages
                if message.role is LlmMessageRole.TOOL
            ]
            self.assertIn("skill_read", second_request_tool_names)
            self.assertIn("echo", second_request_tool_names)

    def test_process_next_orchestration_assignment_can_read_multiple_skills_before_deciding(self) -> None:
        adapter = _MultiSkillReadAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review changes carefully and cite concrete findings.",
                instructions="# Repo Review\n\nReview changes carefully.\n",
            )
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "memory-recall",
                name="memory-recall",
                description="Recall durable memory before answering.",
                instructions="# Memory Recall\n\nUse durable memory.\n",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-read-multiple-skills",
                    inbound_instruction=InboundInstruction(source="cli", content="decide how to answer"),
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

            completed = process_next_orchestration_assignment(self.container,
                worker_id="worker-1",
            )

            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "compared multiple skills before deciding",
            )
            second_request_tool_names = [
                message.name
                for message in adapter.requests[2].messages
                if message.role is LlmMessageRole.TOOL
            ]
            self.assertEqual(second_request_tool_names.count("skill_read"), 2)

    def test_process_next_orchestration_assignment_completes_inline_tool_loop(self) -> None:
        adapter = _InlineToolLoopAdapter()
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
                metadata={
                    "artifact_ids": ["artifact-echo"],
                    "browser_target_id": "tab-echo",
                    "custom_untrusted": "not persisted",
                    "execution_context": {"large": "not persisted"},
                },
            )

        self.local_runtime_registry.register(tool, echo)

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-inline-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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
        self.assertEqual(processed.current_step, 4)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "tool loop complete")
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(len(adapter.requests), 4)
        first_schema_names = [schema.name for schema in adapter.requests[0].tool_schemas]
        self.assertIn("capability.search", first_schema_names)
        self.assertNotIn("echo", first_schema_names)
        second_schema_names = [schema.name for schema in adapter.requests[1].tool_schemas]
        self.assertIn("capability.search", second_schema_names)
        self.assertIn("echo", second_schema_names)
        third_schema_names = [schema.name for schema in adapter.requests[2].tool_schemas]
        self.assertIn("echo", third_schema_names)
        self.assertGreaterEqual(
            sum(
                1
                for item in adapter.requests[3].input_items
                if item.kind is LlmInputItemKind.MESSAGE
            ),
            1,
        )
        echo_messages = [
            message
            for message in adapter.requests[3].messages
            if message.tool_call_id == "call-echo-1"
        ]
        self.assertEqual(
            [message.role for message in echo_messages],
            [LlmMessageRole.ASSISTANT, LlmMessageRole.TOOL],
        )
        self.assertEqual(echo_messages[1].name, "echo")
        latest_invocation = self.llm_service.list_invocations(
            llm_id="openai.gpt-5.4-mini",
            limit=1,
        )[0]
        llm_items = self.orchestration_run_query_service.find_execution_step_items_by_owner(
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=latest_invocation.id,
            ),
        )
        self.assertEqual(len(llm_items), 1)

        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [(item.role, item.kind.value) for item in session_items],
            [
                ("user", "user_message"),
                ("assistant", "tool_call"),
                ("tool", "tool_result"),
                ("assistant", "tool_call"),
                ("tool", "tool_result"),
                ("assistant", "tool_call"),
                ("tool", "tool_result"),
                ("assistant", "assistant_message"),
            ],
        )
        self.assertEqual(session_items[1].call_id, "call-expand-echo")
        self.assertEqual(session_items[2].call_id, "call-expand-echo")
        self.assertEqual(session_items[3].call_id, "call-enable-echo")
        self.assertEqual(session_items[4].call_id, "call-enable-echo")
        self.assertEqual(session_items[5].call_id, "call-echo-1")
        self.assertEqual(session_items[6].call_id, "call-echo-1")
        echo_result_payload = session_items[6].content_payload
        self.assertEqual(
            echo_result_payload["metadata"],
            {
                "artifact_ids": ["artifact-echo"],
                "browser_target_id": "tab-echo",
            },
        )

    def test_response_items_tool_calls_drive_inline_tool_loop(self) -> None:
        adapter = _ResponseItemsInlineToolLoopAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Returns the input payload for response item tool call tests.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-response-items-inline-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        assert processed.result_payload is not None
        self.assertEqual(
            processed.result_payload["output_text"],
            "response item tool loop complete",
        )
        self.assertEqual(len(adapter.requests), 4)
        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        tool_call_ids = [
            item.call_id
            for item in session_items
            if item.call_id
        ]
        self.assertIn("item-call-search-echo", tool_call_ids)
        self.assertIn("item-call-enable-echo", tool_call_ids)
        self.assertIn("item-call-echo-1", tool_call_ids)
        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        session_user_items = [
            item
            for item in session_items
            if item.kind.value == "user_message"
        ]
        self.assertEqual(len(session_user_items), 1)
        self.assertEqual(session_user_items[0].source_module, "orchestration")
        self.assertEqual(session_user_items[0].source_kind, "orchestration_run")
        session_tool_call_items = [
            item
            for item in session_items
            if item.kind.value == "tool_call"
        ]
        session_item_call_ids = [item.call_id for item in session_tool_call_items]
        self.assertIn("item-call-search-echo", session_item_call_ids)
        self.assertIn("item-call-enable-echo", session_item_call_ids)
        self.assertIn("item-call-echo-1", session_item_call_ids)
        self.assertEqual(session_tool_call_items[0].source_module, "llm")
        self.assertEqual(session_tool_call_items[0].source_kind, "llm_response_item")
        self.assertEqual(session_tool_call_items[0].provider_item_id, "provider-item-call-search-echo")
        self.assertEqual(session_tool_call_items[0].tool_name, "capability.search")
        session_tool_result_items = [
            item
            for item in session_items
            if item.kind.value == "tool_result"
        ]
        session_result_call_ids = [item.call_id for item in session_tool_result_items]
        self.assertIn("item-call-search-echo", session_result_call_ids)
        self.assertIn("item-call-enable-echo", session_result_call_ids)
        self.assertIn("item-call-echo-1", session_result_call_ids)
        self.assertEqual(session_tool_result_items[0].source_module, "tool")
        self.assertEqual(session_tool_result_items[0].source_kind, "tool_run")
        invocations = self.llm_service.list_invocations(
            llm_id="openai.gpt-5.4-mini",
            limit=10,
        )
        second_invocation = next(
            invocation
            for invocation in invocations
            if invocation.response_items
            and invocation.response_items[0].call_id == "item-call-enable-echo"
        )
        first_invocation = next(
            invocation
            for invocation in invocations
            if invocation.response_items
            and invocation.response_items[0].call_id == "item-call-search-echo"
        )
        echo_invocation = next(
            invocation
            for invocation in invocations
            if invocation.response_items
            and invocation.response_items[0].call_id == "item-call-echo-1"
        )
        echo_tool_runs = self.tool_service.list_tool_runs(tool_id="echo")
        self.assertEqual(len(echo_tool_runs), 1)
        echo_tool_run = echo_tool_runs[0]
        self.assertEqual(echo_tool_run.call_id, "item-call-echo-1")
        self.assertEqual(
            echo_tool_run.tool_surface_id,
            echo_invocation.request_metadata["tool_surface_id"],
        )
        self.assertEqual(
            echo_tool_run.metadata["tool_surface_snapshot_id"],
            echo_invocation.request_metadata["tool_surface_snapshot_id"],
        )
        self.assertEqual(
            echo_tool_run.metadata["request_render_snapshot_id"],
            echo_invocation.request_metadata["request_render_snapshot_id"],
        )
        echo_llm_items = self.orchestration_run_query_service.find_execution_step_items_by_owner(
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=echo_invocation.id,
            ),
        )
        self.assertTrue(
            any(item.kind.value == "llm_invocation" for item in echo_llm_items),
        )
        echo_tool_run_items = self.orchestration_run_query_service.find_execution_step_items_by_owner(
            ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id=echo_tool_run.id,
            ),
        )
        self.assertTrue(
            any(item.kind.value in {"tool_run", "tool_result"} for item in echo_tool_run_items),
        )
        echo_tool_result_item = next(
            item
            for item in session_tool_result_items
            if item.call_id == "item-call-echo-1"
        )
        echo_session_owner_items = self.orchestration_run_query_service.find_execution_step_items_by_owner(
            ExecutionOwnerReference(
                owner_kind="session_item",
                owner_id=echo_tool_result_item.id,
            ),
        )
        self.assertTrue(
            any(item.kind.value == "tool_result" for item in echo_session_owner_items),
        )
        final_request_output_call_ids = [
            item.payload.get("call_id")
            for item in adapter.requests[-1].input_items
            if item.kind is LlmInputItemKind.FUNCTION_CALL_OUTPUT
        ]
        self.assertIn("item-call-echo-1", final_request_output_call_ids)
        self.assertEqual(
            first_invocation.response_items[0].kind,
            LlmResponseItemKind.TOOL_CALL,
        )
        assert first_invocation.result is not None
        self.assertEqual(len(first_invocation.result.tool_calls), 1)
        self.assertEqual(
            first_invocation.result.tool_calls[0].name,
            "capability.search",
        )

    def test_provider_external_response_item_does_not_create_tool_run(self) -> None:
        adapter = _ProviderExternalOnlyAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-provider-external-item",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="search the web",
                ),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(self.tool_service.list_tool_runs(), [])
        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        provider_items = [
            item
            for item in session_items
            if item.kind.value == "provider_external_activity"
        ]
        self.assertEqual(len(provider_items), 1)
        self.assertEqual(provider_items[0].source_module, "llm")
        self.assertEqual(provider_items[0].source_kind, "llm_response_item")
        self.assertEqual(provider_items[0].provider_item_id, "provider-search-item-1")
        self.assertEqual(provider_items[0].tool_name, "web_search")

    def test_final_answer_response_item_with_no_pending_work_completes_run(self) -> None:
        adapter = _FinalAnswerResponseItemAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-final-answer-response-item",
                inbound_instruction=InboundInstruction(source="cli", content="answer"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(
            processed.status,
            OrchestrationRunStatus.COMPLETED,
            processed.error.to_payload() if processed.error is not None else None,
        )
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(len(adapter.requests), 1)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "final item answer")
        self.assertEqual(self.tool_service.list_tool_runs(), [])
        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        final_items = [
            item
            for item in session_items
            if item.kind.value == "assistant_message"
            and item.phase is not None
            and item.phase.value == "final_answer"
        ]
        self.assertEqual(len(final_items), 1)
        self.assertEqual(final_items[0].source_module, "llm")
        self.assertEqual(final_items[0].source_kind, "llm_response_item")
        self.assertEqual(final_items[0].provider_item_id, "provider-final-item-1")

    def test_commentary_only_response_item_fails_with_loop_diagnostic(self) -> None:
        adapter = _CommentaryOnlyResponseItemAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-commentary-only-response-item",
                inbound_instruction=InboundInstruction(source="cli", content="continue"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertIsNotNone(processed.error)
        assert processed.error is not None
        self.assertEqual(
            processed.error.code,
            "llm_incomplete_terminal_response",
        )
        self.assertEqual(len(adapter.requests), 1)
        details = processed.error.details
        self.assertEqual(
            details["diagnostic"]["reason"],
            "commentary_or_reasoning_without_final_answer_or_follow_up",
        )
        self.assertEqual(
            details["execution_payload"]["llm_loop_diagnostic"]["code"],
            "llm_incomplete_terminal_response",
        )
        llm_invocation_id = adapter.requests[0].invocation_id
        llm_invocation_items = (
            self.orchestration_run_query_service.find_execution_step_items_by_owner(
                ExecutionOwnerReference(
                    owner_kind="llm_invocation",
                    owner_id=llm_invocation_id,
                ),
            )
        )
        self.assertEqual(len(llm_invocation_items), 1)
        self.assertEqual(llm_invocation_items[0].status.value, "failed")
        assert llm_invocation_items[0].summary_payload is not None
        self.assertEqual(
            llm_invocation_items[0].summary_payload["llm_loop_diagnostic"]["code"],
            "llm_incomplete_terminal_response",
        )
        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        commentary_items = [
            item
            for item in session_items
            if item.kind.value == "assistant_message"
            and item.phase.value == "commentary"
        ]
        self.assertEqual(len(commentary_items), 1)
        self.assertEqual(commentary_items[0].source_module, "llm")
        self.assertEqual(commentary_items[0].source_kind, "llm_response_item")

    def test_provider_continuation_without_tool_calls_keeps_loop_open(self) -> None:
        adapter = _ContinuationFollowupAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-provider-continuation-followup",
                inbound_instruction=InboundInstruction(source="cli", content="continue"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        assert processed.result_payload is not None
        self.assertEqual(len(adapter.requests), 2)
        self.assertEqual(
            processed.result_payload["output_text"],
            "final answer after provider continuation",
        )
        invocations = self.llm_service.list_invocations(
            llm_id="openai.gpt-5.4-mini",
            limit=10,
        )
        continuation_invocation = next(
            invocation
            for invocation in invocations
            if invocation.result is not None
            and invocation.result.text == "still thinking"
        )
        self.assertIsNotNone(continuation_invocation.continuation)
        assert continuation_invocation.continuation is not None
        self.assertEqual(
            continuation_invocation.continuation.reason,
            LlmContinuationReason.PROVIDER_END_TURN_FALSE,
        )
        self.assertTrue(continuation_invocation.continuation.needs_follow_up)

    def test_provider_native_tool_result_continuation_uses_previous_response_delta(
        self,
    ) -> None:
        adapter = _ProviderNativeToolContinuationAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-provider-native-tool-delta",
                inbound_instruction=InboundInstruction(source="cli", content="echo"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "provider native final")
        self.assertGreaterEqual(len(adapter.requests), 2)
        first_request = adapter.requests[0]
        second_request = adapter.requests[1]
        self.assertIsNone(first_request.continuation)
        self.assertIsNotNone(second_request.continuation)
        assert second_request.continuation is not None
        self.assertEqual(
            second_request.continuation.previous_response_id,
            "resp_first",
        )
        self.assertIn(
            LlmInputItemKind.FUNCTION_CALL_OUTPUT,
            [item.kind for item in second_request.input_items],
        )
        _request_render_snapshot(second_request)
        tool_messages = [
            message
            for message in second_request.messages
            if message.role == LlmMessageRole.TOOL
        ]
        self.assertEqual(tool_messages[0].tool_call_id, "call-provider-native-search")

        invocations = self.llm_service.list_invocations(
            llm_id="openai.gpt-5.4-mini",
            limit=10,
        )
        continuation_invocation = next(
            invocation
            for invocation in invocations
            if invocation.provider_request_id == "resp_second"
        )
        preview = continuation_invocation.provider_request_payload_preview
        assert isinstance(preview, dict)
        self.assertTrue(preview["has_previous_response_id"])
        self.assertEqual(preview["previous_response_id"], "resp_first")
        self.assertEqual(preview["input_item_types"], ["function_call_output"])
        self.assertEqual(second_request.continuation.transport, "http")
        self.assertEqual(
            preview["payload_preview"]["input"][0]["call_id"],
            "call-provider-native-search",
        )

    def test_provider_continuation_unsupported_api_replays_tool_result_history(
        self,
    ) -> None:
        adapter = _ProviderContinuationUnsupportedToolAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            adapter,
        )
        credential_binding_id = self._install_default_llm_access_binding(self.container)
        self.llm_service.sync_profiles(
            (
                RegisterLlmProfileInput(
                    id="openai.chat-compatible",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
                    model_name="gpt-5.4-mini-chat",
                    credential_binding_id=credential_binding_id,
                ),
            ),
        )
        self.agent_service.sync_profiles(
            (
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.chat-compatible",
                    ),
                ),
            ),
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-provider-continuation-fallback",
                inbound_instruction=InboundInstruction(source="cli", content="echo"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertGreaterEqual(len(adapter.requests), 2)
        second_request = adapter.requests[1]
        self.assertIsNone(second_request.continuation)
        tool_messages = [
            message
            for message in second_request.messages
            if message.role == LlmMessageRole.TOOL
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "call-unsupported-search")
        invocations = self.llm_service.list_invocations(
            llm_id="openai.chat-compatible",
            limit=10,
        )
        provider_request_ids = {
            invocation.provider_request_id for invocation in invocations
        }
        self.assertIn("chat-first", provider_request_ids)
        self.assertIn("chat-second", provider_request_ids)

    def test_provider_continuation_support_is_resolved_from_llm_profile(
        self,
    ) -> None:
        continuation = LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
        )

        def filtered_continuation(
            *,
            api_family: LlmApiFamily,
            capabilities: tuple[LlmCapability, ...],
            provider_options: dict[str, object] | None = None,
            provider: LlmProviderKind = LlmProviderKind.OPENAI,
        ) -> LlmProviderContinuation | None:
            test_case = self
            profile = LlmProfile(
                id="llm.continuation-test",
                provider=provider,
                api_family=api_family,
                model_name="model",
                capabilities=capabilities,
            )

            class _Port:
                def get_profile(self, llm_id: str) -> LlmProfile:
                    test_case.assertEqual(llm_id, "llm.continuation-test")
                    return profile

            invoker = OrchestrationEngineLlmInvoker(llm_port=_Port())
            return invoker.provider_continuation(
                request_envelope=RuntimeLlmRequest(
                    llm_id="llm.continuation-test",
                    session_key="session",
                    active_session_id="session",
                    messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
                    tool_schemas=(),
                    request_render_snapshot=RuntimeLlmRequestRenderSnapshot(),
                    tool_surface=RuntimeToolSurface(id="surface"),
                    provider_options=dict(provider_options or {}),
                ),
                continuation=continuation,
            )

        self.assertIsNotNone(
            filtered_continuation(
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                capabilities=(LlmCapability.PROVIDER_NATIVE_CONTINUATION,),
            ),
        )
        self.assertIsNone(
            filtered_continuation(
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                provider=LlmProviderKind.OPENAI_CODEX,
                provider_options={"provider_transport": "http"},
                capabilities=(
                    LlmCapability.PROVIDER_NATIVE_CONTINUATION,
                    LlmCapability.PROVIDER_WEBSOCKET_TRANSPORT,
                    LlmCapability.PROVIDER_INCREMENTAL_INPUT,
                ),
            ),
        )
        self.assertIsNone(
            filtered_continuation(
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                provider=LlmProviderKind.OPENAI_CODEX,
                provider_options={"provider_transport": "websocket"},
                capabilities=(
                    LlmCapability.PROVIDER_NATIVE_CONTINUATION,
                    LlmCapability.PROVIDER_WEBSOCKET_TRANSPORT,
                    LlmCapability.PROVIDER_INCREMENTAL_INPUT,
                ),
            ),
        )
        self.assertIsNone(
            filtered_continuation(
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                provider=LlmProviderKind.OPENAI_CODEX,
                provider_options={"provider_transport": "websocket"},
                capabilities=(LlmCapability.PROVIDER_NATIVE_CONTINUATION,),
            ),
        )

    def test_codex_websocket_replays_full_history_without_provider_native_continuation(
        self,
    ) -> None:
        adapter = _CodexWebSocketProviderNativeToolContinuationAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_CODEX_RESPONSES,
            adapter,
        )
        credential_binding_id = "codex-oauth-default"
        existing_view = getattr(self.access_service, "config_view", None)
        self.access_service.config_view = _TestAccessConfigView(
            {
                credential_binding_id: AccessCredentialBindingRecord(
                    binding_id=credential_binding_id,
                    asset_id=None,
                    binding_kind="oauth2_account",
                    source_kind="oauth_account",
                    source_ref="openai-codex:default",
                    masked_preview="oauth:openai-codex:default",
                    metadata={"test_fixture": "orchestration"},
                ),
            },
            fallback=existing_view,
        )
        token_storage_key = "oauth_tokens/codex-websocket-test.json"
        self.container.require(AppKey.ACCESS_OAUTH_TOKEN_STORE).write_token(
            token_storage_key,
            OAuthTokenDocument(
                access_token="codex-access-token",
                refresh_token="codex-refresh-token",
            ),
        )
        self.container.require(AppKey.ACCESS_GOVERNANCE_REPOSITORY).upsert_oauth_account(
            AccessOAuthAccountRecord(
                account_id="openai-codex:default",
                provider_id="openai-codex",
                credential_binding_id=credential_binding_id,
                storage_key=token_storage_key,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                refresh_ready=True,
            ),
        )
        self.llm_service.sync_profiles(
            (
                RegisterLlmProfileInput(
                    id="codex.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI_CODEX,
                    api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                    model_name="gpt-5.4-mini",
                    capabilities=(
                        LlmCapability.PROVIDER_NATIVE_CONTINUATION,
                        LlmCapability.PROVIDER_WEBSOCKET_TRANSPORT,
                        LlmCapability.PROVIDER_INCREMENTAL_INPUT,
                    ),
                    default_params=LlmDefaults(provider_transport="websocket"),
                    credential_binding_id=credential_binding_id,
                ),
            ),
        )
        self.agent_service.sync_profiles(
            (
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="codex.gpt-5.4-mini",
                    ),
                ),
            ),
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-codex-websocket-provider-native-tool-delta",
                inbound_instruction=InboundInstruction(source="cli", content="echo"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertGreaterEqual(len(adapter.requests), 2)
        second_request = adapter.requests[1]
        self.assertIsNone(second_request.continuation)

        invocations = self.llm_service.list_invocations(
            llm_id="codex.gpt-5.4-mini",
            limit=10,
        )
        continuation_invocation = next(
            invocation
            for invocation in invocations
            if invocation.provider_request_id == "resp_second"
        )
        preview = continuation_invocation.provider_request_payload_preview
        assert isinstance(preview, dict)
        self.assertEqual(preview["api_family"], LlmApiFamily.OPENAI_CODEX_RESPONSES)
        self.assertEqual(preview["transport"], "websocket")
        self.assertFalse(preview["has_previous_response_id"])
        self.assertIsNone(preview["previous_response_id"])
        self.assertFalse(preview["input_delta_mode"])
        payload_preview = preview["payload_preview"]
        assert isinstance(payload_preview, dict)
        self.assertNotIn("previous_response_id", payload_preview)
        input_items = payload_preview["input"]
        assert isinstance(input_items, list)
        self.assertGreaterEqual(len(input_items), 2)
        self.assertEqual(input_items[-1].get("role"), "user")
        runtime_context = input_items[-1].get("content")
        assert isinstance(runtime_context, list)
        runtime_context_text = runtime_context[0].get("text")
        assert isinstance(runtime_context_text, str)
        self.assertIn("# Runtime Context", runtime_context_text)

    def test_provider_native_tool_surface_updates_after_schema_enable(
        self,
    ) -> None:
        adapter = _ProviderNativeRuntimeToolSurfaceUpdateAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Returns the input payload for provider surface tests.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(str(arguments.get("message") or ""))

        self.local_runtime_registry.register(tool, echo)

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-provider-native-tool-surface-update",
                inbound_instruction=InboundInstruction(source="cli", content="echo"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(len(adapter.requests), 3)
        first_schema_names = [schema.name for schema in adapter.requests[0].tool_schemas]
        self.assertIn("capability.search", first_schema_names)
        self.assertNotIn("echo", first_schema_names)
        second_schema_names = [schema.name for schema in adapter.requests[1].tool_schemas]
        self.assertIn("echo", second_schema_names)
        second_request = adapter.requests[1]
        self.assertIsNotNone(second_request.continuation)
        assert second_request.continuation is not None
        self.assertEqual(
            second_request.continuation.previous_response_id,
            "resp-surface-1",
        )
        context_messages = [
            message
            for message in second_request.messages
            if message.metadata.get("runtime_request_block_kind") == "context_workspace"
        ]
        self.assertEqual(context_messages, [])
        _request_render_snapshot(second_request)
        third_request = adapter.requests[2]
        third_schema_names = [schema.name for schema in third_request.tool_schemas]
        self.assertIn("echo", third_schema_names)
        self.assertIsNotNone(third_request.continuation)
        assert third_request.continuation is not None
        self.assertEqual(
            third_request.continuation.previous_response_id,
            "resp-surface-2",
        )

    def test_text_with_tool_calls_records_assistant_progress_for_next_runtime_request(self) -> None:
        adapter = _SequentialResultAdapter(
            LlmResult(
                tool_calls=(
                    _expand_tool_bundle_call(
                        call_id="call-expand-echo",
                        source_id="test.local_package.echo",
                    ),
                ),
            ),
            LlmResult(
                tool_calls=(
                    _enable_tool_schema_call(
                        call_id="call-enable-echo",
                        tool_id="echo",
                    ),
                ),
            ),
            LlmResult(
                text="我先检查页面状态。",
                tool_calls=(
                    ToolCallIntent(
                        id="call-echo-progress",
                        name="echo",
                        arguments={"message": "progress-visible"},
                    ),
                ),
            ),
            "tool loop complete",
        )
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
            return ToolRunResult.text(str(arguments.get("message") or ""))

        self.local_runtime_registry.register(tool, echo)

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-text-tool-progress-session",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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

        processed = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(len(adapter.requests), 4)

        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        progress_items = [
            item
            for item in session_items
            if item.role == "assistant"
            and item.metadata.get("runtime_semantic_kind") == "runtime.assistant_progress"
            and item.content_payload.get("text") == "我先检查页面状态。"
        ]
        self.assertEqual(len(progress_items), 1)
        function_call_items = [
            item
            for item in session_items
            if item.role == "assistant"
            and item.kind.value == "tool_call"
            and item.call_id == "call-echo-progress"
        ]
        self.assertEqual(len(function_call_items), 1)
        progress_execution_items = self.orchestration_run_query_service.find_execution_step_items_by_owner(
            ExecutionOwnerReference(
                owner_kind="session_item",
                owner_id=progress_items[0].id,
            ),
        )
        self.assertEqual(len(progress_execution_items), 1)
        self.assertEqual(
            progress_execution_items[0].summary_payload["assistant_progress_item_ids"],
            [progress_items[0].id],
        )
        function_call_execution_items = self.orchestration_run_query_service.find_execution_step_items_by_owner(
            ExecutionOwnerReference(
                owner_kind="session_item",
                owner_id=function_call_items[0].id,
            ),
        )
        self.assertEqual(function_call_execution_items, [])
        diagnostic_events = [
            event
            for event in self.published_event_bus_events()
            if event.name == "orchestration.execution.llm_step_completed"
            and progress_items[0].id in event.payload.get("session_item_ids", [])
        ]
        self.assertEqual(len(diagnostic_events), 1)
        self.assertIn(function_call_items[0].id, diagnostic_events[0].payload["session_item_ids"])

        final_request_content = [
            message.content for message in adapter.requests[3].messages
        ]
        self.assertIn("我先检查页面状态。", str(final_request_content))
        self.assertTrue(_has_tool_call_message(adapter.requests[3], "echo"))

    def test_process_next_orchestration_assignment_executes_multiple_inline_tool_calls_concurrently(self) -> None:
        adapter = _SequentialResultAdapter(
            LlmResult(
                tool_calls=(
                    _expand_tool_bundle_call(
                        call_id="call-expand-echo",
                        source_id="test.local_package.echo",
                    ),
                ),
            ),
            LlmResult(
                tool_calls=(
                    _enable_tool_schema_call(
                        call_id="call-enable-echo",
                        tool_id="echo",
                    ),
                ),
            ),
            LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-echo-parallel-1",
                        name="echo",
                        arguments={"message": "first"},
                    ),
                    ToolCallIntent(
                        id="call-echo-parallel-2",
                        name="echo",
                        arguments={"message": "second"},
                    ),
                ),
            ),
            "parallel tool loop complete",
        )
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
        entered: list[str] = []
        entered_lock = threading.Lock()
        both_entered = threading.Event()

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            with entered_lock:
                entered.append(str(arguments.get("message") or ""))
                if len(entered) == 2:
                    both_entered.set()
            if not await asyncio.to_thread(both_entered.wait, 1.0):
                raise AssertionError(
                    "expected inline tool calls to be in flight concurrently",
                )
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-parallel-inline-tools",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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
        self.assertCountEqual(entered, ["first", "second"])
        self.assertEqual(len(adapter.requests), 4)
        tool_messages = [
            message
            for message in adapter.requests[3].messages
            if message.role is LlmMessageRole.TOOL and message.name == "echo"
        ]
        self.assertEqual(
            [message.tool_call_id for message in tool_messages],
            ["call-echo-parallel-1", "call-echo-parallel-2"],
        )

    def test_tool_execution_reuses_run_context_for_batch_decisions(self) -> None:
        self._register_agent_and_llm()
        tool = self.seed_tool(
            tool_id="context_echo",
            name="Context Echo",
            description="Returns whether execution context was attached.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="context_echo",
        )

        async def context_echo(
            arguments: dict[str, object],
            execution_context: object | None = None,
        ) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={
                    "has_context": execution_context is not None,
                },
            )

        self.local_runtime_registry.register(tool, context_echo)
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-batch-context",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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
        bound_run = self.orchestration_run_query_service.get_run(run.id)
        resolved_tools = ResolvedToolSet(
            tools=(
                ResolvedTool(
                    tool=tool,
                    schema=ToolSchema(
                        name="context_echo",
                        description="Returns whether execution context was attached.",
                    ),
                    target=ToolExecutionTarget(mode=ToolMode.INLINE),
                ),
            ),
        )
        call_count = 0

        def run_context_provider(_run: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {
                "available_scopes": ["session_context"],
                "session_key": "agent:assistant:main",
            }

        tool_resolver = (
            self.orchestration_inspection_service.engine.tool_resolver
        )
        tool_resolver.run_context_provider = run_context_provider

        outcome = asyncio.run(
            self.orchestration_inspection_service.engine.tool_executor.execute_tool_calls_async(
                bound_run,
                session_key="agent:assistant:main",
                active_session_id=bound_run.active_session_id or "",
                resolved_tools=resolved_tools,
                tool_calls=(
                    ToolCallIntent(
                        id="call-context-1",
                        name="context_echo",
                        arguments={"message": "first"},
                    ),
                    ToolCallIntent(
                        id="call-context-2",
                        name="context_echo",
                        arguments={"message": "second"},
                    ),
                ),
                append_tool_call_messages=False,
                append_tool_result_messages=False,
                require_running_run=False,
                extra_context_attrs={
                    "tool_surface_id": "tool_surface:batch-context",
                    "tool_surface_functions": [
                        {
                            "tool_id": "context_echo",
                            "name": "context_echo",
                        },
                    ],
                },
            ),
        )

        self.assertEqual(len(outcome.inline_runs), 2)
        self.assertEqual(len(outcome.tool_execution_plans), 2)
        self.assertEqual(
            [plan.tool_call_id for plan in outcome.tool_execution_plans],
            ["call-context-1", "call-context-2"],
        )
        self.assertEqual(
            outcome.tool_execution_plans[0].tool_id,
            "context_echo",
        )
        self.assertEqual(
            outcome.tool_execution_plans[0].mode,
            "inline",
        )
        self.assertEqual(
            outcome.tool_execution_plans[0].tool_surface_id,
            "tool_surface:batch-context",
        )
        self.assertIn(
            "arguments_digest",
            outcome.tool_execution_plans[0].to_payload(),
        )
        self.assertEqual(
            outcome.tool_run_links[0].tool_execution_plan["tool_call_id"],
            "call-context-1",
        )
        self.assertEqual(
            outcome.tool_run_links[0].tool_execution_plan["tool_surface_id"],
            "tool_surface:batch-context",
        )
        self.assertEqual(
            outcome.inline_runs[0].metadata["tool_execution_plan"]["tool_call_id"],
            "call-context-1",
        )
        self.assertEqual(outcome.inline_runs[0].call_id, "call-context-1")
        self.assertEqual(outcome.inline_runs[1].call_id, "call-context-2")
        self.assertEqual(call_count, 1)
        self.assertTrue(
            all(
                tool_run.output_payload["has_context"]
                for tool_run in outcome.inline_runs
            ),
        )

    def test_tool_execution_rejects_call_outside_request_tool_surface(self) -> None:
        self._register_agent_and_llm()
        tool = self.seed_tool(
            tool_id="surface_visible_tool",
            name="Surface Visible Tool",
            description="A tool that is available in resolved tools.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="surface_visible_tool",
        )
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-surface-gate",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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
        bound_run = self.orchestration_run_query_service.get_run(run.id)
        resolved_tools = ResolvedToolSet(
            tools=(
                ResolvedTool(
                    tool=tool,
                    schema=ToolSchema(name="surface.visible"),
                    target=ToolExecutionTarget(mode=ToolMode.INLINE),
                ),
            ),
        )

        with self.assertRaises(OrchestrationValidationError) as raised:
            asyncio.run(
                self.orchestration_inspection_service.engine.tool_executor.execute_tool_calls_async(
                    bound_run,
                    session_key="agent:assistant:main",
                    active_session_id=bound_run.active_session_id or "",
                    resolved_tools=resolved_tools,
                    tool_calls=(
                        ToolCallIntent(
                            id="call-hidden-surface-tool",
                            name="surface.visible",
                            arguments={},
                        ),
                    ),
                    append_tool_call_messages=False,
                    append_tool_result_messages=False,
                    require_running_run=False,
                    extra_context_attrs={
                        "tool_surface_id": "tool_surface:request-1",
                        "tool_surface_functions": [
                            {
                                "tool_id": "other_tool",
                                "name": "surface.other",
                            },
                        ],
                    },
                ),
            )

        self.assertEqual(raised.exception.code, "tool_surface_not_visible")
        self.assertEqual(
            raised.exception.details["tool_surface_id"],
            "tool_surface:request-1",
        )
        self.assertEqual(
            raised.exception.details["visible_tool_names"],
            ["surface.other"],
        )

    def test_tool_result_session_item_uses_result_envelope_payload(self) -> None:
        self._register_agent_and_llm()
        tool = self.seed_tool(
            tool_id="enveloped_result_tool",
            name="Enveloped Result Tool",
            description="Returns a tool result envelope.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="enveloped_result_tool",
        )

        async def enveloped_result(_arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                "raw result should not be the provider replay body",
                metadata={
                    TOOL_RESULT_ENVELOPE_METADATA_KEY: {
                        "status": "completed",
                        "summary": "Envelope summary for model replay.",
                        "tool_run_id": "will-be-overwritten-by-tool-run",
                        "call_id": "call-envelope-1",
                        "tool_name": "enveloped.result",
                        "artifact_refs": [
                            {"artifact_id": "artifact-envelope-1"},
                        ],
                        "provider_replay_payload": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "model-visible envelope body",
                                },
                            ],
                            "details": {"compact": True},
                        },
                        "user_summary_payload": {
                            "summary": "User summary envelope.",
                        },
                        "trace_payload": {
                            "duration_ms": 12,
                        },
                    },
                },
            )

        self.local_runtime_registry.register(tool, enveloped_result)
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-result-envelope-session-item",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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
        bound_run = self.orchestration_run_query_service.get_run(run.id)
        resolved_tools = ResolvedToolSet(
            tools=(
                ResolvedTool(
                    tool=tool,
                    schema=ToolSchema(name="enveloped.result"),
                    target=ToolExecutionTarget(mode=ToolMode.INLINE),
                ),
            ),
        )

        outcome = asyncio.run(
            self.orchestration_inspection_service.engine.tool_executor.execute_tool_calls_async(
                bound_run,
                session_key="agent:assistant:main",
                active_session_id=bound_run.active_session_id or "",
                resolved_tools=resolved_tools,
                tool_calls=(
                    ToolCallIntent(
                        id="call-envelope-1",
                        name="enveloped.result",
                        arguments={},
                    ),
                ),
                append_tool_call_messages=False,
                append_tool_result_messages=True,
                require_running_run=False,
                extra_context_attrs={
                    "tool_surface_id": "tool_surface:envelope",
                    "tool_surface_functions": [
                        {
                            "tool_id": "enveloped_result_tool",
                            "name": "enveloped.result",
                        },
                    ],
                },
            ),
        )

        self.assertEqual(len(outcome.inline_runs), 1)
        tool_run = outcome.inline_runs[0]
        self.assertIsNotNone(tool_run.result_envelope_payload)
        self.assertEqual(
            tool_run.result_envelope_payload["schema_version"],
            TOOL_RESULT_ENVELOPE_SCHEMA_VERSION,
        )
        self.assertEqual(len(outcome.tool_run_links), 1)
        self.assertEqual(outcome.tool_run_links[0].tool_name, "enveloped.result")
        self.assertEqual(outcome.tool_run_links[0].tool_run_id, tool_run.id)
        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        tool_result_items = [
            item
            for item in session_items
            if item.kind.value == "tool_result"
        ]
        self.assertEqual(len(tool_result_items), 1)
        payload = tool_result_items[0].content_payload
        self.assertEqual(
            payload["content"],
            [{"type": "text", "text": "model-visible envelope body"}],
        )
        self.assertEqual(payload["details"], {"compact": True})
        self.assertEqual(payload["trace"], {"duration_ms": 12})
        self.assertEqual(
            payload["user_summary"],
            {"summary": "User summary envelope."},
        )
        self.assertEqual(
            payload["metadata"]["artifact_ids"],
            ["artifact-envelope-1"],
        )
        self.assertEqual(
            payload["metadata"][TOOL_RESULT_ENVELOPE_METADATA_KEY]["summary"],
            "Envelope summary for model replay.",
        )
        self.assertEqual(
            payload["metadata"][TOOL_RESULT_ENVELOPE_METADATA_KEY]["tool_run_id"],
            tool_run.id,
        )
        self.assertEqual(
            payload["metadata"][TOOL_RESULT_ENVELOPE_METADATA_KEY]["call_id"],
            "call-envelope-1",
        )
        self.assertEqual(
            payload["metadata"][TOOL_RESULT_ENVELOPE_METADATA_KEY]["tool_name"],
            "enveloped.result",
        )

    def test_failed_tool_result_session_item_includes_model_recovery_guidance(self) -> None:
        self._register_agent_and_llm()
        tool = self.seed_tool(
            tool_id="failing_arg_tool",
            name="Failing Arg Tool",
            description="Fails on invalid arguments.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="failing_arg_tool",
        )

        async def failing_result(_arguments: dict[str, object]) -> ToolRunResult:
            raise RuntimeError("payload.expression is required.")

        self.local_runtime_registry.register(tool, failing_result)
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-failed-tool-result-guidance",
                inbound_instruction=InboundInstruction(source="cli", content="inspect"),
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
        bound_run = self.orchestration_run_query_service.get_run(run.id)
        resolved_tools = ResolvedToolSet(
            tools=(
                ResolvedTool(
                    tool=tool,
                    schema=ToolSchema(name="failing.arg"),
                    target=ToolExecutionTarget(mode=ToolMode.INLINE),
                ),
            ),
        )

        outcome = asyncio.run(
            self.orchestration_inspection_service.engine.tool_executor.execute_tool_calls_async(
                bound_run,
                session_key="agent:assistant:main",
                active_session_id=bound_run.active_session_id or "",
                resolved_tools=resolved_tools,
                tool_calls=(
                    ToolCallIntent(
                        id="call-failing-arg-1",
                        name="failing.arg",
                        arguments={"script": "() => document.title"},
                    ),
                ),
                append_tool_call_messages=False,
                append_tool_result_messages=True,
                require_running_run=False,
                extra_context_attrs={
                    "tool_surface_id": "tool_surface:failing-arg",
                    "tool_surface_functions": [
                        {
                            "tool_id": "failing_arg_tool",
                            "name": "failing.arg",
                        },
                    ],
                },
            ),
        )

        self.assertEqual(len(outcome.inline_runs), 1)
        self.assertEqual(outcome.inline_runs[0].status.value, "failed")
        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        tool_result_items = [
            item
            for item in session_items
            if item.kind.value == "tool_result"
        ]
        self.assertEqual(len(tool_result_items), 1)
        text = tool_result_items[0].content_payload["content"][0]["text"]
        self.assertIn("payload.expression is required.", text)
        self.assertIn("Do not repeat the same failing tool call unchanged", text)

    def test_process_next_orchestration_assignment_waits_when_tool_is_background(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                _BackgroundToolAdapter(),
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, background_echo)
            AuthorizationServiceAdapter(
                container.require(AppKey.AUTHORIZATION_SERVICE),
            ).grant_agent_effect_authorization(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-tool",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                    metadata={
                        "runtime_request_bootstrap_policy": {
                            "default_tool_schema_ids": ["background_echo"],
                        },
                    },
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(processed.stage, OrchestrationRunStage.WAITING_ON_TOOL)
            self.assertEqual(processed.current_step, 1)
            self.assertEqual(processed.waiting_reason, "tool_background_wait")
            self.assertEqual(len(processed.pending_tool_run_ids), 1)

            tool_run = container.require(AppKey.TOOL_SERVICE).get_tool_run(
                processed.pending_tool_run_ids[0],
            )
            self.assertEqual(tool_run.status, ToolRunStatus.QUEUED)

            session_items = container.require(AppKey.SESSION_SERVICE).list_items(
                ListSessionItemsInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            self.assertEqual(
                [(item.role, item.kind.value) for item in session_items],
                [
                    ("user", "user_message"),
                    ("assistant", "tool_call"),
                ],
            )
            self.assertEqual(session_items[1].call_id, "call-bg-1")
        finally:
            custom_harness.close()

    def test_background_tool_execution_receives_orchestration_context(self) -> None:
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        Path(workspace_dir.name, "README.md").write_text(
            "# Workspace\n\nbackground context\n",
            encoding="utf-8",
        )
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _BackgroundToolAdapter()
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                    runtime_preferences=AgentRuntimePreferences(
                        workspace=workspace_dir.name,
                    ),
                ),
            )

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(
                arguments: dict[str, object],
                execution_context=None,
            ) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={
                        "message": arguments.get("message"),
                        "execution_context": (
                            execution_context.to_payload() if execution_context is not None else None
                        ),
                    },
                )

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, background_echo)
            AuthorizationServiceAdapter(
                container.require(AppKey.AUTHORIZATION_SERVICE),
            ).grant_agent_effect_authorization(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-context",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                    metadata={
                        "runtime_request_bootstrap_policy": {
                            "default_tool_schema_ids": ["background_echo"],
                        },
                    },
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )

            self.assertIsNotNone(waiting)
            assert waiting is not None
            self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(len(waiting.pending_tool_run_ids), 1)

            queued_tool_run = container.require(AppKey.TOOL_SERVICE).get_tool_run(
                waiting.pending_tool_run_ids[0],
            )
            self.assertEqual(
                queued_tool_run.invocation_context_payload["session_key"],
                "agent:assistant:main",
            )
            self.assertEqual(
                queued_tool_run.invocation_context_payload["workspace_dir"],
                workspace_dir.name,
            )
            self.assertEqual(queued_tool_run.metadata["source"], "orchestration")
            self.assertEqual(
                queued_tool_run.metadata["orchestration_run_id"],
                "run-background-context",
            )
            self.assertEqual(
                queued_tool_run.metadata["session_key"],
                "agent:assistant:main",
            )
            self.assertEqual(
                queued_tool_run.metadata["active_session_id"],
                waiting.active_session_id,
            )
            self.assertEqual(queued_tool_run.metadata["agent_id"], "assistant")
            self.assertEqual(queued_tool_run.metadata["tool_call_id"], "call-bg-1")
            self.assertEqual(queued_tool_run.metadata["tool_name"], "background_echo")
            self.assertEqual(queued_tool_run.metadata["workspace_dir"], workspace_dir.name)
            self.assertIn(
                "workspace_bound",
                queued_tool_run.invocation_context_payload["available_scopes"],
            )

            finished_tool_run = process_next_background_tool_run(
                container,
                worker_id="tool-worker-1",
            )

            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(
                finished_tool_run.output_payload["execution_context"]["session_key"],
                "agent:assistant:main",
            )
            self.assertEqual(
                finished_tool_run.output_payload["execution_context"]["active_session_id"],
                waiting.active_session_id,
            )
            self.assertEqual(
                finished_tool_run.output_payload["execution_context"]["trace_id"],
                "run-background-context",
            )
            self.assertEqual(
                finished_tool_run.output_payload["execution_context"]["workspace_dir"],
                workspace_dir.name,
            )
            self.assertIn(
                "workspace_bound",
                finished_tool_run.output_payload["execution_context"]["available_scopes"],
            )
        finally:
            custom_harness.close()

    def test_background_tool_completion_event_resumes_run_and_allows_next_turn(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _BackgroundResumeAdapter()
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, background_echo)
            AuthorizationServiceAdapter(
                container.require(AppKey.AUTHORIZATION_SERVICE),
            ).grant_agent_effect_authorization(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-background-resume",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                    metadata={
                        "runtime_request_bootstrap_policy": {
                            "default_tool_schema_ids": ["background_echo"],
                        },
                    },
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            assert waiting is not None
            self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(len(waiting.pending_tool_run_ids), 1)
            background_tool_run_id = waiting.pending_tool_run_ids[0]

            finished_tool_run = process_next_background_tool_run(
                container,
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.id, background_tool_run_id)
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

            self.assertGreater(publish_outbox_events(container), 0)
            container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).process_runtime_events(
                limit_per_subscription=10,
            )
            processed_continuation = container.require(
                AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            ).process_next_continuation(
                worker_id="scheduler-1",
            )
            self.assertIsNotNone(processed_continuation)
            assert processed_continuation is not None
            self.assertEqual(
                processed_continuation.continuation_kind.value,
                "tool_terminal",
            )

            resumed = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(
                run.id,
            )
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)
            self.assertEqual(resumed.pending_tool_run_ids, ())
            self.assertEqual(resumed.waiting_reason, None)
            self.assertEqual(
                resumed.queue_policy,
                OrchestrationQueuePolicy.RESUME_FIRST,
            )
            session_items = container.require(AppKey.SESSION_SERVICE).list_items(
                ListSessionItemsInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            self.assertEqual(
                [(item.role, item.kind.value) for item in session_items],
                [
                    ("user", "user_message"),
                    ("assistant", "tool_call"),
                    ("tool", "tool_result"),
                ],
            )
            self.assertEqual(session_items[2].source_id, background_tool_run_id)
            self.assertEqual(session_items[2].call_id, "call-bg-1")

            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(completed.stage, OrchestrationRunStage.COMPLETED)
            self.assertEqual(completed.current_step, 3)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "background loop complete",
            )
            self.assertEqual(len(adapter.requests), 3)
            final_request = adapter.requests[-1]
            self.assertGreaterEqual(
                sum(
                    1
                    for item in final_request.input_items
                    if item.kind is LlmInputItemKind.MESSAGE
                ),
                1,
            )
            background_messages = [
                message
                for message in final_request.messages
                if message.tool_call_id == "call-bg-1"
            ]
            self.assertEqual(
                [message.role for message in background_messages],
                [LlmMessageRole.ASSISTANT, LlmMessageRole.TOOL],
            )
            self.assertEqual(completed.metadata["runtime_request_mode"], "normal_turn")
            recovery_system_messages = [
                message
                for message in final_request.messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            _request_render_snapshot(final_request)
            self.assertFalse(
                any("# Recovery Update" in str(message.content) for message in recovery_system_messages),
            )
            self.assertFalse(
                any(
                    "Durable memory is available for this run." in str(message.content)
                    for message in recovery_system_messages
                ),
            )
            self.assertFalse(
                any("# Recalled Memory" in str(message.content) for message in recovery_system_messages),
            )
        finally:
            custom_harness.close()

    def test_failed_background_tool_result_resumes_with_provider_replay_candidate_error(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _BackgroundResumeAdapter()
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(_arguments: dict[str, object]) -> ToolRunResult:
                raise RuntimeError("intentional background failure")

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(
                tool,
                background_echo,
            )
            AuthorizationServiceAdapter(
                container.require(AppKey.AUTHORIZATION_SERVICE),
            ).grant_agent_effect_authorization(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-background-failure-resume",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = process_next_orchestration_assignment(
                container,
                worker_id="worker-1",
            )
            assert waiting is not None
            self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(len(waiting.pending_tool_run_ids), 1)
            background_tool_run_id = waiting.pending_tool_run_ids[0]

            first_attempt = process_next_background_tool_run(
                container,
                worker_id="tool-worker-1",
            )
            second_attempt = process_next_background_tool_run(
                container,
                worker_id="tool-worker-1",
            )
            finished_tool_run = process_next_background_tool_run(
                container,
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(first_attempt)
            assert first_attempt is not None
            self.assertEqual(first_attempt.status, ToolRunStatus.QUEUED)
            self.assertIsNotNone(second_attempt)
            assert second_attempt is not None
            self.assertEqual(second_attempt.status, ToolRunStatus.QUEUED)
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.id, background_tool_run_id)
            self.assertEqual(finished_tool_run.status, ToolRunStatus.FAILED)
            self.assertEqual(finished_tool_run.attempt_count, 3)
            self.assertIn(
                "intentional background failure",
                finished_tool_run.error_message or "",
            )

            self.assertGreater(publish_outbox_events(container), 0)
            container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).process_runtime_events(
                limit_per_subscription=10,
            )
            processed_continuation = container.require(
                AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            ).process_next_continuation(
                worker_id="scheduler-1",
            )
            self.assertIsNotNone(processed_continuation)

            resumed = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)
            self.assertEqual(resumed.pending_tool_run_ids, ())
            self.assertEqual(
                resumed.metadata["runtime_request_flow_hint"]["reason"],
                "tool_failed_results_ready",
            )

            session_items = container.require(AppKey.SESSION_SERVICE).list_items(
                ListSessionItemsInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            self.assertEqual(
                [(item.role, item.kind.value) for item in session_items],
                [
                    ("user", "user_message"),
                    ("assistant", "tool_call"),
                    ("tool", "tool_result"),
                    ("assistant", "tool_call"),
                    ("tool", "tool_result"),
                ],
            )
            self.assertEqual(session_items[-1].source_id, background_tool_run_id)
            self.assertEqual(session_items[-1].content_payload["status"], "failed")
            self.assertIn(
                "intentional background failure",
                str(session_items[-1].content_payload),
            )

            completed = process_next_orchestration_assignment(
                container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(completed.stage, OrchestrationRunStage.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "background loop complete",
            )
            failed_tool_messages = [
                message
                for message in adapter.requests[-1].messages
                if message.role is LlmMessageRole.TOOL
                and message.name == "background_echo"
            ]
            self.assertEqual(len(failed_tool_messages), 1)
            self.assertIn(
                "intentional background failure",
                str(failed_tool_messages[0].content),
            )
        finally:
            custom_harness.close()

    def test_cancelled_background_tool_result_resumes_with_provider_replay_candidate_status(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _BackgroundResumeAdapter()
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(str(arguments.get("message") or ""))

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(
                tool,
                background_echo,
            )
            AuthorizationServiceAdapter(
                container.require(AppKey.AUTHORIZATION_SERVICE),
            ).grant_agent_effect_authorization(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-background-cancel-resume",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = process_next_orchestration_assignment(
                container,
                worker_id="worker-1",
            )
            assert waiting is not None
            self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(len(waiting.pending_tool_run_ids), 1)
            background_tool_run_id = waiting.pending_tool_run_ids[0]

            cancelled_tool_run = container.require(AppKey.TOOL_SERVICE).cancel_tool_run(
                background_tool_run_id,
            )
            self.assertEqual(cancelled_tool_run.status, ToolRunStatus.CANCELLED)

            self.assertGreater(publish_outbox_events(container), 0)
            container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).process_runtime_events(
                limit_per_subscription=10,
            )
            processed_continuation = container.require(
                AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            ).process_next_continuation(
                worker_id="scheduler-1",
            )
            self.assertIsNotNone(processed_continuation)

            resumed = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(
                resumed.metadata["runtime_request_flow_hint"]["reason"],
                "tool_terminal_results_ready",
            )

            session_items = container.require(AppKey.SESSION_SERVICE).list_items(
                ListSessionItemsInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            cancelled_messages = [
                item
                for item in session_items
                if item.kind.value == "tool_result"
                and item.source_id == background_tool_run_id
            ]
            self.assertEqual(len(cancelled_messages), 1)
            self.assertEqual(
                cancelled_messages[0].content_payload["status"],
                "cancelled",
            )
            self.assertIn(
                "cancelled before completion",
                str(cancelled_messages[0].content_payload),
            )

            completed = process_next_orchestration_assignment(
                container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            cancelled_tool_messages = [
                message
                for message in adapter.requests[-1].messages
                if message.role is LlmMessageRole.TOOL
                and message.name == "background_echo"
            ]
            self.assertEqual(len(cancelled_tool_messages), 1)
            self.assertIn("cancelled before completion", str(cancelled_tool_messages[0].content))
        finally:
            custom_harness.close()

    def test_recover_abandoned_runs_recovers_tool_wait_when_wait_mapping_is_lost(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _BackgroundApprovalAdapter()
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, background_echo)

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-tool-wait-recovery",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting_for_approval = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            assert waiting_for_approval is not None
            pending_request = waiting_for_approval.pending_approval_request()
            assert pending_request is not None

            waiting_on_tool = container.require(AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE).resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )
            self.assertEqual(waiting_on_tool.stage, OrchestrationRunStage.WAITING_ON_TOOL)

            with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
                uow.orchestration_waits.delete_for_run(run.id)
                uow.commit()

            finished_tool_run = process_next_background_tool_run(
                container,
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

            recovered = (
                container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).recover_abandoned_runs()
            )
            self.assertTrue(any(item.id == run.id for item in recovered))

            resumed = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(
                completed.result_payload["output_text"],
                "background approval flow complete",
            )
        finally:
            custom_harness.close()

    def test_process_next_orchestration_assignment_fails_when_llm_requests_unknown_tool(self) -> None:
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _ToolCallAdapter(),
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
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
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(processed.stage, OrchestrationRunStage.FAILED)
        self.assertEqual(processed.current_step, 1)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "tool_surface_not_visible")
        self.assertIn("search_docs", processed.error.message)

        session_items = self.session_service.list_items(
            ListSessionItemsInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [(item.role, item.kind.value) for item in session_items],
            [
                ("user", "user_message"),
                ("assistant", "assistant_message"),
                ("assistant", "tool_call"),
            ],
        )
