from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules import (
    OperationsModulePage,
)
from crxzipple.modules.operations.application.read_models.ports import (
    OperationsContextRenderPort,
    OperationsContextTreePort,
    OperationsContextWorkspacePort,
)
from crxzipple.shared.time import format_datetime_utc


@dataclass(frozen=True, slots=True)
class ContextWorkspaceOperationsQuery:
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(slots=True)
class ContextWorkspaceOperationsReadModelProvider:
    workspace_service: OperationsContextWorkspacePort | None
    tree_service: OperationsContextTreePort | None
    render_service: OperationsContextRenderPort | None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(ContextWorkspaceOperationsQuery(limit=40))
        workspaces = _section_rows(page.sections, "workspaces")
        nodes = _section_rows(page.sections, "visible_nodes")
        snapshots = _section_rows(page.sections, "render_snapshots")
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=workspaces,
            lane_locks=nodes,
            executor=snapshots,
            actions=page.actions,
        )

    def page(
        self,
        query: ContextWorkspaceOperationsQuery | None = None,
    ) -> OperationsModulePage:
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        workspaces, workspace_error = _safe_list_workspaces(
            self.workspace_service,
            limit=max(query.limit, 100),
            offset=0,
        )
        filtered = _filter_workspaces(workspaces, query.search)
        visible = filtered[query.offset : query.offset + query.limit]
        tree_views, tree_error = _safe_tree_views(self.tree_service, visible)
        snapshots, snapshot_error = _safe_list_snapshots(
            self.render_service,
            limit=min(max(query.limit, 40), 100),
            offset=0,
        )
        workspace_rows = _workspace_rows(visible, tree_views)
        node_rows = _node_rows(tree_views, query.limit)
        snapshot_rows = _snapshot_rows(snapshots, query.search, query.limit)
        diagnostic_rows = _diagnostic_rows(
            workspace_error=workspace_error,
            tree_error=tree_error,
            snapshot_error=snapshot_error,
        )
        health = _health(
            workspace_service_available=self.workspace_service is not None,
            tree_service_available=self.tree_service is not None,
            render_service_available=self.render_service is not None,
            diagnostic_rows=diagnostic_rows,
        )
        sections = (
            _table_section(
                section_id="workspaces",
                title="Context Workspaces",
                rows=workspace_rows,
                total=len(filtered),
                empty_state="No context workspaces.",
            ),
            _table_section(
                section_id="visible_nodes",
                title="Visible Nodes",
                rows=node_rows,
                total=sum(len(_nodes_from_view(view)) for view in tree_views),
                empty_state="No context nodes.",
            ),
            _table_section(
                section_id="render_snapshots",
                title="Render Snapshots",
                rows=snapshot_rows,
                total=len(_filter_snapshots(snapshots, query.search)),
                empty_state="No context render snapshots.",
            ),
            _table_section(
                section_id="diagnostics",
                title="Diagnostics",
                rows=diagnostic_rows,
                total=len(diagnostic_rows),
                empty_state="No diagnostics.",
            ),
        )
        return OperationsModulePage(
            module="context_workspace",
            title="Context Workspace",
            subtitle="观察会话绑定的 Prompt Tree、可见节点、估算体积与渲染快照。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Context Workspace operator",
                can_operate=True,
                scope="context_workspace",
            ),
            metrics=_metrics(
                health=health,
                workspaces=filtered,
                tree_views=tree_views,
                snapshots=snapshots,
            ),
            tabs=tuple(
                OperationsTabModel(
                    id=section.id,
                    label=section.title,
                    count=section.total,
                )
                for section in sections
            ),
            active_tab="workspaces",
            actions=(
                RuntimeActionModel(
                    id="open_context_tree",
                    label="Open Context Tree",
                    owner="context_workspace",
                    kind="navigation",
                    allowed=True,
                ),
            ),
            sections=sections,
        )


def _normalize_query(
    query: ContextWorkspaceOperationsQuery | None,
) -> ContextWorkspaceOperationsQuery:
    if query is None:
        return ContextWorkspaceOperationsQuery()
    return ContextWorkspaceOperationsQuery(
        search=_text(query.search),
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _safe_list_workspaces(
    service: OperationsContextWorkspacePort | None,
    *,
    limit: int,
    offset: int,
) -> tuple[tuple[Any, ...], str | None]:
    if service is None:
        return (), "Context Workspace service is not available."
    try:
        return tuple(service.list_workspaces(limit=limit, offset=offset)), None
    except Exception as exc:
        return (), str(exc)


def _safe_tree_views(
    service: OperationsContextTreePort | None,
    workspaces: tuple[Any, ...],
) -> tuple[tuple[Any, ...], str | None]:
    if service is None:
        return (), "Context Tree service is not available."
    views: list[Any] = []
    for workspace in workspaces:
        session_key = _text(getattr(workspace, "session_key", ""))
        if not session_key:
            continue
        try:
            views.append(service.list_tree(session_key))
        except Exception as exc:
            return tuple(views), str(exc)
    return tuple(views), None


def _safe_list_snapshots(
    service: OperationsContextRenderPort | None,
    *,
    limit: int,
    offset: int,
) -> tuple[tuple[Any, ...], str | None]:
    if service is None:
        return (), "Context Render service is not available."
    try:
        return tuple(service.list_recent_snapshots(limit=limit, offset=offset)), None
    except Exception as exc:
        return (), str(exc)


def _filter_workspaces(
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
                _text(getattr(workspace, "id", "")),
                _text(getattr(workspace, "session_key", "")),
                _text(getattr(workspace, "agent_id", "")),
                _text(getattr(workspace, "status", "")),
            ),
        ).lower()
    )


def _filter_snapshots(
    snapshots: tuple[Any, ...],
    search: str,
) -> tuple[Any, ...]:
    if not search:
        return snapshots
    needle = search.lower()
    return tuple(
        snapshot
        for snapshot in snapshots
        if needle
        in " ".join(
            (
                _text(getattr(snapshot, "id", "")),
                _text(getattr(snapshot, "run_id", "")),
                _text(getattr(snapshot, "session_key", "")),
                _text(getattr(snapshot, "workspace_id", "")),
            ),
        ).lower()
    )


def _workspace_rows(
    workspaces: tuple[Any, ...],
    tree_views: tuple[Any, ...],
) -> tuple[dict[str, str], ...]:
    views_by_workspace = {
        _text(getattr(getattr(view, "workspace", None), "id", "")): view
        for view in tree_views
    }
    rows: list[dict[str, str]] = []
    for workspace in workspaces:
        workspace_id = _text(getattr(workspace, "id", ""))
        nodes = _nodes_from_view(views_by_workspace.get(workspace_id))
        prompt_nodes = [node for node in nodes if bool(getattr(node.state, "prompt_visible", False))]
        rows.append(
            {
                "id": workspace_id,
                "session": _text(getattr(workspace, "session_key", "")),
                "agent": _text(getattr(workspace, "agent_id", "")),
                "status": _text(getattr(workspace, "status", "")),
                "revision": str(getattr(workspace, "active_revision", "")),
                "nodes": str(len(nodes)),
                "prompt_nodes": str(len(prompt_nodes)),
                "tokens": str(sum(_estimate_tokens(getattr(node, "estimate", None)) for node in prompt_nodes)),
                "updated": _format_time(getattr(workspace, "updated_at", None)),
            },
        )
    return tuple(rows)


def _node_rows(
    tree_views: tuple[Any, ...],
    limit: int,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for view in tree_views:
        workspace = getattr(view, "workspace", None)
        session_key = _text(getattr(workspace, "session_key", ""))
        for node in _nodes_from_view(view):
            rows.append(
                {
                    "id": f"{session_key}:{_text(getattr(node, 'id', ''))}",
                    "session": session_key,
                    "node": _text(getattr(node, "id", "")),
                    "title": _text(getattr(node, "title", "")),
                    "owner": _text(getattr(node, "owner", "")),
                    "kind": _text(getattr(node, "kind", "")),
                    "state": _node_state_label(node),
                    "tokens": str(_estimate_tokens(getattr(node, "estimate", None))),
                    "updated": _format_time(getattr(node, "updated_at", None)),
                },
            )
            if len(rows) >= limit:
                return tuple(rows)
    return tuple(rows)


def _snapshot_rows(
    snapshots: tuple[Any, ...],
    search: str,
    limit: int,
) -> tuple[dict[str, str], ...]:
    filtered = _filter_snapshots(snapshots, search)
    return tuple(
        {
            "id": _text(getattr(snapshot, "id", "")),
            "run": _text(getattr(snapshot, "run_id", "")),
            "session": _text(getattr(snapshot, "session_key", "")),
            "revision": str(getattr(snapshot, "tree_revision", "")),
            "included_nodes": str(len(tuple(getattr(snapshot, "included_node_ids", ())))),
            "mirrored_nodes": str(len(tuple(getattr(snapshot, "mirrored_node_ids", ())))),
            "tokens": str(_estimate_tokens(getattr(snapshot, "estimate", None))),
            "prompt_chars": str(len(_text(getattr(snapshot, "prompt_body", "")))),
            "created": _format_time(getattr(snapshot, "created_at", None)),
        }
        for snapshot in filtered[:limit]
    )


def _diagnostic_rows(
    *,
    workspace_error: str | None,
    tree_error: str | None,
    snapshot_error: str | None,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for key, error in (
        ("workspaces", workspace_error),
        ("tree", tree_error),
        ("render_snapshots", snapshot_error),
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


def _metrics(
    *,
    health: str,
    workspaces: tuple[Any, ...],
    tree_views: tuple[Any, ...],
    snapshots: tuple[Any, ...],
) -> tuple[MetricCardModel, ...]:
    nodes = tuple(node for view in tree_views for node in _nodes_from_view(view))
    prompt_nodes = tuple(
        node for node in nodes if bool(getattr(node.state, "prompt_visible", False))
    )
    pinned_nodes = tuple(node for node in nodes if bool(getattr(node.state, "pinned", False)))
    token_total = sum(
        _estimate_tokens(getattr(snapshot, "estimate", None))
        for snapshot in snapshots[:20]
    )
    return (
        MetricCardModel("health", "Health", health.title(), "context tree", _tone(health)),
        MetricCardModel(
            "workspaces",
            "Workspaces",
            str(len(workspaces)),
            "recent sessions",
            "info",
        ),
        MetricCardModel(
            "nodes",
            "Visible Nodes",
            str(len(nodes)),
            f"{len(prompt_nodes)} prompt-visible",
            "info",
        ),
        MetricCardModel(
            "pinned",
            "Pinned",
            str(len(pinned_nodes)),
            "agent/user pinned nodes",
            "success" if pinned_nodes else "neutral",
        ),
        MetricCardModel(
            "snapshots",
            "Render Snapshots",
            str(len(snapshots)),
            "recent prompt renders",
            "info",
        ),
        MetricCardModel(
            "snapshot_tokens",
            "Snapshot Tokens",
            str(token_total),
            "recent estimated tokens",
            "info",
        ),
    )


def _health(
    *,
    workspace_service_available: bool,
    tree_service_available: bool,
    render_service_available: bool,
    diagnostic_rows: tuple[dict[str, str], ...],
) -> str:
    if diagnostic_rows:
        return "error"
    if not (
        workspace_service_available
        and tree_service_available
        and render_service_available
    ):
        return "warning"
    return "healthy"


def _table_section(
    *,
    section_id: str,
    title: str,
    rows: tuple[dict[str, str], ...],
    total: int,
    empty_state: str,
) -> OperationsTableSectionModel:
    keys = _table_keys(rows)
    return OperationsTableSectionModel(
        id=section_id,
        title=title,
        columns=tuple(
            OperationsTableColumnModel(
                key=key,
                label=" ".join(part.capitalize() for part in key.split("_")),
            )
            for key in keys
        ),
        rows=tuple(
            OperationsTableRowModel(
                id=row.get("id", f"{section_id}:{index}"),
                cells={key: row.get(key, "") for key in keys},
                status=row.get("status"),
                tone=_row_tone(row),
            )
            for index, row in enumerate(rows)
        ),
        total=total,
        view_all_route=f"/operations/context_workspace?tab={section_id}",
        empty_state=empty_state,
    )


def _table_keys(rows: tuple[dict[str, str], ...]) -> tuple[str, ...]:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key == "id" or key in keys:
                continue
            keys.append(key)
    return tuple(keys)


def _section_rows(
    sections: tuple[OperationsTableSectionModel, ...],
    section_id: str,
) -> tuple[dict[str, str], ...]:
    for section in sections:
        if section.id == section_id:
            return tuple(dict(row.cells) for row in section.rows)
    return ()


def _nodes_from_view(view: Any | None) -> tuple[Any, ...]:
    if view is None:
        return ()
    return tuple(getattr(view, "nodes", ()) or ())


def _node_state_label(node: Any) -> str:
    state = getattr(node, "state", None)
    labels: list[str] = []
    if bool(getattr(state, "pinned", False)):
        labels.append("pinned")
    if bool(getattr(state, "schema_enabled", False)):
        labels.append("schema")
    labels.append("visible" if bool(getattr(state, "prompt_visible", False)) else "hidden")
    labels.append("collapsed" if bool(getattr(state, "collapsed", True)) else "expanded")
    return ", ".join(labels)


def _estimate_tokens(estimate: Any | None) -> int:
    if estimate is None:
        return 0
    return (
        int(getattr(estimate, "text_tokens", 0) or 0)
        + int(getattr(estimate, "tool_schema_tokens", 0) or 0)
        + int(getattr(estimate, "file_tokens", 0) or 0)
    )


def _format_time(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return format_datetime_utc(value)
    except Exception:
        return str(value)


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _tone(health: str) -> str:
    if health == "healthy":
        return "success"
    if health == "error":
        return "danger"
    return "warning"


def _row_tone(row: dict[str, str]) -> str:
    status = row.get("status", "").lower()
    if status in {"active", "healthy", "visible"}:
        return "success"
    if status in {"warning", "collapsed"}:
        return "warning"
    if status in {"error", "failed"}:
        return "danger"
    return "neutral"
