from __future__ import annotations

import asyncio
from datetime import datetime
import unittest

from crxzipple.modules.llm.application import (
    InvokeLlmInput,
    LlmAdapterRequest,
    LlmAdapterResponse,
    LlmApplicationService,
    LlmStreamEvent,
    RegisterLlmProfileInput,
    StreamLlmInput,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmContinuationReason,
    LlmContinuationSignal,
    LlmDefaults,
    LlmMessagePhase,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
    LlmResponseEvent,
    LlmResponseEventType,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmSourceKind,
    LlmUsage,
    ToolCallIntent,
    ToolSchema,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.interfaces.dto import LlmInvocationDTO, LlmProfileDTO
from crxzipple.modules.llm.infrastructure import LlmAdapterRegistry
from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.support import SqliteTestHarness, published_event_bus_events


class _FakeLlmAdapter:
    def invoke(self, profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        self.last_profile = profile
        self.last_request = request
        return LlmAdapterResponse(
            result=LlmResult(
                text="legacy adapter summary should be ignored",
                tool_calls=(
                    ToolCallIntent(
                        id="tool-call-1",
                        name="search_docs",
                        arguments={"query": "ddd"},
                    ),
                ),
                usage=LlmUsage(input_tokens=12, output_tokens=8, total_tokens=20),
                finish_reason="stop",
                metadata={"adapter": "fake"},
            ),
            response_items=(
                LlmResponseItem(
                    id=f"{request.invocation_id}:message:1",
                    invocation_id=request.invocation_id,
                    sequence_no=1,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    role=LlmMessageRole.ASSISTANT,
                    phase=LlmMessagePhase.FINAL_ANSWER,
                    content_payload={"text": "hello from fake adapter"},
                    provider_payload={"type": "message"},
                    provider_item_type="message",
                    model_visible=True,
                    user_visible=True,
                ),
                LlmResponseItem(
                    id=f"{request.invocation_id}:tool_call:1",
                    invocation_id=request.invocation_id,
                    sequence_no=2,
                    kind=LlmResponseItemKind.TOOL_CALL,
                    role=LlmMessageRole.ASSISTANT,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={
                        "call_id": "tool-call-1",
                        "tool_name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    provider_payload={"type": "function_call"},
                    provider_item_type="function_call",
                    call_id="tool-call-1",
                    tool_name="search_docs",
                    model_visible=True,
                    user_visible=False,
                ),
            ),
            continuation=LlmContinuationSignal(
                end_turn=False,
                needs_follow_up=True,
                reason=LlmContinuationReason.TOOL_CALL,
                provider_payload={"finish_reason": "tool_calls"},
            ),
            provider_request_id="fake-request-123",
        )


class _FakeStreamingLlmAdapter:
    def stream_invoke(self, profile, request):  # noqa: ANN001
        self.last_profile = profile
        self.last_request = request
        yield LlmStreamEvent(
            type="text_delta",
            sequence=1,
            data={"text": "hello "},
        )
        yield LlmStreamEvent(
            type="completed",
            sequence=2,
            data={
                "result": LlmResult(
                    text="hello from streaming adapter",
                    usage=LlmUsage(input_tokens=4, output_tokens=5, total_tokens=9),
                    finish_reason="completed",
                    metadata={"adapter": "streaming-fake"},
                ).to_payload(),
                "provider_request_id": "stream-request-123",
            },
        )


class _FakeNativeStreamingLlmAdapter:
    def stream_invoke(self, profile, request):  # noqa: ANN001
        yield LlmStreamEvent(
            type="item_started",
            sequence=1,
            data={
                "item_id": "item-native-1",
                "provider_event_type": "response.output_item.added",
                "provider_payload": {"type": "response.output_item.added"},
            },
        )
        yield LlmStreamEvent(
            type="tool_argument_delta",
            sequence=2,
            data={
                "item_id": "item-native-1",
                "delta": '{"query"',
                "provider_event_type": "response.function_call_arguments.delta",
                "provider_payload": {"type": "response.function_call_arguments.delta"},
            },
        )
        yield LlmStreamEvent(
            type="completed",
            sequence=3,
            data={
                "result": LlmResult(
                    text="legacy stream summary should be ignored",
                    finish_reason="completed",
                ).to_payload(),
                "response_items": [
                    LlmResponseItem(
                        id=f"{request.invocation_id}:native:item:1",
                        invocation_id=request.invocation_id,
                        sequence_no=1,
                        kind=LlmResponseItemKind.TOOL_CALL,
                        role=LlmMessageRole.ASSISTANT,
                        phase=LlmMessagePhase.COMMENTARY,
                        content_payload={
                            "call_id": "call-native-1",
                            "tool_name": "search_docs",
                            "arguments": {"query": "native"},
                        },
                        provider_item_id="item-native-1",
                        provider_item_type="function_call",
                        call_id="call-native-1",
                        tool_name="search_docs",
                    ).to_payload(),
                ],
                "continuation": LlmContinuationSignal(
                    end_turn=False,
                    needs_follow_up=True,
                    reason=LlmContinuationReason.TOOL_CALL,
                    provider_payload={"status": "completed"},
                ).to_payload(),
                "provider_request_id": "native-stream-request-123",
            },
        )


class _FakeAsyncLlmAdapter:
    async def invoke_async(self, profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        self.last_profile = profile
        self.last_request = request
        await asyncio.sleep(0)
        return LlmAdapterResponse(
            result=LlmResult(
                text="hello from async fake adapter",
                usage=LlmUsage(input_tokens=2, output_tokens=3, total_tokens=5),
                finish_reason="stop",
                metadata={"adapter": "async-fake"},
            ),
            provider_request_id="async-request-123",
        )


class _ConcurrentAsyncLlmAdapter:
    def __init__(self) -> None:
        self.active_count = 0
        self.max_active_count = 0

    async def invoke_async(self, profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        self.active_count += 1
        self.max_active_count = max(self.max_active_count, self.active_count)
        try:
            await asyncio.sleep(0.01)
            return LlmAdapterResponse(
                result=LlmResult(
                    text="limited async fake adapter",
                    finish_reason="stop",
                ),
                provider_request_id="limited-async-request",
            )
        finally:
            self.active_count -= 1


class _FakeAsyncStreamingLlmAdapter:
    async def stream_invoke_async(self, profile, request):  # noqa: ANN001
        self.last_profile = profile
        self.last_request = request
        await asyncio.sleep(0)
        yield LlmStreamEvent(
            type="text_delta",
            sequence=1,
            data={"text": "async "},
        )
        await asyncio.sleep(0)
        yield LlmStreamEvent(
            type="completed",
            sequence=2,
            data={
                "result": LlmResult(
                    text="hello from async streaming adapter",
                    usage=LlmUsage(input_tokens=3, output_tokens=4, total_tokens=7),
                    finish_reason="completed",
                    metadata={"adapter": "async-streaming-fake"},
                ).to_payload(),
                "provider_request_id": "async-stream-request-123",
            },
        )


class _FakeCredentialProvider:
    def __init__(self, credential: str = "injected-secret") -> None:
        self.credential = credential
        self.calls = []

    def resolve_credential(self, binding, *, consumer, trace_context=None):  # noqa: ANN001, ANN201
        self.calls.append((binding, consumer, trace_context))
        return self.credential


class LlmServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_runtime_container()
        self.uow_factory = self.container.require(AppKey.UNIT_OF_WORK_FACTORY)
        self.registry = LlmAdapterRegistry()
        self.adapter = _FakeLlmAdapter()
        self.registry.register(LlmApiFamily.OPENAI_RESPONSES, self.adapter)
        self.service = LlmApplicationService(self.uow_factory, self.registry)

    def tearDown(self) -> None:
        self.harness.close()

    def test_llm_invocation_dto_serializes_naive_datetimes_as_utc(self) -> None:
        invocation = LlmInvocation(
            id="llm-invocation-naive-time",
            llm_id="local-chat",
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="hello",
                ),
            ),
            created_at=datetime(2026, 4, 18, 7, 0, 0),
            started_at=datetime(2026, 4, 18, 7, 0, 1),
            completed_at=datetime(2026, 4, 18, 7, 0, 2),
        )

        dto = LlmInvocationDTO.from_entity(invocation)

        self.assertEqual(dto.created_at, "2026-04-18T07:00:00+00:00")
        self.assertEqual(dto.started_at, "2026-04-18T07:00:01+00:00")
        self.assertEqual(dto.completed_at, "2026-04-18T07:00:02+00:00")
        self.assertEqual(dto.response_items, ())

    def test_llm_profile_dto_exposes_access_credential_binding_id(self) -> None:
        profile = LlmProfile(
            id="inline-credential-profile",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="openai-api-key",
        )

        dto = LlmProfileDTO.from_entity(profile)

        self.assertEqual(dto.credential_binding_id, "openai-api-key")

    def test_response_item_event_and_continuation_payload_roundtrip(self) -> None:
        item = LlmResponseItem(
            id="item-1",
            invocation_id="inv-1",
            sequence_no=2,
            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
            role=LlmMessageRole.ASSISTANT,
            phase=LlmMessagePhase.COMMENTARY,
            content_payload={"text": "I will inspect the repo."},
            provider_payload={"type": "message", "id": "msg_1"},
            provider_item_id="msg_1",
            provider_item_type="message",
            model_visible=True,
            user_visible=True,
        )
        event = LlmResponseEvent(
            id="event-1",
            invocation_id="inv-1",
            sequence_no=3,
            type=LlmResponseEventType.REASONING_SUMMARY_DELTA,
            item_id=item.id,
            delta_payload={"text": "Inspecting"},
            provider_payload={"type": "response.reasoning_summary_text.delta"},
        )
        continuation = LlmContinuationSignal(
            end_turn=False,
            needs_follow_up=True,
            reason=LlmContinuationReason.PROVIDER_END_TURN_FALSE,
            provider_payload={"end_turn": False},
        )

        restored_item = LlmResponseItem.from_payload(item.to_payload())
        restored_event = LlmResponseEvent.from_payload(event.to_payload())
        restored_continuation = LlmContinuationSignal.from_payload(
            continuation.to_payload(),
        )

        self.assertEqual(restored_item.kind, LlmResponseItemKind.ASSISTANT_MESSAGE)
        self.assertEqual(restored_item.phase, LlmMessagePhase.COMMENTARY)
        self.assertEqual(restored_item.content_payload["text"], "I will inspect the repo.")
        self.assertEqual(restored_event.type, LlmResponseEventType.REASONING_SUMMARY_DELTA)
        self.assertEqual(restored_event.item_id, item.id)
        self.assertEqual(
            restored_continuation.reason,
            LlmContinuationReason.PROVIDER_END_TURN_FALSE,
        )
        self.assertTrue(restored_continuation.needs_follow_up)

    def test_result_summary_can_be_derived_from_response_items(self) -> None:
        usage = LlmUsage(input_tokens=10, output_tokens=8, total_tokens=18)
        result = LlmResult.from_response_items(
            (
                LlmResponseItem(
                    id="inv-derived:item:1",
                    invocation_id="inv-derived",
                    sequence_no=1,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    role=LlmMessageRole.ASSISTANT,
                    phase=LlmMessagePhase.COMMENTARY,
                    content_payload={"text": "I will inspect. "},
                    provider_item_type="message",
                ),
                LlmResponseItem(
                    id="inv-derived:item:2",
                    invocation_id="inv-derived",
                    sequence_no=2,
                    kind=LlmResponseItemKind.TOOL_CALL,
                    role=LlmMessageRole.ASSISTANT,
                    content_payload={
                        "call_id": "call-search-1",
                        "tool_name": "search_docs",
                        "arguments": {"query": "response items"},
                    },
                    provider_item_id="fc_1",
                    provider_item_type="function_call",
                    call_id="call-search-1",
                    tool_name="search_docs",
                ),
                LlmResponseItem(
                    id="inv-derived:item:3",
                    invocation_id="inv-derived",
                    sequence_no=3,
                    kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                    role=LlmMessageRole.ASSISTANT,
                    phase=LlmMessagePhase.FINAL_ANSWER,
                    content_payload={"text": "Done."},
                    provider_item_type="message",
                ),
            ),
            usage=usage,
            finish_reason="completed",
            metadata={"provider": "openai"},
        )

        self.assertEqual(result.text, "I will inspect. Done.")
        self.assertEqual(result.tool_calls[0].id, "call-search-1")
        self.assertEqual(result.tool_calls[0].name, "search_docs")
        self.assertEqual(result.tool_calls[0].arguments, {"query": "response items"})
        self.assertEqual(result.usage, usage)
        self.assertEqual(result.finish_reason, "completed")
        self.assertEqual(result.metadata["provider"], "openai")

    def test_invocation_repository_persists_response_items_events_and_continuation(self) -> None:
        profile = self.service.register_profile(
            RegisterLlmProfileInput(
                id="response-item-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
            ),
        )
        invocation = LlmInvocation(
            id="inv-response-items",
            llm_id=profile.id,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Need a staged plan.",
                ),
            ),
        )
        invocation.start()
        response_item = LlmResponseItem(
            id="item-message-1",
            invocation_id=invocation.id,
            sequence_no=1,
            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
            role=LlmMessageRole.ASSISTANT,
            phase=LlmMessagePhase.FINAL_ANSWER,
            content_payload={"text": "Done."},
            provider_payload={"type": "message"},
            provider_item_type="message",
            model_visible=True,
            user_visible=True,
        )
        continuation = LlmContinuationSignal(
            end_turn=True,
            needs_follow_up=False,
            reason=LlmContinuationReason.NONE,
            provider_payload={"status": "completed"},
        )
        invocation.succeed(
            LlmResult(text="Done.", finish_reason="stop"),
            response_items=(response_item,),
            continuation=continuation,
            provider_request_id="resp_123",
        )

        response_event = LlmResponseEvent(
            id="event-text-1",
            invocation_id=invocation.id,
            sequence_no=1,
            type=LlmResponseEventType.TEXT_DELTA,
            item_id=response_item.id,
            delta_payload={"text": "Done."},
            provider_payload={"type": "response.output_text.delta"},
        )

        with self.uow_factory() as uow:
            uow.llm_invocations.add(invocation)
            uow.llm_invocations.add_response_event(response_event)
            uow.commit()

        fetched = self.service.get_invocation(invocation.id)
        fetched_item = self.service.get_response_item(response_item.id)
        events = self.service.list_response_events(invocation.id)

        self.assertEqual(fetched.response_items[0].id, response_item.id)
        self.assertEqual(fetched_item.id, response_item.id)
        self.assertEqual(fetched_item.invocation_id, invocation.id)
        self.assertEqual(fetched.response_items[0].phase, LlmMessagePhase.FINAL_ANSWER)
        self.assertEqual(fetched.continuation.end_turn, True)
        self.assertFalse(fetched.continuation.needs_follow_up)
        self.assertEqual(events[0].type, LlmResponseEventType.TEXT_DELTA)
        self.assertEqual(events[0].delta_payload["text"], "Done.")

    def test_register_profile_and_invoke_persists_new_llm_shapes(self) -> None:
        profile = self.service.register_profile(
            RegisterLlmProfileInput(
                id="writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
                context_window_tokens=128_000,
                model_family=LlmModelFamily.REASONING,
                capabilities=(
                    LlmCapability.TOOL_CALLING,
                    LlmCapability.STRUCTURED_OUTPUT,
                ),
                default_params=LlmDefaults(
                    temperature=0.2,
                    max_output_tokens=512,
                    extra_body={
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                ),
                credential_binding_id="openai-api-key",
                max_concurrency=2,
                concurrency_key="provider:openai",
            ),
        )

        invocation = self.service.invoke(
            InvokeLlmInput(
                llm_id=profile.id,
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.SYSTEM,
                        content="You are a helpful coding assistant.",
                    ),
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="plan a ddd llm subsystem",
                    ),
                ),
                tool_schemas=(
                    ToolSchema(
                        name="search_docs",
                        description="Search project docs",
                        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                    ),
                ),
                response_format={"type": "json_object"},
                overrides={"reasoning_effort": "medium"},
                request_metadata={
                    "context_render_snapshot_id": "ctxsnap_run_1",
                    "runtime_contract_version": "2026-06-09",
                    "runtime_contract_hash": "abc123",
                    "mirrored_tool_schema_count": 1,
                },
            ),
        )

        self.assertEqual(profile.api_family, LlmApiFamily.OPENAI_RESPONSES)
        self.assertEqual(invocation.status.value, "succeeded")
        self.assertEqual(invocation.result.text, "hello from fake adapter")
        self.assertEqual(invocation.provider_request_id, "fake-request-123")
        self.assertEqual(invocation.result.tool_calls[0].name, "search_docs")
        self.assertEqual(
            invocation.request_metadata["runtime_contract_version"],
            "2026-06-09",
        )
        self.assertEqual(self.adapter.last_profile.id, "writer")
        self.assertEqual(self.adapter.last_request.response_format, {"type": "json_object"})

        fetched_profile = self.service.get_profile("writer")
        fetched_invocation = self.service.get_invocation(invocation.id)
        invocation_list = self.service.list_invocations(llm_id="writer")

        self.assertEqual(fetched_profile.model_name, "gpt-5")
        self.assertEqual(fetched_profile.context_window_tokens, 128_000)
        self.assertEqual(fetched_profile.max_concurrency, 2)
        self.assertEqual(fetched_profile.concurrency_key, "provider:openai")
        self.assertEqual(fetched_profile.default_params.temperature, 0.2)
        self.assertEqual(
            fetched_profile.default_params.extra_body,
            {"chat_template_kwargs": {"enable_thinking": False}},
        )
        self.assertEqual(
            fetched_invocation.request_metadata,
            {
                "context_render_snapshot_id": "ctxsnap_run_1",
                "runtime_contract_version": "2026-06-09",
                "runtime_contract_hash": "abc123",
                "mirrored_tool_schema_count": 1,
            },
        )
        self.assertEqual(fetched_invocation.result.usage.total_tokens, 20)
        self.assertEqual(
            fetched_invocation.response_items[0].kind,
            LlmResponseItemKind.ASSISTANT_MESSAGE,
        )
        self.assertEqual(
            LlmInvocationDTO.from_entity(fetched_invocation).response_items[0][
                "content_payload"
            ],
            {"text": "hello from fake adapter"},
        )
        self.assertEqual(fetched_invocation.response_items[0].invocation_id, invocation.id)
        self.assertEqual(fetched_invocation.continuation.reason, LlmContinuationReason.TOOL_CALL)
        self.assertEqual([item.id for item in invocation_list], [invocation.id])

    def test_invocation_succeeded_event_exposes_text_and_tool_diagnostics(self) -> None:
        profile = self.service.register_profile(
            RegisterLlmProfileInput(
                id="diagnostic-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
            ),
        )

        invocation = self.service.invoke(
            InvokeLlmInput(
                llm_id=profile.id,
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="inspect tool diagnostics",
                    ),
                ),
            ),
        )

        events = [
            event
            for event in published_event_bus_events(self.container)
            if event.name == "llm.invocation_succeeded"
            and event.payload.get("invocation_id") == invocation.id
        ]

        self.assertEqual(len(events), 1)
        payload = events[0].payload
        self.assertEqual(payload["finish_reason"], "stop")
        self.assertTrue(payload["text_present"])
        self.assertEqual(payload["text_chars"], len("hello from fake adapter"))
        self.assertEqual(payload["tool_call_count"], 1)
        self.assertEqual(payload["tool_call_names"], ["search_docs"])
        self.assertEqual(payload["usage"]["total_tokens"], 20)

    def test_profile_update_enable_disable_and_delete_use_llm_repository(self) -> None:
        self.service.register_profile(
            RegisterLlmProfileInput(
                id="runtime-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
            ),
        )

        updated = self.service.update_profile(
            RegisterLlmProfileInput(
                id="runtime-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.1",
                enabled=True,
            ),
        )
        disabled = self.service.set_profile_enabled("runtime-writer", enabled=False)
        enabled = self.service.set_profile_enabled("runtime-writer", enabled=True)
        self.service.delete_profile("runtime-writer")

        self.assertEqual(updated.model_name, "gpt-5.1")
        self.assertFalse(disabled.enabled)
        self.assertTrue(enabled.enabled)
        self.assertNotIn(
            "runtime-writer",
            [profile.id for profile in self.service.list_profiles()],
        )

    def test_invoke_resolves_credential_through_injected_access_provider(self) -> None:
        credential_provider = _FakeCredentialProvider("llm-access-token")
        service = LlmApplicationService(
            self.uow_factory,
            self.registry,
            credential_provider=credential_provider,
        )
        profile = service.register_profile(
            RegisterLlmProfileInput(
                id="access-backed-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
                credential_binding_id="llm-access-token",
            ),
        )

        invocation = service.invoke(
            InvokeLlmInput(
                llm_id=profile.id,
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Use injected access.",
                    ),
                ),
            ),
        )

        binding, consumer, trace_context = credential_provider.calls[0]
        self.assertEqual(binding.source_ref, "llm-access-token")
        self.assertEqual(binding.source_type, "access_credential_binding")
        self.assertEqual(consumer.module, "llm")
        self.assertEqual(consumer.consumer_id, "llm.profile:access-backed-writer")
        self.assertIsNone(trace_context)
        self.assertEqual(self.adapter.last_request.resolved_credential, "llm-access-token")
        self.assertEqual(invocation.status.value, "succeeded")

        fetched_profile = service.get_profile(profile.id)
        self.assertEqual(fetched_profile.credential_binding_id, "llm-access-token")
        self.assertNotEqual(fetched_profile.credential_binding_id, "llm-access-token-secret")

    def test_profile_probe_invokes_without_persisting_profile_or_invocation(self) -> None:
        credential_provider = _FakeCredentialProvider("probe-token")
        service = LlmApplicationService(
            self.uow_factory,
            self.registry,
            credential_provider=credential_provider,
        )

        invocation = service.test_profile(
            RegisterLlmProfileInput(
                id="probe-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
                credential_binding_id="openai-api-key",
            ),
            InvokeLlmInput(
                llm_id="probe-writer",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Probe this unsaved profile.",
                    ),
                ),
            ),
        )

        self.assertEqual(invocation.status.value, "succeeded")
        self.assertEqual(self.adapter.last_request.resolved_credential, "probe-token")
        self.assertNotIn("probe-writer", [profile.id for profile in service.list_profiles()])
        self.assertEqual(service.list_invocations(llm_id="probe-writer"), [])

    def test_sync_profiles_updates_imported_profiles_and_preserves_manual_profiles(self) -> None:
        manual_profile = self.service.register_profile(
            RegisterLlmProfileInput(
                id="manual-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                source_kind=LlmSourceKind.MANUAL,
            ),
        )

        synced_once = self.service.sync_profiles(
            (
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4",
                    model_family=LlmModelFamily.REASONING,
                    source_kind=LlmSourceKind.IMPORTED,
                    credential_binding_id="openai-api-key",
                ),
                RegisterLlmProfileInput(
                    id="manual-writer",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4",
                    source_kind=LlmSourceKind.IMPORTED,
                ),
            ),
        )
        synced_twice = self.service.sync_profiles(
            (
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    model_family=LlmModelFamily.REASONING,
                    source_kind=LlmSourceKind.IMPORTED,
                    credential_binding_id="openai-api-key",
                ),
            ),
        )

        imported_profile = self.service.get_profile("openai.gpt-5.4")
        preserved_manual_profile = self.service.get_profile("manual-writer")

        self.assertEqual(synced_once[0].model_name, "gpt-5.4")
        self.assertEqual(synced_once[1].model_name, manual_profile.model_name)
        self.assertEqual(synced_twice[0].model_name, "gpt-5.4-mini")
        self.assertEqual(imported_profile.model_name, "gpt-5.4-mini")
        self.assertEqual(imported_profile.source_kind, LlmSourceKind.IMPORTED)
        self.assertEqual(preserved_manual_profile.model_name, "gpt-5.4-mini")
        self.assertEqual(preserved_manual_profile.source_kind, LlmSourceKind.MANUAL)

    def test_stream_invoke_emits_events_and_persists_final_result(self) -> None:
        registry = LlmAdapterRegistry()
        adapter = _FakeStreamingLlmAdapter()
        registry.register(LlmApiFamily.OPENAI_CODEX_RESPONSES, adapter)
        service = LlmApplicationService(self.uow_factory, registry)

        profile = service.register_profile(
            RegisterLlmProfileInput(
                id="codex",
                provider=LlmProviderKind.OPENAI_CODEX,
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                model_name="gpt-5-codex",
                model_family=LlmModelFamily.CODEX,
            ),
        )

        events = list(
            service.stream_invoke(
                StreamLlmInput(
                    llm_id=profile.id,
                    messages=(
                        LlmMessage(
                            role=LlmMessageRole.SYSTEM,
                            content="You are a concise coding assistant.",
                        ),
                        LlmMessage(
                            role=LlmMessageRole.USER,
                            content="Say hello.",
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual([event.type for event in events], ["invocation_started", "text_delta", "completed"])
        self.assertEqual(events[1].data["text"], "hello ")
        invocation_id = events[0].invocation_id
        stored = service.get_invocation(invocation_id)

        self.assertEqual(stored.status.value, "succeeded")
        self.assertEqual(stored.result.text, "hello from streaming adapter")
        self.assertEqual(stored.provider_request_id, "stream-request-123")
        response_events = service.list_response_events(invocation_id)
        self.assertEqual(
            [event.type for event in response_events],
            [
                LlmResponseEventType.INVOCATION_STARTED,
                LlmResponseEventType.TEXT_DELTA,
                LlmResponseEventType.COMPLETED,
            ],
        )
        self.assertEqual(response_events[1].delta_payload["text"], "hello ")

    def test_stream_invoke_persists_native_response_events_with_item_refs(self) -> None:
        registry = LlmAdapterRegistry()
        registry.register(LlmApiFamily.OPENAI_RESPONSES, _FakeNativeStreamingLlmAdapter())
        service = LlmApplicationService(self.uow_factory, registry)
        profile = service.register_profile(
            RegisterLlmProfileInput(
                id="native-stream-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
            ),
        )

        events = list(
            service.stream_invoke(
                StreamLlmInput(
                    llm_id=profile.id,
                    messages=(LlmMessage(role=LlmMessageRole.USER, content="Use native."),),
                ),
            ),
        )
        invocation_id = events[0].invocation_id
        response_events = service.list_response_events(invocation_id)

        self.assertEqual(
            [event.type for event in response_events],
            [
                LlmResponseEventType.INVOCATION_STARTED,
                LlmResponseEventType.ITEM_STARTED,
                LlmResponseEventType.TOOL_ARGUMENT_DELTA,
                LlmResponseEventType.COMPLETED,
            ],
        )
        self.assertEqual(response_events[1].item_id, "item-native-1")
        self.assertEqual(response_events[2].item_id, "item-native-1")
        self.assertEqual(
            response_events[2].provider_payload["type"],
            "response.function_call_arguments.delta",
        )
        stored = service.get_invocation(invocation_id)
        self.assertEqual(len(stored.response_items), 1)
        self.assertEqual(stored.response_items[0].kind, LlmResponseItemKind.TOOL_CALL)
        self.assertEqual(stored.result.text, None)
        self.assertEqual(stored.result.tool_calls[0].id, "call-native-1")
        self.assertEqual(stored.result.tool_calls[0].name, "search_docs")
        self.assertEqual(stored.continuation.reason, LlmContinuationReason.TOOL_CALL)

    def test_invoke_async_uses_async_adapter_and_persists_result(self) -> None:
        registry = LlmAdapterRegistry()
        adapter = _FakeAsyncLlmAdapter()
        registry.register(LlmApiFamily.OPENAI_RESPONSES, adapter)
        service = LlmApplicationService(self.uow_factory, registry)
        profile = service.register_profile(
            RegisterLlmProfileInput(
                id="async-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )

        invocation = asyncio.run(
            service.invoke_async(
                InvokeLlmInput(
                    llm_id=profile.id,
                    messages=(
                        LlmMessage(
                            role=LlmMessageRole.USER,
                            content="Say hello asynchronously.",
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(invocation.status.value, "succeeded")
        self.assertEqual(invocation.result.text, "hello from async fake adapter")
        self.assertEqual(invocation.provider_request_id, "async-request-123")
        self.assertEqual(adapter.last_profile.id, "async-writer")

    def test_invoke_async_respects_profile_concurrency_limit(self) -> None:
        registry = LlmAdapterRegistry()
        adapter = _ConcurrentAsyncLlmAdapter()
        registry.register(LlmApiFamily.OPENAI_RESPONSES, adapter)
        service = LlmApplicationService(self.uow_factory, registry)
        profile = service.register_profile(
            RegisterLlmProfileInput(
                id="limited-async-writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                max_concurrency=1,
            ),
        )

        async def _invoke_pair():
            return await asyncio.gather(
                service.invoke_async(
                    InvokeLlmInput(
                        llm_id=profile.id,
                        messages=(
                            LlmMessage(
                                role=LlmMessageRole.USER,
                                content="first",
                            ),
                        ),
                        invocation_id="limited-async-1",
                    ),
                ),
                service.invoke_async(
                    InvokeLlmInput(
                        llm_id=profile.id,
                        messages=(
                            LlmMessage(
                                role=LlmMessageRole.USER,
                                content="second",
                            ),
                        ),
                        invocation_id="limited-async-2",
                    ),
                ),
            )

        invocations = asyncio.run(_invoke_pair())

        self.assertEqual(
            [item.status.value for item in invocations],
            ["succeeded", "succeeded"],
        )
        self.assertEqual(adapter.max_active_count, 1)

    def test_stream_invoke_async_emits_events_and_persists_final_result(self) -> None:
        registry = LlmAdapterRegistry()
        adapter = _FakeAsyncStreamingLlmAdapter()
        registry.register(LlmApiFamily.OPENAI_CODEX_RESPONSES, adapter)
        service = LlmApplicationService(self.uow_factory, registry)
        profile = service.register_profile(
            RegisterLlmProfileInput(
                id="async-codex",
                provider=LlmProviderKind.OPENAI_CODEX,
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                model_name="gpt-5-codex",
                model_family=LlmModelFamily.CODEX,
            ),
        )

        async def _collect_events():
            return [
                event
                async for event in service.stream_invoke_async(
                    StreamLlmInput(
                        llm_id=profile.id,
                        messages=(
                            LlmMessage(
                                role=LlmMessageRole.USER,
                                content="Say hello asynchronously.",
                            ),
                        ),
                    ),
                )
            ]

        events = asyncio.run(_collect_events())

        self.assertEqual(
            [event.type for event in events],
            ["invocation_started", "text_delta", "completed"],
        )
        self.assertEqual(events[1].data["text"], "async ")
        stored = service.get_invocation(events[0].invocation_id)
        self.assertEqual(stored.status.value, "succeeded")
        self.assertEqual(stored.result.text, "hello from async streaming adapter")
        self.assertEqual(stored.provider_request_id, "async-stream-request-123")
