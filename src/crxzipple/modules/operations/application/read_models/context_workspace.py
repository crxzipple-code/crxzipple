from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.context_workspace.application import BuildContextObservationSliceInput
from crxzipple.modules.context_workspace.domain import ContextWorkspaceNotFoundError
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
    OperationsContextObservationSnapshotPort,
    OperationsContextSliceBuilderPort,
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
    observation_snapshot_service: OperationsContextObservationSnapshotPort | None
    slice_builder: OperationsContextSliceBuilderPort | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(ContextWorkspaceOperationsQuery(limit=40))
        workspaces = _section_rows(page.sections, "workspaces")
        nodes = _section_rows(page.sections, "visible_nodes")
        snapshots = _section_rows(page.sections, "snapshots")
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
            self.observation_snapshot_service,
            limit=min(max(query.limit, 40), 100),
            offset=0,
        )
        slice_rows, slice_error = _safe_operations_slice_rows(
            self.slice_builder,
            visible,
            snapshots,
            limit=query.limit,
        )
        workspace_rows = _workspace_rows(visible, tree_views)
        node_rows = _node_rows(tree_views, query.limit)
        node_status_rows = _node_status_rows(tree_views, query.limit)
        snapshot_rows = _snapshot_rows(snapshots, query.search, query.limit)
        context_budget_rows = _context_budget_rows(snapshots, query.search, query.limit)
        diagnostic_rows = _diagnostic_rows(
            workspace_error=workspace_error,
            tree_error=tree_error,
            snapshot_error=snapshot_error,
            slice_error=slice_error,
        )
        health = _health(
            workspace_service_available=self.workspace_service is not None,
            tree_service_available=self.tree_service is not None,
            observation_snapshot_service_available=self.observation_snapshot_service is not None,
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
                section_id="node_status",
                title="Node Status",
                rows=node_status_rows,
                total=len(_node_status_rows(tree_views, 10_000)),
                empty_state="No context node status.",
            ),
            _table_section(
                section_id="snapshots",
                title="Context Snapshots",
                rows=snapshot_rows,
                total=len(_filter_snapshots(snapshots, query.search)),
                empty_state="No context snapshots.",
            ),
            _table_section(
                section_id="context_budget",
                title="Context Budget",
                rows=context_budget_rows,
                total=len(_filter_snapshots(snapshots, query.search)),
                empty_state="No context budget snapshots.",
            ),
            _table_section(
                section_id="observation_slices",
                title="Observation Slices",
                rows=slice_rows,
                total=len(slice_rows),
                empty_state="No operations projection slices.",
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
            subtitle="观察会话绑定的 Context Tree、可见节点、估算体积与上下文快照。",
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
                slice_rows=slice_rows,
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
    service: OperationsContextObservationSnapshotPort | None,
    *,
    limit: int,
    offset: int,
) -> tuple[tuple[Any, ...], str | None]:
    if service is None:
        return (), "Context observation snapshot service is not available."
    try:
        return tuple(service.list_recent_snapshots(limit=limit, offset=offset)), None
    except Exception as exc:
        return (), str(exc)


def _safe_operations_slice_rows(
    builder: OperationsContextSliceBuilderPort | None,
    workspaces: tuple[Any, ...],
    snapshots: tuple[Any, ...],
    *,
    limit: int,
) -> tuple[tuple[dict[str, str], ...], str | None]:
    if builder is None:
        return (), "Context Slice Builder service is not available."
    latest_run_by_session = _latest_run_by_session(snapshots)
    rows: list[dict[str, str]] = []
    for workspace in workspaces:
        session_key = _text(getattr(workspace, "session_key", ""))
        if not session_key:
            continue
        run_id = latest_run_by_session.get(session_key, "")
        try:
            context_slice = builder.build_slice(
                data=BuildContextObservationSliceInput(
                    session_key=session_key,
                    run_id=run_id,
                    audience="operations_projection",
                    metadata={"surface": "operations"},
                ),
            )
        except ContextWorkspaceNotFoundError:
            continue
        except Exception as exc:
            return tuple(rows), str(exc)
        rows.append(_operations_slice_row(context_slice, session_key=session_key))
        if len(rows) >= limit:
            break
    return tuple(rows), None


def _latest_run_by_session(snapshots: tuple[Any, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for snapshot in snapshots:
        session_key = _text(getattr(snapshot, "session_key", ""))
        run_id = _text(getattr(snapshot, "run_id", ""))
        if session_key and run_id and session_key not in result:
            result[session_key] = run_id
    return result


def _operations_slice_row(context_slice: Any, *, session_key: str) -> dict[str, str]:
    payload = context_slice.to_payload()
    report = _metadata(payload.get("report"))
    loss = _metadata(report.get("loss"))
    budget = _metadata(report.get("budget"))
    items = payload.get("items")
    active_tools = payload.get("active_tools")
    return {
        "id": _text(payload.get("slice_id")),
        "slice": _short_text(_text(payload.get("slice_id")), max_length=32),
        "audience": _text(payload.get("audience")),
        "session": session_key,
        "run": _short_text(_text(payload.get("run_id"))),
        "revision": str(payload.get("tree_revision") or ""),
        "items": str(len(items) if isinstance(items, (list, tuple)) else 0),
        "active_tools": str(
            len(active_tools) if isinstance(active_tools, (list, tuple)) else 0,
        ),
        "included": str(_metadata_int(report, "included_count")),
        "omitted": str(_metadata_int(report, "omitted_count")),
        "collapsed": str(_metadata_int(loss, "collapsed_ref_count")),
        "unresolved": str(_metadata_int(loss, "unresolved_ref_count")),
        "tokens": str(_metadata_int(budget, "text_tokens")),
    }


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
        snapshot_nodes = [
            node for node in nodes if bool(getattr(node.state, "snapshot_visible", False))
        ]
        rows.append(
            {
                "id": workspace_id,
                "session": _text(getattr(workspace, "session_key", "")),
                "agent": _text(getattr(workspace, "agent_id", "")),
                "status": _text(getattr(workspace, "status", "")),
                "revision": str(getattr(workspace, "active_revision", "")),
                "nodes": str(len(nodes)),
                "snapshot_nodes": str(len(snapshot_nodes)),
                "tokens": str(
                    sum(_estimate_tokens(getattr(node, "estimate", None)) for node in snapshot_nodes),
                ),
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


def _node_status_rows(
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
        session_key = _text(getattr(workspace, "session_key", ""))
        for node in _nodes_from_view(view):
            owner = _text(getattr(node, "owner", "")) or "-"
            kind = _text(getattr(node, "kind", "")) or "-"
            state = getattr(node, "state", None)
            bucket = grouped[(session_key, owner, kind)]
            bucket["total"] += 1
            bucket["tokens"] += _estimate_tokens(getattr(node, "estimate", None))
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


def _snapshot_rows(
    snapshots: tuple[Any, ...],
    search: str,
    limit: int,
) -> tuple[dict[str, str], ...]:
    filtered = _filter_snapshots(snapshots, search)
    rows: list[dict[str, str]] = []
    for snapshot in filtered[:limit]:
        metadata = _metadata(getattr(snapshot, "metadata", None))
        session_item_refs = _metadata_list(
            metadata,
            "session_item_node_refs",
        )
        rows.append(
            {
                "id": _text(getattr(snapshot, "id", "")),
                "run": _text(getattr(snapshot, "run_id", "")),
                "session": _text(getattr(snapshot, "session_key", "")),
                "revision": str(getattr(snapshot, "tree_revision", "")),
                "history": _text(metadata.get("history_delivery") or "-"),
                "provider_messages": str(
                    _metadata_int(metadata, "draft_input_message_count"),
                ),
                "tree_items": str(
                    _metadata_int(metadata, "tree_session_item_count"),
                ),
                "tool_interactions": str(
                    _metadata_int(metadata, "tree_tool_interaction_count"),
                ),
                "evidence": str(
                    _metadata_int(metadata, "tree_evidence_item_count"),
                ),
                "folded": str(_metadata_int(metadata, "folded_history_node_count")),
                "session_tokens": str(
                    _metadata_int(metadata, "session_estimated_text_tokens"),
                ),
                "range_warnings": str(
                    _metadata_int(metadata, "session_range_warning_count"),
                ),
                "range_blocked": str(
                    _metadata_int(metadata, "session_range_blocked_count"),
                ),
                "range_limited": str(
                    _metadata_int(metadata, "session_range_limited_count"),
                ),
                "session_refs": str(len(session_item_refs)),
                "current_node": _short_text(
                    _text(metadata.get("current_inbound_node_id")),
                ),
                "included_nodes": str(
                    len(tuple(getattr(snapshot, "included_node_ids", ()))),
                ),
                "mirrored_nodes": str(
                    len(tuple(getattr(snapshot, "mirrored_node_ids", ()))),
                ),
                "tokens": str(_estimate_tokens(getattr(snapshot, "estimate", None))),
                "prompt_chars": str(len(_text(getattr(snapshot, "debug_body", "")))),
                "created": _format_time(getattr(snapshot, "created_at", None)),
            },
        )
    return tuple(rows)


def _context_budget_rows(
    snapshots: tuple[Any, ...],
    search: str,
    limit: int,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for snapshot in _filter_snapshots(snapshots, search)[:limit]:
        metadata = _metadata(getattr(snapshot, "metadata", None))
        rows.append(
            {
                "id": _text(getattr(snapshot, "id", "")),
                "run": _text(getattr(snapshot, "run_id", "")),
                "session": _text(getattr(snapshot, "session_key", "")),
                "provider_tokens": str(_snapshot_provider_tokens(snapshot)),
                "tree_tokens": str(_snapshot_rendered_tokens(snapshot)),
                "draft_input_tokens": str(
                    _metadata_int(metadata, "draft_input_estimated_tokens"),
                ),
                "schema_tokens": str(
                    _metadata_int(metadata, "mirrored_tool_schema_estimated_tokens"),
                ),
                "schema_budget_status": _text(
                    metadata.get("tool_schema_mirror_budget_status") or "ok",
                ),
                "schema_budget_skipped": str(
                    _metadata_int(metadata, "tool_schema_mirror_skipped_count"),
                ),
                "provider_messages": str(
                    _metadata_int(metadata, "draft_input_message_count"),
                ),
                "mirrored_schemas": str(
                    len(tuple(getattr(snapshot, "mirrored_node_ids", ()))),
                ),
                "duplicate_risk": "yes"
                if bool(metadata.get("duplicate_tool_delivery_risk"))
                else "no",
                "created": _format_time(getattr(snapshot, "created_at", None)),
            },
        )
    return tuple(rows)


def _diagnostic_rows(
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


def _metrics(
    *,
    health: str,
    workspaces: tuple[Any, ...],
    tree_views: tuple[Any, ...],
    snapshots: tuple[Any, ...],
    slice_rows: tuple[dict[str, str], ...],
) -> tuple[MetricCardModel, ...]:
    nodes = tuple(node for view in tree_views for node in _nodes_from_view(view))
    snapshot_visible_nodes = tuple(
        node for node in nodes if bool(getattr(node.state, "snapshot_visible", False))
    )
    pinned_nodes = tuple(node for node in nodes if bool(getattr(node.state, "pinned", False)))
    token_total = sum(_snapshot_provider_tokens(snapshot) for snapshot in snapshots[:20])
    range_risk_count = sum(
        _snapshot_session_range_risk_count(snapshot)
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
            f"{len(snapshot_visible_nodes)} snapshot-visible",
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
            "Context Snapshots",
            str(len(snapshots)),
            "recent context snapshots",
            "info",
        ),
        MetricCardModel(
            "snapshot_tokens",
            "Provider Wire Tokens",
            str(token_total),
            "recent provider estimate",
            "info",
        ),
        MetricCardModel(
            "session_range_risks",
            "Session Range Risks",
            str(range_risk_count),
            "recent hidden/split/blocked ranges",
            "warning" if range_risk_count else "success",
        ),
        MetricCardModel(
            "observation_slices",
            "Observation Slices",
            str(len(slice_rows)),
            "operations projection slices",
            "success" if slice_rows else "neutral",
        ),
    )


def _health(
    *,
    workspace_service_available: bool,
    tree_service_available: bool,
    observation_snapshot_service_available: bool,
    diagnostic_rows: tuple[dict[str, str], ...],
) -> str:
    if diagnostic_rows:
        return "error"
    if not (
        workspace_service_available
        and tree_service_available
        and observation_snapshot_service_available
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
    labels.append("visible" if bool(getattr(state, "snapshot_visible", False)) else "hidden")
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


def _short_text(value: str, *, max_length: int = 40) -> str:
    if not value:
        return "-"
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def _metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metadata_int(metadata: dict[str, Any], key: str) -> int:
    value = metadata.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _snapshot_session_range_risk_count(snapshot: Any) -> int:
    metadata = _metadata(getattr(snapshot, "metadata", None))
    return (
        _metadata_int(metadata, "session_range_warning_count")
        + _metadata_int(metadata, "session_range_blocked_count")
        + _metadata_int(metadata, "session_range_limited_count")
    )


def _snapshot_provider_tokens(snapshot: Any) -> int:
    metadata = _metadata(getattr(snapshot, "metadata", None))
    value = _metadata_int(metadata, "estimated_provider_input_tokens")
    if value:
        return value
    return _estimate_tokens(getattr(snapshot, "estimate", None))


def _snapshot_rendered_tokens(snapshot: Any) -> int:
    metadata = _metadata(getattr(snapshot, "metadata", None))
    value = _metadata_int(metadata, "debug_body_estimated_tokens")
    if value:
        return value
    rendered_estimate = metadata.get("debug_body_estimate")
    if isinstance(rendered_estimate, dict):
        return _metadata_int(rendered_estimate, "text_tokens")
    return _estimate_tokens(getattr(snapshot, "estimate", None))


def _metadata_list(metadata: dict[str, Any], key: str) -> tuple[Any, ...]:
    value = metadata.get(key)
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, tuple):
        return value
    return ()


def _text_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(item for item in (_text(item) for item in value) if item)
    text = _text(value)
    return (text,) if text else ()


def _row_matches_search(row: dict[str, str], search: str) -> bool:
    if not search:
        return True
    needle = search.lower()
    return needle in " ".join(str(value) for value in row.values()).lower()


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
