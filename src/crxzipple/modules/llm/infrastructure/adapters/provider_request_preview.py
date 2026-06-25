from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.application.provider_request_input_preview import (
    provider_input_preview_from_request_metadata,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_request_preview_utils import (
    openai_provider_payload_fingerprint,
    openai_response_input_fingerprints,
    payload_fingerprint_or_none,
    payload_item_type,
    safe_preview_value,
)
from crxzipple.modules.llm.infrastructure.adapters.provider_request_tool_preview import (
    provider_tool_protocol_render_report,
    provider_tool_render_report,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    provider_safe_input_metadata,
)


def openai_provider_request_preview(
    *,
    profile: LlmProfile,
    endpoint: str,
    payload: dict[str, Any],
    renderer_id: str = "openai_responses",
    transport: str = "http",
    render_strategy: str = "full_wire_payload",
    message_type: str | None = None,
    input_delta_mode: bool | None = None,
    input_baseline_count: int | None = None,
    input_baseline_fingerprints: tuple[str, ...] | None = None,
    request_metadata: dict[str, Any] | None = None,
    runtime_context: dict[str, Any] | None = None,
    runtime_route: dict[str, Any] | None = None,
    runtime_policy: dict[str, Any] | None = None,
    canonical_input_items: tuple[LlmInputItem, ...] = (),
) -> dict[str, object]:
    input_items = payload.get("input") if isinstance(payload.get("input"), list) else []
    tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    has_previous_response_id = bool(payload.get("previous_response_id"))
    delta_mode = has_previous_response_id if input_delta_mode is None else input_delta_mode
    input_fingerprints = openai_response_input_fingerprints(input_items)
    effective_render_strategy = (
        "provider_native_delta" if delta_mode else render_strategy
    )
    tool_render_report = provider_tool_render_report(
        payload=payload,
        request_metadata=request_metadata,
    )
    tool_protocol_report = provider_tool_protocol_render_report(
        request_metadata=request_metadata,
    )
    render_report = {
        "renderer_id": renderer_id,
        "transport": transport,
        "render_strategy": effective_render_strategy,
        "loss_report": {},
        "tool_surface": tool_render_report,
        "tool_protocol": tool_protocol_report,
    }
    input_item_mapping = provider_input_item_mapping(canonical_input_items)
    if input_item_mapping:
        render_report["input_item_mapping"] = input_item_mapping
        render_report["input_item_mapping_coverage"] = provider_input_item_mapping_coverage(
            input_item_mapping,
            provider_input_item_count=len(input_items),
        )
    return {
        "preview_source": "provider_adapter",
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model": payload.get("model") or profile.model_name,
        "endpoint": endpoint,
        "transport": transport,
        "renderer_id": renderer_id,
        "render_strategy": effective_render_strategy,
        "render_report": render_report,
        "message_type": message_type or payload.get("type"),
        "payload_keys": sorted(str(key) for key in payload),
        "input_item_count": len(input_items),
        "input_item_types": tuple(
            payload_item_type(item) for item in input_items[:40]
        ),
        "input_delta_mode": bool(delta_mode),
        "input_baseline_count": input_baseline_count,
        "input_item_fingerprints": input_fingerprints,
        "input_baseline_fingerprints": (
            input_baseline_fingerprints
            if input_baseline_fingerprints is not None
            else input_fingerprints
        ),
        "input_delta_count": len(input_items) if delta_mode else 0,
        "instructions_fingerprint": payload_fingerprint_or_none(
            payload.get("instructions"),
        ),
        "tool_count": len(tools),
        "tool_fingerprints": tuple(
            openai_provider_payload_fingerprint(tool) for tool in tools
        ),
        "tool_types": tuple(payload_item_type(item) for item in tools[:80]),
        "has_previous_response_id": has_previous_response_id,
        "previous_response_id": (
            str(payload.get("previous_response_id"))
            if payload.get("previous_response_id") is not None
            else None
        ),
        "option_summary": {
            "tool_choice": payload.get("tool_choice"),
            "parallel_tool_calls": payload.get("parallel_tool_calls"),
            "service_tier": payload.get("service_tier"),
            "prompt_cache_key": payload.get("prompt_cache_key"),
            "stream": payload.get("stream"),
            "store": payload.get("store"),
            "reasoning": safe_preview_value(payload.get("reasoning")),
            "text": safe_preview_value(payload.get("text")),
            "include": safe_preview_value(payload.get("include")),
        },
        **provider_runtime_preview(
            runtime_route=runtime_route,
            runtime_policy=runtime_policy,
        ),
        "payload_preview": safe_preview_value(payload),
        **provider_input_preview(
            runtime_context=runtime_context,
            request_metadata=request_metadata,
        ),
    }


def provider_wire_request_preview(
    *,
    profile: LlmProfile,
    endpoint: str,
    payload: dict[str, Any],
    renderer_id: str,
    transport: str = "http",
    render_strategy: str = "full_wire_payload",
    loss_report: dict[str, Any] | None = None,
    request_metadata: dict[str, Any] | None = None,
    runtime_context: dict[str, Any] | None = None,
    runtime_route: dict[str, Any] | None = None,
    runtime_policy: dict[str, Any] | None = None,
    canonical_input_items: tuple[LlmInputItem, ...] = (),
) -> dict[str, object]:
    messages = payload.get("messages")
    contents = payload.get("contents")
    input_items = payload.get("input")
    tools = payload.get("tools")
    message_count = len(messages) if isinstance(messages, list) else None
    content_count = len(contents) if isinstance(contents, list) else None
    input_item_count = len(input_items) if isinstance(input_items, list) else None
    tool_count = len(tools) if isinstance(tools, list) else 0
    tool_render_report = provider_tool_render_report(
        payload=payload,
        request_metadata=request_metadata,
    )
    tool_protocol_report = provider_tool_protocol_render_report(
        request_metadata=request_metadata,
    )
    render_report = {
        "renderer_id": renderer_id,
        "transport": transport,
        "render_strategy": render_strategy,
        "loss_report": dict(loss_report or {}),
        "tool_surface": tool_render_report,
        "tool_protocol": tool_protocol_report,
    }
    input_item_mapping = provider_input_item_mapping(canonical_input_items)
    if input_item_mapping:
        render_report["input_item_mapping"] = input_item_mapping
        render_report["input_item_mapping_coverage"] = provider_input_item_mapping_coverage(
            input_item_mapping,
            provider_input_item_count=(
                input_item_count
                if input_item_count is not None
                else message_count
                if message_count is not None
                else content_count
                if content_count is not None
                else 0
            ),
        )
    return {
        "preview_source": "provider_adapter",
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model": payload.get("model") or profile.model_name,
        "endpoint": endpoint,
        "transport": transport,
        "renderer_id": renderer_id,
        "render_strategy": render_strategy,
        "render_report": render_report,
        "payload_keys": sorted(str(key) for key in payload),
        "message_count": message_count,
        "content_count": content_count,
        "input_item_count": input_item_count,
        "tool_count": tool_count,
        "has_system": (
            payload.get("system") not in (None, "", [], {})
            or payload.get("system_instruction") not in (None, "", [], {})
        ),
        "option_summary": {
            "temperature": payload.get("temperature"),
            "top_p": payload.get("top_p"),
            "topP": payload.get("topP"),
            "max_tokens": payload.get("max_tokens"),
            "maxOutputTokens": (
                payload.get("generationConfig", {}).get("maxOutputTokens")
                if isinstance(payload.get("generationConfig"), dict)
                else None
            ),
            "response_format": safe_preview_value(payload.get("response_format")),
            "generationConfig": safe_preview_value(payload.get("generationConfig")),
            "toolConfig": safe_preview_value(payload.get("toolConfig")),
        },
        **provider_runtime_preview(
            runtime_route=runtime_route,
            runtime_policy=runtime_policy,
        ),
        "payload_preview": safe_preview_value(payload),
        **provider_input_preview(
            runtime_context=runtime_context,
            request_metadata=request_metadata,
        ),
    }


def provider_runtime_preview(
    *,
    runtime_route: dict[str, Any] | None,
    runtime_policy: dict[str, Any] | None,
) -> dict[str, object]:
    preview: dict[str, object] = {}
    if isinstance(runtime_route, dict) and runtime_route:
        preview["runtime_route"] = safe_preview_value(runtime_route)
    if isinstance(runtime_policy, dict) and runtime_policy:
        preview["runtime_policy"] = safe_preview_value(runtime_policy)
    return preview


def provider_input_item_mapping(
    input_items: tuple[LlmInputItem, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    provider_index = 0
    for index, item in enumerate(input_items[:120]):
        if (
            item.kind is LlmInputItemKind.MESSAGE
            and str(item.payload.get("role") or "").strip() == "system"
        ):
            continue
        metadata = provider_safe_input_metadata(item.metadata)
        row: dict[str, object] = {
            "provider_payload_index": provider_index,
            "input_item_index": index,
            "input_item_kind": item.kind.value,
            "input_item_source": item.source,
        }
        for key in (
            "node_id",
            "owner",
            "kind",
            "session_item_id",
            "tool_call_id",
            "tool_run_id",
            "llm_response_item_id",
        ):
            value = metadata.get(key)
            if value not in (None, "", {}, []):
                row[key] = str(value)
        rows.append(row)
        provider_index += 1
    return rows


def provider_input_item_mapping_coverage(
    rows: list[dict[str, object]],
    *,
    provider_input_item_count: int,
) -> dict[str, object]:
    traced_count = 0
    generated_or_unattributed: list[dict[str, object]] = []
    for row in rows:
        if row.get("session_item_id"):
            traced_count += 1
            row["trace_status"] = "runtime_input_item"
            continue
        source = str(row.get("input_item_source") or "").strip()
        if source:
            traced_count += 1
            row["trace_status"] = "input_item_source"
            row["trace_reason"] = source
            continue
        row["trace_status"] = "provider_renderer_generated_or_unattributed"
        generated_or_unattributed.append(
            {
                "provider_payload_index": row.get("provider_payload_index"),
                "input_item_index": row.get("input_item_index"),
                "input_item_kind": row.get("input_item_kind"),
            },
        )
    return {
        "provider_input_item_count": provider_input_item_count,
        "canonical_input_item_count": len(rows),
        "traced_input_item_count": traced_count,
        "untraced_input_item_count": len(rows) - traced_count,
        "provider_generated_or_unattributed": generated_or_unattributed,
    }


def provider_input_preview(
    *,
    runtime_context: dict[str, Any] | None,
    request_metadata: dict[str, Any] | None,
) -> dict[str, object]:
    preview = provider_input_preview_from_request_metadata(request_metadata)
    if not isinstance(runtime_context, dict):
        return preview
    for key, value in runtime_context.items():
        if value not in (None, "", {}, []):
            preview[key] = value
    if runtime_context:
        preview["runtime_context_source"] = "adapter_request"
    return preview
