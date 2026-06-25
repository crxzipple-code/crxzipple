from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.llm.application.runtime_request_preview import (
    request_render_snapshot_preview_payload,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation
from crxzipple.modules.llm.domain import LlmMessage


def runtime_request_summary(invocation: LlmInvocation) -> dict[str, Any]:
    metadata = dict(invocation.request_metadata)
    summary: dict[str, Any] = {
        "message_count": len(invocation.messages),
        "input_item_count": len(invocation.input_items),
        "input_item_kinds": [item.kind.value for item in invocation.input_items],
        "provider_context_message_count": len(invocation.provider_context_messages),
        "provider_context_message_kinds": provider_context_message_kinds(
            invocation.provider_context_messages,
        ),
        "tool_schema_count": len(invocation.tool_schemas),
        "response_format_configured": invocation.response_format is not None,
    }
    for key in (
        "request_render_snapshot_id",
        "input_mode",
        "runtime_contract_version",
        "runtime_contract_hash",
        "direct_session_item_count",
        "tool_surface_id",
        "tool_surface_snapshot_id",
        "tool_surface_function_count",
        "tool_surface_mirrored_schema_count",
    ):
        value = metadata.get(key)
        if value not in (None, "", {}, []):
            summary[key] = value
    request_render_snapshot = metadata.get("request_render_snapshot")
    if isinstance(request_render_snapshot, Mapping):
        preview_request_render_snapshot = request_render_snapshot_preview_payload(
            request_render_snapshot,
        )
        if preview_request_render_snapshot:
            summary["request_render_snapshot"] = preview_request_render_snapshot
    tool_surface = metadata.get("tool_surface")
    if isinstance(tool_surface, Mapping):
        tool_summary = tool_surface_summary(tool_surface)
        if tool_summary:
            summary["tool_surface"] = tool_summary
    return {
        key: value
        for key, value in summary.items()
        if value not in (None, "", {}, [])
    }


def tool_surface_summary(tool_surface: Mapping[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    surface_id = optional_preview_text(tool_surface.get("id"))
    if surface_id is not None:
        summary["id"] = surface_id
    functions = tool_surface.get("functions")
    if isinstance(functions, list | tuple):
        summary["function_count"] = len(functions)
    mirrored_schema_names = tool_surface.get("mirrored_schema_names")
    if isinstance(mirrored_schema_names, list | tuple):
        summary["mirrored_schema_count"] = len(mirrored_schema_names)
    blocked_access_count = tool_surface.get("blocked_access_count")
    if isinstance(blocked_access_count, int):
        summary["blocked_access_count"] = blocked_access_count
    return summary


def provider_context_message_kinds(
    messages: tuple[LlmMessage, ...],
) -> list[str]:
    kinds: list[str] = []
    for message in messages:
        kind = str(message.metadata.get("provider_context_kind", "")).strip()
        if kind and kind not in kinds:
            kinds.append(kind)
    return kinds


def optional_preview_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "provider_context_message_kinds",
    "runtime_request_summary",
    "tool_surface_summary",
]
