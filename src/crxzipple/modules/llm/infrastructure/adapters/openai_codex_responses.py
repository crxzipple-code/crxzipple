from __future__ import annotations

from collections.abc import Iterator
import json
from typing import Any

import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmMessageRole,
    LlmResult,
    LlmUsage,
)
from crxzipple.modules.llm.infrastructure.adapters.common import (
    build_openai_tool_name_aliases,
    build_tool_call_intents,
    coerce_text_content,
    default_base_url,
    is_retryable_openai_stream_exception,
    join_url,
    OPENAI_TRANSIENT_HTTP_STATUS_CODES,
    OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS,
    openai_tool_schema,
    RetryableOpenAIStreamError,
    resolve_openai_tool_name,
    resolve_credential_binding,
    sleep_before_openai_stream_retry,
)


class OpenAICodexResponsesAdapter:
    DEFAULT_BASE_URL = "https://chatgpt.com/backend-api/codex"
    DEFAULT_INSTRUCTIONS = "You are a helpful coding assistant."

    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        completed_event: LlmStreamEvent | None = None
        for event in self.stream_invoke(profile, request):
            if event.type == "completed":
                completed_event = event
        if completed_event is None:
            raise RuntimeError(
                f"OpenAI Codex Responses profile '{profile.id}' did not complete.",
            )
        result_payload = completed_event.data.get("result")
        if not isinstance(result_payload, dict):
            raise RuntimeError(
                f"OpenAI Codex Responses profile '{profile.id}' completed without a result payload.",
            )
        result = LlmResult.from_payload(result_payload)
        if result is None:
            raise RuntimeError(
                f"OpenAI Codex Responses profile '{profile.id}' completed with an invalid result payload.",
            )
        provider_request_id = completed_event.data.get("provider_request_id")
        return LlmAdapterResponse(
            result=result,
            provider_request_id=(
                str(provider_request_id) if provider_request_id is not None else None
            ),
        )

    def stream_invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> Iterator[LlmStreamEvent]:
        tool_name_aliases = build_openai_tool_name_aliases(request.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        description = f"OpenAI Codex Responses profile '{profile.id}'"
        attempt = 1
        while True:
            response: requests.Response | None = None
            emitted_output = False
            try:
                response = self._open_stream(
                    profile,
                    request,
                    tool_name_aliases=tool_name_aliases,
                )
                for event in self._stream_sse_response(
                    profile,
                    response,
                    description=description,
                    tool_name_aliases=alias_to_original,
                ):
                    emitted_output = True
                    yield event
                return
            except Exception as exc:
                if (
                    emitted_output
                    or attempt >= OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS
                    or not is_retryable_openai_stream_exception(exc)
                ):
                    raise
                sleep_before_openai_stream_retry(attempt)
                attempt += 1
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()

    def _open_stream(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> requests.Response:
        token = resolve_credential_binding(
            profile.credential_binding or "codex_auth_json",
            required=True,
            description=f"LLM profile '{profile.id}'",
        )
        payload = self._build_payload(
            profile,
            request,
            tool_name_aliases=tool_name_aliases,
        )
        return requests.post(
            join_url(default_base_url(profile, self.DEFAULT_BASE_URL), "/responses"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=payload,
            timeout=profile.timeout_seconds,
            stream=True,
        )

    def _build_payload(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": profile.model_name,
            "instructions": self._resolve_instructions(request),
            "input": self._build_input_items(
                request,
                tool_name_aliases=tool_name_aliases,
            ),
            "store": False,
            "stream": True,
        }
        if request.tool_schemas:
            payload["tools"] = [
                openai_tool_schema(tool, tool_name_aliases=tool_name_aliases)
                for tool in request.tool_schemas
            ]
            payload["tool_choice"] = "auto"
        if request.response_format is not None:
            payload["text"] = {"format": dict(request.response_format)}

        defaults = profile.default_params
        if defaults.temperature is not None:
            payload["temperature"] = defaults.temperature
        if defaults.top_p is not None:
            payload["top_p"] = defaults.top_p
        if defaults.max_output_tokens is not None:
            payload["max_output_tokens"] = defaults.max_output_tokens
        if defaults.reasoning_effort is not None:
            payload["reasoning"] = {"effort": defaults.reasoning_effort}

        for key, value in request.overrides.items():
            if key not in {"model", "input", "stream"}:
                payload[key] = value
        return payload

    def _resolve_instructions(self, request: LlmAdapterRequest) -> str:
        system_messages = [
            coerce_text_content(message.content)
            for message in request.messages
            if message.role == LlmMessageRole.SYSTEM
        ]
        if system_messages:
            return "\n\n".join(system_messages)
        return self.DEFAULT_INSTRUCTIONS

    def _build_input_items(
        self,
        request: LlmAdapterRequest,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == LlmMessageRole.SYSTEM:
                continue
            assistant_tool_call = self._build_assistant_tool_call(
                message,
                tool_name_aliases=tool_name_aliases,
            )
            if assistant_tool_call is not None:
                items.append(assistant_tool_call)
                continue
            tool_output = self._build_tool_output(message)
            if tool_output is not None:
                items.append(tool_output)
                continue
            role = message.role.value
            if role not in {
                LlmMessageRole.USER.value,
                LlmMessageRole.ASSISTANT.value,
            }:
                role = LlmMessageRole.USER.value
            items.append(
                {
                    "role": role,
                    "content": coerce_text_content(message.content),
                },
            )
        if not items:
            raise RuntimeError(
                "OpenAI Codex invocations require at least one non-system message.",
            )
        return items

    @staticmethod
    def _build_assistant_tool_call(
        message: Any,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        if message.role != LlmMessageRole.ASSISTANT:
            return None
        if not isinstance(message.content, dict):
            return None
        if message.content.get("type") != "function_call":
            return None
        call_id = message.content.get("call_id") or message.tool_call_id
        name = message.content.get("name")
        if not isinstance(call_id, str) or not call_id.strip():
            return None
        if not isinstance(name, str) or not name.strip():
            return None
        arguments = message.content.get("arguments", {})
        if isinstance(arguments, str):
            arguments_text = arguments
        else:
            arguments_text = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        return {
            "type": "function_call",
            "call_id": call_id.strip(),
            "name": resolve_openai_tool_name(
                name.strip(),
                tool_name_aliases=tool_name_aliases,
            ),
            "arguments": arguments_text,
        }

    @staticmethod
    def _build_tool_output(message: Any) -> dict[str, Any] | None:
        if message.role != LlmMessageRole.TOOL:
            return None
        call_id = message.tool_call_id
        if call_id is None or not call_id.strip():
            return None
        return {
            "type": "function_call_output",
            "call_id": call_id.strip(),
            "output": coerce_text_content(message.content),
        }

    @classmethod
    def _stream_sse_response(
        cls,
        profile: LlmProfile,
        response: requests.Response,
        *,
        description: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> Iterator[LlmStreamEvent]:
        if response.status_code >= 400:
            if response.status_code in OPENAI_TRANSIENT_HTTP_STATUS_CODES:
                raise RetryableOpenAIStreamError(
                    f"{description} failed with HTTP {response.status_code}: {response.text}",
                )
            raise RuntimeError(
                f"{description} failed with HTTP {response.status_code}: {response.text}",
            )

        current_event: str | None = None
        data_lines: list[str] = []
        sequence = 1
        for raw_line in response.iter_lines(decode_unicode=False):
            if raw_line is None:
                continue
            line = (
                raw_line.decode("utf-8", errors="replace")
                if isinstance(raw_line, bytes)
                else str(raw_line)
            ).rstrip("\r\n")
            if line.startswith("event: "):
                current_event = line[7:]
                continue
            if line.startswith("data: "):
                data_lines.append(line[6:])
                continue
            if line:
                continue
            event, event_completed = cls._consume_sse_event(
                profile,
                current_event,
                data_lines,
                sequence=sequence,
                description=description,
                tool_name_aliases=tool_name_aliases,
            )
            if event is not None:
                yield event
                sequence += 1
            if event_completed:
                return
            current_event = None
            data_lines = []

        if data_lines:
            event, event_completed = cls._consume_sse_event(
                profile,
                current_event,
                data_lines,
                sequence=sequence,
                description=description,
                tool_name_aliases=tool_name_aliases,
            )
            if event is not None:
                yield event
            if event_completed:
                return

        raise RuntimeError(f"{description} returned an incomplete SSE response.")

    @classmethod
    def _consume_sse_event(
        cls,
        profile: LlmProfile,
        event_name: str | None,
        data_lines: list[str],
        *,
        sequence: int,
        description: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> tuple[LlmStreamEvent | None, bool]:
        if not data_lines:
            return None, False
        payload_text = "\n".join(data_lines)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{description} returned invalid SSE JSON: {payload_text}",
            ) from exc
        if not isinstance(payload, dict):
            return None, False

        response_payload = payload.get("response")
        if event_name == "response.completed":
            if isinstance(response_payload, dict):
                response = cls._build_response(
                    profile,
                    dict(response_payload),
                    tool_name_aliases=tool_name_aliases,
                )
                return (
                    LlmStreamEvent(
                        type="completed",
                        sequence=sequence,
                        data={
                            "result": response.result.to_payload(),
                            "provider_request_id": response.provider_request_id,
                        },
                    ),
                    True,
                )
            return None, True

        if payload.get("type") == "error":
            error_payload = payload.get("error")
            message = payload.get("message")
            if isinstance(error_payload, dict):
                message = error_payload.get("message") or message
                if error_payload.get("code") == "server_error":
                    raise RetryableOpenAIStreamError(
                        f"{description} returned an error event: {message or payload}",
                    )
            raise RuntimeError(
                f"{description} returned an error event: {message or payload}",
            )

        if event_name == "response.output_text.delta":
            delta = payload.get("delta")
            if delta is not None:
                return (
                    LlmStreamEvent(
                        type="text_delta",
                        sequence=sequence,
                        data={"text": str(delta)},
                    ),
                    False,
                )

        if event_name in {"response.created", "response.in_progress"}:
            return None, False
        return None, False

    @staticmethod
    def _build_response(
        profile: LlmProfile,
        data: dict[str, Any],
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> LlmAdapterResponse:
        output = data.get("output") if isinstance(data.get("output"), list) else []
        text_fragments: list[str] = []
        raw_tool_calls: list[dict[str, Any]] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
                raw_tool_calls.append(item)
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "output_text" and block.get("text") is not None:
                    text_fragments.append(str(block.get("text")))

        usage_raw = data.get("usage")
        usage = None
        if isinstance(usage_raw, dict):
            output_details = usage_raw.get("output_tokens_details")
            reasoning_tokens = None
            if isinstance(output_details, dict):
                reasoning_tokens = output_details.get("reasoning_tokens")
            usage = LlmUsage(
                input_tokens=usage_raw.get("input_tokens"),
                output_tokens=usage_raw.get("output_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
                reasoning_tokens=reasoning_tokens,
            )

        response_id = data.get("id")
        return LlmAdapterResponse(
            result=LlmResult(
                text="".join(text_fragments) or None,
                tool_calls=build_tool_call_intents(
                    raw_tool_calls,
                    tool_name_aliases=tool_name_aliases,
                ),
                usage=usage,
                finish_reason=str(data.get("status")) if data.get("status") is not None else None,
                metadata={
                    "provider": profile.provider.value,
                    "response_id": response_id,
                    "model": data.get("model"),
                    "transport": "sse",
                },
            ),
            provider_request_id=str(response_id) if response_id is not None else None,
        )
