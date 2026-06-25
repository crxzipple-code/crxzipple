from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import json
from typing import Any

import httpx
import requests

from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    httpx_response_text,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_events import (
    alias_to_original_tool_names,
    build_json_completed_event,
    build_openai_chat_adapter_response,
    build_stream_completed_event,
    merge_stream_tool_calls,
    openai_chat_response_items_from_completed_event,
)

__all__ = [
    "alias_to_original_tool_names",
    "build_openai_chat_adapter_response",
    "openai_chat_response_items_from_completed_event",
    "stream_openai_chat_sse_response",
    "stream_openai_chat_sse_response_async",
]


def stream_openai_chat_sse_response(
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
        yield build_json_completed_event(
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
            yield build_stream_completed_event(
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
                merge_stream_tool_calls(tool_call_chunks, tool_calls)
        if choice.get("finish_reason") is not None:
            finish_reason = str(choice.get("finish_reason"))
            yield build_stream_completed_event(
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
        yield build_stream_completed_event(
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


async def stream_openai_chat_sse_response_async(
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
        yield build_json_completed_event(
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
            yield build_stream_completed_event(
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
                merge_stream_tool_calls(tool_call_chunks, tool_calls)
        if choice.get("finish_reason") is not None:
            finish_reason = str(choice.get("finish_reason"))
            yield build_stream_completed_event(
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
        yield build_stream_completed_event(
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
