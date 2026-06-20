from __future__ import annotations

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.application.models import (
    ContextDebugDeltaResult,
    ContextObservationRenderResult,
)
from crxzipple.modules.context_workspace.domain import (
    ContextNode,
    ContextSnapshot,
    ContextWorkspace,
)

from .estimates import aggregate_estimate, estimate_breakdown, text_estimate
from .provider_mirror import render_provider_attachments
from .snapshot_metadata import root_node_ids, runtime_contract_metadata
from .xml_renderer import render_context_tree, tree_snapshot_visible_nodes


class ContextTreeRenderPipeline:
    def render_observation(
        self,
        *,
        workspace: ContextWorkspace,
        nodes: tuple[ContextNode, ...],
        provider_attachments: dict[str, object],
        metadata: dict[str, object],
    ) -> ContextObservationRenderResult:
        visible_nodes = tree_snapshot_visible_nodes(nodes)
        node_estimate = aggregate_estimate(visible_nodes)
        breakdown = estimate_breakdown(visible_nodes)
        debug_body = render_context_tree(workspace, visible_nodes)
        estimate = text_estimate(debug_body)
        breakdown["node_visible"] = node_estimate.to_payload()
        breakdown["debug_body"] = estimate.to_payload()
        (
            mirrored_attachments,
            mirrored_node_ids,
            tool_schema_mirror_available,
            provider_attachment_report,
        ) = render_provider_attachments(
            visible_nodes,
            base=provider_attachments,
            render_metadata=metadata,
        )
        return ContextObservationRenderResult(
            workspace=workspace,
            debug_body=debug_body,
            estimate=estimate,
            included_node_ids=tuple(node.id for node in visible_nodes),
            estimate_breakdown=breakdown,
            runtime_contract=runtime_contract_metadata(visible_nodes),
            tree_schema_version=root_nodes.CONTEXT_TREE_SCHEMA_VERSION,
            root_node_ids=root_node_ids(visible_nodes),
            provider_attachments=mirrored_attachments,
            provider_attachment_report=provider_attachment_report,
            mirrored_node_ids=mirrored_node_ids,
            tool_schema_mirror_available=tool_schema_mirror_available,
        )

    def render_delta(
        self,
        *,
        workspace: ContextWorkspace,
        baseline: ContextSnapshot,
        current: ContextObservationRenderResult,
        metadata: dict[str, object],
    ) -> ContextDebugDeltaResult:
        current_node_ids = tuple(current.included_node_ids)
        baseline_node_ids = tuple(baseline.included_node_ids)
        added_node_ids = tuple(
            node_id for node_id in current_node_ids if node_id not in baseline_node_ids
        )
        removed_node_ids = tuple(
            node_id for node_id in baseline_node_ids if node_id not in current_node_ids
        )
        current_tool_schema_names = tool_schema_names(current.provider_attachments)
        baseline_tool_schema_names = tool_schema_names(baseline.provider_attachments)
        added_tool_schema_names = tuple(
            name
            for name in current_tool_schema_names
            if name not in baseline_tool_schema_names
        )
        removed_tool_schema_names = tuple(
            name
            for name in baseline_tool_schema_names
            if name not in current_tool_schema_names
        )
        delta_metadata = dict(metadata)
        delta_metadata.update(
            {
                "baseline_snapshot_id": baseline.id,
                "baseline_tree_revision": baseline.tree_revision,
                "current_tree_revision": workspace.active_revision,
                "added_node_count": len(added_node_ids),
                "removed_node_count": len(removed_node_ids),
                "added_tool_schema_count": len(added_tool_schema_names),
                "removed_tool_schema_count": len(removed_tool_schema_names),
            },
        )
        return ContextDebugDeltaResult(
            workspace=workspace,
            baseline_snapshot_id=baseline.id,
            baseline_revision=baseline.tree_revision,
            current_revision=workspace.active_revision,
            changed_revision=workspace.active_revision != baseline.tree_revision,
            added_node_ids=added_node_ids,
            removed_node_ids=removed_node_ids,
            current_included_node_ids=current_node_ids,
            baseline_included_node_ids=baseline_node_ids,
            added_tool_schema_names=added_tool_schema_names,
            removed_tool_schema_names=removed_tool_schema_names,
            current_tool_schema_names=current_tool_schema_names,
            baseline_tool_schema_names=baseline_tool_schema_names,
            debug_body=render_context_debug_delta_body(
                workspace=workspace,
                baseline=baseline,
                added_node_ids=added_node_ids,
                removed_node_ids=removed_node_ids,
                added_tool_schema_names=added_tool_schema_names,
                removed_tool_schema_names=removed_tool_schema_names,
            ),
            provider_attachments=current.provider_attachments,
            provider_attachment_report=current.provider_attachment_report,
            estimate=current.estimate,
            metadata=delta_metadata,
        )


def tool_schema_names(provider_attachments: dict[str, object]) -> tuple[str, ...]:
    schemas = provider_attachments.get("tool_schemas")
    if not isinstance(schemas, list | tuple):
        return ()
    names = {
        name.strip()
        for schema in schemas
        if isinstance(schema, dict)
        for name in (schema.get("name"),)
        if isinstance(name, str) and name.strip()
    }
    return tuple(sorted(names))


def render_context_debug_delta_body(
    *,
    workspace: ContextWorkspace,
    baseline: ContextSnapshot,
    added_node_ids: tuple[str, ...],
    removed_node_ids: tuple[str, ...],
    added_tool_schema_names: tuple[str, ...],
    removed_tool_schema_names: tuple[str, ...],
) -> str:
    lines = [
        (
            f'<context_tree_delta session_key="{workspace.session_key}" '
            f'from_snapshot_id="{baseline.id}" '
            f'from_revision="{baseline.tree_revision}" '
            f'to_revision="{workspace.active_revision}">'
        ),
        _xml_list("added_rendered_nodes", added_node_ids),
        _xml_list("removed_rendered_nodes", removed_node_ids),
        _xml_list("added_tool_schemas", added_tool_schema_names),
        _xml_list("removed_tool_schemas", removed_tool_schema_names),
        "</context_tree_delta>",
    ]
    return "\n".join(lines)


def _xml_list(tag: str, values: tuple[str, ...]) -> str:
    if not values:
        return f"  <{tag} />"
    lines = [f"  <{tag}>"]
    lines.extend(f"    <item>{_escape_xml(value)}</item>" for value in values)
    lines.append(f"  </{tag}>")
    return "\n".join(lines)


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


__all__ = [
    "ContextTreeRenderPipeline",
    "render_context_debug_delta_body",
    "tool_schema_names",
]
