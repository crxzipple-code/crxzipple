from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from crxzipple.modules.llm.application import LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmContinuationReason,
    LlmDefaults,
    LlmInputItem,
    LlmInputItemKind,
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
from crxzipple.modules.llm.infrastructure.adapters.provider_message_common import (
    projected_input_items_from_messages,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_openai_message_projection import (
    openai_response_projected_input_items,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_response_projection import (
    build_openai_response_items,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderWireRequest,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    openai_provider_payload_fingerprint,
    openai_response_input_fingerprints,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import openai_tool_schema


def _adapter_request(**kwargs) -> LlmAdapterRequest:  # noqa: ANN003
    codex_input = bool(kwargs.pop("codex_input", False))
    kwargs.setdefault("invocation_id", "adapter-test-invocation")
    kwargs.setdefault("resolved_credential", "adapter-test-token")
    if "input_items" not in kwargs and kwargs.get("messages"):
        messages = tuple(kwargs["messages"])
        if codex_input:
            messages = tuple(
                message
                for message in messages
                if message.role != LlmMessageRole.SYSTEM
            )
        kwargs["input_items"] = tuple(
            projected_input_items_from_messages(messages),
        )
    return LlmAdapterRequest(**kwargs)


class OpenAIResponseItemMappingTests(unittest.TestCase):
    def test_openai_message_response_items_preserve_provider_phase(self) -> None:
        items = build_openai_response_items(
            invocation_id="phase-invocation",
            response_payload={
                "output": [
                    {
                        "type": "message",
                        "id": "msg-commentary",
                        "role": "assistant",
                        "phase": "commentary",
                        "content": [
                            {"type": "output_text", "text": "still working"},
                        ],
                    },
                    {
                        "type": "message",
                        "id": "msg-final",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [
                            {"type": "output_text", "text": "done"},
                        ],
                    },
                    {
                        "type": "message",
                        "id": "msg-unknown",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "untagged"},
                        ],
                    },
                ],
            },
        )

        self.assertEqual(
            [item.phase for item in items],
            [
                LlmMessagePhase.COMMENTARY,
                LlmMessagePhase.FINAL_ANSWER,
                LlmMessagePhase.UNKNOWN,
            ],
        )
        self.assertEqual(items[0].provider_payload["phase"], "commentary")
        self.assertEqual(items[0].content_payload["text"], "still working")


def _openai_input_fingerprints_for_messages(
    messages: tuple[LlmMessage, ...],
    *,
    take: int | None = None,
) -> tuple[str, ...]:
    items = openai_response_projected_input_items(
        projected_input_items_from_messages(
            tuple(message for message in messages if message.role != LlmMessageRole.SYSTEM),
        ),
    )
    if take is not None:
        items = items[:take]
    return openai_response_input_fingerprints(items)


def _codex_surface_fingerprints(
    messages: tuple[LlmMessage, ...],
    *,
    tool_schemas: tuple[ToolSchema, ...] = (),
) -> dict[str, object]:
    system_messages = [
        str(message.content)
        for message in messages
        if message.role == LlmMessageRole.SYSTEM
    ]
    instructions = (
        "\n\n".join(system_messages)
        if system_messages
        else OpenAICodexResponsesAdapter.DEFAULT_INSTRUCTIONS
    )
    return {
        "instructions_fingerprint": openai_provider_payload_fingerprint(instructions),
        "tool_fingerprints": tuple(
            openai_provider_payload_fingerprint(openai_tool_schema(schema))
            for schema in tool_schemas
        ),
    }


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


class _FakeWebSocket:
    def __init__(self, messages: tuple[dict[str, object], ...]) -> None:
        self._messages = [json.dumps(message) for message in messages]
        self.sent: list[str] = []
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self) -> str | None:
        if not self._messages:
            return None
        return self._messages.pop(0)

    def close(self) -> None:
        self.closed = True


class _BrokenPipeOnSendWebSocket(_FakeWebSocket):
    def send(self, payload: str) -> None:
        self.sent.append(payload)
        raise BrokenPipeError(32, "Broken pipe")


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

    def test_openai_responses_preview_includes_surface_fingerprints(self) -> None:
        profile = LlmProfile(
            id="writer-surface-preview",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Check the runtime."),
            ),
            tool_schemas=(
                ToolSchema(
                    name="command.exec",
                    description="Run a command",
                    input_schema={"type": "object"},
                ),
            ),
            request_metadata={
                "request_render_snapshot_id": "ctxsnap_provider_1",
                "request_render_snapshot": {
                    "snapshot_id": "ctxsnap_provider_1",
                    "tree_schema_version": "2026-06-11",
                    "included_node_ids": ["runtime.contract", "tools.exec"],
                },
                "tool_surface_snapshot_id": "toolsnap_provider_1",
                "tool_surface": {
                    "id": "tool_surface:ctxsnap_provider_1",
                    "functions": [
                        {"name": "command.exec", "tool_id": "command.exec"},
                    ],
                    "mirrored_schema_names": ["command.exec"],
                },
                "runtime_input_filter": {
                    "mode": "request_render_session_refs",
                    "input_before_filter_count": 2,
                    "input_after_filter_count": 1,
                    "allowed_session_item_count": 1,
                    "dropped_input_item_count": 1,
                    "dropped_orphan_function_call_count": 1,
                    "dropped_orphan_function_call_ids": ["call-orphan"],
                },
            },
        )

        preview = OpenAIResponsesAdapter().preview_request(profile, request)

        self.assertEqual(preview["renderer_id"], "openai_responses")
        self.assertEqual(preview["render_strategy"], "full_wire_payload")
        self.assertEqual(preview["render_report"]["renderer_id"], "openai_responses")
        self.assertEqual(
            preview["render_report"]["tool_surface"],
            {
                "source_tool_schema_count": 1,
                "provider_visible_tool_count": 1,
                "provider_visible_tool_names": ("command_exec",),
                "dropped_tool_schema_count": 0,
                "provider_tool_mapping": [
                    {
                        "provider_name": "command_exec",
                        "runtime_tool_name": "command.exec",
                        "tool_id": "command.exec",
                        "trace_status": "runtime_tool_surface",
                    },
                ],
            },
        )
        self.assertEqual(
            preview["render_report"]["tool_protocol"],
            {
                "schema_version": "2026-06-19.runtime_input_filter.v1",
                "source_had_protocol_breaks": False,
                "replay_has_protocol_breaks": False,
                "replay_orphan_tool_output_count": 0,
                "replay_missing_tool_output_count": 0,
                "replay_duplicate_tool_call_id_count": 0,
                "replay_duplicate_tool_output_id_count": 0,
                "dropped_orphan_tool_output_count": 0,
                "dropped_missing_tool_output_count": 1,
                "dropped_duplicate_tool_call_id_count": 0,
                "dropped_duplicate_tool_output_id_count": 0,
            },
        )
        self.assertEqual(
            preview["request_render_snapshot_id"],
            "ctxsnap_provider_1",
        )
        self.assertEqual(preview["request_render_snapshot_schema_version"], "2026-06-11")
        self.assertEqual(preview["request_render_snapshot_included_node_count"], 2)
        self.assertTrue(str(preview["request_render_snapshot_fingerprint"]).startswith("sha256:"))
        self.assertEqual(
            preview["tool_surface_id"],
            "tool_surface:ctxsnap_provider_1",
        )
        self.assertEqual(preview["tool_surface_function_count"], 1)
        self.assertEqual(preview["tool_surface_mirrored_schema_count"], 1)

    def test_openai_responses_adapter_builds_provider_wire_request(self) -> None:
        profile = LlmProfile(
            id="writer-wire-request",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Explain boundaries."),
            ),
        )

        wire_request = OpenAIResponsesAdapter()._wire_request(profile, request)

        self.assertIsInstance(wire_request, ProviderWireRequest)
        self.assertEqual(wire_request.renderer_id, "openai_responses")
        self.assertEqual(wire_request.transport, "http")
        self.assertEqual(wire_request.endpoint, "https://api.openai.com/v1/responses")
        self.assertEqual(wire_request.payload["model"], "gpt-5")
        self.assertEqual(wire_request.render_report["renderer_id"], "openai_responses")

    def test_openai_responses_adapter_prefers_projected_input_items(self) -> None:
        profile = LlmProfile(
            id="writer-projected-input",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding_id="inline-openai-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="stale message"),
            ),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "fresh projected input"},
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL,
                    payload={
                        "call_id": "call_projected_1",
                        "name": "unsafe.tool name",
                        "arguments": {"query": "flight"},
                    },
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                    payload={"call_id": "call_projected_1", "output": {"ok": True}},
                ),
            ),
        )

        preview = OpenAIResponsesAdapter().preview_request(profile, request)

        self.assertEqual(
            preview["input_item_types"],
            ("user", "function_call", "function_call_output"),
        )
        payload_preview = preview["payload_preview"]
        assert isinstance(payload_preview, dict)
        self.assertEqual(
            payload_preview["input"],
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "fresh projected input"},
                    ],
                },
                {
                    "call_id": "call_projected_1",
                    "name": "unsafe_tool_name",
                    "arguments": '{"query": "flight"}',
                    "type": "function_call",
                },
                {
                    "call_id": "call_projected_1",
                    "output": '{"ok": true}',
                    "type": "function_call_output",
                },
            ],
        )

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
        self.assertFalse(response.response_items[0].user_timeline_candidate)
        self.assertEqual(
            response.response_items[1].kind,
            LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM,
        )
        self.assertFalse(response.response_items[1].user_timeline_candidate)
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
        self.assertFalse(response.response_items[1].user_timeline_candidate)
        self.assertEqual(response.continuation.reason, LlmContinuationReason.TOOL_CALL)
        self.assertTrue(response.continuation.needs_follow_up)

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

    def test_openai_chat_compatible_preview_uses_renderer_payload(self) -> None:
        profile = LlmProfile(
            id="local-chat-preview",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5",
            base_url="http://localhost:8010/v1",
            credential_binding_id="inline-chat-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
            tool_schemas=(
                ToolSchema(
                    name="command.exec",
                    description="Run a command",
                    input_schema={"type": "object"},
                ),
            ),
            request_metadata={
                "request_render_snapshot": {
                    "snapshot_id": "ctxsnap_chat_1",
                    "included_node_ids": ["runtime.contract"],
                },
            },
        )

        preview = OpenAIChatCompatibleAdapter().preview_request(profile, request)

        self.assertEqual(preview["preview_source"], "provider_adapter")
        self.assertEqual(preview["renderer_id"], "openai_chat_compatible")
        self.assertEqual(preview["transport"], "http")
        self.assertEqual(preview["message_count"], 2)
        self.assertEqual(preview["tool_count"], 1)
        self.assertEqual(preview["request_render_snapshot_id"], "ctxsnap_chat_1")
        payload_preview = preview["payload_preview"]
        assert isinstance(payload_preview, dict)
        self.assertEqual(payload_preview["messages"][0]["role"], "system")
        self.assertEqual(
            payload_preview["tools"][0]["function"]["name"],
            "command_exec",
        )

    def test_openai_chat_compatible_adapter_builds_provider_wire_request(self) -> None:
        profile = LlmProfile(
            id="local-chat-wire-request",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5",
            base_url="http://localhost:8010/v1",
            credential_binding_id="inline-chat-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
            tool_schemas=(
                ToolSchema(
                    name="command.exec",
                    description="Run a command",
                    input_schema={"type": "object"},
                ),
            ),
        )

        wire_request = OpenAIChatCompatibleAdapter()._wire_request(profile, request)
        stream_wire_request = OpenAIChatCompatibleAdapter()._wire_request(
            profile,
            request,
            stream=True,
        )

        self.assertIsInstance(wire_request, ProviderWireRequest)
        self.assertEqual(wire_request.renderer_id, "openai_chat_compatible")
        self.assertEqual(wire_request.transport, "http")
        self.assertEqual(wire_request.endpoint, "http://localhost:8010/v1/chat/completions")
        self.assertEqual(wire_request.payload["messages"][0]["role"], "system")
        self.assertEqual(wire_request.payload["tools"][0]["function"]["name"], "command_exec")
        self.assertEqual(stream_wire_request.transport, "sse")
        self.assertTrue(stream_wire_request.payload["stream"])

    def test_openai_chat_compatible_adapter_converts_projected_input_items(self) -> None:
        profile = LlmProfile(
            id="local-chat-input-items",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="llama3.2",
            base_url="http://localhost:11434/v1",
            credential_binding_id="ollama-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="legacy message should not be used",
                ),
            ),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "Use replay input"},
                    source="session_item",
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL,
                    payload={
                        "call_id": "call_replay_1",
                        "name": "echo_tool",
                        "arguments": {"message": "hello"},
                    },
                    source="session_item",
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                    payload={"call_id": "call_replay_1", "output": "hello"},
                    source="session_item",
                ),
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
                    "id": "chatcmpl_replay_1",
                    "model": "llama3.2",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "done"},
                        },
                    ],
                },
            ),
        ) as post:
            OpenAIChatCompatibleAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        messages = kwargs["json"]["messages"]
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(
            messages[0]["content"],
            [{"type": "text", "text": "Use replay input"}],
        )
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIsNone(messages[1]["content"])
        self.assertEqual(
            messages[1]["tool_calls"][0]["id"],
            "call_replay_1",
        )
        self.assertEqual(
            json.loads(messages[1]["tool_calls"][0]["function"]["arguments"]),
            {"message": "hello"},
        )
        self.assertEqual(messages[2]["role"], "tool")
        self.assertEqual(messages[2]["tool_call_id"], "call_replay_1")
        self.assertEqual(messages[2]["content"], "hello")
        self.assertNotIn("legacy message should not be used", json.dumps(messages))

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

    def test_openai_chat_compatible_stream_and_non_stream_emit_equivalent_response_items(
        self,
    ) -> None:
        profile = LlmProfile(
            id="local-chat-equivalent",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="qwen3.5-35b",
            base_url="http://localhost:8010/v1",
            credential_binding_id="inline-vllm-token",
        )
        request = _adapter_request(
            messages=(LlmMessage(role=LlmMessageRole.USER, content="Say hello"),),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "chatcmpl_equiv_1",
                    "model": "qwen3.5-35b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "hello"},
                        },
                    ],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 2,
                        "total_tokens": 6,
                    },
                },
            ),
        ):
            non_stream_response = OpenAIChatCompatibleAdapter().invoke(
                profile,
                request,
            )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "chat.completion.chunk",
                        {
                            "id": "chatcmpl_equiv_1",
                            "model": "qwen3.5-35b",
                            "choices": [
                                {
                                    "delta": {"content": "he"},
                                    "finish_reason": None,
                                },
                            ],
                        },
                    ),
                    (
                        "chat.completion.chunk",
                        {
                            "id": "chatcmpl_equiv_1",
                            "model": "qwen3.5-35b",
                            "choices": [
                                {
                                    "delta": {"content": "llo"},
                                    "finish_reason": None,
                                },
                            ],
                        },
                    ),
                    (
                        "chat.completion.chunk",
                        {
                            "id": "chatcmpl_equiv_1",
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
        ):
            stream_events = list(
                OpenAIChatCompatibleAdapter().stream_invoke(profile, request),
            )

        stream_completed = stream_events[-1].data
        self.assertEqual(non_stream_response.result.text, stream_completed["result"]["text"])
        self.assertEqual(
            non_stream_response.result.finish_reason,
            stream_completed["result"]["finish_reason"],
        )
        non_stream_item = non_stream_response.response_items[0]
        stream_item = stream_completed["response_items"][0]
        self.assertEqual(non_stream_item.kind.value, stream_item["kind"])
        self.assertEqual(non_stream_item.content_payload, stream_item["content_payload"])
        self.assertEqual(
            non_stream_item.user_timeline_candidate,
            stream_item["user_timeline_candidate"],
        )

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
            codex_messages = (
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="You are a concise coding assistant.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Reply with codex-ok.",
                ),
            )
            request = _adapter_request(
                codex_input=True,
                messages=codex_messages,
                input_items=tuple(projected_input_items_from_messages(codex_messages)),
                overrides={"reasoning": {"summary": "auto"}},
            )

            with patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.requests.post",
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
        self.assertEqual(response.response_items[0].phase, LlmMessagePhase.UNKNOWN)
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
            codex_input=True,
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
        self.assertEqual(preview["renderer_id"], "openai_codex_responses")
        self.assertEqual(
            preview["render_report"]["renderer_id"],
            "openai_codex_responses",
        )
        self.assertEqual(
            preview["endpoint"],
            "https://chatgpt.com/backend-api/codex/responses",
        )
        self.assertEqual(preview["transport"], "http")
        self.assertIsNone(preview["message_type"])
        self.assertEqual(preview["input_item_count"], 1)
        self.assertEqual(preview["tool_count"], 1)
        self.assertFalse(preview["has_previous_response_id"])
        self.assertFalse(preview["input_delta_mode"])
        self.assertEqual(preview["input_delta_count"], 0)
        self.assertIsNone(preview["previous_response_id"])
        self.assertIn("instructions", preview["payload_keys"])
        self.assertNotIn("previous_response_id", preview["payload_keys"])
        self.assertNotIn("provider_transport", preview["payload_keys"])
        self.assertNotIn("type", preview["payload_keys"])
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

    def test_openai_codex_responses_adapter_builds_http_provider_wire_request(self) -> None:
        profile = LlmProfile(
            id="codex-agent-wire-http",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Use HTTP replay."),
            ),
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
            ),
        )

        wire_request = OpenAICodexResponsesAdapter()._wire_request(profile, request)

        self.assertIsInstance(wire_request, ProviderWireRequest)
        self.assertEqual(wire_request.renderer_id, "openai_codex_responses")
        self.assertEqual(wire_request.transport, "http")
        self.assertEqual(
            wire_request.endpoint,
            "https://chatgpt.com/backend-api/codex/responses",
        )
        self.assertNotIn("previous_response_id", wire_request.payload)
        self.assertEqual(wire_request.render_report["renderer_id"], "openai_codex_responses")

    def test_openai_codex_responses_adapter_builds_websocket_provider_wire_request(self) -> None:
        profile = LlmProfile(
            id="codex-agent-wire-websocket",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        messages = (
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Use websocket continuation."),
            LlmMessage(
                role=LlmMessageRole.ASSISTANT,
                content={
                    "type": "function_call",
                    "call_id": "call_ws_1",
                    "name": "exec",
                    "arguments": {"cmd": "echo ws"},
                },
            ),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                tool_call_id="call_ws_1",
                content="ws output",
            ),
        )
        request = _adapter_request(
            codex_input=True,
            messages=messages,
            input_items=tuple(projected_input_items_from_messages(messages)),
            provider_transport="websocket",
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
                input_item_fingerprints=_openai_input_fingerprints_for_messages(
                    messages,
                    take=2,
                ),
                **_codex_surface_fingerprints(messages),
            ),
        )

        wire_request = OpenAICodexResponsesAdapter()._websocket_wire_request(
            profile,
            request,
            endpoint="wss://chatgpt.com/backend-api/codex/responses",
        )

        self.assertIsInstance(wire_request, ProviderWireRequest)
        self.assertEqual(wire_request.renderer_id, "openai_codex_responses")
        self.assertEqual(wire_request.transport, "websocket")
        self.assertEqual(wire_request.payload["type"], "response.create")
        self.assertEqual(wire_request.payload["previous_response_id"], "resp_previous")
        self.assertEqual(wire_request.render_report["renderer_id"], "openai_codex_responses")

    def test_openai_codex_responses_adapter_projects_replay_text_blocks(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="legacy message should not be used",
                ),
            ),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={
                        "role": "user",
                        "content": [{"type": "text", "text": "Use replay input"}],
                    },
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Planning next step."}],
                    },
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_codex_replay",
                                "status": "completed",
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [
                                            {"type": "output_text", "text": "done"},
                                        ],
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            OpenAICodexResponsesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"],
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Use replay input"}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Planning next step."}],
                },
            ],
        )
        self.assertNotIn("legacy message should not be used", json.dumps(kwargs["json"]))

    def test_openai_codex_responses_adapter_projects_replay_reasoning_summary(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(LlmMessage(role=LlmMessageRole.USER, content="unused"),),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={
                        "role": "user",
                        "content": [{"type": "text", "text": "Find flights"}],
                    },
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.REASONING,
                    payload={
                        "type": "reasoning",
                        "content": [
                            {
                                "type": "text",
                                "text": "Need to ask for exact Sunday.",
                            },
                        ],
                    },
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.REASONING,
                    payload={"type": "reasoning", "summary": [], "text": None},
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_codex_reasoning_replay",
                                "status": "completed",
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [
                                            {"type": "output_text", "text": "done"},
                                        ],
                                    },
                                ],
                            },
                        },
                    ),
                ),
            ),
        ) as post:
            OpenAICodexResponsesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        self.assertEqual(
            kwargs["json"]["input"],
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Find flights"}],
                },
                {
                    "type": "reasoning",
                    "summary": [
                        {
                            "type": "summary_text",
                            "text": "Need to ask for exact Sunday.",
                        },
                    ],
                },
            ],
        )

    def test_openai_codex_websocket_transport_streams_response_create(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        messages = (
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="Runtime contract.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Use websocket continuation.",
                ),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content="",
                    metadata={
                        "provider_item": {
                            "type": "function_call",
                            "call_id": "call_ws_1",
                            "name": "exec",
                            "arguments": '{"cmd":"echo ws"}',
                        },
                    },
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    tool_call_id="call_ws_1",
                    content="ws output",
                ),
        )
        request = _adapter_request(
            codex_input=True,
            messages=messages,
            input_items=tuple(projected_input_items_from_messages(messages)),
            overrides={"provider_transport": "websocket"},
            provider_transport="websocket",
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
                input_item_fingerprints=_openai_input_fingerprints_for_messages(
                    messages,
                    take=2,
                ),
                **_codex_surface_fingerprints(messages),
            ),
        )

        preview = OpenAICodexResponsesAdapter().preview_request(profile, request)

        self.assertEqual(preview["transport"], "websocket")
        self.assertEqual(preview["message_type"], "response.create")
        self.assertEqual(
            preview["endpoint"],
            "wss://chatgpt.com/backend-api/codex/responses",
        )
        self.assertIn("type", preview["payload_keys"])
        self.assertNotIn("provider_transport", preview["payload_keys"])
        self.assertIn("previous_response_id", preview["payload_keys"])
        self.assertEqual(preview["previous_response_id"], "resp_previous")
        self.assertTrue(preview["input_delta_mode"])
        self.assertEqual(preview["input_baseline_count"], 3)
        self.assertEqual(preview["input_delta_count"], 1)

        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_next",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "websocket done",
                                    },
                                ],
                            },
                        ],
                        "usage": {
                            "input_tokens": 7,
                            "output_tokens": 3,
                            "total_tokens": 10,
                        },
                    },
                },
            ),
        )
        adapter = OpenAICodexResponsesAdapter()
        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ) as create_connection:
            response = adapter.invoke(profile, request)

        create_connection.assert_called_once()
        _, kwargs = create_connection.call_args
        self.assertEqual(
            create_connection.call_args.args[0],
            "wss://chatgpt.com/backend-api/codex/responses",
        )
        self.assertIn(
            "OpenAI-Beta: responses_websockets=2026-02-06",
            kwargs["header"],
        )
        self.assertIn("Authorization: Bearer adapter-test-token", kwargs["header"])
        self.assertFalse(fake_ws.closed)
        sent = json.loads(fake_ws.sent[0])
        self.assertEqual(sent["type"], "response.create")
        self.assertEqual(sent["previous_response_id"], "resp_previous")
        self.assertEqual(
            sent["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_ws_1",
                    "output": "ws output",
                },
            ],
        )
        self.assertNotIn("provider_transport", sent)
        self.assertEqual(response.provider_request_id, "resp_next")
        self.assertEqual(response.result.text, "websocket done")
        self.assertEqual(response.result.metadata["transport"], "websocket")
        adapter.close_websocket_pool()
        self.assertTrue(fake_ws.closed)

    def test_openai_codex_context_snapshot_metadata_does_not_create_input_item(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.SYSTEM,
                    content="Runtime contract.",
                ),
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Continue the run.",
                ),
            ),
            input_items=tuple(
                projected_input_items_from_messages(
                    (
                        LlmMessage(
                            role=LlmMessageRole.SYSTEM,
                            content="Runtime contract.",
                        ),
                        LlmMessage(
                            role=LlmMessageRole.USER,
                            content="Continue the run.",
                        ),
                    ),
                ),
            ),
            request_metadata={
                "request_render_snapshot": {
                    "snapshot_id": "ctx-1",
                    "included_node_ids": ["runtime.contract"],
                    "provider_attachment_mirror": {
                        "runtime_request_draft": {"session_item_count": 1},
                    },
                },
            },
        )

        payload = OpenAICodexResponsesAdapter()._build_payload(  # noqa: SLF001
            profile,
            request,
        )

        self.assertEqual(payload["instructions"], "Runtime contract.")
        self.assertEqual(
            payload["input"],
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Continue the run."},
                    ],
                },
            ],
        )

    def test_openai_codex_websocket_reuses_completed_connection(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Use websocket connection reuse.",
                ),
            ),
            provider_transport="websocket",
        )
        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_reuse_1",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {"type": "output_text", "text": "first"},
                                ],
                            },
                        ],
                    },
                },
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_reuse_2",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-2",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {"type": "output_text", "text": "second"},
                                ],
                            },
                        ],
                    },
                },
            ),
        )
        adapter = OpenAICodexResponsesAdapter()
        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ) as create_connection:
            first = adapter.invoke(profile, request)
            second = adapter.invoke(profile, request)

        create_connection.assert_called_once()
        self.assertEqual(len(fake_ws.sent), 2)
        self.assertEqual(first.provider_request_id, "resp_reuse_1")
        self.assertEqual(first.result.text, "first")
        self.assertEqual(second.provider_request_id, "resp_reuse_2")
        self.assertEqual(second.result.text, "second")
        self.assertFalse(fake_ws.closed)
        adapter.close_websocket_pool()
        self.assertTrue(fake_ws.closed)

    def test_openai_codex_websocket_warmup_reuses_connection_without_request(
        self,
    ) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Use warmed websocket connection.",
                ),
            ),
            provider_transport="websocket",
        )
        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_warm",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-warm",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {"type": "output_text", "text": "warm done"},
                                ],
                            },
                        ],
                    },
                },
            ),
        )
        adapter = OpenAICodexResponsesAdapter()
        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ) as create_connection:
            warmup = adapter.warmup_websocket(
                profile,
                resolved_credential="adapter-test-token",
            )
            self.assertEqual(fake_ws.sent, [])
            response = adapter.invoke(profile, request)

        create_connection.assert_called_once()
        self.assertEqual(warmup["transport"], "websocket")
        self.assertFalse(warmup["reused_connection"])
        self.assertEqual(len(fake_ws.sent), 1)
        self.assertEqual(response.provider_request_id, "resp_warm")
        self.assertEqual(response.result.text, "warm done")
        self.assertFalse(fake_ws.closed)
        adapter.close_websocket_pool()
        self.assertTrue(fake_ws.closed)

    def test_openai_codex_websocket_requires_input_fingerprints_for_previous_response(
        self,
    ) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Use websocket full request.",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    tool_call_id="call_ws_1",
                    content="ws output",
                ),
            ),
            provider_transport="websocket",
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
            ),
        )

        preview = OpenAICodexResponsesAdapter().preview_request(profile, request)

        self.assertFalse(preview["input_delta_mode"])
        self.assertNotIn("previous_response_id", preview["payload_keys"])
        self.assertIsNone(preview["previous_response_id"])
        self.assertEqual(preview["input_baseline_count"], 2)
        self.assertEqual(preview["input_item_count"], 2)

        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_full",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "full websocket done",
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
        )
        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ):
            response = OpenAICodexResponsesAdapter().invoke(profile, request)

        sent = json.loads(fake_ws.sent[0])
        self.assertNotIn("previous_response_id", sent)
        self.assertEqual(len(sent["input"]), 2)
        self.assertEqual(response.provider_request_id, "resp_full")
        self.assertEqual(response.result.text, "full websocket done")

    def test_openai_codex_websocket_prefix_mismatch_uses_full_request(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        messages = (
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="This prompt does not match previous input.",
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    tool_call_id="call_ws_1",
                    content="ws output",
                ),
        )
        request = _adapter_request(
            codex_input=True,
            messages=messages,
            provider_transport="websocket",
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
                input_item_fingerprints=("mismatched-previous-fingerprint",),
                **_codex_surface_fingerprints(messages),
            ),
        )

        preview = OpenAICodexResponsesAdapter().preview_request(profile, request)

        self.assertFalse(preview["input_delta_mode"])
        self.assertNotIn("previous_response_id", preview["payload_keys"])
        self.assertIsNone(preview["previous_response_id"])
        self.assertEqual(preview["input_baseline_count"], 2)
        self.assertEqual(preview["input_item_count"], 2)

        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_mismatch_full",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "prefix mismatch full request",
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
        )
        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ):
            response = OpenAICodexResponsesAdapter().invoke(profile, request)

        sent = json.loads(fake_ws.sent[0])
        self.assertNotIn("previous_response_id", sent)
        self.assertEqual(len(sent["input"]), 2)
        self.assertEqual(response.provider_request_id, "resp_mismatch_full")
        self.assertEqual(response.result.text, "prefix mismatch full request")

    def test_openai_codex_websocket_instruction_mismatch_uses_full_request(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        messages = (
            LlmMessage(role=LlmMessageRole.SYSTEM, content="New instructions."),
            LlmMessage(role=LlmMessageRole.USER, content="Continue safely."),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                tool_call_id="call_ws_1",
                content="ws output",
            ),
        )
        request = _adapter_request(
            codex_input=True,
            messages=messages,
            provider_transport="websocket",
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
                input_item_fingerprints=_openai_input_fingerprints_for_messages(
                    messages,
                    take=1,
                ),
                instructions_fingerprint=openai_provider_payload_fingerprint(
                    "Old instructions.",
                ),
            ),
        )

        preview = OpenAICodexResponsesAdapter().preview_request(profile, request)

        self.assertFalse(preview["input_delta_mode"])
        self.assertNotIn("previous_response_id", preview["payload_keys"])
        self.assertIsNone(preview["previous_response_id"])
        self.assertEqual(preview["input_item_count"], 2)

    def test_openai_codex_websocket_tool_schema_mismatch_uses_full_request(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        messages = (
            LlmMessage(role=LlmMessageRole.USER, content="Continue safely."),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                tool_call_id="call_ws_1",
                content="ws output",
            ),
        )
        previous_tool_schema = ToolSchema(
            name="exec",
            description="Old exec tool.",
            input_schema={"type": "object"},
        )
        current_tool_schema = ToolSchema(
            name="exec",
            description="Changed exec tool.",
            input_schema={"type": "object"},
        )
        request = _adapter_request(
            codex_input=True,
            messages=messages,
            tool_schemas=(current_tool_schema,),
            provider_transport="websocket",
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
                input_item_fingerprints=_openai_input_fingerprints_for_messages(
                    messages,
                    take=1,
                ),
                **_codex_surface_fingerprints(
                    messages,
                    tool_schemas=(previous_tool_schema,),
                ),
            ),
        )

        preview = OpenAICodexResponsesAdapter().preview_request(profile, request)

        self.assertFalse(preview["input_delta_mode"])
        self.assertNotIn("previous_response_id", preview["payload_keys"])
        self.assertIsNone(preview["previous_response_id"])
        self.assertEqual(preview["input_item_count"], 2)
        self.assertEqual(preview["tool_count"], 1)

    def test_openai_codex_websocket_uses_completed_output_item_cache(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Call a tool.",
                ),
            ),
            provider_transport="websocket",
        )
        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "fc-1",
                        "type": "function_call",
                        "call_id": "call_ws_1",
                        "name": "exec",
                        "arguments": '{"cmd":"echo websocket"}',
                    },
                },
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_tool",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "usage": {
                            "input_tokens": 9,
                            "output_tokens": 2,
                            "total_tokens": 11,
                        },
                    },
                },
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ):
            response = OpenAICodexResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.provider_request_id, "resp_tool")
        self.assertEqual(len(response.result.tool_calls), 1)
        self.assertEqual(response.result.tool_calls[0].id, "call_ws_1")
        self.assertEqual(response.result.tool_calls[0].name, "exec")
        self.assertEqual(
            response.result.tool_calls[0].arguments,
            {"cmd": "echo websocket"},
        )

    def test_openai_codex_websocket_continuation_falls_back_to_full_request_before_output(
        self,
    ) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        messages = (
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Summarize current state.",
                ),
                LlmMessage(
                    role=LlmMessageRole.ASSISTANT,
                    content="I will call a tool.",
                    metadata={
                        "provider_item": {
                            "type": "function_call",
                            "call_id": "call_ws_1",
                            "name": "exec",
                            "arguments": '{"cmd":"pwd"}',
                        },
                    },
                ),
                LlmMessage(
                    role=LlmMessageRole.TOOL,
                    content="tool completed with evidence",
                    tool_call_id="call_ws_1",
                ),
        )
        request = _adapter_request(
            codex_input=True,
            messages=messages,
            provider_transport="websocket",
            continuation=LlmProviderContinuation(
                mode="provider_native",
                previous_response_id="resp_previous",
                input_item_fingerprints=_openai_input_fingerprints_for_messages(
                    messages,
                    take=2,
                ),
                **_codex_surface_fingerprints(messages),
            ),
        )
        rejected_delta_ws = _FakeWebSocket(
            (
                {
                    "type": "error",
                    "error": {
                        "code": "invalid_request_error",
                        "message": "delta did not match previous response",
                    },
                },
            ),
        )
        full_request_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_full_retry",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "full request worked",
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
        )

        adapter = OpenAICodexResponsesAdapter()
        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            side_effect=[rejected_delta_ws, full_request_ws],
        ) as create_connection:
            response = adapter.invoke(profile, request)

        self.assertEqual(create_connection.call_count, 2)
        self.assertTrue(rejected_delta_ws.closed)
        self.assertFalse(full_request_ws.closed)
        delta_payload = json.loads(rejected_delta_ws.sent[0])
        self.assertEqual(delta_payload["previous_response_id"], "resp_previous")
        self.assertEqual(
            delta_payload["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_ws_1",
                    "output": "tool completed with evidence",
                },
            ],
        )
        fallback_payload = json.loads(full_request_ws.sent[0])
        self.assertNotIn("previous_response_id", fallback_payload)
        self.assertEqual(len(fallback_payload["input"]), 3)
        self.assertEqual(response.provider_request_id, "resp_full_retry")
        self.assertEqual(response.result.text, "full request worked")
        self.assertEqual(response.result.metadata["transport"], "websocket")
        self.assertEqual(
            [item.kind for item in response.response_items],
            [LlmResponseItemKind.ASSISTANT_MESSAGE],
        )
        self.assertEqual(
            response.response_items[0].content_payload["text"],
            "full request worked",
        )
        self.assertEqual(response.continuation.reason, LlmContinuationReason.NONE)
        self.assertFalse(response.continuation.needs_follow_up)
        self.assertTrue(response.result.metadata["provider_continuation_fallback"])
        self.assertEqual(
            response.result.metadata["provider_continuation_fallback_reason"],
            "websocket_continuation_failed_before_output",
        )
        fallback_error = response.result.metadata["provider_continuation_fallback_error"]
        self.assertEqual(fallback_error["type"], "RuntimeError")
        self.assertIn(
            "delta did not match previous response",
            fallback_error["message"],
        )
        adapter.close_websocket_pool()
        self.assertTrue(full_request_ws.closed)

    def test_openai_codex_websocket_async_invoke_uses_thread_bridge(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Use websocket async bridge.",
                ),
            ),
            provider_transport="websocket",
        )
        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_async_ws",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "async websocket done",
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
        )

        async def _invoke():
            return await OpenAICodexResponsesAdapter().invoke_async(profile, request)

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ):
            response = asyncio.run(_invoke())

        self.assertEqual(response.provider_request_id, "resp_async_ws")
        self.assertEqual(response.result.text, "async websocket done")
        self.assertEqual(response.result.metadata["transport"], "websocket")

    def test_openai_codex_websocket_async_stream_yields_bridge_events(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Use websocket async stream bridge.",
                ),
            ),
            provider_transport="websocket",
        )
        fake_ws = _FakeWebSocket(
            (
                {"type": "response.output_text.delta", "delta": "async "},
                {"type": "response.output_text.delta", "delta": "bridge"},
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_async_ws_stream",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "async bridge",
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
        )

        async def _collect_events():
            return [
                event
                async for event in OpenAICodexResponsesAdapter().stream_invoke_async(
                    profile,
                    request,
                )
            ]

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ):
            events = asyncio.run(_collect_events())

        self.assertEqual(
            [event.type for event in events],
            ["text_delta", "text_delta", "completed"],
        )
        self.assertEqual(events[0].data["text"], "async ")
        self.assertEqual(events[1].data["text"], "bridge")
        self.assertEqual(events[2].data["provider_request_id"], "resp_async_ws_stream")
        self.assertEqual(events[2].data["result"]["text"], "async bridge")

    def test_openai_codex_websocket_streams_reasoning_summary_events(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Reason briefly.",
                ),
            ),
            provider_transport="websocket",
        )
        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.reasoning_summary_text.delta",
                    "item_id": "rs-1",
                    "delta": "Checking approach.",
                },
                {
                    "type": "response.reasoning.delta",
                    "item_id": "rs-1",
                    "delta": "hidden raw reasoning",
                },
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_reasoning_ws",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
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
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
            return_value=fake_ws,
        ):
            events = list(OpenAICodexResponsesAdapter().stream_invoke(profile, request))

        self.assertEqual(
            [event.type for event in events],
            ["reasoning_summary_delta", "reasoning_raw_delta", "completed"],
        )
        self.assertEqual(events[0].data["item_id"], "rs-1")
        self.assertEqual(events[0].data["text"], "Checking approach.")
        self.assertEqual(events[1].data["item_id"], "rs-1")
        self.assertEqual(events[1].data["text"], "hidden raw reasoning")
        self.assertEqual(events[2].data["provider_request_id"], "resp_reasoning_ws")

    def test_openai_codex_websocket_retries_transient_connection_before_output(
        self,
    ) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Retry websocket connect.",
                ),
            ),
            provider_transport="websocket",
        )
        fake_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_retry_ws",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "retry websocket done",
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
        )
        with (
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
                side_effect=[requests.Timeout("temporary websocket timeout"), fake_ws],
            ) as create_connection,
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.sleep_before_openai_stream_retry",
            ) as sleep,
        ):
            response = OpenAICodexResponsesAdapter().invoke(profile, request)

        self.assertEqual(create_connection.call_count, 2)
        sleep.assert_called_once_with(1)
        self.assertEqual(response.provider_request_id, "resp_retry_ws")
        self.assertEqual(response.result.text, "retry websocket done")

    def test_openai_codex_websocket_retries_broken_pipe_on_send_before_output(
        self,
    ) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Retry websocket broken pipe.",
                ),
            ),
            provider_transport="websocket",
        )
        broken_ws = _BrokenPipeOnSendWebSocket(())
        healthy_ws = _FakeWebSocket(
            (
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_retry_broken_pipe_ws",
                        "status": "completed",
                        "model": "gpt-5.5",
                        "output": [
                            {
                                "id": "msg-1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "retry after broken pipe",
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
        )
        adapter = OpenAICodexResponsesAdapter()
        with (
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport.websocket.create_connection",
                side_effect=[broken_ws, healthy_ws],
            ) as create_connection,
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.sleep_before_openai_stream_retry",
            ) as sleep,
        ):
            response = adapter.invoke(profile, request)

        self.assertEqual(create_connection.call_count, 2)
        sleep.assert_called_once_with(1)
        self.assertTrue(broken_ws.closed)
        self.assertFalse(healthy_ws.closed)
        self.assertEqual(len(broken_ws.sent), 1)
        self.assertEqual(len(healthy_ws.sent), 1)
        self.assertEqual(
            response.provider_request_id,
            "resp_retry_broken_pipe_ws",
        )
        self.assertEqual(response.result.text, "retry after broken pipe")
        adapter.close_websocket_pool()
        self.assertTrue(healthy_ws.closed)

    def test_openai_codex_http_replays_tool_output_without_previous_response_id(self) -> None:
        profile = LlmProfile(
            id="codex-agent",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5.5",
            model_family=LlmModelFamily.CODEX,
        )
        request = _adapter_request(
            codex_input=True,
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

        self.assertIsNone(preview["previous_response_id"])
        self.assertEqual(preview["input_item_count"], 2)
        self.assertEqual(preview["input_item_types"], ("user", "function_call_output"))
        self.assertEqual(preview["transport"], "http")
        self.assertFalse(preview["input_delta_mode"])
        self.assertNotIn("previous_response_id", preview["payload_keys"])
        self.assertEqual(
            preview["payload_preview"]["input"][-1],
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "tool completed with evidence",
            },
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
            codex_input=True,
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
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.requests.post",
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
            codex_input=True,
            messages=(
                LlmMessage(
                    role=LlmMessageRole.USER,
                    content="Reply with codex-stream.",
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.requests.post",
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
            codex_input=True,
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
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.httpx.AsyncClient",
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
            codex_input=True,
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
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.requests.post",
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
            codex_input=True,
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="Retry codex."),
            ),
        )

        with (
            patch(
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport.requests.post",
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
                "crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_dispatch.sleep_before_openai_stream_retry",
            ),
        ):
            response = OpenAICodexResponsesAdapter().invoke(profile, request)

        self.assertEqual(response.result.text, "codex-recovered")
        self.assertEqual(post.call_count, 2)

    def test_anthropic_messages_preview_uses_renderer_payload(self) -> None:
        profile = LlmProfile(
            id="claude-preview",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-api-key",
            default_params=LlmDefaults(max_output_tokens=512),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
            tool_schemas=(
                ToolSchema(
                    name="search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
            request_metadata={
                "tool_surface": {
                    "id": "tool_surface:anthropic",
                    "functions": [{"name": "search_docs"}],
                },
            },
        )

        preview = AnthropicMessagesAdapter().preview_request(profile, request)

        self.assertEqual(preview["preview_source"], "provider_adapter")
        self.assertEqual(preview["renderer_id"], "anthropic_messages")
        self.assertEqual(preview["message_count"], 1)
        self.assertEqual(preview["tool_count"], 1)
        self.assertTrue(preview["has_system"])
        self.assertEqual(preview["tool_surface_id"], "tool_surface:anthropic")
        self.assertEqual(
            preview["render_report"]["tool_surface"],
            {
                "source_tool_schema_count": 1,
                "provider_visible_tool_count": 1,
                "provider_visible_tool_names": ("search_docs",),
                "dropped_tool_schema_count": 0,
                "provider_tool_mapping": [
                    {
                        "provider_name": "search_docs",
                        "runtime_tool_name": "search_docs",
                        "trace_status": "runtime_tool_surface",
                    },
                ],
            },
        )
        payload_preview = preview["payload_preview"]
        assert isinstance(payload_preview, dict)
        self.assertEqual(payload_preview["system"], "system")
        self.assertEqual(payload_preview["messages"][0]["role"], "user")

    def test_anthropic_messages_adapter_builds_provider_wire_request(self) -> None:
        profile = LlmProfile(
            id="claude-wire-request",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-api-key",
            default_params=LlmDefaults(max_output_tokens=512),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
        )

        wire_request = AnthropicMessagesAdapter()._wire_request(profile, request)

        self.assertIsInstance(wire_request, ProviderWireRequest)
        self.assertEqual(wire_request.renderer_id, "anthropic_messages")
        self.assertEqual(wire_request.transport, "http")
        self.assertEqual(wire_request.endpoint, "https://api.anthropic.com/v1/messages")
        self.assertEqual(wire_request.payload["system"], "system")
        self.assertEqual(wire_request.payload["messages"][0]["role"], "user")
        self.assertEqual(wire_request.render_report["renderer_id"], "anthropic_messages")

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

    def test_anthropic_messages_adapter_converts_projected_input_items(self) -> None:
        profile = LlmProfile(
            id="claude-input-items",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding_id="anthropic-api-key",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="legacy"),
            ),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "Use replay input"},
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL,
                    payload={
                        "call_id": "call_anthropic_replay",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                    payload={
                        "call_id": "call_anthropic_replay",
                        "output": '{"hits":1}',
                    },
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.anthropic_messages.requests.post",
            return_value=_FakeResponse(
                payload={
                    "id": "msg_replay",
                    "model": "claude-sonnet-4-5",
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "done"}],
                },
            ),
        ) as post:
            AnthropicMessagesAdapter().invoke(profile, request)

        _, kwargs = post.call_args
        messages = kwargs["json"]["messages"]
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"][0]["text"], "Use replay input")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"][0]["type"], "tool_use")
        self.assertEqual(messages[1]["content"][0]["id"], "call_anthropic_replay")
        self.assertEqual(messages[1]["content"][0]["input"], {"query": "ddd"})
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[2]["content"][0]["type"], "tool_result")
        self.assertEqual(messages[2]["content"][0]["tool_use_id"], "call_anthropic_replay")
        self.assertNotIn("legacy", json.dumps(messages))

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

    def test_gemini_generate_content_preview_uses_renderer_payload(self) -> None:
        profile = LlmProfile(
            id="gemini-preview",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding_id="gemini-api-key",
            default_params=LlmDefaults(max_output_tokens=300),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
            tool_schemas=(
                ToolSchema(
                    name="search_docs",
                    description="Search docs",
                    input_schema={"type": "object"},
                ),
            ),
            overrides={"toolConfig": {"functionCallingConfig": {"mode": "AUTO"}}},
            request_metadata={
                "request_render_snapshot": {
                    "snapshot_id": "ctxsnap_gemini_1",
                    "included_node_ids": ["runtime.contract"],
                },
            },
        )

        preview = GeminiGenerateContentAdapter().preview_request(profile, request)

        self.assertEqual(preview["preview_source"], "provider_adapter")
        self.assertEqual(preview["renderer_id"], "gemini_generate_content")
        self.assertEqual(preview["content_count"], 1)
        self.assertEqual(preview["tool_count"], 1)
        self.assertTrue(preview["has_system"])
        self.assertEqual(preview["request_render_snapshot_id"], "ctxsnap_gemini_1")
        payload_preview = preview["payload_preview"]
        assert isinstance(payload_preview, dict)
        self.assertIn("system_instruction", payload_preview)
        self.assertEqual(
            payload_preview["toolConfig"],
            {"functionCallingConfig": {"mode": "AUTO"}},
        )

    def test_gemini_generate_content_adapter_builds_provider_wire_request(self) -> None:
        profile = LlmProfile(
            id="gemini-wire-request",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding_id="gemini-api-key",
            default_params=LlmDefaults(max_output_tokens=300),
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.SYSTEM, content="system"),
                LlmMessage(role=LlmMessageRole.USER, content="hello"),
            ),
        )

        wire_request = GeminiGenerateContentAdapter()._wire_request(profile, request)

        self.assertIsInstance(wire_request, ProviderWireRequest)
        self.assertEqual(wire_request.renderer_id, "gemini_generate_content")
        self.assertEqual(wire_request.transport, "http")
        self.assertEqual(
            wire_request.endpoint,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
        )
        self.assertIn("system_instruction", wire_request.payload)
        self.assertEqual(wire_request.payload["contents"][0]["role"], "user")
        self.assertEqual(wire_request.render_report["renderer_id"], "gemini_generate_content")

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

    def test_gemini_generate_content_adapter_converts_projected_input_items(self) -> None:
        profile = LlmProfile(
            id="gemini-input-items",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding_id="gemini-inline-token",
        )
        request = _adapter_request(
            messages=(
                LlmMessage(role=LlmMessageRole.USER, content="legacy"),
            ),
            input_items=(
                LlmInputItem(
                    kind=LlmInputItemKind.MESSAGE,
                    payload={"role": "user", "content": "Use replay input"},
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL,
                    payload={
                        "call_id": "call_gemini_replay",
                        "name": "search_docs",
                        "arguments": {"query": "ddd"},
                    },
                ),
                LlmInputItem(
                    kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                    payload={
                        "call_id": "call_gemini_replay",
                        "output": '{"hits":1}',
                    },
                ),
            ),
        )

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content.requests.post",
            return_value=_FakeResponse(
                payload={
                    "responseId": "gemini-replay-1",
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
        contents = kwargs["json"]["contents"]
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[0]["parts"][0]["text"], "Use replay input")
        self.assertEqual(contents[1]["role"], "model")
        self.assertEqual(
            contents[1]["parts"][0]["functionCall"]["id"],
            "call_gemini_replay",
        )
        self.assertEqual(
            contents[1]["parts"][0]["functionCall"]["args"],
            {"query": "ddd"},
        )
        self.assertEqual(contents[2]["role"], "user")
        self.assertEqual(
            contents[2]["parts"][0]["functionResponse"]["id"],
            "call_gemini_replay",
        )
        self.assertNotIn("legacy", json.dumps(contents))

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
