from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import requests

from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    OPENAI_TRANSIENT_HTTP_STATUS_CODES,
    RetryableOpenAIStreamError,
    httpx_response_text,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses_event_projection import (
    consume_openai_responses_event,
)


def stream_openai_responses_sse_response(
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
        event, event_completed = consume_openai_responses_event(
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
        event, event_completed = consume_openai_responses_event(
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


async def stream_openai_responses_sse_response_async(
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
        event, event_completed = consume_openai_responses_event(
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
        event, event_completed = consume_openai_responses_event(
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

