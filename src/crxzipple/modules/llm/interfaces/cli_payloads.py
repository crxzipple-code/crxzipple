from __future__ import annotations

from collections import Counter
import json

import typer

from crxzipple.modules.llm.application import RegisterLlmProfileInput
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
    LlmSourceKind,
    ToolSchema,
)


def load_json(value: str | None, option_name: str) -> object:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"{option_name} must be valid JSON: {exc.msg}",
        ) from exc


def parse_messages(raw: str) -> tuple[LlmMessage, ...]:
    payload = load_json(raw, "--messages")
    if not isinstance(payload, list):
        raise typer.BadParameter("--messages must be a JSON array.")
    messages: list[LlmMessage] = []
    for item in payload:
        if not isinstance(item, dict):
            raise typer.BadParameter("--messages items must be JSON objects.")
        messages.append(
            LlmMessage(
                role=LlmMessageRole(item["role"]),
                content=item.get("content"),
                name=item.get("name"),
                tool_call_id=item.get("tool_call_id"),
                metadata=(
                    dict(item.get("metadata"))
                    if isinstance(item.get("metadata"), dict)
                    else {}
                ),
            ),
        )
    return tuple(messages)


def parse_tool_schemas(raw: str | None) -> tuple[ToolSchema, ...]:
    payload = load_json(raw, "--tool-schemas")
    if payload is None:
        return ()
    if not isinstance(payload, list):
        raise typer.BadParameter("--tool-schemas must be a JSON array.")
    schemas: list[ToolSchema] = []
    for item in payload:
        if not isinstance(item, dict):
            raise typer.BadParameter("--tool-schemas items must be JSON objects.")
        schemas.append(
            ToolSchema(
                name=str(item["name"]),
                description=str(item.get("description", "")),
                input_schema=(
                    dict(item.get("input_schema"))
                    if isinstance(item.get("input_schema"), dict)
                    else {}
                ),
            ),
        )
    return tuple(schemas)


def profile_input_from_cli_args(
    *,
    llm_id: str,
    provider: LlmProviderKind,
    api_family: LlmApiFamily,
    model_name: str,
    context_window_tokens: int | None,
    model_family: LlmModelFamily,
    capability: list[LlmCapability] | None,
    temperature: float | None,
    top_p: float | None,
    max_output_tokens: int | None,
    reasoning_effort: str | None,
    base_url: str | None,
    credential_binding_id: str | None,
    timeout_seconds: int,
    max_concurrency: int | None,
    concurrency_key: str | None,
    enabled: bool,
) -> RegisterLlmProfileInput:
    return RegisterLlmProfileInput(
        id=llm_id,
        provider=provider,
        api_family=api_family,
        model_name=model_name,
        context_window_tokens=context_window_tokens,
        model_family=model_family,
        capabilities=tuple(capability or ()),
        default_params=LlmDefaults(
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
        ),
        base_url=base_url,
        credential_binding_id=credential_binding_id,
        timeout_seconds=timeout_seconds,
        max_concurrency=max_concurrency,
        concurrency_key=concurrency_key,
        source_kind=LlmSourceKind.MANUAL,
        enabled=enabled,
    )


def invocation_request_preview_report(
    invocation: object,
    *,
    include_provider_preview: bool = False,
) -> dict[str, object]:
    preview = dict(getattr(invocation, "provider_request_payload_preview", {}) or {})
    input_items = tuple(getattr(invocation, "input_items", ()) or ())
    messages = tuple(getattr(invocation, "messages", ()) or ())
    provider_context_messages = tuple(
        getattr(invocation, "provider_context_messages", ()) or (),
    )
    tool_schemas = tuple(getattr(invocation, "tool_schemas", ()) or ())
    request_metadata = dict(getattr(invocation, "request_metadata", {}) or {})
    continuation = getattr(invocation, "continuation", None)
    input_kind_counts = Counter(
        str(getattr(item.kind, "value", item.kind)) for item in input_items
    )
    message_role_counts = Counter(
        str(getattr(message.role, "value", message.role)) for message in messages
    )
    provider_context_role_counts = Counter(
        str(getattr(message.role, "value", message.role))
        for message in provider_context_messages
    )
    report: dict[str, object] = {
        "invocation_id": getattr(invocation, "id", ""),
        "llm_id": getattr(invocation, "llm_id", ""),
        "status": _status_text(invocation),
        "provider_request_id": getattr(invocation, "provider_request_id", None),
        "transport": preview.get("transport") or preview.get("provider_transport"),
        "renderer": preview.get("renderer"),
        "render_strategy": preview.get("render_strategy"),
        "message_type": preview.get("message_type"),
        "has_previous_response_id": bool(preview.get("has_previous_response_id")),
        "input_delta_mode": bool(preview.get("input_delta_mode")),
        "input_baseline_count": preview.get("input_baseline_count"),
        "input_delta_count": preview.get("input_delta_count"),
        "canonical_input_item_count": len(input_items),
        "canonical_input_item_kind_counts": dict(sorted(input_kind_counts.items())),
        "message_count": len(messages),
        "message_role_counts": dict(sorted(message_role_counts.items())),
        "provider_context_message_count": len(provider_context_messages),
        "provider_context_role_counts": dict(
            sorted(provider_context_role_counts.items()),
        ),
        "provider_input_item_count": preview.get("input_item_count"),
        "provider_input_item_kinds": preview.get("input_item_kinds", []),
        "tool_schema_count": len(tool_schemas),
        "tool_schema_names": [
            getattr(schema, "name", "")
            for schema in tool_schemas
            if str(getattr(schema, "name", "")).strip()
        ],
        "preview_tool_count": preview.get("tool_count"),
        "preview_tool_names": preview.get("tool_names", []),
        "request_metadata_keys": sorted(str(key) for key in request_metadata),
        "request_render_snapshot_id": request_metadata.get(
            "request_render_snapshot_id",
        ),
        "continuation": (
            continuation.to_payload()
            if hasattr(continuation, "to_payload")
            else None
        ),
    }
    if include_provider_preview:
        report["provider_request_payload_preview"] = preview
    return report


def _status_text(invocation: object) -> str:
    status = getattr(invocation, "status", "")
    return str(getattr(status, "value", status))
