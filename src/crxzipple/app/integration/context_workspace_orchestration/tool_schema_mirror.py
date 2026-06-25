from __future__ import annotations

from crxzipple.modules.context_workspace.application import ContextTreeService
from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .tool_schema_bootstrap import (
    merge_default_tool_schema_metadata,
    resolve_default_tool_schema_metadata,
    resolve_draft_tool_schema_metadata,
    ToolRuntimeRequestCatalog,
)
from .tool_schema_context_slice_projection import (
    context_slice_tool_schema_refs,
    context_slice_tool_schemas,
)
from .tool_schema_node_sync import sync_requested_tool_schema_nodes
from .tool_schema_request_selection import request_render_tool_schemas


class ToolSchemaMirrorAdapter:
    def __init__(
        self,
        *,
        tree_service: ContextTreeService | None = None,
        runtime_request_catalog: ToolRuntimeRequestCatalog | None = None,
    ) -> None:
        self._tree_service = tree_service
        self._runtime_request_catalog = runtime_request_catalog

    def resolve_render_metadata(
        self,
        *,
        session_key: str,
        run_id: str,
        draft: RuntimeLlmRequestDraft,
        allow_tree_fallback: bool,
    ) -> dict[str, object]:
        return merge_default_tool_schema_metadata(
            resolve_draft_tool_schema_metadata(draft),
            resolve_default_tool_schema_metadata(
                tree_service=self._tree_service,
                runtime_request_catalog=self._runtime_request_catalog,
                session_key=session_key,
                run_id=run_id,
                draft=draft,
                allow_tree_fallback=allow_tree_fallback,
            ),
        )

    def request_render_tool_schemas(
        self,
        schemas: tuple[ToolSchema, ...],
        *,
        render_metadata: dict[str, object],
        session_key: str,
        surface_contract: str = "default_open",
        active_tool_names: frozenset[str] = frozenset(),
    ) -> tuple[ToolSchema, ...]:
        return request_render_tool_schemas(
            schemas,
            render_metadata=render_metadata,
            tree_service=self._tree_service,
            session_key=session_key,
            surface_contract=surface_contract,
            active_tool_names=active_tool_names,
        )

    def sync_requested_tool_schema_nodes(
        self,
        *,
        session_key: str,
        run_id: str,
        schema_names: tuple[str, ...],
        render_metadata: dict[str, object],
    ) -> None:
        sync_requested_tool_schema_nodes(
            tree_service=self._tree_service,
            session_key=session_key,
            run_id=run_id,
            schema_names=schema_names,
            render_metadata=render_metadata,
        )

    def visible_tool_schemas(
        self,
        context_slice: object | None,
        *,
        available_schemas: tuple[ToolSchema, ...] = (),
        requested_schema_names: tuple[str, ...] = (),
    ) -> tuple[ToolSchema, ...]:
        return context_slice_tool_schemas(
            context_slice,
            available_schemas=available_schemas,
            requested_schema_names=requested_schema_names,
        )

    def visible_tool_schema_refs(
        self,
        context_slice: object | None,
        *,
        schemas: tuple[ToolSchema, ...] = (),
    ) -> tuple[dict[str, object], ...]:
        return context_slice_tool_schema_refs(context_slice, schemas=schemas)
