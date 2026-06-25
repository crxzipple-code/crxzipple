from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
import json
import threading
from typing import Any

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    default_base_url,
    ensure_image_input_supported,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS,
    join_url,
    resolve_credential_binding,
    sleep_before_openai_stream_retry,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_completion import (
    codex_adapter_response_from_completed_event,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_http_dispatch import (
    codex_http_wire_request,
    stream_codex_http_invoke,
    stream_codex_http_invoke_async,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_event_projection import (
    with_codex_websocket_fallback_metadata,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_streaming import (
    stream_codex_websocket_response,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses_renderer import (
    OpenAICodexResponsesRenderer,
    requested_provider_transport_input,
    uses_provider_native_continuation_input,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_websocket_transport import (
    CodexWebsocketPool,
    close_codex_websocket,
    codex_websocket_endpoint,
    codex_websocket_headers,
    is_retryable_codex_websocket_exception,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
    ProviderWireRequest,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    build_openai_tool_name_aliases,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
)


class OpenAICodexResponsesAdapter:
    DEFAULT_BASE_URL = "https://chatgpt.com/backend-api/codex"
    DEFAULT_INSTRUCTIONS = "You are a helpful coding assistant."

    def __init__(self) -> None:
        self._websocket_pool = CodexWebsocketPool()
        self._renderer = OpenAICodexResponsesRenderer(
            default_base_url=self.DEFAULT_BASE_URL,
            default_instructions=self.DEFAULT_INSTRUCTIONS,
        )

    def close_websocket_pool(self) -> None:
        self._websocket_pool.close_all()

    def warmup_websocket(
        self,
        profile: LlmProfile,
        *,
        resolved_credential: str | None = None,
    ) -> dict[str, Any]:
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=True,
            description=f"LLM profile '{profile.id}'",
            resolved_credential=resolved_credential,
        )
        endpoint = codex_websocket_endpoint(
            join_url(default_base_url(profile, self.DEFAULT_BASE_URL), "/responses"),
        )
        headers = codex_websocket_headers(token)
        ws, key, reused = self._websocket_pool.acquire(
            endpoint,
            headers=headers,
            timeout_seconds=profile.timeout_seconds,
        )
        self._websocket_pool.release(key, ws)
        return {
            "transport": "websocket",
            "endpoint": endpoint,
            "reused_connection": reused,
        }

    def preview_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> dict[str, Any]:
        return self._renderer.preview_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
        )

    def invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> LlmAdapterResponse:
        completed_event: LlmStreamEvent | None = None
        for event in self.stream_invoke(profile, request):
            if event.type == "completed":
                completed_event = event
        return codex_adapter_response_from_completed_event(
            completed_event,
            description=f"OpenAI Codex Responses profile '{profile.id}'",
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
        return codex_adapter_response_from_completed_event(
            completed_event,
            description=f"OpenAI Codex Responses profile '{profile.id}'",
        )

    def stream_invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> Iterator[LlmStreamEvent]:
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        if requested_provider_transport_input(render_input) == "websocket":
            yield from self._stream_websocket_invoke(
                profile,
                request,
                render_input=render_input,
            )
            return
        _ensure_supported_transport_input(render_input)
        yield from stream_codex_http_invoke(
            profile,
            request,
            render_input=render_input,
            renderer=self._renderer,
        )

    async def stream_invoke_async(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> AsyncIterator[LlmStreamEvent]:
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        if requested_provider_transport_input(render_input) == "websocket":
            async for event in self._stream_websocket_invoke_async_bridge(
                profile,
                request,
            ):
                yield event
            return
        _ensure_supported_transport_input(render_input)
        async for event in stream_codex_http_invoke_async(
            profile,
            request,
            render_input=render_input,
            renderer=self._renderer,
        ):
            yield event

    def _stream_websocket_invoke(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> Iterator[LlmStreamEvent]:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        tool_name_aliases = build_openai_tool_name_aliases(model_input.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        ensure_image_input_supported(
            profile,
            messages_from_projected_input_items(model_input.input_items),
        )
        token = resolve_credential_binding(
            profile.credential_binding_id,
            required=True,
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        endpoint = codex_websocket_endpoint(
            join_url(default_base_url(profile, self.DEFAULT_BASE_URL), "/responses"),
        )
        description = f"OpenAI Codex Responses profile '{profile.id}'"
        headers = codex_websocket_headers(token)

        request_attempts = [request]
        if uses_provider_native_continuation_input(model_input):
            request_attempts.append(replace(request, continuation=None))

        fallback_error: dict[str, Any] | None = None
        for attempt_index, attempt_request in enumerate(request_attempts):
            transient_attempt = 1
            while True:
                ws: Any | None = None
                pool_key: tuple[str, tuple[str, ...], int] | None = None
                keep_websocket = False
                emitted_output = False
                try:
                    wire_request = self._websocket_wire_request(
                        profile,
                        attempt_request,
                        endpoint=endpoint,
                        render_input=(
                            model_input
                            if attempt_request is request
                            else ProviderRenderInput.from_request(
                                profile=profile,
                                request=attempt_request,
                            )
                        ),
                    )
                    ws, pool_key, _ = self._websocket_pool.acquire(
                        endpoint,
                        headers=headers,
                        timeout_seconds=profile.timeout_seconds,
                    )
                    ws.send(json.dumps(wire_request.payload))
                    for event in stream_codex_websocket_response(
                        profile,
                        ws,
                        invocation_id=attempt_request.invocation_id,
                        description=description,
                        tool_name_aliases=alias_to_original,
                    ):
                        emitted_output = True
                        if attempt_index > 0:
                            event = with_codex_websocket_fallback_metadata(
                                event,
                                fallback_error=fallback_error,
                            )
                        yield event
                    keep_websocket = True
                    return
                except Exception as exc:
                    keep_websocket = False
                    retryable = is_retryable_codex_websocket_exception(exc)
                    if (
                        not emitted_output
                        and retryable
                        and transient_attempt < OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS
                    ):
                        sleep_before_openai_stream_retry(transient_attempt)
                        transient_attempt += 1
                        continue
                    has_fallback = attempt_index + 1 < len(request_attempts)
                    if has_fallback and not emitted_output and not retryable:
                        fallback_error = _codex_websocket_fallback_error(exc)
                        break
                    raise
                finally:
                    if ws is not None:
                        if keep_websocket and pool_key is not None:
                            self._websocket_pool.release(pool_key, ws)
                        else:
                            close_codex_websocket(ws)

    async def _stream_websocket_invoke_async_bridge(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
    ) -> AsyncIterator[LlmStreamEvent]:
        queue: asyncio.Queue[object] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        done = object()

        def _worker() -> None:
            try:
                for event in self._stream_websocket_invoke(profile, request):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, done)

        thread = threading.Thread(
            target=_worker,
            name=f"llm-codex-ws-{profile.id}",
            daemon=True,
        )
        thread.start()
        while True:
            item = await queue.get()
            if item is done:
                return
            if isinstance(item, Exception):
                raise item
            if isinstance(item, LlmStreamEvent):
                yield item

    def _wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        render_input: ProviderRenderInput | None = None,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> ProviderWireRequest:
        del tool_name_aliases
        return codex_http_wire_request(
            self._renderer,
            profile,
            request,
            render_input=render_input,
        )

    def _websocket_wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        endpoint: str,
        render_input: ProviderRenderInput | None = None,
    ) -> ProviderWireRequest:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        rendered = self._renderer.render_websocket_create_input(
            model_input,
            endpoint=endpoint,
        )
        return ProviderWireRequest.from_rendered(
            renderer_id=self._renderer.renderer_id,
            rendered=rendered,
            preview=self._renderer.preview_input(model_input),
        )

    def _build_payload(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._renderer.build_payload_input(
            ProviderRenderInput.from_request(profile=profile, request=request),
            tool_name_aliases=tool_name_aliases,
        )


def _ensure_supported_transport_input(render_input: ProviderRenderInput) -> None:
    _ensure_supported_transport_value(requested_provider_transport_input(render_input))


def _ensure_supported_transport_value(transport: str) -> None:
    if transport == "websocket":
        return
    if transport not in {"auto", "http"}:
        raise ValueError(
            f"Unsupported OpenAI Codex Responses provider_transport: {transport}",
        )


def _codex_websocket_fallback_error(exc: Exception) -> dict[str, Any]:
    message = str(exc).strip().replace("\n", " ")
    if len(message) > 500:
        message = f"{message[:497]}..."
    return {
        "type": type(exc).__name__,
        "message": message,
    }
