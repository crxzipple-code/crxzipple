from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crxzipple.modules.llm.application import LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmContinuationReason,
    LlmDefaults,
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderContinuation,
    LlmProfile,
    LlmProviderKind,
    LlmResponseItemKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure import (
    AnthropicMessagesAdapter,
    GeminiGenerateContentAdapter,
    OpenAIChatCompatibleAdapter,
    OpenAICodexResponsesAdapter,
    OpenAIResponsesAdapter,
)


def _adapter_request(**kwargs) -> LlmAdapterRequest:  # noqa: ANN003
    kwargs.setdefault("invocation_id", "adapter-test-invocation")
    kwargs.setdefault("resolved_credential", "adapter-test-token")
    return LlmAdapterRequest(**kwargs)


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: dict[str, object] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, object]:
        return dict(self._payload)


class _FakeStreamResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        events: tuple[tuple[str | None, dict[str, object]], ...] = (),
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._events = events
        self.text = text
        self.iter_lines_chunk_size: int | None = None

    def iter_lines(
        self,
        chunk_size: int | None = None,
        decode_unicode: bool = False,
    ):  # noqa: ANN001
        self.iter_lines_chunk_size = chunk_size
        del decode_unicode
        for event_name, payload in self._events:
            if event_name is not None:
                yield f"event: {event_name}".encode("utf-8")
            yield f"data: {json.dumps(payload)}".encode("utf-8")
            yield b""


class _FakeAsyncResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: dict[str, object] | None = None,
        events: tuple[tuple[str | None, dict[str, object]], ...] = (),
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self._events = events
        self._text = text
        self.headers = headers or {}

    @property
    def text(self) -> str:
        if self._text:
            return self._text
        if self._payload:
            return json.dumps(self._payload)
        return ""

    def json(self) -> dict[str, object]:
        return dict(self._payload)

    async def aread(self) -> bytes:
        return self.text.encode("utf-8")

    async def aiter_lines(self):  # noqa: ANN201
        for event_name, payload in self._events:
            if event_name is not None:
                yield f"event: {event_name}"
            yield f"data: {json.dumps(payload)}"
            yield ""


class _FakeAsyncStreamContext:
    def __init__(self, response: _FakeAsyncResponse) -> None:
        self.response = response

    async def __aenter__(self) -> _FakeAsyncResponse:
        return self.response

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


class _FakeAsyncClient:
    response = _FakeAsyncResponse()
    instances: list["_FakeAsyncClient"] = []

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.args = args
        self.kwargs = kwargs
        self.requests: list[tuple[str, str, dict[str, object]]] = []
        type(self).instances.append(self)

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def post(self, url: str, **kwargs):  # noqa: ANN003, ANN201
        self.requests.append(("POST", url, dict(kwargs)))
        return type(self).response

    def stream(self, method: str, url: str, **kwargs):  # noqa: ANN003, ANN201
        self.requests.append((method, url, dict(kwargs)))
        return _FakeAsyncStreamContext(type(self).response)


class LlmAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_env = dict(os.environ)
        _FakeAsyncClient.instances = []

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.previous_env)
        _FakeAsyncClient.response = _FakeAsyncResponse()

    def test_openai_responses_adapter_shapes_request_and_result(self) -> None:
        profile = LlmProfile(
            id="writer",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            model_family=LlmModelFamily.REASONING,
            default_params=LlmDefaults(
                temperature=0.2,
                max_output_tokens=512,
                reasoning_effort="medium",
            ),
            credential_binding_id="openai-api-key",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="You are a precise assistant.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Explain DDD.",
                ),
            ),
            tool_schemas=(
                ToolSchema(
                    name="search_docs",
                    description="Search project docs",
                    input_schema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                ),
            ),
            response_format={"type": "json_schema", "name": "answer"},
            overrides={"reasoning": {"summary": "auto"}},
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_123",
                                "model": "gpt-5",
                                "status": "completed",
                                "output_text": "DDD focuses on domain boundaries.",
                                "output": [
                                    {
                                        "type": "function_call",
                                        "call_id": "call_1",
                                        "name": "search_docs",
                                        "arguments": '{"query":"ddd"}',
                                    },
                                ],
                                "usage": {
                                    "input_tokens": 11,
                                    "output_tokens": 22,
                                    "total_tokens": 33,
                                },
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            response = OpenAIResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.provider_request_id, "resp_123")
        self.assertEqual(response.result.text, "DDD focuses on domain boundaries.")
        self.assertEqual(response.result.tool_calls[0].name, "search_docs")
        self.assertEqual(response.result.tool_calls[0].arguments, {"query": "ddd"})
        self.assertEqual(response.result.usage.total_tokens, 33)
        self.assertEqual(response.response_items[0].kind, LlmResponseItemKind.TOOL_CALL)
        self.assertEqual(response.response_items[0].invocation_id, request.invocation_id)
        self.assertEqual(response.response_items[0].tool_name, "search_docs")
        self.assertEqual(response.continuation.reason, LlmContinuationReason.TOOL_CALL)
        self.assertTrue(response.continuation.needs_follow_up)

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer adapter-test-token")
        self.assertEqual(kwargs["json"]["model"], "gpt-5")
        self.assertEqual(kwargs["json"]["tools"][0]["name"], "search_docs")
        self.assertEqual(kwargs["json"]["text"]["format"]["name"], "answer")
        self.assertEqual(
            kwargs["json"]["reasoning"],
            {"effort": "medium", "summary": "auto"},
        )
        self.assertTrue(kwargs["json"]["stream"])
        self.assertEqual(kwargs["headers"]["Accept"], "text/event-stream")

    def test_openai_responses_adapter_sanitizes_tool_names_and_restores_tool_calls(self) -> None:
        profile = LlmProfile(
            id="writer-tool-alias",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Need docs"),
            ),
            tool_schemas=(
                ToolSchema(
                    name="sample_api.search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_tool_alias_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [
                                    {
                                        "type": "function_call",
                                        "call_id": "call_alias_1",
                                        "name": "sample_api_search_docs",
                                        "arguments": '{"query":"ddd"}',
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            response = OpenAIResponsesAdapter().invoke(profile, request)

        self.assertEqual(
            response.result.tool_calls[0].name,
            "sample_api.search_docs",
        )
        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["tools"][0]["name"],
            "sample_api_search_docs",
        )

    def test_openai_responses_adapter_maps_reasoning_external_items_and_end_turn(self) -> None:
        profile = LlmProfile(
            id="writer-structured-items",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Search and explain."),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_structured_items_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "end_turn": False,
                                "output": [
                                    {
                                        "type": "reasoning",
                                        "id": "rs_1",
                                        "summary": [
                                            {
                                                "type": "summary_text",
                                                "text": "Need current facts.",
                                            },
                                        ],
                                    },
                                    {
                                        "type": "web_search_call",
                                        "id": "ws_1",
                                        "status": "completed",
                                        "query": "CRXZipple",
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ):
            response = OpenAIResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.response_items[0].kind, LlmResponseItemKind.REASONING)
        self.assertEqual(response.response_items[0].content_payload["text"], "Need current facts.")
        self.assertEqual(
            response.response_items[1].kind,
            LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM,
        )
        self.assertIsNone(response.response_items[1].tool_name)
        self.assertEqual(
            response.continuation.reason,
            LlmContinuationReason.PROVIDER_END_TURN_FALSE,
        )
        self.assertTrue(response.continuation.needs_follow_up)

    def test_openai_responses_adapter_uses_resolved_request_credential(self) -> None:
        profile = LlmProfile(
            id="writer-access-provider",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="missing-openai-api-key",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Use injected access."),
            ),
            resolved_credential="access-provider-token",
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_access_provider_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output_text": "ok",
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            OpenAIResponsesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer access-provider-token",
        )

    def test_openai_responses_adapter_does_not_resolve_binding_fallback(self) -> None:
        os.environ["OPENAI_API_KEY"] = "env-token-that-must-not-be-read"
        profile = LlmProfile(
            id="writer-no-private-fallback",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="openai-api-key",
        )
        request = LlmAdapterRequest(
            invocation_id="no-private-fallback-invocation",
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="No private fallback."),
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "no resolved credential was injected",
        ):
            OpenAIResponsesAdapter().invoke(profile, request)

    def test_openai_responses_adapter_stream_invoke_emits_text_delta_and_completed(self) -> None:
        profile = LlmProfile(
            id="writer-stream",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Reply with stream-openai."),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "delta": "stream-",
                        },
                    ),
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_stream_123",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [
                                            {
                                                "type": "output_text",
                                                "text": "stream-openai",
                                            },
                                        ],
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ):
            events = list(OpenAIResponsesAdapter().stream_invoke(profile, request))

        self.assertEqual([event.type for event in events], ["text_delta", "completed"])
        self.assertEqual(events[0].data["text"], "stream-")
        self.assertEqual(events[1].data["result"]["text"], "stream-openai")

    def test_openai_responses_adapter_stream_invoke_emits_native_lifecycle_events(self) -> None:
        profile = LlmProfile(
            id="writer-stream-native",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Use native events."),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "output_index": 0,
                            "item": {
                                "id": "fc_native_1",
                                "type": "function_call",
                                "call_id": "call_native_1",
                                "name": "search_docs",
                            },
                        },
                    ),
                    (
                        "response.function_call_arguments.delta",
                        {
                            "type": "response.function_call_arguments.delta",
                            "item_id": "fc_native_1",
                            "delta": '{"query"',
                        },
                    ),
                    (
                        "response.reasoning_summary_text.delta",
                        {
                            "type": "response.reasoning_summary_text.delta",
                            "item_id": "rs_native_1",
                            "delta": "Need docs.",
                        },
                    ),
                    (
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": 0,
                            "item": {
                                "id": "fc_native_1",
                                "type": "function_call",
                                "call_id": "call_native_1",
                                "name": "search_docs",
                                "arguments": '{"query":"native"}',
                            },
                        },
                    ),
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_native_stream",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [],
                            },
                        },
                    ),
                ),
            ),
        ):
            events = list(OpenAIResponsesAdapter().stream_invoke(profile, request))

        self.assertEqual(
            [event.type for event in events],
            [
                "item_started",
                "tool_argument_delta",
                "reasoning_summary_delta",
                "item_completed",
                "completed",
            ],
        )
        self.assertEqual(events[0].data["item_id"], "fc_native_1")
        self.assertEqual(events[1].data["delta"], '{"query"')
        self.assertEqual(events[2].data["text"], "Need docs.")
        self.assertEqual(events[3].data["item_id"], "fc_native_1")
        self.assertEqual(events[4].data["response_items"][0]["kind"], "tool_call")
        self.assertEqual(events[4].data["result"]["tool_calls"][0]["name"], "search_docs")

    def test_openai_responses_adapter_stream_invoke_async_uses_async_stream(self) -> None:
        profile = LlmProfile(
            id="writer-stream-async",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Reply async."),
            ),
        )
        _FakeAsyncClient.response = _FakeAsyncResponse(
            headers={"content-type": "text/event-stream"},
            events=(
                (
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "delta": "async-",
                    },
                ),
                (
                    "response.completed",
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_stream_async_123",
                            "model": "gpt-5",
                            "status": "completed",
                            "output_text": "async-openai",
                        },
                    },
                ),
            ),
        )

        async def collect_events():
            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_responses.httpx.AsyncClient",
                _FakeAsyncClient,
            ):
                return [
                    event
                    async for event in OpenAIResponsesAdapter().stream_invoke_async(
                        profile,
                        request,
                    )
                ]

        events = asyncio.run(collect_events())

        self.assertEqual([event.type for event in events], ["text_delta", "completed"])
        self.assertEqual(events[0].data["text"], "async-")
        self.assertEqual(events[1].data["result"]["text"], "async-openai")
        self.assertEqual(len(_FakeAsyncClient.instances), 1)
        method, url, kwargs = _FakeAsyncClient.instances[0].requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.openai.com/v1/responses")
        self.assertTrue(kwargs["json"]["stream"])

    def test_openai_responses_adapter_encodes_user_image_blocks(self) -> None:
        profile = LlmProfile(
            id="writer-vision",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
            capabilities=(LlmCapability.VISION_INPUT,),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {"type": "text", "text": "Describe the screenshot."},
                        {
                            "type": "image",
                            "data": "ZmFrZS1wbmc=",
                            "mime_type": "image/png",
                        },
                    ],
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_vision_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            OpenAIResponsesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"][0]["content"],
            [
                {"type": "input_text", "text": "Describe the screenshot."},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,ZmFrZS1wbmc=",
                },
            ],
        )

    def test_openai_responses_adapter_encodes_user_file_blocks_without_vision_capability(self) -> None:
        profile = LlmProfile(
            id="writer-document",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {"type": "text", "text": "Summarize this PDF."},
                        {
                            "type": "file",
                            "data": "JVBERi0xLjQKZmFrZQ==",
                            "mime_type": "application/pdf",
                            "name": "brief.pdf",
                        },
                    ],
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_file_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            OpenAIResponsesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"][0]["content"],
            [
                {"type": "input_text", "text": "Summarize this PDF."},
                {
                    "type": "input_file",
                    "file_data": "JVBERi0xLjQKZmFrZQ==",
                    "filename": "brief.pdf",
                },
            ],
        )

    def test_openai_responses_adapter_rejects_image_blocks_without_vision_capability(self) -> None:
        profile = LlmProfile(
            id="writer-no-vision",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {
                            "type": "image",
                            "data": "ZmFrZS1wbmc=",
                            "mime_type": "image/png",
                        },
                    ],
                ),
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "does not support vision input"):
            OpenAIResponsesAdapter().invoke(profile, request)

    def test_openai_responses_adapter_emits_tool_result_image_blocks(self) -> None:
        profile = LlmProfile(
            id="writer-tool-vision",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
            capabilities=(LlmCapability.VISION_INPUT,),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    tool_call_id="call_browser_1",
                    name="browser.screenshot",
                    content=[
                        {
                            "type": "text",
                            "text": "Browser screenshot captured.",
                        },
                        {
                            "type": "image",
                            "data": "ZmFrZS1wbmc=",
                            "mime_type": "image/png",
                        },
                    ],
                    metadata={
                        "tool_name": "browser.screenshot",
                        "tool_details": {
                            "ok": True,
                            "value": {
                                "kind": "screenshot",
                                "content_type": "image/png",
                                "attachment_in_blocks": True,
                            },
                        },
                    },
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_tool_vision_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            OpenAIResponsesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"][0],
            {
                "type": "function_call_output",
                "call_id": "call_browser_1",
                "output": "Browser screenshot captured.\n[image]",
            },
        )
        self.assertEqual(
            kwargs["json"]["input"][1],
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Browser screenshot captured.",
                    },
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,ZmFrZS1wbmc=",
                    },
                ],
            },
        )

    def test_openai_responses_adapter_emits_tool_result_file_blocks(self) -> None:
        profile = LlmProfile(
            id="writer-tool-document",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    tool_call_id="call_pdf_1",
                    name="browser.screenshot",
                    content=[
                        {"type": "text", "text": "Exported PDF."},
                        {
                            "type": "file",
                            "data": "JVBERi0xLjQKZmFrZQ==",
                            "mime_type": "application/pdf",
                            "name": "report.pdf",
                        },
                    ],
                    metadata={
                        "tool_name": "browser.screenshot",
                        "tool_details": {
                            "ok": True,
                            "value": {
                                "kind": "pdf",
                                "attachment_in_blocks": True,
                            },
                        },
                    },
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_tool_file_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            OpenAIResponsesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"][0],
            {
                "type": "function_call_output",
                "call_id": "call_pdf_1",
                "output": "Exported PDF.\n[file:report.pdf]",
            },
        )
        self.assertEqual(
            kwargs["json"]["input"][1],
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Exported PDF."},
                    {
                        "type": "input_file",
                        "file_data": "JVBERi0xLjQKZmFrZQ==",
                        "filename": "report.pdf",
                    },
                ],
            },
        )

    def test_openai_responses_adapter_retries_transient_server_error_before_output(self) -> None:
        profile = LlmProfile(
            id="writer-retry",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Retry please."),
            ),
        )

        with (
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
                side_effect=[
                    _FakeStreamResponse(
                        events=(
                            (
                                "response.created",
                                {
                                    "type": "response.created",
                                    "response": {
                                        "id": "resp_retry_1",
                                        "status": "in_progress",
                                        "model": "gpt-5",
                                    },
                                },
                            ),
                            (
                                "error",
                                {
                                    "type": "error",
                                    "error": {
                                        "code": "server_error",
                                        "message": "temporary upstream issue",
                                    },
                                },
                            ),
                        ),
                    ),
                    _FakeStreamResponse(
                        events=(
                            (
                                "response.completed",
                                {
                                    "type": "response.completed",
                                    "response": {
                                        "id": "resp_retry_2",
                                        "model": "gpt-5",
                                        "status": "completed",
                                        "output": [
                                            {
                                                "type": "message",
                                                "content": [
                                                    {
                                                        "type": "output_text",
                                                        "text": "recovered",
                                                    },
                                                ],
                                            },
                                        ],
                                    },
                                },
                            ),
                        ),
                    ),
                ],
            ) as post,
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_responses.sleep_before_openai_stream_retry",
            ),
        ):
            response = OpenAIResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "recovered")
        self.assertEqual(post.call_count, 2)

    def test_openai_responses_adapter_encodes_tool_history_items(self) -> None:
        profile = LlmProfile(
            id="writer-history",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Need docs"),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "call_hist_1",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    tool_call_id="call_hist_1",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content='{"hits":1}',
                    tool_call_id="call_hist_1",
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_hist_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [
                                            {
                                                "type": "output_text",
                                                "text": "done",
                                            },
                                        ],
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            response = OpenAIResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "done")
        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"],
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Need docs"}],
                },
                {
                    "type": "function_call",
                    "call_id": "call_hist_1",
                    "name": "search_docs",
                    "arguments": '{"query": "ddd"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_hist_1",
                    "output": '{"hits":1}',
                },
            ],
        )

    def test_openai_responses_adapter_sanitizes_tool_history_names(self) -> None:
        profile = LlmProfile(
            id="writer-history-alias",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Need docs"),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "call_hist_alias_1",
                        "name": "sample_api.search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    tool_call_id="call_hist_alias_1",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content='{"hits":1}',
                    tool_call_id="call_hist_alias_1",
                ),
            ),
            tool_schemas=(
                ToolSchema(
                    name="sample_api.search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_hist_alias_1",
                                "model": "gpt-5",
                                "status": "completed",
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [
                                            {
                                                "type": "output_text",
                                                "text": "done",
                                            },
                                        ],
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            response = OpenAIResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "done")
        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"][1]["name"],
            "sample_api_search_docs",
        )

    def test_openai_chat_compatible_adapter_shapes_request_and_result(self) -> None:
        profile = LlmProfile(
            id="local-chat",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="llama3.2",
            base_url="http://localhost:11434/v1",
            credential_binding_id="ollama-token",
            default_params=LlmDefaults(top_p=0.9, max_output_tokens=256),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Say hello"),
            ),
            tool_schemas=(
                ToolSchema(
                    name="echo_tool",
                    description="Echo text",
                    input_schema={"type": "object"},
                ),
            ),
            response_format={"type": "json_object"},
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_123",
                    "model": "llama3.2",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": "hello",
                                "tool_calls": [
                                    {
                                        "id": "call_chat_1",
                                        "function": {
                                            "name": "echo_tool",
                                            "arguments": '{"message":"hello"}',
                                        },
                                    },
                                ],
                            },
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 7,
                        "total_tokens": 16,
                    },
                },
            ),
        ) as post:
            response = OpenAIChatCompatibleAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "hello")
        self.assertEqual(response.result.tool_calls[0].name, "echo_tool")
        self.assertEqual(response.result.tool_calls[0].arguments, {"message": "hello"})
        self.assertEqual(response.result.finish_reason, "tool_calls")
        self.assertEqual(
            [item.kind for item in response.response_items],
            [
                LlmResponseItemKind.ASSISTANT_MESSAGE,
                LlmResponseItemKind.TOOL_CALL,
            ],
        )
        self.assertEqual(response.response_items[0].content_payload["text"], "hello")
        self.assertEqual(response.response_items[1].call_id, "call_chat_1")
        self.assertEqual(response.response_items[1].tool_name, "echo_tool")
        self.assertFalse(response.response_items[1].user_visible)

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer adapter-test-token")
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "user")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_object")
        self.assertEqual(kwargs["json"]["max_tokens"], 256)
        self.assertEqual(kwargs["json"]["tools"][0]["type"], "function")
        self.assertEqual(
            kwargs["json"]["tools"][0]["function"]["name"],
            "echo_tool",
        )
        self.assertEqual(
            kwargs["json"]["tools"][0]["function"]["parameters"],
            {"type": "object"},
        )

    def test_openai_chat_compatible_adapter_stream_invoke_emits_text_delta_and_completed(
        self,
    ) -> None:
        profile = LlmProfile(
            id="local-chat-stream",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5-35b",
            base_url="http://localhost:8010/v1",
            credential_binding_id="inline-vllm-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Say hello"),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "chat.completion.chunk",
                        {
                            "id": "chatcmpl_stream_1",
                            "model": "qwen3.5-35b",
                            "choices": [
                                {
                                    "delta": {"content": "你"},
                                    "finish_reason": None,
                                },
                            ],
                        },
                    ),
                    (
                        "chat.completion.chunk",
                        {
                            "id": "chatcmpl_stream_1",
                            "model": "qwen3.5-35b",
                            "choices": [
                                {
                                    "delta": {"content": "好"},
                                    "finish_reason": None,
                                },
                            ],
                        },
                    ),
                    (
                        "chat.completion.chunk",
                        {
                            "id": "chatcmpl_stream_1",
                            "model": "qwen3.5-35b",
                            "choices": [
                                {
                                    "delta": {},
                                    "finish_reason": "stop",
                                },
                            ],
                            "usage": {
                                "prompt_tokens": 4,
                                "completion_tokens": 2,
                                "total_tokens": 6,
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            events = list(OpenAIChatCompatibleAdapter().stream_invoke(profile, request))

        self.assertEqual(
            [event.type for event in events],
            ["text_delta", "text_delta", "completed"],
        )
        self.assertEqual(events[0].data["text"], "你")
        self.assertEqual(events[1].data["text"], "好")
        result = events[2].data["result"]
        self.assertEqual(result["text"], "你好")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["usage"]["total_tokens"], 6)
        self.assertEqual(
            events[2].data["response_items"][0]["kind"],
            "assistant_message",
        )
        self.assertEqual(
            events[2].data["response_items"][0]["content_payload"]["text"],
            "你好",
        )

        _, kwargs = post.call_args
        self.assertTrue(kwargs["stream"])
        self.assertEqual(kwargs["headers"]["Accept"], "text/event-stream")
        self.assertTrue(kwargs["json"]["stream"])

    def test_openai_chat_compatible_adapter_stream_invoke_async_handles_json_fallback(
        self,
    ) -> None:
        profile = LlmProfile(
            id="local-chat-async-json",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5-35b",
            base_url="http://localhost:8010/v1",
            credential_binding_id="inline-vllm-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Say hello"),
            ),
        )
        _FakeAsyncClient.response = _FakeAsyncResponse(
            headers={"content-type": "application/json"},
            payload={
                "id": "chatcmpl_async_json_1",
                "model": "qwen3.5-35b",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "async hello"},
                    },
                ],
            },
        )

        async def collect_events():
            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.httpx.AsyncClient",
                _FakeAsyncClient,
            ):
                return [
                    event
                    async for event in OpenAIChatCompatibleAdapter().stream_invoke_async(
                        profile,
                        request,
                    )
                ]

        events = asyncio.run(collect_events())

        self.assertEqual([event.type for event in events], ["completed"])
        self.assertEqual(events[0].data["result"]["text"], "async hello")
        self.assertEqual(
            events[0].data["response_items"][0]["kind"],
            "assistant_message",
        )
        self.assertEqual(
            events[0].data["response_items"][0]["content_payload"]["text"],
            "async hello",
        )
        method, url, kwargs = _FakeAsyncClient.instances[0].requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "http://localhost:8010/v1/chat/completions")
        self.assertTrue(kwargs["json"]["stream"])

    def test_openai_chat_compatible_adapter_does_not_buffer_sse_body(self) -> None:
        class StrictStreamResponse:
            status_code = 200
            headers = {"Content-Type": "text/event-stream; charset=utf-8"}

            @property
            def text(self) -> str:
                raise AssertionError("SSE body should not be read through response.text")

            def iter_lines(
                self,
                chunk_size: int | None = None,
                decode_unicode: bool = False,
            ):  # noqa: ANN001
                self.chunk_size = chunk_size
                del decode_unicode
                yield b'data: {"id":"chatcmpl_stream_2","model":"qwen","choices":[{"delta":{"content":"A"},"finish_reason":null}]}'
                yield b""
                yield b'data: {"id":"chatcmpl_stream_2","model":"qwen","choices":[{"delta":{},"finish_reason":"stop"}]}'
                yield b""

        profile = LlmProfile(
            id="local-chat-stream-strict",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen",
            base_url="http://localhost:8010/v1",
            credential_binding_id="inline-vllm-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Say A"),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=StrictStreamResponse(),
        ):
            events = list(OpenAIChatCompatibleAdapter().stream_invoke(profile, request))

        self.assertEqual([event.type for event in events], ["text_delta", "completed"])
        self.assertEqual(events[0].data["text"], "A")

    def test_openai_chat_compatible_adapter_merges_extra_body_from_defaults_and_overrides(
        self,
    ) -> None:
        profile = LlmProfile(
            id="qwen-chat",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5-35b",
            base_url="http://localhost:8010/v1",
            credential_binding_id="empty-token",
            default_params=LlmDefaults(
                temperature=0.7,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    "seed": 7,
                },
            ),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Say hello"),
            ),
            overrides={
                "max_tokens": 80,
                "extra_body": {
                    "chat_template_kwargs": {"user_role": "user"},
                    "repetition_penalty": 1.05,
                },
            },
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_qwen_1",
                    "model": "qwen3.5-35b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "你好",
                                "tool_calls": [],
                            },
                        },
                    ],
                },
            ),
        ) as post:
            response = OpenAIChatCompatibleAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "你好")
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["temperature"], 0.7)
        self.assertEqual(kwargs["json"]["max_tokens"], 80)
        self.assertEqual(kwargs["json"]["seed"], 7)
        self.assertEqual(kwargs["json"]["repetition_penalty"], 1.05)
        self.assertEqual(
            kwargs["json"]["chat_template_kwargs"],
            {"enable_thinking": False, "user_role": "user"},
        )
        self.assertNotIn("extra_body", kwargs["json"])

    def test_openai_chat_compatible_adapter_encodes_tool_history_messages(self) -> None:
        profile = LlmProfile(
            id="local-chat-history",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="llama3.2",
            credential_binding_id="compat-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Need docs"),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content="I'll inspect the docs.",
                ),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "call_chat_hist_1",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    tool_call_id="call_chat_hist_1",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content='{"hits":1}',
                    tool_call_id="call_chat_hist_1",
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_hist_1",
                    "model": "llama3.2",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "done",
                                "tool_calls": [],
                            },
                        },
                    ],
                },
            ),
        ) as post:
            response = OpenAIChatCompatibleAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "done")
        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["messages"],
            [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Need docs"}],
                },
                {
                    "role": "assistant",
                    "content": "I'll inspect the docs.",
                    "tool_calls": [
                        {
                            "id": "call_chat_hist_1",
                            "type": "function",
                            "function": {
                                "name": "search_docs",
                                "arguments": '{"query": "ddd"}',
                            },
                        },
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_chat_hist_1",
                    "content": '{"hits":1}',
                },
            ],
        )

    def test_openai_chat_compatible_adapter_parses_xmlish_tool_call_content(self) -> None:
        profile = LlmProfile(
            id="local-chat-xmlish-tools",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5-35b",
            credential_binding_id="compat-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Call a tool."),
            ),
            tool_schemas=(
                ToolSchema(
                    name="echo_tool",
                    description="Echo text",
                    input_schema={"type": "object"},
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_xml_tool_1",
                    "model": "qwen3.5-35b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": (
                                    "<tool_call>\n"
                                    "<function=echo_tool>\n"
                                    "<parameter=text>\n"
                                    "auto-ping\n"
                                    "</parameter>\n"
                                    "</function>\n"
                                    "</tool_call>"
                                ),
                                "tool_calls": [],
                            },
                        },
                    ],
                },
            ),
        ):
            response = OpenAIChatCompatibleAdapter().invoke(profile, request)

        self.assertIsNone(response.result.text)
        self.assertEqual(len(response.result.tool_calls), 1)
        self.assertEqual(response.result.tool_calls[0].name, "echo_tool")
        self.assertEqual(
            response.result.tool_calls[0].arguments,
            {"text": "auto-ping"},
        )

    def test_openai_chat_compatible_adapter_merges_system_messages_to_single_front_message(
        self,
    ) -> None:
        profile = LlmProfile(
            id="local-chat-system-order",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5-35b",
            credential_binding_id="compat-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
                LlmMessage(role=LlmMessageRole.SYSTEM, content="system-late"),
                LlmMessage(role=LlmMessageRole.ASSISTANT, content="hi"),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_system_order_1",
                    "model": "qwen3.5-35b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "ok", "tool_calls": []},
                        },
                    ],
                },
            ),
        ) as post:
            response = OpenAIChatCompatibleAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "ok")
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "system")
        self.assertEqual(kwargs["json"]["messages"][0]["content"], "system-late")
        self.assertEqual(kwargs["json"]["messages"][1]["role"], "user")
        self.assertEqual(kwargs["json"]["messages"][2]["role"], "assistant")
        self.assertEqual(len(kwargs["json"]["messages"]), 3)

    def test_openai_chat_compatible_adapter_combines_multiple_system_messages(self) -> None:
        profile = LlmProfile(
            id="local-chat-multi-system",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5-35b",
            credential_binding_id="compat-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="sys1"),
                LlmMessage(role=LlmMessageRole.SYSTEM, content="sys2"),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_multi_system_1",
                    "model": "qwen3.5-35b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "ok", "tool_calls": []},
                        },
                    ],
                },
            ),
        ) as post:
            response = OpenAIChatCompatibleAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "ok")
        _, kwargs = post.call_args
        self.assertEqual(len(kwargs["json"]["messages"]), 2)
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "system")
        self.assertEqual(kwargs["json"]["messages"][0]["content"], "sys1\n\nsys2")
        self.assertEqual(kwargs["json"]["messages"][1]["role"], "user")

    def test_openai_chat_compatible_adapter_encodes_user_file_blocks(self) -> None:
        profile = LlmProfile(
            id="chat-compatible-file",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="gpt-4.1",
            credential_binding_id="inline-chat-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {"type": "text", "text": "Review this PDF."},
                        {
                            "type": "file",
                            "data": "JVBERi0xLjQKZmFrZQ==",
                            "mime_type": "application/pdf",
                            "name": "review.pdf",
                        },
                    ],
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chat-file-1",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "ok"},
                        },
                    ],
                },
            ),
        ) as post:
            OpenAIChatCompatibleAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["messages"][0]["content"],
            [
                {"type": "text", "text": "Review this PDF."},
                {
                    "type": "file",
                    "file": {
                        "file_data": "JVBERi0xLjQKZmFrZQ==",
                        "filename": "review.pdf",
                    },
                },
            ],
        )

    def test_openai_chat_compatible_adapter_sanitizes_tool_names_and_restores_tool_calls(self) -> None:
        profile = LlmProfile(
            id="local-chat-tool-alias",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="llama3.2",
            credential_binding_id="compat-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Need docs"),
            ),
            tool_schemas=(
                ToolSchema(
                    name="sample_api.search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_tool_alias_1",
                    "model": "llama3.2",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_chat_alias_1",
                                        "function": {
                                            "name": "sample_api_search_docs",
                                            "arguments": '{"query":"ddd"}',
                                        },
                                    },
                                ],
                            },
                        },
                    ],
                },
            ),
        ) as post:
            response = OpenAIChatCompatibleAdapter().invoke(profile, request)

        self.assertEqual(
            response.result.tool_calls[0].name,
            "sample_api.search_docs",
        )
        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["tools"][0]["function"]["name"],
            "sample_api_search_docs",
        )

    def test_openai_codex_responses_adapter_uses_resolved_credential_and_sse(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            auth_path = Path(tempdir) / "auth.json"
            auth_path.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": None,
                        "tokens": {
                            "access_token": "codex-access-token",
                            "refresh_token": "codex-refresh-token",
                            "account_id": "acct_123",
                        },
                    },
                ),
                encoding="utf-8",
            )

            profile = LlmProfile(
                id="codex-agent",
                provider=LlmProviderKind.OPENAI_CODEX,
                api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
                model_name="gpt-5-codex",
                model_family=LlmModelFamily.CODEX,
                credential_binding_id="codex-auth-json",
                default_params=LlmDefaults(reasoning_effort="medium"),
            )
            request = _adapter_request(
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.SYSTEM,
                        content="You are a concise coding assistant.",
                    ),
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Reply with codex-ok.",
                    ),
                ),
                overrides={"reasoning": {"summary": "auto"}},
            )

            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.requests.post",
                return_value=_FakeStreamResponse(
                    events=(
                        (
                            "response.created",
                            {
                                "type": "response.created",
                                "response": {
                                    "id": "resp_codex_1",
                                    "status": "in_progress",
                                    "model": "gpt-5.1-codex",
                                },
                            },
                        ),
                        (
                            "response.completed",
                            {
                                "type": "response.completed",
                                "response": {
                                    "id": "resp_codex_1",
                                    "status": "completed",
                                    "model": "gpt-5.1-codex",
                                    "output": [
                                        {
                                            "type": "message",
                                            "content": [
                                                {
                                                    "type": "output_text",
                                                    "text": "codex-ok",
                                                },
                                            ],
                                        },
                                        {
                                            "type": "function_call",
                                            "call_id": "call_codex_1",
                                            "name": "search_docs",
                                            "arguments": '{"query":"codex"}',
                                        },
                                    ],
                                    "usage": {
                                        "input_tokens": 10,
                                        "output_tokens": 4,
                                        "total_tokens": 14,
                                        "output_tokens_details": {
                                            "reasoning_tokens": 2,
                                        },
                                    },
                                },
                            },
                        ),
                    ),
                ),
            ) as post:
                response = OpenAICodexResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.provider_request_id, "resp_codex_1")
        self.assertEqual(response.result.text, "codex-ok")
        self.assertEqual(response.result.tool_calls[0].name, "search_docs")
        self.assertEqual(response.result.tool_calls[0].arguments, {"query": "codex"})
        self.assertEqual(response.result.usage.reasoning_tokens, 2)
        self.assertEqual(response.result.metadata["transport"], "sse")
        self.assertEqual(response.response_items[0].kind, LlmResponseItemKind.ASSISTANT_MESSAGE)
        self.assertEqual(response.response_items[0].phase, LlmMessagePhase.FINAL_ANSWER)
        self.assertEqual(response.response_items[1].kind, LlmResponseItemKind.TOOL_CALL)
        self.assertEqual(response.response_items[1].tool_name, "search_docs")
        self.assertEqual(response.continuation.reason, LlmContinuationReason.TOOL_CALL)

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer adapter-test-token")
        self.assertEqual(kwargs["headers"]["Accept"], "text/event-stream")
        self.assertEqual(kwargs["json"]["instructions"], "You are a concise coding assistant.")
        self.assertEqual(
            kwargs["json"]["reasoning"],
            {"effort": "medium", "summary": "auto"},
        )
        self.assertEqual(
            kwargs["json"]["input"],
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Reply with codex-ok."}],
                },
            ],
        )
        self.assertTrue(kwargs["json"]["stream"])

    def test_openai_codex_responses_adapter_previews_provider_request(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
            default_params=LlmDefaults(reasoning_effort="medium"),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="System instructions.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Use the command tool.",
                ),
            ),
            tool_schemas=(
                ToolSchema(
                    name="exec",
                    description="Run a command",
                    input_schema={
                        "type": "object",
                        "properties": {"cmd": {"type": "string"}},
                    },
                ),
            ),
            overrides={
                "parallel_tool_calls": True,
                "prompt_cache_key": "session-stable-key",
                "text": {"verbosity": "low"},
                "include": ["reasoning.encrypted_content"],
            },
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
                previous_invocation_id="inv_previous",
                provider_family="openai_codex_responses",
            ),
        )

        preview = OpenAICodexResponsesAdapter().preview_request(profile, request)

        self.assertEqual(preview["preview_source"], "provider_adapter")
        self.assertEqual(
            preview["endpoint"],
            "https://chatgpt.com/backend-api/codex/responses",
        )
        self.assertEqual(preview["input_item_count"], 1)
        self.assertEqual(preview["tool_count"], 1)
        self.assertTrue(preview["has_previous_response_id"])
        self.assertEqual(preview["previous_response_id"], "resp_previous")
        self.assertIn("instructions", preview["payload_keys"])
        self.assertIn("previous_response_id", preview["payload_keys"])
        self.assertIn("type", preview["payload_keys"])
        self.assertIn("tools", preview["payload_keys"])
        self.assertEqual(
            preview["option_summary"]["parallel_tool_calls"],
            True,
        )
        self.assertEqual(
            preview["option_summary"]["prompt_cache_key"],
            "session-stable-key",
        )
        self.assertEqual(
            preview["option_summary"]["text"],
            {"verbosity": "low"},
        )

    def test_openai_codex_responses_continuation_sends_tool_output_delta(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="Runtime tree that should not be replayed.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Original task that should not be replayed.",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content="tool completed with evidence",
                    tool_call_id="call_123",
                ),
            ),
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
            ),
        )

        preview = OpenAICodexResponsesAdapter().preview_request(profile, request)

        self.assertEqual(preview["previous_response_id"], "resp_previous")
        self.assertEqual(preview["input_item_count"], 1)
        self.assertEqual(
            preview["input_item_types"],
            ("function_call_output",),
        )
        self.assertEqual(
            preview["payload_preview"]["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": "tool completed with evidence",
                },
            ],
        )

    def test_openai_codex_responses_adapter_sanitizes_tool_names_and_restores_tool_calls(self) -> None:
        profile = LlmProfile(
            id="codex-tool-alias",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5-codex",
            model_family=LlmModelFamily.CODEX,
            credential_binding_id="codex-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Need docs",
                ),
            ),
            tool_schemas=(
                ToolSchema(
                    name="sample_api.search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_codex_tool_alias_1",
                                "status": "completed",
                                "model": "gpt-5.1-codex",
                                "output": [
                                    {
                                        "type": "function_call",
                                        "call_id": "call_codex_alias_1",
                                        "name": "sample_api_search_docs",
                                        "arguments": '{"query":"ddd"}',
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            response = OpenAICodexResponsesAdapter().invoke(profile, request)

        self.assertEqual(
            response.result.tool_calls[0].name,
            "sample_api.search_docs",
        )
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["tools"][0]["name"], "sample_api_search_docs")

    def test_openai_codex_responses_adapter_stream_invoke_emits_text_delta_and_completed(self) -> None:
        profile = LlmProfile(
            id="codex-stream",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5-codex",
            model_family=LlmModelFamily.CODEX,
            credential_binding_id="codex-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Reply with codex-stream.",
                ),
            ),
        )

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
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "output_index": 0,
                            "item": {
                                "id": "msg_codex_stream",
                                "type": "message",
                                "status": "completed",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "codex-stream",
                                    },
                                ],
                            },
                        },
                    ),
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_codex_stream",
                                "status": "completed",
                                "model": "gpt-5.1-codex",
                                "output": [],
                            },
                        },
                    ),
                ),
            ),
        ):
            events = list(OpenAICodexResponsesAdapter().stream_invoke(profile, request))

        self.assertEqual(
            [event.type for event in events],
            ["text_delta", "item_completed", "completed"],
        )
        self.assertEqual(events[0].data["text"], "codex-")
        self.assertEqual(events[1].data["item_id"], "msg_codex_stream")
        self.assertEqual(events[2].data["result"]["text"], "codex-stream")

    def test_openai_codex_responses_adapter_stream_invoke_async_uses_async_stream(self) -> None:
        profile = LlmProfile(
            id="codex-stream-async",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5-codex",
            model_family=LlmModelFamily.CODEX,
            credential_binding_id="codex-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Reply with async codex stream.",
                ),
            ),
        )
        _FakeAsyncClient.response = _FakeAsyncResponse(
            headers={"content-type": "text/event-stream"},
            events=(
                (
                    "response.output_item.done",
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": {
                            "id": "msg_codex_stream_async",
                            "type": "message",
                            "status": "completed",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "async-codex-stream",
                                },
                            ],
                        },
                    },
                ),
                (
                    "response.completed",
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_codex_stream_async",
                            "status": "completed",
                            "model": "gpt-5.1-codex",
                            "output": [],
                        },
                    },
                ),
            ),
        )

        async def collect_events():
            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.httpx.AsyncClient",
                _FakeAsyncClient,
            ):
                return [
                    event
                    async for event in OpenAICodexResponsesAdapter().stream_invoke_async(
                        profile,
                        request,
                    )
                ]

        events = asyncio.run(collect_events())

        self.assertEqual([event.type for event in events], ["item_completed", "completed"])
        self.assertEqual(events[0].data["item_id"], "msg_codex_stream_async")
        self.assertEqual(events[1].data["result"]["text"], "async-codex-stream")
        method, url, kwargs = _FakeAsyncClient.instances[0].requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://chatgpt.com/backend-api/codex/responses")
        self.assertTrue(kwargs["json"]["stream"])

    def test_openai_codex_responses_adapter_stream_invoke_uses_data_type_without_event_line(self) -> None:
        profile = LlmProfile(
            id="codex-stream-data-type",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.4",
            model_family=LlmModelFamily.CODEX,
            credential_binding_id="codex-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Reply with codex data type stream.",
                ),
            ),
        )
        stream_response = _FakeStreamResponse(
            events=(
                (
                    None,
                    {
                        "type": "response.output_text.delta",
                        "delta": "data-",
                    },
                ),
                (
                    None,
                    {
                        "type": "response.output_text.delta",
                        "text": "type",
                    },
                ),
                (
                    None,
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": {
                            "id": "msg_codex_stream_data_type",
                            "type": "message",
                            "status": "completed",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "data-type",
                                },
                            ],
                        },
                    },
                ),
                (
                    None,
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "resp_codex_stream_data_type",
                            "status": "completed",
                            "model": "gpt-5.4",
                            "output": [],
                        },
                    },
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.requests.post",
            return_value=stream_response,
        ):
            events = list(OpenAICodexResponsesAdapter().stream_invoke(profile, request))

        self.assertEqual(
            [event.type for event in events],
            ["text_delta", "text_delta", "item_completed", "completed"],
        )
        self.assertEqual(events[0].data["text"], "data-")
        self.assertEqual(events[1].data["text"], "type")
        self.assertEqual(events[2].data["item_id"], "msg_codex_stream_data_type")
        self.assertEqual(events[3].data["result"]["text"], "data-type")
        self.assertEqual(stream_response.iter_lines_chunk_size, 1)

    def test_openai_codex_responses_adapter_retries_transient_server_error_before_output(self) -> None:
        profile = LlmProfile(
            id="codex-retry",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5-codex",
            model_family=LlmModelFamily.CODEX,
            credential_binding_id="codex-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Retry codex."),
            ),
        )

        with (
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.requests.post",
                side_effect=[
                    _FakeStreamResponse(
                        events=(
                            (
                                "response.created",
                                {
                                    "type": "response.created",
                                    "response": {
                                        "id": "resp_codex_retry_1",
                                        "status": "in_progress",
                                        "model": "gpt-5-codex",
                                    },
                                },
                            ),
                            (
                                "error",
                                {
                                    "type": "error",
                                    "error": {
                                        "code": "server_error",
                                        "message": "temporary codex issue",
                                    },
                                },
                            ),
                        ),
                    ),
                    _FakeStreamResponse(
                        events=(
                            (
                                "response.completed",
                                {
                                    "type": "response.completed",
                                    "response": {
                                        "id": "resp_codex_retry_2",
                                        "status": "completed",
                                        "model": "gpt-5-codex",
                                        "output": [
                                            {
                                                "type": "message",
                                                "content": [
                                                    {
                                                        "type": "output_text",
                                                        "text": "codex-recovered",
                                                    },
                                                ],
                                            },
                                        ],
                                    },
                                },
                            ),
                        ),
                    ),
                ],
            ) as post,
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.sleep_before_openai_stream_retry",
            ),
        ):
            response = OpenAICodexResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "codex-recovered")
        self.assertEqual(post.call_count, 2)

    def test_anthropic_messages_adapter_shapes_request_and_result(self) -> None:
        profile = LlmProfile(
            id="claude",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-api-key",
            default_params=LlmDefaults(temperature=0.3, top_p=0.8),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="Return concise answers.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Need docs",
                ),
            ),
            tool_schemas=(
                ToolSchema(
                    name="search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.anthropic_messages.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "msg_123",
                    "model": "claude-sonnet-4-5",
                    "stop_reason": "tool_use",
                    "content": [
                        {"type": "text", "text": "I'll inspect the docs."},
                        {
                            "type": "tool_use",
                            "id": "toolu_123",
                            "name": "search_docs",
                            "input": {"query": "ddd"},
                        },
                    ],
                    "usage": {
                        "input_tokens": 17,
                        "output_tokens": 19,
                    },
                },
            ),
        ) as post:
            response = AnthropicMessagesAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "I'll inspect the docs.")
        self.assertEqual(response.result.tool_calls[0].name, "search_docs")
        self.assertEqual(response.result.tool_calls[0].arguments, {"query": "ddd"})
        self.assertEqual(response.result.usage.input_tokens, 17)
        self.assertEqual(response.result.finish_reason, "tool_use")
        self.assertEqual(
            [item.kind for item in response.response_items],
            [
                LlmResponseItemKind.ASSISTANT_MESSAGE,
                LlmResponseItemKind.TOOL_CALL,
            ],
        )
        self.assertEqual(
            response.response_items[0].content_payload["text"],
            "I'll inspect the docs.",
        )
        self.assertEqual(response.response_items[1].call_id, "toolu_123")
        self.assertEqual(response.response_items[1].tool_name, "search_docs")

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["x-api-key"], "adapter-test-token")
        self.assertEqual(kwargs["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(kwargs["json"]["system"], "Return concise answers.")
        self.assertEqual(kwargs["json"]["tools"][0]["name"], "search_docs")
        self.assertEqual(kwargs["json"]["max_tokens"], 1024)

    def test_anthropic_messages_adapter_invoke_async_uses_async_http(self) -> None:
        profile = LlmProfile(
            id="claude-async",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-api-key",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Need async docs",
                ),
            ),
        )
        _FakeAsyncClient.response = _FakeAsyncResponse(
            payload={
                "id": "msg_async_123",
                "model": "claude-sonnet-4-5",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "async anthropic"}],
            },
        )

        async def invoke():
            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.anthropic_messages.httpx.AsyncClient",
                _FakeAsyncClient,
            ):
                return await AnthropicMessagesAdapter().invoke_async(profile, request)

        response = asyncio.run(invoke())

        self.assertEqual(response.provider_request_id, "msg_async_123")
        self.assertEqual(response.result.text, "async anthropic")
        method, url, kwargs = _FakeAsyncClient.instances[0].requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(kwargs["headers"]["x-api-key"], "adapter-test-token")

    def test_anthropic_messages_adapter_encodes_tool_history_messages(self) -> None:
        profile = LlmProfile(
            id="claude-history",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Need docs"),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content="I'll inspect the docs.",
                ),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "toolu_hist_1",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    tool_call_id="toolu_hist_1",
                ),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "toolu_hist_2",
                        "name": "fetch_file",
                        "arguments": {"path": "README.md"},
                    },
                    tool_call_id="toolu_hist_2",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content='{"hits":1}',
                    tool_call_id="toolu_hist_1",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content='{"path":"README.md"}',
                    tool_call_id="toolu_hist_2",
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.anthropic_messages.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "msg_hist_1",
                    "model": "claude-sonnet-4-5",
                    "stop_reason": "end_turn",
                    "content": [
                        {"type": "text", "text": "done"},
                    ],
                },
            ),
        ) as post:
            response = AnthropicMessagesAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "done")
        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["messages"],
            [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Need docs"}],
                },
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "I'll inspect the docs."},
                        {
                            "type": "tool_use",
                            "id": "toolu_hist_1",
                            "name": "search_docs",
                            "input": {"query": "ddd"},
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_hist_2",
                            "name": "fetch_file",
                            "input": {"path": "README.md"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_hist_1",
                            "content": '{"hits":1}',
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_hist_2",
                            "content": '{"path":"README.md"}',
                        },
                    ],
                },
            ],
        )

    def test_anthropic_messages_adapter_encodes_user_pdf_blocks(self) -> None:
        profile = LlmProfile(
            id="claude-pdf",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {"type": "text", "text": "Summarize this PDF."},
                        {
                            "type": "file",
                            "data": "JVBERi0xLjQKZmFrZQ==",
                            "mime_type": "application/pdf",
                            "name": "summary.pdf",
                        },
                    ],
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.anthropic_messages.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "msg_pdf_1",
                    "model": "claude-sonnet-4-5",
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "done"}],
                },
            ),
        ) as post:
            AnthropicMessagesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["messages"],
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Summarize this PDF."},
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": "JVBERi0xLjQKZmFrZQ==",
                            },
                            "title": "summary.pdf",
                        },
                    ],
                },
            ],
        )

    def test_anthropic_messages_adapter_rejects_non_pdf_file_blocks(self) -> None:
        profile = LlmProfile(
            id="claude-non-pdf",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {
                            "type": "file",
                            "data": "UEsDBAoAAAAAA",
                            "mime_type": "application/zip",
                            "name": "archive.zip",
                        },
                    ],
                ),
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "only supports PDF and text-like file content blocks",
        ):
            AnthropicMessagesAdapter().invoke(profile, request)

    def test_anthropic_messages_adapter_encodes_text_file_blocks_as_text(self) -> None:
        profile = LlmProfile(
            id="claude-text-file",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {
                            "type": "file",
                            "data": "IyBUaXRsZQoKSGVsbG8=",
                            "mime_type": "text/markdown",
                            "name": "notes.md",
                        },
                    ],
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.anthropic_messages.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "msg_text_file_1",
                    "model": "claude-sonnet-4-5",
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "done"}],
                },
            ),
        ) as post:
            AnthropicMessagesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["messages"],
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "[file:notes.md]\n# Title\n\nHello",
                        },
                    ],
                },
            ],
        )

    def test_gemini_generate_content_adapter_shapes_request_and_result(self) -> None:
        profile = LlmProfile(
            id="gemini",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding_id="gemini-api-key",
            default_params=LlmDefaults(
                temperature=0.1,
                max_output_tokens=300,
            ),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="Use tools when needed.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Find documentation",
                ),
            ),
            tool_schemas=(
                ToolSchema(
                    name="search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
            overrides={"toolConfig": {"functionCallingConfig": {"mode": "AUTO"}}},
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content.requests.post",
            return_value=_FakeResponse(
                payload={
                    "responseId": "gemini-response-1",
                    "modelVersion": "gemini-2.5-pro",
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {"text": "I'll search the docs."},
                                    {
                                        "functionCall": {
                                            "name": "search_docs",
                                            "args": {"query": "ddd"},
                                        },
                                    },
                                ],
                            },
                        },
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 14,
                        "candidatesTokenCount": 6,
                        "totalTokenCount": 20,
                    },
                },
            ),
        ) as post:
            response = GeminiGenerateContentAdapter().invoke(profile, request)

        self.assertEqual(response.provider_request_id, "gemini-response-1")
        self.assertEqual(response.result.text, "I'll search the docs.")
        self.assertEqual(response.result.tool_calls[0].name, "search_docs")
        self.assertEqual(response.result.tool_calls[0].arguments, {"query": "ddd"})
        self.assertEqual(response.result.usage.total_tokens, 20)
        self.assertEqual(
            [item.kind for item in response.response_items],
            [
                LlmResponseItemKind.ASSISTANT_MESSAGE,
                LlmResponseItemKind.TOOL_CALL,
            ],
        )
        self.assertEqual(
            response.response_items[0].content_payload["text"],
            "I'll search the docs.",
        )
        self.assertEqual(response.response_items[1].tool_name, "search_docs")
        self.assertEqual(
            response.response_items[1].content_payload["arguments"],
            {"query": "ddd"},
        )

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "adapter-test-token")
        self.assertEqual(
            kwargs["json"]["system_instruction"]["parts"][0]["text"],
            "Use tools when needed.",
        )
        self.assertEqual(kwargs["json"]["generationConfig"]["maxOutputTokens"], 300)
        self.assertEqual(
            kwargs["json"]["toolConfig"]["functionCallingConfig"]["mode"],
            "AUTO",
        )

    def test_gemini_generate_content_adapter_invoke_async_uses_async_http(self) -> None:
        profile = LlmProfile(
            id="gemini-async",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding_id="gemini-api-key",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Find docs async",
                ),
            ),
        )
        _FakeAsyncClient.response = _FakeAsyncResponse(
            payload={
                "responseId": "gemini-response-async",
                "modelVersion": "gemini-2.5-pro",
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [{"text": "async gemini"}],
                        },
                    },
                ],
            },
        )

        async def invoke():
            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content.httpx.AsyncClient",
                _FakeAsyncClient,
            ):
                return await GeminiGenerateContentAdapter().invoke_async(profile, request)

        response = asyncio.run(invoke())

        self.assertEqual(response.provider_request_id, "gemini-response-async")
        self.assertEqual(response.result.text, "async gemini")
        method, url, kwargs = _FakeAsyncClient.instances[0].requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(
            url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
        )
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "adapter-test-token")

    def test_gemini_generate_content_adapter_encodes_tool_history_messages(self) -> None:
        profile = LlmProfile(
            id="gemini-history",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding_id="gemini-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Need docs"),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content="I'll inspect the docs.",
                ),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content={
                        "type": "function_call",
                        "call_id": "call_gemini_1",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                    tool_call_id="call_gemini_1",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content='{"hits":1}',
                    name="search_docs",
                    tool_call_id="call_gemini_1",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content="raw tool output",
                    name="echo_tool",
                    tool_call_id="call_gemini_2",
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content.requests.post",
            return_value=_FakeResponse(
                payload={
                    "responseId": "gemini-history-1",
                    "modelVersion": "gemini-2.5-pro",
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "done"}]},
                        },
                    ],
                },
            ),
        ) as post:
            response = GeminiGenerateContentAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "done")
        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["contents"],
            [
                {
                    "role": "user",
                    "parts": [{"text": "Need docs"}],
                },
                {
                    "role": "model",
                    "parts": [
                        {"text": "I'll inspect the docs."},
                        {
                            "functionCall": {
                                "id": "call_gemini_1",
                                "name": "search_docs",
                                "args": {"query": "ddd"},
                            },
                        },
                    ],
                },
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": "call_gemini_1",
                                "name": "search_docs",
                                "response": {"result": {"hits": 1}},
                            },
                        },
                        {
                            "functionResponse": {
                                "id": "call_gemini_2",
                                "name": "echo_tool",
                                "response": {"result": "raw tool output"},
                            },
                        },
                    ],
                },
            ],
        )

    def test_gemini_generate_content_adapter_encodes_user_file_blocks(self) -> None:
        profile = LlmProfile(
            id="gemini-file",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding_id="gemini-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content=[
                        {"type": "text", "text": "Read this PDF."},
                        {
                            "type": "file",
                            "data": "JVBERi0xLjQKZmFrZQ==",
                            "mime_type": "application/pdf",
                            "name": "paper.pdf",
                        },
                    ],
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content.requests.post",
            return_value=_FakeResponse(
                payload={
                    "responseId": "gemini-file-1",
                    "modelVersion": "gemini-2.5-pro",
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "done"}]},
                        },
                    ],
                },
            ),
        ) as post:
            GeminiGenerateContentAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["contents"],
            [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Read this PDF."},
                        {
                            "inlineData": {
                                "mimeType": "application/pdf",
                                "data": "JVBERi0xLjQKZmFrZQ==",
                            },
                        },
                    ],
                },
            ],
        )
