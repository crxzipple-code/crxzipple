from __future__ import annotations

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
    LlmDefaults,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
    LlmResult,
    LlmSourceKind,
    LlmUsage,
    ToolCallIntent,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure import LlmAdapterRegistry
from tests.unit.support import SqliteTestHarness


class _FakeLlmAdapter:
    def invoke(self, profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        self.last_profile = profile
        self.last_request = request
        return LlmAdapterResponse(
            result=LlmResult(
                text="hello from fake adapter",
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


class LlmServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.container = self.harness.build_container()
        self.registry = LlmAdapterRegistry()
        self.adapter = _FakeLlmAdapter()
        self.registry.register(LlmApiFamily.OPENAI_RESPONSES, self.adapter)
        self.service = LlmApplicationService(self.container.uow_factory, self.registry)

    def tearDown(self) -> None:
        self.harness.close()

    def test_register_profile_and_invoke_persists_new_llm_shapes(self) -> None:
        profile = self.service.register_profile(
            RegisterLlmProfileInput(
                id="writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5",
                model_family=LlmModelFamily.REASONING,
                capabilities=(
                    LlmCapability.TOOL_CALLING,
                    LlmCapability.STRUCTURED_OUTPUT,
                ),
                default_params=LlmDefaults(
                    temperature=0.2,
                    max_output_tokens=512,
                ),
                credential_binding="env:OPENAI_API_KEY",
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
            ),
        )

        self.assertEqual(profile.api_family, LlmApiFamily.OPENAI_RESPONSES)
        self.assertEqual(invocation.status.value, "succeeded")
        self.assertEqual(invocation.result.text, "hello from fake adapter")
        self.assertEqual(invocation.provider_request_id, "fake-request-123")
        self.assertEqual(invocation.result.tool_calls[0].name, "search_docs")
        self.assertEqual(self.adapter.last_profile.id, "writer")
        self.assertEqual(self.adapter.last_request.response_format, {"type": "json_object"})

        fetched_profile = self.service.get_profile("writer")
        fetched_invocation = self.service.get_invocation(invocation.id)
        invocation_list = self.service.list_invocations(llm_id="writer")

        self.assertEqual(fetched_profile.model_name, "gpt-5")
        self.assertEqual(fetched_profile.default_params.temperature, 0.2)
        self.assertEqual(fetched_invocation.result.usage.total_tokens, 20)
        self.assertEqual([item.id for item in invocation_list], [invocation.id])

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
                    credential_binding="env:OPENAI_API_KEY",
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
                    credential_binding="env:OPENAI_API_KEY",
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
        service = LlmApplicationService(self.container.uow_factory, registry)

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
