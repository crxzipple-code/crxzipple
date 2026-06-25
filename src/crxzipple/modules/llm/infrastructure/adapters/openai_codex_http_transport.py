from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import requests

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.infrastructure.adapters.adapter_utils import (
    ensure_image_input_supported,
)
from crxzipple.modules.llm.infrastructure.adapters.http_helpers import (
    resolve_credential_binding,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
    ProviderWireRequest,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    messages_from_projected_input_items,
)
from crxzipple.shared.infrastructure.http import get_async_http_client


def codex_http_request_headers(
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


def post_codex_sse_wire_request(
    profile: LlmProfile,
    request: LlmAdapterRequest,
    wire_request: ProviderWireRequest,
    *,
    render_input: ProviderRenderInput | None = None,
) -> requests.Response:
    return requests.post(
        wire_request.endpoint,
        headers=codex_http_request_headers(
            profile,
            request,
            render_input=render_input,
        ),
        json=wire_request.payload,
        timeout=profile.timeout_seconds,
        stream=True,
    )


@asynccontextmanager
async def open_codex_async_sse_wire_request(
    profile: LlmProfile,
    request: LlmAdapterRequest,
    wire_request: ProviderWireRequest,
    *,
    render_input: ProviderRenderInput | None = None,
) -> AsyncIterator[httpx.Response]:
    client = get_async_http_client(
        wire_request.endpoint,
        timeout=profile.timeout_seconds,
        client_factory=httpx.AsyncClient,
    )
    async with client.stream(
        "POST",
        wire_request.endpoint,
        headers=codex_http_request_headers(
            profile,
            request,
            render_input=render_input,
        ),
        json=wire_request.payload,
    ) as response:
        yield response
