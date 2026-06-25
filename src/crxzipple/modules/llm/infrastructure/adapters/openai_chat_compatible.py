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
from crxzipple.modules.llm.domain import LlmContinuationSignal
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    ensure_image_input_supported,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    ensure_json_response,
    resolve_credential_binding,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_projection import (
    alias_to_original_tool_names,
    build_openai_chat_adapter_response,
    openai_chat_response_items_from_completed_event,
    stream_openai_chat_sse_response,
    stream_openai_chat_sse_response_async,
)
from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible_renderer import (
    OpenAIChatCompatibleRequestRenderer,
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
        return build_openai_chat_adapter_response(
            profile,
            invocation_id=request.invocation_id,
            payload=data,
            tool_name_aliases=alias_to_original_tool_names(wire_request),
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
        continuation = LlmContinuationSignal.from_payload(
            completed_event.data.get("continuation")
            if isinstance(completed_event.data.get("continuation"), dict)
            else None,
        )
        response_items = openai_chat_response_items_from_completed_event(
            completed_event,
        )
        return LlmAdapterResponse(
            result=result,
            response_items=response_items,
            provider_request_id=(
                str(provider_request_id) if provider_request_id is not None else None
            ),
            continuation=continuation,
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
        alias_to_original = alias_to_original_tool_names(wire_request)

        response: requests.Response | None = None
        try:
            response = self._send_stream_wire_request(
                profile,
                request,
                wire_request,
                render_input=render_input,
            )
            yield from stream_openai_chat_sse_response(
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
        alias_to_original = alias_to_original_tool_names(wire_request)
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
            async for event in stream_openai_chat_sse_response_async(
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
