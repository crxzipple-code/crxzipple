from __future__ import annotations

import json
from html import escape

from crxzipple.modules.context_workspace.application import root_nodes
from crxzipple.modules.context_workspace.domain import ContextNode, ContextWorkspace


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


def tree_prompt_visible_nodes(nodes: tuple[ContextNode, ...]) -> tuple[ContextNode, ...]:
    prompt_nodes = tuple(node for node in nodes if node.state.prompt_visible)
    children_by_parent = children_by_parent_for_nodes(prompt_nodes)
    visible: list[ContextNode] = []

    def has_forced_visible_descendant(node: ContextNode) -> bool:
        if node.state.opened or node.state.pinned:
            return True
        return any(
            has_forced_visible_descendant(child)
            for child in children_by_parent.get(node.id, ())
        )

    def visit(node: ContextNode) -> None:
        visible.append(node)
        if node.state.collapsed:
            children = tuple(
                child
                for child in children_by_parent.get(node.id, ())
                if has_forced_visible_descendant(child)
            )
        else:
            children = tuple(children_by_parent.get(node.id, ()))
        for child in sorted_nodes(children):
            visit(child)

    for root in sorted_nodes(children_by_parent.get(None, ())):
        visit(root)
    return tuple(visible)


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
        )
        return
    if node.kind == "tool_function":
        _append_tool_function_node_xml(
            lines,
            node,
            children_by_parent,
            depth=depth,
        )
        return
    if node.kind in {"tool_bundle", "tool_bundle_group"}:
        _append_tool_bundle_node_xml(
            lines,
            node,
            children_by_parent,
            depth=depth,
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
    if node.content and not node.state.collapsed:
        lines.append(f"{child_indent}<content>{escape(node.content)}</content>")
    for child in rendered_children(node, children_by_parent):
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def node_state_label(node: ContextNode) -> str:
    if node.state.opened:
        return "opened"
    return "collapsed" if node.state.collapsed else "expanded"


def node_actions_label(node: ContextNode) -> str:
    return " ".join(action.value for action in node.actions)


def children_by_parent_for_nodes(
    nodes: tuple[ContextNode, ...],
) -> dict[str | None, list[ContextNode]]:
    node_ids = {node.id for node in nodes}
    children_by_parent: dict[str | None, list[ContextNode]] = {}
    for node in nodes:
        if node.parent_id is not None and node.parent_id not in node_ids:
            continue
        parent_id = node.parent_id
        children_by_parent.setdefault(parent_id, []).append(node)
    return children_by_parent


def sorted_nodes(nodes: list[ContextNode] | tuple[ContextNode, ...]) -> tuple[ContextNode, ...]:
    return tuple(sorted(nodes, key=lambda item: (item.display_order, item.id)))


def rendered_children(
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
) -> tuple[ContextNode, ...]:
    return sorted_nodes(tuple(children_by_parent.get(node.id, ())))


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
    if node.content and not node.state.collapsed:
        lines.append(f"{item_indent}<content>")
        for content_line in node.content.splitlines() or [""]:
            lines.append(f"{content_indent}{escape(content_line)}")
        lines.append(f"{item_indent}</content>")
    lines.append(f"{child_indent}</item>")
    for child in rendered_children(node, children_by_parent):
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def _append_tool_interaction_node_xml(
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
    tool_name = str(
        node.owner_ref.get("tool_name") or node.metadata.get("tool_name") or "",
    ).strip()
    tool_call_id = str(
        node.owner_ref.get("tool_call_id") or node.metadata.get("tool_call_id") or "",
    ).strip()
    status = str(
        node.owner_ref.get("status") or node.metadata.get("status") or "",
    ).strip()
    lifecycle_status = str(
        node.owner_ref.get("lifecycle_status")
        or node.metadata.get("lifecycle_status")
        or "",
    ).strip()
    frontier = _node_bool_value(node, "frontier")
    consumed = _node_bool_value(node, "consumed")
    failed = _node_bool_value(node, "failed")
    verified = _node_bool_value(node, "verified")
    superseded = _node_bool_value(node, "superseded")
    call_sequence = str(
        node.owner_ref.get("call_sequence_no")
        or node.metadata.get("call_sequence_no")
        or "",
    ).strip()
    result_sequence = str(
        node.owner_ref.get("result_sequence_no")
        or node.metadata.get("result_sequence_no")
        or "",
    ).strip()
    sequence_range = (
        f"{call_sequence}-{result_sequence}"
        if call_sequence and result_sequence
        else call_sequence or result_sequence
    )
    inline_content_allowed = _tool_interaction_inline_content_allowed(
        node,
        frontier=frontier,
    )
    if node.state.collapsed or not inline_content_allowed:
        attrs = [
            f'tool_name="{escape(tool_name)}"',
            f'node_id="{escape(node.id)}"',
        ]
        if status:
            attrs.append(f'status="{escape(status)}"')
        if sequence_range:
            attrs.append(f'sequence="{escape(sequence_range)}"')
        if frontier and tool_call_id:
            attrs.append(f'call_id="{escape(tool_call_id)}"')
        if frontier:
            attrs.append('frontier="true"')
        if not consumed:
            attrs.append('consumed="false"')
        if superseded:
            attrs.append('superseded="true"')
        if lifecycle_status and lifecycle_status not in {"consumed"}:
            attrs.append(f'lifecycle="{escape(lifecycle_status)}"')
        if failed:
            attrs.append('failed="true"')
            error_summary = _optional_metadata_text(node, "error_json")
            if error_summary is not None:
                attrs.append(
                    f'error="{escape(_truncate_xml_attr(error_summary, 120))}"',
                )
        if verified:
            attrs.append('verified="true"')
        if node.summary:
            attrs.append(f'summary="{escape(_truncate_xml_attr(node.summary, 180))}"')
        if not node.state.collapsed and _tool_interaction_inline_content_chars(node) > 0:
            attrs.append('content_omitted="non_frontier_budget_guard"')
        lines.append(f"{indent}<tool_interaction {' '.join(attrs)}>")
        if not node.state.collapsed or frontier:
            _append_tool_interaction_refs(
                lines,
                node,
                block_indent=child_indent,
            )
            _append_tool_result_summary(
                lines,
                node,
                block_indent=child_indent,
                value_indent=block_indent,
            )
        for child in rendered_children(node, children_by_parent):
            append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
        lines.append(f"{indent}</tool_interaction>")
        return
    lines.append(
        f'{indent}<node id="{escape(node.id)}" kind="{escape(node.kind)}" '
        f'owner="{escape(node.owner)}" state="{node_state_label(node)}" '
        f'actions="{escape(node_actions_label(node))}">',
    )
    lines.append(f"{child_indent}<title>{escape(node.title)}</title>")
    if node.summary:
        lines.append(f"{child_indent}<summary>{escape(node.summary)}</summary>")
    lines.append(
        f'{child_indent}<tool_interaction tool_name="{escape(tool_name)}" '
        f'call_id="{escape(tool_call_id)}" status="{escape(status)}" '
        f'lifecycle="{escape(lifecycle_status)}" '
        f'frontier="{_xml_bool(frontier)}" consumed="{_xml_bool(consumed)}" '
        f'failed="{_xml_bool(failed)}" verified="{_xml_bool(verified)}" '
        f'superseded="{_xml_bool(superseded)}" '
        f'sequence="{escape(sequence_range)}">',
    )
    _append_tool_interaction_refs(
        lines,
        node,
        block_indent=block_indent,
    )
    has_result_summary = _append_tool_result_summary(
        lines,
        node,
        block_indent=block_indent,
        value_indent=value_indent,
    )
    _append_xml_text_block(
        lines,
        "arguments",
        _optional_metadata_text(node, "arguments_json"),
        block_indent=block_indent,
        value_indent=value_indent,
    )
    _append_xml_text_block(
        lines,
        "error",
        _optional_metadata_text(node, "error_json"),
        block_indent=block_indent,
        value_indent=value_indent,
    )
    _append_xml_text_block(
        lines,
        "result",
        None if has_result_summary else _optional_metadata_text(node, "result_content"),
        block_indent=block_indent,
        value_indent=value_indent,
    )
    lines.append(f"{child_indent}</tool_interaction>")
    for child in rendered_children(node, children_by_parent):
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def _append_xml_text_block(
    lines: list[str],
    tag_name: str,
    value: str | None,
    *,
    block_indent: str,
    value_indent: str,
) -> None:
    if value is None:
        return
    lines.append(f"{block_indent}<{tag_name}>")
    for content_line in value.splitlines() or [""]:
        lines.append(f"{value_indent}{escape(content_line)}")
    lines.append(f"{block_indent}</{tag_name}>")


def _append_tool_result_summary(
    lines: list[str],
    node: ContextNode,
    *,
    block_indent: str,
    value_indent: str,
) -> bool:
    envelope = _tool_result_envelope(node)
    if envelope is None:
        return False
    attrs = ['source="tool_result_envelope"']
    status = _optional_dict_text(envelope, "status")
    if status is not None:
        attrs.append(f'status="{escape(_truncate_xml_attr(status, 64))}"')
    if envelope.get("truncated") is True:
        attrs.append('truncated="true"')
    omitted_count = _optional_int(envelope.get("omitted_count"))
    omitted_chars = _optional_int(envelope.get("omitted_chars"))
    if omitted_count is not None:
        attrs.append(f'omitted_count="{omitted_count}"')
    if omitted_chars is not None:
        attrs.append(f'omitted_chars="{omitted_chars}"')
    lines.append(f"{block_indent}<result_summary {' '.join(attrs)}>")
    _append_xml_text_block(
        lines,
        "summary",
        _bounded_optional_text(envelope.get("summary"), 600),
        block_indent=value_indent,
        value_indent=f"{value_indent}  ",
    )
    key_facts = envelope.get("key_facts")
    if isinstance(key_facts, dict) and key_facts:
        _append_xml_text_block(
            lines,
            "key_facts",
            _bounded_text(_json_fragment(key_facts), 1000),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    evidence_path = _browser_evidence_path_ref_line(node)
    if evidence_path is not None:
        _append_xml_text_block(
            lines,
            "evidence_path",
            evidence_path,
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    artifact_refs = _text_list(envelope.get("evidence_refs"))
    if artifact_refs:
        _append_xml_text_block(
            lines,
            "artifact_refs",
            ", ".join(artifact_refs),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    read_handles = envelope.get("read_handles")
    if read_handles is not None:
        _append_xml_text_block(
            lines,
            "read_handles",
            _bounded_text(_json_fragment(read_handles), 1200),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    warnings = _text_list(envelope.get("warnings"))
    if warnings:
        _append_xml_text_block(
            lines,
            "warnings",
            _bounded_text("; ".join(warnings), 600),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    lines.append(f"{value_indent}<read_full_result>use refs or read handles</read_full_result>")
    lines.append(f"{block_indent}</result_summary>")
    return True


def _tool_interaction_inline_content_allowed(
    node: ContextNode,
    *,
    frontier: bool,
) -> bool:
    if node.state.collapsed:
        return False
    if frontier or node.state.pinned or node.state.opened:
        return True
    return False


def _tool_interaction_inline_content_chars(node: ContextNode) -> int:
    return sum(
        len(value)
        for value in (
            _optional_metadata_text(node, "arguments_json"),
            _optional_metadata_text(node, "error_json"),
            _optional_metadata_text(node, "result_content"),
        )
        if value is not None
    )


def _append_tool_interaction_refs(
    lines: list[str],
    node: ContextNode,
    *,
    block_indent: str,
) -> None:
    attrs: list[str] = []
    for attr_name, metadata_key in (
        ("call_session_item_id", "call_session_item_id"),
        ("result_session_item_id", "result_session_item_id"),
        ("call_sequence", "call_sequence_no"),
        ("result_sequence", "result_sequence_no"),
    ):
        value = _optional_metadata_text(node, metadata_key)
        if value is not None:
            attrs.append(f'{attr_name}="{escape(value)}"')
    if not attrs:
        return
    lines.append(f"{block_indent}<refs {' '.join(attrs)} />")


def _append_tool_function_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
) -> None:
    indent = "  " * depth
    child_indent = "  " * (depth + 1)
    tool_id = str(node.owner_ref.get("tool_id") or node.title or "").strip()
    display_name = str(
        node.owner_ref.get("tool_name")
        or node.metadata.get("display_name")
        or node.title
        or "",
    ).strip()
    source_id = str(node.owner_ref.get("source_id") or "").strip()
    runtime_key = str(node.owner_ref.get("runtime_key") or "").strip()
    compact = node.state.collapsed and not node.state.pinned and not node.state.opened
    if compact and node.state.schema_enabled:
        return
    attrs = [
        f'name="{escape(tool_id)}"',
        f'node_id="{escape(node.id)}"',
        f'schema_enabled="{_xml_bool(node.state.schema_enabled)}"',
    ]
    if not compact:
        attrs.append(f'state="{node_state_label(node)}"')
    if display_name and display_name != tool_id and not compact:
        attrs.append(f'display_name="{escape(display_name)}"')
    if source_id and not compact:
        attrs.append(f'source_id="{escape(source_id)}"')
    if runtime_key and not compact:
        attrs.append(f'runtime_key="{escape(runtime_key)}"')
    if compact:
        access_label = _metadata_sequence_label(node, "access_requirements")
        if access_label:
            attrs.append(
                f'access="{escape(_truncate_xml_attr(access_label, 96))}"',
            )
    else:
        for attr_name, metadata_key in (
            ("effects", "required_effect_ids"),
            ("access", "access_requirements"),
            ("capabilities", "capability_ids"),
        ):
            label = _metadata_sequence_label(node, metadata_key)
            if label:
                attrs.append(f'{attr_name}="{escape(label)}"')

    children = rendered_children(node, children_by_parent)
    if compact:
        if node.summary and not node.state.schema_enabled:
            attrs.append(f'summary="{escape(_truncate_xml_attr(node.summary, 96))}"')
        if not children:
            lines.append(f"{indent}<tool_function {' '.join(attrs)} />")
            return
        lines.append(f"{indent}<tool_function {' '.join(attrs)}>")
        for child in children:
            append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
        lines.append(f"{indent}</tool_function>")
        return

    lines.append(
        f'{indent}<node id="{escape(node.id)}" kind="{escape(node.kind)}" '
        f'owner="{escape(node.owner)}" state="{node_state_label(node)}" '
        f'actions="{escape(node_actions_label(node))}">',
    )
    lines.append(f"{child_indent}<tool_function {' '.join(attrs)}>")
    if node.summary:
        lines.append(f"{child_indent}  <summary>{escape(node.summary)}</summary>")
    if node.content:
        lines.append(f"{child_indent}  <content>{escape(node.content)}</content>")
    lines.append(f"{child_indent}</tool_function>")
    for child in children:
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def _append_tool_bundle_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
) -> None:
    indent = "  " * depth
    tag_name = "tool_group" if node.kind == "tool_bundle_group" else "tool_bundle"
    attrs = [
        f'node_id="{escape(node.id)}"',
        f'title="{escape(node.title)}"',
        f'state="{node_state_label(node)}"',
    ]
    source_id = _optional_ref_text(node, "source_id")
    group_key = _optional_ref_text(node, "group_key")
    function_count = _optional_ref_text(node, "function_count")
    if source_id is not None:
        attrs.append(f'source_id="{escape(source_id)}"')
    if group_key is not None:
        attrs.append(f'group_key="{escape(group_key)}"')
    if function_count is not None:
        attrs.append(f'functions="{escape(function_count)}"')
    if node.kind == "tool_bundle":
        credential_count = _optional_metadata_text(node, "credential_requirement_count")
        runtime_count = _optional_metadata_text(node, "runtime_requirement_count")
        if credential_count not in {None, "0"}:
            attrs.append(f'credentials="{escape(credential_count)}"')
        if runtime_count not in {None, "0"}:
            attrs.append(f'runtime_requirements="{escape(runtime_count)}"')
    if node.summary:
        summary_limit = 320 if node.kind == "tool_bundle" else 128
        attrs.append(
            f'summary="{escape(_truncate_xml_attr(node.summary, summary_limit))}"',
        )
    children = rendered_children(node, children_by_parent)
    if not children:
        lines.append(f"{indent}<{tag_name} {' '.join(attrs)} />")
        return
    lines.append(f"{indent}<{tag_name} {' '.join(attrs)}>")
    for child in children:
        append_context_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</{tag_name}>")


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
    if node.content:
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


def _browser_evidence_path_ref_line(node: ContextNode) -> str | None:
    evidence = node.metadata.get("tool_result_browser_evidence")
    if not isinstance(evidence, dict):
        return None
    key = _optional_dict_text(evidence, "evidence_path_key")
    title = _optional_dict_text(evidence, "evidence_path_title")
    tools = _text_list(evidence.get("evidence_path_tools"))
    if key is None and title is None and not tools:
        return None
    label = key or title or "browser_evidence"
    if key is not None and title is not None:
        label = f"{key} ({title})"
    if tools:
        label += ": " + ", ".join(tools[:4])
    return label


def _json_fragment(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return str(value)


def _bounded_optional_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return _bounded_text(normalized, limit)


def _bounded_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)].rstrip() + "..."


def _optional_dict_text(mapping: dict[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            return int(normalized)
    return None


def _text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    parts: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized:
            parts.append(normalized)
    return tuple(dict.fromkeys(parts))


def _truncate_xml_attr(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)].rstrip() + "..."


def _optional_metadata_text(node: ContextNode, key: str) -> str | None:
    value = node.metadata.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_ref_text(node: ContextNode, key: str) -> str | None:
    value = node.owner_ref.get(key)
    if value is None:
        value = node.metadata.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _metadata_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return False


def _node_bool_value(node: ContextNode, key: str) -> bool:
    if key in node.owner_ref:
        return _metadata_bool(node.owner_ref[key])
    return _metadata_bool(node.metadata.get(key))


def _metadata_sequence_label(node: ContextNode, key: str) -> str:
    value = node.metadata.get(key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, (list, tuple, set)):
        return str(value).strip()
    parts: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized:
            parts.append(normalized)
    return ", ".join(parts)


def _xml_bool(value: bool) -> str:
    return "true" if value else "false"


__all__ = [
    "append_context_node_xml",
    "children_by_parent_for_nodes",
    "node_actions_label",
    "node_state_label",
    "render_context_node_without_descendants",
    "render_context_tree",
    "rendered_children",
    "sorted_nodes",
    "tree_prompt_visible_nodes",
]
