from __future__ import annotations

from collections import defaultdict
from typing import Any

from crxzipple.modules.operations.application.read_models.context_workspace_row_helpers import (
    estimate_tokens,
    nodes_from_view,
    text,
)


def node_status_rows(
    tree_views: tuple[Any, ...],
    limit: int,
) -> tuple[dict[str, str], ...]:
    grouped: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {
            "total": 0,
            "snapshot_visible": 0,
            "collapsed": 0,
            "pinned": 0,
            "schema_enabled": 0,
            "tokens": 0,
        },
    )
    for view in tree_views:
        workspace = getattr(view, "workspace", None)
        session_key = text(getattr(workspace, "session_key", ""))
        for node in nodes_from_view(view):
            owner = text(getattr(node, "owner", "")) or "-"
            kind = text(getattr(node, "kind", "")) or "-"
            state = getattr(node, "state", None)
            bucket = grouped[(session_key, owner, kind)]
            bucket["total"] += 1
            bucket["tokens"] += estimate_tokens(getattr(node, "estimate", None))
            if bool(getattr(state, "snapshot_visible", False)):
                bucket["snapshot_visible"] += 1
            if bool(getattr(state, "collapsed", True)):
                bucket["collapsed"] += 1
            if bool(getattr(state, "pinned", False)):
                bucket["pinned"] += 1
            if bool(getattr(state, "schema_enabled", False)):
                bucket["schema_enabled"] += 1

    rows: list[dict[str, str]] = []
    for (session_key, owner, kind), counts in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            item[0][2],
        ),
    ):
        rows.append(
            {
                "id": f"{session_key}:{owner}:{kind}",
                "session": session_key,
                "owner": owner,
                "kind": kind,
                "total": str(counts["total"]),
                "snapshot_visible": str(counts["snapshot_visible"]),
                "collapsed": str(counts["collapsed"]),
                "pinned": str(counts["pinned"]),
                "schema_enabled": str(counts["schema_enabled"]),
                "tokens": str(counts["tokens"]),
            },
        )
        if len(rows) >= limit:
            break
    return tuple(rows)
