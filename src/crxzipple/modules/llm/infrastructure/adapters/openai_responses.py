from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import requests

from crxzipple.modules.llm.application.adapters import (
    LlmAdapterRequest,
    LlmAdapterResponse,
)
from crxzipple.modules.llm.application.streaming import LlmStreamEvent
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import LlmResult
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    ensure_image_input_supported,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    OPENAI_TRANSIENT_STREAM_MAX_ATTEMPTS,
    async_sleep_before_openai_stream_retry,
    is_retryable_openai_stream_exception,
    resolve_credential_binding,
    sleep_before_openai_stream_retry,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses_renderer import (
    OpenAIResponsesRenderer,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses_event_projection import (
    openai_responses_continuation_from_completed_event,
    openai_responses_response_items_from_completed_event,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_responses_streaming import (
    stream_openai_responses_sse_response,
    stream_openai_responses_sse_response_async,
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


class OpenAIResponsesAdapter:
    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self) -> None:
        self._renderer = OpenAIResponsesRenderer(
            default_base_url=self.DEFAULT_BASE_URL,
        )

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
                f"OpenAI Responses profile '{profile.id}' did not complete.",
            )
        result_payload = completed_event.data.get("result")
        if not isinstance(result_payload, dict):
            raise RuntimeError(
                f"OpenAI Responses profile '{profile.id}' completed without a result payload.",
            )
        result = LlmResult.from_payload(result_payload)
        if result is None:
            raise RuntimeError(
                f"OpenAI Responses profile '{profile.id}' completed with an invalid result payload.",
            )
        provider_request_id = completed_event.data.get("provider_request_id")
        response_items = openai_responses_response_items_from_completed_event(
            completed_event,
        )
        return LlmAdapterResponse(
            result=result,
            response_items=response_items,
            continuation=openai_responses_continuation_from_completed_event(
                completed_event,
            ),
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
                f"OpenAI Responses profile '{profile.id}' did not complete.",
            )
        result_payload = completed_event.data.get("result")
        if not isinstance(result_payload, dict):
            raise RuntimeError(
                f"OpenAI Responses profile '{profile.id}' completed without a result payload.",
            )
        result = LlmResult.from_payload(result_payload)
        if result is None:
            raise RuntimeError(
                f"OpenAI Responses profile '{profile.id}' completed with an invalid result payload.",
            )
        provider_request_id = completed_event.data.get("provider_request_id")
        response_items = openai_responses_response_items_from_completed_event(
            completed_event,
        )
        return LlmAdapterResponse(
            result=result,
            response_items=response_items,
            continuation=openai_responses_continuation_from_completed_event(
                completed_event,
            ),
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
        tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        description = f"OpenAI Responses profile '{profile.id}'"
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
                for event in stream_openai_responses_sse_response(
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
        tool_name_aliases = build_openai_tool_name_aliases(render_input.tool_schemas)
        alias_to_original = {
            alias: original
            for original, alias in tool_name_aliases.items()
        }
        description = f"OpenAI Responses profile '{profile.id}'"
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
                    async for event in stream_openai_responses_sse_response_async(
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
            required=profile.provider.value == "openai",
            description=f"LLM profile '{profile.id}'",
            resolved_credential=request.resolved_credential,
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return headers

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
        rendered = self._renderer.render_input(model_input)
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
