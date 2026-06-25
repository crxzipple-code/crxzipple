from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.infrastructure.adapters.provider_protocol import (
    ProviderRenderInput,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview import (
    openai_response_input_fingerprints,
)


def requested_provider_transport_input(render_input: ProviderRenderInput) -> str:
    return (render_input.provider_transport or "auto").strip().lower() or "auto"


def uses_provider_native_continuation_input(
    render_input: ProviderRenderInput,
) -> bool:
    continuation = render_input.continuation
    return (
        continuation is not None
        and continuation.mode == "provider_native"
        and continuation.previous_response_id is not None
        and requested_provider_transport_input(render_input) == "websocket"
    )


def websocket_continuation_delta_items_input(
    render_input: ProviderRenderInput,
    full_items: list[dict[str, Any]],
    *,
    instructions_fingerprint: str,
    tool_fingerprints: tuple[str, ...],
) -> list[dict[str, Any]] | None:
    if not uses_provider_native_continuation_input(render_input):
        return None
    continuation = render_input.continuation
    if continuation is None:
        return None
    previous_fingerprints = continuation.input_item_fingerprints
    if not previous_fingerprints:
        return None
    if continuation.instructions_fingerprint != instructions_fingerprint:
        return None
    if not _continuation_tool_surface_is_compatible(
        previous_tool_fingerprints=continuation.tool_fingerprints,
        current_tool_fingerprints=tool_fingerprints,
    ):
        return None
    current_fingerprints = openai_response_input_fingerprints(full_items)
    prefix_size = len(previous_fingerprints)
    if current_fingerprints[:prefix_size] != previous_fingerprints:
        return None
    return full_items[prefix_size:]


def websocket_response_create_payload_input(
    payload: dict[str, Any],
    render_input: ProviderRenderInput,
) -> dict[str, Any]:
    ws_payload = dict(payload)
    ws_payload["type"] = "response.create"
    ws_payload.pop("provider_transport", None)
    input_delta_mode = bool(ws_payload.pop("_crxzipple_input_delta_mode", False))
    continuation = render_input.continuation
    previous_response_id = (
        continuation.previous_response_id
        if continuation is not None
        and requested_provider_transport_input(render_input) == "websocket"
        and input_delta_mode
        else None
    )
    if previous_response_id is not None:
        ws_payload["previous_response_id"] = previous_response_id
    return ws_payload


def _continuation_tool_surface_is_compatible(
    *,
    previous_tool_fingerprints: tuple[str, ...],
    current_tool_fingerprints: tuple[str, ...],
) -> bool:
    if previous_tool_fingerprints == current_tool_fingerprints:
        return True
    if not previous_tool_fingerprints:
        return True
    current = set(current_tool_fingerprints)
    return all(fingerprint in current for fingerprint in previous_tool_fingerprints)
