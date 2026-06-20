from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
import errno
import json
import threading
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import requests
import websocket

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmContinuationSignal,
    LlmResponseItem,
    LlmResult,
    LlmUsage,
)
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    default_base_url,
    ensure_image_input_supported,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    OPENAI_TRANSIENT_HTTP_STATUS_CODES,
    OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS,
    RetryableOpenAIStreamError,
    async_sleep_before_openai_stream_retry,
    httpx_response_text,
    is_retryable_openai_stream_exception,
    join_url,
    resolve_credential_binding,
    sleep_before_openai_stream_retry,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses_renderer import (
    OpenAICodexResponsesRenderer,
    requested_provider_transport_input,
    uses_provider_native_continuation_input,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_response_projection import (
    build_openai_continuation_signal,
    build_openai_response_items,
    openai_response_stream_event,
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
from crxzipple.shared.infrastructure.http import get_async_http_client


class OpenAICodexResponsesAdapter:
    DEFAULT_BASE_URL = "https://chatgpt.com/backend-api/codex"
    DEFAULT_INSTRUCTIONS = "You are a helpful coding assistant."

    def __init__(self) -> None:
        self._websocket_pool: dict[tuple[str, tuple[str, ...], int], list[Any]] = {}
        self._websocket_pool_lock = threading.Lock()
        self._renderer = OpenAICodexResponsesRenderer(
            default_base_url=self.DEFAULT_BASE_URL,
            default_instructions=self.DEFAULT_INSTRUCTIONS,
        )

    def close_websocket_pool(self) -> None:
        with self._websocket_pool_lock:
            sockets = [
                ws
                for bucket in self._websocket_pool.values()
                for ws in bucket
            ]
            self._websocket_pool.clear()
        for ws in sockets:
            _close_websocket(ws)

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
        endpoint = _websocket_endpoint(
            join_url(default_base_url(profile, self.DEFAULT_BASE_URL), "/responses"),
        )
        headers = _websocket_headers(token)
        ws, key, reused = self._acquire_websocket(
            endpoint,
            headers=headers,
            timeout_seconds=profile.timeout_seconds,
        )
        self._release_websocket(key, ws)
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
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        if requested_provider_transport_input(render_input) == "websocket":
            yield from self._stream_websocket_invoke(
                profile,
                request,
                render_input=render_input,
            )
            return
        _ensure_supported_transport_input(render_input)
        tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)
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
                    render_input=render_input,
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
        render_input = ProviderRenderInput.from_request(profile=profile, request=request)
        if requested_provider_transport_input(render_input) == "websocket":
            async for event in self._stream_websocket_invoke_async_bridge(
                profile,
                request,
            ):
                yield event
            return
        _ensure_supported_transport_input(render_input)
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
                wire_request = self._wire_request(
                    profile,
                    request,
                    render_input=render_input,
                    tool_name_aliases=tool_name_aliases,
                )
                client = get_async_http_client(
                    wire_request.endpoint,
                    timeout=profile.timeout_seconds,
                    client_factory=httpx.AsyncClient,
                )
                async with client.stream(
                    "POST",
                    wire_request.endpoint,
                    headers=self._request_headers(
                        profile,
                        request,
                        render_input=render_input,
                    ),
                    json=wire_request.payload,
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
        render_input: ProviderRenderInput | None = None,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> requests.Response:
        wire_request = self._wire_request(
            profile,
            request,
            render_input=render_input,
            tool_name_aliases=tool_name_aliases,
        )
        return self._send_stream_wire_request(
            profile,
            request,
            wire_request,
            render_input=render_input,
        )

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
        endpoint = _websocket_endpoint(
            join_url(default_base_url(profile, self.DEFAULT_BASE_URL), "/responses"),
        )
        description = f"OpenAI Codex Responses profile '{profile.id}'"
        headers = _websocket_headers(token)

        request_attempts = [request]
        if uses_provider_native_continuation_input(model_input):
            request_attempts.append(replace(request, continuation=None))

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
                    ws, pool_key, _ = self._acquire_websocket(
                        endpoint,
                        headers=headers,
                        timeout_seconds=profile.timeout_seconds,
                    )
                    ws.send(json.dumps(wire_request.payload))
                    for event in self._stream_websocket_response(
                        profile,
                        ws,
                        invocation_id=attempt_request.invocation_id,
                        description=description,
                        tool_name_aliases=alias_to_original,
                    ):
                        emitted_output = True
                        if attempt_index > 0:
                            event = _with_websocket_fallback_metadata(event)
                        yield event
                    keep_websocket = True
                    return
                except Exception as exc:
                    keep_websocket = False
                    retryable = _is_retryable_websocket_exception(exc)
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
                        break
                    raise
                finally:
                    if ws is not None:
                        if keep_websocket and pool_key is not None:
                            self._release_websocket(pool_key, ws)
                        else:
                            _close_websocket(ws)

    def _acquire_websocket(
        self,
        endpoint: str,
        *,
        headers: list[str],
        timeout_seconds: int,
    ) -> tuple[Any, tuple[str, tuple[str, ...], int], bool]:
        key = (endpoint, tuple(headers), timeout_seconds)
        with self._websocket_pool_lock:
            bucket = self._websocket_pool.get(key)
            while bucket:
                ws = bucket.pop()
                if not _websocket_is_closed(ws):
                    return ws, key, True
        return (
            websocket.create_connection(
                endpoint,
                header=headers,
                timeout=timeout_seconds,
            ),
            key,
            False,
        )

    def _release_websocket(
        self,
        key: tuple[str, tuple[str, ...], int],
        ws: Any,
    ) -> None:
        if _websocket_is_closed(ws):
            return
        with self._websocket_pool_lock:
            self._websocket_pool.setdefault(key, []).append(ws)

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

    def _request_headers(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> dict[str, str]:
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
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
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    def _send_stream_wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        wire_request: ProviderWireRequest,
        *,
        render_input: ProviderRenderInput | None = None,
    ) -> requests.Response:
        return requests.post(
            wire_request.endpoint,
            headers=self._request_headers(
                profile,
                request,
                render_input=render_input,
            ),
            json=wire_request.payload,
            timeout=profile.timeout_seconds,
            stream=True,
        )

    def _wire_request(
        self,
        profile: LlmProfile,
        request: LlmAdapterRequest,
        *,
        render_input: ProviderRenderInput | None = None,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> ProviderWireRequest:
        del tool_name_aliases
        model_input = render_input or ProviderRenderInput.from_request(
            profile=profile,
            request=request,
        )
        rendered = self._renderer.render_http_input(model_input)
        return ProviderWireRequest.from_rendered(
            renderer_id=self._renderer.renderer_id,
            rendered=rendered,
            preview=self._renderer.preview_input(model_input),
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
    def _stream_websocket_response(
        cls,
        profile: LlmProfile,
        ws: Any,
        *,
        invocation_id: str,
        description: str,
        tool_name_aliases: dict[str, str] | None = None,
    ) -> Iterator[LlmStreamEvent]:
        completed_output_items: dict[int, dict[str, Any]] = {}
        sequence = 1
        while True:
            raw_message = ws.recv()
            if raw_message is None:
                break
            if isinstance(raw_message, bytes):
                message = raw_message.decode("utf-8", errors="replace")
            else:
                message = str(raw_message)
            if not message.strip():
                continue
            event, event_completed = cls._consume_sse_event(
                profile,
                None,
                [message],
                sequence=sequence,
                description=description,
                invocation_id=invocation_id,
                tool_name_aliases=tool_name_aliases,
                completed_output_items=completed_output_items,
                transport="websocket",
            )
            if event is not None:
                yield event
                sequence += 1
            if event_completed:
                return
        raise RuntimeError(f"{description} returned an incomplete WebSocket response.")

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
        transport: str = "sse",
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
                    transport=transport,
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
        transport: str = "sse",
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
                    "transport": transport,
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


def _with_websocket_fallback_metadata(event: LlmStreamEvent) -> LlmStreamEvent:
    if event.type != "completed":
        return event
    result = event.data.get("result")
    if not isinstance(result, dict):
        return event
    next_result = dict(result)
    metadata = dict(next_result.get("metadata") or {})
    metadata["provider_continuation_fallback"] = True
    metadata["provider_continuation_fallback_reason"] = (
        "websocket_continuation_failed_before_output"
    )
    next_result["metadata"] = metadata
    next_data = dict(event.data)
    next_data["result"] = next_result
    return LlmStreamEvent(
        type=event.type,
        sequence=event.sequence,
        invocation_id=event.invocation_id,
        data=next_data,
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


def _is_retryable_websocket_exception(exc: BaseException) -> bool:
    if is_retryable_openai_stream_exception(exc):
        return True
    if isinstance(
        exc,
        (
            BrokenPipeError,
            ConnectionAbortedError,
            ConnectionResetError,
            TimeoutError,
        ),
    ):
        return True
    if isinstance(exc, OSError):
        return exc.errno in {
            errno.EPIPE,
            errno.ECONNABORTED,
            errno.ECONNRESET,
            errno.ETIMEDOUT,
        }
    websocket_exception = getattr(websocket, "WebSocketException", None)
    return isinstance(websocket_exception, type) and isinstance(exc, websocket_exception)


def _websocket_is_closed(ws: Any) -> bool:
    closed = getattr(ws, "closed", None)
    if isinstance(closed, bool):
        return closed
    connected = getattr(ws, "connected", None)
    if isinstance(connected, bool):
        return not connected
    sock = getattr(ws, "sock", None)
    if sock is not None:
        sock_connected = getattr(sock, "connected", None)
        if isinstance(sock_connected, bool):
            return not sock_connected
    return False


def _close_websocket(ws: Any) -> None:
    close = getattr(ws, "close", None)
    if callable(close):
        close()


def _websocket_endpoint(http_endpoint: str) -> str:
    parsed = urlsplit(http_endpoint)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _websocket_headers(token: str | None) -> list[str]:
    headers = [
        "OpenAI-Beta: responses_websockets=2026-02-06",
        "Content-Type: application/json",
    ]
    if token is not None:
        headers.append(f"Authorization: Bearer {token}")
    return headers
