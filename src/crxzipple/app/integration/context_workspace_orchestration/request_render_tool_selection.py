"""Tool schema selection helpers for request-render snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .tool_schema_mirror import ToolSchemaMirrorAdapter


@dataclass(frozen=True)
class RequestRenderVisibleTools:
    schemas: tuple[ToolSchema, ...]
    refs: tuple[dict[str, object], ...]


def requested_tool_schema_names(
    *,
    adapter: ToolSchemaMirrorAdapter,
    draft: RuntimeLlmRequestDraft,
    render_metadata: dict[str, object],
    session_key: str,
) -> tuple[str, ...]:
    return tuple(
        schema.name
        for schema in adapter.request_render_tool_schemas(
            draft.tool_schemas,
            render_metadata=render_metadata,
            session_key=session_key,
            surface_contract=draft.surface_policy.surface_contract,
            active_tool_names=(),
        )
    )


def visible_tool_schema_selection(
    *,
    adapter: ToolSchemaMirrorAdapter,
    context_slice: object | None,
    available_schemas: tuple[ToolSchema, ...],
    requested_schema_names: tuple[str, ...],
) -> RequestRenderVisibleTools:
    if context_slice is None:
        return RequestRenderVisibleTools(schemas=(), refs=())
    schemas = adapter.visible_tool_schemas(
        context_slice,
        available_schemas=available_schemas,
        requested_schema_names=requested_schema_names,
    )
    refs = adapter.visible_tool_schema_refs(
        context_slice,
        schemas=schemas,
    )
    return RequestRenderVisibleTools(schemas=schemas, refs=refs)
