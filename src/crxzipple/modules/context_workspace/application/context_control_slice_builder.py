from __future__ import annotations

from uuid import uuid4

from crxzipple.modules.context_workspace.application.context_control_projection import (
    merge_control_refs_with_protocol_required,
)
from crxzipple.modules.context_workspace.application.context_slice_refs import (
    archived_ref,
    collapsed_ref,
    metadata_dict_list,
    metadata_string_set,
)
from crxzipple.modules.context_workspace.application.context_slice_selection import (
    included_nodes_for_slice,
)
from crxzipple.modules.context_workspace.application.context_tool_surface_projection import (
    active_tools_for_slice,
)
from crxzipple.modules.context_workspace.application.models import (
    ContextControlReport,
    ContextControlSlice,
)
from crxzipple.modules.context_workspace.domain import ContextNode, ContextWorkspace


def build_context_control_slice(
    *,
    workspace: ContextWorkspace,
    nodes: tuple[ContextNode, ...],
    visible_nodes: tuple[ContextNode, ...],
    run_id: str,
    audience: str,
    provider_profile: str | None,
    request_metadata: dict[str, object],
    read_only: bool,
) -> ContextControlSlice:
    selected_nodes = included_nodes_for_slice(
        nodes=nodes,
        visible_nodes=visible_nodes,
        audience=audience,
        request_metadata=request_metadata,
    )
    selected_node_ids = {node.id for node in selected_nodes}
    requested_tool_schema_names = metadata_string_set(
        request_metadata.get("requested_tool_schema_names"),
    )
    active_tools = active_tools_for_slice(
        nodes=nodes,
        audience=audience,
        requested_tool_schema_names=requested_tool_schema_names,
    )
    collapsed_refs = tuple(
        collapsed_ref(node)
        for node in visible_nodes
        if node.state.collapsed
    )
    archived_refs = tuple(
        archived_ref(node)
        for node in nodes
        if node.state.archived
    )
    protocol_required_refs = tuple(
        dict(item)
        for item in metadata_dict_list(
            request_metadata.get("protocol_required_refs"),
        )
    )
    selected_refs = merge_control_refs_with_protocol_required(
        selected_nodes=selected_nodes,
        protocol_required_refs=protocol_required_refs,
    )
    selected_ref_node_ids = tuple(item.node_id for item in selected_refs)
    omitted_node_ids = tuple(
        node.id for node in nodes if node.id not in selected_node_ids
    )
    report = ContextControlReport(
        selected_node_ids=selected_ref_node_ids,
        omitted_node_ids=omitted_node_ids,
        collapsed_refs=collapsed_refs,
        archived_refs=archived_refs,
        protocol_required_refs=protocol_required_refs,
        metadata={
            "audience": audience,
            "provider_profile": provider_profile or "",
            "visible_node_count": len(visible_nodes),
            "active_tool_count": len(active_tools),
            "tree_scan_performed": True,
            "read_only": read_only,
            "tree_backed_selected_node_count": len(selected_nodes),
            "protocol_synthetic_ref_count": max(
                0,
                len(selected_refs) - len(selected_nodes),
            ),
            **request_metadata,
        },
    )
    slice_id = f"ctxctrl_{uuid4().hex}"
    return ContextControlSlice(
        slice_id=slice_id,
        session_key=workspace.session_key,
        run_id=run_id,
        audience=audience,
        tree_revision=workspace.active_revision,
        selected_refs=selected_refs,
        active_tools=active_tools,
        report=report,
        metadata={
            "slice_id": slice_id,
            "audience": audience,
            "provider_profile": provider_profile or "",
            "workspace_id": workspace.id,
            "tree_scan_performed": True,
            "read_only": read_only,
            **request_metadata,
        },
    )


__all__ = ["build_context_control_slice"]
