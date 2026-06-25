"""Default tool schema metadata bootstrap for context snapshots."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import ContextTreeService
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from ._metadata import metadata_string_list, metadata_text
from .tool_schema_catalog_bootstrap import (
    ToolRuntimeRequestCatalog,
    resolve_default_tool_schema_metadata_from_catalog,
)
from .tool_schema_group_refs import metadata_tool_schema_group_refs
from .tool_schema_tree_bootstrap import (
    default_tool_schema_group_refs_from_source_policy,
    resolve_default_tool_schema_metadata_from_tree,
)

__all__ = [
    "ToolRuntimeRequestCatalog",
    "default_tool_schema_group_refs_from_source_policy",
    "merge_default_tool_schema_metadata",
    "metadata_tool_schema_group_refs",
    "resolve_default_tool_schema_metadata",
    "resolve_draft_tool_schema_metadata",
]


def resolve_draft_tool_schema_metadata(draft: RuntimeLlmRequestDraft) -> dict[str, object]:
    default_tool_schema_ids = metadata_string_list(
        draft.flow_hint.get("default_tool_schema_ids"),
    )
    default_tool_schema_group_refs = metadata_tool_schema_group_refs(
        draft.flow_hint.get("default_tool_schema_group_refs"),
    )
    if not default_tool_schema_ids and not default_tool_schema_group_refs:
        return {}
    metadata: dict[str, object] = {}
    if default_tool_schema_group_refs:
        metadata["default_tool_schema_group_refs"] = [
            dict(ref) for ref in default_tool_schema_group_refs
        ]
    if not default_tool_schema_ids:
        return metadata
    source = metadata_text(draft.flow_hint.get("default_tool_schema_source"))
    metadata["default_tool_schema_ids"] = default_tool_schema_ids
    metadata["default_tool_schema_source"] = source or "runtime_request_flow_hint"
    return metadata


def merge_default_tool_schema_metadata(
    direct_metadata: dict[str, object],
    group_metadata: dict[str, object],
) -> dict[str, object]:
    if not direct_metadata:
        return dict(group_metadata)
    if not group_metadata:
        return dict(direct_metadata)
    metadata = dict(direct_metadata)
    schema_ids: list[str] = []
    for item in metadata_string_list(direct_metadata.get("default_tool_schema_ids")):
        if item not in schema_ids:
            schema_ids.append(item)
    for item in metadata_string_list(group_metadata.get("default_tool_schema_ids")):
        if item not in schema_ids:
            schema_ids.append(item)
    if schema_ids:
        metadata["default_tool_schema_ids"] = schema_ids
    source_values = [
        source
        for source in (
            metadata_text(direct_metadata.get("default_tool_schema_source")),
            metadata_text(group_metadata.get("default_tool_schema_source")),
        )
        if source is not None
    ]
    if source_values:
        metadata["default_tool_schema_source"] = ",".join(dict.fromkeys(source_values))
    for key in ("default_tool_schema_group_refs", "default_tool_schema_group_matches"):
        if key in group_metadata:
            metadata[key] = group_metadata[key]
    return metadata


def resolve_default_tool_schema_metadata(
    *,
    tree_service: ContextTreeService | None,
    runtime_request_catalog: ToolRuntimeRequestCatalog | None = None,
    session_key: str,
    run_id: str,
    draft: RuntimeLlmRequestDraft,
    allow_tree_fallback: bool = True,
) -> dict[str, object]:
    catalog_metadata = resolve_default_tool_schema_metadata_from_catalog(
        runtime_request_catalog=runtime_request_catalog,
        draft=draft,
    )
    if catalog_metadata:
        return catalog_metadata
    if not allow_tree_fallback or tree_service is None:
        return {}
    return resolve_default_tool_schema_metadata_from_tree(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        draft=draft,
    )
