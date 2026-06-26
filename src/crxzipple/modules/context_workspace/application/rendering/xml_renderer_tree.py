from __future__ import annotations

from crxzipple.modules.context_workspace.domain import ContextNode

_HANDLE_ONLY_CONTENT_OWNERS = frozenset(
    {
        "tool",
        "skills",
        "memory",
        "artifacts",
        "workspace",
        "agent",
    },
)


def node_content_renderable(node: ContextNode) -> bool:
    return bool(node.content) and node.owner not in _HANDLE_ONLY_CONTENT_OWNERS


def tree_snapshot_visible_nodes(nodes: tuple[ContextNode, ...]) -> tuple[ContextNode, ...]:
    snapshot_nodes = tuple(node for node in nodes if node.state.snapshot_visible)
    children_by_parent = children_by_parent_for_nodes(snapshot_nodes)
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


__all__ = [
    "children_by_parent_for_nodes",
    "node_actions_label",
    "node_content_renderable",
    "node_state_label",
    "rendered_children",
    "sorted_nodes",
    "tree_snapshot_visible_nodes",
]
