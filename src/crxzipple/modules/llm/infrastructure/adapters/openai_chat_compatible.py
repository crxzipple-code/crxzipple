from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import json
import re
from typing import Any
from uuid import uuid4

import httpx
import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmUsage,
    utcnow,
)
from crxzipple.modules.llm.infrastructure.adapters.common import (
    build_openai_tool_name_aliases,
    build_tool_call_intents,
    coerce_text_content,
    default_base_url,
    ensure_image_input_supported,
    ensure_json_response,
    httpx_response_text,
    join_url,
    openai_chat_messages,
    openai_chat_tool_schema,
    resolve_credential_binding,
)
from crxzipple.shared.infrastructure.http import get_async_http_client


class OpenAIChatCompatibleAdapter:
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    TOOL_CALL_BLOCK_PATTERN = re.compile(
        r"<tool_call>\s*(.*?)\s*</tool_call>",
        re.DOTALL,
    )
    FUNCTION_PATTERN = re.compile(
        r"<function=([^>]+)>\s*(.*?)\s*</function>",
        re.DOTALL,
    )
    PARAMETER_PATTERN = re.compile(
        r"<parameter=([^>]+)>\s*(.*?)\s*</parameter>",
        re.DOTALL,
    )

    @staticmethod
    def _merge_payload_fields(
        payload: dict[str, Any],
        fields: dict[str, Any] | None,
    ) -> None:
        if not fields:
            return
        for key, value in fields.items():
            if key in {"model", "messages", "tools"}:
                continue
            if isinstance(payload.get(key), dict) and isinstance(value, dict):
                merged = dict(payload[key])
                merged.update(value)
                payload[key] = merged
                continue
            payload[key] = value

    @staticmethod
    def _normalize_message_order(
        messages: tuple[LlmMessage, ...],
    ) -> tuple[LlmMessage, ...]:
        system_messages = tuple(
            message for message in messages if message.role == LlmMessageRole.SYSTEM
        )
        if not system_messages:
            return messages
        non_system_messages = tuple(
            message for message in messages if message.role != LlmMessageRole.SYSTEM
        )
        combined_system = LlmMessage(
            role=LlmMessageRole.SYSTEM,
            content="\n\n".join(
                coerce_text_content(message.content)
                for message in system_messages
            ),
        )
        return (combined_system,) + non_system_messages

    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        normalized_messages = self._normalize_message_order(request.messages)
        ensure_image_input_supported(profile, normalized_messages)
        tool_name_aliases = build_openai_tool_name_aliases(request.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=profile.provider.value == "openai_compatible",
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        payload: dict[str, Any] = {
            "model": profile.model_name,
            "messages": openai_chat_messages(
                normalized_messages,
                tool_name_aliases=tool_name_aliases,
            ),
        }
        if request.tool_schemas:
            payload["tools"] = [
                openai_chat_tool_schema(tool, tool_name_aliases=tool_name_aliases)
                for tool in request.tool_schemas
            ]
        if request.response_format is not None:
            payload["response_format"] = dict(request.response_format)

        defaults = profile.default_params
        if defaults.temperature is not None:
            payload["temperature"] = defaults.temperature
        if defaults.top_p is not None:
            payload["top_p"] = defaults.top_p
        if defaults.max_output_tokens is not None:
            payload["max_tokens"] = defaults.max_output_tokens
        self._merge_payload_fields(payload, defaults.extra_body)

        overrides = dict(request.overrides)
        extra_body_overrides = overrides.pop("extra_body", None)
        if isinstance(extra_body_overrides, dict):
            self._merge_payload_fields(payload, extra_body_overrides)

        for key, value in overrides.items():
            if key not in {"model", "messages", "tools"}:
                payload[key] = value

        response = requests.post(
            join_url(
                default_base_url(profile, self.DEFAULT_BASE_URL),
                "/chat/completions",
            ),
            headers=headers,
            json=payload,
            timeout=profile.timeout_seconds,
        )
        data = ensure_json_response(
            response,
            description=f"OpenAI-compatible profile '{profile.id}'",
        )

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned no choices.",
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned an invalid choice payload.",
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned no message payload.",
            )

        raw_tool_calls: list[dict[str, Any]] = []
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for item in tool_calls:
                if not isinstance(item, dict):
                    continue
                function_payload = item.get("function")
                raw_tool_calls.append(
                    {
                        "id": item.get("id"),
                        "name": (
                            function_payload.get("name")
                            if isinstance(function_payload, dict)
                            else None
                        ),
                        "arguments": (
                            function_payload.get("arguments")
                            if isinstance(function_payload, dict)
                            else None
                        ),
                    },
                )
        content_text = (
            str(message.get("content"))
            if message.get("content") is not None
            else None
        )
        if not raw_tool_calls and content_text:
            parsed_tool_calls = self._parse_xmlish_tool_calls(content_text)
            if parsed_tool_calls:
                raw_tool_calls.extend(parsed_tool_calls)
                content_text = self._strip_xmlish_tool_calls(content_text)

        usage_raw = data.get("usage")
        usage = None
        if isinstance(usage_raw, dict):
            usage = LlmUsage(
                input_tokens=usage_raw.get("prompt_tokens"),
                output_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            )

        response_items = _chat_response_items(
            invocation_id=request.invocation_id,
            content_text=content_text,
            raw_tool_calls=raw_tool_calls,
            provider_response_id=(
                str(data.get("id")) if data.get("id") is not None else None
            ),
            model_name=str(data.get("model")) if data.get("model") is not None else None,
            transport="json",
            tool_name_aliases=alias_to_original,
        )
        return LlmAdapterResponse(
            result=LlmResult.from_response_items(
                response_items,
                usage=usage,
                finish_reason=(
                    str(choice.get("finish_reason"))
                    if choice.get("finish_reason") is not None
                    else None
                ),
                metadata={
                    "provider": profile.provider.value,
                    "response_id": data.get("id"),
                    "model": data.get("model"),
                },
                text_fallback=content_text,
            ),
            response_items=response_items,
            provider_request_id=str(data.get("id")) if data.get("id") is not None else None,
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
                f"OpenAI-compatible profile '{profile.id}' did not complete.",
            )
        result_payload = completed_event.data.get("result")
        if not isinstance(result_payload, dict):
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' completed without a result payload.",
            )
        result = LlmResult.from_payload(result_payload)
        if result is None:
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' completed with an invalid result payload.",
            )
        provider_request_id = completed_event.data.get("provider_request_id")
        response_items = _response_items_from_completed_event(completed_event)
        return LlmAdapterResponse(
            result=result,
            response_items=response_items,
            provider_request_id=(
                str(provider_request_id) if provider_request_id is not None else None
            ),
        )

    def stream_invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> Iterator[LlmStreamEvent]:
        url, headers, payload, alias_to_original = self._stream_request(
            profile,
            request,
        )

        response: requests.Response | None = None
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=profile.timeout_seconds,
                stream=True,
            )
            yield from self._stream_sse_response(
                profile,
                response,
                description=f"OpenAI-compatible profile '{profile.id}'",
                invocation_id=request.invocation_id,
                tool_name_aliases=alias_to_original,
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    async def stream_invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> AsyncIterator[LlmStreamEvent]:
        url, headers, payload, alias_to_original = self._stream_request(
            profile,
            request,
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
                description=f"OpenAI-compatible profile '{profile.id}'",
                invocation_id=request.invocation_id,
                tool_name_aliases=alias_to_original,
            ):
                yield event

    def _stream_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> tuple[str, dict[str, str], dict[str, Any], dict[str, str]]:
        normalized_messages = self._normalize_message_order(request.messages)
        ensure_image_input_supported(profile, normalized_messages)
        tool_name_aliases = build_openai_tool_name_aliases(request.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=profile.provider.value == "openai_compatible",
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        payload: dict[str, Any] = {
            "model": profile.model_name,
            "messages": openai_chat_messages(
                normalized_messages,
                tool_name_aliases=tool_name_aliases,
            ),
            "stream": True,
        }
        if request.tool_schemas:
            payload["tools"] = [
                openai_chat_tool_schema(tool, tool_name_aliases=tool_name_aliases)
                for tool in request.tool_schemas
            ]
        if request.response_format is not None:
            payload["response_format"] = dict(request.response_format)

        defaults = profile.default_params
        if defaults.temperature is not None:
            payload["temperature"] = defaults.temperature
        if defaults.top_p is not None:
            payload["top_p"] = defaults.top_p
        if defaults.max_output_tokens is not None:
            payload["max_tokens"] = defaults.max_output_tokens
        self._merge_payload_fields(payload, defaults.extra_body)

        overrides = dict(request.overrides)
        extra_body_overrides = overrides.pop("extra_body", None)
        if isinstance(extra_body_overrides, dict):
            self._merge_payload_fields(payload, extra_body_overrides)

        for key, value in overrides.items():
            if key not in {"model", "messages", "tools", "stream"}:
                payload[key] = value

        return (
            join_url(
                default_base_url(profile, self.DEFAULT_BASE_URL),
                "/chat/completions",
            ),
            headers,
            payload,
            alias_to_original,
        )

    @classmethod
    def _stream_sse_response(
        cls,
        profile: LlmProfile,
        response: requests.Response,
        *,
        description: str,
        invocation_id: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> Iterator[LlmStreamEvent]:
        if response.status_code >= 400:
            raise RuntimeError(
                f"{description} failed with HTTP {response.status_code}: {response.text}",
            )
        headers = getattr(response, "headers", {}) or {}
        content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
        if content_type and "text/event-stream" not in content_type.lower():
            response_text = str(getattr(response, "text", "") or "")
            if not response_text.strip():
                raise RuntimeError(
                    f"{description} returned an empty non-SSE response.",
                )
            try:
                payload = json.loads(response_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{description} returned non-SSE response: {response_text}",
                ) from exc
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"{description} returned an invalid non-SSE response.",
                )
            yield cls._build_json_completed_event(
                profile,
                payload,
                sequence=1,
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
            )
            return

        sequence = 1
        response_id: str | None = None
        model_name: str | None = None
        finish_reason: str | None = None
        usage_raw: dict[str, Any] | None = None
        text_fragments: list[str] = []
        tool_call_chunks: dict[int, dict[str, Any]] = {}

        for raw_line in response.iter_lines(chunk_size=1, decode_unicode=False):
            if raw_line is None:
                continue
            line = (
                raw_line.decode("utf-8", errors="replace")
                if isinstance(raw_line, bytes)
                else str(raw_line)
            ).strip()
            if not line or line.startswith("event:"):
                continue
            if not line.startswith("data:"):
                continue
            payload_text = line[5:].strip()
            if payload_text == "[DONE]":
                yield cls._build_stream_completed_event(
                    profile,
                    sequence=sequence,
                    invocation_id=invocation_id,
                    response_id=response_id,
                    model_name=model_name,
                    text_fragments=text_fragments,
                    tool_call_chunks=tool_call_chunks,
                    usage_raw=usage_raw,
                    finish_reason=finish_reason,
                    tool_name_aliases=tool_name_aliases,
                )
                return
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{description} returned invalid SSE JSON: {payload_text}",
                ) from exc
            if not isinstance(payload, dict):
                continue
            if payload.get("error") is not None:
                raise RuntimeError(
                    f"{description} returned an error event: {payload.get('error')}",
                )
            if payload.get("id") is not None:
                response_id = str(payload.get("id"))
            if payload.get("model") is not None:
                model_name = str(payload.get("model"))
            if isinstance(payload.get("usage"), dict):
                usage_raw = dict(payload.get("usage") or {})
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if content is not None:
                    text = str(content)
                    text_fragments.append(text)
                    yield LlmStreamEvent(
                        type="text_delta",
                        sequence=sequence,
                        data={"text": text},
                    )
                    sequence += 1
                tool_calls = delta.get("tool_calls")
                if isinstance(tool_calls, list):
                    cls._merge_stream_tool_calls(tool_call_chunks, tool_calls)
            if choice.get("finish_reason") is not None:
                finish_reason = str(choice.get("finish_reason"))
                yield cls._build_stream_completed_event(
                    profile,
                    sequence=sequence,
                    invocation_id=invocation_id,
                    response_id=response_id,
                    model_name=model_name,
                    text_fragments=text_fragments,
                    tool_call_chunks=tool_call_chunks,
                    usage_raw=usage_raw,
                    finish_reason=finish_reason,
                    tool_name_aliases=tool_name_aliases,
                )
                return

        if text_fragments or tool_call_chunks:
            yield cls._build_stream_completed_event(
                profile,
                sequence=sequence,
                invocation_id=invocation_id,
                response_id=response_id,
                model_name=model_name,
                text_fragments=text_fragments,
                tool_call_chunks=tool_call_chunks,
                usage_raw=usage_raw,
                finish_reason=finish_reason,
                tool_name_aliases=tool_name_aliases,
            )
            return

        raise RuntimeError(f"{description} returned an incomplete SSE response.")

    @classmethod
    async def _stream_sse_response_async(
        cls,
        profile: LlmProfile,
        response: httpx.Response,
        *,
        description: str,
        invocation_id: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> AsyncIterator[LlmStreamEvent]:
        if response.status_code >= 400:
            response_text = await httpx_response_text(response)
            raise RuntimeError(
                f"{description} failed with HTTP {response.status_code}: {response_text}",
            )
        headers = getattr(response, "headers", {}) or {}
        content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
        if content_type and "text/event-stream" not in content_type.lower():
            response_text = await httpx_response_text(response)
            if not response_text.strip():
                raise RuntimeError(
                    f"{description} returned an empty non-SSE response.",
                )
            try:
                payload = json.loads(response_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{description} returned non-SSE response: {response_text}",
                ) from exc
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"{description} returned an invalid non-SSE response.",
                )
            yield cls._build_json_completed_event(
                profile,
                payload,
                sequence=1,
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
            )
            return

        sequence = 1
        response_id: str | None = None
        model_name: str | None = None
        finish_reason: str | None = None
        usage_raw: dict[str, Any] | None = None
        text_fragments: list[str] = []
        tool_call_chunks: dict[int, dict[str, Any]] = {}

        async for line in response.aiter_lines():
            line = line.strip()
            if not line or line.startswith("event:"):
                continue
            if not line.startswith("data:"):
                continue
            payload_text = line[5:].strip()
            if payload_text == "[DONE]":
                yield cls._build_stream_completed_event(
                    profile,
                    sequence=sequence,
                    invocation_id=invocation_id,
                    response_id=response_id,
                    model_name=model_name,
                    text_fragments=text_fragments,
                    tool_call_chunks=tool_call_chunks,
                    usage_raw=usage_raw,
                    finish_reason=finish_reason,
                    tool_name_aliases=tool_name_aliases,
                )
                return
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{description} returned invalid SSE JSON: {payload_text}",
                ) from exc
            if not isinstance(payload, dict):
                continue
            if payload.get("error") is not None:
                raise RuntimeError(
                    f"{description} returned an error event: {payload.get('error')}",
                )
            if payload.get("id") is not None:
                response_id = str(payload.get("id"))
            if payload.get("model") is not None:
                model_name = str(payload.get("model"))
            if isinstance(payload.get("usage"), dict):
                usage_raw = dict(payload.get("usage") or {})
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if content is not None:
                    text = str(content)
                    text_fragments.append(text)
                    yield LlmStreamEvent(
                        type="text_delta",
                        sequence=sequence,
                        data={"text": text},
                    )
                    sequence += 1
                tool_calls = delta.get("tool_calls")
                if isinstance(tool_calls, list):
                    cls._merge_stream_tool_calls(tool_call_chunks, tool_calls)
            if choice.get("finish_reason") is not None:
                finish_reason = str(choice.get("finish_reason"))
                yield cls._build_stream_completed_event(
                    profile,
                    sequence=sequence,
                    invocation_id=invocation_id,
                    response_id=response_id,
                    model_name=model_name,
                    text_fragments=text_fragments,
                    tool_call_chunks=tool_call_chunks,
                    usage_raw=usage_raw,
                    finish_reason=finish_reason,
                    tool_name_aliases=tool_name_aliases,
                )
                return

        if text_fragments or tool_call_chunks:
            yield cls._build_stream_completed_event(
                profile,
                sequence=sequence,
                invocation_id=invocation_id,
                response_id=response_id,
                model_name=model_name,
                text_fragments=text_fragments,
                tool_call_chunks=tool_call_chunks,
                usage_raw=usage_raw,
                finish_reason=finish_reason,
                tool_name_aliases=tool_name_aliases,
            )
            return

        raise RuntimeError(f"{description} returned an incomplete SSE response.")

    @classmethod
    def _build_json_completed_event(
        cls,
        profile: LlmProfile,
        payload: dict[str, Any],
        *,
        sequence: int,
        invocation_id: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> LlmStreamEvent:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned no choices.",
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned an invalid choice payload.",
            )
        message = choice.get("message")
        if not isinstance(message, dict):
            raise RuntimeError(
                f"OpenAI-compatible profile '{profile.id}' returned no message payload.",
            )
        raw_tool_calls: list[dict[str, Any]] = []
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for item in tool_calls:
                if not isinstance(item, dict):
                    continue
                function_payload = item.get("function")
                raw_tool_calls.append(
                    {
                        "id": item.get("id"),
                        "name": (
                            function_payload.get("name")
                            if isinstance(function_payload, dict)
                            else None
                        ),
                        "arguments": (
                            function_payload.get("arguments")
                            if isinstance(function_payload, dict)
                            else None
                        ),
                    },
                )
        content_text = (
            str(message.get("content"))
            if message.get("content") is not None
            else None
        )
        if not raw_tool_calls and content_text:
            parsed_tool_calls = cls._parse_xmlish_tool_calls(content_text)
            if parsed_tool_calls:
                raw_tool_calls.extend(parsed_tool_calls)
                content_text = cls._strip_xmlish_tool_calls(content_text)
        usage_raw = payload.get("usage")
        usage = None
        if isinstance(usage_raw, dict):
            usage = LlmUsage(
                input_tokens=usage_raw.get("prompt_tokens"),
                output_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            )
        provider_request_id = (
            str(payload.get("id")) if payload.get("id") is not None else None
        )
        response_items = _chat_response_items(
            invocation_id=invocation_id,
            content_text=content_text,
            raw_tool_calls=raw_tool_calls,
            provider_response_id=provider_request_id,
            model_name=str(payload.get("model")) if payload.get("model") is not None else None,
            transport="json_fallback",
            tool_name_aliases=tool_name_aliases,
        )
        result = LlmResult.from_response_items(
            response_items,
            usage=usage,
            finish_reason=(
                str(choice.get("finish_reason"))
                if choice.get("finish_reason") is not None
                else None
            ),
            metadata={
                "provider": profile.provider.value,
                "response_id": payload.get("id"),
                "model": payload.get("model"),
                "transport": "json_fallback",
            },
            text_fallback=content_text,
        )
        return LlmStreamEvent(
            type="completed",
            sequence=sequence,
            data={
                "result": result.to_payload(),
                "response_items": [item.to_payload() for item in response_items],
                "provider_request_id": provider_request_id,
            },
        )

    @staticmethod
    def _merge_stream_tool_calls(
        tool_call_chunks: dict[int, dict[str, Any]],
        tool_calls: list[Any],
    ) -> None:
        for position, item in enumerate(tool_calls):
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", position))
            except (TypeError, ValueError):
                index = position
            existing = tool_call_chunks.setdefault(
                index,
                {
                    "id": None,
                    "name": "",
                    "arguments": "",
                },
            )
            if item.get("id") is not None:
                existing["id"] = str(item.get("id"))
            function = item.get("function")
            if not isinstance(function, dict):
                continue
            if function.get("name") is not None:
                existing["name"] = f"{existing.get('name') or ''}{function.get('name')}"
            if function.get("arguments") is not None:
                existing["arguments"] = (
                    f"{existing.get('arguments') or ''}{function.get('arguments')}"
                )

    @classmethod
    def _build_stream_completed_event(
        cls,
        profile: LlmProfile,
        *,
        sequence: int,
        invocation_id: str,
        response_id: str | None,
        model_name: str | None,
        text_fragments: list[str],
        tool_call_chunks: dict[int, dict[str, Any]],
        usage_raw: dict[str, Any] | None,
        finish_reason: str | None,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> LlmStreamEvent:
        content_text = "".join(text_fragments) or None
        raw_tool_calls = [
            {
                "id": chunk.get("id") or f"chatcmpl-tool-{index}",
                "name": chunk.get("name"),
                "arguments": chunk.get("arguments"),
            }
            for index, chunk in sorted(tool_call_chunks.items())
            if chunk.get("name")
        ]
        if not raw_tool_calls and content_text:
            parsed_tool_calls = cls._parse_xmlish_tool_calls(content_text)
            if parsed_tool_calls:
                raw_tool_calls.extend(parsed_tool_calls)
                content_text = cls._strip_xmlish_tool_calls(content_text)
        usage = None
        if isinstance(usage_raw, dict):
            usage = LlmUsage(
                input_tokens=usage_raw.get("prompt_tokens"),
                output_tokens=usage_raw.get("completion_tokens"),
                total_tokens=usage_raw.get("total_tokens"),
            )
        response_items = _chat_response_items(
            invocation_id=invocation_id,
            content_text=content_text,
            raw_tool_calls=raw_tool_calls,
            provider_response_id=response_id,
            model_name=model_name or profile.model_name,
            transport="sse",
            tool_name_aliases=tool_name_aliases,
        )
        result = LlmResult.from_response_items(
            response_items,
            usage=usage,
            finish_reason=finish_reason,
            metadata={
                "provider": profile.provider.value,
                "response_id": response_id,
                "model": model_name or profile.model_name,
                "transport": "sse",
            },
            text_fallback=content_text,
        )
        return LlmStreamEvent(
            type="completed",
            sequence=sequence,
            data={
                "result": result.to_payload(),
                "response_items": [item.to_payload() for item in response_items],
                "provider_request_id": response_id,
            },
        )

    @classmethod
    def _parse_xmlish_tool_calls(cls, content: str) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for block_match in cls.TOOL_CALL_BLOCK_PATTERN.finditer(content):
            block_body = block_match.group(1)
            function_match = cls.FUNCTION_PATTERN.search(block_body)
            if function_match is None:
                continue
            function_name = function_match.group(1).strip()
            parameter_body = function_match.group(2)
            arguments: dict[str, Any] = {}
            for parameter_match in cls.PARAMETER_PATTERN.finditer(parameter_body):
                parameter_name = parameter_match.group(1).strip()
                parameter_value = parameter_match.group(2).strip()
                if parameter_name:
                    arguments[parameter_name] = parameter_value
            if not function_name:
                continue
            tool_calls.append(
                {
                    "id": f"chatcmpl-tool-{uuid4().hex}",
                    "name": function_name,
                    "arguments": arguments,
                },
            )
        return tool_calls

    @classmethod
    def _strip_xmlish_tool_calls(cls, content: str) -> str | None:
        stripped = cls.TOOL_CALL_BLOCK_PATTERN.sub("", content).strip()
        return stripped or None


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


def _chat_response_items(
    *,
    invocation_id: str,
    content_text: str | None,
    raw_tool_calls: list[dict[str, Any]],
    provider_response_id: str | None,
    model_name: str | None,
    transport: str,
    tool_name_aliases: dict[str, str] | None,
) -> tuple[LlmResponseItem, ...]:
    items: list[LlmResponseItem] = []
    now = utcnow()
    if content_text is not None:
        sequence_no = len(items) + 1
        provider_item_id = (
            f"{provider_response_id}:message"
            if provider_response_id is not None
            else f"{invocation_id}:message:{sequence_no}"
        )
        items.append(
            LlmResponseItem(
                id=f"{invocation_id}:item:{sequence_no}",
                invocation_id=invocation_id,
                sequence_no=sequence_no,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.FINAL_ANSWER,
                content_payload={"text": content_text},
                provider_payload={
                    "type": "chat.completion.message",
                    "response_id": provider_response_id,
                    "model": model_name,
                    "transport": transport,
                },
                provider_item_id=provider_item_id,
                provider_item_type="chat.completion.message",
                model_visible=True,
                user_visible=True,
                created_at=now,
                completed_at=now,
            ),
        )
    for tool_call in build_tool_call_intents(
        raw_tool_calls,
        tool_name_aliases=tool_name_aliases,
    ):
        sequence_no = len(items) + 1
        items.append(
            LlmResponseItem(
                id=f"{invocation_id}:item:{sequence_no}",
                invocation_id=invocation_id,
                sequence_no=sequence_no,
                kind=LlmResponseItemKind.TOOL_CALL,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.UNKNOWN,
                content_payload={
                    "call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                },
                provider_payload={
                    "type": "chat.completion.tool_call",
                    "response_id": provider_response_id,
                    "model": model_name,
                    "transport": transport,
                },
                provider_item_id=tool_call.id,
                provider_item_type="chat.completion.tool_call",
                call_id=tool_call.id,
                tool_name=tool_call.name,
                model_visible=True,
                user_visible=False,
                created_at=now,
                completed_at=now,
            ),
        )
    return tuple(items)
