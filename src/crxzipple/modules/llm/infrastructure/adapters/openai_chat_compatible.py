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
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmUsage,
    utcnow,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_renderer import (
    OpenAIChatCompatibleRequestRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    ensure_image_input_supported,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    ensure_json_response,
    httpx_response_text,
    resolve_credential_binding,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_response_projection import (
    build_tool_call_intents,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
    ProviderWireRequest,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
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

    def __init__(self) -> None:
        self._renderer = OpenAIChatCompatibleRequestRenderer(
            default_base_url=self.DEFAULT_BASE_URL,
        )

    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        wire_request = self._wire_request(
            profile,
            request,
            render_input=render_input,
        )
        response = self._send_wire_request(
            profile,
            request,
            wire_request,
            render_input=render_input,
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
            tool_name_aliases=_alias_to_original_tool_names(wire_request),
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

    def preview_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, Any]:
        return self._renderer.preview_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
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
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        wire_request = self._wire_request(
            profile,
            request,
            stream=True,
            render_input=render_input,
        )
        alias_to_original = _alias_to_original_tool_names(wire_request)

        response: requests.Response | None = None
        try:
            response = self._send_stream_wire_request(
                profile,
                request,
                wire_request,
                render_input=render_input,
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
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        wire_request = self._wire_request(
            profile,
            request,
            stream=True,
            render_input=render_input,
        )
        alias_to_original = _alias_to_original_tool_names(wire_request)
        ensure_image_input_supported(
            profile,
            messages_from_projected_input_items(render_input.input_items),
        )
        client = get_async_http_client(
            wire_request.endpoint,
            timeout=profile.timeout_seconds,
            client_factory=httpx.AsyncClient,
        )
        async with client.stream(
            "POST",
            wire_request.endpoint,
            headers=self._request_headers(profile, request, stream=True),
            json=wire_request.payload,
        ) as response:
            async for event in self._stream_sse_response_async(
                profile,
                response,
                description=f"OpenAI-compatible profile '{profile.id}'",
                invocation_id=request.invocation_id,
                tool_name_aliases=alias_to_original,
            ):
                yield event

    def _request_headers(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        stream: bool = False,
    ) -> dict[str, str]:
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=profile.provider.value == "openai_compatible",
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        headers = {
            "Content-Type": "application/json",
        }
        if stream:
            headers["Accept"] = "text/event-stream"
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _send_wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        wire_request: ProviderWireRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> requests.Response:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        ensure_image_input_supported(
            profile,
            messages_from_projected_input_items(model_input.input_items),
        )
        return requests.post(
            wire_request.endpoint,
            headers=self._request_headers(profile, request),
            json=wire_request.payload,
            timeout=profile.timeout_seconds,
        )

    def _send_stream_wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        wire_request: ProviderWireRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> requests.Response:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        ensure_image_input_supported(
            profile,
            messages_from_projected_input_items(model_input.input_items),
        )
        return requests.post(
            wire_request.endpoint,
            headers=self._request_headers(profile, request, stream=True),
            json=wire_request.payload,
            timeout=profile.timeout_seconds,
            stream=True,
        )

    def _wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        stream: bool = False,
        render_input: ProviderRenderInput | None = None,
    ) -> ProviderWireRequest:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        rendered = self._renderer.render_input(model_input, stream=stream)
        return ProviderWireRequest.from_rendered(
            renderer_id=self._renderer.renderer_id,
            rendered=rendered,
            preview=self._renderer.preview_input(model_input, stream=stream),
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
                provider_replay_candidate=True,
                user_timeline_candidate=True,
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
                provider_replay_candidate=True,
                user_timeline_candidate=False,
                created_at=now,
                completed_at=now,
            ),
        )
    return tuple(items)


def _alias_to_original_tool_names(
    wire_request: ProviderWireRequest,
) -> dict[str, str]:
    return {
        alias: original
        for original, alias in wire_request.tool_name_aliases.items()
    }
