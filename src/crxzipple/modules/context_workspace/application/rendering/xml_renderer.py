from __future__ import annotations

from html import escape

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.domain import ContextNode, ContextWorkspace
from crxzipple.modules.context_workspace.application.rendering.xml_renderer_tree import (
    children_by_parent_for_nodes,
    node_actions_label,
    node_content_renderable as _node_content_renderable,
    node_state_label,
    rendered_children,
    sorted_nodes,
    tree_snapshot_visible_nodes,
)
from crxzipple.modules.context_workspace.application.rendering.xml_renderer_tool_nodes import (
    append_tool_bundle_node_xml as _append_tool_bundle_node_xml,
    append_tool_function_node_xml as _append_tool_function_node_xml,
    append_tool_interaction_node_xml as _append_tool_interaction_node_xml,
)
from crxzipple.modules.context_workspace.application.rendering.xml_renderer_values import (
    node_bool_value as _node_bool_value,
    optional_metadata_text as _optional_metadata_text,
    truncate_xml_attr as _truncate_xml_attr,
)


def render_context_tree(
    workspace: ContextWorkspace,
    nodes: tuple[ContextNode, ...],
) -> str:
    children_by_parent = children_by_parent_for_nodes(nodes)
    lines = [
        (
            f'<context_tree session="{escape(workspace.session_key)}" '
            f'revision="{workspace.active_revision}" '
            f'schema_version="{escape(root_nodes.CONTEXT_TREE_SCHEMA_VERSION)}">'
        ),
    ]
    for node in sorted_nodes(children_by_parent.get(None, ())):
        append_context_node_xml(lines, node, children_by_parent, depth=1)
    lines.append("</context_tree>")
    return "\n".join(lines)


def render_context_node_without_descendants(node: ContextNode) -> str:
    lines: list[str] = []
    append_context_node_xml(lines, node, {}, depth=0)
    return "\n".join(lines)


def append_context_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
) -> None:
    if node.kind == "session_item":
        _append_session_item_node_xml(
            lines,
            node,
            children_by_parent,
            depth=depth,
        )
        return
    if node.kind == "tool_interaction":
        _append_tool_interaction_node_xml(
            lines,
            node,
            children_by_parent,
            depth=depth,
            append_node_xml=append_context_node_xml,
        )
        return
    if node.kind == "tool_function":
        _append_tool_function_node_xml(
            lines,
            node,
            children_by_parent,
            depth=depth,
            append_node_xml=append_context_node_xml,
        )
        return
    if node.kind in {"tool_bundle", "tool_bundle_group"}:
        _append_tool_bundle_node_xml(
            lines,
            node,
            children_by_parent,
            depth=depth,
            append_node_xml=append_context_node_xml,
        )
        return
    if node.kind == "session_evidence":
        _append_session_evidence_node_xml(
            lines,
            node,
            children_by_parent,
            depth=depth,
        )
        return
    indent = "  " * depth
    child_indent = "  " * (depth + 1)
    lines.append(
        f'{indent}<node id="{escape(node.id)}" kind="{escape(node.kind)}" '
        f'owner="{escape(node.owner)}" state="{node_state_label(node)}" '
        f'actions="{escape(node_actions_label(node))}">',
    )
    lines.append(f"{child_indent}<title>{escape(node.title)}</title>")
    if node.summary:
        lines.append(f"{child_indent}<summary>{escape(node.summary)}</summary>")
    if _node_content_renderable(node) and not node.state.collapsed:
        lines.append(f"{child_indent}<content>{escape(node.content)}</content>")
    for child in rendered_children(node, children_by_parent):
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def _append_session_item_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
) -> None:
    indent = "  " * depth
    child_indent = "  " * (depth + 1)
    item_indent = "  " * (depth + 2)
    content_indent = "  " * (depth + 3)
    role = str(node.owner_ref.get("role") or node.metadata.get("role") or "").strip()
    kind = str(node.owner_ref.get("kind") or node.metadata.get("kind") or "").strip()
    sequence_no = str(
        node.owner_ref.get("sequence_no") or node.metadata.get("sequence_no") or "",
    ).strip()
    visibility = str(
        node.owner_ref.get("visibility") or node.metadata.get("visibility") or "",
    ).strip()
    lines.append(
        f'{indent}<node id="{escape(node.id)}" kind="{escape(node.kind)}" '
        f'owner="{escape(node.owner)}" state="{node_state_label(node)}" '
        f'actions="{escape(node_actions_label(node))}">',
    )
    lines.append(f"{child_indent}<title>{escape(node.title)}</title>")
    if node.summary:
        lines.append(f"{child_indent}<summary>{escape(node.summary)}</summary>")
    lines.append(
        f'{child_indent}<item role="{escape(role)}" '
        f'sequence="{escape(sequence_no)}" kind="{escape(kind)}" '
        f'visibility="{escape(visibility)}">',
    )
    if _node_content_renderable(node) and not node.state.collapsed:
        lines.append(f"{item_indent}<content>")
        for content_line in node.content.splitlines() or [""]:
            lines.append(f"{content_indent}{escape(content_line)}")
        lines.append(f"{item_indent}</content>")
    lines.append(f"{child_indent}</item>")
    for child in rendered_children(node, children_by_parent):
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def _append_session_evidence_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
) -> None:
    indent = "  " * depth
    child_indent = "  " * (depth + 1)
    block_indent = "  " * (depth + 2)
    value_indent = "  " * (depth + 3)
    evidence_type = str(
        node.owner_ref.get("evidence_type")
        or node.metadata.get("evidence_type")
        or "",
    ).strip()
    lifecycle_status = str(
        node.owner_ref.get("evidence_lifecycle_status")
        or node.metadata.get("evidence_lifecycle_status")
        or "",
    ).strip()
    tool_name = str(
        node.owner_ref.get("tool_name") or node.metadata.get("tool_name") or "",
    ).strip()
    tool_call_id = str(
        node.owner_ref.get("tool_call_id") or node.metadata.get("tool_call_id") or "",
    ).strip()
    status = str(
        node.owner_ref.get("status") or node.metadata.get("status") or "",
    ).strip()
    observed = _node_bool_value(node, "observed")
    verified = _node_bool_value(node, "verified")
    failed = _node_bool_value(node, "failed")
    superseded = _node_bool_value(node, "superseded")
    attrs = [
        f'node_id="{escape(node.id)}"',
        f'type="{escape(evidence_type)}"',
        f'lifecycle="{escape(lifecycle_status)}"',
        f'status="{escape(status)}"',
        f'tool_name="{escape(tool_name)}"',
    ]
    if tool_call_id and not node.state.collapsed:
        attrs.append(f'call_id="{escape(tool_call_id)}"')
    if observed:
        attrs.append('observed="true"')
    if verified:
        attrs.append('verified="true"')
    if failed:
        attrs.append('failed="true"')
    if superseded:
        attrs.append('superseded="true"')
    if node.summary:
        attrs.append(f'summary="{escape(_truncate_xml_attr(node.summary, 120))}"')
    if node.state.collapsed:
        lines.append(f"{indent}<evidence {' '.join(attrs)}>")
        _append_evidence_refs(lines, node, block_indent=child_indent, compact=True)
        for child in rendered_children(node, children_by_parent):
            append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
        lines.append(f"{indent}</evidence>")
        return
    lines.append(
        f'{indent}<node id="{escape(node.id)}" kind="{escape(node.kind)}" '
        f'owner="{escape(node.owner)}" state="{node_state_label(node)}" '
        f'actions="{escape(node_actions_label(node))}">',
    )
    lines.append(f"{child_indent}<title>{escape(node.title)}</title>")
    if node.summary:
        lines.append(f"{child_indent}<summary>{escape(node.summary)}</summary>")
    lines.append(f"{child_indent}<evidence {' '.join(attrs)}>")
    _append_evidence_refs(lines, node, block_indent=block_indent, compact=False)
    if _node_content_renderable(node):
        lines.append(f"{block_indent}<content>")
        for content_line in node.content.splitlines() or [""]:
            lines.append(f"{value_indent}{escape(content_line)}")
        lines.append(f"{block_indent}</content>")
    lines.append(f"{child_indent}</evidence>")
    for child in rendered_children(node, children_by_parent):
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def _append_evidence_refs(
    lines: list[str],
    node: ContextNode,
    *,
    block_indent: str,
    compact: bool,
) -> None:
    attrs: list[str] = []
    ref_keys = (
        (
            ("tool_run_id", "tool_run_id"),
        )
        if compact
        else (
            ("tool_run_id", "tool_run_id"),
            ("call_session_item_id", "call_session_item_id"),
            ("result_session_item_id", "result_session_item_id"),
            ("call_sequence", "call_sequence_no"),
            ("result_sequence", "result_sequence_no"),
        )
    )
    for attr_name, metadata_key in ref_keys:
        value = _optional_metadata_text(node, metadata_key)
        if value is not None:
            attrs.append(f'{attr_name}="{escape(value)}"')
    if attrs:
        lines.append(f"{block_indent}<refs {' '.join(attrs)} />")


def _tool_result_envelope(node: ContextNode) -> dict[str, object] | None:
    envelope = node.metadata.get("tool_result_envelope")
    if not isinstance(envelope, dict):
        return None
    return envelope


__all__ = [
    "append_context_node_xml",
    "children_by_parent_for_nodes",
    "node_actions_label",
    "node_state_label",
    "render_context_node_without_descendants",
    "render_context_tree",
    "rendered_children",
    "sorted_nodes",
    "tree_snapshot_visible_nodes",
]
