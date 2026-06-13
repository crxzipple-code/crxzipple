from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import json
from typing import Any

import httpx
import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmContinuationSignal,
    LlmMessageRole,
    LlmResponseItem,
    LlmResult,
    LlmUsage,
)
from crxzipple.modules.llm.infrastructure.adapters.common import (
    async_sleep_before_openai_stream_retry,
    build_openai_continuation_signal,
    build_openai_response_items,
    build_openai_tool_name_aliases,
    coerce_text_content,
    default_base_url,
    ensure_image_input_supported,
    httpx_response_text,
    is_retryable_openai_stream_exception,
    join_url,
    openai_response_stream_event,
    openai_response_input_items,
    OPENAI_TRANSIENT_HTTP_STATUS_CODES,
    OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS,
    openai_tool_schema,
    RetryableOpenAIStreamError,
    resolve_credential_binding,
    sleep_before_openai_stream_retry,
)
from crxzipple.shared.infrastructure.http import get_async_http_client


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
        response_items = _response_items_from_completed_event(completed_event)
        return LlmAdapterResponse(
            result=result,
            response_items=response_items,
            continuation=_continuation_from_completed_event(completed_event),
            provider_request_id=(
                str(provider_request_id) if provider_request_id is not None else None
            ),
        )

    async def invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        completed_event: LlmStreamEvent | None = None
        async for event in self.stream_invoke_async(profile, request):
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
        response_items = _response_items_from_completed_event(completed_event)
        return LlmAdapterResponse(
            result=result,
            response_items=response_items,
            continuation=_continuation_from_completed_event(completed_event),
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
                    invocation_id=request.invocation_id,
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

    async def stream_invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> AsyncIterator[LlmStreamEvent]:
        tool_name_aliases = build_openai_tool_name_aliases(request.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        description = f"OpenAI Codex Responses profile '{profile.id}'"
        attempt = 1
        while True:
            emitted_output = False
            try:
                url, headers, payload = self._stream_request(
                    profile,
                    request,
                    tool_name_aliases=tool_name_aliases,
                )
                client = get_async_http_client(
                    url,
                    timeout=profile.timeout_seconds,
                    client_factory=httpx.AsyncClient,
                )
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                ) as response:
                    async for event in self._stream_sse_response_async(
                        profile,
                        response,
                        invocation_id=request.invocation_id,
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
                await async_sleep_before_openai_stream_retry(attempt)
                attempt += 1

    def _open_stream(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> requests.Response:
        url, headers, payload = self._stream_request(
            profile,
            request,
            tool_name_aliases=tool_name_aliases,
        )
        return requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=profile.timeout_seconds,
            stream=True,
        )

    def _stream_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        ensure_image_input_supported(profile, request.messages)
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=True,
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        payload = self._build_payload(
            profile,
            request,
            tool_name_aliases=tool_name_aliases,
        )
        return (
            join_url(default_base_url(profile, self.DEFAULT_BASE_URL), "/responses"),
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            payload,
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
        reasoning = _merged_reasoning_payload(
            defaults_reasoning_effort=defaults.reasoning_effort,
            override_reasoning=request.overrides.get("reasoning"),
        )
        if reasoning:
            payload["reasoning"] = reasoning

        for key, value in request.overrides.items():
            if key not in {"model", "input", "stream", "reasoning"}:
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
        items = openai_response_input_items(
            tuple(
                message
                for message in request.messages
                if message.role != LlmMessageRole.SYSTEM
            ),
            tool_name_aliases=tool_name_aliases,
        )
        if not items:
            raise RuntimeError(
                "OpenAI Codex invocations require at least one non-system message.",
            )
        return items

    @classmethod
    def _stream_sse_response(
        cls,
        profile: LlmProfile,
        response: requests.Response,
        *,
        invocation_id: str,
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
        completed_output_items: dict[int, dict[str, Any]] = {}
        sequence = 1
        for raw_line in response.iter_lines(chunk_size=1, decode_unicode=False):
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
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
                completed_output_items=completed_output_items,
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
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
                completed_output_items=completed_output_items,
            )
            if event is not None:
                yield event
            if event_completed:
                return

        raise RuntimeError(f"{description} returned an incomplete SSE response.")

    @classmethod
    async def _stream_sse_response_async(
        cls,
        profile: LlmProfile,
        response: httpx.Response,
        *,
        invocation_id: str,
        description: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> AsyncIterator[LlmStreamEvent]:
        if response.status_code >= 400:
            response_text = await httpx_response_text(response)
            if response.status_code in OPENAI_TRANSIENT_HTTP_STATUS_CODES:
                raise RetryableOpenAIStreamError(
                    f"{description} failed with HTTP {response.status_code}: {response_text}",
                )
            raise RuntimeError(
                f"{description} failed with HTTP {response.status_code}: {response_text}",
            )

        current_event: str | None = None
        data_lines: list[str] = []
        completed_output_items: dict[int, dict[str, Any]] = {}
        sequence = 1
        async for line in response.aiter_lines():
            line = line.rstrip("\r\n")
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
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
                completed_output_items=completed_output_items,
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
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
                completed_output_items=completed_output_items,
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
        invocation_id: str,
        tool_name_aliases: dict[str, str] | None = None,
        completed_output_items: dict[int, dict[str, Any]] | None = None,
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

        resolved_event_name = (
            event_name
            if isinstance(event_name, str) and event_name.strip()
            else payload.get("type")
            if isinstance(payload.get("type"), str)
            else None
        )

        response_payload = payload.get("response")
        if resolved_event_name == "response.completed":
            if isinstance(response_payload, dict):
                normalized_response_payload = dict(response_payload)
                if (
                    completed_output_items
                    and not normalized_response_payload.get("output")
                ):
                    normalized_response_payload["output"] = [
                        dict(item)
                        for _, item in sorted(completed_output_items.items())
                    ]
                response = cls._build_response(
                    profile,
                    normalized_response_payload,
                    invocation_id=invocation_id,
                    tool_name_aliases=tool_name_aliases,
                )
                return (
                    LlmStreamEvent(
                        type="completed",
                        sequence=sequence,
                        data={
                            "result": response.result.to_payload(),
                            "response_items": [
                                item.to_payload() for item in response.response_items
                            ],
                            "continuation": (
                                response.continuation.to_payload()
                                if response.continuation is not None
                                else None
                            ),
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

        if resolved_event_name == "response.output_text.delta":
            delta = payload.get("delta")
            if delta is None:
                delta = payload.get("text")
            if delta is not None:
                return (
                    LlmStreamEvent(
                        type="text_delta",
                        sequence=sequence,
                        data={"text": str(delta)},
                    ),
                    False,
                )

        if resolved_event_name in {
            "response.output_item.added",
            "response.output_item.created",
            "response.output_item.done",
            "response.reasoning_summary_text.delta",
            "response.reasoning_summary.delta",
            "response.reasoning_text.delta",
            "response.reasoning.delta",
            "response.function_call_arguments.delta",
            "response.tool_call_arguments.delta",
        }:
            if resolved_event_name == "response.output_item.done":
                output_index = payload.get("output_index")
                item = payload.get("item")
                if (
                    completed_output_items is not None
                    and isinstance(output_index, int)
                    and isinstance(item, dict)
                ):
                    completed_output_items[output_index] = dict(item)
            return (
                openai_response_stream_event(
                    event_name=resolved_event_name,
                    payload=payload,
                    sequence=sequence,
                ),
                False,
            )

        if resolved_event_name in {"response.created", "response.in_progress"}:
            return None, False
        return None, False

    @staticmethod
    def _build_response(
        profile: LlmProfile,
        data: dict[str, Any],
        *,
        invocation_id: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> LlmAdapterResponse:
        output = data.get("output") if isinstance(data.get("output"), list) else []
        text_fragments: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
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
        response_items = build_openai_response_items(
            invocation_id=invocation_id,
            response_payload=data,
            tool_name_aliases=tool_name_aliases,
        )
        return LlmAdapterResponse(
            result=LlmResult.from_response_items(
                response_items,
                usage=usage,
                finish_reason=str(data.get("status")) if data.get("status") is not None else None,
                metadata={
                    "provider": profile.provider.value,
                    "response_id": response_id,
                    "model": data.get("model"),
                    "transport": "sse",
                },
                text_fallback="".join(text_fragments) or None,
            ),
            response_items=response_items,
            continuation=build_openai_continuation_signal(data, response_items),
            provider_request_id=str(response_id) if response_id is not None else None,
        )


def _response_items_from_completed_event(
    event: LlmStreamEvent,
) -> tuple[LlmResponseItem, ...]:
    raw_items = event.data.get("response_items")
    if not isinstance(raw_items, list):
        return ()
    return tuple(
        LlmResponseItem.from_payload(item)
        for item in raw_items
        if isinstance(item, dict)
    )


def _continuation_from_completed_event(
    event: LlmStreamEvent,
) -> LlmContinuationSignal | None:
    payload = event.data.get("continuation")
    if not isinstance(payload, dict):
        return None
    return LlmContinuationSignal.from_payload(payload)


def _merged_reasoning_payload(
    *,
    defaults_reasoning_effort: str | None,
    override_reasoning: object,
) -> dict[str, Any]:
    reasoning: dict[str, Any] = {}
    if defaults_reasoning_effort is not None:
        reasoning["effort"] = defaults_reasoning_effort
    if isinstance(override_reasoning, dict):
        reasoning.update(override_reasoning)
    return reasoning
