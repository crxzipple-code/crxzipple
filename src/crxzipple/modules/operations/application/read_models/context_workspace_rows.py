from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.context_workspace_row_helpers import (
    estimate_tokens,
    format_time,
    metadata,
    metadata_int,
    nodes_from_view,
    short_text,
    text,
)


def operations_slice_row(context_slice: Any, *, session_key: str) -> dict[str, str]:
    payload = context_slice.to_payload()
    report = metadata(payload.get("report"))
    loss = metadata(report.get("loss"))
    budget = metadata(report.get("budget"))
    items = payload.get("items")
    active_tools = payload.get("active_tools")
    return {
        "id": text(payload.get("slice_id")),
        "slice": short_text(text(payload.get("slice_id")), max_length=32),
        "audience": text(payload.get("audience")),
        "session": session_key,
        "run": short_text(text(payload.get("run_id"))),
        "revision": str(payload.get("tree_revision") or ""),
        "items": str(len(items) if isinstance(items, (list, tuple)) else 0),
        "active_tools": str(
            len(active_tools) if isinstance(active_tools, (list, tuple)) else 0,
        ),
        "included": str(metadata_int(report, "included_count")),
        "omitted": str(metadata_int(report, "omitted_count")),
        "collapsed": str(metadata_int(loss, "collapsed_ref_count")),
        "unresolved": str(metadata_int(loss, "unresolved_ref_count")),
        "tokens": str(metadata_int(budget, "text_tokens")),
    }


def filter_workspaces(
    workspaces: tuple[Any, ...],
    search: str,
) -> tuple[Any, ...]:
    if not search:
        return workspaces
    needle = search.lower()
    return tuple(
        workspace
        for workspace in workspaces
        if needle
        in " ".join(
            (
                text(getattr(workspace, "id", "")),
                text(getattr(workspace, "session_key", "")),
                text(getattr(workspace, "agent_id", "")),
                text(getattr(workspace, "status", "")),
            ),
        ).lower()
    )


def workspace_rows(
    workspaces: tuple[Any, ...],
    tree_views: tuple[Any, ...],
) -> tuple[dict[str, str], ...]:
    views_by_workspace = {
        text(getattr(getattr(view, "workspace", None), "id", "")): view
        for view in tree_views
    }
    rows: list[dict[str, str]] = []
    for workspace in workspaces:
        workspace_id = text(getattr(workspace, "id", ""))
        nodes = nodes_from_view(views_by_workspace.get(workspace_id))
        snapshot_nodes = [
            node for node in nodes if bool(getattr(node.state, "snapshot_visible", False))
        ]
        rows.append(
            {
                "id": workspace_id,
                "session": text(getattr(workspace, "session_key", "")),
                "agent": text(getattr(workspace, "agent_id", "")),
                "status": text(getattr(workspace, "status", "")),
                "revision": str(getattr(workspace, "active_revision", "")),
                "nodes": str(len(nodes)),
                "snapshot_nodes": str(len(snapshot_nodes)),
                "tokens": str(
                    sum(
                        estimate_tokens(getattr(node, "estimate", None))
                        for node in snapshot_nodes
                    ),
                ),
                "updated": format_time(getattr(workspace, "updated_at", None)),
            },
        )
    return tuple(rows)


def node_rows(
    tree_views: tuple[Any, ...],
    limit: int,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for view in tree_views:
        workspace = getattr(view, "workspace", None)
        session_key = text(getattr(workspace, "session_key", ""))
        for node in nodes_from_view(view):
            rows.append(
                {
                    "id": f"{session_key}:{text(getattr(node, 'id', ''))}",
                    "session": session_key,
                    "node": text(getattr(node, "id", "")),
                    "title": text(getattr(node, "title", "")),
                    "owner": text(getattr(node, "owner", "")),
                    "kind": text(getattr(node, "kind", "")),
                    "state": _node_state_label(node),
                    "tokens": str(estimate_tokens(getattr(node, "estimate", None))),
                    "updated": format_time(getattr(node, "updated_at", None)),
                },
            )
            if len(rows) >= limit:
                return tuple(rows)
    return tuple(rows)


def diagnostic_rows(
    *,
    workspace_error: str | None,
    tree_error: str | None,
    snapshot_error: str | None,
    slice_error: str | None,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for key, error in (
        ("workspaces", workspace_error),
        ("tree", tree_error),
        ("snapshots", snapshot_error),
        ("observation_slices", slice_error),
    ):
        if error:
            rows.append(
                {
                    "id": key,
                    "component": key,
                    "status": "error",
                    "message": error,
                },
            )
    return tuple(rows)


def _node_state_label(node: Any) -> str:
    state = getattr(node, "state", None)
    labels: list[str] = []
    if bool(getattr(state, "pinned", False)):
        labels.append("pinned")
    if bool(getattr(state, "schema_enabled", False)):
        labels.append("schema")
    labels.append("visible" if bool(getattr(state, "snapshot_visible", False)) else "hidden")
    labels.append("collapsed" if bool(getattr(state, "collapsed", True)) else "expanded")
    return ", ".join(labels)
