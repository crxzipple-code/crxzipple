from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS,
    async_sleep_before_openai_stream_retry,
    is_retryable_openai_stream_exception,
    sleep_before_openai_stream_retry,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_transport import (
    open_codex_async_sse_wire_request,
    post_codex_sse_wire_request,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses_renderer import (
    OpenAICodexResponsesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_streaming import (
    stream_codex_sse_response,
    stream_codex_sse_response_async,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
    ProviderWireRequest,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    build_openai_tool_name_aliases,
)


def stream_codex_http_invoke(
    profile: LlmProfile,
    request: LlmAdapterRequest,
    *,
    render_input: ProviderRenderInput,
    renderer: OpenAICodexResponsesRenderer,
) -> Iterator[LlmStreamEvent]:
    tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)
    alias_to_original = {
        alias: original
        for original, alias in tool_name_aliases.items()
    }
    description = f"OpenAI Codex Responses profile '{profile.id}'"
    attempt = 1
    while True:
        response: Any | None = None
        emitted_output = False
        try:
            wire_request = codex_http_wire_request(
                renderer,
                profile,
                request,
                render_input=render_input,
            )
            response = post_codex_sse_wire_request(
                profile,
                request,
                wire_request,
                render_input=render_input,
            )
            for event in stream_codex_sse_response(
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


async def stream_codex_http_invoke_async(
    profile: LlmProfile,
    request: LlmAdapterRequest,
    *,
    render_input: ProviderRenderInput,
    renderer: OpenAICodexResponsesRenderer,
) -> AsyncIterator[LlmStreamEvent]:
    tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)
    alias_to_original = {
        alias: original
        for original, alias in tool_name_aliases.items()
    }
    description = f"OpenAI Codex Responses profile '{profile.id}'"
    attempt = 1
    while True:
        emitted_output = False
        try:
            wire_request = codex_http_wire_request(
                renderer,
                profile,
                request,
                render_input=render_input,
            )
            async with open_codex_async_sse_wire_request(
                profile,
                request,
                wire_request,
                render_input=render_input,
            ) as response:
                async for event in stream_codex_sse_response_async(
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


def codex_http_wire_request(
    renderer: OpenAICodexResponsesRenderer,
    profile: LlmProfile,
    request: LlmAdapterRequest,
    *,
    render_input: ProviderRenderInput | None = None,
) -> ProviderWireRequest:
    model_input = render_input or ProviderRenderInput.from_request(
        profile=profile,
        request=request,
    )
    rendered = renderer.render_http_input(model_input)
    return ProviderWireRequest.from_rendered(
        renderer_id=renderer.renderer_id,
        rendered=rendered,
        preview=renderer.preview_input(model_input),
    )
