from __future__ import annotations

from html import escape
from typing import Protocol

from crxzipple.modules.context_workspace.domain import ContextNode

from .xml_renderer_tree import (
    node_actions_label,
    node_content_renderable,
    node_state_label,
    rendered_children,
)
from .xml_renderer_values import (
    append_xml_text_block,
    bounded_optional_text,
    bounded_text,
    json_fragment,
    metadata_sequence_label,
    node_bool_value,
    optional_dict_text,
    optional_int,
    optional_metadata_text,
    optional_ref_text,
    text_list,
    truncate_xml_attr,
    xml_bool,
)


class NodeXmlAppender(Protocol):
    def __call__(
        self,
        lines: list[str],
        node: ContextNode,
        children_by_parent: dict[str | None, list[ContextNode]],
        *,
        depth: int,
    ) -> None: ...


def append_tool_interaction_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
    append_node_xml: NodeXmlAppender,
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
    frontier = node_bool_value(node, "frontier")
    consumed = node_bool_value(node, "consumed")
    failed = node_bool_value(node, "failed")
    observed = node_bool_value(node, "observed")
    verified = node_bool_value(node, "verified")
    superseded = node_bool_value(node, "superseded")
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
            error_summary = optional_metadata_text(node, "error_json")
            if error_summary is not None:
                attrs.append(
                    f'error="{escape(truncate_xml_attr(error_summary, 120))}"',
                )
        if observed:
            attrs.append('observed="true"')
        if verified:
            attrs.append('verified="true"')
        if node.summary:
            attrs.append(f'summary="{escape(truncate_xml_attr(node.summary, 180))}"')
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
            append_node_xml(lines, child, children_by_parent, depth=depth + 1)
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
        f'frontier="{xml_bool(frontier)}" consumed="{xml_bool(consumed)}" '
        f'failed="{xml_bool(failed)}" verified="{xml_bool(verified)}" '
        f'superseded="{xml_bool(superseded)}" '
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
    append_xml_text_block(
        lines,
        "arguments",
        optional_metadata_text(node, "arguments_json"),
        block_indent=block_indent,
        value_indent=value_indent,
    )
    append_xml_text_block(
        lines,
        "error",
        optional_metadata_text(node, "error_json"),
        block_indent=block_indent,
        value_indent=value_indent,
    )
    append_xml_text_block(
        lines,
        "result",
        None if has_result_summary else optional_metadata_text(node, "result_content"),
        block_indent=block_indent,
        value_indent=value_indent,
    )
    lines.append(f"{child_indent}</tool_interaction>")
    for child in rendered_children(node, children_by_parent):
        append_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def append_tool_function_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
    append_node_xml: NodeXmlAppender,
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
        f'schema_enabled="{xml_bool(node.state.schema_enabled)}"',
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
        access_label = metadata_sequence_label(node, "access_requirements")
        if access_label:
            attrs.append(
                f'access="{escape(truncate_xml_attr(access_label, 96))}"',
            )
    else:
        for attr_name, metadata_key in (
            ("effects", "required_effect_ids"),
            ("access", "access_requirements"),
            ("capabilities", "capability_ids"),
        ):
            label = metadata_sequence_label(node, metadata_key)
            if label:
                attrs.append(f'{attr_name}="{escape(label)}"')

    children = rendered_children(node, children_by_parent)
    if compact:
        if node.summary and not node.state.schema_enabled:
            attrs.append(f'summary="{escape(truncate_xml_attr(node.summary, 96))}"')
        if not children:
            lines.append(f"{indent}<tool_function {' '.join(attrs)} />")
            return
        lines.append(f"{indent}<tool_function {' '.join(attrs)}>")
        for child in children:
            append_node_xml(lines, child, children_by_parent, depth=depth + 1)
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
    if node_content_renderable(node):
        lines.append(f"{child_indent}  <content>{escape(node.content)}</content>")
    lines.append(f"{child_indent}</tool_function>")
    for child in children:
        append_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</node>")


def append_tool_bundle_node_xml(
    lines: list[str],
    node: ContextNode,
    children_by_parent: dict[str | None, list[ContextNode]],
    *,
    depth: int,
    append_node_xml: NodeXmlAppender,
) -> None:
    indent = "  " * depth
    tag_name = "tool_group" if node.kind == "tool_bundle_group" else "tool_bundle"
    attrs = [
        f'node_id="{escape(node.id)}"',
        f'title="{escape(node.title)}"',
        f'state="{node_state_label(node)}"',
    ]
    source_id = optional_ref_text(node, "source_id")
    group_key = optional_ref_text(node, "group_key")
    function_count = optional_ref_text(node, "function_count")
    if source_id is not None:
        attrs.append(f'source_id="{escape(source_id)}"')
    if group_key is not None:
        attrs.append(f'group_key="{escape(group_key)}"')
    if function_count is not None:
        attrs.append(f'functions="{escape(function_count)}"')
    if node.kind == "tool_bundle":
        credential_count = optional_metadata_text(node, "credential_requirement_count")
        runtime_count = optional_metadata_text(node, "runtime_requirement_count")
        if credential_count not in {None, "0"}:
            attrs.append(f'credentials="{escape(credential_count)}"')
        if runtime_count not in {None, "0"}:
            attrs.append(f'runtime_requirements="{escape(runtime_count)}"')
    if node.summary:
        summary_limit = 320 if node.kind == "tool_bundle" else 128
        attrs.append(
            f'summary="{escape(truncate_xml_attr(node.summary, summary_limit))}"',
        )
    children = rendered_children(node, children_by_parent)
    if not children:
        lines.append(f"{indent}<{tag_name} {' '.join(attrs)} />")
        return
    lines.append(f"{indent}<{tag_name} {' '.join(attrs)}>")
    for child in children:
        append_node_xml(lines, child, children_by_parent, depth=depth + 1)
    lines.append(f"{indent}</{tag_name}>")


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
    status = optional_dict_text(envelope, "status")
    if status is not None:
        attrs.append(f'status="{escape(truncate_xml_attr(status, 64))}"')
    if envelope.get("truncated") is True:
        attrs.append('truncated="true"')
    omitted_count = optional_int(envelope.get("omitted_count"))
    omitted_chars = optional_int(envelope.get("omitted_chars"))
    if omitted_count is not None:
        attrs.append(f'omitted_count="{omitted_count}"')
    if omitted_chars is not None:
        attrs.append(f'omitted_chars="{omitted_chars}"')
    lines.append(f"{block_indent}<result_summary {' '.join(attrs)}>")
    append_xml_text_block(
        lines,
        "summary",
        bounded_optional_text(envelope.get("summary"), 600),
        block_indent=value_indent,
        value_indent=f"{value_indent}  ",
    )
    key_facts = envelope.get("key_facts")
    if isinstance(key_facts, dict) and key_facts:
        append_xml_text_block(
            lines,
            "key_facts",
            bounded_text(json_fragment(key_facts), 1000),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    artifact_refs = text_list(envelope.get("evidence_refs"))
    if artifact_refs:
        append_xml_text_block(
            lines,
            "artifact_refs",
            ", ".join(artifact_refs),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    read_handles = envelope.get("read_handles")
    if read_handles is not None:
        append_xml_text_block(
            lines,
            "read_handles",
            bounded_text(json_fragment(read_handles), 1200),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    warnings = text_list(envelope.get("warnings"))
    if warnings:
        append_xml_text_block(
            lines,
            "warnings",
            bounded_text("; ".join(warnings), 600),
            block_indent=value_indent,
            value_indent=f"{value_indent}  ",
        )
    lines.append(
        f"{value_indent}<full_result_refs>"
        "artifact refs or read handles are available when needed"
        "</full_result_refs>"
    )
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
            optional_metadata_text(node, "arguments_json"),
            optional_metadata_text(node, "error_json"),
            optional_metadata_text(node, "result_content"),
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
        value = optional_metadata_text(node, metadata_key)
        if value is not None:
            attrs.append(f'{attr_name}="{escape(value)}"')
    if not attrs:
        return
    lines.append(f"{block_indent}<refs {' '.join(attrs)} />")


def _tool_result_envelope(node: ContextNode) -> dict[str, object] | None:
    envelope = node.metadata.get("tool_result_envelope")
    if not isinstance(envelope, dict):
        return None
    return envelope


__all__ = [
    "NodeXmlAppender",
    "append_tool_bundle_node_xml",
    "append_tool_function_node_xml",
    "append_tool_interaction_node_xml",
]
