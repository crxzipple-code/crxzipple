from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crxzipple.modules.llm.application import LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmDefaults,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProfile,
    LlmProviderKind,
    ToolSchema,
)
from crxzipple.modules.llm.infrastructure import (
    AnthropicMessagesAdapter,
    GeminiGenerateContentAdapter,
    OpenAIChatCompatibleAdapter,
    OpenAICodexResponsesAdapter,
    OpenAIResponsesAdapter,
)


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
        events: tuple[tuple[str, dict[str, object]], ...] = (),
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._events = events
        self.text = text

    def iter_lines(self, decode_unicode: bool = False):  # noqa: ANN001
        del decode_unicode
        for event_name, payload in self._events:
            yield f"event: {event_name}".encode("utf-8")
            yield f"data: {json.dumps(payload)}".encode("utf-8")
            yield b""


class LlmAdapterTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.previous_env)

    def test_openai_responses_adapter_shapes_request_and_result(self) -> None:
        os.environ["OPENAI_API_KEY"] = "openai-secret"
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
            credential_binding="env:OPENAI_API_KEY",
        )
        request = LlmAdapterRequest(
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

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer openai-secret")
        self.assertEqual(kwargs["json"]["model"], "gpt-5")
        self.assertEqual(kwargs["json"]["tools"][0]["name"], "search_docs")
        self.assertEqual(kwargs["json"]["text"]["format"]["name"], "answer")
        self.assertEqual(kwargs["json"]["reasoning"]["effort"], "medium")
        self.assertTrue(kwargs["json"]["stream"])
        self.assertEqual(kwargs["headers"]["Accept"], "text/event-stream")

    def test_openai_responses_adapter_sanitizes_tool_names_and_restores_tool_calls(self) -> None:
        profile = LlmProfile(
            id="writer-tool-alias",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding="inline-openai-token",
        )
        request = LlmAdapterRequest(
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
        self.assertEqual(kwargs["json"]["tools"][0]["name"], "sample_api_search_docs")

    def test_openai_responses_adapter_stream_invoke_emits_text_delta_and_completed(self) -> None:
        profile = LlmProfile(
            id="writer-stream",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding="inline-openai-token",
        )
        request = LlmAdapterRequest(
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

    def test_openai_responses_adapter_encodes_tool_history_items(self) -> None:
        profile = LlmProfile(
            id="writer-history",
            provider=LlmProviderKind.OPENAI,
            api_family=LlmApiFamily.OPENAI_RESPONSES,
            model_name="gpt-5",
            credential_binding="inline-openai-token",
        )
        request = LlmAdapterRequest(
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
                {"role": "user", "content": "Need docs"},
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
            credential_binding="inline-openai-token",
        )
        request = LlmAdapterRequest(
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
        os.environ["OLLAMA_TOKEN"] = "compat-secret"
        profile = LlmProfile(
            id="local-chat",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="llama3.2",
            base_url="http://localhost:11434/v1",
            credential_binding="env:OLLAMA_TOKEN",
            default_params=LlmDefaults(top_p=0.9, max_output_tokens=256),
        )
        request = LlmAdapterRequest(
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

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer compat-secret")
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "user")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_object")
        self.assertEqual(kwargs["json"]["max_tokens"], 256)

    def test_openai_chat_compatible_adapter_encodes_tool_history_messages(self) -> None:
        profile = LlmProfile(
            id="local-chat-history",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="llama3.2",
            credential_binding="compat-inline-token",
        )
        request = LlmAdapterRequest(
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
                {"role": "user", "content": "Need docs"},
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

    def test_openai_chat_compatible_adapter_sanitizes_tool_names_and_restores_tool_calls(self) -> None:
        profile = LlmProfile(
            id="local-chat-tool-alias",
            provider=LlmProviderKind.OPENAI_COMPATIBLE,
            api_family=LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
            model_name="llama3.2",
            credential_binding="compat-inline-token",
        )
        request = LlmAdapterRequest(
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
        self.assertEqual(kwargs["json"]["tools"][0]["name"], "sample_api_search_docs")

    def test_openai_codex_responses_adapter_reads_auth_json_and_sse(self) -> None:
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
                credential_binding=f"codex_auth_json:{auth_path}",
                default_params=LlmDefaults(reasoning_effort="medium"),
            )
            request = LlmAdapterRequest(
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

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer codex-access-token")
        self.assertEqual(kwargs["headers"]["Accept"], "text/event-stream")
        self.assertEqual(kwargs["json"]["instructions"], "You are a concise coding assistant.")
        self.assertEqual(kwargs["json"]["input"], [{"role": "user", "content": "Reply with codex-ok."}])
        self.assertTrue(kwargs["json"]["stream"])

    def test_openai_codex_responses_adapter_sanitizes_tool_names_and_restores_tool_calls(self) -> None:
        profile = LlmProfile(
            id="codex-tool-alias",
            provider=LlmProviderKind.OPENAI_CODEX,
            api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
            model_name="gpt-5-codex",
            model_family=LlmModelFamily.CODEX,
            credential_binding="codex-inline-token",
        )
        request = LlmAdapterRequest(
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
            credential_binding="codex-inline-token",
        )
        request = LlmAdapterRequest(
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
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_codex_stream",
                                "status": "completed",
                                "model": "gpt-5.1-codex",
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [
                                            {
                                                "type": "output_text",
                                                "text": "codex-stream",
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
            events = list(OpenAICodexResponsesAdapter().stream_invoke(profile, request))

        self.assertEqual([event.type for event in events], ["text_delta", "completed"])
        self.assertEqual(events[0].data["text"], "codex-")
        self.assertEqual(events[1].data["result"]["text"], "codex-stream")

    def test_anthropic_messages_adapter_shapes_request_and_result(self) -> None:
        os.environ["ANTHROPIC_API_KEY"] = "anthropic-secret"
        profile = LlmProfile(
            id="claude",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding="env:ANTHROPIC_API_KEY",
            default_params=LlmDefaults(temperature=0.3, top_p=0.8),
        )
        request = LlmAdapterRequest(
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

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["x-api-key"], "anthropic-secret")
        self.assertEqual(kwargs["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(kwargs["json"]["system"], "Return concise answers.")
        self.assertEqual(kwargs["json"]["tools"][0]["name"], "search_docs")
        self.assertEqual(kwargs["json"]["max_tokens"], 1024)

    def test_anthropic_messages_adapter_encodes_tool_history_messages(self) -> None:
        profile = LlmProfile(
            id="claude-history",
            provider=LlmProviderKind.ANTHROPIC,
            api_family=LlmApiFamily.ANTHROPIC_MESSAGES,
            model_name="claude-sonnet-4-5",
            credential_binding="anthropic-inline-token",
        )
        request = LlmAdapterRequest(
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

    def test_gemini_generate_content_adapter_shapes_request_and_result(self) -> None:
        os.environ["GEMINI_API_KEY"] = "gemini-secret"
        profile = LlmProfile(
            id="gemini",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding="env:GEMINI_API_KEY",
            default_params=LlmDefaults(
                temperature=0.1,
                max_output_tokens=300,
            ),
        )
        request = LlmAdapterRequest(
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

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "gemini-secret")
        self.assertEqual(
            kwargs["json"]["system_instruction"]["parts"][0]["text"],
            "Use tools when needed.",
        )
        self.assertEqual(kwargs["json"]["generationConfig"]["maxOutputTokens"], 300)
        self.assertEqual(
            kwargs["json"]["toolConfig"]["functionCallingConfig"]["mode"],
            "AUTO",
        )

    def test_gemini_generate_content_adapter_encodes_tool_history_messages(self) -> None:
        profile = LlmProfile(
            id="gemini-history",
            provider=LlmProviderKind.GOOGLE,
            api_family=LlmApiFamily.GEMINI_GENERATE_CONTENT,
            model_name="gemini-2.5-pro",
            credential_binding="gemini-inline-token",
        )
        request = LlmAdapterRequest(
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
