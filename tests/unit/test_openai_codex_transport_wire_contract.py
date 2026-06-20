from __future__ import annotations

import json
from unittest.mock import patch

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest as _LlmAdapterRequest
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProfile,
    LlmProviderContinuation,
    LlmProviderKind,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_message_projection import (
    openai_response_projected_input_items,
    projected_input_items_from_messages,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    openai_provider_payload_fingerprint,
    openai_response_input_fingerprints,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses import (
    OpenAICodexResponsesAdapter,
)


def LlmAdapterRequest(**kwargs) -> _LlmAdapterRequest:  # noqa: N802, ANN003
    if "input_items" not in kwargs and kwargs.get("messages"):
        kwargs["input_items"] = tuple(
            projected_input_items_from_messages(
                tuple(
                    message
                    for message in kwargs["messages"]
                    if message.role != LlmMessageRole.SYSTEM
                ),
            ),
        )
    return _LlmAdapterRequest(**kwargs)


def test_codex_websocket_fake_server_records_previous_response_id_and_delta_input() -> None:
    adapter = OpenAICodexResponsesAdapter()
    messages = (
        LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
        LlmMessage(role=LlmMessageRole.USER, content="Original task."),
        LlmMessage(
            role=LlmMessageRole.ASSISTANT,
            content={
                "type": "function_call",
                "call_id": "call_ws",
                "name": "exec",
                "arguments": {"cmd": "echo ws"},
            },
        ),
        LlmMessage(
            role=LlmMessageRole.TOOL,
            tool_call_id="call_ws",
            content="ws output",
        ),
    )
    baseline_items = openai_response_projected_input_items(
        projected_input_items_from_messages(messages[1:3]),
    )
    request = LlmAdapterRequest(
        invocation_id="inv-ws-wire",
        messages=messages,
        input_items=projected_input_items_from_messages(messages),
        resolved_credential="token",
        provider_transport="websocket",
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
            input_item_fingerprints=openai_response_input_fingerprints(
                baseline_items,
            ),
            instructions_fingerprint=openai_provider_payload_fingerprint(
                "Runtime contract.",
            ),
            tool_fingerprints=(),
        ),
    )
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
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "websocket done"},
                            ],
                        },
                    ],
                },
            },
        ),
    )

    with patch(
        "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.websocket.create_connection",
        return_value=fake_ws,
    ):
        response = adapter.invoke(_profile(), request)

    sent = json.loads(fake_ws.sent[0])
    assert sent["type"] == "response.create"
    assert sent["previous_response_id"] == "resp_previous"
    assert sent["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call_ws",
            "output": "ws output",
        },
    ]
    assert "provider_transport" not in sent
    assert response.provider_request_id == "resp_next"
    adapter.close_websocket_pool()


def test_codex_http_fake_server_records_full_input_without_previous_response_id() -> None:
    adapter = OpenAICodexResponsesAdapter()
    request = LlmAdapterRequest(
        invocation_id="inv-http-wire",
        messages=(
            LlmMessage(role=LlmMessageRole.SYSTEM, content="Runtime contract."),
            LlmMessage(role=LlmMessageRole.USER, content="Original task."),
            LlmMessage(
                role=LlmMessageRole.TOOL,
                tool_call_id="call_http",
                content="http output",
            ),
        ),
        resolved_credential="token",
        continuation=LlmProviderContinuation(
            mode="provider_native",
            previous_response_id="resp_previous",
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
                            "id": "resp_http",
                            "status": "completed",
                            "model": "gpt-5.5",
                            "output": [
                                {
                                    "type": "message",
                                    "content": [
                                        {"type": "output_text", "text": "http done"},
                                    ],
                                },
                            ],
                        },
                    },
                ),
            ),
        ),
    ) as post:
        response = adapter.invoke(_profile(), request)

    _, kwargs = post.call_args
    sent = kwargs["json"]
    assert "previous_response_id" not in sent
    assert sent["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "Original task."}],
        },
        {
            "type": "function_call_output",
            "call_id": "call_http",
            "output": "http output",
        },
    ]
    assert sent["stream"] is True
    assert response.provider_request_id == "resp_http"


class _FakeStreamResponse:
    def __init__(
        self,
        *,
        events: tuple[tuple[str | None, dict[str, object]], ...] = (),
    ) -> None:
        self.status_code = 200
        self._events = events
        self.text = ""

    def iter_lines(
        self,
        chunk_size: int | None = None,
        decode_unicode: bool = False,
    ):  # noqa: ANN001
        del chunk_size, decode_unicode
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


def _profile() -> LlmProfile:
    return LlmProfile(
        id="codex-profile",
        provider=LlmProviderKind.OPENAI_CODEX,
        api_family=LlmApiFamily.OPENAI_CODEX_RESPONSES,
        model_name="gpt-5.5",
        model_family=LlmModelFamily.CODEX,
    )
